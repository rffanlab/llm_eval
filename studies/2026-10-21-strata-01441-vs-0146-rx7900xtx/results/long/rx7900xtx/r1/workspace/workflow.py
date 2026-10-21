"""Order reconciliation, spec-v1 and spec-v2 contracts.

Pure functions only: no file/network/process access, no dunder attributes.
Amounts are parsed with decimal fixed-point (never float*100).
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ORDERS_HEADER = ["order_id", "customer", "amount", "status", "created_at"]
REFUNDS_HEADER_V1 = ["refund_id", "order_id", "amount"]
REFUNDS_HEADER_V2 = ["refund_id", "order_id", "amount", "status",
                     "created_at"]


def _amount_to_cents(raw, max_decimals=2):
    """Parse a non-negative decimal string to integer cents.

    ROUND_HALF_UP to whole cents. Rejects negatives, NaN/Infinity,
    exponent notation and (when max_decimals is not None) too many decimals.
    """
    if not isinstance(raw, str):
        raise ValueError("amount must be a string")
    s = raw.strip()
    if not s:
        raise ValueError("amount must not be empty")
    for ch in s:
        if not (ch.isascii() and ch.isdigit()) and ch != ".":
            raise ValueError("invalid amount: %r" % raw)
    parts = s.split(".")
    if len(parts) > 2:
        raise ValueError("invalid amount: %r" % raw)
    if any(p == "" for p in parts):
        raise ValueError("invalid amount: %r" % raw)
    if max_decimals is not None and len(parts) == 2 \
            and len(parts[1]) > max_decimals:
        raise ValueError("amount has more than %d decimals: %r"
                         % (max_decimals, raw))
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % raw)
    if not d.is_finite() or d < 0:
        raise ValueError("amount must be finite and non-negative: %r" % raw)
    return int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _read_rows(csv_text, expected_header, kind):
    """Parse a CSV string into a list of dicts, validating the header."""
    if not isinstance(csv_text, str):
        raise ValueError("%s input must be a string" % kind)
    reader = csv.reader(io.StringIO(csv_text))
    rows = [r for r in reader if r != []]
    if not rows:
        raise ValueError("%s input missing header" % kind)
    header = rows[0]
    if header != expected_header:
        raise ValueError("%s header mismatch" % kind)
    out = []
    for r in rows[1:]:
        if len(r) != len(expected_header):
            raise ValueError("%s row has wrong field count: %r" % (kind, r))
        out.append(dict(zip(expected_header, r)))
    return out


def _validate_cutoff(cutoff):
    """Validate strict YYYY-MM-DDTHH:MM:SSZ and return it unchanged."""
    if not isinstance(cutoff, str):
        raise ValueError("cutoff must be a string")
    s = cutoff
    if len(s) != 20:
        raise ValueError("invalid cutoff: %r" % cutoff)
    digits = [0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18]
    for i in digits:
        if not (s[i].isascii() and s[i].isdigit()):
            raise ValueError("invalid cutoff: %r" % cutoff)
    if s[4] != "-" or s[7] != "-" or s[10] != "T":
        raise ValueError("invalid cutoff: %r" % cutoff)
    if s[13] != ":" or s[16] != ":" or s[19] != "Z":
        raise ValueError("invalid cutoff: %r" % cutoff)
    month = int(s[5:7])
    day = int(s[8:10])
    hour = int(s[11:13])
    minute = int(s[14:16])
    second = int(s[17:19])
    if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 23
            and minute <= 59 and second <= 60):
        raise ValueError("invalid cutoff: %r" % cutoff)
    return s


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v1":
        # cutoff is not part of the v1 contract; ignored.
        cutoff_value = None
        refunds_header = REFUNDS_HEADER_V1
        max_decimals = 2
    else:
        if cutoff is None:
            raise ValueError("cutoff is required for policy v2")
        cutoff_value = _validate_cutoff(cutoff)
        refunds_header = REFUNDS_HEADER_V2
        max_decimals = None

    order_rows = _read_rows(orders_csv, ORDERS_HEADER, "orders")
    refund_rows = _read_rows(refunds_csv, refunds_header, "refunds")

    # --- orders: dedupe by order_id -------------------------------------
    seen_orders = {}
    all_order_status = {}
    orders = {}
    for row in order_rows:
        oid = row["order_id"]
        if not oid:
            raise ValueError("order row with empty order_id")
        status = row["status"]
        if status not in ("paid", "cancelled"):
            raise ValueError("unknown order status: %r" % status)
        record = (row["customer"], row["amount"], status, row["created_at"])
        if oid in seen_orders:
            if seen_orders[oid] != record:
                raise ValueError(
                    "conflicting duplicate order_id: %r" % oid)
            continue
        seen_orders[oid] = record
        all_order_status[oid] = status
        if status != "paid":
            continue
        if policy == "v2" and row["created_at"] > cutoff_value:
            continue
        orders[oid] = {
            "customer": row["customer"],
            "paid_cents": _amount_to_cents(row["amount"], max_decimals),
            "refund_cents": 0,
        }

    # --- refunds: dedupe by refund_id ------------------------------------
    seen_refunds = {}
    refunds = {}
    for row in refund_rows:
        rid = row["refund_id"]
        if not rid:
            raise ValueError("refund row with empty refund_id")
        if policy == "v2":
            status = row["status"]
            if status not in ("succeeded", "pending"):
                raise ValueError("unknown refund status: %r" % status)
            record = (row["order_id"], row["amount"], status,
                      row["created_at"])
        else:
            record = (row["order_id"], row["amount"])
        if rid in seen_refunds:
            if seen_refunds[rid] != record:
                raise ValueError(
                    "conflicting duplicate refund_id: %r" % rid)
            continue
        seen_refunds[rid] = record
        refunds[rid] = record

    # --- apply refunds ----------------------------------------------------
    for rid, record in refunds.items():
        oid = record[0]
        amount = record[1]
        if policy == "v2":
            status = record[2]
            created_at = record[3]
            if status != "succeeded" or created_at > cutoff_value:
                # pending or after-cutoff refunds are not counted; but a
                # refund that *would* count must reference a live order.
                continue
        if oid not in all_order_status:
            raise ValueError(
                "refund %s references unknown order: %r" % (rid, oid))
        if all_order_status[oid] == "cancelled":
            raise ValueError(
                "refund %s references cancelled order: %r" % (rid, oid))
        if oid not in orders:
            # order exists and is paid but excluded by cutoff -> ignore
            continue
        cents = _amount_to_cents(amount, max_decimals)
        order = orders[oid]
        order["refund_cents"] += cents
        if order["refund_cents"] > order["paid_cents"]:
            raise ValueError(
                "refunds exceed paid amount for order: %r" % oid)

    # --- build result -----------------------------------------------------
    order_list = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for oid in sorted(orders):
        o = orders[oid]
        net = o["paid_cents"] - o["refund_cents"]
        order_list.append({
            "order_id": oid,
            "customer": o["customer"],
            "paid_cents": o["paid_cents"],
            "refund_cents": o["refund_cents"],
            "net_cents": net,
        })
        customer_net[o["customer"]] = \
            customer_net.get(o["customer"], 0) + net
        totals["paid_cents"] += o["paid_cents"]
        totals["refund_cents"] += o["refund_cents"]
        totals["net_cents"] += net

    customers = [
        {"customer": c, "net_cents": customer_net[c]}
        for c in sorted(customer_net)
    ]
    return {"orders": order_list, "customers": customers, "totals": totals}


def _csv_text(header, rows):
    """Render rows (list of lists) as CSV text with a standard writer."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Build the release bundle: exactly orders.csv, customers.csv,
    summary.json (dict[str, str])."""
    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            [o["order_id"], o["customer"], o["paid_cents"],
             o["refund_cents"], o["net_cents"]]
            for o in result["orders"]
        ],
    )
    customers_csv = _csv_text(
        ["customer", "net_cents"],
        [[c["customer"], c["net_cents"]] for c in result["customers"]],
    )
    summary_json = json.dumps(result["totals"], sort_keys=True)
    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
