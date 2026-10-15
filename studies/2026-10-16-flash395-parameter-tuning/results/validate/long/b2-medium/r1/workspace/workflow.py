"""Order reconciliation per spec-v1 and spec-v2.

reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None) -> dict
All money handled as integer cents via decimal fixed-point (no float math).

export_bundle(result) -> dict[str, str] with exactly orders.csv,
customers.csv and summary.json, formatted per release-spec.md.
"""

import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_HUNDRED = Decimal(100)

_ORDER_FIELDS = ["order_id", "customer", "amount", "status", "created_at"]
_REFUND_FIELDS_V1 = ["refund_id", "order_id", "amount"]
_REFUND_FIELDS_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]

_DIGITS = "0123456789"


def _is_valid_cutoff(text):
    """Strict YYYY-MM-DDTHH:MM:SSZ shape check (lexicographically comparable)."""
    if not isinstance(text, str) or len(text) != 20:
        return False
    if (
        text[4] != "-"
        or text[7] != "-"
        or text[10] != "T"
        or text[13] != ":"
        or text[16] != ":"
        or text[19] != "Z"
    ):
        return False
    for i in (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18):
        if text[i] not in _DIGITS:
            return False
    return True


def _is_valid_amount_text(text):
    """Strict fixed-point check: optional integer digits, up to 2 decimals."""
    if not text:
        return False
    if "." in text:
        if text.count(".") != 1:
            return False
        head, tail = text.split(".")
        if head == "" and tail == "":
            return False
        if any(c not in _DIGITS for c in head) or any(c not in _DIGITS for c in tail):
            return False
        if len(tail) > 2:
            return False
    else:
        if any(c not in _DIGITS for c in text):
            return False
    return True


def _reject_amount(raw, context):
    """Raise a precise ValueError explaining why the amount is invalid."""
    text = raw.strip()
    try:
        d = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if d.is_nan() or d.is_infinite():
        raise ValueError("%s: NaN/Infinity amount" % context)
    if d < 0:
        raise ValueError("%s: negative amount" % context)
    raise ValueError("%s: amount exceeds 2 decimal places %r" % (context, raw))


def _parse_amount_cents_v1(raw, context):
    """v1: non-negative, at most 2 decimals, exact conversion to cents."""
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = raw.strip()
    if not _is_valid_amount_text(text):
        _reject_amount(raw, context)
    cents = (Decimal(text) * _HUNDRED).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _parse_amount_cents_v2(raw, context):
    """v2: non-negative, any number of decimals, ROUND_HALF_UP to cents."""
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = raw.strip()
    if not text or text[0] == "-" or text.count(".") > 1:
        _reject_amount(raw, context)
    if any(c not in (_DIGITS + ".") for c in text) or text == ".":
        _reject_amount(raw, context)
    d = Decimal(text)
    if d.is_nan() or d.is_infinite() or d < 0:
        _reject_amount(raw, context)
    cents = (d * _HUNDRED).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _split_csv_line(line):
    """Minimal RFC4180-style CSV line splitter (quotes, escaped quotes)."""
    fields = []
    field = ""
    in_quotes = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < n and line[i + 1] == '"':
                    field += '"'
                    i += 2
                    continue
                in_quotes = False
                i += 1
                continue
            field += ch
            i += 1
            continue
        if ch == '"':
            in_quotes = True
            i += 1
            continue
        if ch == ",":
            fields.append(field)
            field = ""
            i += 1
            continue
        field += ch
        i += 1
    if in_quotes:
        raise ValueError("csv: unbalanced quotes in line %r" % (line,))
    fields.append(field)
    return fields


