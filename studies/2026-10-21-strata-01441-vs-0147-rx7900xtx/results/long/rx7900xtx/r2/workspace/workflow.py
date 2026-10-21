"""Order reconciliation.

Contracts:
- spec-v1: policy="v1", legacy CSV columns, amounts with at most 2 decimals.
- spec-v2: policy="v2", cutoff required (YYYY-MM-DDTHH:MM:SSZ), refund
  status/created_at columns, amounts with any decimals rounded to cents with
  Decimal ROUND_HALF_UP (per row, before aggregation).
- release-spec: export_bundle(result) -> dict with exactly three files:
  orders.csv, customers.csv, summary.json.

Pure functions only; no file/network/process access. Decimal fixed-point,
never float*100. Output structure and ordering are identical for v1 and v2.
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_FIELDS = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_FIELDS_V1 = ("refund_id", "order_id", "amount")
_REFUND_FIELDS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")

_VALID_ORDER_STATUS = ("paid", "cancelled")
_VALID_REFUND_STATUS = ("succeeded", "pending")


def _is_valid_amount_text(text, max_decimals):
    """Non-negative fixed-point digits with at most `max_decimals` places."""
    if not text:
        return False
    if "." in text:
        parts = text.split(".")
        if len(parts) != 2:
            return False
        whole, frac = parts
        if not whole.isdigit() or not frac.isdigit():
            return False
        if len(frac) > max_decimals:
            return False
    else:
        if not text.isdigit():
            return False
    return True


def _is_valid_cutoff(text):
    """Strictly validate YYYY-MM-DDTHH:MM:SSZ (digits, ranges, calendar)."""
    if not isinstance(text, str) or len(text) != 20:
        return False
    if (text[4] != "-" or text[7] != "-" or text[10] != "T"
            or text[13] != ":" or text[16] != ":" or text[19] != "Z"):
        return False
    digits = (text[0:4] + text[5:7] + text[8:10]
              + text[11:13] + text[14:16] + text[17:19])
    if not digits.isdigit():
        return False
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    hour = int(text[11:13])
    minute = int(text[14:16])
    second = int(text[17:19])
    if not (1 <= month <= 12):
        return False
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return False
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        days_in_month[1] = 29
    if not (1 <= day <= days_in_month[month - 1]):
        return False
    return True


def _parse_amount_cents(raw, allow_extra_decimals=False):
    """Parse a non-negative fixed-point amount and return integer cents.

    v1 (allow_extra_decimals=False): reject more than two decimal places.
    v2 (allow_extra_decimals=True): accept any decimals, ROUND_HALF_UP to
    cents per row before aggregation.
    Raises ValueError on negatives, NaN/Infinity, exponents, etc.
    """
    if not isinstance(raw, str):
        raise ValueError("amount must be a string")
    text = raw.strip()
    max_decimals = 10 ** 9 if allow_extra_decimals else 2
    if not _is_valid_amount_text(text, max_decimals):
        raise ValueError("invalid amount: %r" % (raw,))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % (raw,))
    if not value.is_finite() or value < 0:
        raise ValueError("invalid amount: %r" % (raw,))
    cents = (value * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _read_rows(csv_text, expected_fields, kind):
    if csv_text is None:
        raise ValueError("%s csv must not be None" % kind)
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        # Completely empty input: treat as no rows.
        return []
    if tuple(reader.fieldnames) != expected_fields:
        raise ValueError(
            "%s csv header mismatch: expected %s, got %s"
            % (kind, list(expected_fields), list(reader.fieldnames))
        )
    rows = []
    for row in reader:
        if any(row.get(name) is None for name in expected_fields):
            raise ValueError("%s row has missing fields: %r" % (kind, row))
        rows.append({name: row[name] for name in expected_fields})
    return rows


def _dedupe(rows, id_field, kind):
    """Return {id: row}; identical duplicate rows collapse, conflicts raise.

    Conflicts are rejected even when the rows differ only in fields that are
    later filtered out (status, timestamps, ...).
    """
    seen = {}
    for row in rows:
        key = row[id_field]
        if key in seen:
            if seen[key] != row:
                raise ValueError(
                    "conflicting duplicate %s id %r" % (kind, key)
                )
            continue
        seen[key] = row
    return seen


def _reconcile_v1(orders_csv, refunds_csv):
    order_rows = _read_rows(orders_csv, _ORDER_FIELDS, "orders")
    refund_rows = _read_rows(refunds_csv, _REFUND_FIELDS_V1, "refunds")

    orders = _dedupe(order_rows, "order_id", "order")
    refunds = _dedupe(refund_rows, "refund_id", "refund")

    paid_cents_by_order = {}
    customer_by_order = {}
    for order_id, row in orders.items():
        status = row["status"]
        if status not in _VALID_ORDER_STATUS:
            raise ValueError("unknown order status: %r" % (status,))
        if status == "cancelled":
            continue
        paid_cents_by_order[order_id] = _parse_amount_cents(
            row["amount"], allow_extra_decimals=False)
        customer_by_order[order_id] = row["customer"]

    refund_cents_by_order = {order_id: 0 for order_id in paid_cents_by_order}
    for refund_id, row in refunds.items():
        order_id = row["order_id"]
        if order_id not in paid_cents_by_order:
            raise ValueError(
                "refund %s references unknown or cancelled order %r"
                % (refund_id, order_id)
            )
        refund_cents = _parse_amount_cents(row["amount"], allow_extra_decimals=False)
        refund_cents_by_order[order_id] += refund_cents
        if refund_cents_by_order[order_id] > paid_cents_by_order[order_id]:
            raise ValueError(
                "refunds exceed paid amount for order %r" % (order_id,)
            )

    return _build_result(paid_cents_by_order, customer_by_order, refund_cents_by_order)


def _reconcile_v2(orders_csv, refunds_csv, cutoff):
    if not _is_valid_cutoff(cutoff):
        raise ValueError("v2 requires a valid cutoff YYYY-MM-DDTHH:MM:SSZ")

    order_rows = _read_rows(orders_csv, _ORDER_FIELDS, "orders")
    refund_rows = _read_rows(refunds_csv, _REFUND_FIELDS_V2, "refunds")

    # Dedupe first: conflicts must be rejected regardless of filtering.
    orders = _dedupe(order_rows, "order_id", "order")
    refunds = _dedupe(refund_rows, "refund_id", "refund")

    order_status = {}
    paid_cents_all = {}
    created_all = {}
    customer_by_order = {}
    for order_id, row in orders.items():
        status = row["status"]
        if status not in _VALID_ORDER_STATUS:
            raise ValueError("unknown order status: %r" % (status,))
        order_status[order_id] = status
        paid_cents_all[order_id] = _parse_amount_cents(
            row["amount"], allow_extra_decimals=True)
        created_all[order_id] = row["created_at"]
        customer_by_order[order_id] = row["customer"]

    # Paid orders within the cutoff are the ones included in the result.
    paid_cents_by_order = {}
    included_customer = {}
    for order_id, status in order_status.items():
        if status == "paid" and created_all[order_id] <= cutoff:
            paid_cents_by_order[order_id] = paid_cents_all[order_id]
            included_customer[order_id] = customer_by_order[order_id]

    refund_cents_by_order = {order_id: 0 for order_id in paid_cents_by_order}
    for refund_id, row in refunds.items():
        order_id = row["order_id"]
        status = row["status"]
        if status not in _VALID_REFUND_STATUS:
            raise ValueError("unknown refund status: %r" % (status,))
        if order_id not in order_status or order_status[order_id] == "cancelled":
            raise ValueError(
                "refund %s references unknown or cancelled order %r"
                % (refund_id, order_id)
            )
        # pending refunds, refunds after the cutoff, and refunds whose paid
        # order was excluded by the cutoff are ignored.
        if status != "succeeded" or row["created_at"] > cutoff:
            continue
        if order_id not in paid_cents_by_order:
            continue
        refund_cents = _parse_amount_cents(row["amount"], allow_extra_decimals=True)
        refund_cents_by_order[order_id] += refund_cents
        if refund_cents_by_order[order_id] > paid_cents_by_order[order_id]:
            raise ValueError(
                "refunds exceed paid amount for order %r" % (order_id,)
            )

    return _build_result(paid_cents_by_order, included_customer, refund_cents_by_order)


def _build_result(paid_cents_by_order, customer_by_order, refund_cents_by_order):
    order_entries = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(paid_cents_by_order):
        paid = paid_cents_by_order[order_id]
        refunded = refund_cents_by_order[order_id]
        net = paid - refunded
        customer = customer_by_order[order_id]
        order_entries.append(
            {
                "order_id": order_id,
                "customer": customer,
                "paid_cents": paid,
                "refund_cents": refunded,
                "net_cents": net,
            }
        )
        customer_net[customer] = customer_net.get(customer, 0) + net
        totals["paid_cents"] += paid
        totals["refund_cents"] += refunded
        totals["net_cents"] += net

    customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]

    return {"orders": order_entries, "customers": customers, "totals": totals}


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    # v1 keeps its original behavior and ignores cutoff; v2 requires it.
    if policy == "v1":
        return _reconcile_v1(orders_csv, refunds_csv)
    if policy == "v2":
        if cutoff is None:
            raise ValueError("v2 requires a cutoff")
        return _reconcile_v2(orders_csv, refunds_csv, cutoff)
    raise ValueError("unsupported policy: %r" % (policy,))


def _csv_text(header, rows):
    """Render CSV with the standard csv writer; amounts are integer text."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """Build the release bundle per release-spec.md.

    Returns exactly three files: orders.csv, customers.csv, summary.json.
    Row order follows the reconcile ordering; amounts are integer text;
    summary.json parses to exactly result["totals"].
    """
    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            [
                entry["order_id"],
                entry["customer"],
                str(entry["paid_cents"]),
                str(entry["refund_cents"]),
                str(entry["net_cents"]),
            ]
            for entry in result["orders"]
        ],
    )
    customers_csv = _csv_text(
        ["customer", "net_cents"],
        [
            [entry["customer"], str(entry["net_cents"])]
            for entry in result["customers"]
        ],
    )
    summary_json = json.dumps(result["totals"])
    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
