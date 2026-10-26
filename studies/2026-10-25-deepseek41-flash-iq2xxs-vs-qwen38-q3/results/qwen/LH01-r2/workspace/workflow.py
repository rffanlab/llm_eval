import csv
import io
import json
import hashlib
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _parse_amount(raw, context, policy):
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = raw.strip()
    if text == "":
        raise ValueError("%s: empty amount" % context)
    lowered = text.lower()
    if lowered in ("nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"):
        raise ValueError("%s: NaN/Infinity not allowed: %r" % (context, raw))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid decimal amount %r" % (context, raw))
    if not value.is_finite():
        raise ValueError("%s: non-finite amount %r" % (context, raw))
    if value < 0:
        raise ValueError("%s: negative amount %r" % (context, raw))
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise ValueError("%s: non-finite amount %r" % (context, raw))
    if policy == "v1" and exponent < -2:
        raise ValueError("%s: more than two decimal places: %r" % (context, raw))
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _read_rows(csv_text, required, label):
    if csv_text is None:
        raise ValueError("%s csv is None" % label)
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("%s csv must contain a header row" % label)
    columns = [name.strip() for name in header]
    for name in required:
        if name not in columns:
            raise ValueError("%s csv missing column: %s" % (label, name))
    rows = []
    for line in reader:
        if len(line) == 1 and (line[0] is None or line[0].strip() == ""):
            continue
        if len(line) != len(columns):
            raise ValueError("%s csv row has wrong field count: %r" % (label, line))
        rows.append({name: (value.strip() if value is not None else "") for name, value in zip(columns, line)})
    return rows


