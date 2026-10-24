import csv
import io
import json
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _parse_amount_cents(text, policy):
    """Parse an amount string into integer cents using decimal fixed point.

    v1: at most two decimals, no rounding needed.
    v2: any number of decimals, rounded HALF_UP to integer cents.
    Both: reject NaN/Infinity/negatives.
    """
    s = (text or "").strip()
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % (text,))
    if not d.is_finite():
        raise ValueError("non-finite amount: %r" % (text,))
    if d < 0:
        raise ValueError("negative amount: %r" % (text,))
    exp = d.as_tuple().exponent
    if policy == "v1":
        if isinstance(exp, int) and exp < -2:
            raise ValueError("amount has more than two decimals: %r" % (text,))
        return int(d * 100)
    return int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _read_rows(csv_text, required_cols):
    """Parse CSV text into a list of dicts keyed by header names."""
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    for col in required_cols:
        if col not in header:
            raise ValueError("missing column: %s" % col)
    out = []
    for row in rows[1:]:
        if len(row) != len(header):
            raise ValueError("row length does not match header")
        out.append(dict((col, row[i].strip()) for i, col in enumerate(header)))
    return out


def _dedupe(rows, id_field):
    """Exact-duplicate rows with the same id collapse; conflicting rows raise."""
    seen = {}
    unique = []
    for row in rows:
        rid = row[id_field]
        key = tuple(sorted(row.items()))
        if rid in seen:
            if seen[rid] != key:
                raise ValueError("conflicting duplicate id: %s" % rid)
            continue
        seen[rid] = key
        unique.append(row)
    return unique


def _validate_cutoff(cutoff):
    if not isinstance(cutoff, str):
        raise ValueError("invalid cutoff, expected YYYY-MM-DDTHH:MM:SSZ")
    s = cutoff.strip()
    if len(s) != 20 or s[4] != "-" or s[7] != "-" or s[10] != "T" \
            or s[13] != ":" or s[16] != ":" or s[19] != "Z":
        raise ValueError("invalid cutoff, expected YYYY-MM-DDTHH:MM:SSZ")
    digits = s[0:4] + s[5:7] + s[8:10] + s[11:13] + s[14:16] + s[17:19]
    if not all(c in "0123456789" for c in digits):
        raise ValueError("invalid cutoff, expected YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("invalid cutoff date/time: %r" % (cutoff,))
    return s


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %s" % policy)
    if policy == "v2":
        if cutoff is None:
            raise ValueError("cutoff is required for policy v2")
        cutoff = _validate_cutoff(cutoff)

    order_rows = _read_rows(
        orders_csv, ["order_id", "customer", "amount", "status", "created_at"]
    )
    if policy == "v1":
        refund_cols = ["refund_id", "order_id", "amount"]
    else:
        refund_cols = ["refund_id", "order_id", "amount", "status", "created_at"]
    refund_rows = _read_rows(refunds_csv, refund_cols)
    # Dedupe first: conflicts must be rejected regardless of status/cutoff.
    order_rows = _dedupe(order_rows, "order_id")
    refund_rows = _dedupe(refund_rows, "refund_id")

    orders = {}
    for row in order_rows:
        status = row["status"].lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("unknown order status: %r" % (row["status"],))
        cents = _parse_amount_cents(row["amount"], policy)
        orders[row["order_id"]] = {
            "customer": row["customer"],
            "paid_cents": cents,
            "status": status,
            "created_at": row["created_at"],
        }

    refunds_by_order = {}
    for row in refund_rows:
        if policy == "v2":
            status = row["status"].lower()
            if status not in ("succeeded", "pending"):
                raise ValueError("unknown refund status: %r" % (row["status"],))
            if status != "succeeded" or row["created_at"] > cutoff:
                # pending or after-cutoff refunds are not counted at all
                continue
        oid = row["order_id"]
        if oid not in orders:
            raise ValueError("refund for unknown order: %s" % oid)
        if orders[oid]["status"] != "paid":
            raise ValueError("refund for cancelled order: %s" % oid)
        if policy == "v2" and orders[oid]["created_at"] > cutoff:
            # order exists but was excluded by cutoff: ignore the refund
            continue
        refunds_by_order[oid] = (
            refunds_by_order.get(oid, 0) + _parse_amount_cents(row["amount"], policy)
        )

    for oid, refund_total in refunds_by_order.items():
        if refund_total > orders[oid]["paid_cents"]:
            raise ValueError("refund exceeds paid amount for order: %s" % oid)

    result_orders = []
    customers = {}
    total_paid = 0
    total_refund = 0
    for oid in sorted(orders):
        order = orders[oid]
        if order["status"] != "paid":
            continue
        if policy == "v2" and order["created_at"] > cutoff:
            continue
        refund = refunds_by_order.get(oid, 0)
        net = order["paid_cents"] - refund
        result_orders.append({
            "order_id": oid,
            "customer": order["customer"],
            "paid_cents": order["paid_cents"],
            "refund_cents": refund,
            "net_cents": net,
        })
        customers[order["customer"]] = customers.get(order["customer"], 0) + net
        total_paid += order["paid_cents"]
        total_refund += refund

    result_customers = [
        {"customer": name, "net_cents": customers[name]}
        for name in sorted(customers)
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
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    order_rows = [
        [o["order_id"], o["customer"],
         "%d" % o["paid_cents"], "%d" % o["refund_cents"], "%d" % o["net_cents"]]
        for o in result["orders"]
    ]
    customer_rows = [
        [c["customer"], "%d" % c["net_cents"]]
        for c in result["customers"]
    ]
    return {
        "orders.csv": _rows_to_csv(
            ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
            order_rows,
        ),
        "customers.csv": _rows_to_csv(["customer", "net_cents"], customer_rows),
        "summary.json": json.dumps(result["totals"], sort_keys=True),
    }
