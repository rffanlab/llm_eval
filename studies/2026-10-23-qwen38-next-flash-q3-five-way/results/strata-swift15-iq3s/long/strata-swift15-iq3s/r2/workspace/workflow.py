"""Order reconciliation pipeline (spec v1 + v2) and release bundle.

Pure functions only. Inputs are UTF-8 CSV strings; outputs use integer cents.
No file/network/process access; only stdlib csv/io/datetime/decimal/json.
"""

import csv
import io
import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

_ORDER_COLUMNS = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_COLUMNS_V1 = ("refund_id", "order_id", "amount")
_REFUND_COLUMNS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")

_CUTOFF_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _is_amount_string(s, max_decimals):
    """Return True if s is a plain non-negative decimal with <=max_decimals.

    Accepts forms like "0", "10", "10.1", "10.10", "10.105". Rejects signs,
    exponents, NaN/Infinity, empty, multiple dots, leading zeros like "01".
    """
    if not s:
        return False
    if not all(c.isdigit() or c == "." for c in s):
        return False
    parts = s.split(".")
    if len(parts) > 2:
        return False
    int_part = parts[0]
    frac_part = parts[1] if len(parts) == 2 else "0"
    if not int_part:
        return False
    if len(int_part) > 1 and int_part[0] == "0":
        return False
    if len(frac_part) > max_decimals:
        return False
    return True


