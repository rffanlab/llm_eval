"""Order reconciliation, v1 + v2 contracts (see spec-v1.md, spec-v2.md).

Pure functions only: no file/network/process access. Inputs are UTF-8 CSV
strings; monetary outputs are integer cents computed with decimal fixed
point (never float * 100).
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _parse_amount_cents_v1(raw, kind):
    """Parse a non-negative amount with at most 2 decimals to cents (v1)."""
    if raw is None:
        raise ValueError("%s: missing amount" % kind)
    s = raw.strip()
    if s == "":
        raise ValueError("%s: empty amount" % kind)
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        raise ValueError("%s: invalid amount %r" % (kind, raw))
    if d.is_nan() or d.is_infinite():
        raise ValueError("%s: NaN/Infinity amount %r" % (kind, raw))
    if d < 0:
        raise ValueError("%s: negative amount %r" % (kind, raw))
    exponent = d.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2:
        raise ValueError("%s: more than 2 decimals in %r" % (kind, raw))
    cents = d * Decimal(100)
    if cents != cents.to_integral_value():
        raise ValueError("%s: cannot convert to integer cents: %r" % (kind, raw))
    return int(cents)


def _parse_amount_cents_v2(raw, kind):
    """Parse a non-negative amount, any decimals, ROUND_HALF_UP to cents (v2)."""
    if raw is None:
        raise ValueError("%s: missing amount" % kind)
    s = raw.strip()
    if s == "":
        raise ValueError("%s: empty amount" % kind)
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        raise ValueError("%s: invalid amount %r" % (kind, raw))
    if d.is_nan() or d.is_infinite():
        raise ValueError("%s: NaN/Infinity amount %r" % (kind, raw))
    if d < 0:
        raise ValueError("%s: negative amount %r" % (kind, raw))
    cents = (d * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _read_rows(csv_text, kind):
    """Read CSV text into (fieldnames, row dicts). Empty text -> ([], [])."""
    if csv_text is None:
        return [], []
    text = csv_text
    if text.startswith("\ufeff"):
        text = text[1:]
    if text.strip() == "":
        return [], []
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fieldnames = reader.fieldnames
    if fieldnames is None:
        return [], []
    rows = []
    for row in reader:
        if row is None:
            continue
        values = list(row.values())
        if not values or all(v in (None, "") for v in values):
            continue
        rows.append(row)
    return fieldnames, rows


def _normalize_row(row, fieldnames):
    return tuple((row.get(f) or "") for f in fieldnames)


def _validate_cutoff(cutoff):
    if not isinstance(cutoff, str):
        raise ValueError("cutoff must be a string YYYY-MM-DDTHH:MM:SSZ")
    s = cutoff
    expected_len = len("YYYY-MM-DDTHH:MM:SSZ")
    ok = (
        len(s) == expected_len
        and s[4] == "-" and s[7] == "-" and s[10] == "T"
        and s[13] == ":" and s[16] == ":" and s[19] == "Z"
        and s[0:4].isdigit() and s[5:7].isdigit() and s[8:10].isdigit()
        and s[11:13].isdigit() and s[14:16].isdigit() and s[17:19].isdigit()
    )
    if not ok:
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ, got %r" % (cutoff,))
    month, day = int(s[5:7]), int(s[8:10])
    hour, minute, second = int(s[11:13]), int(s[14:16]), int(s[17:19])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError("cutoff has invalid date: %r" % (cutoff,))
    if not (hour <= 23 and minute <= 59 and second <= 59):
        raise ValueError("cutoff has invalid time: %r" % (cutoff,))
    return s


def _validate_timestamp(value, kind):
    if not isinstance(value, str) or len(value) != 20 or value[10] != "T" or value[19] != "Z":
        raise ValueError("%s: invalid timestamp %r" % (kind, value))
    digits = value[0:4] + value[5:7] + value[8:10] + value[11:13] + value[14:16] + value[17:19]
    if not digits.isdigit():
        raise ValueError("%s: invalid timestamp %r" % (kind, value))
    return value


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v1":
        if cutoff is not None:
            raise ValueError("cutoff is not supported by the v1 policy")
        parse_amount = _parse_amount_cents_v1
    else:
        if cutoff is None:
            raise ValueError("v2 policy requires a cutoff")
        cutoff = _validate_cutoff(cutoff)
        parse_amount = _parse_amount_cents_v2

    # ---- orders ----
    order_fields, order_rows = _read_rows(orders_csv, "orders")
    required_order_fields = ["order_id", "customer", "amount", "status", "created_at"]
    if order_fields and set(required_order_fields) - set(order_fields):
        raise ValueError("orders CSV missing required columns")

    orders = {}           # order_id -> dict
    seen_order_rows = {}  # order_id -> normalized row tuple
    for row in order_rows:
        order_id = (row.get("order_id") or "").strip()
        if order_id == "":
            raise ValueError("orders: empty order_id")
        key = _normalize_row(row, order_fields)
        if order_id in seen_order_rows:
            if seen_order_rows[order_id] == key:
                continue  # exact duplicate row: count once
            raise ValueError("orders: duplicate order_id %s with differing fields" % order_id)
        seen_order_rows[order_id] = key
        status = (row.get("status") or "").strip().lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("orders: unknown status %r for %s" % (status, order_id))
        paid_cents = parse_amount(row.get("amount"), "order %s amount" % order_id)
        created_at = (row.get("created_at") or "").strip()
        if policy == "v2":
            _validate_timestamp(created_at, "order %s created_at" % order_id)
        orders[order_id] = {
            "order_id": order_id,
            "customer": (row.get("customer") or "").strip(),
            "paid_cents": paid_cents,
            "status": status,
            "created_at": created_at,
        }

    def order_included(order):
        if order["status"] != "paid":
            return False
        if policy == "v2" and order["created_at"] > cutoff:
            return False  # lexicographic compare on canonical UTC strings
        return True

    # ---- refunds ----
    refund_fields, refund_rows = _read_rows(refunds_csv, "refunds")
    required_refund_fields = ["refund_id", "order_id", "amount"]
    if policy == "v2":
        required_refund_fields = required_refund_fields + ["status", "created_at"]
    if refund_fields and set(required_refund_fields) - set(refund_fields):
        raise ValueError("refunds CSV missing required columns")

    refund_cents_by_order = {oid: 0 for oid in orders}
    seen_refund_rows = {}
    for row in refund_rows:
        refund_id = (row.get("refund_id") or "").strip()
        if refund_id == "":
            raise ValueError("refunds: empty refund_id")
        # Dedup/conflict detection covers ALL rows, including pending/late ones.
        key = _normalize_row(row, refund_fields)
        if refund_id in seen_refund_rows:
            if seen_refund_rows[refund_id] == key:
                continue  # exact duplicate row: count once
            raise ValueError("refunds: duplicate refund_id %s with differing fields" % refund_id)
        seen_refund_rows[refund_id] = key

        order_id = (row.get("order_id") or "").strip()
        order = orders.get(order_id)
        if order is None:
            raise ValueError("refunds: refund %s references unknown order %s" % (refund_id, order_id))
        if order["status"] != "paid":
            raise ValueError("refunds: refund %s references cancelled order %s" % (refund_id, order_id))

        if policy == "v2":
            status = (row.get("status") or "").strip().lower()
            if status not in ("succeeded", "pending"):
                raise ValueError("refunds: unknown status %r for %s" % (status, refund_id))
            created_at = (row.get("created_at") or "").strip()
            _validate_timestamp(created_at, "refund %s created_at" % refund_id)
            if status == "pending":
                continue  # not counted
            if created_at > cutoff:
                continue  # after cutoff: not counted
            if order["created_at"] > cutoff:
                continue  # target order excluded by cutoff: ignore
        amount_cents = parse_amount(row.get("amount"), "refund %s amount" % refund_id)
        refund_cents_by_order[order_id] += amount_cents
        if refund_cents_by_order[order_id] > order["paid_cents"]:
            raise ValueError("refunds: cumulative refunds exceed paid amount for order %s" % order_id)

    # ---- results ----
    order_entries = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(orders):
        order = orders[order_id]
        if not order_included(order):
            continue  # cancelled / after-cutoff orders are excluded
        paid = order["paid_cents"]
        refunded = refund_cents_by_order[order_id]
        net = paid - refunded
        order_entries.append({
            "order_id": order_id,
            "customer": order["customer"],
            "paid_cents": paid,
            "refund_cents": refunded,
            "net_cents": net,
        })
        customer_net[order["customer"]] = customer_net.get(order["customer"], 0) + net
        totals["paid_cents"] += paid
        totals["refund_cents"] += refunded
        totals["net_cents"] += net

    customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]

    return {
        "orders": order_entries,
        "customers": customers,
        "totals": totals,
    }


def _csv_text(header, rows):
    """Render rows with the standard csv writer (CRLF line endings)."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Build the release bundle per release-spec.md.

    Returns dict[str, str] with exactly three files:
      orders.csv    - header order_id,customer,paid_cents,refund_cents,net_cents
      customers.csv - header customer,net_cents
      summary.json  - parses to exactly result["totals"]
    Row order follows reconcile ordering; amounts are integer text.
    """
    order_rows = [
        [
            entry["order_id"],
            entry["customer"],
            str(int(entry["paid_cents"])),
            str(int(entry["refund_cents"])),
            str(int(entry["net_cents"])),
        ]
        for entry in result["orders"]
    ]
    customer_rows = [
        [entry["customer"], str(int(entry["net_cents"]))]
        for entry in result["customers"]
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
        "summary.json": json.dumps(summary, sort_keys=True),
    }
