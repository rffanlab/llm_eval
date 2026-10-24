"""Order reconciliation pipeline (v1 + v2 contract, see spec-v1.md / spec-v2.md)."""

import csv
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_FIELDS = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_FIELDS_V1 = ("refund_id", "order_id", "amount")
_REFUND_FIELDS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")


def _validate_cutoff(cutoff):
    """Strict canonical UTC format YYYY-MM-DDTHH:MM:SSZ."""
    if not isinstance(cutoff, str) or len(cutoff) != 20:
        raise ValueError("invalid cutoff: %r" % (cutoff,))
    digits_ok = (
        cutoff[0:4].isdigit()
        and cutoff[5:7].isdigit()
        and cutoff[8:10].isdigit()
        and cutoff[11:13].isdigit()
        and cutoff[14:16].isdigit()
        and cutoff[17:19].isdigit()
    )
    shape_ok = (
        cutoff[4] == "-"
        and cutoff[7] == "-"
        and cutoff[10] == "T"
        and cutoff[13] == ":"
        and cutoff[16] == ":"
        and cutoff[19] == "Z"
    )
    if not digits_ok or not shape_ok:
        raise ValueError("invalid cutoff: %r" % (cutoff,))
    try:
        datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("invalid cutoff: %r" % (cutoff,))
    return cutoff


