import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _parse_amount_cents(raw, kind, allow_extra_decimals=False):
    """Parse a non-negative fixed-point amount into integer cents.

    Uses Decimal only (no float arithmetic). Rejects NaN/Infinity/negatives.
    v1 (allow_extra_decimals=False): at most two decimals, exact conversion.
    v2 (allow_extra_decimals=True): any number of decimals, ROUND_HALF_UP to
    whole cents (per-row rounding; callers sum afterwards).
    """
    if raw is None:
        raise ValueError("%s: missing amount" % kind)
    text = raw.strip()
    if not text:
        raise ValueError("%s: empty amount" % kind)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (kind, raw))
    if not value.is_finite():
        raise ValueError("%s: non-finite amount %r" % (kind, raw))
    if value < 0:
        raise ValueError("%s: negative amount %r" % (kind, raw))
    if not allow_extra_decimals:
        sign, digits, exponent = value.as_tuple()
        if exponent < -2:
            raise ValueError("%s: more than two decimals in %r" % (kind, raw))
        # exponent >= -2, so shifting by 2 yields an exact integer.
        return int(value.scaleb(2).to_integral_value())
    return int(value.scaleb(2).to_integral_value(rounding=ROUND_HALF_UP))


def _validate_cutoff(cutoff):
    if not isinstance(cutoff, str):
        raise ValueError("cutoff must be a string")
    text = cutoff.strip()
    if len(text) != 20 or text[-1] != "Z":
        raise ValueError("cutoff: expected YYYY-MM-DDTHH:MM:SSZ, got %r" % cutoff)
    try:
        date_part, time_part = text[:-1].split("T")
        year, month, day = (int(p) for p in date_part.split("-"))
        hour, minute, second = (int(p) for p in time_part.split(":"))
    except ValueError:
        raise ValueError("cutoff: expected YYYY-MM-DDTHH:MM:SSZ, got %r" % cutoff)
    ok = (
        len(date_part) == 10
        and len(time_part) == 8
        and 1 <= month <= 12
        and 1 <= day <= 31
        and hour < 24
        and minute < 60
        and second < 60
    )
    if not ok:
        raise ValueError("cutoff: invalid date/time %r" % cutoff)
    return text


