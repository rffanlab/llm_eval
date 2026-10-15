"""Order reconciliation - v1 and v2 contracts (spec-v1.md, spec-v2.md).

Pure functions only. Inputs are UTF-8 CSV strings; monetary outputs are integer cents
computed with decimal fixed-point (never float * 100).
"""

import csv
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_HEADER = ["order_id", "customer", "amount", "status", "created_at"]
_REFUND_HEADERS = {
    "v1": ["refund_id", "order_id", "amount"],
    "v2": ["refund_id", "order_id", "amount", "status", "created_at"],
}


def _parse_amount_cents(raw, policy):
    """Parse an amount string to integer cents under the given policy.

    v1: non-negative, at most two decimal places; reject NaN/Infinity/negatives.
    v2: non-negative, any number of decimals, ROUND_HALF_UP to integer cents.
    Raises ValueError on invalid input.
    """
    if raw is None:
        raise ValueError("missing amount")
    text = str(raw).strip()
    if text == "":
        raise ValueError("empty amount")
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("invalid amount: %r" % (raw,))
    if not value.is_finite():
        raise ValueError("non-finite amount: %r" % (raw,))
    if value < 0:
        raise ValueError("negative amount: %r" % (raw,))
    if policy == "v1":
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("more than two decimal places: %r" % (raw,))
        cents = value * Decimal(100)
        if cents != cents.to_integral_value():
            raise ValueError("amount not representable in cents: %r" % (raw,))
        return int(cents.to_integral_value())
    # v2: fixed-point ROUND_HALF_UP to cents, no float involved.
    cents = (value * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _validate_cutoff(cutoff):
    """Validate cutoff is a strict UTC string YYYY-MM-DDTHH:MM:SSZ."""
    if cutoff is None:
        raise ValueError("v2 policy requires a cutoff")
    text = str(cutoff)
    expected_shape = (
        len(text) == 20
        and text[4] == "-" and text[7] == "-"
        and text[10] == "T"
        and text[13] == ":" and text[16] == ":"
        and text[19] == "Z"
        and all(ch.isdigit() for ch in text[0:4] + text[5:7] + text[8:10]
                + text[11:13] + text[14:16] + text[17:19])
    )
    if not expected_shape:
        raise ValueError("invalid cutoff format: %r" % (cutoff,))
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("invalid cutoff value: %r" % (cutoff,))
    return text


def _read_rows(csv_text, required_header):
    """Parse CSV text into list of row tuples (header validated). Empty -> []."""
    if csv_text is None:
        return []
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row and any(field.strip() != "" for field in row)]
    if not rows:
        return []
    header = [field.strip() for field in rows[0]]
    if header != required_header:
        raise ValueError("bad header: expected %r, got %r" % (required_header, header))
    return rows[1:]


def _dedupe(rows, key_index, kind):
    """Dedupe rows by key. Identical duplicates collapse; conflicting rows raise.

    Runs before any filtering so conflicts involving pending/after-cutoff rows
    are still rejected.
    """
    seen = {}
    unique = []
    for row in rows:
        key = row[key_index].strip()
        normalized = tuple(field.strip() for field in row)
        if key in seen:
            if seen[key] != normalized:
                raise ValueError("conflicting duplicate %s id: %r" % (kind, key))
            continue
        seen[key] = normalized
        unique.append(normalized)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile orders and refunds per the v1/v2 contract.

    Returns {"orders": [...], "customers": [...], "totals": {...}} with integer cents.
    Raises ValueError on invalid policy/amounts, duplicate-id conflicts, and (for
    valid refunds) references to unknown or cancelled orders or over-refunds.

    v2 additionally requires cutoff (YYYY-MM-DDTHH:MM:SSZ): only paid orders with
    created_at <= cutoff count, and only succeeded refunds with
    created_at <= cutoff count.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    cutoff_text = _validate_cutoff(cutoff) if policy == "v2" else None

    order_rows = _read_rows(orders_csv, _ORDER_HEADER)
    refund_rows = _read_rows(refunds_csv, _REFUND_HEADERS[policy])

    orders = {}
    for row in _dedupe(order_rows, 0, "order"):
        order_id, customer, amount_raw, status, created_at = row
        paid_cents = _parse_amount_cents(amount_raw, policy)
        orders[order_id] = {
            "customer": customer,
            "paid_cents": paid_cents,
            "status": status.lower(),
            "created_at": created_at,
        }

    refunds = {}
    for row in _dedupe(refund_rows, 0, "refund"):
        if policy == "v1":
            refund_id, order_id, amount_raw = row
            status, created_at = "succeeded", None
        else:
            refund_id, order_id, amount_raw, status, created_at = row
        refund_cents = _parse_amount_cents(amount_raw, policy)
        refunds[refund_id] = {
            "order_id": order_id,
            "refund_cents": refund_cents,
            "status": status.lower(),
            "created_at": created_at,
        }

    def _refund_counts(refund):
        if policy == "v1":
            return True
        if refund["status"] != "succeeded":
            return False
        return refund["created_at"] <= cutoff_text

    def _order_counts(order):
        if policy == "v1":
            return True
        return order["created_at"] <= cutoff_text

    refund_by_order = {}
    for refund_id in sorted(refunds):
        refund = refunds[refund_id]
        if not _refund_counts(refund):
            continue  # pending or after-cutoff refunds are ignored entirely
        order_id = refund["order_id"]
        order = orders.get(order_id)
        if order is None:
            raise ValueError("refund %s references unknown order %r" % (refund_id, order_id))
        if order["status"] != "paid":
            raise ValueError("refund %s references non-paid order %r" % (refund_id, order_id))
        if not _order_counts(order):
            continue  # order exists but is excluded by cutoff: ignore the refund
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + refund["refund_cents"]

    for order_id, refunded in refund_by_order.items():
        if refunded > orders[order_id]["paid_cents"]:
            raise ValueError(
                "order %s over-refunded: %d > %d" % (order_id, refunded, orders[order_id]["paid_cents"])
            )

    order_entries = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(orders):
        order = orders[order_id]
        if order["status"] != "paid" or not _order_counts(order):
            continue
        paid = order["paid_cents"]
        refunded = refund_by_order.get(order_id, 0)
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

    return {"orders": order_entries, "customers": customers, "totals": totals}


def _rows_to_csv(header, rows):
    """Render rows with the standard csv writer (deterministic output)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """Export a reconcile result as the release bundle (release-spec.md).

    Returns exactly three files: orders.csv, customers.csv, summary.json.
    Row order follows the reconcile ordering; amounts are integer text;
    summary.json parses back to result["totals"] exactly.
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError("result missing key: %r" % (key,))

    order_rows = []
    for entry in result["orders"]:
        order_rows.append([
            entry["order_id"],
            entry["customer"],
            int(entry["paid_cents"]),
            int(entry["refund_cents"]),
            int(entry["net_cents"]),
        ])

    customer_rows = []
    for entry in result["customers"]:
        customer_rows.append([entry["customer"], int(entry["net_cents"])])

    totals = result["totals"]
    summary = {
        "paid_cents": int(totals["paid_cents"]),
        "refund_cents": int(totals["refund_cents"]),
        "net_cents": int(totals["net_cents"]),
    }

    return {
        "orders.csv": _rows_to_csv(
            ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"], order_rows),
        "customers.csv": _rows_to_csv(["customer", "net_cents"], customer_rows),
        "summary.json": json.dumps(summary),
    }
