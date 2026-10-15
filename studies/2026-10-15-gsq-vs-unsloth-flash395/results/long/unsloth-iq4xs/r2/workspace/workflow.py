"""Order reconciliation per spec-v1, spec-v2 and release-spec.

reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None) -> dict
export_bundle(result) -> dict[str, str]  (orders.csv, customers.csv,
summary.json)
Pure functions only; no file/network/process access. Fixed-point decimal
money handling via the decimal module (never float * 100).
"""

import csv
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDERS_HEADER = ["order_id", "customer", "amount", "status", "created_at"]
_REFUNDS_HEADER_V1 = ["refund_id", "order_id", "amount"]
_REFUNDS_HEADER_V2 = ["refund_id", "order_id", "amount", "status",
                      "created_at"]
_TWO_PLACES = Decimal("0.01")
_CENT = Decimal("1")


def _amount_to_cents(raw, context, policy):
    """Parse a non-negative fixed-point amount string into integer cents.

    v1: at most two decimal places (legacy contract).
    v2: any number of decimal places, rounded HALF_UP to cents.
    Both reject signs, exponents, NaN/Infinity words and empty values.
    """
    if not isinstance(raw, str):
        raise ValueError("%s: amount must be a string" % context)
    s = raw.strip()
    if not s:
        raise ValueError("%s: amount is empty" % context)
    if s.count(".") > 1:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    int_part, dot, frac_part = s.partition(".")
    if not int_part or not int_part.isdigit():
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if dot:
        if not frac_part or not frac_part.isdigit():
            raise ValueError("%s: invalid amount %r" % (context, raw))
        if policy == "v1" and len(frac_part) > 2:
            raise ValueError(
                "%s: v1 allows at most two decimal places %r" % (context, raw))
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if not d.is_finite() or d < 0:
        raise ValueError("%s: amount must be finite and non-negative" % context)
    if policy == "v1" and d != d.quantize(_TWO_PLACES):
        raise ValueError("%s: more than two decimal places" % context)
    return int((d * 100).quantize(_CENT, rounding=ROUND_HALF_UP))


def _require_field(row, idx, name, context):
    if idx >= len(row) or row[idx] == "":
        raise ValueError("%s: missing %s" % (context, name))
    return row[idx]


def _parse_rows(csv_text, header, context):
    """Return list of data rows (lists of strings). Raises on missing or
    mismatching header."""
    if not isinstance(csv_text, str):
        raise ValueError("%s: input must be a string" % context)
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row != []]
    if not rows:
        raise ValueError("%s: missing header" % context)
    if rows[0] != header:
        raise ValueError("%s: bad header %r" % (context, rows[0]))
    return rows[1:]


