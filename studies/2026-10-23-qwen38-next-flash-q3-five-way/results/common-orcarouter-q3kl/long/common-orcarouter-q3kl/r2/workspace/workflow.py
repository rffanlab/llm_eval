"""Reconciliation delivery workflow (v1 + v2 contracts).

Pure functions only: parses UTF-8 CSV strings, no file/network access.
v1: amounts at most 2 decimals, exact cents.
v2: cutoff required, order/refund created_at + refund status, amounts
    rounded to cents with Decimal ROUND_HALF_UP (per line, then summed).
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _validate_timestamp(text):
    if not isinstance(text, str) or len(text) != 20 or not text.endswith("Z"):
        raise ValueError("invalid timestamp: %r" % (text,))
    digits = text[:19]
    ok = all(ch.isdigit() or ch in "-:T" for ch in digits)
    ok = ok and digits[4] == "-" and digits[7] == "-" and digits[10] == "T" and digits[13] == ":" and digits[16] == ":"
    if not ok:
        raise ValueError("invalid timestamp: %r" % (text,))


def _validate_amount(raw):
    """Common amount checks: finite, non-negative, no NaN/Infinity."""
    if raw is None:
        raise ValueError("amount is missing")
    text = raw.strip()
    if not text:
        raise ValueError("amount is empty")
    lowered = text.lower().lstrip("+-")
    if lowered.startswith(("nan", "inf")):
        raise ValueError("amount is not a finite number: %r" % raw)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("amount is not a valid decimal: %r" % raw)
    if not value.is_finite():
        raise ValueError("amount is not finite: %r" % raw)
    if value < 0:
        raise ValueError("amount is negative: %r" % raw)
    return value


def _parse_cents(raw):
    """v1: at most two decimals, exact integer cents."""
    value = _validate_amount(raw)
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2:
        raise ValueError("amount has more than two decimals: %r" % raw)
    return int(value * 100)  # exact: at most two decimal places


def _parse_cents_rounded(raw):
    """v2: any number of decimals, ROUND_HALF_UP to integer cents."""
    value = _validate_amount(raw)
    return int(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def _read_rows(csv_string, required_headers, kind):
    if csv_string is None:
        raise ValueError("%s CSV is missing" % kind)
    reader = csv.DictReader(io.StringIO(csv_string, newline=""))
    if reader.fieldnames is None:
        raise ValueError("%s CSV has no header row" % kind)
    headers = [name.strip() if name else name for name in reader.fieldnames]
    for column in required_headers:
        if column not in headers:
            raise ValueError("%s CSV missing column %r" % (kind, column))
    rows = []
    for row in reader:
        clean = {}
        for key in required_headers:
            value = row.get(key)
            clean[key] = "" if value is None else value
        rows.append(clean)
    return rows


def _validate_unique(rows, key_field, kind):
    """Deduplicate identical rows by id; conflict on same id raises ValueError.

    Runs before any filtering so pending/after-cutoff conflicts are still caught.
    """
    seen = {}
    unique = []
    for row in rows:
        key = row[key_field]
        if not key:
            raise ValueError("blank %s id in %s" % (key_field, kind))
        fingerprint = tuple(sorted(row.items()))
        if key in seen:
            if seen[key] != fingerprint:
                raise ValueError("conflicting rows for %s id %r in %s" % (key_field, key, kind))
            continue  # exact duplicate row: counted once
        seen[key] = fingerprint
        unique.append(row)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds per the v1/v2 contracts."""
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    v2 = policy == "v2"
    if v2:
        if cutoff is None:
            raise ValueError("cutoff is required for policy v2")
        _validate_timestamp(cutoff)

    parse = _parse_cents_rounded if v2 else _parse_cents

    order_rows = _read_rows(orders_csv, ("order_id", "customer", "amount", "status", "created_at"), "orders")
    refund_columns = ("refund_id", "order_id", "amount", "status", "created_at") if v2 else ("refund_id", "order_id", "amount")
    refund_rows = _read_rows(refunds_csv, refund_columns, "refunds")

    order_rows = _validate_unique(order_rows, "order_id", "orders")
    refund_rows = _validate_unique(refund_rows, "refund_id", "refunds")

    paid_cents = {}   # orders counted (paid, within cutoff)
    excluded = set()  # cancelled, or (v2) paid but after cutoff: refunds ignored
    for row in order_rows:
        status = row["status"].strip().lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("unknown order status %r" % row["status"])
        cents = parse(row["amount"])
        order_id = row["order_id"]
        if status == "cancelled":
            excluded.add(order_id)
            continue
        if v2:
            _validate_timestamp(row["created_at"])
            if row["created_at"] > cutoff:
                excluded.add(order_id)  # paid but after cutoff: refunds ignored
                continue
        paid_cents[order_id] = {"customer": row["customer"], "cents": cents}

    refund_cents = {}
    for row in refund_rows:
        if v2:
            status = row["status"].strip().lower()
            if status not in ("succeeded", "pending"):
                raise ValueError("unknown refund status %r" % row["status"])
            if status == "pending":
                continue
            _validate_timestamp(row["created_at"])
            if row["created_at"] > cutoff:
                continue
        order_id = row["order_id"]
        if order_id not in paid_cents:
            if order_id in excluded:
                continue  # refund for order excluded by cutoff: ignored
            raise ValueError("refund %r targets unknown or cancelled order %r" % (row["refund_id"], order_id))
        refund_cents[order_id] = refund_cents.get(order_id, 0) + parse(row["amount"])

    for order_id, total in refund_cents.items():
        if total > paid_cents[order_id]["cents"]:
            raise ValueError("refunds exceed paid amount for order %r" % order_id)

    orders_out = []
    customers = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(paid_cents):
        info = paid_cents[order_id]
        paid = info["cents"]
        refunded = refund_cents.get(order_id, 0)
        net = paid - refunded
        orders_out.append({
            "order_id": order_id,
            "customer": info["customer"],
            "paid_cents": paid,
            "refund_cents": refunded,
            "net_cents": net,
        })
        customers[info["customer"]] = customers.get(info["customer"], 0) + net
        total_paid += paid
        total_refund += refunded

    customers_out = [
        {"customer": name, "net_cents": customers[name]}
        for name in sorted(customers)
    ]
    return {
        "orders": orders_out,
        "customers": customers_out,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def _csv_text(rows, header):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([row[column] for column in header])
    return buffer.getvalue()


def export_bundle(result):
    """Render a reconcile result into the three release files (release-spec)."""
    if not isinstance(result, dict) or "orders" not in result or "customers" not in result or "totals" not in result:
        raise ValueError("result must be a reconcile output dict")
    orders_csv = _csv_text(
        result["orders"],
        ("order_id", "customer", "paid_cents", "refund_cents", "net_cents"),
    )
    customers_csv = _csv_text(result["customers"], ("customer", "net_cents"))
    summary = json.dumps({
        "paid_cents": int(result["totals"]["paid_cents"]),
        "refund_cents": int(result["totals"]["refund_cents"]),
        "net_cents": int(result["totals"]["net_cents"]),
    }, sort_keys=True)
    return {"orders.csv": orders_csv, "customers.csv": customers_csv, "summary.json": summary}
