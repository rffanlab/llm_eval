"""Order reconciliation, spec-v1 and spec-v2 contracts.

Pure functions only. Inputs are UTF-8 CSV strings; all money is handled
with decimal fixed-point and emitted as integer cents.
"""

import csv
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_FIELDS = ["order_id", "customer", "amount", "status", "created_at"]
_REFUND_FIELDS_V1 = ["refund_id", "order_id", "amount"]
_REFUND_FIELDS_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]

_CUTOFF_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_VALID_REFUND_STATUSES = ("succeeded", "pending")


def _is_amount_text(text, max_decimals):
    """True if text is digits with an optional fraction of <= max_decimals."""
    if not text:
        return False
    if "." in text:
        parts = text.split(".")
        if len(parts) != 2:
            return False
        whole, frac = parts
        if not whole.isdigit() or not frac.isdigit():
            return False
        if max_decimals is not None and len(frac) > max_decimals:
            return False
    else:
        if not text.isdigit():
            return False
    return True


def _parse_amount_cents(raw, context, max_decimals):
    """Parse a non-negative decimal string to integer cents.

    max_decimals=2 (v1) rejects more than two decimals; max_decimals=None
    (v2) allows any number of decimals and rounds ROUND_HALF_UP to cents.
    Rejects negatives, NaN/Infinity and scientific notation. Uses Decimal,
    never float.
    """
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = raw.strip()
    if not _is_amount_text(text, max_decimals):
        raise ValueError("%s: invalid amount %r" % (context, raw))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if not value.is_finite() or value < 0:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    cents = value * Decimal(100)
    if max_decimals is None:
        cents = cents.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    elif cents != cents.to_integral_value():
        raise ValueError("%s: amount exceeds two decimals %r" % (context, raw))
    return int(cents.to_integral_value())


def _read_rows(csv_text, required_fields, name):
    """Read a CSV string into a list of dicts; validate the header."""
    if csv_text is None:
        raise ValueError("%s: input must be a string" % name)
    reader = csv.reader(io.StringIO(csv_text))
    rows = []
    header = None
    for row in reader:
        if not row:
            continue  # skip blank lines
        if header is None:
            header = [field.strip() for field in row]
            for field in required_fields:
                if field not in header:
                    raise ValueError("%s: missing column %r" % (name, field))
            continue
        record = {}
        for index, field in enumerate(header):
            value = row[index] if index < len(row) else ""
            record[field] = value.strip() if value else ""
        rows.append(record)
    if header is None:
        # Completely empty input: treat like an empty table with zero rows.
        return []
    return rows


def _dedupe(rows, id_field, name):
    """Deduplicate rows by id: exact duplicates collapse; conflicts raise."""
    unique = {}
    for record in rows:
        key = record.get(id_field, "")
        if not key:
            raise ValueError("%s: empty %s" % (name, id_field))
        if key in unique:
            if unique[key] != record:
                raise ValueError(
                    "%s: conflicting rows for %s %r" % (name, id_field, key)
                )
            continue
        unique[key] = record
    return unique


def _validate_cutoff(cutoff):
    if not isinstance(cutoff, str) or not cutoff:
        raise ValueError("v2 requires a cutoff (YYYY-MM-DDTHH:MM:SSZ)")
    try:
        datetime.strptime(cutoff, _CUTOFF_FORMAT)
    except ValueError:
        raise ValueError("invalid cutoff format %r" % (cutoff,))
    return cutoff


