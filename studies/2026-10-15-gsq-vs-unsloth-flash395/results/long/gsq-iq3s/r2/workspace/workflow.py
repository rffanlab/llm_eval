import csv
import io
import json
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _parse_amount_cents(raw, field, allow_many_decimals):
    """Parse a non-negative decimal string into integer cents using
    fixed-point Decimal (no float math).

    v1 (allow_many_decimals=False): at most 2 decimal places.
    v2 (allow_many_decimals=True): any number of decimals, rounded to
    cents with ROUND_HALF_UP.
    """
    if raw is None:
        raise ValueError("%s missing" % field)
    s = raw.strip()
    if s == "":
        raise ValueError("%s empty" % field)
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError("%s invalid amount: %r" % (field, raw))
    if not d.is_finite():
        raise ValueError("%s non-finite amount: %r" % (field, raw))
    if d < 0:
        raise ValueError("%s negative amount: %r" % (field, raw))
    if not allow_many_decimals:
        exponent = d.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("%s more than 2 decimals: %r" % (field, raw))
        cents = d * 100
        if cents != cents.to_integral_value():
            raise ValueError("%s more than 2 decimals: %r" % (field, raw))
        return int(cents.to_integral_value())
    cents = (d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _read_rows(csv_text, required_fields):
    if csv_text is None:
        raise ValueError("csv input missing")
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        raise ValueError("csv header missing")
    for f in required_fields:
        if f not in reader.fieldnames:
            raise ValueError("csv column missing: %s" % f)
    rows = []
    for row in reader:
        # DictReader yields all-empty rows for blank lines; skip them.
        if all(v in (None, "") for v in row.values()):
            continue
        rows.append(row)
    return rows


def _validate_cutoff(cutoff):
    if not isinstance(cutoff, str):
        raise ValueError("cutoff must be a string")
    try:
        datetime.datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ: %r" % (cutoff,))
    return cutoff


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    many_decimals = policy == "v2"
    if policy == "v2":
        if cutoff is None:
            raise ValueError("cutoff required for policy v2")
        cutoff = _validate_cutoff(cutoff)

    # ---- Orders: parse, validate, dedup by order_id ----
    order_fields = ["order_id", "customer", "amount", "status"]
    if many_decimals:
        order_fields.append("created_at")
    order_rows = _read_rows(orders_csv, order_fields)
    orders = {}  # order_id -> (customer, status, amount_cents, created_at)
    for row in order_rows:
        order_id = (row.get("order_id") or "").strip()
        customer = (row.get("customer") or "").strip()
        status = (row.get("status") or "").strip()
        created_at = (row.get("created_at") or "").strip()
        if order_id == "":
            raise ValueError("order_id empty")
        if customer == "":
            raise ValueError("customer empty for order %s" % order_id)
        if status == "":
            raise ValueError("status empty for order %s" % order_id)
        if many_decimals and created_at == "":
            raise ValueError("created_at empty for order %s" % order_id)
        amount_cents = _parse_amount_cents(
            row.get("amount"), "amount of %s" % order_id, many_decimals
        )
        signature = (customer, status, amount_cents, created_at)
        prev = orders.get(order_id)
        if prev is not None:
            if prev != signature:
                raise ValueError(
                    "conflicting duplicate order_id %s" % order_id
                )
            continue  # exact duplicate row: count once
        orders[order_id] = signature

    # ---- Refunds: parse, validate, dedup by refund_id ----
    refund_fields = ["refund_id", "order_id", "amount"]
    if many_decimals:
        refund_fields.extend(["status", "created_at"])
    refund_rows = _read_rows(refunds_csv, refund_fields)
    refunds_seen = {}  # refund_id -> signature (dedup covers all rows)
    refund_by_order = {}
    for row in refund_rows:
        refund_id = (row.get("refund_id") or "").strip()
        order_id = (row.get("order_id") or "").strip()
        status = (row.get("status") or "").strip()
        created_at = (row.get("created_at") or "").strip()
        if refund_id == "":
            raise ValueError("refund_id empty")
        if order_id == "":
            raise ValueError("order_id empty for refund %s" % refund_id)
        if many_decimals and status not in ("succeeded", "pending"):
            raise ValueError("invalid refund status for %s" % refund_id)
        if many_decimals and created_at == "":
            raise ValueError("created_at empty for refund %s" % refund_id)
        amount_cents = _parse_amount_cents(
            row.get("amount"), "amount of %s" % refund_id, many_decimals
        )
        signature = (order_id, amount_cents, status, created_at)
        prev = refunds_seen.get(refund_id)
        if prev is not None:
            if prev != signature:
                raise ValueError(
                    "conflicting duplicate refund_id %s" % refund_id
                )
            continue  # exact duplicate row: count once
        refunds_seen[refund_id] = signature

        if many_decimals:
            # pending or after-cutoff refunds are not effective at all.
            if status != "succeeded" or created_at > cutoff:
                continue
        if order_id not in orders:
            raise ValueError(
                "refund %s targets unknown order %s" % (refund_id, order_id)
            )
        customer, ostatus, paid_cents, o_created = orders[order_id]
        if ostatus != "paid":
            raise ValueError(
                "refund %s targets non-paid order %s" % (refund_id, order_id)
            )
        if many_decimals and o_created > cutoff:
            # order exists but is excluded by cutoff: ignore the refund
            continue
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + amount_cents

    for order_id, total in refund_by_order.items():
        if total > orders[order_id][2]:
            raise ValueError(
                "refunds exceed paid amount for order %s" % order_id
            )

    # ---- Build result ----
    order_entries = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(orders):
        customer, status, amount_cents, created_at = orders[order_id]
        if status != "paid":
            continue
        if many_decimals and created_at > cutoff:
            continue
        refund_cents = refund_by_order.get(order_id, 0)
        net_cents = amount_cents - refund_cents
        order_entries.append({
            "order_id": order_id,
            "customer": customer,
            "paid_cents": amount_cents,
            "refund_cents": refund_cents,
            "net_cents": net_cents,
        })
        customer_net[customer] = customer_net.get(customer, 0) + net_cents
        totals["paid_cents"] += amount_cents
        totals["refund_cents"] += refund_cents
        totals["net_cents"] += net_cents

    customers = [
        {"customer": c, "net_cents": customer_net[c]}
        for c in sorted(customer_net)
    ]
    return {"orders": order_entries, "customers": customers, "totals": totals}


def export_bundle(result):
    """Render the reconcile result as exactly three release files:
    orders.csv, customers.csv, summary.json (per release-spec.md)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["order_id", "customer", "paid_cents", "refund_cents", "net_cents"])
    for o in result["orders"]:
        writer.writerow([
            o["order_id"],
            o["customer"],
            "%d" % o["paid_cents"],
            "%d" % o["refund_cents"],
            "%d" % o["net_cents"],
        ])
    orders_csv = buf.getvalue()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["customer", "net_cents"])
    for c in result["customers"]:
        writer.writerow([c["customer"], "%d" % c["net_cents"]])
    customers_csv = buf.getvalue()

    summary_json = json.dumps(result["totals"], sort_keys=True)

    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
