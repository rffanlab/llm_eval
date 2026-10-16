"""Order reconciliation - v1 & v2 contracts (spec-v1.md, spec-v2.md).

Pure functions only: parses CSV strings, returns dict with integer cents.
export_bundle implements the release contract (release-spec.md).
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


ORDER_FIELDS = ["order_id", "customer", "amount", "status", "created_at"]
REFUND_FIELDS_V1 = ["refund_id", "order_id", "amount"]
REFUND_FIELDS_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]


def _parse_cents(raw, what, policy):
    """Parse a decimal amount string to integer cents (fixed-point, no float).

    v1: at most two decimals (legacy limit).
    v2: any number of decimals, rounded HALF_UP to integer cents
        (scale by 100 first, then round each line individually).
    Both: reject empty/NaN/Infinity/negative.
    """
    if raw is None:
        raise ValueError("%s: missing amount" % what)
    s = raw.strip()
    if s == "":
        raise ValueError("%s: empty amount" % what)
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (what, raw))
    if not d.is_finite():
        raise ValueError("%s: non-finite amount %r" % (what, raw))
    if d < 0:
        raise ValueError("%s: negative amount %r" % (what, raw))
    if policy == "v1":
        sign, digits, exponent = d.as_tuple()
        if exponent < -2:
            raise ValueError("%s: more than two decimals %r" % (what, raw))
        return int(d.scaleb(2).to_integral_value())
    return int(d.scaleb(2).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _is_valid_ts(value):
    """Check canonical UTC timestamp YYYY-MM-DDTHH:MM:SSZ."""
    if not isinstance(value, str) or len(value) != 20:
        return False
    if (value[4] != "-" or value[7] != "-" or value[10] != "T"
            or value[13] != ":" or value[16] != ":" or value[19] != "Z"):
        return False
    positions = [0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18]
    return all(value[i].isdigit() for i in positions)


def _read_rows(csv_text, expected_fields, name):
    """Return list of dict rows; validate header. Empty input -> []."""
    if csv_text is None:
        raise ValueError("%s: input must be a string" % name)
    text = csv_text
    if text.strip() == "":
        return []
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return []
    header = [h.strip() for h in header]
    if header != expected_fields:
        raise ValueError(
            "%s: bad header %r, expected %r" % (name, header, expected_fields)
        )
    rows = []
    for row in reader:
        if len(row) == 1 and (row[0] is None or row[0].strip() == ""):
            continue  # skip blank lines
        if len(row) != len(expected_fields):
            raise ValueError("%s: bad row width %r" % (name, row))
        rows.append(dict(zip(expected_fields, row)))
    return rows


def _dedupe(rows, id_field, name):
    """Exact duplicates collapse; same id with different fields -> ValueError.

    Runs before any filtering, so conflicts on pending/after-cutoff rows
    are still rejected.
    """
    seen = {}
    unique = []
    for row in rows:
        key = row[id_field].strip()
        if key == "":
            raise ValueError("%s: empty %s" % (name, id_field))
        fingerprint = tuple(sorted(row.items()))
        if key in seen:
            if seen[key] != fingerprint:
                raise ValueError(
                    "%s: conflicting rows for %s %r" % (name, id_field, key)
                )
            continue
        seen[key] = fingerprint
        unique.append(row)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v2" and cutoff is None:
        raise ValueError("v2 requires a cutoff")
    if policy == "v2" and not _is_valid_ts(cutoff):
        raise ValueError("invalid cutoff %r" % (cutoff,))
    # cutoff is not part of the v1 contract; ignored for v1.

    refund_fields = REFUND_FIELDS_V2 if policy == "v2" else REFUND_FIELDS_V1
    order_rows = _dedupe(
        _read_rows(orders_csv, ORDER_FIELDS, "orders"), "order_id", "orders"
    )
    refund_rows = _dedupe(
        _read_rows(refunds_csv, refund_fields, "refunds"), "refund_id", "refunds"
    )

    orders = {}  # order_id -> record (all statuses, for refund validation)
    for row in order_rows:
        order_id = row["order_id"].strip()
        status = row["status"].strip().lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("orders: unknown status %r" % row["status"])
        created_at = row["created_at"].strip()
        if policy == "v2" and not _is_valid_ts(created_at):
            raise ValueError(
                "orders: invalid created_at %r for %s" % (row["created_at"], order_id)
            )
        cents = _parse_cents(row["amount"], "order %s" % order_id, policy)
        orders[order_id] = {
            "order_id": order_id,
            "customer": row["customer"],
            "status": status,
            "created_at": created_at,
            "paid_cents": cents,
            "refund_cents": 0,
        }

    for row in refund_rows:
        refund_id = row["refund_id"].strip()
        order_id = row["order_id"].strip()
        if policy == "v2":
            status = row["status"].strip().lower()
            if status not in ("succeeded", "pending"):
                raise ValueError("refunds: unknown status %r" % row["status"])
            created_at = row["created_at"].strip()
            if not _is_valid_ts(created_at):
                raise ValueError(
                    "refunds: invalid created_at %r for %s"
                    % (row["created_at"], refund_id)
                )
            # pending or after-cutoff refunds are ignored entirely, even if
            # they reference unknown/cancelled orders.
            if status != "succeeded" or created_at > cutoff:
                continue
        cents = _parse_cents(row["amount"], "refund %s" % refund_id, policy)
        order = orders.get(order_id)
        if order is None:
            raise ValueError(
                "refunds: %s references unknown order %r" % (refund_id, order_id)
            )
        if order["status"] != "paid":
            raise ValueError(
                "refunds: %s references cancelled order %r" % (refund_id, order_id)
            )
        if policy == "v2" and order["created_at"] > cutoff:
            # order exists but is excluded by cutoff: ignore the refund
            continue
        order["refund_cents"] += cents
        if order["refund_cents"] > order["paid_cents"]:
            raise ValueError(
                "refunds: order %s refunded more than paid" % order_id
            )

    paid_orders = [
        o for o in orders.values()
        if o["status"] == "paid"
        and not (policy == "v2" and o["created_at"] > cutoff)
    ]
    paid_orders.sort(key=lambda o: o["order_id"])

    out_orders = []
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    by_customer = {}
    for o in paid_orders:
        net = o["paid_cents"] - o["refund_cents"]
        out_orders.append(
            {
                "order_id": o["order_id"],
                "customer": o["customer"],
                "paid_cents": o["paid_cents"],
                "refund_cents": o["refund_cents"],
                "net_cents": net,
            }
        )
        totals["paid_cents"] += o["paid_cents"]
        totals["refund_cents"] += o["refund_cents"]
        totals["net_cents"] += net
        by_customer[o["customer"]] = by_customer.get(o["customer"], 0) + net

    customers = [
        {"customer": c, "net_cents": by_customer[c]}
        for c in sorted(by_customer)
    ]

    return {"orders": out_orders, "customers": customers, "totals": totals}


def _csv_text(rows, header):
    """Render rows (list of dicts) to CSV text with the given header order."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([row[field] for field in header])
    return buf.getvalue()


def export_bundle(result):
    """Release contract: exactly orders.csv, customers.csv, summary.json.

    - orders.csv header: order_id,customer,paid_cents,refund_cents,net_cents
    - customers.csv header: customer,net_cents
    - row order follows reconcile ordering; amounts are integer text.
    - summary.json parses to exactly result["totals"].
    """
    orders_csv = _csv_text(
        result.get("orders", []),
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
    )
    customers_csv = _csv_text(
        result.get("customers", []),
        ["customer", "net_cents"],
    )
    summary_json = json.dumps(result["totals"], sort_keys=True)
    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