def _parse_amount_cents(raw, policy):
    """Parse a non-negative amount to integer cents.

    v1: at most 2 decimals, exact cents.
    v2: any number of decimals, ROUND_HALF_UP to cents.
    Both reject negatives, NaN/Infinity and malformed text. Decimal only,
    never float.
    """
    if not isinstance(raw, str):
        raise ValueError("invalid amount: %r" % (raw,))
    text = raw.strip()
    if not text:
        raise ValueError("invalid amount: %r" % (raw,))
    # Manual validation: digits with optional . and digits after; this also
    # rejects NaN/Infinity and any sign characters.
    int_part, dot, frac_part = text.partition(".")
    if not int_part.isdigit():
        raise ValueError("invalid amount: %r" % (raw,))
    if dot and not frac_part.isdigit():
        raise ValueError("invalid amount: %r" % (raw,))
    if policy == "v1" and dot and len(frac_part) > 2:
        raise ValueError("amount has more than 2 decimals: %r" % (raw,))
    try:
        dec = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % (raw,))
    if not (dec >= 0):
        raise ValueError("invalid amount: %r" % (raw,))
    if policy == "v1":
        cents = dec * 100
        if cents != cents.to_integral_value():
            raise ValueError("amount not expressible in cents: %r" % (raw,))
        return int(cents.to_integral_value())
    cents = (dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _read_rows(csv_text, expected_fields, kind):
    if csv_text is None:
        raise ValueError("%s csv is None" % kind)
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        return []
    missing = [f for f in expected_fields if f not in reader.fieldnames]
    if missing:
        raise ValueError("%s csv missing columns: %s" % (kind, missing))
    rows = []
    for row in reader:
        if all(v is None or v == "" for v in row.values()):
            continue  # skip blank lines
        rows.append({f: (row[f] if row[f] is not None else "") for f in expected_fields})
    return rows


def _dedupe(rows, id_field, kind):
    """Exact duplicates collapse; same id with differing fields -> ValueError.

    Applied before any filtering so pending/late rows still conflict-check.
    """
    by_id = {}
    unique = []
    for row in rows:
        key = row[id_field]
        if key in by_id:
            if by_id[key] != row:
                raise ValueError(
                    "conflicting duplicate %s id: %s" % (kind, key)
                )
            continue  # exact duplicate counted once
        by_id[key] = dict(row)
        unique.append(row)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v2":
        if cutoff is None:
            raise ValueError("cutoff is required for policy v2")
        _validate_cutoff(cutoff)

    order_rows = _dedupe(
        _read_rows(orders_csv, _ORDER_FIELDS, "orders"), "order_id", "order"
    )
    refund_fields = _REFUND_FIELDS_V1 if policy == "v1" else _REFUND_FIELDS_V2
    refund_rows = _dedupe(
        _read_rows(refunds_csv, refund_fields, "refunds"), "refund_id", "refund"
    )

    orders = {}
    for row in order_rows:
        order_id = row["order_id"]
        status = row["status"]
        if status not in ("paid", "cancelled"):
            raise ValueError("unknown order status: %r" % (status,))
        orders[order_id] = {
            "order_id": order_id,
            "customer": row["customer"],
            "status": status,
            "created_at": row["created_at"],
            "paid_cents": _parse_amount_cents(row["amount"], policy),
            "refund_cents": 0,
        }

    def order_included(order):
        if order["status"] != "paid":
            return False
        if policy == "v2" and order["created_at"] > cutoff:
            return False
        return True

    for row in refund_rows:
        order_id = row["order_id"]
        if policy == "v2":
            status = row["status"]
            if status not in ("succeeded", "pending"):
                raise ValueError("unknown refund status: %r" % (status,))
            if status != "succeeded" or row["created_at"] > cutoff:
                continue  # pending or after-cutoff refunds are not counted
        order = orders.get(order_id)
        if order is None:
            raise ValueError("refund for unknown order: %s" % (order_id,))
        if order["status"] != "paid":
            raise ValueError("refund for cancelled order: %s" % (order_id,))
        if not order_included(order):
            # order exists but excluded by cutoff: ignore the refund
            continue
        order["refund_cents"] += _parse_amount_cents(row["amount"], policy)
        if order["refund_cents"] > order["paid_cents"]:
            raise ValueError(
                "refund exceeds paid amount for order: %s" % (order_id,)
            )

    result_orders = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order in orders.values():
        if not order_included(order):
            continue
        net = order["paid_cents"] - order["refund_cents"]
        result_orders.append(
            {
                "order_id": order["order_id"],
                "customer": order["customer"],
                "paid_cents": order["paid_cents"],
                "refund_cents": order["refund_cents"],
                "net_cents": net,
            }
        )
        customer_net[order["customer"]] = customer_net.get(order["customer"], 0) + net
        totals["paid_cents"] += order["paid_cents"]
        totals["refund_cents"] += order["refund_cents"]
        totals["net_cents"] += net

    result_orders.sort(key=lambda o: o["order_id"])
    customers = [
        {"customer": name, "net_cents": net}
        for name, net in sorted(customer_net.items(), key=lambda kv: kv[0])
    ]
    return {"orders": result_orders, "customers": customers, "totals": totals}


def export_bundle(result):
    """Render reconcile output into the release bundle (release-spec.md).

    Exactly three files: orders.csv, customers.csv, summary.json.
    Row order follows reconcile ordering; amounts are integer text;
    summary.json parses to exactly result["totals"].
    """
    if not isinstance(result, dict) or "orders" not in result or "customers" not in result or "totals" not in result:
        raise ValueError("result must be a reconcile output dict")

    orders_buf = io.StringIO()
    writer = csv.writer(orders_buf, lineterminator="\n")
    writer.writerow(["order_id", "customer", "paid_cents", "refund_cents", "net_cents"])
    for row in result["orders"]:
        writer.writerow(
            [
                row["order_id"],
                row["customer"],
                "%d" % row["paid_cents"],
                "%d" % row["refund_cents"],
                "%d" % row["net_cents"],
            ]
        )

    customers_buf = io.StringIO()
    writer = csv.writer(customers_buf, lineterminator="\n")
    writer.writerow(["customer", "net_cents"])
    for row in result["customers"]:
        writer.writerow([row["customer"], "%d" % row["net_cents"]])

    summary = json.dumps(result["totals"], sort_keys=True)

    return {
        "orders.csv": orders_buf.getvalue(),
        "customers.csv": customers_buf.getvalue(),
        "summary.json": summary,
    }
