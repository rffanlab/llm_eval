"""Order reconciliation per spec-v1 and spec-v2.

reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None) -> dict
Pure function: parses CSV strings, no file/network/process access.
Amounts use decimal fixed-point; outputs are integer cents.

v1: amounts max 2 decimals, refunds have no status, no cutoff.
v2: cutoff required (YYYY-MM-DDTHH:MM:SSZ); orders counted only if
    created_at <= cutoff and paid; refunds counted only if succeeded and
    created_at <= cutoff; amounts may have many decimals, rounded to cents
    with Decimal ROUND_HALF_UP (per line, then summed).

export_bundle(result) -> dict[str, str] with exactly orders.csv,
customers.csv and summary.json per release-spec.md.
"""

import csv
import io
import json
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

_ORDER_HEADER = ["order_id", "customer", "amount", "status", "created_at"]
_REFUND_HEADER_V1 = ["refund_id", "order_id", "amount"]
_REFUND_HEADER_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]

_DIGITS = "0123456789"


def _is_decimal_str(text, max_frac):
    """Non-negative plain decimal string, at most max_frac fraction digits.

    Rejects signs, exponents, NaN/Infinity, empty. max_frac=None means any
    number of fraction digits.
    """
    if not isinstance(text, str):
        return False
    s = text.strip()
    if not s:
        return False
    parts = s.split(".")
    if len(parts) > 2:
        return False
    int_part = parts[0]
    frac_part = parts[1] if len(parts) == 2 else ""
    if not int_part or any(ch not in _DIGITS for ch in int_part):
        return False
    if max_frac is not None and len(frac_part) > max_frac:
        return False
    if any(ch not in _DIGITS for ch in frac_part):
        return False
    return True