def _validate_cutoff(cutoff):
    if not isinstance(cutoff, str):
        raise ValueError("cutoff must be a string YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("cutoff must match YYYY-MM-DDTHH:MM:SSZ: %r"
                         % (cutoff,))
    return cutoff


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v2":
        if cutoff is None:
            raise ValueError("v2 requires cutoff")
        _validate_cutoff(cutoff)
    # cutoff is not part of the v1 contract; ignored there.

    # ---- orders ----
    order_rows = _parse_rows(orders_csv, _ORDERS_HEADER, "orders")
    seen_orders = {}          # order_id -> full row tuple (for dedupe)
    orders = {}               # included paid order_id -> dict
    known_paid_ids = set()    # all paid order ids seen (any date)
    cancelled_ids = set()
    for row in order_rows:
        context = "order row %r" % (row,)
        order_id = _require_field(row, 0, "order_id", context)
        customer = _require_field(row, 1, "customer", context)
        amount_raw = _require_field(row, 2, "amount", context)
        status = _require_field(row, 3, "status", context)
        created_at = _require_field(row, 4, "created_at", context)
        key = (order_id, customer, amount_raw, status, created_at)
        if order_id in seen_orders:
            if seen_orders[order_id] == key:
                continue  # exact duplicate row: count once
            raise ValueError("duplicate order_id with different fields: %s"
                             % order_id)
        seen_orders[order_id] = key
        if status == "cancelled":
            cancelled_ids.add(order_id)
            continue
        if status != "paid":
            raise ValueError("%s: unknown status %r" % (context, status))
        known_paid_ids.add(order_id)
        if policy == "v2" and created_at > cutoff:
            continue  # after cutoff: excluded, but the order is known
        paid_cents = _amount_to_cents(amount_raw, context, policy)
        orders[order_id] = {
            "order_id": order_id,
            "customer": customer,
            "paid_cents": paid_cents,
            "refund_cents": 0,
        }

    # ---- refunds ----
    refunds_header = (_REFUNDS_HEADER_V2 if policy == "v2"
                      else _REFUNDS_HEADER_V1)
    refund_rows = _parse_rows(refunds_csv, refunds_header, "refunds")
    seen_refunds = {}         # refund_id -> full row tuple (for dedupe)
    for row in refund_rows:
        context = "refund row %r" % (row,)
        refund_id = _require_field(row, 0, "refund_id", context)
        order_id = _require_field(row, 1, "order_id", context)
        amount_raw = _require_field(row, 2, "amount", context)
        if policy == "v2":
            status = _require_field(row, 3, "status", context)
            created_at = _require_field(row, 4, "created_at", context)
        else:
            status = "succeeded"
            created_at = ""
        key = tuple(row)
        if refund_id in seen_refunds:
            if seen_refunds[refund_id] == key:
                continue  # exact duplicate row: count once
            raise ValueError("duplicate refund_id with different fields: %s"
                             % refund_id)
        seen_refunds[refund_id] = key
        if policy == "v2":
            if status not in ("succeeded", "pending"):
                raise ValueError("%s: unknown refund status %r"
                                 % (context, status))
            if status == "pending" or created_at > cutoff:
                # Not counted. Duplicate conflicts were already checked.
                continue
        # Effective refund: its order must exist (paid) and not be excluded
        # by the cutoff.
        if order_id not in orders:
            if order_id in cancelled_ids:
                raise ValueError("refund %s targets cancelled order %s"
                                 % (refund_id, order_id))
            if order_id in known_paid_ids:
                continue  # order exists but excluded by cutoff: ignore
            raise ValueError("refund %s targets unknown order %s"
                             % (refund_id, order_id))
        refund_cents = _amount_to_cents(amount_raw, context, policy)
        order = orders[order_id]
        order["refund_cents"] += refund_cents
        if order["refund_cents"] > order["paid_cents"]:
            raise ValueError("refunds exceed paid amount for order %s"
                             % order_id)

    # ---- results ----
    result_orders = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(orders):
        order = orders[order_id]
        net = order["paid_cents"] - order["refund_cents"]
        result_orders.append({
            "order_id": order["order_id"],
            "customer": order["customer"],
            "paid_cents": order["paid_cents"],
            "refund_cents": order["refund_cents"],
            "net_cents": net,
        })
        customer_net[order["customer"]] = (
            customer_net.get(order["customer"], 0) + net)
        totals["paid_cents"] += order["paid_cents"]
        totals["refund_cents"] += order["refund_cents"]
        totals["net_cents"] += net

    result_customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]
    return {
        "orders": result_orders,
        "customers": result_customers,
        "totals": totals,
    }


def _csv_text(rows):
    """Render rows with the standard csv writer (CRLF line endings)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Render the release bundle: exactly orders.csv, customers.csv and
    summary.json (release-spec). Amounts are integer text; row order
    follows reconcile ordering; summary.json is exactly result["totals"].
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a dict")
    orders = result.get("orders", [])
    customers = result.get("customers", [])
    totals = result.get("totals", {})

    order_rows = [["order_id", "customer", "paid_cents", "refund_cents",
                   "net_cents"]]
    for o in orders:
        order_rows.append([
            str(o["order_id"]),
            str(o["customer"]),
            str(int(o["paid_cents"])),
            str(int(o["refund_cents"])),
            str(int(o["net_cents"])),
        ])

    customer_rows = [["customer", "net_cents"]]
    for c in customers:
        customer_rows.append([str(c["customer"]), str(int(c["net_cents"]))])

    return {
        "orders.csv": _csv_text(order_rows),
        "customers.csv": _csv_text(customer_rows),
        "summary.json": json.dumps(totals, sort_keys=True),
    }
