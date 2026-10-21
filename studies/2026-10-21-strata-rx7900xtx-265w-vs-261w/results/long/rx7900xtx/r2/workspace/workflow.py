"""Order reconciliation, v1 + v2 contracts (see spec-v1.md, spec-v2.md).

Pure functions only: parses CSV strings, returns plain dicts with integer cents.
Release bundle format per release-spec.md.
"""

import csv
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _parse_amount_cents(raw, context, max_dp=2):
    """Parse a non-negative amount into integer cents using Decimal.

    max_dp=2 (v1): reject more than two decimals.
    max_dp=None (v2): allow any decimals, ROUND_HALF_UP to cents.
    Always rejects NaN/Infinity/negatives/unparseable input. Never float*100.
    """
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = str(raw).strip()
    if text == "":
        raise ValueError("%s: empty amount" % context)
    try:
        value = Decimal(text)
    except (InvalidOperation, ArithmeticError):
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if not value.is_finite():
        raise ValueError("%s: non-finite amount %r" % (context, raw))
    if value < 0:
        raise ValueError("%s: negative amount %r" % (context, raw))
    sign, digits, exponent = value.as_tuple()
    if max_dp is not None and isinstance(exponent, int) and exponent < -max_dp:
        raise ValueError("%s: more than two decimals %r" % (context, raw))
    cents = value.scaleb(2).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _read_rows(csv_text, required_header, kind):
    if csv_text is None:
        raise ValueError("%s csv is None" % kind)
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("%s csv is empty (missing header)" % kind)
    if header != required_header:
        raise ValueError(
            "%s csv bad header: expected %r, got %r" % (kind, required_header, header)
        )
    rows = []
    for row in reader:
        if row == []:
            continue
        if len(row) != len(required_header):
            raise ValueError("%s csv bad row width: %r" % (kind, row))
        rows.append(tuple(row))
    return rows


def _dedupe(rows, id_index, kind):
    """Deduplicate rows by id. Identical rows collapse; conflicting rows raise.

    Runs over all rows (including pending / after-cutoff ones), so conflicts
    involving excluded duplicates are still rejected.
    """
    seen = {}
    unique = []
    for row in rows:
        key = row[id_index]
        if key in seen:
            if seen[key] != row:
                raise ValueError(
                    "%s %s: duplicate id with differing fields: %r vs %r"
                    % (kind, key, seen[key], row)
                )
            continue
        seen[key] = row
        unique.append(row)
    return unique


def _validate_cutoff(cutoff):
    if cutoff is None or not isinstance(cutoff, str):
        raise ValueError("v2 policy requires cutoff YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        raise ValueError("v2 cutoff bad format: %r" % (cutoff,))
    return cutoff


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy == "v1":
        max_dp = 2
        refund_header = ["refund_id", "order_id", "amount"]
    elif policy == "v2":
        max_dp = None
        _validate_cutoff(cutoff)
        refund_header = ["refund_id", "order_id", "amount", "status", "created_at"]
    else:
        raise ValueError("unsupported policy: %r" % (policy,))

    order_rows = _read_rows(
        orders_csv,
        ["order_id", "customer", "amount", "status", "created_at"],
        "orders",
    )
    refund_rows = _read_rows(refunds_csv, refund_header, "refunds")

    order_rows = _dedupe(order_rows, 0, "order")
    refund_rows = _dedupe(refund_rows, 0, "refund")

    # Validate and index orders.
    orders = {}
    for row in order_rows:
        order_id, customer, amount, status, created_at = row
        if status not in ("paid", "cancelled"):
            raise ValueError("order %s: unknown status %r" % (order_id, status))
        cents = _parse_amount_cents(amount, "order %s" % order_id, max_dp)
        orders[order_id] = {
            "order_id": order_id,
            "customer": customer,
            "paid_cents": cents,
            "status": status,
            "created_at": created_at,
        }

    # Validate and index refunds.
    refund_by_order = {}
    for row in refund_rows:
        refund_id, order_id, amount = row[0], row[1], row[2]
        if policy == "v2":
            status, created_at = row[3], row[4]
            if status not in ("succeeded", "pending"):
                raise ValueError(
                    "refund %s: unknown status %r" % (refund_id, status)
                )
            if status != "succeeded" or created_at > cutoff:
                # pending / after-cutoff refunds are ignored entirely.
                continue
            order = orders.get(order_id)
            if order is None:
                raise ValueError(
                    "refund %s: unknown order %r" % (refund_id, order_id)
                )
            if order["status"] != "paid":
                raise ValueError(
                    "refund %s: order %s is not paid" % (refund_id, order_id)
                )
            if order["created_at"] > cutoff:
                # Order exists but is excluded by cutoff: ignore the refund.
                continue
        else:
            order = orders.get(order_id)
            if order is None:
                raise ValueError(
                    "refund %s: unknown order %r" % (refund_id, order_id)
                )
            if order["status"] != "paid":
                raise ValueError(
                    "refund %s: order %s is not paid" % (refund_id, order_id)
                )
        cents = _parse_amount_cents(amount, "refund %s" % refund_id, max_dp)
        refund_by_order.setdefault(order_id, 0)
        refund_by_order[order_id] += cents

    order_entries = []
    customers = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}

    for order_id in sorted(orders):
        order = orders[order_id]
        if order["status"] != "paid":
            continue
        if policy == "v2" and order["created_at"] > cutoff:
            continue
        paid = order["paid_cents"]
        refund = refund_by_order.get(order_id, 0)
        if refund > paid:
            raise ValueError(
                "order %s: refunds %d exceed paid %d" % (order_id, refund, paid)
            )
        net = paid - refund
        order_entries.append(
            {
                "order_id": order_id,
                "customer": order["customer"],
                "paid_cents": paid,
                "refund_cents": refund,
                "net_cents": net,
            }
        )
        customers[order["customer"]] = customers.get(order["customer"], 0) + net
        totals["paid_cents"] += paid
        totals["refund_cents"] += refund
        totals["net_cents"] += net

    customer_entries = [
        {"customer": name, "net_cents": customers[name]} for name in sorted(customers)
    ]

    return {"orders": order_entries, "customers": customer_entries, "totals": totals}


def export_bundle(result):
    """Render a reconcile result into the release bundle (see release-spec.md).

    Returns dict[str, str] with exactly three files:
      orders.csv    header order_id,customer,paid_cents,refund_cents,net_cents
      customers.csv header customer,net_cents
      summary.json  parses to exactly result["totals"]
    Row order follows reconcile's sorting; amounts are integer text.
    """
    orders_buf = io.StringIO(newline="")
    orders_writer = csv.writer(orders_buf, lineterminator="\n")
    orders_writer.writerow(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"]
    )
    for entry in result["orders"]:
        orders_writer.writerow(
            [
                entry["order_id"],
                entry["customer"],
                "%d" % entry["paid_cents"],
                "%d" % entry["refund_cents"],
                "%d" % entry["net_cents"],
            ]
        )

    customers_buf = io.StringIO(newline="")
    customers_writer = csv.writer(customers_buf, lineterminator="\n")
    customers_writer.writerow(["customer", "net_cents"])
    for entry in result["customers"]:
        customers_writer.writerow([entry["customer"], "%d" % entry["net_cents"]])

    return {
        "orders.csv": orders_buf.getvalue(),
        "customers.csv": customers_buf.getvalue(),
        "summary.json": json.dumps(result["totals"], sort_keys=True),
    }
