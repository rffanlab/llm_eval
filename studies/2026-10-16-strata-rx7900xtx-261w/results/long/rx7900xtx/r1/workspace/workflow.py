"""Order reconciliation, spec-v1 + spec-v2 contract.

reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None) -> dict
Pure function: parses CSV strings, no file/network/process access.
Fixed-point decimal money; outputs integer cents.

v1: <=2-decimal amounts, refunds without status, no cutoff.
v2: cutoff required (YYYY-MM-DDTHH:MM:SSZ), refunds carry status/created_at,
    amounts may have many decimals and are rounded ROUND_HALF_UP to cents,
    per-row rounding before aggregation. Only paid orders with
    created_at<=cutoff count; only succeeded refunds with created_at<=cutoff
    count. Duplicate-id conflicts are rejected regardless of filtering.

export_bundle(result) -> dict[str, str] with exactly orders.csv,
customers.csv and summary.json per release-spec.md.
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _parse_amount_cents(raw, context, max_places=2):
    """Parse a non-negative amount into integer cents.

    max_places=2 (v1) rejects more than two decimals; max_places=None (v2)
    allows any number of decimals and rounds ROUND_HALF_UP.
    Rejects NaN, Infinity and negatives. Uses Decimal, never float * 100.
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
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        if max_places is not None and exponent < -max_places:
            raise ValueError(
                "%s: more than %d decimals %r" % (context, max_places, raw)
            )
        cents = value.scaleb(2).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    else:
        cents = value.scaleb(2).to_integral_value()
    return int(cents)


def _validate_cutoff(cutoff):
    if not isinstance(cutoff, str) or len(cutoff) != 20:
        raise ValueError("cutoff: expected YYYY-MM-DDTHH:MM:SSZ, got %r" % (cutoff,))
    if (
        cutoff[4] != "-"
        or cutoff[7] != "-"
        or cutoff[10] != "T"
        or cutoff[13] != ":"
        or cutoff[16] != ":"
        or cutoff[19] != "Z"
    ):
        raise ValueError("cutoff: expected YYYY-MM-DDTHH:MM:SSZ, got %r" % (cutoff,))
    digits = (cutoff[0:4], cutoff[5:7], cutoff[8:10],
              cutoff[11:13], cutoff[14:16], cutoff[17:19])
    if not all(part.isdigit() for part in digits):
        raise ValueError("cutoff: expected YYYY-MM-DDTHH:MM:SSZ, got %r" % (cutoff,))
    year, month, day, hour, minute, second = (int(p) for p in digits)
    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError("cutoff: invalid date %r" % (cutoff,))
    if not (hour <= 23 and minute <= 59 and second <= 60):
        raise ValueError("cutoff: invalid time %r" % (cutoff,))
    return cutoff


