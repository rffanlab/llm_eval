import csv
import io
import json
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _parse_amount_cents(raw, allow_many_decimals=False):
    """Parse an amount string into integer cents using Decimal fixed point.

    Rejects: non-numeric, NaN, Infinity, negative.
    v1 (allow_many_decimals=False): also rejects more than two decimals.
    v2: rounds to cents with ROUND_HALF_UP.
    """
    if raw is None:
        raise ValueError("missing amount")
    text = raw.strip()
    if not text:
        raise ValueError("empty amount")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % raw)
    if not value.is_finite():
        raise ValueError("non-finite amount: %r" % raw)
    if value < 0:
        raise ValueError("negative amount: %r" % raw)
    sign, digits, exponent = value.as_tuple()
    if not allow_many_decimals and exponent < -2:
        raise ValueError("more than two decimals: %r" % raw)
    scaled = value.scaleb(2).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(scaled)


def _validate_cutoff(cutoff):
    if not isinstance(cutoff, str):
        raise ValueError("cutoff must be a string")
    try:
        datetime.datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("invalid cutoff format: %r" % cutoff)
    return cutoff


def _read_rows(csv_text, required_columns):
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        raise ValueError("missing CSV header")
    for column in required_columns:
        if column not in reader.fieldnames:
            raise ValueError("missing column: %s" % column)
    return reader


def _row_key(row, columns):
    return tuple((row.get(col) or "") for col in columns)


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy == "v1":
        allow_many_decimals = False
        refund_columns = ["refund_id", "order_id", "amount"]
        cutoff_value = None
    elif policy == "v2":
        if cutoff is None:
            raise ValueError("cutoff required for policy v2")
        cutoff_value = _validate_cutoff(cutoff)
        allow_many_decimals = True
        refund_columns = ["refund_id", "order_id", "amount", "status", "created_at"]
    else:
        raise ValueError("unsupported policy: %r" % policy)

    order_columns = ["order_id", "customer", "amount", "status", "created_at"]

    # --- orders: dedupe by order_id over ALL rows (conflicts always rejected) ---
    orders = {}      # order_id -> row key
    order_rows = []  # deduped rows in first-seen order
    for row in _read_rows(orders_csv, order_columns):
        order_id = row.get("order_id") or ""
        if not order_id:
            raise ValueError("empty order_id")
        key = _row_key(row, order_columns)
        if order_id in orders:
            if orders[order_id] != key:
                raise ValueError("conflicting rows for order_id: %s" % order_id)
            continue
        orders[order_id] = key
        order_rows.append(row)

    # --- refunds: dedupe by refund_id over ALL rows (conflicts always rejected) ---
    refunds = {}
    refund_rows = []
    for row in _read_rows(refunds_csv, refund_columns):
        refund_id = row.get("refund_id") or ""
        if not refund_id:
            raise ValueError("empty refund_id")
        key = _row_key(row, refund_columns)
        if refund_id in refunds:
            if refunds[refund_id] != key:
                raise ValueError("conflicting rows for refund_id: %s" % refund_id)
            continue
        refunds[refund_id] = key
        refund_rows.append(row)

    def _is_paid_included(order_id):
        key = orders.get(order_id)
        if key is None:
            return False
        if (key[3] or "").strip() != "paid":
            return False
        if cutoff_value is not None and (key[4] or "") > cutoff_value:
            return False
        return True

    # --- validate & accumulate refunds per order ---
    refund_cents_by_order = {}
    for row in refund_rows:
        order_id = (row.get("order_id") or "").strip()
        if cutoff_value is not None:
            # v2: only succeeded refunds within cutoff are "valid"
            if (row.get("status") or "").strip() != "succeeded":
                continue
            if (row.get("created_at") or "") > cutoff_value:
                continue
        if order_id not in orders:
            raise ValueError("refund for unknown order: %s" % order_id)
        if (orders[order_id][3] or "").strip() != "paid":
            raise ValueError("refund for non-paid order: %s" % order_id)
        if not _is_paid_included(order_id):
            # order exists but excluded by cutoff -> ignore this refund
            continue
        cents = _parse_amount_cents(row.get("amount"), allow_many_decimals)
        refund_cents_by_order[order_id] = refund_cents_by_order.get(order_id, 0) + cents

    # --- build result over included paid orders ---
    result_orders = []
    customers_total = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for row in order_rows:
        order_id = (row.get("order_id") or "").strip()
        if not _is_paid_included(order_id):
            continue
        customer = (row.get("customer") or "").strip()
        paid = _parse_amount_cents(row.get("amount"), allow_many_decimals)
        refunded = refund_cents_by_order.get(order_id, 0)
        if refunded > paid:
            raise ValueError(
                "refunds exceed paid amount for order: %s" % order_id
            )
        net = paid - refunded
        result_orders.append({
            "order_id": order_id,
            "customer": customer,
            "paid_cents": paid,
            "refund_cents": refunded,
            "net_cents": net,
        })
        customers_total[customer] = customers_total.get(customer, 0) + net
        totals["paid_cents"] += paid
        totals["refund_cents"] += refunded
        totals["net_cents"] += net

    result_orders.sort(key=lambda item: item["order_id"])
    customers = [
        {"customer": name, "net_cents": net}
        for name, net in sorted(customers_total.items())
    ]

    return {"orders": result_orders, "customers": customers, "totals": totals}


def export_bundle(result):
    """Render the release bundle: exactly orders.csv, customers.csv, summary.json."""
    orders_buffer = io.StringIO()
    writer = csv.writer(orders_buffer, lineterminator="\n")
    writer.writerow(["order_id", "customer", "paid_cents", "refund_cents", "net_cents"])
    for item in result["orders"]:
        writer.writerow([
            item["order_id"],
            item["customer"],
            "%d" % item["paid_cents"],
            "%d" % item["refund_cents"],
            "%d" % item["net_cents"],
        ])

    customers_buffer = io.StringIO()
    writer = csv.writer(customers_buffer, lineterminator="\n")
    writer.writerow(["customer", "net_cents"])
    for item in result["customers"]:
        writer.writerow([item["customer"], "%d" % item["net_cents"]])

    summary = json.dumps(result["totals"], sort_keys=True)

    return {
        "orders.csv": orders_buffer.getvalue(),
        "customers.csv": customers_buffer.getvalue(),
        "summary.json": summary,
    }
