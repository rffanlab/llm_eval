"""Order reconciliation workflow (spec v1 + v2).

Pure functions only. Inputs are UTF-8 CSV strings; monetary outputs are
integer cents computed with decimal fixed-point arithmetic (no float *100).

v1: legacy amount rules (<=2 decimals), refunds have 3 columns.
v2: cutoff required; refunds carry status/created_at; amounts with any
    number of decimals are rounded ROUND_HALF_UP to integer cents per row.

Release contract: export_bundle(result) -> exactly three files
(orders.csv, customers.csv, summary.json) as str values.
"""

import csv
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_FIELDS = ["order_id", "customer", "amount", "status", "created_at"]
_REFUND_FIELDS_V1 = ["refund_id", "order_id", "amount"]
_REFUND_FIELDS_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]


def _parse_amount_cents(raw, context, policy):
    """Parse a non-negative amount string to integer cents.

    v1: at most two decimals. v2: any number of decimals, ROUND_HALF_UP.
    """
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = raw.strip()
    if not text:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    # Reject negatives / NaN / Infinity / garbage before Decimal parsing.
    if text[0] == "-":
        raise ValueError("%s: negative amount %r" % (context, raw))
    if text[0] not in "0123456789.":
        raise ValueError("%s: invalid amount %r" % (context, raw))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if value.is_nan() or value.is_infinite() or value < 0:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    sign, digits, exponent = value.as_tuple()
    if exponent < -2 and policy != "v2":
        raise ValueError("%s: amount has more than 2 decimals %r" % (context, raw))
    cents = value.scaleb(2).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    if cents != value.scaleb(2):
        # Only reachable for v1-like values; safety net.
        if policy != "v2":
            raise ValueError("%s: amount is not a whole number of cents %r" % (context, raw))
    return int(cents)


def _read_rows(csv_text, expected_fields, kind):
    """Parse CSV text, validate header, return list of dict rows."""
    reader = csv.reader(io.StringIO(csv_text))
    rows = []
    header = None
    for lineno, row in enumerate(reader):
        if not row and lineno > 0:
            continue  # skip blank trailing lines
        if lineno == 0:
            header = [f.strip() for f in row]
            if header != expected_fields:
                raise ValueError(
                    "%s: bad header %r, expected %r" % (kind, header, expected_fields)
                )
            continue
        if len(row) != len(expected_fields):
            raise ValueError(
                "%s: line %d has %d fields, expected %d"
                % (kind, lineno + 1, len(row), len(expected_fields))
            )
        rows.append({name: value for name, value in zip(expected_fields, row)})
    if header is None:
        raise ValueError("%s: empty input, header required" % kind)
    return rows


