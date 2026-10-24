"""Order reconciliation, v1 + v2 contracts.

reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None) -> dict
Pure functions only; inputs are UTF-8 CSV strings and are never modified.
All money handled as decimal fixed point, output integer cents.
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_FIELDS_V1 = ("order_id", "customer", "amount", "status")
_ORDER_FIELDS_V2 = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_FIELDS_V1 = ("refund_id", "order_id", "amount")
_REFUND_FIELDS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")


def _valid_timestamp(value):
    """Validate canonical UTC string YYYY-MM-DDTHH:MM:SSZ so that
    lexicographic comparison against cutoff is safe."""
    if len(value) != 20 or not value.endswith("Z"):
        return False
    ok = (value[4] == "-" and value[7] == "-" and value[10] == "T"
          and value[13] == ":" and value[16] == ":")
    if not ok:
        return False
    parts = (value[0:4], value[5:7], value[8:10],
             value[11:13], value[14:16], value[17:19])
    if not all(p.isdigit() for p in parts):
        return False
    year, month, day, hour, minute, second = (int(p) for p in parts)
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return False
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    return year >= 1


def _parse_cents(raw, what, policy):
    """Parse an amount into integer cents.

    v1: non-negative, at most two decimals.
    v2: non-negative, any number of decimals, ROUND_HALF_UP to cents.
    """
    if raw is None:
        raise ValueError(f"{what}: missing amount")
    text = raw.strip()
    if not text:
        raise ValueError(f"{what}: empty amount")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{what}: invalid amount {raw!r}")
    if not value.is_finite():
        raise ValueError(f"{what}: non-finite amount {raw!r}")
    if value < 0:
        raise ValueError(f"{what}: negative amount {raw!r}")
    if policy == "v1":
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -2:
            raise ValueError(f"{what}: more than two decimals in {raw!r}")
        return int(value * 100)
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _read_rows(csv_text, required, name):
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        raise ValueError(f"{name}: missing header")
    missing = [c for c in required if c not in reader.fieldnames]
    if missing:
        raise ValueError(f"{name}: missing columns {missing}")
    for row in reader:
        if all(v is None or v == "" for v in row.values()):
            continue
        yield row


def _dedupe(rows, key_field, name):
    """Return unique rows keyed by key_field.

    Exact duplicate rows collapse to one; same key with any differing
    field raises ValueError. Runs over every row (including pending or
    after-cutoff rows) so conflicts are always detected.
    """
    seen = {}
    unique = []
    for row in rows:
        key = (row.get(key_field) or "").strip()
        if not key:
            raise ValueError(f"{name}: missing {key_field}")
        signature = tuple((field, (row.get(field) or "").strip())
                          for field in sorted(row.keys() - {None}))
        if key in seen:
            if seen[key] != signature:
                raise ValueError(
                    f"{name}: conflicting rows for {key_field}={key!r}")
            continue
        seen[key] = signature
        unique.append(row)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError(f"unsupported policy {policy!r}")
    if policy == "v2":
        if not cutoff or not _valid_timestamp(str(cutoff)):
            raise ValueError(
                "v2 requires cutoff in YYYY-MM-DDTHH:MM:SSZ format")

    order_fields = _ORDER_FIELDS_V1 if policy == "v1" else _ORDER_FIELDS_V2
    refund_fields = _REFUND_FIELDS_V1 if policy == "v1" else _REFUND_FIELDS_V2
    orders = _dedupe(
        _read_rows(orders_csv, order_fields, "orders"), "order_id", "orders")
    refunds = _dedupe(
        _read_rows(refunds_csv, refund_fields, "refunds"),
        "refund_id", "refunds")

    paid = {}        # order_id -> {"customer", "paid_cents", "refund_cents"}
    cancelled = set()  # orders with status != paid
    cutoff_out = set()  # paid orders excluded by cutoff (v2 only)
    for row in orders:
        order_id = (row["order_id"] or "").strip()
        status = (row["status"] or "").strip().lower()
        paid_cents = _parse_cents(row["amount"], f"order {order_id}", policy)
        if order_id in paid or order_id in cancelled or order_id in cutoff_out:
            continue
        if status != "paid":
            cancelled.add(order_id)
            continue
        if policy == "v2":
            created_at = (row.get("created_at") or "").strip()
            if not created_at:
                raise ValueError(f"order {order_id}: missing created_at")
            if created_at > cutoff:
                cutoff_out.add(order_id)
                continue
        paid[order_id] = {
            "customer": (row["customer"] or "").strip(),
            "paid_cents": paid_cents,
            "refund_cents": 0,
        }

    for row in refunds:
        refund_id = (row["refund_id"] or "").strip()
        order_id = (row["order_id"] or "").strip()
        refund_cents = _parse_cents(row["amount"], f"refund {refund_id}", policy)
        if policy == "v2":
            status = (row.get("status") or "").strip().lower()
            if status not in ("succeeded", "pending"):
                raise ValueError(f"refund {refund_id}: invalid status")
            created_at = (row.get("created_at") or "").strip()
            if not created_at:
                raise ValueError(f"refund {refund_id}: missing created_at")
            if status == "pending" or created_at > cutoff:
                continue  # not effective; order existence not checked
        if order_id not in paid:
            if order_id in cutoff_out:
                # order exists but excluded by cutoff -> ignore refund
                continue
            # truly unknown order, or cancelled order (both policies error)
            raise ValueError(
                f"refund {refund_id}: order {order_id!r} is not paid")
        entry = paid[order_id]
        if entry["refund_cents"] + refund_cents > entry["paid_cents"]:
            raise ValueError(
                f"refund {refund_id}: cumulative refunds exceed paid for "
                f"order {order_id!r}")
        entry["refund_cents"] += refund_cents

    order_rows = []
    customers = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(paid):
        entry = paid[order_id]
        net = entry["paid_cents"] - entry["refund_cents"]
        order_rows.append({
            "order_id": order_id,
            "customer": entry["customer"],
            "paid_cents": entry["paid_cents"],
            "refund_cents": entry["refund_cents"],
            "net_cents": net,
        })
        customers[entry["customer"]] = customers.get(entry["customer"], 0) + net
        totals["paid_cents"] += entry["paid_cents"]
        totals["refund_cents"] += entry["refund_cents"]
        totals["net_cents"] += net

    return {
        "orders": order_rows,
        "customers": [
            {"customer": name, "net_cents": customers[name]}
            for name in sorted(customers)
        ],
        "totals": totals,
    }


def _csv_text(header, rows):
    """Render rows with the standard csv writer; amounts as integer text."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """Build the release bundle: exactly three files.

    orders.csv / customers.csv follow reconcile ordering with integer
    amounts; summary.json parses to exactly result["totals"].
    """
    order_rows = [
        [o["order_id"], o["customer"],
         str(o["paid_cents"]), str(o["refund_cents"]), str(o["net_cents"])]
        for o in result["orders"]
    ]
    customer_rows = [
        [c["customer"], str(c["net_cents"])]
        for c in result["customers"]
    ]
    totals = result["totals"]
    summary = {
        "paid_cents": int(totals["paid_cents"]),
        "refund_cents": int(totals["refund_cents"]),
        "net_cents": int(totals["net_cents"]),
    }
    return {
        "orders.csv": _csv_text(
            ("order_id", "customer", "paid_cents", "refund_cents", "net_cents"),
            order_rows),
        "customers.csv": _csv_text(("customer", "net_cents"), customer_rows),
        "summary.json": json.dumps(summary, sort_keys=True),
    }
