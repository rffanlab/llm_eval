"""Order reconciliation, v1 + v2 contracts.

Pure functions only: parses CSV strings, returns plain dicts of integer cents.
No file/network/process access.
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


_ORDER_HEADER = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_HEADER_V1 = ("refund_id", "order_id", "amount")
_REFUND_HEADER_V2 = ("refund_id", "order_id", "amount", "status", "created_at")


def _validate_cutoff(cutoff):
    """Validate cutoff is a canonical UTC string YYYY-MM-DDTHH:MM:SSZ."""
    if not isinstance(cutoff, str) or len(cutoff) != 20:
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ, got %r"
                         % (cutoff,))
    digits = [str(d).isdigit() for d in cutoff]
    ok = (all(digits[0:4]) and cutoff[4] == "-" and all(digits[5:7])
          and cutoff[7] == "-" and all(digits[8:10]) and cutoff[10] == "T"
          and all(digits[11:13]) and cutoff[13] == ":" and all(digits[14:16])
          and cutoff[16] == ":" and all(digits[17:19]) and cutoff[19] == "Z")
    if not ok:
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ, got %r"
                         % (cutoff,))
    month = int(cutoff[5:7])
    day = int(cutoff[8:10])
    hour = int(cutoff[11:13])
    minute = int(cutoff[14:16])
    second = int(cutoff[17:19])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError("cutoff has invalid date: %r" % (cutoff,))
    if not (hour <= 23 and minute <= 59 and second <= 59):
        raise ValueError("cutoff has invalid time: %r" % (cutoff,))


def _amount_to_cents(raw, field, allow_multi_decimal):
    """Parse a fixed-point decimal string to integer cents.

    Rejects: empty, NaN, Infinity, negatives.
    v1 (allow_multi_decimal=False): at most two decimals, exact cents.
    v2: any number of decimals, rounded ROUND_HALF_UP to integer cents.
    Uses Decimal only (never float multiplication).
    """
    if raw is None:
        raise ValueError("%s: missing amount" % field)
    text = raw.strip()
    if not text:
        raise ValueError("%s: empty amount" % field)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (field, raw))
    if not value.is_finite():
        raise ValueError("%s: non-finite amount %r" % (field, raw))
    if value < 0:
        raise ValueError("%s: negative amount %r" % (field, raw))
    if allow_multi_decimal:
        try:
            rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            raise ValueError("%s: amount out of range %r" % (field, raw))
        return int(rounded * 100)
    sign, digits, exponent = value.as_tuple()
    if exponent < -2:
        raise ValueError("%s: more than two decimals %r" % (field, raw))
    cents = value.scaleb(2)
    if not cents == cents.to_integral_value():
        raise ValueError("%s: not an exact number of cents %r" % (field, raw))
    return int(cents.to_integral_value())


def _read_rows(csv_text, expected_header):
    """Read CSV text into list of dicts keyed by header names.

    Validates that the header matches expected_header exactly.
    """
    if csv_text is None:
        raise ValueError("csv input must not be None")
    reader = csv.reader(io.StringIO(csv_text))
    rows = []
    header = None
    for line in reader:
        if header is None:
            if not line:
                continue
            header = [name.strip() for name in line]
            if header != list(expected_header):
                raise ValueError("unexpected header: %r" % (line,))
            continue
        if not line or (len(line) == 1 and not line[0].strip()):
            continue
        if len(line) != len(header):
            raise ValueError("row has %d fields, expected %d: %r"
                             % (len(line), len(header), line))
        rows.append({name: field.strip() for name, field in zip(header, line)})
    if header is None:
        return []
    return rows


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds.

    policy="v1": legacy contract, two-decimal amounts, no cutoff, refunds
    without status/date columns.
    policy="v2": cutoff required (YYYY-MM-DDTHH:MM:SSZ); only paid orders
    with created_at <= cutoff are counted; only succeeded refunds with
    created_at <= cutoff are counted; amounts of any precision are rounded
    HALF_UP to cents per row, then summed.

    Returns:
        {"orders": [{order_id, customer, paid_cents, refund_cents, net_cents}],
         "customers": [{customer, net_cents}],
         "totals": {paid_cents, refund_cents, net_cents}}

    Raises ValueError on duplicate ids with conflicting fields (including
    rows excluded by status/cutoff), invalid amounts, invalid policy or
    cutoff, and valid refunds against truly missing or cancelled orders.
    """
    if policy == "v1":
        allow_multi = False
        refund_header = _REFUND_HEADER_V1
    elif policy == "v2":
        if cutoff is None:
            raise ValueError("policy v2 requires cutoff")
        _validate_cutoff(cutoff)
        allow_multi = True
        refund_header = _REFUND_HEADER_V2
    else:
        raise ValueError("unsupported policy: %r" % (policy,))

    # --- Orders ---------------------------------------------------------
    order_rows = _read_rows(orders_csv, _ORDER_HEADER)
    seen_orders = {}          # order_id -> full row tuple (for dedupe check)
    orders = {}               # order_id -> {customer, paid_cents, status, created_at}
    for row in order_rows:
        order_id = row["order_id"]
        if not order_id:
            raise ValueError("order row with empty order_id")
        key = tuple(row[name] for name in _ORDER_HEADER)
        if order_id in seen_orders:
            if seen_orders[order_id] == key:
                continue  # exact duplicate row: count once
            raise ValueError("duplicate order_id with different fields: %r"
                             % order_id)
        seen_orders[order_id] = key
        cents = _amount_to_cents(row["amount"],
                                 "order %s amount" % order_id, allow_multi)
        orders[order_id] = {
            "customer": row["customer"],
            "paid_cents": cents,
            "status": row["status"],
            "created_at": row["created_at"],
        }

    # --- Refunds --------------------------------------------------------
    refund_rows = _read_rows(refunds_csv, refund_header)
    seen_refunds = {}         # refund_id -> full row tuple
    refund_by_order = {}
    for row in refund_rows:
        refund_id = row["refund_id"]
        if not refund_id:
            raise ValueError("refund row with empty refund_id")
        key = tuple(row[name] for name in refund_header)
        if refund_id in seen_refunds:
            if seen_refunds[refund_id] == key:
                continue  # exact duplicate row: count once
            raise ValueError("duplicate refund_id with different fields: %r"
                             % refund_id)
        seen_refunds[refund_id] = key

        order_id = row["order_id"]

        if policy == "v2":
            status = row["status"]
            if status not in ("succeeded", "pending"):
                raise ValueError("refund %s has invalid status %r"
                                 % (refund_id, status))
            valid = (status == "succeeded" and row["created_at"] <= cutoff)
            if not valid:
                continue  # pending or after-cutoff refunds are not counted
            order = orders.get(order_id)
            if order is None:
                raise ValueError("refund %s references unknown order %r"
                                 % (refund_id, order_id))
            if order["status"] != "paid":
                raise ValueError("refund %s references non-paid order %r"
                                 % (refund_id, order_id))
            if order["created_at"] > cutoff:
                continue  # order exists but excluded by cutoff: ignore
        else:
            order = orders.get(order_id)
            if order is None:
                raise ValueError("refund %s references unknown order %r"
                                 % (refund_id, order_id))
            if order["status"] != "paid":
                raise ValueError("refund %s references non-paid order %r"
                                 % (refund_id, order_id))

        cents = _amount_to_cents(row["amount"],
                                 "refund %s amount" % refund_id, allow_multi)
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + cents

    for order_id, refunded in sorted(refund_by_order.items()):
        if refunded > orders[order_id]["paid_cents"]:
            raise ValueError("order %s over-refunded: %d > %d"
                             % (order_id, refunded,
                                orders[order_id]["paid_cents"]))

    # --- Results --------------------------------------------------------
    result_orders = []
    customer_net = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(orders):
        order = orders[order_id]
        if order["status"] != "paid":
            continue
        if policy == "v2" and order["created_at"] > cutoff:
            continue
        paid = order["paid_cents"]
        refunded = refund_by_order.get(order_id, 0)
        net = paid - refunded
        result_orders.append({
            "order_id": order_id,
            "customer": order["customer"],
            "paid_cents": paid,
            "refund_cents": refunded,
            "net_cents": net,
        })
        customer_net[order["customer"]] = \
            customer_net.get(order["customer"], 0) + net
        total_paid += paid
        total_refund += refunded

    customers = [{"customer": name, "net_cents": customer_net[name]}
                 for name in sorted(customer_net)]
    return {
        "orders": result_orders,
        "customers": customers,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def export_bundle(result):
    """Export a reconcile result as the release bundle.

    Returns exactly three files (dict[str, str]):
      orders.csv    header order_id,customer,paid_cents,refund_cents,net_cents
      customers.csv header customer,net_cents
      summary.json  exactly result["totals"] when parsed

    Row order follows the reconcile ordering; amounts are integer text.
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a dict")

    orders_out = io.StringIO()
    writer = csv.writer(orders_out)
    writer.writerow(["order_id", "customer", "paid_cents",
                     "refund_cents", "net_cents"])
    for row in result.get("orders", []):
        writer.writerow([row["order_id"], row["customer"],
                         int(row["paid_cents"]), int(row["refund_cents"]),
                         int(row["net_cents"])])

    customers_out = io.StringIO()
    writer = csv.writer(customers_out)
    writer.writerow(["customer", "net_cents"])
    for row in result.get("customers", []):
        writer.writerow([row["customer"], int(row["net_cents"])])

    totals = result.get("totals")
    if not isinstance(totals, dict):
        raise ValueError("result totals must be a dict")
    summary = json.dumps({
        "paid_cents": int(totals["paid_cents"]),
        "refund_cents": int(totals["refund_cents"]),
        "net_cents": int(totals["net_cents"]),
    })

    return {
        "orders.csv": orders_out.getvalue(),
        "customers.csv": customers_out.getvalue(),
        "summary.json": summary,
    }
