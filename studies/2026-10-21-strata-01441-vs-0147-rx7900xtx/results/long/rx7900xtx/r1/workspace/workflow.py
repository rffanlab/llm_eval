"""Order reconciliation, spec-v1 and spec-v2 contracts.

Pure functions only: no file, network or process access.
Amounts are parsed with decimal.Decimal (fixed-point), never float*100.
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_FIELDS = ["order_id", "customer", "amount", "status", "created_at"]
_REFUND_FIELDS_V1 = ["refund_id", "order_id", "amount"]
_REFUND_FIELDS_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]

_CUTOFF_LEN = len("YYYY-MM-DDTHH:MM:SSZ")


def _is_amount_text(text, max_decimals):
    """Digits with optional dot and at most max_decimals decimals.

    No signs, no exponents, no letters (rejects NaN/Infinity).
    """
    if not text:
        return False
    int_part = text
    frac_part = ""
    if "." in text:
        parts = text.split(".")
        if len(parts) != 2:
            return False
        int_part, frac_part = parts
        if len(frac_part) > max_decimals:
            return False
    if not int_part or not int_part.isdigit():
        return False
    if frac_part and not frac_part.isdigit():
        return False
    return True


def _parse_amount_cents(raw, max_decimals=2):
    """Return integer cents for a non-negative amount.

    v1: at most 2 decimals (exact). v2: any decimals, ROUND_HALF_UP.
    Rejects NaN, Infinity, negatives, exponent forms.
    """
    if raw is None:
        raise ValueError("missing amount")
    text = raw.strip()
    if not _is_amount_text(text, max_decimals):
        raise ValueError("invalid amount: %r" % (raw,))
    try:
        dec = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % (raw,))
    cents = (dec * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _is_valid_cutoff(text):
    """Strictly validate YYYY-MM-DDTHH:MM:SSZ (canonical UTC)."""
    if not isinstance(text, str) or len(text) != _CUTOFF_LEN:
        return False
    if text[4] != "-" or text[7] != "-" or text[10] != "T":
        return False
    if text[13] != ":" or text[16] != ":" or text[19] != "Z":
        return False
    for pos in (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18):
        if not text[pos].isdigit():
            return False
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    hour = int(text[11:13])
    minute = int(text[14:16])
    second = int(text[17:19])
    if year < 1 or month < 1 or month > 12 or day < 1 or day > 31:
        return False
    if hour > 23 or minute > 59 or second > 59:
        return False
    return True


def _read_rows(csv_text, required_fields, kind):
    if csv_text is None:
        raise ValueError("%s csv is None" % kind)
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("%s csv is empty (header required)" % kind)
    header = [h.strip() for h in header]
    if header != required_fields:
        raise ValueError(
            "%s csv header mismatch: expected %s, got %s"
            % (kind, required_fields, header)
        )
    rows = []
    for row in reader:
        if not row or (len(row) == 1 and row[0].strip() == ""):
            continue  # ignore blank lines
        if len(row) != len(required_fields):
            raise ValueError("%s row has wrong arity: %r" % (kind, row))
        rows.append(dict(zip(required_fields, [c.strip() for c in row])))
    return rows


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile orders and refunds per the v1/v2 contract.

    Returns {"orders": [...], "customers": [...], "totals": {...}}
    with all money as integer cents.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v2":
        if cutoff is None:
            raise ValueError("cutoff is required for policy v2")
        if not _is_valid_cutoff(cutoff):
            raise ValueError("invalid cutoff: %r" % (cutoff,))
    else:
        # v1 ignores cutoff; accepted for forward compatibility.
        pass

    max_decimals = 2 if policy == "v1" else 999999
    refund_fields = _REFUND_FIELDS_V1 if policy == "v1" else _REFUND_FIELDS_V2

    order_rows = _read_rows(orders_csv, _ORDER_FIELDS, "orders")
    refund_rows = _read_rows(refunds_csv, refund_fields, "refunds")

    # ---- orders: dedupe by order_id (all rows, before any filtering) ----
    seen_orders = {}  # order_id -> full row tuple
    orders = {}       # order_id -> record for included paid orders
    known_paid_ids = set()
    cancelled_ids = set()
    for row in order_rows:
        oid = row["order_id"]
        key = tuple(row[f] for f in _ORDER_FIELDS)
        if oid in seen_orders:
            if seen_orders[oid] == key:
                continue  # exact duplicate row, count once
            raise ValueError("conflicting rows for order_id %r" % (oid,))
        seen_orders[oid] = key
        status = row["status"]
        if status == "cancelled":
            cancelled_ids.add(oid)
            continue
        if status != "paid":
            raise ValueError("unknown order status: %r" % (status,))
        known_paid_ids.add(oid)
        if policy == "v2" and row["created_at"] > cutoff:
            continue  # order after cutoff: excluded
        paid_cents = _parse_amount_cents(row["amount"], max_decimals)
        orders[oid] = {
            "order_id": oid,
            "customer": row["customer"],
            "paid_cents": paid_cents,
            "refund_cents": 0,
        }

    # ---- refunds: dedupe by refund_id (all rows, incl. pending/late) ----
    seen_refunds = {}  # refund_id -> full row tuple
    for row in refund_rows:
        rid = row["refund_id"]
        key = tuple(row[f] for f in refund_fields)
        if rid in seen_refunds:
            if seen_refunds[rid] == key:
                continue  # exact duplicate row, count once
            raise ValueError("conflicting rows for refund_id %r" % (rid,))
        seen_refunds[rid] = key

        if policy == "v2":
            status = row["status"]
            if status not in ("succeeded", "pending"):
                raise ValueError("unknown refund status: %r" % (status,))
            if status == "pending" or row["created_at"] > cutoff:
                continue  # not effective: ignored entirely

        oid = row["order_id"]
        if oid not in orders:
            if oid in cancelled_ids:
                raise ValueError(
                    "refund %r targets cancelled order %r" % (rid, oid)
                )
            if oid in known_paid_ids:
                # paid order excluded by cutoff: ignore the refund
                continue
            raise ValueError("refund %r targets unknown order %r" % (rid, oid))
        refund_cents = _parse_amount_cents(row["amount"], max_decimals)
        orders[oid]["refund_cents"] += refund_cents

    # ---- validate and build results ----
    result_orders = []
    totals_paid = 0
    totals_refund = 0
    customer_net = {}
    for oid in sorted(orders):
        rec = orders[oid]
        if rec["refund_cents"] > rec["paid_cents"]:
            raise ValueError(
                "refunds exceed paid amount for order %r" % (oid,)
            )
        net = rec["paid_cents"] - rec["refund_cents"]
        result_orders.append({
            "order_id": rec["order_id"],
            "customer": rec["customer"],
            "paid_cents": rec["paid_cents"],
            "refund_cents": rec["refund_cents"],
            "net_cents": net,
        })
        totals_paid += rec["paid_cents"]
        totals_refund += rec["refund_cents"]
        customer_net[rec["customer"]] = customer_net.get(rec["customer"], 0) + net

    result_customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]

    return {
        "orders": result_orders,
        "customers": result_customers,
        "totals": {
            "paid_cents": totals_paid,
            "refund_cents": totals_refund,
            "net_cents": totals_paid - totals_refund,
        },
    }


def _csv_text(header, rows):
    """Render CSV rows with the standard csv writer."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Serialize a reconcile() result into the release bundle.

    Returns exactly three files per the release contract:
    orders.csv, customers.csv, summary.json.
    """
    order_rows = [
        [
            rec["order_id"],
            rec["customer"],
            str(rec["paid_cents"]),
            str(rec["refund_cents"]),
            str(rec["net_cents"]),
        ]
        for rec in result["orders"]
    ]
    customer_rows = [
        [rec["customer"], str(rec["net_cents"])]
        for rec in result["customers"]
    ]
    return {
        "orders.csv": _csv_text(
            ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
            order_rows,
        ),
        "customers.csv": _csv_text(["customer", "net_cents"], customer_rows),
        "summary.json": json.dumps(result["totals"], sort_keys=True),
    }
