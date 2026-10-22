"""Order reconciliation, v1 + v2 contracts (see spec-v1.md / spec-v2.md)."""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _valid_cutoff(cutoff):
    """Validate YYYY-MM-DDTHH:MM:SSZ without regex."""
    if not isinstance(cutoff, str) or len(cutoff) != 20:
        return False
    if cutoff[4] != "-" or cutoff[7] != "-" or cutoff[10] != "T":
        return False
    if cutoff[13] != ":" or cutoff[16] != ":" or cutoff[19] != "Z":
        return False
    digits_idx = [0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18]
    if not all(cutoff[i].isdigit() for i in digits_idx):
        return False
    try:
        year = int(cutoff[0:4])
        month = int(cutoff[5:7])
        day = int(cutoff[8:10])
        hour = int(cutoff[11:13])
        minute = int(cutoff[14:16])
        second = int(cutoff[17:19])
    except ValueError:
        return False
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    if hour > 23 or minute > 59 or second > 60:
        return False
    if year < 1:
        return False
    return True


def _parse_amount_cents(raw, what, policy):
    """Parse a decimal amount string to integer cents.

    v1: non-negative, at most two decimal places, no NaN/Infinity.
    v2: non-negative, any number of decimals, ROUND_HALF_UP to cents.
    Always decimal fixed-point (never float multiplication).
    """
    if raw is None:
        raise ValueError("%s is missing" % what)
    text = raw.strip()
    if text == "":
        raise ValueError("%s is empty" % what)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s is not a valid number: %r" % (what, raw))
    if not value.is_finite():
        raise ValueError("%s is not finite: %r" % (what, raw))
    if value < 0:
        raise ValueError("%s is negative: %r" % (what, raw))
    if policy == "v1":
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("%s has more than two decimal places: %r" % (what, raw))
        cents = value.scaleb(2).to_integral_value()
    else:
        cents = value.scaleb(2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _read_rows(csv_text, required_headers, kind):
    if csv_text is None:
        raise ValueError("%s csv is missing" % kind)
    reader = csv.reader(csv_text.splitlines())
    rows = [row for row in reader if row and any(cell.strip() != "" for cell in row)]
    if not rows:
        raise ValueError("%s csv must have a header" % kind)
    header = [h.strip() for h in rows[0]]
    for name in required_headers:
        if name not in header:
            raise ValueError("%s csv missing column: %s" % (kind, name))
    out = []
    for row in rows[1:]:
        if len(row) != len(header):
            raise ValueError("%s row has wrong number of fields: %r" % (kind, row))
        out.append({name: row[i].strip() for i, name in enumerate(header)})
    return out


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v2":
        if cutoff is None:
            raise ValueError("v2 requires a cutoff")
        if isinstance(cutoff, str):
            cutoff = cutoff.strip()
        if not _valid_cutoff(cutoff):
            raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ: %r" % (cutoff,))

    # ---- orders: parse, validate, dedupe by order_id ----
    order_rows = _read_rows(
        orders_csv, ["order_id", "customer", "amount", "status"], "orders"
    )
    orders = {}  # order_id -> record
    for row in order_rows:
        order_id = row["order_id"]
        if order_id == "":
            raise ValueError("orders row has empty order_id")
        customer = row["customer"]
        status = row["status"].lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("unknown order status: %r" % row["status"])
        amount_cents = _parse_amount_cents(
            row["amount"], "order amount for %s" % order_id, policy
        )
        created_at = row.get("created_at", "")
        if policy == "v2" and created_at == "":
            raise ValueError("order %s missing created_at" % order_id)
        record = {
            "customer": customer,
            "status": status,
            "paid_cents": amount_cents,
            "created_at": created_at,
        }
        if order_id in orders:
            if orders[order_id] != record:
                raise ValueError("conflicting rows for order_id %s" % order_id)
            continue  # exact duplicate, count once
        orders[order_id] = record

    # ---- refunds: parse, validate, dedupe by refund_id ----
    refund_required = ["refund_id", "order_id", "amount"]
    if policy == "v2":
        refund_required += ["status", "created_at"]
    refund_rows = _read_rows(refunds_csv, refund_required, "refunds")
    refunds = {}  # refund_id -> record
    for row in refund_rows:
        refund_id = row["refund_id"]
        if refund_id == "":
            raise ValueError("refunds row has empty refund_id")
        status = "succeeded"
        created_at = ""
        if policy == "v2":
            status = row["status"].lower()
            if status not in ("succeeded", "pending"):
                raise ValueError("unknown refund status: %r" % row["status"])
            created_at = row.get("created_at", "")
            if created_at == "":
                raise ValueError("refund %s missing created_at" % refund_id)
        record = {
            "order_id": row["order_id"],
            "amount_cents": _parse_amount_cents(
                row["amount"], "refund amount for %s" % refund_id, policy
            ),
            "status": status,
            "created_at": created_at,
        }
        if refund_id in refunds:
            # conflicts rejected even for pending / post-cutoff rows
            if refunds[refund_id] != record:
                raise ValueError("conflicting rows for refund_id %s" % refund_id)
            continue
        refunds[refund_id] = record

    # ---- apply refunds ----
    refund_by_order = {}
    for refund_id, record in refunds.items():
        effective = record["status"] == "succeeded"
        if policy == "v2" and effective and record["created_at"] > cutoff:
            effective = False  # post-cutoff refund: ignored
        order_id = record["order_id"]
        order = orders.get(order_id)
        if effective:
            if order is None:
                raise ValueError(
                    "refund %s references unknown order %s" % (refund_id, order_id)
                )
            if order["status"] != "paid":
                raise ValueError(
                    "refund %s references cancelled order %s" % (refund_id, order_id)
                )
            if policy == "v2" and order["created_at"] > cutoff:
                # order exists but excluded by cutoff -> ignore the refund
                continue
            refund_by_order[order_id] = (
                refund_by_order.get(order_id, 0) + record["amount_cents"]
            )
    for order_id, total in refund_by_order.items():
        if total > orders[order_id]["paid_cents"]:
            raise ValueError("refunds for order %s exceed paid amount" % order_id)

    # ---- build result (paid orders only, within cutoff) ----
    result_orders = []
    customers_total = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(orders):
        order = orders[order_id]
        if order["status"] != "paid":
            continue
        if policy == "v2" and order["created_at"] > cutoff:
            continue
        paid = order["paid_cents"]
        refund = refund_by_order.get(order_id, 0)
        net = paid - refund
        result_orders.append({
            "order_id": order_id,
            "customer": order["customer"],
            "paid_cents": paid,
            "refund_cents": refund,
            "net_cents": net,
        })
        customers_total[order["customer"]] = (
            customers_total.get(order["customer"], 0) + net
        )
        totals["paid_cents"] += paid
        totals["refund_cents"] += refund
        totals["net_cents"] += net

    customers = [
        {"customer": name, "net_cents": customers_total[name]}
        for name in sorted(customers_total)
    ]
    return {"orders": result_orders, "customers": customers, "totals": totals}


def _csv_text(header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Render reconcile output into the release bundle (release-spec.md).

    Exactly three files: orders.csv, customers.csv, summary.json.
    Amounts are integer text; row order follows reconcile ordering;
    summary.json is exactly result["totals"].
    """
    order_rows = [
        [
            o["order_id"],
            o["customer"],
            str(int(o["paid_cents"])),
            str(int(o["refund_cents"])),
            str(int(o["net_cents"])),
        ]
        for o in result["orders"]
    ]
    customer_rows = [
        [c["customer"], str(int(c["net_cents"]))] for c in result["customers"]
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
            order_rows,
        ),
        "customers.csv": _csv_text(["customer", "net_cents"], customer_rows),
        "summary.json": json.dumps(summary),
    }