def _parse_amount_cents(text, field, max_frac=2):
    """Convert a decimal string to integer cents without float math.

    max_frac=2 (v1): reject more than two fraction digits.
    max_frac=None (v2): accept any digits, ROUND_HALF_UP to cents.
    """
    if not _is_decimal_str(text, max_frac):
        raise ValueError("invalid %s: %r" % (field, text))
    s = text.strip()
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError("invalid %s: %r" % (field, text))
    if max_frac is None:
        return int(d.scaleb(2).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    cents = d.scaleb(2)
    if cents != cents.to_integral_value():
        raise ValueError("invalid %s: %r" % (field, text))
    return int(cents)


def _is_valid_cutoff(text):
    """Strict YYYY-MM-DDTHH:MM:SSZ shape check (lexicographic-safe)."""
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


def _read_rows(csv_text, header, kind):
    """Parse a CSV string into a list of dicts keyed by header columns."""
    if not isinstance(csv_text, str):
        raise ValueError("%s csv must be a string" % kind)
    reader = csv.reader(io.StringIO(csv_text))
    try:
        got_header = next(reader)
    except StopIteration:
        raise ValueError("%s csv missing header" % kind)
    if got_header != header:
        raise ValueError(
            "%s csv has bad header: %r (expected %r)" % (kind, got_header, header)
        )
    rows = []
    for raw in reader:
        if not raw or (len(raw) == 1 and raw[0].strip() == ""):
            continue  # ignore blank lines
        if len(raw) != len(header):
            raise ValueError("%s row has wrong column count: %r" % (kind, raw))
        rows.append(dict(zip(header, raw)))
    return rows


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy == "v1":
        max_frac = 2
        refund_header = _REFUND_HEADER_V1
    elif policy == "v2":
        if not _is_valid_cutoff(cutoff):
            raise ValueError("v2 policy requires cutoff YYYY-MM-DDTHH:MM:SSZ")
        max_frac = None
        refund_header = _REFUND_HEADER_V2
    else:
        raise ValueError("unsupported policy: %r" % (policy,))

    def amount(text, field):
        return _parse_amount_cents(text, field, max_frac=max_frac)

    # ---- orders: parse, validate amounts, dedupe by order_id ----
    order_rows = _read_rows(orders_csv, _ORDER_HEADER, "orders")
    orders = {}  # order_id -> row dict (raw fields)
    for row in order_rows:
        oid = row["order_id"]
        # Validate amount early so bad data fails even on duplicate rows.
        amount(row["amount"], "order amount")
        if oid in orders:
            if orders[oid] == row:
                continue  # exact duplicate, count once
            raise ValueError("conflicting rows for order_id %r" % (oid,))
        orders[oid] = row

    # ---- refunds: parse, validate amounts, dedupe by refund_id ----
    refund_rows = _read_rows(refunds_csv, refund_header, "refunds")
    refunds = {}  # refund_id -> row dict
    for row in refund_rows:
        rid = row["refund_id"]
        amount(row["amount"], "refund amount")
        if policy == "v2" and row["status"] not in ("succeeded", "pending"):
            raise ValueError("invalid refund status: %r" % (row["status"],))
        if rid in refunds:
            if refunds[rid] == row:
                continue
            raise ValueError("conflicting rows for refund_id %r" % (rid,))
        refunds[rid] = row

    # ---- classify refunds; validate them against orders ----
    counted = set()  # refund_ids that should be counted
    for rid, row in refunds.items():
        if policy == "v2":
            if row["status"] != "succeeded" or row["created_at"] > cutoff:
                continue  # pending / after cutoff: not counted, no checks
        counted.add(rid)
        oid = row["order_id"]
        order = orders.get(oid)
        if order is None:
            raise ValueError("refund %s references unknown order %r" % (rid, oid))
        if order["status"] != "paid":
            raise ValueError("refund %s targets non-paid order %r" % (rid, oid))
        # v2: refund whose order exists+paid but is excluded by cutoff is
        # ignored (not counted) -- handled by the order loop below.

    refund_by_order = {}
    for rid in counted:
        row = refunds[rid]
        oid = row["order_id"]
        if policy == "v2" and orders[oid]["created_at"] > cutoff:
            continue  # order excluded by cutoff -> ignore its refunds
        refund_by_order[oid] = (
            refund_by_order.get(oid, 0) + amount(row["amount"], "refund amount")
        )

    # ---- build results for counted paid orders only ----
    paid_orders = []
    totals_paid = 0
    totals_refund = 0
    customer_net = {}
    for oid in sorted(orders):
        row = orders[oid]
        if row["status"] != "paid":
            continue
        if policy == "v2" and row["created_at"] > cutoff:
            continue  # order created after cutoff
        paid_cents = amount(row["amount"], "order amount")
        refund_cents = refund_by_order.get(oid, 0)
        if refund_cents > paid_cents:
            raise ValueError(
                "refunds exceed paid amount for order %r (%d > %d)"
                % (oid, refund_cents, paid_cents)
            )
        net_cents = paid_cents - refund_cents
        paid_orders.append(
            {
                "order_id": oid,
                "customer": row["customer"],
                "paid_cents": paid_cents,
                "refund_cents": refund_cents,
                "net_cents": net_cents,
            }
        )
        totals_paid += paid_cents
        totals_refund += refund_cents
        customer_net[row["customer"]] = (
            customer_net.get(row["customer"], 0) + net_cents
        )

    customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]

    return {
        "orders": paid_orders,
        "customers": customers,
        "totals": {
            "paid_cents": totals_paid,
            "refund_cents": totals_refund,
            "net_cents": totals_paid - totals_refund,
        },
    }


def _csv_text(rows, header):
    """Render rows (list of dicts) to CSV text with the given header."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow([row[col] for col in header])
    return buf.getvalue()


def export_bundle(result):
    """Render a reconcile result into the release bundle files.

    Returns exactly {"orders.csv", "customers.csv", "summary.json"} as
    strings; CSVs keep reconcile ordering with integer amount text, and
    summary.json is exactly result["totals"].
    """
    orders_csv = _csv_text(
        result["orders"],
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
    )
    customers_csv = _csv_text(result["customers"], ["customer", "net_cents"])
    summary_json = json.dumps(result["totals"])
    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