def _require_timestamp(value, context):
    if not value:
        raise ValueError("%s: missing created_at" % context)
    return value


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds.

    policy="v1": legacy contract (2-decimal amounts, all refunds valid).
    policy="v2": cutoff required; only paid orders with created_at <= cutoff
    and succeeded refunds with created_at <= cutoff count; amounts may have
    many decimals and are rounded ROUND_HALF_UP to cents per row.

    Returns {"orders": [...], "customers": [...], "totals": {...}} with all
    amounts as integer cents. Orders sorted by order_id, customers by name.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))

    if policy == "v2":
        cutoff = _validate_cutoff(cutoff)
        max_decimals = None
        refund_fields = _REFUND_FIELDS_V2
    else:
        max_decimals = 2
        refund_fields = _REFUND_FIELDS_V1

    order_rows = _read_rows(orders_csv, _ORDER_FIELDS, "orders")
    refund_rows = _read_rows(refunds_csv, refund_fields, "refunds")

    # Dedupe first: conflicts must raise even for pending/after-cutoff rows.
    orders = _dedupe(order_rows, "order_id", "orders")
    refunds = _dedupe(refund_rows, "refund_id", "refunds")

    # Paid orders within the cutoff window.
    paid_cents_by_order = {}
    excluded_paid_ids = set()  # paid but after cutoff (v2 only)
    for order_id, record in orders.items():
        if record.get("status") != "paid":
            continue  # cancelled (and any non-paid) orders are excluded
        paid_cents_by_order[order_id] = _parse_amount_cents(
            record.get("amount"), "orders %s" % order_id, max_decimals
        )
        if policy == "v2":
            created_at = _require_timestamp(
                record.get("created_at"), "orders %s" % order_id
            )
            if created_at > cutoff:
                excluded_paid_ids.add(order_id)
                del paid_cents_by_order[order_id]

    refund_cents_by_order = {}
    for refund_id, record in refunds.items():
        order_id = record.get("order_id", "")

        if policy == "v2":
            status = record.get("status", "")
            if status not in _VALID_REFUND_STATUSES:
                raise ValueError(
                    "refunds %s: invalid status %r" % (refund_id, status)
                )
            created_at = _require_timestamp(
                record.get("created_at"), "refunds %s" % refund_id
            )
            if status != "succeeded" or created_at > cutoff:
                continue  # pending or after cutoff: not counted
        # v1: all refunds are valid.

        if order_id not in paid_cents_by_order:
            if order_id in excluded_paid_ids:
                continue  # order exists but excluded by cutoff: ignore
            if order_id in orders:
                raise ValueError(
                    "refunds %s: refund against cancelled order %s"
                    % (refund_id, order_id)
                )
            raise ValueError(
                "refunds %s: unknown order %s" % (refund_id, order_id)
            )
        cents = _parse_amount_cents(
            record.get("amount"), "refunds %s" % refund_id, max_decimals
        )
        refund_cents_by_order[order_id] = (
            refund_cents_by_order.get(order_id, 0) + cents
        )

    for order_id, total_refund in refund_cents_by_order.items():
        if total_refund > paid_cents_by_order[order_id]:
            raise ValueError(
                "order %s: refunds exceed paid amount" % order_id
            )

    result_orders = []
    customer_net = {}
    totals_paid = 0
    totals_refund = 0
    for order_id in sorted(paid_cents_by_order):
        record = orders[order_id]
        paid = paid_cents_by_order[order_id]
        refund = refund_cents_by_order.get(order_id, 0)
        net = paid - refund
        customer = record.get("customer", "")
        result_orders.append(
            {
                "order_id": order_id,
                "customer": customer,
                "paid_cents": paid,
                "refund_cents": refund,
                "net_cents": net,
            }
        )
        customer_net[customer] = customer_net.get(customer, 0) + net
        totals_paid += paid
        totals_refund += refund

    result_customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]

    return {
        "orders": result_orders,
        "customers": result_customers,
        "totals": {
            "paid_cents": totals_paid,
            "refund_cents": totals_refund,
            "net_cents": totals_paid - totals_refund,
        },
    }


def _csv_text(header, rows):
    """Render rows (lists of strings) as CSV text with the given header."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """Render a reconcile result into the release bundle files.

    Returns exactly {"orders.csv", "customers.csv", "summary.json"}:
    - orders.csv / customers.csv keep the reconcile row order and use
      integer-cent text values, written with the standard csv writer.
    - summary.json is exactly result["totals"] as JSON.
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a reconcile result dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError("result missing %r" % key)

    order_rows = []
    for entry in result["orders"]:
        order_rows.append(
            [
                str(entry["order_id"]),
                str(entry["customer"]),
                str(int(entry["paid_cents"])),
                str(int(entry["refund_cents"])),
                str(int(entry["net_cents"])),
            ]
        )
    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        order_rows,
    )

    customer_rows = [
        [str(entry["customer"]), str(int(entry["net_cents"]))]
        for entry in result["customers"]
    ]
    customers_csv = _csv_text(["customer", "net_cents"], customer_rows)

    summary_json = json.dumps(result["totals"])

    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
