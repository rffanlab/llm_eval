"""Order reconciliation - v1 + v2 contracts (spec-v1.md, spec-v2.md).

Pure functions only. No file/network/process access.
Allowed imports: csv, io, json, decimal, hashlib, collections, datetime, math.
"""

import csv
import io
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDERS_HEADER = ["order_id", "customer", "amount", "status", "created_at"]
_REFUNDS_HEADER_V1 = ["refund_id", "order_id", "amount"]
_REFUNDS_HEADER_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]


def _is_valid_cutoff(value):
    """Validate YYYY-MM-DDTHH:MM:SSZ shape without extra imports."""
    if not isinstance(value, str) or len(value) != 20:
        return False
    digits = set("0123456789")
    for i in (4, 7):
        if value[i] != "-":
            return False
    if value[10] != "T" or value[13] != ":" or value[16] != ":":
        return False
    if value[19] != "Z":
        return False
    for i in (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18):
        if value[i] not in digits:
            return False
    return True


def _parse_amount_to_cents(raw, context, policy):
    """Parse an amount string to integer cents.

    v1: at most two decimals (old restriction), exact.
    v2: any number of decimals, Decimal ROUND_HALF_UP to cents.
    Never uses float. Rejects empty/NaN/Infinity/negative.
    """
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = raw.strip()
    if text == "":
        raise ValueError("%s: empty amount" % context)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if not value.is_finite():
        raise ValueError("%s: non-finite amount %r" % (context, raw))
    if value < 0:
        raise ValueError("%s: negative amount %r" % (context, raw))
    if policy == "v1":
        sign, digits, exponent = value.as_tuple()
        if exponent < -2:
            raise ValueError("%s: more than two decimals %r" % (context, raw))
        return int(value.scaleb(2))
    # v2: ROUND_HALF_UP to integer cents (fixed-point, no float).
    return int(value.scaleb(2).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _read_rows(csv_text, required_header, kind):
    """Parse CSV text into list of dicts keyed by header. Raises ValueError on shape issues."""
    if csv_text is None:
        raise ValueError("%s csv is None" % kind)
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row and any(field.strip() != "" for field in row)]
    if not rows:
        raise ValueError("%s csv: missing header" % kind)
    header = [field.strip() for field in rows[0]]
    if header != required_header:
        raise ValueError(
            "%s csv: bad header %r, expected %r" % (kind, header, required_header)
        )
    records = []
    for lineno, row in enumerate(rows[1:], start=2):
        if len(row) != len(header):
            raise ValueError("%s csv line %d: wrong column count" % (kind, lineno))
        records.append({header[i]: row[i].strip() for i in range(len(header))})
    return records


