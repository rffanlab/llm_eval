"""Order reconciliation, v1 + v2 contracts (see spec-v1.md / spec-v2.md).

Pure functions only: inputs are CSV strings, outputs are plain dicts with
integer cents. No file/network/process access; only stdlib pure modules.
"""

import csv
import io
import json
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_CUTOFF_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_V2_REFUND_STATUSES = ("succeeded", "pending")


def _parse_amount_cents(raw, context, policy):
    """Parse an amount string into integer cents using Decimal (never float).

    policy "v1": at most 2 decimals, exact (legacy contract).
    policy "v2": any number of decimals, ROUND_HALF_UP to integer cents.
    Both reject empty/NaN/Infinity/negatives/malformed strings.
    """
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = str(raw).strip()
    if not text:
        raise ValueError("%s: empty amount" % context)
    if text[0] in "+-" or "e" in text.lower():
        raise ValueError("%s: invalid amount %r" % (context, raw))
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
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("%s: more than 2 decimals %r" % (context, raw))
        cents = value.scaleb(2)
        if cents != cents.to_integral_value():
            raise ValueError("%s: non-integral cents %r" % (context, raw))
        return int(cents)
    # v2: round half-up to integer cents.
    cents = (value.scaleb(2)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _rows(csv_text, required, id_field, kind):
    """Yield rows (as dicts) from a CSV string; validate header presence."""
    reader = csv.reader(io.StringIO(csv_text if csv_text is not None else ""))
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("%s CSV must have a header row" % kind)
    columns = [name.strip() for name in header]
    for name in required:
        if name not in columns:
            raise ValueError("%s CSV missing column %r" % (kind, name))
    for row in reader:
        if not row or all(cell.strip() == "" for cell in row):
            continue
        if len(row) != len(columns):
            raise ValueError("%s CSV: malformed row %r" % (kind, row))
        record = dict(zip(columns, row))
        if not str(record.get(id_field, "")).strip():
            raise ValueError("%s CSV: empty %s" % (kind, id_field))
        yield record


def _full_sig(record):
    """Signature over every field of a row, for duplicate-conflict checks."""
    return tuple(sorted(record.items()))


def _validate_cutoff(cutoff):
    if cutoff is None:
        raise ValueError("policy v2 requires a cutoff")
    text = str(cutoff)
    try:
        parsed = datetime.datetime.strptime(text, _CUTOFF_FORMAT)
    except ValueError:
        raise ValueError("invalid cutoff %r (expected YYYY-MM-DDTHH:MM:SSZ)" % (cutoff,))
    return parsed.strftime(_CUTOFF_FORMAT)


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds.

    policy="v1": legacy contract (2-decimal amounts, no refund status).
    policy="v2": adds cutoff filtering, refund status, and ROUND_HALF_UP
    multi-decimal amounts. See spec-v2.md.
    Returns {"orders": [...], "customers": [...], "totals": {...}} with all
    monetary values as integer cents. Raises ValueError on contract breaches.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v2":
        cutoff = _validate_cutoff(cutoff)
    else:
        cutoff = None if cutoff is None else str(cutoff)

    # --- Orders: dedupe by order_id (identical rows collapse, conflicts fail).
    order_required = ("order_id", "customer", "amount", "status")
    if policy == "v2":
        order_required = order_required + ("created_at",)
    orders = {}  # order_id -> dict
    for record in _rows(orders_csv, order_required, "order_id", "orders"):
        order_id = record["order_id"].strip()
        sig = _full_sig(record)
        if order_id in orders:
            if orders[order_id]["sig"] != sig:
                raise ValueError("conflicting duplicate order %s" % order_id)
            continue
        paid_cents = _parse_amount_cents(record["amount"], "order %s" % order_id, policy)
        orders[order_id] = {
            "customer": record["customer"],
            "status": record["status"].strip().lower(),
            "created_at": str(record.get("created_at", "")).strip(),
            "paid_cents": paid_cents,
            "sig": sig,
        }

    # --- Refunds: dedupe by refund_id, validate references.
    refund_required = ("refund_id", "order_id", "amount")
    if policy == "v2":
        refund_required = refund_required + ("status", "created_at")
    refunds = {}  # refund_id -> dict
    refund_by_order = {}  # order_id -> total counted refund cents
    for record in _rows(refunds_csv, refund_required, "refund_id", "refunds"):
        refund_id = record["refund_id"].strip()
        order_id = record["order_id"].strip()
        sig = _full_sig(record)
        if refund_id in refunds:
            if refunds[refund_id]["sig"] != sig:
                raise ValueError("conflicting duplicate refund %s" % refund_id)
            continue
        status = None
        if policy == "v2":
            status = record["status"].strip().lower()
            if status not in _V2_REFUND_STATUSES:
                raise ValueError("refund %s: invalid status %r" % (refund_id, record["status"]))
        created_at = str(record.get("created_at", "")).strip()

        # Decide whether this refund counts (v2: succeeded and <= cutoff).
        counted = True
        if policy == "v2":
            counted = status == "succeeded" and created_at <= cutoff

        order = orders.get(order_id)
        if counted:
            if order is None:
                raise ValueError(
                    "refund %s references unknown order %s" % (refund_id, order_id))
            if order["status"] != "paid":
                raise ValueError(
                    "refund %s references non-paid order %s" % (refund_id, order_id))
            if cutoff is not None and order["created_at"] > cutoff:
                counted = False  # order exists but excluded by cutoff: ignore

        amount_cents = _parse_amount_cents(record["amount"], "refund %s" % refund_id, policy)
        refunds[refund_id] = {"order_id": order_id, "amount": record["amount"], "sig": sig}
        if counted:
            refund_by_order[order_id] = refund_by_order.get(order_id, 0) + amount_cents

    # --- Build result (paid orders only; v2 also requires created_at<=cutoff).
    order_rows = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(orders):
        order = orders[order_id]
        if order["status"] != "paid":
            continue
        if policy == "v2" and order["created_at"] > cutoff:
            continue
        paid_cents = order["paid_cents"]
        refund_cents = refund_by_order.get(order_id, 0)
        if refund_cents > paid_cents:
            raise ValueError(
                "order %s refunded %d cents exceeds paid %d cents"
                % (order_id, refund_cents, paid_cents)
            )
        net_cents = paid_cents - refund_cents
        order_rows.append({
            "order_id": order_id,
            "customer": order["customer"],
            "paid_cents": paid_cents,
            "refund_cents": refund_cents,
            "net_cents": net_cents,
        })
        customer = order["customer"]
        customer_net[customer] = customer_net.get(customer, 0) + net_cents
        totals["paid_cents"] += paid_cents
        totals["refund_cents"] += refund_cents
        totals["net_cents"] += net_cents

    customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]
    return {"orders": order_rows, "customers": customers, "totals": totals}


def _csv_text(rows, header):
    """Render rows (list of dicts) to CSV text with the given header order.

    Uses the standard csv writer; monetary values are plain integer text.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([str(row[column]) for column in header])
    return buffer.getvalue()


def export_bundle(result):
    """Serialize a reconcile result into the release bundle.

    Per release-spec.md the bundle is exactly three files:
    - orders.csv    header order_id,customer,paid_cents,refund_cents,net_cents
    - customers.csv header customer,net_cents
    - summary.json  exactly result["totals"]
    Row order follows the reconcile ordering; amounts are integer text.
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a dict")
    orders = result.get("orders", [])
    customers = result.get("customers", [])
    totals = result.get("totals")
    if not isinstance(totals, dict):
        raise ValueError("result missing totals")
    return {
        "orders.csv": _csv_text(
            orders, ("order_id", "customer", "paid_cents", "refund_cents", "net_cents")),
        "customers.csv": _csv_text(customers, ("customer", "net_cents")),
        "summary.json": json.dumps(totals, sort_keys=True),
    }
