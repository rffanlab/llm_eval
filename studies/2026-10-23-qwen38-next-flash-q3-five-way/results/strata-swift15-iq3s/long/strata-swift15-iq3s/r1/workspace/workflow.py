"""Order reconciliation per spec-v1 and spec-v2, plus release bundle export.

Pure functions only; no file/network/process access. Uses decimal fixed-point.
"""

import csv
import io
import json
from decimal import Decimal, ROUND_HALF_UP

_ORDER_COLUMNS = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_COLUMNS_V1 = ("refund_id", "order_id", "amount")
_REFUND_COLUMNS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")

_DIGITS = set("0123456789")


def _is_amount_text(text, max_frac):
    """Non-negative decimal text; at most max_frac fraction digits (None = any)."""
    if not text:
        return False
    if "." in text:
        parts = text.split(".")
        if len(parts) != 2:
            return False
        int_part, frac_part = parts
        if not int_part:
            return False
        if not (1 <= len(frac_part)):
            return False
        if max_frac is not None and len(frac_part) > max_frac:
            return False
        for ch in int_part + frac_part:
            if ch not in _DIGITS:
                return False
        return True
    for ch in text:
        if ch not in _DIGITS:
            return False
    return True


def _amount_to_cents_v1(value, context):
    """v1: at most two decimals, exact cents only."""
    if not isinstance(value, str):
        raise ValueError("invalid amount in %s: %r" % (context, value))
    text = value.strip()
    if not _is_amount_text(text, 2):
        raise ValueError("invalid amount in %s: %r" % (context, value))
    cents = Decimal(text) * 100
    if cents != cents.to_integral_value():
        raise ValueError("amount not representable in cents in %s: %r" % (context, value))
    return int(cents)


