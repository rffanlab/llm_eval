"""Order reconciliation per spec-v1 and spec-v2.

Pure functions only. Inputs are UTF-8 CSV strings; outputs use integer cents.
"""

import csv
import io
import json
from decimal import Decimal, ROUND_HALF_UP

_ORDERS_HEADER = ["order_id", "customer", "amount", "status", "created_at"]
_REFUNDS_HEADER_V1 = ["refund_id", "order_id", "amount"]
_REFUNDS_HEADER_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]

_DIGITS = "0123456789"


def _is_valid_amount(text, max_decimals):
    """Non-negative fixed-point with at most max_decimals decimals.

    Rejects signs, exponents, NaN/Infinity and empty strings.
    """
    if not isinstance(text, str) or not text:
        return False
    parts = text.split(".")
    if len(parts) > 2:
        return False
    if not parts[0] or any(ch not in _DIGITS for ch in parts[0]):
        return False
    if len(parts) == 2:
        if not parts[1] or len(parts[1]) > max_decimals:
            return False
        if any(ch not in _DIGITS for ch in parts[1]):
            return False
    return True


def _parse_amount_cents(text, max_decimals=2, round_half_up=False):
    """Parse an amount string to integer cents using Decimal only.

    v1: max_decimals=2, exact (no rounding needed).
    v2: any number of decimals, ROUND_HALF_UP to cents. Never float.
    """
    if not _is_valid_amount(text, max_decimals):
        raise ValueError("invalid amount: %r" % (text,))
    dec = Decimal(text)
    scaled = dec.scaleb(2)
    if round_half_up:
        return int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    cents = scaled.to_integral_value()
    if cents != scaled:
        raise ValueError("amount has more than 2 decimals: %r" % (text,))
    return int(cents)


def _is_valid_cutoff(text):
    """Strict YYYY-MM-DDTHH:MM:SSZ check (digits/positions only)."""
    if not isinstance(text, str) or len(text) != 20:
        return False
    if text[4] != "-" or text[7] != "-" or text[10] != "T":
        return False
    if text[13] != ":" or text[16] != ":" or text[19] != "Z":
        return False
    for i in (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18):
        if text[i] not in _DIGITS:
            return False
    return True


