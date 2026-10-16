"""Order reconciliation per spec-v1 and spec-v2.

Pure functions only. Inputs are UTF-8 CSV strings; monetary outputs are integer cents.
Decimal fixed-point is used for parsing; float multiplication is never used.
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import OrderedDict
from datetime import datetime

ORDERS_HEADER = ["order_id", "customer", "amount", "status", "created_at"]
REFUNDS_HEADER_V1 = ["refund_id", "order_id", "amount"]
REFUNDS_HEADER_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]


def _split_amount(text):
    """Return (int_part, frac_part) for a plain non-negative decimal literal, else None."""
    if not text:
        return None
    int_part, dot, frac_part = text.partition(".")
    if not int_part.isdigit():
        return None
    if dot:
        if not frac_part.isdigit():
            return None
    else:
        frac_part = ""
    return int_part, frac_part


def _parse_amount_cents_v1(raw, context):
    """v1: non-negative, at most two decimals, exact conversion to cents."""
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = raw.strip()
    parts = _split_amount(text)
    if parts is None or len(parts[1]) > 2:
        # Rejects NaN, Infinity, negatives, exponents, >2 decimals.
        raise ValueError("%s: invalid amount %r" % (context, raw))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if value < 0:
        raise ValueError("%s: negative amount %r" % (context, raw))
    return int(value.scaleb(2).to_integral_value(ROUND_HALF_UP))


def _parse_amount_cents_v2(raw, context):
    """v2: non-negative decimal with any number of decimals, ROUND_HALF_UP to cents."""
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = raw.strip()
    parts = _split_amount(text)
    if parts is None:
        # Rejects NaN, Infinity, negatives, exponents, empty.
        raise ValueError("%s: invalid amount %r" % (context, raw))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if value < 0:
        raise ValueError("%s: negative amount %r" % (context, raw))
    return int(value.scaleb(2).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _validate_cutoff(cutoff):
    if not isinstance(cutoff, str) or len(cutoff) != 20 or not cutoff.endswith("Z"):
        raise ValueError("cutoff: expected YYYY-MM-DDTHH:MM:SSZ, got %r" % (cutoff,))
    try:
        datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("cutoff: expected YYYY-MM-DDTHH:MM:SSZ, got %r" % (cutoff,))
    return cutoff


def _read_rows(csv_text, expected_header, name):
    """Read CSV text into a list of tuples, validating the header."""
    if csv_text is None:
        raise ValueError("%s: input must be a string" % name)
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows:
        return []
    header = [cell.strip() for cell in rows[0]]
    if header != expected_header:
        raise ValueError("%s: unexpected header %r" % (name, rows[0]))
    return [tuple(cell.strip() for cell in row) for row in rows[1:]]


def _dedupe(rows, id_index, name):
    """Deduplicate rows by id: identical rows collapse; conflicting rows raise.

    Conflicts are detected on the raw rows, so pending/post-cutoff rows
    still participate in duplicate-id conflict detection.
    """
    seen = OrderedDict()
    for row in rows:
        key = row[id_index]
        if key in seen:
            if seen[key] == row:
                continue
            raise ValueError(
                "%s: duplicate id %r with conflicting fields" % (name, key)
            )
        seen[key] = row
    return seen


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile orders against refunds. See spec-v1 / spec-v2 for contracts."""
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v1":
        if cutoff is not None:
            raise ValueError("cutoff is not supported in policy v1")
        amount_parser = _parse_amount_cents_v1
        refunds_header = REFUNDS_HEADER_V1
    else:
        if cutoff is None:
            raise ValueError("policy v2 requires a cutoff")
        cutoff = _validate_cutoff(cutoff)
        amount_parser = _parse_amount_cents_v2
        refunds_header = REFUNDS_HEADER_V2

    order_rows = _read_rows(orders_csv, ORDERS_HEADER, "orders")
    refund_rows = _read_rows(refunds_csv, refunds_header, "refunds")

    orders = _dedupe(order_rows, 0, "orders")
    refunds = _dedupe(refund_rows, 0, "refunds")

    # Parse orders.
    parsed_orders = {}
    for order_id, row in orders.items():
        if len(row) != len(ORDERS_HEADER):
            raise ValueError("orders: malformed row %r" % (row,))
        _oid, customer, amount_raw, status, created_at = row
        if status not in ("paid", "cancelled"):
            raise ValueError("orders: unknown status %r for %r" % (status, order_id))
        paid_cents = amount_parser(amount_raw, "orders %s" % order_id)
        parsed_orders[order_id] = {
            "customer": customer,
            "status": status,
            "paid_cents": paid_cents,
            "created_at": created_at,
        }

    def _order_included(order):
        if order["status"] != "paid":
            return False
        if policy == "v2" and order["created_at"] > cutoff:
            return False
        return True

    # Parse and validate refunds.
    refund_by_order = {}
    for refund_id, row in refunds.items():
        if len(row) != len(refunds_header):
            raise ValueError("refunds: malformed row %r" % (row,))
        if policy == "v1":
            _rid, order_id, amount_raw = row
            status, created_at = "succeeded", None
        else:
            _rid, order_id, amount_raw, status, created_at = row
            if status not in ("succeeded", "pending"):
                raise ValueError(
                    "refunds: unknown status %r for %r" % (status, refund_id)
                )
        amount_cents = amount_parser(amount_raw, "refunds %s" % refund_id)
        order = parsed_orders.get(order_id)
        if order is None:
            raise ValueError(
                "refunds: %s references unknown order %r" % (refund_id, order_id)
            )
        if order["status"] != "paid":
            raise ValueError(
                "refunds: %s references cancelled order %r" % (refund_id, order_id)
            )
        # Counting filters: v2 skips pending and post-cutoff refunds; refunds
        # whose order exists but is excluded by the cutoff are ignored too.
        if policy == "v2":
            if status != "succeeded":
                continue
            if created_at > cutoff:
                continue
            if not _order_included(order):
                continue
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + amount_cents

    # Build results (included paid orders only).
    result_orders = []
    customers_total = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(parsed_orders):
        order = parsed_orders[order_id]
        if not _order_included(order):
            continue
        refund_cents = refund_by_order.get(order_id, 0)
        if refund_cents > order["paid_cents"]:
            raise ValueError(
                "order %s: cumulative refunds %d exceed paid %d"
                % (order_id, refund_cents, order["paid_cents"])
            )
        net_cents = order["paid_cents"] - refund_cents
        result_orders.append(
            {
                "order_id": order_id,
                "customer": order["customer"],
                "paid_cents": order["paid_cents"],
                "refund_cents": refund_cents,
                "net_cents": net_cents,
            }
        )
        customers_total[order["customer"]] = (
            customers_total.get(order["customer"], 0) + net_cents
        )
        totals["paid_cents"] += order["paid_cents"]
        totals["refund_cents"] += refund_cents
        totals["net_cents"] += net_cents

    result_customers = [
        {"customer": name, "net_cents": customers_total[name]}
        for name in sorted(customers_total)
    ]
    return {"orders": result_orders, "customers": result_customers, "totals": totals}


def _csv_text(header, rows):
    """Render rows (list of lists) with the standard csv writer."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """Render a reconcile result as the release bundle (release-spec.md).

    Returns exactly three files: orders.csv, customers.csv, summary.json.
    Row order follows the reconcile ordering; amounts are integer text;
    summary.json parses to exactly result["totals"].
    """
    orders_rows = [
        [
            order["order_id"],
            order["customer"],
            str(order["paid_cents"]),
            str(order["refund_cents"]),
            str(order["net_cents"]),
        ]
        for order in result["orders"]
    ]
    customers_rows = [
        [customer["customer"], str(customer["net_cents"])]
        for customer in result["customers"]
    ]
    totals = result["totals"]
    summary = json.dumps(
        {
            "paid_cents": totals["paid_cents"],
            "refund_cents": totals["refund_cents"],
            "net_cents": totals["net_cents"],
        },
        sort_keys=True,
    )
    return {
        "orders.csv": _csv_text(
            ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
            orders_rows,
        ),
        "customers.csv": _csv_text(["customer", "net_cents"], customers_rows),
        "summary.json": summary,
    }
