"""Order reconciliation engine (contract: spec-v1 / spec-v2 / spec-final).

reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None) returns integer cents.
export_bundle(result) renders the three release files as text.

Only csv, io, json, decimal and stdlib-pure helpers are used; no file, network
or process access.

v1: strict two-decimal amounts, no date filtering, no refund status.
v2 / final: cutoff (YYYY-MM-DDTHH:MM:SSZ) required, refund status filter, and
    amounts rounded half-up to whole cents row by row before aggregation.
    "final" keeps the v2 rules so earlier callers and data stay valid.
"""

import csv
import io
import json
import decimal

_ZERO_TOTALS = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}

_ORDER_REQUIRED_V1 = ("order_id", "customer", "amount", "status")
_REFUND_REQUIRED_V1 = ("refund_id", "order_id", "amount")
_ORDER_REQUIRED_V2 = _ORDER_REQUIRED_V1 + ("created_at",)
_REFUND_REQUIRED_V2 = _REFUND_REQUIRED_V1 + ("status", "created_at")

_KNOWN_POLICIES = ("v1", "v2", "final")
_DATED_POLICIES = ("v2", "final")

_ORDER_HEADER = ("order_id", "customer", "paid_cents", "refund_cents", "net_cents")
_CUSTOMER_HEADER = ("customer", "net_cents")


def _clean(value):
    if value is None:
        return ""
    return str(value).strip()


def _amount_value(raw, field_name):
    """Validate the plain non-negative decimal shape shared by every policy."""
    if not raw:
        raise ValueError("%s is empty" % field_name)
    if raw[0] == "-":
        raise ValueError("%s must not be negative: %r" % (field_name, raw))
    dots = 0
    for ch in raw:
        if ch == ".":
            dots += 1
            if dots > 1:
                raise ValueError("%s is not a valid amount: %r" % (field_name, raw))
        elif not ("0" <= ch <= "9"):
            raise ValueError("%s is not a valid amount: %r" % (field_name, raw))
    try:
        value = decimal.Decimal(raw)
    except (decimal.InvalidOperation, ValueError):
        raise ValueError("%s is not a valid amount: %r" % (field_name, raw))
    if not value.is_finite():
        raise ValueError("%s must be finite: %r" % (field_name, raw))
    if value < 0:
        raise ValueError("%s must not be negative: %r" % (field_name, raw))
    return value


def _parse_cents_strict(text, field_name):
    """v1: at most two decimal places, no rounding tolerated."""
    raw = _clean(text)
    value = _amount_value(raw, field_name)
    scaled = value * 100
    as_integer = scaled.to_integral_value()
    if scaled != as_integer:
        raise ValueError("%s has more than two decimal places: %r" % (field_name, raw))
    return int(as_integer)


def _parse_cents_round(text, field_name):
    """v2/final: any number of decimals, ROUND_HALF_UP to cents (integer math)."""
    raw = _clean(text)
    _amount_value(raw, field_name)
    if "." in raw:
        whole, frac = raw.split(".", 1)
    else:
        whole, frac = raw, ""
    cents = int(whole or "0") * 100
    head = (frac + "00")[:2]
    cents += int(head or "0")
    if len(frac) > 2 and frac[2] >= "5":
        cents += 1
    return cents


def _read_records(csv_text, required, label):
    """Read a CSV string into records; keep the normalized raw row for dedupe."""
    if csv_text is None:
        raise ValueError("%s csv is missing" % label)
    text = str(csv_text)
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.reader(io.StringIO(text, newline=""))
    header = None
    records = []
    for raw_row in reader:
        if not raw_row:
            continue
        if header is None:
            header = [_clean(cell).lower() for cell in raw_row]
            for name in required:
                if name not in header:
                    raise ValueError("%s csv missing column: %s" % (label, name))
            continue
        cells = [_clean(cell) for cell in raw_row]
        if len(cells) < len(header):
            cells = cells + [""] * (len(header) - len(cells))
        elif len(cells) > len(header):
            cells = cells[: len(header)]
        record = {}
        for index, name in enumerate(header):
            if name in record:
                continue
            record[name] = cells[index]
        record["_row"] = tuple(cells)
        records.append(record)
    if header is None:
        # Completely empty input carries no rows, so the result is empty.
        return []
    return records


def _dedupe(records, id_field, label):
    """Identical duplicate rows collapse to one; differing rows with same id fail."""
    unique = {}
    kept = []
    for record in records:
        ident = record[id_field]
        if not ident:
            raise ValueError("%s %s is empty" % (label, id_field))
        row = record["_row"]
        existing = unique.get(ident)
        if existing is not None:
            if existing["_row"] != row:
                raise ValueError(
                    "conflicting %s rows for %s %r" % (label, id_field, ident)
                )
            continue
        unique[ident] = record
        kept.append(record)
    return kept


