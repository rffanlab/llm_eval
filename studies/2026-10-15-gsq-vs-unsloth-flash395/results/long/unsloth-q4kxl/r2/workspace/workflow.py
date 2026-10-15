"""Order reconciliation - pure functions only (csv/io/json/decimal/collections/datetime/math)."""
import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime


def _parse_amount_cents(raw, policy):
    """Parse a non-negative decimal amount string into integer cents.

    v1: at most two decimal places (legacy contract).
    v2: any number of decimals, rounded to cents with ROUND_HALF_UP.
    Always rejects NaN/Infinity/negatives. Uses Decimal fixed-point;
    never float * 100.
    """
    if raw is None:
        raise ValueError("missing amount")
    text = str(raw).strip()
    if text == "":
        raise ValueError("empty amount")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % (raw,))
    if not value.is_finite():
        raise ValueError("non-finite amount: %r" % (raw,))
    if value < 0:
        raise ValueError("negative amount: %r" % (raw,))
    if policy == "v1":
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("amount has more than two decimals: %r" % (raw,))
        cents = value * Decimal(100)
        if cents != cents.to_integral_value():
            raise ValueError("amount not representable in cents: %r" % (raw,))
        return int(cents.to_integral_value())
    # v2: fixed-point ROUND_HALF_UP to integer cents.
    cents = (value * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _validate_utc_timestamp(text, field):
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        raise ValueError("invalid %s: %r (expected YYYY-MM-DDTHH:MM:SSZ)" % (field, text))
    return text


def _read_rows(csv_text, required_header, kind):
    """Read a CSV string into a list of dict rows. Does not mutate input."""
    if csv_text is None:
        raise ValueError("%s csv is None" % kind)
    reader = csv.reader(io.StringIO(csv_text))
    rows = []
    for row in reader:
        if not row or all(cell.strip() == "" for cell in row):
            continue
        rows.append(row)
    if not rows:
        raise ValueError("%s csv must have a header" % kind)
    header = [h.strip() for h in rows[0]]
    if header != required_header:
        raise ValueError(
            "%s header mismatch: expected %r, got %r" % (kind, required_header, header)
        )
    dicts = []
    for row in rows[1:]:
        if len(row) != len(header):
            raise ValueError("%s row has wrong column count: %r" % (kind, row))
        dicts.append({header[i]: row[i].strip() for i in range(len(header))})
    return dicts


def _dedupe(rows, id_field, kind):
    """Dedupe by id: exact duplicate rows count once; conflicting rows raise.

    Runs before any filtering so conflicts involving pending or
    after-cutoff rows are still rejected.
    """
    seen = {}
    unique = []
    for row in rows:
        key = row.get(id_field, "")
        if key in seen:
            if seen[key] != row:
                raise ValueError(
                    "conflicting duplicate %s for %s=%r" % (kind, id_field, key)
                )
            continue
        seen[key] = row
        unique.append(row)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile orders and refunds per the v1/v2 contracts.

    Returns {"orders": [...], "customers": [...], "totals": {...}} with
    integer cents. Pure function: no file/network/process access, inputs
    are never mutated.

    v1: legacy amount limits, refunds have no status/created_at, cutoff
    is ignored.
    v2: cutoff required (YYYY-MM-DDTHH:MM:SSZ); only paid orders with
    created_at <= cutoff count; only succeeded refunds with
    created_at <= cutoff count; amounts rounded HALF_UP to cents per
    row before summing.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v2":
        if cutoff is None:
            raise ValueError("v2 requires a cutoff")
        _validate_utc_timestamp(cutoff, "cutoff")

    order_rows = _read_rows(
        orders_csv, ["order_id", "customer", "amount", "status", "created_at"], "orders"
    )
    refund_header = ["refund_id", "order_id", "amount"]
    if policy == "v2":
        refund_header = refund_header + ["status", "created_at"]
    refund_rows = _read_rows(refunds_csv, refund_header, "refunds")

    order_rows = _dedupe(order_rows, "order_id", "order")
    refund_rows = _dedupe(refund_rows, "refund_id", "refund")

    # Build paid-order table; cancelled orders are excluded from results.
    paid = {}
    all_order_ids = set()
    for row in order_rows:
        order_id = row["order_id"]
        status = row["status"].lower()
        all_order_ids.add(order_id)
        cents = _parse_amount_cents(row["amount"], policy)
        if status == "paid":
            if policy == "v2":
                _validate_utc_timestamp(row["created_at"], "order created_at")
                if row["created_at"] > cutoff:
                    # After-cutoff orders do not count.
                    continue
            paid[order_id] = {
                "order_id": order_id,
                "customer": row["customer"],
                "paid_cents": cents,
                "refund_cents": 0,
            }
        elif status != "cancelled":
            raise ValueError("unknown order status: %r" % (row["status"],))

    # Apply refunds.
    for row in refund_rows:
        order_id = row["order_id"]
        refund_cents = _parse_amount_cents(row["amount"], policy)
        if policy == "v2":
            status = row["status"].lower()
            if status not in ("succeeded", "pending"):
                raise ValueError("unknown refund status: %r" % (row["status"],))
            _validate_utc_timestamp(row["created_at"], "refund created_at")
            if status != "succeeded" or row["created_at"] > cutoff:
                # Pending or after-cutoff refunds do not count.
                continue
        if order_id not in all_order_ids:
            raise ValueError("refund for unknown order: %r" % (order_id,))
        if order_id not in paid:
            if policy == "v2":
                # Order exists but was excluded by cutoff -> ignore;
                # a cancelled order is still an error.
                cancelled = any(
                    r["order_id"] == order_id and r["status"].lower() == "cancelled"
                    for r in order_rows
                )
                if not cancelled:
                    continue
            raise ValueError("refund for cancelled order: %r" % (order_id,))
        entry = paid[order_id]
        entry["refund_cents"] += refund_cents
        if entry["refund_cents"] > entry["paid_cents"]:
            raise ValueError(
                "refunds exceed paid amount for order: %r" % (order_id,)
            )

    orders_out = []
    totals_paid = 0
    totals_refund = 0
    for order_id in sorted(paid):
        entry = paid[order_id]
        net = entry["paid_cents"] - entry["refund_cents"]
        orders_out.append(
            {
                "order_id": order_id,
                "customer": entry["customer"],
                "paid_cents": entry["paid_cents"],
                "refund_cents": entry["refund_cents"],
                "net_cents": net,
            }
        )
        totals_paid += entry["paid_cents"]
        totals_refund += entry["refund_cents"]

    customer_nets = {}
    for order in orders_out:
        customer_nets[order["customer"]] = (
            customer_nets.get(order["customer"], 0) + order["net_cents"]
        )
    customers_out = [
        {"customer": name, "net_cents": customer_nets[name]}
        for name in sorted(customer_nets)
    ]

    return {
        "orders": orders_out,
        "customers": customers_out,
        "totals": {
            "paid_cents": totals_paid,
            "refund_cents": totals_refund,
            "net_cents": totals_paid - totals_refund,
        },
    }


def _csv_text(header, rows):
    """Render CSV text with the standard csv writer (integers as plain text)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """Build the release bundle for a reconcile result.

    Returns exactly three files per the release contract:
    - orders.csv: order_id,customer,paid_cents,refund_cents,net_cents
      (row order follows reconcile ordering).
    - customers.csv: customer,net_cents.
    - summary.json: JSON that parses to exactly result["totals"].
    Amounts are written as integer text.
    """
    orders_rows = [
        [
            order["order_id"],
            order["customer"],
            int(order["paid_cents"]),
            int(order["refund_cents"]),
            int(order["net_cents"]),
        ]
        for order in result["orders"]
    ]
    customers_rows = [
        [customer["customer"], int(customer["net_cents"])]
        for customer in result["customers"]
    ]
    return {
        "orders.csv": _csv_text(
            ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
            orders_rows,
        ),
        "customers.csv": _csv_text(["customer", "net_cents"], customers_rows),
        "summary.json": json.dumps(
            result["totals"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
    }