def _read_rows(csv_text, required_header, name):
    """Read a CSV string into a list of dict rows, validating the header."""
    if csv_text is None:
        raise ValueError("%s: input must be a string" % name)
    reader = csv.reader(io.StringIO(csv_text), strict=True)
    rows = []
    for row in reader:
        if not row or (len(row) == 1 and row[0].strip() == ""):
            continue  # ignore blank lines
        rows.append(row)
    if not rows:
        raise ValueError("%s: missing header" % name)
    header = [h.strip() for h in rows[0]]
    if header != required_header:
        raise ValueError(
            "%s: bad header %r, expected %r" % (name, header, required_header)
        )
    out = []
    for row in rows[1:]:
        if len(row) != len(header):
            raise ValueError("%s: ragged row %r" % (name, row))
        out.append({header[i]: row[i].strip() for i in range(len(header))})
    return out


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v2":
        if cutoff is None:
            raise ValueError("policy v2 requires cutoff")
        cutoff = _validate_cutoff(cutoff)

    order_fields = ["order_id", "customer", "amount", "status", "created_at"]
    if policy == "v1":
        refund_fields = ["refund_id", "order_id", "amount"]
    else:
        refund_fields = ["refund_id", "order_id", "amount", "status", "created_at"]

    order_rows = _read_rows(orders_csv, order_fields, "orders")
    refund_rows = _read_rows(refunds_csv, refund_fields, "refunds")

    max_places = 2 if policy == "v1" else None

    # --- Orders: dedupe by order_id (identical rows collapse, conflicts fail)
    orders = {}  # order_id -> dict
    for row in order_rows:
        oid = row["order_id"]
        if oid == "":
            raise ValueError("orders: empty order_id")
        status = row["status"].lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("orders: unknown status %r" % row["status"])
        paid_cents = _parse_amount_cents(row["amount"], "order %s" % oid, max_places)
        signature = (row["customer"], row["amount"], status, row["created_at"])
        if oid in orders:
            if orders[oid]["signature"] != signature:
                raise ValueError(
                    "orders: duplicate order_id %s with conflicting fields" % oid
                )
            continue  # exact duplicate row, count once
        orders[oid] = {
            "customer": row["customer"],
            "status": status,
            "paid_cents": paid_cents,
            "created_at": row["created_at"],
            "signature": signature,
        }

    # --- Refunds: dedupe by refund_id (conflicts rejected even for rows
    #     excluded by status/cutoff), then validate and count.
    refunds = {}  # refund_id -> signature
    refund_cents_by_order = {}  # order_id -> accumulated cents
    for row in refund_rows:
        rid = row["refund_id"]
        if rid == "":
            raise ValueError("refunds: empty refund_id")
        if policy == "v1":
            signature = (row["order_id"], row["amount"])
            status = "succeeded"  # v1 refunds are all valid
            created_at = None
        else:
            status = row["status"]
            created_at = row["created_at"]
            if status not in ("succeeded", "pending"):
                raise ValueError("refunds: unknown status %r" % row["status"])
            signature = (row["order_id"], row["amount"], status, created_at)
        if rid in refunds:
            if refunds[rid] != signature:
                raise ValueError(
                    "refunds: duplicate refund_id %s with conflicting fields" % rid
                )
            continue  # exact duplicate row, count once
        refunds[rid] = signature

        # Ineffective refunds (pending or after cutoff) are ignored entirely.
        effective = status == "succeeded"
        if policy == "v2" and created_at > cutoff:
            effective = False
        if not effective:
            continue

        oid = row["order_id"]
        if oid not in orders:
            raise ValueError("refunds: refund %s targets unknown order %s" % (rid, oid))
        if orders[oid]["status"] != "paid":
            raise ValueError(
                "refunds: refund %s targets cancelled order %s" % (rid, oid)
            )
        if policy == "v2" and orders[oid]["created_at"] > cutoff:
            # Order exists but is excluded by cutoff: ignore the refund too.
            continue
        amount_cents = _parse_amount_cents(
            row["amount"], "refund %s" % rid, max_places
        )
        refund_cents_by_order[oid] = (
            refund_cents_by_order.get(oid, 0) + amount_cents
        )

    for oid, total in refund_cents_by_order.items():
        if total > orders[oid]["paid_cents"]:
            raise ValueError(
                "refunds: order %s refunded %d cents exceeds paid %d cents"
                % (oid, total, orders[oid]["paid_cents"])
            )

    # --- Build result for paid orders within cutoff only.
    result_orders = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for oid in sorted(orders):
        info = orders[oid]
        if info["status"] != "paid":
            continue
        if policy == "v2" and info["created_at"] > cutoff:
            continue
        paid = info["paid_cents"]
        refunded = refund_cents_by_order.get(oid, 0)
        net = paid - refunded
        result_orders.append(
            {
                "order_id": oid,
                "customer": info["customer"],
                "paid_cents": paid,
                "refund_cents": refunded,
                "net_cents": net,
            }
        )
        customer_net[info["customer"]] = customer_net.get(info["customer"], 0) + net
        totals["paid_cents"] += paid
        totals["refund_cents"] += refunded
        totals["net_cents"] += net

    customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]
    return {"orders": result_orders, "customers": customers, "totals": totals}


def export_bundle(result):
    """Render the reconcile result into the release bundle files.

    Returns exactly three files: orders.csv, customers.csv, summary.json.
    Row order follows the reconcile ordering; amounts are integer text;
    summary.json parses back to result["totals"].
    """
    def _csv_text(header, rows):
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
        return buf.getvalue()

    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            [
                o["order_id"],
                o["customer"],
                "%d" % o["paid_cents"],
                "%d" % o["refund_cents"],
                "%d" % o["net_cents"],
            ]
            for o in result["orders"]
        ],
    )
    customers_csv = _csv_text(
        ["customer", "net_cents"],
        [[c["customer"], "%d" % c["net_cents"]] for c in result["customers"]],
    )
    summary_json = json.dumps(result["totals"], sort_keys=True)
    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
