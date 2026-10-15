"""Order reconciliation - v1 + v2 contracts (spec-v1.md, spec-v2.md).

Pure functions only. Inputs are UTF-8 CSV strings; monetary outputs are integer cents
computed with decimal fixed-point (never float * 100).
"""

import csv
import datetime
import decimal
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_FIELDS = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_FIELDS_V1 = ("refund_id", "order_id", "amount")
_REFUND_FIELDS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")


def _validate_cutoff(cutoff):
    if cutoff is None:
        raise ValueError("policy v2 requires a cutoff")
    if not isinstance(cutoff, str) or len(cutoff) != 20 or not cutoff.endswith("Z"):
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ, got %r" % (cutoff,))
    try:
        datetime.datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("cutoff is not a valid UTC timestamp: %r" % (cutoff,))
    return cutoff


def _amount_to_cents(text, context, policy):
    """Parse a non-negative decimal amount to integer cents.

    v1: at most two decimal places.
    v2: any number of decimals, rounded to cents with ROUND_HALF_UP.
    """
    if text is None:
        raise ValueError("%s: missing amount" % context)
    s = text.strip()
    if s == "":
        raise ValueError("%s: empty amount" % context)
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, text))
    if not d.is_finite():
        raise ValueError("%s: non-finite amount %r" % (context, text))
    if d < 0:
        raise ValueError("%s: negative amount %r" % (context, text))
    if policy == "v1":
        exponent = d.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("%s: more than two decimal places %r" % (context, text))
        cents = d * 100
        if cents != cents.to_integral_value():
            raise ValueError("%s: not an integral number of cents %r" % (context, text))
        return int(cents)
    cents = (d * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _read_rows(csv_text, expected_fields, name):
    """Read CSV text into dicts; require the exact expected header."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        raise ValueError("%s CSV is missing a header row" % name)
    header = tuple(reader.fieldnames)
    if header != expected_fields:
        raise ValueError(
            "%s CSV header must be %s, got %s" % (name, list(expected_fields), list(header))
        )
    rows = []
    for row in reader:
        if row.get(None):
            raise ValueError("%s CSV row has too many columns: %r" % (name, row))
        missing = [f for f in expected_fields if row.get(f) is None]
        if missing:
            raise ValueError("%s CSV row missing fields %s: %r" % (name, missing, row))
        rows.append(row)
    return rows


def _dedupe(rows, id_field, name):
    """Deduplicate rows by id: exact duplicates collapse; conflicting rows raise.

    Applies to every row regardless of status or timestamp.
    """
    seen = {}
    unique = []
    for row in rows:
        key = row[id_field]
        if key in seen:
            if seen[key] != row:
                raise ValueError(
                    "%s %s appears with conflicting data: %r vs %r"
                    % (name, key, seen[key], row)
                )
            continue
        seen[key] = row
        unique.append(row)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v1":
        cutoff = None  # v1 ignores cutoff entirely.
    else:
        _validate_cutoff(cutoff)

    order_rows = _dedupe(_read_rows(orders_csv, _ORDER_FIELDS, "orders"), "order_id", "order")
    refund_fields = _REFUND_FIELDS_V1 if policy == "v1" else _REFUND_FIELDS_V2
    refund_rows = _dedupe(_read_rows(refunds_csv, refund_fields, "refunds"), "refund_id", "refund")

    orders = {}
    for row in order_rows:
        order_id = row["order_id"]
        if order_id == "":
            raise ValueError("order row with empty order_id")
        status = row["status"]
        if status not in ("paid", "cancelled"):
            raise ValueError("unknown order status %r for order %s" % (status, order_id))
        created_at = row["created_at"]
        if policy == "v2" and created_at == "":
            raise ValueError("order %s has empty created_at" % order_id)
        orders[order_id] = {
            "order_id": order_id,
            "customer": row["customer"],
            "status": status,
            "created_at": created_at,
            "paid_cents": _amount_to_cents(row["amount"], "order %s" % order_id, policy),
        }

    def _order_included(order):
        if order["status"] != "paid":
            return False
        if policy == "v2" and order["created_at"] > cutoff:
            return False
        return True

    refund_by_order = {}
    for row in refund_rows:
        refund_id = row["refund_id"]
        order_id = row["order_id"]

        if policy == "v2":
            status = row["status"]
            if status not in ("succeeded", "pending"):
                raise ValueError("unknown refund status %r for refund %s" % (status, refund_id))
            created_at = row["created_at"]
            if created_at == "":
                raise ValueError("refund %s has empty created_at" % refund_id)
            # pending or after-cutoff refunds never count and never validate orders.
            if status != "succeeded" or created_at > cutoff:
                continue

        order = orders.get(order_id)
        if order is None:
            raise ValueError("refund %s references unknown order %s" % (refund_id, order_id))
        if order["status"] == "cancelled":
            raise ValueError("refund %s references cancelled order %s" % (refund_id, order_id))
        if policy == "v2" and order["created_at"] > cutoff:
            # Order exists and is paid but is excluded by the cutoff: ignore the refund.
            continue

        cents = _amount_to_cents(row["amount"], "refund %s" % refund_id, policy)
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + cents

    for order_id, refunded in refund_by_order.items():
        if refunded > orders[order_id]["paid_cents"]:
            raise ValueError(
                "refunds (%d cents) exceed paid amount (%d cents) for order %s"
                % (refunded, orders[order_id]["paid_cents"], order_id)
            )

    result_orders = []
    customer_totals = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(orders):
        order = orders[order_id]
        if not _order_included(order):
            continue
        paid = order["paid_cents"]
        refunded = refund_by_order.get(order_id, 0)
        net = paid - refunded
        result_orders.append(
            {
                "order_id": order_id,
                "customer": order["customer"],
                "paid_cents": paid,
                "refund_cents": refunded,
                "net_cents": net,
            }
        )
        customer_totals[order["customer"]] = customer_totals.get(order["customer"], 0) + net
        total_paid += paid
        total_refund += refunded

    result_customers = [
        {"customer": name, "net_cents": customer_totals[name]}
        for name in sorted(customer_totals)
    ]

    return {
        "orders": result_orders,
        "customers": result_customers,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def export_bundle(result):
    """Render a reconcile result as the release bundle (release-spec.md).

    Returns exactly three files: orders.csv, customers.csv, summary.json.
    Row order follows the reconcile ordering; amounts are integer text;
    summary.json parses to exactly result["totals"].
    """
    if not isinstance(result, dict) or "orders" not in result or "customers" not in result or "totals" not in result:
        raise ValueError("export_bundle expects a reconcile result object")

    orders_buf = io.StringIO()
    writer = csv.writer(orders_buf)
    writer.writerow(["order_id", "customer", "paid_cents", "refund_cents", "net_cents"])
    for order in result["orders"]:
        writer.writerow(
            [
                order["order_id"],
                order["customer"],
                int(order["paid_cents"]),
                int(order["refund_cents"]),
                int(order["net_cents"]),
            ]
        )

    customers_buf = io.StringIO()
    writer = csv.writer(customers_buf)
    writer.writerow(["customer", "net_cents"])
    for customer in result["customers"]:
        writer.writerow([customer["customer"], int(customer["net_cents"])])

    return {
        "orders.csv": orders_buf.getvalue(),
        "customers.csv": customers_buf.getvalue(),
        "summary.json": json.dumps(result["totals"]),
    }
