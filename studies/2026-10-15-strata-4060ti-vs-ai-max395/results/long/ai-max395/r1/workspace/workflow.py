"""Order reconciliation per spec-v1 and spec-v2, plus release bundle export.

reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None) -> dict
export_bundle(result) -> dict[str, str] with exactly orders.csv,
customers.csv and summary.json (see release-spec.md).

Pure functions only: no file/network/process access, no dunder attributes.
Amounts use decimal fixed-point; never float*100.

v1: strict amounts (<=2 decimals), old CSV column contract, no cutoff.
v2: cutoff required (YYYY-MM-DDTHH:MM:SSZ); refunds carry status/created_at;
    only paid orders with created_at <= cutoff count; only succeeded refunds
    with created_at <= cutoff count; amounts may have many decimals and are
    rounded to cents with Decimal ROUND_HALF_UP per row before summing.
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_FIELDS = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_FIELDS_V1 = ("refund_id", "order_id", "amount")
_REFUND_FIELDS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")

_DIGITS = "0123456789"


def _is_valid_amount(text, max_decimals):
    """Digits with optional dot and 1..max_decimals decimals; no sign/exponent."""
    if not text:
        return False
    whole, dot, frac = text.partition(".")
    if not whole or any(ch not in _DIGITS for ch in whole):
        return False
    if dot:
        if not frac or any(ch not in _DIGITS for ch in frac):
            return False
        if max_decimals is not None and len(frac) > max_decimals:
            return False
    return True


def _parse_amount_cents(raw, context, max_decimals=None):
    """Parse a non-negative fixed-point amount to integer cents.

    max_decimals=None allows any number of decimals (v2); the value is then
    rounded to cents with ROUND_HALF_UP. With a limit, excess decimals raise.
    """
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = raw.strip()
    if not _is_valid_amount(text, max_decimals):
        raise ValueError("%s: invalid amount %r" % (context, raw))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if not value.is_finite() or value < 0:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    exact_cents = value * Decimal(100)
    cents = exact_cents.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    if max_decimals is not None and cents != exact_cents:
        raise ValueError("%s: more than two decimals %r" % (context, raw))
    return int(cents)


def _is_valid_cutoff(text):
    """Strictly validate YYYY-MM-DDTHH:MM:SSZ and return True if valid."""
    if not isinstance(text, str):
        return False
    if len(text) != 20:
        return False
    if (text[4] != "-" or text[7] != "-" or text[10] != "T"
            or text[13] != ":" or text[16] != ":" or text[19] != "Z"):
        return False
    for index in (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18):
        if text[index] not in _DIGITS:
            return False
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    hour = int(text[11:13])
    minute = int(text[14:16])
    second = int(text[17:19])
    if not 1 <= month <= 12:
        return False
    if hour > 23 or minute > 59 or second > 59:
        return False
    leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
    days_in_month = [31, 29 if leap else 28, 31, 30, 31, 30,
                     31, 31, 30, 31, 30, 31]
    if not 1 <= day <= days_in_month[month - 1]:
        return False
    return True


def _read_rows(csv_text, required_fields, label):
    if csv_text is None:
        raise ValueError("%s: input must be a string" % label)
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows:
        return []  # empty input (no header): treated as no records
    header = [name.strip() for name in rows[0]]
    missing = [name for name in required_fields if name not in header]
    if missing:
        raise ValueError("%s: missing columns %r" % (label, missing))
    records = []
    for row in rows[1:]:
        record = {}
        for index, name in enumerate(header):
            record[name] = row[index].strip() if index < len(row) else ""
        records.append(record)
    return records


def _dedupe(records, id_field, label):
    """Keep first occurrence; identical duplicates collapse; conflicts raise."""
    seen = {}
    unique = []
    for record in records:
        key = record.get(id_field, "")
        if not key:
            raise ValueError("%s: empty %s" % (label, id_field))
        if key in seen:
            if seen[key] != record:
                raise ValueError(
                    "%s: conflicting rows for %s %r" % (label, id_field, key)
                )
            continue
        seen[key] = record
        unique.append(record)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))

    if policy == "v2":
        if cutoff is None:
            raise ValueError("v2 requires a cutoff")
        if not _is_valid_cutoff(cutoff):
            raise ValueError("invalid cutoff %r" % (cutoff,))
        refund_fields = _REFUND_FIELDS_V2
        max_decimals = None
    else:
        refund_fields = _REFUND_FIELDS_V1
        max_decimals = 2

    order_rows = _read_rows(orders_csv, _ORDER_FIELDS, "orders")
    refund_rows = _read_rows(refunds_csv, refund_fields, "refunds")

    # Dedupe first: conflicts are rejected even for pending/after-cutoff rows.
    orders = _dedupe(order_rows, "order_id", "orders")
    refunds = _dedupe(refund_rows, "refund_id", "refunds")

    # All orders keyed by id, with amounts parsed.
    all_orders = {}
    for order in orders:
        order_id = order["order_id"]
        amount_cents = _parse_amount_cents(
            order["amount"], "order %s" % order_id, max_decimals
        )
        all_orders[order_id] = {
            "order_id": order_id,
            "customer": order["customer"],
            "status": order["status"],
            "created_at": order["created_at"],
            "paid_cents": amount_cents,
        }

    # Paid orders within the cutoff window.
    paid_orders = {}
    for order_id in sorted(all_orders):
        order = all_orders[order_id]
        if order["status"] != "paid":
            continue
        if policy == "v2" and order["created_at"] > cutoff:
            continue
        paid_orders[order_id] = order

    refund_by_order = {}
    for refund in refunds:
        refund_id = refund["refund_id"]
        order_id = refund["order_id"]
        if policy == "v2":
            status = refund["status"]
            if status not in ("succeeded", "pending"):
                raise ValueError(
                    "refund %s: invalid status %r" % (refund_id, status)
                )
            if status != "succeeded" or refund["created_at"] > cutoff:
                continue  # pending or after-cutoff refunds never count
        refund_cents = _parse_amount_cents(
            refund["amount"], "refund %s" % refund_id, max_decimals
        )
        if order_id not in paid_orders:
            known = all_orders.get(order_id)
            if (policy == "v2" and known is not None
                    and known["status"] == "paid"
                    and known["created_at"] > cutoff):
                continue  # order exists but excluded by cutoff: ignore
            raise ValueError(
                "refund %s references unknown or cancelled order %r"
                % (refund_id, order_id)
            )
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + refund_cents

    result_orders = []
    customer_totals = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(paid_orders):
        order = paid_orders[order_id]
        refund_cents = refund_by_order.get(order_id, 0)
        if refund_cents > order["paid_cents"]:
            raise ValueError(
                "order %s: refunds exceed paid amount" % order_id
            )
        net_cents = order["paid_cents"] - refund_cents
        result_orders.append({
            "order_id": order_id,
            "customer": order["customer"],
            "paid_cents": order["paid_cents"],
            "refund_cents": refund_cents,
            "net_cents": net_cents,
        })
        customer = order["customer"]
        customer_totals[customer] = customer_totals.get(customer, 0) + net_cents
        total_paid += order["paid_cents"]
        total_refund += refund_cents

    result_customers = [
        {"customer": name, "net_cents": customer_totals[name]}
        for name in sorted(customer_totals)
    ]

    return {
        "orders": result_orders,
        "customers": result_customers,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def _rows_to_csv(header, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """Render a reconcile result into the release bundle files.

    Returns exactly {"orders.csv", "customers.csv", "summary.json"}:
    - orders.csv / customers.csv use the documented headers, keep the
      reconcile ordering, and render amounts as integer text.
    - summary.json is exactly result["totals"] as JSON.
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a dict")
    totals = result.get("totals")
    if not isinstance(totals, dict):
        raise ValueError("result is missing totals")

    order_rows = []
    for order in result.get("orders", []):
        order_rows.append([
            order["order_id"],
            order["customer"],
            int(order["paid_cents"]),
            int(order["refund_cents"]),
            int(order["net_cents"]),
        ])
    orders_csv = _rows_to_csv(
        ("order_id", "customer", "paid_cents", "refund_cents", "net_cents"),
        order_rows,
    )

    customer_rows = []
    for customer in result.get("customers", []):
        customer_rows.append([
            customer["customer"],
            int(customer["net_cents"]),
        ])
    customers_csv = _rows_to_csv(("customer", "net_cents"), customer_rows)

    summary = json.dumps({
        "paid_cents": int(totals["paid_cents"]),
        "refund_cents": int(totals["refund_cents"]),
        "net_cents": int(totals["net_cents"]),
    })

    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary,
    }