def _amount_to_cents_v2(value, context):
    """v2: any number of decimals, ROUND_HALF_UP to integer cents."""
    if not isinstance(value, str):
        raise ValueError("invalid amount in %s: %r" % (context, value))
    text = value.strip()
    if not _is_amount_text(text, None):
        raise ValueError("invalid amount in %s: %r" % (context, value))
    cents = (Decimal(text) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _is_utc_timestamp(text):
    if not isinstance(text, str) or len(text) != 20:
        return False
    if text[4] != "-" or text[7] != "-" or text[10] != "T":
        return False
    if text[13] != ":" or text[16] != ":" or text[19] != "Z":
        return False
    for pos in (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18):
        if text[pos] not in _DIGITS:
            return False
    return True


def _check_cutoff(cutoff):
    if not _is_utc_timestamp(cutoff):
        raise ValueError("invalid cutoff: %r" % (cutoff,))


def _read_rows(csv_text, required, kind):
    if not isinstance(csv_text, str):
        raise ValueError("%s input must be a string" % kind)
    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = reader.fieldnames
    if fieldnames is None:
        raise ValueError("%s input missing header" % kind)
    for col in required:
        if col not in fieldnames:
            raise ValueError("%s input missing column: %s" % (kind, col))
    return list(reader)


def _dedupe(rows, id_column, required, kind):
    """Return {id: row} keeping first occurrence of exact duplicates.

    Same id with any differing field -> ValueError (checked on all rows,
    including pending / post-cutoff rows).
    """
    seen = {}
    result = {}
    for row in rows:
        ident = row[id_column]
        key = tuple(row[col] for col in required)
        if ident in seen:
            if seen[ident] != key:
                raise ValueError(
                    "duplicate %s id %r with differing fields" % (kind, ident)
                )
            continue
        seen[ident] = key
        result[ident] = row
    return result


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy == "v1":
        amount_to_cents = _amount_to_cents_v1
        refund_columns = _REFUND_COLUMNS_V1
        use_cutoff = False
    elif policy == "v2":
        if cutoff is None:
            raise ValueError("policy v2 requires cutoff")
        _check_cutoff(cutoff)
        amount_to_cents = _amount_to_cents_v2
        refund_columns = _REFUND_COLUMNS_V2
        use_cutoff = True
    else:
        raise ValueError("unsupported policy: %r" % (policy,))

    order_rows = _read_rows(orders_csv, _ORDER_COLUMNS, "orders")
    refund_rows = _read_rows(refunds_csv, refund_columns, "refunds")

    orders_by_id = _dedupe(order_rows, "order_id", _ORDER_COLUMNS, "order")
    refunds_by_id = _dedupe(refund_rows, "refund_id", refund_columns, "refund")

    # Validate and parse every order row (including cancelled).
    parsed_orders = {}
    for oid, row in orders_by_id.items():
        cents = amount_to_cents(row["amount"], "order %s" % oid)
        if use_cutoff and not _is_utc_timestamp(row["created_at"]):
            raise ValueError("invalid created_at for order %s: %r" % (oid, row["created_at"]))
        parsed_orders[oid] = {
            "order_id": row["order_id"],
            "customer": row["customer"],
            "status": row["status"],
            "created_at": row["created_at"],
            "paid_cents": cents,
        }

    # Process refunds (deterministic order for error reporting).
    refund_cents_by_order = {}
    for rid in sorted(refunds_by_id):
        row = refunds_by_id[rid]
        oid = row["order_id"]

        if use_cutoff:
            status = row["status"]
            if status not in ("succeeded", "pending"):
                raise ValueError("refund %s has invalid status: %r" % (rid, status))
            if not _is_utc_timestamp(row["created_at"]):
                raise ValueError(
                    "invalid created_at for refund %s: %r" % (rid, row["created_at"])
                )
            # Only effective refunds (succeeded, created_at <= cutoff) matter.
            if status != "succeeded" or row["created_at"] > cutoff:
                continue

        order = parsed_orders.get(oid)
        if order is None:
            raise ValueError("refund %s references unknown order %r" % (rid, oid))
        if order["status"] != "paid":
            raise ValueError(
                "refund %s references non-paid order %s (%s)"
                % (rid, oid, order["status"])
            )
        if use_cutoff and order["created_at"] > cutoff:
            # Order exists but is excluded by cutoff: ignore the refund.
            continue

        cents = amount_to_cents(row["amount"], "refund %s" % rid)
        total = refund_cents_by_order.get(oid, 0) + cents
        if total > order["paid_cents"]:
            raise ValueError("refunds for order %s exceed paid amount" % oid)
        refund_cents_by_order[oid] = total

    order_entries = []
    customer_totals = {}
    total_paid = 0
    total_refund = 0
    for oid in sorted(parsed_orders):
        order = parsed_orders[oid]
        if order["status"] != "paid":
            continue
        if use_cutoff and order["created_at"] > cutoff:
            continue
        refund = refund_cents_by_order.get(oid, 0)
        net = order["paid_cents"] - refund
        order_entries.append({
            "order_id": order["order_id"],
            "customer": order["customer"],
            "paid_cents": order["paid_cents"],
            "refund_cents": refund,
            "net_cents": net,
        })
        customer_totals[order["customer"]] = (
            customer_totals.get(order["customer"], 0) + net
        )
        total_paid += order["paid_cents"]
        total_refund += refund

    customers = [
        {"customer": name, "net_cents": customer_totals[name]}
        for name in sorted(customer_totals)
    ]

    return {
        "orders": order_entries,
        "customers": customers,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def _csv_text(header, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """Render reconcile output into the release bundle (release-spec.md).

    Returns exactly three files: orders.csv, customers.csv, summary.json.
    Row order follows reconcile ordering; amounts are integer text.
    """
    order_rows = [
        [
            entry["order_id"],
            entry["customer"],
            str(entry["paid_cents"]),
            str(entry["refund_cents"]),
            str(entry["net_cents"]),
        ]
        for entry in result["orders"]
    ]
    customer_rows = [
        [entry["customer"], str(entry["net_cents"])]
        for entry in result["customers"]
    ]

    orders_csv = _csv_text(
        ("order_id", "customer", "paid_cents", "refund_cents", "net_cents"),
        order_rows,
    )
    customers_csv = _csv_text(("customer", "net_cents"), customer_rows)
    summary_json = json.dumps(result["totals"])

    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
