"""Order reconciliation, spec-v1 and spec-v2 contracts.

reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None) -> dict
Pure functions only; no file/network/process access. Decimal fixed-point
conversion to integer cents (never float * 100).
"""

import csv
import io
import json
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import OrderedDict

_ORDER_FIELDS = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_FIELDS_V1 = ("refund_id", "order_id", "amount")
_REFUND_FIELDS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")


def _parse_amount_cents(raw, context, max_two_decimals):
    """Parse a non-negative amount string to integer cents.

    max_two_decimals=True (v1): reject more than two decimal places.
    max_two_decimals=False (v2): allow any number of decimals, round to
    cents with Decimal ROUND_HALF_UP.
    """
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = raw.strip()
    if text == "":
        raise ValueError("%s: empty amount" % context)
    if text[0] == "-":
        raise ValueError("%s: negative amount %r" % (context, raw))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if not value.is_finite():
        raise ValueError("%s: non-finite amount %r" % (context, raw))
    if value.copy_abs() != value:
        raise ValueError("%s: negative amount %r" % (context, raw))
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if max_two_decimals and exponent < -2:
        raise ValueError("%s: more than two decimals %r" % (context, raw))
    return int(value.scaleb(2).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _validate_cutoff(cutoff):
    if not isinstance(cutoff, str):
        raise ValueError("cutoff must be a string YYYY-MM-DDTHH:MM:SSZ")
    text = cutoff.strip()
    if len(text) != 20 or not text.endswith("Z"):
        raise ValueError("cutoff bad format %r" % (cutoff,))
    if text[4] != "-" or text[7] != "-" or text[10] != "T" \
            or text[13] != ":" or text[16] != ":":
        raise ValueError("cutoff bad format %r" % (cutoff,))
    digits = text[:4] + text[5:7] + text[8:10] + text[11:13] + text[14:16] + text[17:19]
    if not digits.isdigit():
        raise ValueError("cutoff bad format %r" % (cutoff,))
    try:
        datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("cutoff invalid date/time %r" % (cutoff,))
    return text


def _read_rows(csv_text, required_fields, table_name):
    if csv_text is None:
        raise ValueError("%s csv is None" % table_name)
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("%s csv must have a header row" % table_name)
    header = [h.strip() for h in header]
    missing = [f for f in required_fields if f not in header]
    if missing:
        raise ValueError("%s csv missing columns: %s" % (table_name, missing))
    rows = []
    for line_no, raw in enumerate(reader, start=2):
        if not raw or all(cell.strip() == "" for cell in raw):
            continue
        if len(raw) != len(header):
            raise ValueError(
                "%s csv line %d: expected %d fields, got %d"
                % (table_name, line_no, len(header), len(raw))
            )
        rows.append(dict(zip(header, raw)))
    return rows


def _dedupe(rows, id_field, table_name):
    """Return OrderedDict id -> row dict; exact duplicates collapse,
    conflicting duplicates raise ValueError (regardless of any filters)."""
    seen = OrderedDict()
    for row in rows:
        key = (row.get(id_field) or "").strip()
        if key == "":
            raise ValueError("%s: empty %s" % (table_name, id_field))
        if key in seen:
            if seen[key] != row:
                raise ValueError(
                    "%s: duplicate %s %r with differing fields"
                    % (table_name, id_field, key)
                )
            continue
        seen[key] = row
    return seen


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v1":
        max_two_decimals = True
        refund_fields = _REFUND_FIELDS_V1
        cutoff_value = None
    else:
        if cutoff is None:
            raise ValueError("policy v2 requires cutoff")
        max_two_decimals = False
        refund_fields = _REFUND_FIELDS_V2
        cutoff_value = _validate_cutoff(cutoff)

    order_rows = _read_rows(orders_csv, _ORDER_FIELDS, "orders")
    refund_rows = _read_rows(refunds_csv, refund_fields, "refunds")

    # Dedupe first: conflicts are rejected even for rows later filtered out.
    orders = _dedupe(order_rows, "order_id", "orders")
    refunds = _dedupe(refund_rows, "refund_id", "refunds")

    # Validate and convert orders.
    parsed_orders = {}
    for order_id, row in orders.items():
        status = (row.get("status") or "").strip().lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("orders: unknown status %r for %r" % (status, order_id))
        customer = (row.get("customer") or "").strip()
        if customer == "":
            raise ValueError("orders: empty customer for %r" % order_id)
        cents = _parse_amount_cents(
            row.get("amount"), "orders %s" % order_id, max_two_decimals
        )
        created_at = (row.get("created_at") or "").strip()
        if policy == "v2" and created_at == "":
            raise ValueError("orders %s: missing created_at" % order_id)
        parsed_orders[order_id] = {
            "order_id": order_id,
            "customer": customer,
            "status": status,
            "paid_cents": cents,
            "created_at": created_at,
        }

    def _order_included(order):
        if order["status"] != "paid":
            return False
        if cutoff_value is not None and order["created_at"] > cutoff_value:
            return False
        return True

    # Validate refunds and accumulate per included paid order.
    refund_by_order = {}
    for refund_id, row in refunds.items():
        order_id = (row.get("order_id") or "").strip()
        status = (row.get("status") or "succeeded").strip().lower()
        if policy == "v2" and status not in ("succeeded", "pending"):
            raise ValueError(
                "refunds %s: unknown status %r" % (refund_id, status)
            )
        created_at = (row.get("created_at") or "").strip()

        effective = True
        if policy == "v2":
            if status != "succeeded":
                effective = False
            if cutoff_value is not None and created_at > cutoff_value:
                effective = False

        order = parsed_orders.get(order_id)
        if order is None:
            # Truly unknown order: valid refunds raise; ignored ones skip.
            if effective:
                raise ValueError(
                    "refunds %s: unknown order %r" % (refund_id, order_id)
                )
            continue
        if effective:
            if order["status"] != "paid":
                raise ValueError(
                    "refunds %s: order %r is not paid" % (refund_id, order_id)
                )
            if cutoff_value is not None and order["created_at"] > cutoff_value:
                # Order exists but excluded by cutoff: ignore the refund.
                continue
            cents = _parse_amount_cents(
                row.get("amount"), "refunds %s" % refund_id, max_two_decimals
            )
            refund_by_order[order_id] = refund_by_order.get(order_id, 0) + cents

    for order_id, total in refund_by_order.items():
        if total > parsed_orders[order_id]["paid_cents"]:
            raise ValueError(
                "refunds: order %r refund total %d exceeds paid %d"
                % (order_id, total, parsed_orders[order_id]["paid_cents"])
            )

    # Build outputs. Only included paid orders appear; sorted by order_id.
    out_orders = []
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    customer_net = {}
    for order_id in sorted(parsed_orders):
        order = parsed_orders[order_id]
        if not _order_included(order):
            continue
        paid = order["paid_cents"]
        refund = refund_by_order.get(order_id, 0)
        net = paid - refund
        out_orders.append({
            "order_id": order_id,
            "customer": order["customer"],
            "paid_cents": paid,
            "refund_cents": refund,
            "net_cents": net,
        })
        totals["paid_cents"] += paid
        totals["refund_cents"] += refund
        totals["net_cents"] += net
        customer_net[order["customer"]] = customer_net.get(order["customer"], 0) + net

    out_customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]

    return {"orders": out_orders, "customers": out_customers, "totals": totals}