def _digest(row):
    payload = "\x1f".join("%s=%s" % (key, row[key]) for key in sorted(row))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_timestamp(text, context):
    if not isinstance(text, str) or len(text) != 20:
        raise ValueError("%s: invalid timestamp %r" % (context, text))
    if text[4] != "-" or text[7] != "-" or text[10] != "T" or text[19] != "Z":
        raise ValueError("%s: invalid timestamp %r" % (context, text))
    if text[13] != ":" or text[16] != ":":
        raise ValueError("%s: invalid timestamp %r" % (context, text))
    digits = text[0:4] + text[5:7] + text[8:10] + text[11:13] + text[14:16] + text[17:19]
    if not digits.isdigit():
        raise ValueError("%s: invalid timestamp %r" % (context, text))
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    hour = int(text[11:13])
    minute = int(text[14:16])
    second = int(text[17:19])
    if month < 1 or month > 12:
        raise ValueError("%s: invalid month in %r" % (context, text))
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    days_in_month = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    if day < 1 or day > days_in_month:
        raise ValueError("%s: invalid day in %r" % (context, text))
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError("%s: invalid time in %r" % (context, text))


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v2":
        if cutoff is None:
            raise ValueError("v2 policy requires cutoff")
        if not isinstance(cutoff, str) or not cutoff.strip():
            raise ValueError("v2 cutoff must be a non-empty string")
        cutoff = cutoff.strip()
        _validate_timestamp(cutoff, "cutoff")
    else:
        if cutoff is not None and (not isinstance(cutoff, str) or not cutoff.strip()):
            raise ValueError("cutoff must be a non-empty string or None")
        cutoff = None

    if policy == "v2":
        order_required = ["order_id", "customer", "amount", "status", "created_at"]
        refund_required = ["refund_id", "order_id", "amount", "status", "created_at"]
    else:
        order_required = ["order_id", "customer", "amount", "status"]
        refund_required = ["refund_id", "order_id", "amount"]

    order_rows = _read_rows(orders_csv, order_required, "orders")
    refund_rows = _read_rows(refunds_csv, refund_required, "refunds")

    orders = {}
    order_digests = {}
    for row in order_rows:
        order_id = row["order_id"]
        if order_id == "":
            raise ValueError("orders: empty order_id")
        digest = _digest(row)
        if order_id in order_digests:
            if order_digests[order_id] != digest:
                raise ValueError("orders: conflicting rows for order_id %s" % order_id)
            continue
        order_digests[order_id] = digest
        created_at = row.get("created_at", "")
        if policy == "v2":
            _validate_timestamp(created_at, "orders %s created_at" % order_id)
        paid_cents = _parse_amount(row["amount"], "orders %s" % order_id, policy)
        orders[order_id] = {
            "order_id": order_id,
            "customer": row["customer"],
            "status": row["status"].lower(),
            "paid_cents": paid_cents,
            "refund_cents": 0,
            "created_at": created_at,
        }

    refund_digests = {}
    for row in refund_rows:
        refund_id = row["refund_id"]
        if refund_id == "":
            raise ValueError("refunds: empty refund_id")
        digest = _digest(row)
        if refund_id in refund_digests:
            if refund_digests[refund_id] != digest:
                raise ValueError("refunds: conflicting rows for refund_id %s" % refund_id)
            continue
        refund_digests[refund_id] = digest

        status = row.get("status", "succeeded").lower()
        created_at = row.get("created_at", "")
        if policy == "v2":
            if status not in ("succeeded", "pending"):
                raise ValueError("refunds %s: invalid status %r" % (refund_id, row.get("status")))
            _validate_timestamp(created_at, "refunds %s created_at" % refund_id)

        order_id = row["order_id"]
        order = orders.get(order_id)

        if policy == "v2":
            # pending or after-cutoff refunds are not effective: ignore entirely.
            if status == "pending" or created_at > cutoff:
                continue
            # effective refund from here on
            if order is None:
                raise ValueError("refunds: unknown order_id %s for refund %s" % (order_id, refund_id))
            if order["status"] != "paid":
                raise ValueError("refunds: refund %s targets non-paid order %s" % (refund_id, order_id))
            if order["created_at"] > cutoff:
                # order exists but excluded by cutoff: ignore this refund
                continue
        else:
            if order is None:
                raise ValueError("refunds: unknown order_id %s for refund %s" % (order_id, refund_id))
            if order["status"] != "paid":
                raise ValueError("refunds: refund %s targets non-paid order %s" % (refund_id, order_id))

        refund_cents = _parse_amount(row["amount"], "refunds %s" % refund_id, policy)
        order["refund_cents"] += refund_cents
        if order["refund_cents"] > order["paid_cents"]:
            raise ValueError(
                "refunds: cumulative refund %d exceeds paid %d for order %s"
                % (order["refund_cents"], order["paid_cents"], order_id)
            )

    result_orders = []
    customer_totals = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(orders):
        order = orders[order_id]
        if order["status"] != "paid":
            continue
        if policy == "v2" and order["created_at"] > cutoff:
            continue
        net_cents = order["paid_cents"] - order["refund_cents"]
        result_orders.append(
            {
                "order_id": order["order_id"],
                "customer": order["customer"],
                "paid_cents": order["paid_cents"],
                "refund_cents": order["refund_cents"],
                "net_cents": net_cents,
            }
        )
        total_paid += order["paid_cents"]
        total_refund += order["refund_cents"]
        customer_totals[order["customer"]] = customer_totals.get(order["customer"], 0) + net_cents

    customers = [
        {"customer": name, "net_cents": customer_totals[name]}
        for name in sorted(customer_totals)
    ]
    return {
        "orders": result_orders,
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
    order_rows = [
        [
            order["order_id"],
            order["customer"],
            str(order["paid_cents"]),
            str(order["refund_cents"]),
            str(order["net_cents"]),
        ]
        for order in result["orders"]
    ]
    customer_rows = [
        [customer["customer"], str(customer["net_cents"])]
        for customer in result["customers"]
    ]
    return {
        "orders.csv": _csv_text(
            ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
            order_rows,
        ),
        "customers.csv": _csv_text(["customer", "net_cents"], customer_rows),
        "summary.json": json.dumps(result["totals"], sort_keys=True),
    }
