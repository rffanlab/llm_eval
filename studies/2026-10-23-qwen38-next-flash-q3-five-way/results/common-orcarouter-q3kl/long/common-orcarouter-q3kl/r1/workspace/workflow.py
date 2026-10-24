import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _is_utc_stamp(value):
    """Validate YYYY-MM-DDTHH:MM:SSZ without regex (no extra imports)."""
    if value is None:
        return False
    text = str(value).strip()
    if len(text) != 20 or text[4] != "-" or text[7] != "-" or text[10] != "T" or text[19] != "Z":
        return False
    if text[13] != ":" or text[16] != ":":
        return False
    digits = text[0:4] + text[5:7] + text[8:10] + text[11:13] + text[14:16] + text[17:19]
    if len(digits) != 14 or not digits.isdigit():
        return False
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    hour = int(text[11:13])
    minute = int(text[14:16])
    second = int(text[17:19])
    if month < 1 or month > 12 or day < 1 or day > 31:
        return False
    if hour > 23 or minute > 59 or second > 59:
        return False
    if year < 1:
        return False
    return True


def _parse_cents(amount, allow_fractions=False):
    """Parse a decimal string amount to integer cents.

    v1 (allow_fractions=False): at most two decimals, exact integer cents.
    v2 (allow_fractions=True): any number of decimals, ROUND_HALF_UP to cents.
    Always rejects non-numeric, NaN/Infinity and negative amounts; uses Decimal.
    """
    if amount is None:
        raise ValueError("amount is required")
    text = str(amount).strip()
    if text == "":
        raise ValueError("amount is required")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % (amount,))
    if not value.is_finite():
        raise ValueError("amount must be finite: %r" % (amount,))
    if value < 0:
        raise ValueError("amount must be non-negative: %r" % (amount,))
    if not allow_fractions:
        if -value.as_tuple().exponent > 2:
            raise ValueError("amount must have at most two decimals: %r" % (amount,))
        cents = value * 100
        if cents != cents.to_integral_value():
            raise ValueError("amount does not convert to integer cents: %r" % (amount,))
        return int(cents)
    cents_value = (value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents_value)


def _dedupe(rows, id_field, label):
    """Collapse exact-duplicate rows by id; conflict on same id raises ValueError.

    Conflicts are detected on the raw rows before any v2 filtering, so rows
    that are pending or after-cutoff still participate in duplicate detection.
    """
    seen = {}
    unique = []
    for row in rows:
        key = row[id_field]
        if key is None or str(key).strip() == "":
            raise ValueError("%s id is required" % label)
        payload = tuple(sorted((k, v) for k, v in row.items()))
        if key in seen:
            if seen[key] != payload:
                raise ValueError("conflicting duplicate %s %r" % (label, key))
            continue
        seen[key] = payload
        unique.append(row)
    return unique


def _read_csv(csv_text, id_field, label):
    if csv_text is None:
        raise ValueError("%s csv is required" % label)
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        return []
    if reader.fieldnames is None or id_field not in reader.fieldnames:
        raise ValueError("%s csv must contain %s header" % (label, id_field))
    for row in rows:
        for key, value in row.items():
            if value is None:
                raise ValueError("missing %s field in %s row" % (key, label))
    return _dedupe(rows, id_field, label)


def _check_cutoff(cutoff):
    if cutoff is None:
        raise ValueError("cutoff is required for v2")
    if not _is_utc_stamp(cutoff):
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ: %r" % (cutoff,))
    return str(cutoff).strip()


def _check_created_at(created_at, label):
    if not _is_utc_stamp(created_at):
        raise ValueError("invalid %s created_at: %r" % (label, created_at))
    return str(created_at).strip()


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    v2 = policy == "v2"
    cutoff_at = _check_cutoff(cutoff) if v2 else None
    if not v2 and cutoff is not None:
        raise ValueError("cutoff is not supported in v1")

    orders = _read_csv(orders_csv, "order_id", "order")
    refunds = _read_csv(refunds_csv, "refund_id", "refund")

    paid = {}
    cancelled = set()
    for row in orders:
        order_id = row["order_id"].strip()
        status = row["status"].strip().lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("unknown order status: %r" % (row["status"],))
        if v2:
            created_at = _check_created_at(row.get("created_at"), "order")
            if created_at > cutoff_at:
                continue  # after-cutoff orders are excluded entirely
        if status == "cancelled":
            cancelled.add(order_id)
            continue
        paid[order_id] = {
            "order_id": order_id,
            "customer": row["customer"].strip(),
            "paid_cents": _parse_cents(row["amount"], allow_fractions=v2),
        }

    refund_by_order = {}
    for row in refunds:
        order_id = row["order_id"].strip()
        status = "succeeded"
        if v2:
            status = str(row.get("status", "")).strip().lower()
            if status not in ("succeeded", "pending"):
                raise ValueError("unknown refund status: %r" % (row.get("status"),))
            created_at = _check_created_at(row.get("created_at"), "refund")
            if status == "pending" or created_at > cutoff_at:
                # pending / after-cutoff refunds never count; they are ignored
                # entirely, including when the order is cancelled or unknown.
                continue
        if order_id in cancelled:
            raise ValueError("refund for cancelled order %r" % (order_id,))
        if order_id not in paid:
            raise ValueError("refund for unknown order %r" % (order_id,))
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + _parse_cents(
            row["amount"], allow_fractions=v2
        )

    order_rows = []
    customer_totals = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(paid):
        order = paid[order_id]
        refund_cents = refund_by_order.get(order_id, 0)
        if refund_cents > order["paid_cents"]:
            raise ValueError("refund exceeds paid amount for order %r" % (order_id,))
        net_cents = order["paid_cents"] - refund_cents
        order_rows.append({
            "order_id": order_id,
            "customer": order["customer"],
            "paid_cents": order["paid_cents"],
            "refund_cents": refund_cents,
            "net_cents": net_cents,
        })
        totals["paid_cents"] += order["paid_cents"]
        totals["refund_cents"] += refund_cents
        totals["net_cents"] += net_cents
        customer = order["customer"]
        customer_totals[customer] = customer_totals.get(customer, 0) + net_cents

    customers = [
        {"customer": customer, "net_cents": customer_totals[customer]}
        for customer in sorted(customer_totals)
    ]
    return {"orders": order_rows, "customers": customers, "totals": totals}


def export_bundle(result):
    """Render a reconcile result into the release bundle files.

    Returns exactly three files: orders.csv, customers.csv and summary.json.
    Row order follows the reconcile result order; amounts are integer text.
    """
    orders_buf = io.StringIO(newline="")
    writer = csv.writer(orders_buf)
    writer.writerow(["order_id", "customer", "paid_cents", "refund_cents", "net_cents"])
    for row in result["orders"]:
        writer.writerow([
            row["order_id"],
            row["customer"],
            str(row["paid_cents"]),
            str(row["refund_cents"]),
            str(row["net_cents"]),
        ])

    customers_buf = io.StringIO(newline="")
    writer = csv.writer(customers_buf)
    writer.writerow(["customer", "net_cents"])
    for row in result["customers"]:
        writer.writerow([row["customer"], str(row["net_cents"])])

    return {
        "orders.csv": orders_buf.getvalue(),
        "customers.csv": customers_buf.getvalue(),
        "summary.json": json.dumps(result["totals"]),
    }