def _parse_amount_cents(raw, context, max_decimals):
    """Parse a non-negative decimal string into integer cents.

    v1 (max_decimals=2): reject more than 2 decimals.
    v2: ROUND_HALF_UP to integer cents, per row.
    Uses Decimal fixed-point; never float multiplication.
    """
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    s = raw.strip()
    if not _is_amount_string(s, max_decimals):
        raise ValueError("%s: invalid amount %r" % (context, raw))
    value = Decimal(s)
    cents = value * Decimal(100)
    if max_decimals <= 2:
        if cents != cents.to_integral_value():
            raise ValueError(
                "%s: amount %r has more than 2 decimals" % (context, raw)
            )
        return int(cents.to_integral_value())
    return int(cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _validate_timestamp(s, context):
    try:
        datetime.strptime(s, _CUTOFF_FORMAT)
    except (ValueError, TypeError):
        raise ValueError("%s: invalid UTC timestamp %r" % (context, s))
    return s


def _read_rows(csv_text, required_columns, kind):
    if csv_text is None:
        raise ValueError("%s: input is None" % kind)
    if not isinstance(csv_text, str):
        raise ValueError("%s: input must be a string" % kind)
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        raise ValueError("%s: CSV is empty (missing header)" % kind)
    for col in required_columns:
        if col not in reader.fieldnames:
            raise ValueError("%s: missing column %r" % (kind, col))
    return list(reader)


def _field(row, name, context):
    value = row.get(name)
    if value is None:
        raise ValueError("%s: missing field %r" % (context, name))
    return value.strip()


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile orders and refunds per the v1/v2 contract.

    Returns {"orders": [...], "customers": [...], "totals": {...}} with all
    money values as integer cents. Raises ValueError on any contract violation.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    max_decimals = 2 if policy == "v1" else 10 ** 6
    if policy == "v2":
        if cutoff is None:
            raise ValueError("v2 requires a cutoff")
        _validate_timestamp(cutoff, "cutoff")
    # v1 ignores cutoff.

    # ---- Orders -----------------------------------------------------------
    orders_by_id = {}
    for row in _read_rows(orders_csv, _ORDER_COLUMNS, "orders"):
        context = "orders row"
        order_id = _field(row, "order_id", context)
        customer = _field(row, "customer", context)
        status = _field(row, "status", context).lower()
        created_at = _field(row, "created_at", context)
        amount_raw = _field(row, "amount", context)
        if not order_id:
            raise ValueError("orders row: empty order_id")
        if status not in ("paid", "cancelled"):
            raise ValueError("orders row: unknown status %r" % status)
        if policy == "v2":
            _validate_timestamp(created_at, "order %s created_at" % order_id)
        paid_cents = _parse_amount_cents(
            amount_raw, "order %s" % order_id, max_decimals
        )
        key = (order_id, customer, amount_raw, status, created_at)
        if order_id in orders_by_id:
            if orders_by_id[order_id]["key"] != key:
                raise ValueError(
                    "duplicate order_id %s with differing fields" % order_id
                )
            continue  # exact duplicate row: count once
        orders_by_id[order_id] = {
            "key": key,
            "order_id": order_id,
            "customer": customer,
            "status": status,
            "created_at": created_at,
            "paid_cents": paid_cents,
            "refund_cents": 0,
        }

    # ---- Refunds ----------------------------------------------------------
    refund_columns = (
        _REFUND_COLUMNS_V2 if policy == "v2" else _REFUND_COLUMNS_V1
    )
    refunds_seen = {}
    for row in _read_rows(refunds_csv, refund_columns, "refunds"):
        context = "refunds row"
        refund_id = _field(row, "refund_id", context)
        order_id = _field(row, "order_id", context)
        amount_raw = _field(row, "amount", context)
        if not refund_id:
            raise ValueError("refunds row: empty refund_id")
        if policy == "v2":
            status = _field(row, "status", context).lower()
            created_at = _field(row, "created_at", context)
            if status not in ("succeeded", "pending"):
                raise ValueError("refunds row: unknown status %r" % status)
            _validate_timestamp(created_at, "refund %s created_at" % refund_id)
        else:
            status = "succeeded"
            created_at = None
        refund_cents = _parse_amount_cents(
            amount_raw, "refund %s" % refund_id, max_decimals
        )
        key = (refund_id, order_id, amount_raw, status, created_at)
        if refund_id in refunds_seen:
            if refunds_seen[refund_id] != key:
                raise ValueError(
                    "duplicate refund_id %s with differing fields" % refund_id
                )
            continue  # exact duplicate row: count once
        refunds_seen[refund_id] = key
        # v2: pending or after-cutoff refunds are not counted at all.
        if policy == "v2" and (status != "succeeded" or created_at > cutoff):
            continue
        order = orders_by_id.get(order_id)
        if order is None:
            raise ValueError(
                "refund %s references unknown order %s" % (refund_id, order_id)
            )
        if order["status"] != "paid":
            raise ValueError(
                "refund %s targets non-paid order %s" % (refund_id, order_id)
            )
        # v2: refund for a paid order excluded by cutoff is ignored.
        if policy == "v2" and order["created_at"] > cutoff:
            continue
        order["refund_cents"] += refund_cents

    # ---- Validate cumulative refunds & build output -----------------------
    order_results = []
    customer_totals = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(orders_by_id):
        order = orders_by_id[order_id]
        if order["status"] != "paid":
            continue
        # v2: orders created after cutoff are excluded entirely.
        if policy == "v2" and order["created_at"] > cutoff:
            continue
        if order["refund_cents"] > order["paid_cents"]:
            raise ValueError(
                "order %s refunds (%d cents) exceed paid (%d cents)"
                % (order_id, order["refund_cents"], order["paid_cents"])
            )
        net_cents = order["paid_cents"] - order["refund_cents"]
        order_results.append(
            {
                "order_id": order["order_id"],
                "customer": order["customer"],
                "paid_cents": order["paid_cents"],
                "refund_cents": order["refund_cents"],
                "net_cents": net_cents,
            }
        )
        total_paid += order["paid_cents"]
        total_refund += order["refund_cents"]
        customer_totals[order["customer"]] = (
            customer_totals.get(order["customer"], 0) + net_cents
        )

    customers = [
        {"customer": name, "net_cents": customer_totals[name]}
        for name in sorted(customer_totals)
    ]
    return {
        "orders": order_results,
        "customers": customers,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def _rows_to_csv(header, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """Render a reconcile result into the release bundle files.

    Returns exactly {"orders.csv", "customers.csv", "summary.json"} as
    strings. CSV rows follow reconcile ordering with integer money text;
    summary.json is exactly result["totals"].
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError("result missing %r" % key)

    order_rows = []
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
    customer_rows = [
        [str(c["customer"]), str(int(c["net_cents"]))]
        for c in result["customers"]
    ]

    totals = result["totals"]
    summary = json.dumps(
        {
            "paid_cents": int(totals["paid_cents"]),
            "refund_cents": int(totals["refund_cents"]),
            "net_cents": int(totals["net_cents"]),
        }
    )

    return {
        "orders.csv": _rows_to_csv(
            ("order_id", "customer", "paid_cents", "refund_cents", "net_cents"),
            order_rows,
        ),
        "customers.csv": _rows_to_csv(("customer", "net_cents"), customer_rows),
        "summary.json": summary,
    }