def _read_rows(csv_text, required_header, kind):
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows:
        return []
    header = [cell.strip() for cell in rows[0]]
    if header != required_header:
        raise ValueError(
            "%s: bad header %r, expected %r" % (kind, header, required_header)
        )
    return [dict(zip(header, row)) for row in rows[1:]]


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds per the v1/v2 contract.

    Returns a dict:
      {"orders": [{order_id, customer, paid_cents, refund_cents, net_cents}...],
       "customers": [{customer, net_cents}...],
       "totals": {paid_cents, refund_cents, net_cents}}
    All amounts are integer cents. Inputs are CSV strings and are not modified.

    policy="v1": legacy column contract and strict two-decimal amounts.
    policy="v2": cutoff required (YYYY-MM-DDTHH:MM:SSZ); refunds carry
    status/created_at; only paid orders and succeeded refunds with
    created_at <= cutoff count; amounts may have extra decimals and are
    rounded HALF_UP to cents per row. Duplicate-id conflicts are checked on
    every row regardless of status/cutoff.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v2":
        if cutoff is None:
            raise ValueError("policy v2 requires cutoff")
        cutoff = _validate_cutoff(cutoff)
    allow_extra = policy == "v2"

    order_fields = ["order_id", "customer", "amount", "status", "created_at"]
    if policy == "v1":
        refund_fields = ["refund_id", "order_id", "amount"]
    else:
        refund_fields = ["refund_id", "order_id", "amount", "status", "created_at"]

    order_rows = _read_rows(orders_csv, order_fields, "orders")
    refund_rows = _read_rows(refunds_csv, refund_fields, "refunds")

    # ---- Orders: dedupe by order_id (all rows, even excluded ones) ----
    orders = {}  # order_id -> dict(customer, status, paid_cents, created_at)
    seen_order_rows = {}  # order_id -> raw row tuple for exact-duplicate check
    for row in order_rows:
        order_id = (row.get("order_id") or "").strip()
        if not order_id:
            raise ValueError("orders: empty order_id")
        key = tuple((row.get(field) or "").strip() for field in order_fields)
        if order_id in seen_order_rows:
            if seen_order_rows[order_id] == key:
                continue  # exact duplicate, count once
            raise ValueError(
                "orders: duplicate order_id %s with differing fields" % order_id
            )
        seen_order_rows[order_id] = key
        status = (row.get("status") or "").strip().lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("orders: unknown status %r" % row.get("status"))
        customer = (row.get("customer") or "").strip()
        if not customer:
            raise ValueError("orders: empty customer for %s" % order_id)
        paid_cents = _parse_amount_cents(
            row.get("amount"), "order %s" % order_id, allow_extra
        )
        orders[order_id] = {
            "customer": customer,
            "status": status,
            "paid_cents": paid_cents,
            "created_at": (row.get("created_at") or "").strip(),
        }

    # ---- Refunds: dedupe by refund_id, validate against orders ----
    refund_by_order = {}  # order_id -> accumulated refund_cents (counted only)
    seen_refund_rows = {}  # refund_id -> raw row tuple
    for row in refund_rows:
        refund_id = (row.get("refund_id") or "").strip()
        if not refund_id:
            raise ValueError("refunds: empty refund_id")
        key = tuple((row.get(field) or "").strip() for field in refund_fields)
        if refund_id in seen_refund_rows:
            if seen_refund_rows[refund_id] == key:
                continue  # exact duplicate, count once
            raise ValueError(
                "refunds: duplicate refund_id %s with differing fields" % refund_id
            )
        seen_refund_rows[refund_id] = key

        if policy == "v2":
            status = (row.get("status") or "").strip().lower()
            if status not in ("succeeded", "pending"):
                raise ValueError("refunds: unknown status %r" % row.get("status"))
            created_at = (row.get("created_at") or "").strip()
            # Pending or after-cutoff refunds are not effective: ignore them
            # entirely (even if the order is unknown or cancelled).
            if status != "succeeded" or created_at > cutoff:
                continue

        order_id = (row.get("order_id") or "").strip()
        if order_id not in orders:
            raise ValueError("refunds: unknown order %s" % order_id)
        if orders[order_id]["status"] != "paid":
            raise ValueError("refunds: order %s is not paid" % order_id)
        if policy == "v2" and orders[order_id]["created_at"] > cutoff:
            # Order exists but is excluded by cutoff: ignore the refund.
            continue
        refund_cents = _parse_amount_cents(
            row.get("amount"), "refund %s" % refund_id, allow_extra
        )
        total = refund_by_order.get(order_id, 0) + refund_cents
        if total > orders[order_id]["paid_cents"]:
            raise ValueError(
                "refunds: order %s over-refunded (%d > %d cents)"
                % (order_id, total, orders[order_id]["paid_cents"])
            )
        refund_by_order[order_id] = total

    # ---- Build result ----
    result_orders = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(orders):
        info = orders[order_id]
        if info["status"] != "paid":
            continue
        if policy == "v2" and info["created_at"] > cutoff:
            continue
        paid_cents = info["paid_cents"]
        refund_cents = refund_by_order.get(order_id, 0)
        net_cents = paid_cents - refund_cents
        result_orders.append(
            {
                "order_id": order_id,
                "customer": info["customer"],
                "paid_cents": paid_cents,
                "refund_cents": refund_cents,
                "net_cents": net_cents,
            }
        )
        customer = info["customer"]
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
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Render a reconcile result into the release bundle.

    Returns exactly three files as dict[str, str]:
      orders.csv    - header order_id,customer,paid_cents,refund_cents,net_cents
      customers.csv - header customer,net_cents
      summary.json  - JSON object equal to result["totals"]
    Row order follows reconcile ordering; amounts are written as integers.
    """
    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            [
                order["order_id"],
                order["customer"],
                int(order["paid_cents"]),
                int(order["refund_cents"]),
                int(order["net_cents"]),
            ]
            for order in result["orders"]
        ],
    )
    customers_csv = _csv_text(
        ["customer", "net_cents"],
        [[c["customer"], int(c["net_cents"])] for c in result["customers"]],
    )
    totals = result["totals"]
    summary = json.dumps(
        {
            "paid_cents": int(totals["paid_cents"]),
            "refund_cents": int(totals["refund_cents"]),
            "net_cents": int(totals["net_cents"]),
        },
        sort_keys=True,
    )
    return {"orders.csv": orders_csv, "customers.csv": customers_csv, "summary.json": summary}