def _validate_cutoff(cutoff):
    if not isinstance(cutoff, str):
        raise ValueError("cutoff must be a string YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ, got %r" % (cutoff,))
    return cutoff


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds (v1/v2 contracts).

    Returns a dict:
      orders: sorted by order_id -> {order_id, customer, paid_cents,
                                     refund_cents, net_cents}
      customers: sorted by customer -> {customer, net_cents}
      totals: {paid_cents, refund_cents, net_cents}
    Raises ValueError on any contract violation.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v1":
        if cutoff is not None:
            raise ValueError("cutoff is not supported by policy v1")
    else:
        if cutoff is None:
            raise ValueError("policy v2 requires cutoff")
        _validate_cutoff(cutoff)

    refund_fields = _REFUND_FIELDS_V2 if policy == "v2" else _REFUND_FIELDS_V1
    order_rows = _read_rows(orders_csv, _ORDER_FIELDS, "orders")
    refund_rows = _read_rows(refunds_csv, refund_fields, "refunds")

    # --- Orders: dedupe by order_id, validate amounts, keep paid only ---
    orders = {}  # order_id -> record (raw strings + paid_cents)
    for row in order_rows:
        order_id = row["order_id"]
        customer = row["customer"]
        status = row["status"]
        created_at = row["created_at"]
        if not order_id:
            raise ValueError("orders: empty order_id")
        if not customer:
            raise ValueError("orders %s: empty customer" % order_id)
        if status not in ("paid", "cancelled"):
            raise ValueError("orders %s: unknown status %r" % (order_id, status))
        paid_cents = _parse_amount_cents(row["amount"], "orders %s" % order_id, policy)
        record = {
            "order_id": order_id,
            "customer": customer,
            "amount": row["amount"],
            "paid_cents": paid_cents,
            "status": status,
            "created_at": created_at,
        }
        existing = orders.get(order_id)
        if existing is None:
            orders[order_id] = record
        else:
            if existing != record:
                raise ValueError(
                    "orders: duplicate order_id %s with conflicting fields" % order_id
                )
            # exact duplicate row: count once

    # --- Refunds: dedupe by refund_id, then filter/validate ---
    refund_by_order = {}  # order_id -> accumulated refund_cents (counted only)
    seen_refund_ids = {}  # refund_id -> full record
    for row in refund_rows:
        refund_id = row["refund_id"]
        order_id = row["order_id"]
        if not refund_id:
            raise ValueError("refunds: empty refund_id")
        status = row.get("status", "succeeded") if policy == "v2" else "succeeded"
        created_at = row.get("created_at", "") if policy == "v2" else ""
        if status not in ("succeeded", "pending"):
            raise ValueError("refunds %s: unknown status %r" % (refund_id, status))
        refund_cents = _parse_amount_cents(
            row["amount"], "refunds %s" % refund_id, policy
        )
        record = {
            "refund_id": refund_id,
            "order_id": order_id,
            "amount": row["amount"],
            "amount_cents": refund_cents,
            "status": status,
            "created_at": created_at,
        }
        existing = seen_refund_ids.get(refund_id)
        if existing is not None:
            # Conflicts are rejected even for pending / after-cutoff rows.
            if existing != record:
                raise ValueError(
                    "refunds: duplicate refund_id %s with conflicting fields" % refund_id
                )
            continue  # exact duplicate row: count once
        seen_refund_ids[refund_id] = record

        # v2: pending or after-cutoff refunds are not counted at all.
        if policy == "v2" and (
            status != "succeeded" or created_at > cutoff
        ):
            continue

        order = orders.get(order_id)
        if order is None:
            raise ValueError("refunds %s: unknown order %s" % (refund_id, order_id))
        if order["status"] != "paid":
            raise ValueError(
                "refunds %s: order %s is not paid" % (refund_id, order_id)
            )
        if policy == "v2" and order["created_at"] > cutoff:
            # Order exists but is excluded by cutoff: ignore the refund.
            continue
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + refund_cents

    for order_id, total_refund in refund_by_order.items():
        if total_refund > orders[order_id]["paid_cents"]:
            raise ValueError(
                "refunds: order %s refunded %d cents exceeds paid %d cents"
                % (order_id, total_refund, orders[order_id]["paid_cents"])
            )

    # --- Build outputs (paid orders only, honoring cutoff for v2) ---
    result_orders = []
    customer_net = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(orders):
        order = orders[order_id]
        if order["status"] != "paid":
            continue
        if policy == "v2" and order["created_at"] > cutoff:
            continue
        paid_cents = order["paid_cents"]
        refund_cents = refund_by_order.get(order_id, 0)
        net_cents = paid_cents - refund_cents
        result_orders.append(
            {
                "order_id": order_id,
                "customer": order["customer"],
                "paid_cents": paid_cents,
                "refund_cents": refund_cents,
                "net_cents": net_cents,
            }
        )
        customer_net[order["customer"]] = (
            customer_net.get(order["customer"], 0) + net_cents
        )
        total_paid += paid_cents
        total_refund += refund_cents

    result_customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]
    totals = {
        "paid_cents": total_paid,
        "refund_cents": total_refund,
        "net_cents": total_paid - total_refund,
    }
    return {"orders": result_orders, "customers": result_customers, "totals": totals}


def _csv_text(header, rows):
    """Render rows (list of lists) to CSV text with a standard writer."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Render a reconcile() result into the release bundle.

    Returns dict[str, str] with exactly three files:
      orders.csv    - order_id,customer,paid_cents,refund_cents,net_cents
      customers.csv - customer,net_cents
      summary.json  - exactly result["totals"]
    Row order follows the reconcile() ordering; amounts are integer text.
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError("result missing key %r" % (key,))

    order_rows = []
    for item in result["orders"]:
        order_rows.append(
            [
                item["order_id"],
                item["customer"],
                item["paid_cents"],
                item["refund_cents"],
                item["net_cents"],
            ]
        )
    customer_rows = []
    for item in result["customers"]:
        customer_rows.append([item["customer"], item["net_cents"]])

    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        order_rows,
    )
    customers_csv = _csv_text(["customer", "net_cents"], customer_rows)
    summary_json = json.dumps(result["totals"], sort_keys=True)

    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
