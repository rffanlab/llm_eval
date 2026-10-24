import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _valid_cutoff(text):
    """Validate YYYY-MM-DDTHH:MM:SSZ format without regex."""
    if not isinstance(text, str) or len(text) != 20:
        return False
    if text[4] != "-" or text[7] != "-" or text[10] != "T" or text[13] != ":" \
            or text[16] != ":" or text[19] != "Z":
        return False
    digits = text[0:4] + text[5:7] + text[8:10] + text[11:13] + text[14:16] + text[17:19]
    return digits.isdigit()


def _parse_amount(raw):
    """Validate an amount string and return a Decimal.

    Rejects empty, NaN/Infinity, negatives, signs, exponents and junk.
    """
    if raw is None:
        raise ValueError("missing amount")
    text = raw.strip()
    if not text:
        raise ValueError("missing amount")
    int_part, dot, frac_part = text.partition(".")
    if not int_part.isdigit():
        raise ValueError("invalid amount: %r" % (raw,))
    if dot and not frac_part.isdigit():
        raise ValueError("invalid amount: %r" % (raw,))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % (raw,))
    if not value.is_finite() or value < 0:
        raise ValueError("invalid amount: %r" % (raw,))
    return value


def _to_cents_v1(raw):
    """v1: at most two decimals, exact conversion to integer cents."""
    value = _parse_amount(raw)
    text = raw.strip()
    dot = text.find(".")
    if dot != -1 and len(text) - dot - 1 > 2:
        raise ValueError("amount has more than two decimals: %r" % (raw,))
    cents = value * Decimal(100)
    if cents != cents.to_integral_value():
        raise ValueError("amount has more than two decimals: %r" % (raw,))
    return int(cents.to_integral_value())


def _to_cents_v2(raw):
    """v2: any number of decimals, ROUND_HALF_UP to integer cents."""
    value = _parse_amount(raw)
    cents = (value * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _read_rows(csv_text, required_header):
    """Read a CSV string into (header, list_of_row_tuples). Empty input -> ([], [])."""
    if csv_text is None:
        return [], []
    reader = csv.reader(io.StringIO(csv_text))
    rows = [tuple(row) for row in reader if row and any(cell != "" for cell in row)]
    if not rows:
        return [], []
    header = rows[0]
    if tuple(header) != tuple(required_header):
        raise ValueError("bad header: expected %r" % (required_header,))
    return header, rows[1:]


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v2":
        if not cutoff or not _valid_cutoff(cutoff):
            raise ValueError("v2 requires cutoff in YYYY-MM-DDTHH:MM:SSZ format")
    to_cents = _to_cents_v1 if policy == "v1" else _to_cents_v2

    _, order_rows = _read_rows(orders_csv, ["order_id", "customer", "amount", "status", "created_at"])
    if policy == "v1":
        _, refund_rows = _read_rows(refunds_csv, ["refund_id", "order_id", "amount"])
    else:
        _, refund_rows = _read_rows(refunds_csv, ["refund_id", "order_id", "amount", "status", "created_at"])

    # ---- orders: dedupe by order_id (conflicts rejected regardless of filters) ----
    orders = {}  # order_id -> (order_id, customer, cents, status, created_at)
    for row in order_rows:
        if len(row) != 5:
            raise ValueError("bad order row: %r" % (row,))
        order_id, customer, amount, status, created_at = row
        if not order_id or not customer:
            raise ValueError("missing order_id/customer: %r" % (row,))
        if status not in ("paid", "cancelled"):
            raise ValueError("unknown status: %r" % (status,))
        cents = to_cents(amount)
        key = (order_id, customer, cents, status, created_at)
        if order_id in orders:
            if orders[order_id] != key:
                raise ValueError("conflicting duplicate order: %s" % order_id)
            continue
        orders[order_id] = key

    # ---- refunds: dedupe by refund_id (conflicts rejected regardless of filters) ----
    refunds = {}  # refund_id -> (refund_id, order_id, cents, status, created_at)
    for row in refund_rows:
        if policy == "v1":
            if len(row) != 3:
                raise ValueError("bad refund row: %r" % (row,))
            refund_id, order_id, amount = row
            status, created_at = "succeeded", None
        else:
            if len(row) != 5:
                raise ValueError("bad refund row: %r" % (row,))
            refund_id, order_id, amount, status, created_at = row
            if status not in ("succeeded", "pending"):
                raise ValueError("unknown refund status: %r" % (status,))
        if not refund_id or not order_id:
            raise ValueError("missing refund_id/order_id: %r" % (row,))
        cents = to_cents(amount)
        key = (refund_id, order_id, cents, status, created_at)
        if refund_id in refunds:
            if refunds[refund_id] != key:
                raise ValueError("conflicting duplicate refund: %s" % refund_id)
            continue
        refunds[refund_id] = key

    # ---- select counted refunds and validate against orders ----
    def counted(status, created_at):
        if policy == "v1":
            return True
        return status == "succeeded" and created_at <= cutoff

    refund_by_order = {}
    for refund_id, order_id, cents, status, created_at in refunds.values():
        if not counted(status, created_at):
            continue
        order = orders.get(order_id)
        if order is None:
            raise ValueError("refund %s references unknown order %s" % (refund_id, order_id))
        if order[3] != "paid":
            raise ValueError("refund %s references cancelled order %s" % (refund_id, order_id))
        if policy == "v2" and order[4] > cutoff:
            # Order exists but is excluded by cutoff: ignore the refund.
            continue
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + cents
    for order_id, total_refund in refund_by_order.items():
        if total_refund > orders[order_id][2]:
            raise ValueError("refund exceeds paid amount for order %s" % order_id)

    # ---- build result ----
    result_orders = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(orders):
        _, customer, paid_cents, status, created_at = orders[order_id]
        if status != "paid":
            continue
        if policy == "v2" and created_at > cutoff:
            continue
        refund_cents = refund_by_order.get(order_id, 0)
        net_cents = paid_cents - refund_cents
        result_orders.append({
            "order_id": order_id,
            "customer": customer,
            "paid_cents": paid_cents,
            "refund_cents": refund_cents,
            "net_cents": net_cents,
        })
        customer_net[customer] = customer_net.get(customer, 0) + net_cents
        totals["paid_cents"] += paid_cents
        totals["refund_cents"] += refund_cents
        totals["net_cents"] += net_cents

    result_customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]
    return {"orders": result_orders, "customers": result_customers, "totals": totals}


def _csv_text(header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Render reconcile output into the three release files."""
    orders_rows = [
        (o["order_id"], o["customer"], int(o["paid_cents"]),
         int(o["refund_cents"]), int(o["net_cents"]))
        for o in result["orders"]
    ]
    customers_rows = [
        (c["customer"], int(c["net_cents"]))
        for c in result["customers"]
    ]
    totals = result["totals"]
    summary = {
        "paid_cents": int(totals["paid_cents"]),
        "refund_cents": int(totals["refund_cents"]),
        "net_cents": int(totals["net_cents"]),
    }
    return {
        "orders.csv": _csv_text(
            ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
            orders_rows),
        "customers.csv": _csv_text(["customer", "net_cents"], customers_rows),
        "summary.json": json.dumps(summary),
    }