def _csv_text(rows, header):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([str(row[field]) for field in header])
    return buffer.getvalue()


def export_bundle(result):
    """Return exactly three files per release-spec:
    orders.csv, customers.csv, summary.json."""
    if not isinstance(result, dict) or \
            "orders" not in result or "customers" not in result \
            or "totals" not in result:
        raise ValueError("result must contain orders, customers and totals")
    orders_header = ("order_id", "customer", "paid_cents", "refund_cents", "net_cents")
    customers_header = ("customer", "net_cents")
    for row in result["orders"]:
        if set(row) != set(orders_header):
            raise ValueError("bad order row keys: %r" % (sorted(row),))
        for field in orders_header[2:]:
            if not isinstance(row[field], int):
                raise ValueError("order %r: %s must be int cents"
                                 % (row.get("order_id"), field))
    for row in result["customers"]:
        if set(row) != set(customers_header):
            raise ValueError("bad customer row keys: %r" % (sorted(row),))
        if not isinstance(row["net_cents"], int):
            raise ValueError("customer %r: net_cents must be int cents"
                             % row.get("customer"))
    totals = result["totals"]
    if set(totals) != {"paid_cents", "refund_cents", "net_cents"}:
        raise ValueError("totals must have exactly the three *_cents keys")
    return {
        "orders.csv": _csv_text(result["orders"], orders_header),
        "customers.csv": _csv_text(result["customers"], customers_header),
        "summary.json": json.dumps(totals, sort_keys=True),
    }