def _dedupe(records, kind, policy, cents_getter):
    """Return dict id -> record, skipping exact duplicate rows, rejecting conflicts.

    Conflict checks apply to every row, including pending/after-cutoff ones.
    """
    seen = {}
    for rec in records:
        rid = rec["order_id"] if kind == "orders" else rec["refund_id"]
        if rid == "":
            raise ValueError("%s: empty id" % kind)
        key = tuple(rec[col] for col in sorted(rec))
        if rid in seen:
            if seen[rid]["_key"] == key:
                continue  # exact duplicate row: counted once
            raise ValueError(
                "%s: duplicate id %s with different fields" % (kind, rid)
            )
        entry = dict(rec)
        entry["_key"] = key
        entry["_cents"] = cents_getter(rec, rid)
        seen[rid] = entry
    return seen


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds per the v1/v2 contract.

    Returns:
        {
          "orders": [{"order_id", "customer", "paid_cents", "refund_cents", "net_cents"}...],
          "customers": [{"customer", "net_cents"}...],
          "totals": {"paid_cents", "refund_cents", "net_cents"}
        }
    Raises ValueError on any contract violation.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v1":
        if cutoff is not None:
            raise ValueError("cutoff is not supported by policy v1")
    else:  # v2
        if cutoff is None:
            raise ValueError("policy v2 requires cutoff")
        if not _is_valid_cutoff(cutoff):
            raise ValueError("policy v2: bad cutoff %r" % (cutoff,))

    # ---- Orders ----
    order_records = _read_rows(orders_csv, _ORDERS_HEADER, "orders")

    def order_cents(rec, oid):
        status = rec["status"]
        if status not in ("paid", "cancelled"):
            raise ValueError("orders: unknown status %r for %s" % (status, oid))
        return _parse_amount_to_cents(rec["amount"], "orders %s" % oid, policy)

    orders = _dedupe(order_records, "orders", policy, order_cents)

    # ---- Refunds ----
    refunds_header = _REFUNDS_HEADER_V1 if policy == "v1" else _REFUNDS_HEADER_V2
    refund_records = _read_rows(refunds_csv, refunds_header, "refunds")

    def refund_cents(rec, rid):
        if policy == "v2":
            status = rec["status"]
            if status not in ("succeeded", "pending"):
                raise ValueError("refunds: unknown status %r for %s" % (status, rid))
        return _parse_amount_to_cents(rec["amount"], "refunds %s" % rid, policy)

    refunds = _dedupe(refund_records, "refunds", policy, refund_cents)

    # ---- Selection predicates ----
    def order_counts(oid):
        order = orders[oid]
        if order["status"] != "paid":
            return False
        if policy == "v2" and order["created_at"] > cutoff:
            return False  # after-cutoff order: excluded
        return True

    def refund_counts(rid):
        refund = refunds[rid]
        if policy == "v1":
            return True
        if refund["status"] != "succeeded":
            return False
        if refund["created_at"] > cutoff:
            return False
        return True

    # ---- Validate counted refunds against orders ----
    refund_by_order = {}
    for rid in sorted(refunds):
        if not refund_counts(rid):
            continue  # pending / after-cutoff refunds are not counted
        oid = refunds[rid]["order_id"]
        order = orders.get(oid)
        if order is None:
            raise ValueError("refunds: %s references unknown order %s" % (rid, oid))
        if order["status"] != "paid":
            raise ValueError("refunds: %s references cancelled order %s" % (rid, oid))
        if policy == "v2" and order["created_at"] > cutoff:
            continue  # order exists but excluded by cutoff: ignore refund
        refund_by_order[oid] = refund_by_order.get(oid, 0) + refunds[rid]["_cents"]

    for oid in sorted(refund_by_order):
        order = orders[oid]
        if refund_by_order[oid] > order["_cents"]:
            raise ValueError(
                "refunds: order %s refunded %d cents exceeds paid %d cents"
                % (oid, refund_by_order[oid], order["_cents"])
            )

    # ---- Build result (counted paid orders only) ----
    result_orders = []
    customer_net = {}
    total_paid = total_refund = 0
    for oid in sorted(orders):
        if not order_counts(oid):
            continue
        order = orders[oid]
        paid = order["_cents"]
        refunded = refund_by_order.get(oid, 0)
        net = paid - refunded
        result_orders.append(
            {
                "order_id": oid,
                "customer": order["customer"],
                "paid_cents": paid,
                "refund_cents": refunded,
                "net_cents": net,
            }
        )
        customer = order["customer"]
        customer_net[customer] = customer_net.get(customer, 0) + net
        total_paid += paid
        total_refund += refunded

    result_customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
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


def _csv_text(header, rows):
    """Render rows (list of lists) to CSV text with the standard writer."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Serialize a reconcile result into the release bundle (release-spec.md).

    Returns exactly three files: orders.csv, customers.csv, summary.json.
    Row order follows reconcile ordering; amounts are integer text;
    summary.json is exactly result["totals"].
    """
    import json

    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            [
                o["order_id"],
                o["customer"],
                str(o["paid_cents"]),
                str(o["refund_cents"]),
                str(o["net_cents"]),
            ]
            for o in result["orders"]
        ],
    )
    customers_csv = _csv_text(
        ["customer", "net_cents"],
        [[c["customer"], str(c["net_cents"])] for c in result["customers"]],
    )
    summary_json = json.dumps(result["totals"], sort_keys=True)
    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