def _normalize_policy(policy):
    if policy is None:
        return "v1"
    text = _clean(policy).lower()
    if not text:
        return "v1"
    if text not in _KNOWN_POLICIES:
        raise ValueError("unsupported policy: %r" % (policy,))
    return text


def _require_cutoff(cutoff):
    text = "" if cutoff is None else str(cutoff).strip()
    if not text:
        raise ValueError("policy v2 requires a cutoff")
    return text


def _is_cancelled(status):
    return status in ("canceled", "cancelled")


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds, returning integer cents."""
    mode = _normalize_policy(policy)
    cutoff_text = None
    if mode in _DATED_POLICIES:
        cutoff_text = _require_cutoff(cutoff)
        parse_amount = _parse_cents_round
        order_required = _ORDER_REQUIRED_V2
        refund_required = _REFUND_REQUIRED_V2
    else:
        parse_amount = _parse_cents_strict
        order_required = _ORDER_REQUIRED_V1
        refund_required = _REFUND_REQUIRED_V1

    order_records = _dedupe(
        _read_records(orders_csv, order_required, "orders"), "order_id", "order"
    )

    paid = {}
    cancelled = set()
    out_of_window = set()
    for record in order_records:
        order_id = record["order_id"]
        customer = record["customer"]
        amount_cents = parse_amount(record["amount"], "order amount")
        status = _clean(record["status"]).lower()
        if _is_cancelled(status):
            cancelled.add(order_id)
            continue
        if status != "paid":
            raise ValueError("unknown order status: %r" % record["status"])
        if cutoff_text is not None and _clean(record["created_at"]) > cutoff_text:
            out_of_window.add(order_id)
            continue
        paid[order_id] = {
            "order_id": order_id,
            "customer": customer,
            "paid_cents": amount_cents,
            "refund_cents": 0,
        }

    refund_records = _dedupe(
        _read_records(refunds_csv, refund_required, "refunds"), "refund_id", "refund"
    )

    for record in refund_records:
        order_id = record["order_id"]
        amount_cents = parse_amount(record["amount"], "refund amount")
        if cutoff_text is not None:
            if _clean(record["status"]).lower() != "succeeded":
                continue
            if _clean(record["created_at"]) > cutoff_text:
                continue
        order = paid.get(order_id)
        if order is not None:
            order["refund_cents"] += amount_cents
            continue
        if order_id in out_of_window:
            continue
        if order_id in cancelled:
            raise ValueError("refund for cancelled order: %r" % order_id)
        raise ValueError("refund for unknown order: %r" % order_id)

    orders = []
    for order_id in sorted(paid):
        entry = paid[order_id]
        refund_cents = entry["refund_cents"]
        if refund_cents > entry["paid_cents"]:
            raise ValueError("refunds exceed payment for order: %r" % order_id)
        orders.append(
            {
                "order_id": order_id,
                "customer": entry["customer"],
                "paid_cents": entry["paid_cents"],
                "refund_cents": refund_cents,
                "net_cents": entry["paid_cents"] - refund_cents,
            }
        )

    customer_net = {}
    for entry in orders:
        customer = entry["customer"]
        customer_net[customer] = customer_net.get(customer, 0) + entry["net_cents"]
    customers = [
        {"customer": customer, "net_cents": customer_net[customer]}
        for customer in sorted(customer_net)
    ]

    totals = dict(_ZERO_TOTALS)
    for entry in orders:
        totals["paid_cents"] += entry["paid_cents"]
        totals["refund_cents"] += entry["refund_cents"]
        totals["net_cents"] += entry["net_cents"]

    return {"orders": orders, "customers": customers, "totals": totals}


def _render_csv(header, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(list(header))
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """Render the release bundle: orders.csv, customers.csv, summary.json."""
    data = result if isinstance(result, dict) else {}
    orders = data.get("orders") or []
    customers = data.get("customers") or []
    totals = data.get("totals") or {}

    order_rows = []
    for row in orders:
        order_rows.append(
            [
                str(row.get("order_id", "")),
                str(row.get("customer", "")),
                str(int(row.get("paid_cents", 0))),
                str(int(row.get("refund_cents", 0))),
                str(int(row.get("net_cents", 0))),
            ]
        )

    customer_rows = []
    for row in customers:
        customer_rows.append(
            [str(row.get("customer", "")), str(int(row.get("net_cents", 0)))]
        )

    summary = {
        "paid_cents": int(totals.get("paid_cents", 0)),
        "refund_cents": int(totals.get("refund_cents", 0)),
        "net_cents": int(totals.get("net_cents", 0)),
    }

    return {
        "orders.csv": _render_csv(_ORDER_HEADER, order_rows),
        "customers.csv": _render_csv(_CUSTOMER_HEADER, customer_rows),
        "summary.json": json.dumps(summary, ensure_ascii=False),
    }
