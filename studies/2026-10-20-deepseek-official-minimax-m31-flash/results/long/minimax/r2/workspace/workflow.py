"""Order reconciliation workflow.

Pure functions only (no file, network or process access).

Contracts implemented here:
  * spec-v1.md      -- policy="v1" reconciliation.
  * spec-v2.md      -- policy="v2" changes: cutoff date, refund status,
                       multi decimal amounts rounded half-up to integer cents.
  * release-spec.md -- export_bundle(): exactly three files
                       (orders.csv, customers.csv, summary.json).
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


ONE_CENT = Decimal("0.01")
ORDER_HEADER = ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"]
CUSTOMER_HEADER = ["customer", "net_cents"]
DATE_SHAPE = "dddd-dd-ddTdd:dd:ddZ"
DATE_SHAPE_LENGTH = len(DATE_SHAPE)


# --------------------------------------------------------------------------
# amount helpers (decimal fixed point, never float * 100)
# --------------------------------------------------------------------------
def _parse_amount(text, context):
    raw = "" if text is None else text.strip()
    if raw == "":
        raise ValueError("empty amount in %s" % context)
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError, ArithmeticError):
        raise ValueError("invalid amount %r in %s" % (text, context))
    if not value.is_finite():
        raise ValueError("non-finite amount %r in %s" % (text, context))
    if value < 0:
        raise ValueError("negative amount %r in %s" % (text, context))
    return value


def _exact_cents(value, context):
    """Exact integer cents of a non-negative Decimal with at most two decimals."""
    sign, digits, exponent = value.as_tuple()
    if sign:
        raise ValueError("negative amount in %s" % context)
    if exponent < -2:
        raise ValueError("amount with more than two decimal places in %s" % context)
    number = 0
    for digit in digits:
        number = number * 10 + digit
    return number * (10 ** (exponent + 2))


def _v1_cents(text, context):
    """v1: at most two decimals, otherwise ValueError."""
    value = _parse_amount(text, context)
    return _exact_cents(value, context)


def _v2_cents(text, context):
    """v2: any number of decimals, rounded half-up to integer cents."""
    value = _parse_amount(text, context)
    try:
        quantized = value.quantize(ONE_CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ArithmeticError):
        raise ValueError("invalid amount %r in %s" % (text, context))
    return _exact_cents(quantized, context)


# --------------------------------------------------------------------------
# csv helpers
# --------------------------------------------------------------------------
def _read_table(csv_text, kind):
    """Parse a CSV string into (header names, records).  Records keep every raw
    cell so that duplicate ids can be compared field by field."""
    if not isinstance(csv_text, str):
        raise ValueError("%s csv must be a string" % kind)
    text = csv_text
    if text.startswith("﻿"):
        text = text[1:]
    reader = csv.reader(io.StringIO(text, newline=""))
    table = []
    for row in reader:
        if len(row) == 0:
            continue
        if len(row) == 1 and row[0].strip() == "":
            continue
        table.append([cell.strip() for cell in row])
    if not table:
        return [], []
    header = [name.lower() for name in table[0]]
    records = []
    for cells in table[1:]:
        row = list(cells)
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        record = {}
        for index, name in enumerate(header):
            record[name] = row[index]
        record["_cells"] = tuple(row)
        records.append(record)
    return header, records


def _require_columns(header, required, kind):
    missing = [name for name in required if name not in header]
    if missing:
        raise ValueError("missing column(s) %s in %s csv" % (",".join(missing), kind))


def _dedupe(records, key_column, kind):
    """Keep one row per id.  Identical rows collapse, conflicting rows raise."""
    unique = {}
    for record in records:
        key = record[key_column]
        if key == "":
            raise ValueError("empty %s in %s csv" % (key_column, kind))
        previous = unique.get(key)
        if previous is None:
            unique[key] = record
        elif previous["_cells"] != record["_cells"]:
            raise ValueError("conflicting duplicate %s %r in %s csv" % (key_column, key, kind))
    return unique


def _is_canonical_date(text):
    """True for the canonical UTC shape YYYY-MM-DDTHH:MM:SSZ."""
    if not isinstance(text, str) or len(text) != DATE_SHAPE_LENGTH:
        return False
    for index, char in enumerate(text):
        shape = DATE_SHAPE[index]
        if shape == "d":
            if char < "0" or char > "9":
                return False
        elif char != shape:
            return False
    return True


def _check_cutoff(cutoff):
    if not isinstance(cutoff, str):
        raise ValueError("cutoff must be a string")
    text = cutoff.strip()
    if not _is_canonical_date(text):
        raise ValueError("invalid cutoff %r, expected YYYY-MM-DDTHH:MM:SSZ" % (cutoff,))
    return text


# --------------------------------------------------------------------------
# reconciliation
# --------------------------------------------------------------------------
def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds.

    policy "v1": original contract (two decimals max, no cutoff, no refund
    status).  policy "v2": cutoff filter, succeeded refunds only, amounts
    rounded half-up to integer cents.
    """
    if policy == "v1":
        use_v2 = False
    elif policy == "v2":
        use_v2 = True
        if cutoff is None:
            raise ValueError("cutoff is required for policy 'v2'")
        cutoff = _check_cutoff(cutoff)
    else:
        raise ValueError("unknown policy %r" % (policy,))

    order_header, order_rows = _read_table(orders_csv, "orders")
    refund_header, refund_rows = _read_table(refunds_csv, "refunds")
    order_required = ["order_id", "customer", "amount", "status"]
    refund_required = ["refund_id", "order_id", "amount"]
    if use_v2:
        order_required = order_required + ["created_at"]
        refund_required = refund_required + ["status", "created_at"]
    _require_columns(order_header, order_required, "orders")
    _require_columns(refund_header, refund_required, "refunds")

    orders = _dedupe(order_rows, "order_id", "orders")
    refunds = _dedupe(refund_rows, "refund_id", "refunds")

    order_info = {}
    for order_id, record in orders.items():
        context = "order %s" % order_id
        cents = _v2_cents(record["amount"], context) if use_v2 else _v1_cents(record["amount"], context)
        status = record["status"]
        created_at = record.get("created_at", "") if use_v2 else ""
        included = status == "paid" and (not use_v2 or created_at <= cutoff)
        order_info[order_id] = {
            "customer": record["customer"],
            "paid_cents": cents,
            "status": status,
            "created_at": created_at,
            "included": included,
        }

    refunds_by_order = {}
    for refund_id, record in refunds.items():
        context = "refund %s" % refund_id
        cents = _v2_cents(record["amount"], context) if use_v2 else _v1_cents(record["amount"], context)
        if use_v2:
            # pending refunds and refunds created after the cutoff never count
            if record.get("status", "") != "succeeded":
                continue
            if record.get("created_at", "") > cutoff:
                continue
        order_id = record["order_id"]
        info = order_info.get(order_id)
        if info is None:
            raise ValueError("refund %s references unknown order %s" % (refund_id, order_id))
        if info["status"] != "paid":
            raise ValueError(
                "refund %s references order %s with status %s" % (refund_id, order_id, info["status"])
            )
        if use_v2 and not info["included"]:
            # the order exists but is excluded by the cutoff -> ignore the refund
            continue
        total = refunds_by_order.get(order_id, 0) + cents
        if total > info["paid_cents"]:
            raise ValueError("refund %s exceeds the paid amount of order %s" % (refund_id, order_id))
        refunds_by_order[order_id] = total

    order_results = []
    for order_id in sorted(order_info):
        info = order_info[order_id]
        if not info["included"]:
            continue
        refund_cents = refunds_by_order.get(order_id, 0)
        order_results.append(
            {
                "order_id": order_id,
                "customer": info["customer"],
                "paid_cents": info["paid_cents"],
                "refund_cents": refund_cents,
                "net_cents": info["paid_cents"] - refund_cents,
            }
        )

    customer_nets = {}
    for entry in order_results:
        customer_nets[entry["customer"]] = customer_nets.get(entry["customer"], 0) + entry["net_cents"]
    customer_results = [{"customer": name, "net_cents": customer_nets[name]} for name in sorted(customer_nets)]

    totals = {
        "paid_cents": sum(entry["paid_cents"] for entry in order_results),
        "refund_cents": sum(entry["refund_cents"] for entry in order_results),
        "net_cents": sum(entry["net_cents"] for entry in order_results),
    }
    return {"orders": order_results, "customers": customer_results, "totals": totals}


# --------------------------------------------------------------------------
# release bundle
# --------------------------------------------------------------------------
def _csv_text(header, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """Build the release bundle: exactly orders.csv, customers.csv, summary.json."""
    if not isinstance(result, dict):
        raise ValueError("result must be a mapping")
    orders = result.get("orders") or []
    customers = result.get("customers") or []
    totals = result.get("totals") or {}
    orders_text = _csv_text(
        ORDER_HEADER,
        [
            [
                entry["order_id"],
                entry["customer"],
                int(entry["paid_cents"]),
                int(entry["refund_cents"]),
                int(entry["net_cents"]),
            ]
            for entry in orders
        ],
    )
    customers_text = _csv_text(
        CUSTOMER_HEADER,
        [[entry["customer"], int(entry["net_cents"])] for entry in customers],
    )
    summary_text = json.dumps(totals, sort_keys=True, ensure_ascii=False)
    return {
        "orders.csv": orders_text,
        "customers.csv": customers_text,
        "summary.json": summary_text,
    }
