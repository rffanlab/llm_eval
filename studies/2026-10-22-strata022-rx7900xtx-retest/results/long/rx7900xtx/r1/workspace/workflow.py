"""Order reconciliation, spec-v1 and spec-v2 contracts.

Pure functions only: parses CSV strings, uses Decimal fixed-point,
outputs integer cents. No file/network/process access.
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_FIELDS = ["order_id", "customer", "amount", "status", "created_at"]
_REFUND_FIELDS_V1 = ["refund_id", "order_id", "amount"]
_REFUND_FIELDS_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]

_DIGITS = set("0123456789")


def _is_digits(text):
    return bool(text) and all(ch in _DIGITS for ch in text)


def _valid_amount_text_v1(text):
    """v1: non-negative integer or at most two decimal places."""
    if "." in text:
        parts = text.split(".")
        if len(parts) != 2:
            return False
        whole, frac = parts
        return _is_digits(whole) and _is_digits(frac) and len(frac) <= 2
    return _is_digits(text)


def _valid_amount_text_v2(text):
    """v2: non-negative, any number of decimal places."""
    if "." in text:
        parts = text.split(".")
        if len(parts) != 2:
            return False
        whole, frac = parts
        return _is_digits(whole) and _is_digits(frac)
    return _is_digits(text)


def _parse_amount_cents(raw, policy):
    """Return integer cents for a non-negative amount string.

    v1: at most two decimals, exact conversion.
    v2: any decimals, Decimal ROUND_HALF_UP to integer cents.
    Rejects negatives, NaN/Infinity. Never uses float * 100.
    """
    if raw is None:
        raise ValueError("missing amount")
    text = raw.strip()
    if policy == "v1":
        if not _valid_amount_text_v1(text):
            raise ValueError("invalid amount: %r" % (raw,))
    else:
        if not _valid_amount_text_v2(text):
            raise ValueError("invalid amount: %r" % (raw,))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % (raw,))
    cents = (value * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _valid_cutoff(cutoff):
    """Validate cutoff format YYYY-MM-DDTHH:MM:SSZ (digits, ranges)."""
    if not isinstance(cutoff, str) or len(cutoff) != 20:
        return False
    if cutoff[4] != "-" or cutoff[7] != "-":
        return False
    if cutoff[10] != "T" or cutoff[19] != "Z":
        return False
    if cutoff[13] != ":" or cutoff[16] != ":":
        return False
    y, mo, d = cutoff[0:4], cutoff[5:7], cutoff[8:10]
    h, mi, s = cutoff[11:13], cutoff[14:16], cutoff[17:19]
    for part in (y, mo, d, h, mi, s):
        if not _is_digits(part):
            return False
    month, day = int(mo), int(d)
    hour, minute, sec = int(h), int(mi), int(s)
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    return hour <= 23 and minute <= 59 and sec <= 59


def _read_rows(csv_text, expected_fields, kind):
    """Parse a CSV string into a list of dicts keyed by expected fields.

    Returns [] for empty input or header-only input.
    """
    if csv_text is None:
        raise ValueError("missing %s csv" % kind)
    if csv_text == "":
        return []
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        return []
    header = [h.strip() for h in header]
    if header != expected_fields:
        raise ValueError("bad %s header: %r" % (kind, header))
    rows = []
    for line in reader:
        if not line or (len(line) == 1 and line[0].strip() == ""):
            continue  # skip blank lines
        if len(line) != len(expected_fields):
            raise ValueError("bad %s row: %r" % (kind, line))
        rows.append({k: v.strip() for k, v in zip(expected_fields, line)})
    return rows


def _dedupe(rows, id_field, kind):
    """Deduplicate rows by id: exact duplicates collapse; conflicts raise.

    Runs before any cutoff/status filtering, so conflicts involving
    pending or post-cutoff rows are still rejected.
    """
    seen = {}
    unique = []
    for row in rows:
        key = row[id_field]
        if key in seen:
            if seen[key] != row:
                raise ValueError(
                    "conflicting %s rows for id %r" % (kind, key)
                )
            continue  # exact duplicate, count once
        seen[key] = row
        unique.append(row)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile orders and refunds per the v1/v2 contract.

    Returns {"orders": [...], "customers": [...], "totals": {...}} with
    all money as integer cents. Raises ValueError on invalid data.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v2":
        if cutoff is None:
            raise ValueError("cutoff is required for policy v2")
        if not _valid_cutoff(cutoff):
            raise ValueError("invalid cutoff: %r" % (cutoff,))

    refund_fields = _REFUND_FIELDS_V1 if policy == "v1" else _REFUND_FIELDS_V2
    order_rows = _dedupe(
        _read_rows(orders_csv, _ORDER_FIELDS, "orders"), "order_id", "order"
    )
    refund_rows = _dedupe(
        _read_rows(refunds_csv, refund_fields, "refunds"), "refund_id", "refund"
    )

    # Parse and validate all orders (existence map covers excluded ones).
    orders = {}
    for row in order_rows:
        status = row["status"]
        if status not in ("paid", "cancelled"):
            raise ValueError("unknown order status: %r" % (status,))
        if not row["order_id"] or not row["customer"]:
            raise ValueError("empty order_id or customer")
        paid_cents = _parse_amount_cents(row["amount"], policy)
        orders[row["order_id"]] = {
            "order_id": row["order_id"],
            "customer": row["customer"],
            "status": status,
            "paid_cents": paid_cents,
            "created_at": row["created_at"],
        }

    def _order_included(order):
        if order["status"] != "paid":
            return False
        if policy == "v2" and order["created_at"] > cutoff:
            return False
        return True

    # Validate refund statuses up front (v2), even for excluded rows.
    if policy == "v2":
        for row in refund_rows:
            if row["status"] not in ("succeeded", "pending"):
                raise ValueError("unknown refund status: %r" % (row["status"],))
            if not row["refund_id"]:
                raise ValueError("empty refund_id")

    refund_cents_by_order = {}
    for row in refund_rows:
        oid = row["order_id"]
        if policy == "v1":
            effective = True
        else:
            effective = row["status"] == "succeeded" and row["created_at"] <= cutoff
        order = orders.get(oid)
        if effective:
            # Effective refund pointing at a truly missing or cancelled
            # order is an error in both policies; orders excluded only
            # by cutoff are ignored (handled below).
            if order is None:
                raise ValueError("refund %r for unknown order %r"
                                 % (row["refund_id"], oid))
            if order["status"] != "paid":
                raise ValueError("refund %r for cancelled order %r"
                                 % (row["refund_id"], oid))
        if not effective:
            continue
        if not _order_included(order):
            # refund whose order exists but is excluded by cutoff: ignore
            continue
        amount = _parse_amount_cents(row["amount"], policy)
        refund_cents_by_order[oid] = refund_cents_by_order.get(oid, 0) + amount
        if refund_cents_by_order[oid] > order["paid_cents"]:
            raise ValueError("refunds exceed paid amount for order %r" % (oid,))

    result_orders = []
    customers_total = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for oid in sorted(orders):
        order = orders[oid]
        if not _order_included(order):
            continue
        refund = refund_cents_by_order.get(oid, 0)
        net = order["paid_cents"] - refund
        result_orders.append({
            "order_id": oid,
            "customer": order["customer"],
            "paid_cents": order["paid_cents"],
            "refund_cents": refund,
            "net_cents": net,
        })
        customers_total[order["customer"]] = (
            customers_total.get(order["customer"], 0) + net
        )
        totals["paid_cents"] += order["paid_cents"]
        totals["refund_cents"] += refund
        totals["net_cents"] += net

    customers = [
        {"customer": name, "net_cents": customers_total[name]}
        for name in sorted(customers_total)
    ]
    return {"orders": result_orders, "customers": customers, "totals": totals}


def _csv_text(header, rows):
    """Render rows (list of lists) as CSV text with a standard writer."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Build the release bundle: exactly three files.

    orders.csv    : order_id,customer,paid_cents,refund_cents,net_cents
    customers.csv : customer,net_cents
    summary.json  : exactly result["totals"]
    Row order follows reconcile ordering; amounts are integer text.
    """
    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            [o["order_id"], o["customer"], o["paid_cents"],
             o["refund_cents"], o["net_cents"]]
            for o in result["orders"]
        ],
    )
    customers_csv = _csv_text(
        ["customer", "net_cents"],
        [[c["customer"], c["net_cents"]] for c in result["customers"]],
    )
    summary_json = json.dumps(result["totals"], sort_keys=True)
    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