def _read_rows(csv_text, expected_header, name):
    if not isinstance(csv_text, str):
        raise ValueError("%s input must be a string" % name)
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("%s input must contain a header row" % name)
    header = [h.strip() for h in rows[0]]
    if header != expected_header:
        raise ValueError(
            "%s header mismatch: expected %s got %s" % (name, expected_header, header)
        )
    out = []
    for row in rows[1:]:
        out.append(tuple(cell.strip() for cell in row))
    return out


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds. See spec-v1 / spec-v2.

    policy="v1": legacy amount limits (<=2 decimals) and 3-column refunds.
    policy="v2": cutoff required; refunds carry status/created_at; amounts
        allow many decimals rounded HALF_UP to cents (per row, then summed).
    Returns dict with keys: orders, customers, totals (all integer cents).
    Raises ValueError on any contract violation.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v2" and not _is_valid_cutoff(cutoff):
        raise ValueError("v2 requires cutoff in YYYY-MM-DDTHH:MM:SSZ format")

    v2 = policy == "v2"
    max_decimals = 999999 if v2 else 2
    round_half_up = v2

    # --- orders: dedupe by order_id, exact duplicates collapse ---
    orders_by_id = {}
    for row in _read_rows(orders_csv, _ORDERS_HEADER, "orders"):
        if len(row) != 5:
            raise ValueError("orders row must have 5 fields: %r" % (row,))
        order_id, customer, amount, status, created_at = row
        paid_cents = _parse_amount_cents(amount, max_decimals, round_half_up)
        if status not in ("paid", "cancelled"):
            raise ValueError("unknown order status: %r" % (status,))
        record = (order_id, customer, paid_cents, status, created_at)
        if order_id in orders_by_id:
            if orders_by_id[order_id] == record:
                continue
            raise ValueError("conflicting duplicate order_id: %s" % (order_id,))
        orders_by_id[order_id] = record

    # --- refunds: dedupe by refund_id (conflicts rejected even for
    #     pending / post-cutoff rows) ---
    refunds_header = _REFUNDS_HEADER_V2 if v2 else _REFUNDS_HEADER_V1
    refunds_by_id = {}
    for row in _read_rows(refunds_csv, refunds_header, "refunds"):
        if len(row) != len(refunds_header):
            raise ValueError(
                "refunds row must have %d fields: %r" % (len(refunds_header), row)
            )
        if v2:
            refund_id, order_id, amount, status, created_at = row
            if status not in ("succeeded", "pending"):
                raise ValueError("unknown refund status: %r" % (status,))
        else:
            refund_id, order_id, amount = row
            status, created_at = "succeeded", None
        amount_cents = _parse_amount_cents(amount, max_decimals, round_half_up)
        record = (refund_id, order_id, amount_cents, status, created_at)
        if refund_id in refunds_by_id:
            if refunds_by_id[refund_id] == record:
                continue
            raise ValueError("conflicting duplicate refund_id: %s" % (refund_id,))
        refunds_by_id[refund_id] = record

    # --- apply refund eligibility and attribute to orders ---
    refund_cents_by_order = {}
    for refund_id in sorted(refunds_by_id):
        _rid, order_id, amount_cents, status, created_at = refunds_by_id[refund_id]
        if v2:
            if status != "succeeded":
                continue  # pending refunds are ignored
            if created_at > cutoff:
                continue  # post-cutoff refunds are ignored
        order = orders_by_id.get(order_id)
        if order is None:
            raise ValueError("refund %s references unknown order %s" % (refund_id, order_id))
        if order[3] != "paid":
            raise ValueError("refund %s references cancelled order %s" % (refund_id, order_id))
        if v2 and order[4] > cutoff:
            continue  # order exists and is paid but excluded by cutoff: ignore
        refund_cents_by_order[order_id] = refund_cents_by_order.get(order_id, 0) + amount_cents

    # --- build results over paid orders only ---
    orders_out = []
    customers_net = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(orders_by_id):
        rec = orders_by_id[order_id]
        customer = rec[1]
        paid_cents = rec[2]
        status = rec[3]
        created_at = rec[4]
        if status != "paid":
            continue
        if v2 and created_at > cutoff:
            continue  # post-cutoff orders are not counted
        refund_cents = refund_cents_by_order.get(order_id, 0)
        if refund_cents > paid_cents:
            raise ValueError(
                "refunds %s exceed paid %s for order %s" % (refund_cents, paid_cents, order_id)
            )
        net_cents = paid_cents - refund_cents
        orders_out.append(
            {
                "order_id": order_id,
                "customer": customer,
                "paid_cents": paid_cents,
                "refund_cents": refund_cents,
                "net_cents": net_cents,
            }
        )
        customers_net[customer] = customers_net.get(customer, 0) + net_cents
        total_paid += paid_cents
        total_refund += refund_cents

    customers_out = [
        {"customer": c, "net_cents": customers_net[c]} for c in sorted(customers_net)
    ]
    total_net = total_paid - total_refund
    return {
        "orders": orders_out,
        "customers": customers_out,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_net,
        },
    }


def _csv_text(header, rows):
    """Render a CSV document with the standard csv writer."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Render a reconcile result as the release bundle (release-spec).

    Returns exactly three files: orders.csv, customers.csv, summary.json.
    Row order follows reconcile ordering; amounts are integer text;
    summary.json is exactly result["totals"].
    """
    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            (
                o["order_id"],
                o["customer"],
                str(o["paid_cents"]),
                str(o["refund_cents"]),
                str(o["net_cents"]),
            )
            for o in result["orders"]
        ],
    )
    customers_csv = _csv_text(
        ["customer", "net_cents"],
        [(c["customer"], str(c["net_cents"])) for c in result["customers"]],
    )
    summary_json = json.dumps(result["totals"], sort_keys=True)
    return {"orders.csv": orders_csv, "customers.csv": customers_csv, "summary.json": summary_json}