def _read_rows(csv_text, expected_fields, kind):
    """Parse CSV text into a list of dicts keyed by the expected header."""
    if csv_text is None:
        raise ValueError("%s csv is None" % kind)
    lines = csv_text.splitlines()
    # Drop purely empty trailing lines; keep interior structure intact.
    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        raise ValueError("%s csv: missing header" % kind)
    header = [h.strip() for h in _split_csv_line(lines[0])]
    if header != expected_fields:
        raise ValueError(
            "%s csv: expected header %s, got %s" % (kind, expected_fields, header)
        )
    rows = []
    for line in lines[1:]:
        if line == "":
            continue  # tolerate blank lines
        raw_row = _split_csv_line(line)
        if len(raw_row) != len(expected_fields):
            raise ValueError("%s csv: malformed row %r" % (kind, line))
        rows.append(dict(zip(header, [v.strip() for v in raw_row])))
    return rows


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v1":
        parse_amount = _parse_amount_cents_v1
        refund_fields = _REFUND_FIELDS_V1
    else:
        if cutoff is None:
            raise ValueError("policy v2 requires cutoff")
        if not _is_valid_cutoff(cutoff):
            raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ, got %r" % (cutoff,))
        parse_amount = _parse_amount_cents_v2
        refund_fields = _REFUND_FIELDS_V2

    order_rows = _read_rows(orders_csv, _ORDER_FIELDS, "orders")
    refund_rows = _read_rows(refunds_csv, refund_fields, "refunds")

    # ---- Orders: dedupe by order_id (all rows, even excluded ones) -------
    orders = {}  # order_id -> record dict
    for row in order_rows:
        oid = row["order_id"]
        if not oid:
            raise ValueError("orders: empty order_id")
        cents = parse_amount(row["amount"], "order %s" % oid)
        status = row["status"]
        if status not in ("paid", "cancelled"):
            raise ValueError("order %s: unknown status %r" % (oid, status))
        record = {
            "order_id": oid,
            "customer": row["customer"],
            "paid_cents": cents,
            "status": status,
            "created_at": row["created_at"],
        }
        if oid in orders:
            if orders[oid] == record:
                continue  # exact duplicate row: count once
            raise ValueError("order %s: duplicate id with different fields" % oid)
        orders[oid] = record

    # ---- Refunds: dedupe by refund_id (all rows, even excluded ones) -----
    refunds = {}  # refund_id -> record dict
    for row in refund_rows:
        rid = row["refund_id"]
        if not rid:
            raise ValueError("refunds: empty refund_id")
        cents = parse_amount(row["amount"], "refund %s" % rid)
        record = {"refund_id": rid, "order_id": row["order_id"], "refund_cents": cents}
        if policy == "v2":
            if row["status"] not in ("succeeded", "pending"):
                raise ValueError("refund %s: unknown status %r" % (rid, row["status"]))
            record["status"] = row["status"]
            record["created_at"] = row["created_at"]
        if rid in refunds:
            if refunds[rid] == record:
                continue  # exact duplicate row: count once
            raise ValueError("refund %s: duplicate id with different fields" % rid)
        refunds[rid] = record

    def _order_included(order):
        if order["status"] != "paid":
            return False
        if policy == "v2" and order["created_at"] > cutoff:
            return False
        return True

    def _refund_counted(rec):
        if policy == "v1":
            return True
        return rec["status"] == "succeeded" and rec["created_at"] <= cutoff

    # ---- Validate refunds against orders ---------------------------------
    refund_by_order = {}
    for rid in sorted(refunds):
        rec = refunds[rid]
        oid = rec["order_id"]
        order = orders.get(oid)
        counted = _refund_counted(rec)
        if order is None:
            if counted:
                raise ValueError("refund %s: unknown order %s" % (rid, oid))
            continue  # pending/late refund for unknown order: not counted
        if order["status"] != "paid":
            if counted:
                raise ValueError("refund %s: order %s is not paid" % (rid, oid))
            continue
        if not counted:
            continue  # pending or after-cutoff refund: ignored
        if policy == "v2" and order["created_at"] > cutoff:
            continue  # order exists but excluded by cutoff: ignore refund
        refund_by_order[oid] = refund_by_order.get(oid, 0) + rec["refund_cents"]
    for oid, total in refund_by_order.items():
        if total > orders[oid]["paid_cents"]:
            raise ValueError(
                "order %s: refunds %d exceed paid %d" % (oid, total, orders[oid]["paid_cents"])
            )

    # ---- Build result ------------------------------------------------------
    result_orders = []
    customers_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for oid in sorted(orders):
        order = orders[oid]
        if not _order_included(order):
            continue  # cancelled or after-cutoff orders are excluded
        paid = order["paid_cents"]
        refund = refund_by_order.get(oid, 0)
        net = paid - refund
        result_orders.append(
            {
                "order_id": oid,
                "customer": order["customer"],
                "paid_cents": paid,
                "refund_cents": refund,
                "net_cents": net,
            }
        )
        customers_net[order["customer"]] = customers_net.get(order["customer"], 0) + net
        totals["paid_cents"] += paid
        totals["refund_cents"] += refund
        totals["net_cents"] += net

    result_customers = [
        {"customer": name, "net_cents": customers_net[name]}
        for name in sorted(customers_net)
    ]
    return {"orders": result_orders, "customers": result_customers, "totals": totals}


# ---------------------------------------------------------------------------
# Release bundle (release-spec.md)
# ---------------------------------------------------------------------------


def _csv_field(value):
    """QUOTE_MINIMAL escaping identical to csv.writer defaults."""
    text = str(value)
    if any(c in text for c in (",", '"', "\r", "\n")):
        return '"' + text.replace('"', '""') + '"'
    return text


def _csv_text(header, rows):
    """Render CSV exactly like csv.writer defaults (CRLF line terminator)."""
    out = _csv_field(header[0])
    for h in header[1:]:
        out += "," + _csv_field(h)
    out += "\r\n"
    for row in rows:
        out += ",".join(_csv_field(v) for v in row) + "\r\n"
    return out


def export_bundle(result):
    """Return exactly orders.csv, customers.csv and summary.json as text."""
    orders = result.get("orders", [])
    customers = result.get("customers", [])
    totals = result.get("totals", {"paid_cents": 0, "refund_cents": 0, "net_cents": 0})

    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            [
                o["order_id"],
                o["customer"],
                o["paid_cents"],
                o["refund_cents"],
                o["net_cents"],
            ]
            for o in orders
        ],
    )
    customers_csv = _csv_text(
        ["customer", "net_cents"],
        [[c["customer"], c["net_cents"]] for c in customers],
    )
    summary = json.dumps(totals, sort_keys=True)
    return {"orders.csv": orders_csv, "customers.csv": customers_csv, "summary.json": summary}
