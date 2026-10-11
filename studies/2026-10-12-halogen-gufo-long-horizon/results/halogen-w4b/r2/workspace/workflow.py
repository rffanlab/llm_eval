"""Order reconciliation, v1 + v2 contracts.

reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None) -> dict

Inputs are UTF-8 CSV strings. Money is parsed with Decimal (fixed point),
never float*100. Outputs are integer cents.

v1: refunds have (refund_id, order_id, amount); amounts max two decimals;
    no cutoff.
v2: refunds have (refund_id, order_id, amount, status, created_at);
    cutoff (YYYY-MM-DDTHH:MM:SSZ) required; only paid orders with
    created_at <= cutoff count; only succeeded refunds with
    created_at <= cutoff count; amounts of any decimal length are
    ROUND_HALF_UP to integer cents per row before summing.

export_bundle(result) -> dict[str, str] with exactly three files:
orders.csv, customers.csv, summary.json (see release-spec.md).
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


_ORDER_FIELDS = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_FIELDS_V1 = ("refund_id", "order_id", "amount")
_REFUND_FIELDS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")


def _parse_amount_cents_v1(raw, context):
    """v1: non-negative, at most two decimals -> integer cents."""
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = str(raw).strip()
    if text == "":
        raise ValueError("%s: empty amount" % context)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if value.is_nan() or value.is_infinite():
        raise ValueError("%s: non-finite amount %r" % (context, raw))
    if value < 0:
        raise ValueError("%s: negative amount %r" % (context, raw))
    _, _, exponent = value.as_tuple()
    if exponent < -2:
        raise ValueError("%s: more than two decimals %r" % (context, raw))
    # exponent >= -2 guarantees value * 100 is an exact integer.
    return int(value.scaleb(2))


def _parse_amount_cents_v2(raw, context):
    """v2: non-negative, any decimals -> integer cents via ROUND_HALF_UP.

    Round each amount individually to the nearest cent (half up).
    """
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = str(raw).strip()
    if text == "":
        raise ValueError("%s: empty amount" % context)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if value.is_nan() or value.is_infinite():
        raise ValueError("%s: non-finite amount %r" % (context, raw))
    if value < 0:
        raise ValueError("%s: negative amount %r" % (context, raw))
    cents = value.scaleb(2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _validate_cutoff(cutoff):
    """Validate canonical UTC string YYYY-MM-DDTHH:MM:SSZ."""
    if cutoff is None or not isinstance(cutoff, str):
        raise ValueError("v2 requires a cutoff (YYYY-MM-DDTHH:MM:SSZ)")
    text = cutoff.strip()
    if len(text) != 20:
        raise ValueError("invalid cutoff format: %r" % (cutoff,))
    if text[4] != "-" or text[7] != "-" or text[10] != "T" or text[19] != "Z":
        raise ValueError("invalid cutoff format: %r" % (cutoff,))
    digit_positions = [0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18]
    for i in digit_positions:
        if not text[i].isdigit():
            raise ValueError("invalid cutoff format: %r" % (cutoff,))
    year, month, day = int(text[0:4]), int(text[5:7]), int(text[8:10])
    hour, minute, second = int(text[11:13]), int(text[14:16]), int(text[17:19])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError("invalid cutoff date: %r" % (cutoff,))
    if not (hour <= 23 and minute <= 59 and second <= 59):
        raise ValueError("invalid cutoff time: %r" % (cutoff,))
    _ = year
    return text


def _read_rows(csv_string, expected_fields, label):
    reader = csv.reader(io.StringIO(csv_string))
    rows = [row for row in reader if row and any(cell.strip() != "" for cell in row)]
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    if header != list(expected_fields):
        raise ValueError("%s: unexpected header %r" % (label, header))
    out = []
    for row in rows[1:]:
        if len(row) != len(expected_fields):
            raise ValueError("%s: bad row width: %r" % (label, row))
        out.append({name: cell.strip() for name, cell in zip(expected_fields, row)})
    return out


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))

    is_v2 = policy == "v2"
    if is_v2:
        cutoff = _validate_cutoff(cutoff)
        amount_parser = _parse_amount_cents_v2
        refund_fields = _REFUND_FIELDS_V2
    else:
        amount_parser = _parse_amount_cents_v1
        refund_fields = _REFUND_FIELDS_V1

    order_rows = _read_rows(orders_csv, _ORDER_FIELDS, "orders")
    refund_rows = _read_rows(refunds_csv, refund_fields, "refunds")

    # Deduplicate orders: identical rows count once; conflicting ids raise.
    orders = {}
    for row in order_rows:
        oid = row["order_id"]
        if oid == "":
            raise ValueError("orders: empty order_id")
        cents = amount_parser(row["amount"], "order %s" % oid)
        record = {
            "order_id": oid,
            "customer": row["customer"],
            "amount_cents": cents,
            "status": row["status"],
            "created_at": row["created_at"],
        }
        if oid in orders:
            if orders[oid] != record:
                raise ValueError("orders: conflicting rows for order_id %s" % oid)
            continue
        orders[oid] = record

    # Deduplicate refunds: identical rows count once; conflicting ids raise
    # (including conflicts among pending / post-cutoff rows).
    refunds = {}
    for row in refund_rows:
        rid = row["refund_id"]
        if rid == "":
            raise ValueError("refunds: empty refund_id")
        cents = amount_parser(row["amount"], "refund %s" % rid)
        record = {"refund_id": rid, "order_id": row["order_id"], "amount_cents": cents}
        if is_v2:
            record["status"] = row["status"]
            record["created_at"] = row["created_at"]
        if rid in refunds:
            if refunds[rid] != record:
                raise ValueError("refunds: conflicting rows for refund_id %s" % rid)
            continue
        refunds[rid] = record

    def _order_included(order):
        if order["status"] != "paid":
            return False
        if is_v2 and order["created_at"] > cutoff:
            return False
        return True

    # Validate and aggregate refunds against orders.
    refund_by_order = {}
    for record in sorted(refunds.values(), key=lambda r: r["refund_id"]):
        if is_v2 and not (record["status"] == "succeeded"
                         and record["created_at"] <= cutoff):
            continue  # pending or post-cutoff refunds are not counted
        oid = record["order_id"]
        order = orders.get(oid)
        if order is None:
            raise ValueError("refund %s: unknown order %s" % (record["refund_id"], oid))
        if order["status"] != "paid":
            raise ValueError(
                "refund %s: order %s is not paid" % (record["refund_id"], oid)
            )
        if is_v2 and order["created_at"] > cutoff:
            # Order exists but is excluded by cutoff: ignore the refund.
            continue
        refund_by_order.setdefault(oid, 0)
        refund_by_order[oid] += record["amount_cents"]
        if refund_by_order[oid] > order["amount_cents"]:
            raise ValueError(
                "order %s: cumulative refunds exceed paid amount" % oid
            )

    order_results = []
    customer_net = {}
    total_paid = 0
    total_refund = 0
    for oid in sorted(orders):
        order = orders[oid]
        if not _order_included(order):
            continue
        paid = order["amount_cents"]
        refund = refund_by_order.get(oid, 0)
        net = paid - refund
        order_results.append({
            "order_id": oid,
            "customer": order["customer"],
            "paid_cents": paid,
            "refund_cents": refund,
            "net_cents": net,
        })
        customer_net[order["customer"]] = customer_net.get(order["customer"], 0) + net
        total_paid += paid
        total_refund += refund

    customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]

    return {
        "orders": order_results,
        "customers": customers,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def _rows_to_csv(header, rows):
    """Render rows with the standard csv writer (\\r\\n line endings)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Build the release bundle: exactly orders.csv, customers.csv, summary.json.

    Row order follows the reconcile output order. Amounts are integer text.
    summary.json parses to exactly result["totals"].
    """
    if not isinstance(result, dict):
        raise ValueError("export_bundle: result must be a dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError("export_bundle: missing %r in result" % key)

    order_rows = []
    for item in result["orders"]:
        order_rows.append([
            str(item["order_id"]),
            str(item["customer"]),
            str(int(item["paid_cents"])),
            str(int(item["refund_cents"])),
            str(int(item["net_cents"])),
        ])
    orders_csv = _rows_to_csv(
        ("order_id", "customer", "paid_cents", "refund_cents", "net_cents"),
        order_rows,
    )

    customer_rows = []
    for item in result["customers"]:
        customer_rows.append([str(item["customer"]), str(int(item["net_cents"]))])
    customers_csv = _rows_to_csv(("customer", "net_cents"), customer_rows)

    totals = result["totals"]
    summary = {
        "paid_cents": int(totals["paid_cents"]),
        "refund_cents": int(totals["refund_cents"]),
        "net_cents": int(totals["net_cents"]),
    }
    summary_json = json.dumps(summary)

    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
