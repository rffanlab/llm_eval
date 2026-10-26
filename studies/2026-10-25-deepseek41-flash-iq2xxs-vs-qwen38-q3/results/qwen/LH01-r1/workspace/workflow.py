"""Order reconciliation - v1 + v2 contracts (spec-v1.md, spec-v2.md).

Pure functions only: parse CSV strings, compute integer-cent results.
No file/network/process access; only stdlib csv/io/json/decimal.
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


_ORDER_FIELDS = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_FIELDS_V1 = ("refund_id", "order_id", "amount")
_REFUND_FIELDS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")
_CUTOFF_LEN = len("2026-10-01T00:00:00Z")
_VALID_REFUND_STATUSES = ("succeeded", "pending")


def _validate_cutoff(cutoff):
    """Strictly validate the normalized UTC cutoff YYYY-MM-DDTHH:MM:SSZ."""
    if not isinstance(cutoff, str):
        raise ValueError("cutoff must be a string")
    text = cutoff.strip()
    if len(text) != _CUTOFF_LEN:
        raise ValueError("bad cutoff format: %r" % (cutoff,))
    digits = [0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18]
    for pos in digits:
        if text[pos] not in "0123456789":
            raise ValueError("bad cutoff format: %r" % (cutoff,))
    if text[4] != "-" or text[7] != "-" or text[10] != "T":
        raise ValueError("bad cutoff format: %r" % (cutoff,))
    if text[13] != ":" or text[16] != ":" or text[19] != "Z":
        raise ValueError("bad cutoff format: %r" % (cutoff,))
    return text


def _parse_amount_cents(raw, policy):
    """Parse an amount string to integer cents using Decimal (no float math).

    v1: non-negative, at most two decimal places, reject NaN/Infinity.
    v2: non-negative, any number of decimals, ROUND_HALF_UP to whole cents.
    """
    if raw is None:
        raise ValueError("missing amount")
    text = str(raw).strip()
    if text == "":
        raise ValueError("empty amount")
    try:
        dec = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % (raw,))
    if not dec.is_finite():
        raise ValueError("non-finite amount: %r" % (raw,))
    if dec < 0:
        raise ValueError("negative amount: %r" % (raw,))
    if policy == "v1":
        exponent = dec.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -2:
            raise ValueError("amount has more than two decimals: %r" % (raw,))
    cents = (dec * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _read_rows(csv_text, fields, kind):
    """Parse CSV text into a list of dicts keyed by the expected fields.

    Header-only or empty input yields an empty list.
    """
    if csv_text is None:
        raise ValueError("missing %s CSV" % kind)
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row and not (len(row) == 1 and row[0].strip() == "")]
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    if tuple(header) != fields:
        raise ValueError("bad %s header: %r" % (kind, rows[0]))
    records = []
    for row in rows[1:]:
        if len(row) != len(fields):
            raise ValueError("bad %s row: %r" % (kind, row))
        records.append({name: value.strip() for name, value in zip(fields, row)})
    return records


def _dedupe(records, id_field, kind):
    """Deduplicate by id: exact-duplicate rows collapse; conflicting rows raise.

    Runs before any filtering, so conflicts involving pending or after-cutoff
    rows are still rejected.
    """
    seen = {}
    unique = []
    for record in records:
        key = record[id_field]
        if key in seen:
            if seen[key] != record:
                raise ValueError(
                    "conflicting duplicate %s id %r" % (kind, key)
                )
            continue
        seen[key] = record
        unique.append(record)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile orders and refunds per the v1/v2 contracts.

    Returns {"orders": [...], "customers": [...], "totals": {...}} with all
    money as integer cents. v2 requires cutoff (YYYY-MM-DDTHH:MM:SSZ) and
    applies date filtering plus refund status handling.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    cutoff_at = None
    if policy == "v2":
        if cutoff is None:
            raise ValueError("policy v2 requires cutoff")
        cutoff_at = _validate_cutoff(cutoff)

    refund_fields = _REFUND_FIELDS_V1 if policy == "v1" else _REFUND_FIELDS_V2

    order_rows = _dedupe(_read_rows(orders_csv, _ORDER_FIELDS, "orders"), "order_id", "order")
    refund_rows = _dedupe(_read_rows(refunds_csv, refund_fields, "refunds"), "refund_id", "refund")

    orders = {}  # order_id -> record with paid_cents
    for record in order_rows:
        if record["order_id"] == "" or record["customer"] == "":
            raise ValueError("empty order_id or customer: %r" % (record,))
        paid_cents = _parse_amount_cents(record["amount"], policy)
        orders[record["order_id"]] = {
            "order_id": record["order_id"],
            "customer": record["customer"],
            "status": record["status"],
            "paid_cents": paid_cents,
            "created_at": record["created_at"],
        }

    refund_by_order = {}
    for record in refund_rows:
        refund_id = record["refund_id"]
        if refund_id == "":
            raise ValueError("empty refund_id: %r" % (record,))
        amount_cents = _parse_amount_cents(record["amount"], policy)
        if policy == "v2":
            status = record["status"]
            if status not in _VALID_REFUND_STATUSES:
                raise ValueError("bad refund status: %r" % (record,))
            if status == "pending":
                continue  # pending refunds never count
            if record["created_at"] > cutoff_at:
                continue  # refund after cutoff never counts
        order_id = record["order_id"]
        order = orders.get(order_id)
        if order is None:
            raise ValueError("refund %s references unknown order %r" % (refund_id, order_id))
        if order["status"] != "paid":
            raise ValueError(
                "refund %s targets non-paid order %r" % (refund_id, order_id)
            )
        if policy == "v2" and order["created_at"] > cutoff_at:
            continue  # order exists but is excluded by cutoff: ignore refund
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + amount_cents

    for order_id, refund_cents in refund_by_order.items():
        if refund_cents > orders[order_id]["paid_cents"]:
            raise ValueError(
                "order %r refunded %d cents exceeds paid %d cents"
                % (order_id, refund_cents, orders[order_id]["paid_cents"])
            )

    result_orders = []
    customer_totals = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(orders):
        order = orders[order_id]
        if order["status"] != "paid":
            continue  # cancelled orders never enter the result
        if policy == "v2" and order["created_at"] > cutoff_at:
            continue  # orders created after cutoff never enter the result
        paid_cents = order["paid_cents"]
        refund_cents = refund_by_order.get(order_id, 0)
        net_cents = paid_cents - refund_cents
        result_orders.append(
            {
                "order_id": order_id,
                "customer": order["customer"],
                "paid_cents": paid_cents,
                "refund_cents": refund_cents,
                "net_cents": net_cents,
            }
        )
        customer = order["customer"]
        customer_totals[customer] = customer_totals.get(customer, 0) + net_cents
        totals["paid_cents"] += paid_cents
        totals["refund_cents"] += refund_cents
        totals["net_cents"] += net_cents

    customers = [
        {"customer": name, "net_cents": customer_totals[name]}
        for name in sorted(customer_totals)
    ]
    return {"orders": result_orders, "customers": customers, "totals": totals}


def _csv_text(rows):
    """Render rows with the standard csv writer into a CSV string."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """Serialize a reconcile result into the release bundle (release-spec.md).

    Returns exactly three files: orders.csv, customers.csv, summary.json.
    Row order follows the reconcile ordering; amounts are integer text;
    summary.json parses back to exactly result["totals"].
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a reconcile result dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError("result missing %r" % (key,))

    order_rows = [["order_id", "customer", "paid_cents", "refund_cents", "net_cents"]]
    for order in result["orders"]:
        order_rows.append(
            [
                str(order["order_id"]),
                str(order["customer"]),
                str(int(order["paid_cents"])),
                str(int(order["refund_cents"])),
                str(int(order["net_cents"])),
            ]
        )

    customer_rows = [["customer", "net_cents"]]
    for customer in result["customers"]:
        customer_rows.append(
            [str(customer["customer"]), str(int(customer["net_cents"]))]
        )

    totals = result["totals"]
    summary = json.dumps(
        {
            "paid_cents": int(totals["paid_cents"]),
            "refund_cents": int(totals["refund_cents"]),
            "net_cents": int(totals["net_cents"]),
        },
        sort_keys=True,
    )

    return {
        "orders.csv": _csv_text(order_rows),
        "customers.csv": _csv_text(customer_rows),
        "summary.json": summary,
    }
