"""Order reconciliation, spec-v1 and spec-v2 contracts.

reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None) -> dict
export_bundle(result) -> dict[str, str] per release-spec.
Pure functions only; no file/network/process access. Fixed-point decimal
money, output in integer cents.
"""

import csv
import datetime
import io
import json
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

_ORDER_FIELDS = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_FIELDS_V1 = ("refund_id", "order_id", "amount")
_REFUND_FIELDS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")

_CUTOFF_LEN = len("YYYY-MM-DDTHH:MM:SSZ")


def _valid_cutoff(cutoff):
    """Strict YYYY-MM-DDTHH:MM:SSZ check (fixed-width, zero padded)."""
    if not isinstance(cutoff, str) or len(cutoff) != _CUTOFF_LEN:
        return False
    digit_positions = [0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18]
    for i in digit_positions:
        if not cutoff[i].isdigit():
            return False
    fixed = {4: "-", 7: "-", 10: "T", 13: ":", 16: ":", 19: "Z"}
    for i, ch in fixed.items():
        if cutoff[i] != ch:
            return False
    try:
        datetime.datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _parse_amount_cents(raw, what, max_decimals=2):
    """Non-negative plain decimal amount -> integer cents.

    max_decimals=2 (v1): reject more than two decimals.
    max_decimals=None (v2): allow many decimals, ROUND_HALF_UP to cents.
    Always rejects NaN, Infinity, signs, exponents and junk text.
    Uses Decimal fixed-point; never float*100.
    """
    if raw is None:
        raise ValueError("%s: missing amount" % what)
    text = raw.strip()
    if not text:
        raise ValueError("%s: empty amount" % what)
    if text[0] in "+-":
        raise ValueError("%s: invalid amount %r" % (what, raw))
    if "e" in text or "E" in text:
        raise ValueError("%s: invalid amount %r" % (what, raw))
    parts = text.split(".")
    if len(parts) > 2:
        raise ValueError("%s: invalid amount %r" % (what, raw))
    int_part = parts[0]
    frac_part = parts[1] if len(parts) == 2 else ""
    if int_part and not int_part.isdigit():
        raise ValueError("%s: invalid amount %r" % (what, raw))
    if frac_part and not frac_part.isdigit():
        raise ValueError("%s: invalid amount %r" % (what, raw))
    if not int_part and not frac_part:
        raise ValueError("%s: invalid amount %r" % (what, raw))
    if max_decimals is not None and len(frac_part) > max_decimals:
        raise ValueError(
            "%s: amount %r has more than %d decimals" % (what, raw, max_decimals)
        )
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (what, raw))
    cents = (value * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _read_rows(csv_text, expected_fields, what):
    if not isinstance(csv_text, str):
        raise ValueError("%s input must be a string" % what)
    reader = csv.DictReader(io.StringIO(csv_text, newline=""))
    if reader.fieldnames is None:
        # Completely empty input: treat like header-only empty table.
        return []
    if tuple(reader.fieldnames) != expected_fields:
        raise ValueError("%s: unexpected header %r" % (what, reader.fieldnames))
    rows = []
    for row in reader:
        if any(v is None for v in row.values()):
            raise ValueError("%s: malformed row %r" % (what, row))
        rows.append(row)
    return rows


def _dedupe(rows, key_field, what):
    """Exact duplicates collapse; same key with different fields -> error.

    Applies to every row, including rows that would later be filtered out
    (pending / after-cutoff), per spec-v2.
    """
    seen = {}
    unique = []
    for row in rows:
        key = row[key_field]
        if key in seen:
            if seen[key] != row:
                raise ValueError(
                    "%s: duplicate %s=%r with differing fields"
                    % (what, key_field, key)
                )
            continue
        seen[key] = row
        unique.append(row)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v2":
        if cutoff is None:
            raise ValueError("policy v2 requires cutoff")
        if not _valid_cutoff(cutoff):
            raise ValueError("invalid cutoff %r" % (cutoff,))

    refund_fields = _REFUND_FIELDS_V2 if policy == "v2" else _REFUND_FIELDS_V1
    max_decimals = None if policy == "v2" else 2

    order_rows = _dedupe(
        _read_rows(orders_csv, _ORDER_FIELDS, "orders"), "order_id", "orders"
    )
    refund_rows = _dedupe(
        _read_rows(refunds_csv, refund_fields, "refunds"), "refund_id", "refunds"
    )

    # Register every order (paid or not) so refunds can be validated.
    orders = {}
    for row in order_rows:
        order_id = row["order_id"]
        if order_id == "":
            raise ValueError("orders: empty order_id")
        orders[order_id] = {
            "customer": row["customer"],
            "status": row["status"].strip().lower(),
            "created_at": row["created_at"],
            "paid_cents": _parse_amount_cents(
                row["amount"], "order %s" % order_id, max_decimals
            ),
            "refund_cents": 0,
        }

    for row in refund_rows:
        refund_id = row["refund_id"]
        order_id = row["order_id"]
        if refund_id == "" or order_id == "":
            raise ValueError("refunds: empty refund_id/order_id")

        if policy == "v2":
            status = row["status"].strip().lower()
            if status not in ("succeeded", "pending"):
                raise ValueError("refunds: %s bad status %r"
                                 % (refund_id, row["status"]))
            created_at = row["created_at"]
            if status != "succeeded" or created_at > cutoff:
                # pending or after-cutoff refunds are not counted at all.
                continue

        order = orders.get(order_id)
        if order is None:
            raise ValueError("refunds: %s references unknown order %r"
                             % (refund_id, order_id))
        if order["status"] != "paid":
            raise ValueError("refunds: %s references non-paid order %r"
                             % (refund_id, order_id))
        if policy == "v2" and order["created_at"] > cutoff:
            # Order exists but is excluded by cutoff: ignore the refund.
            continue

        refund_cents = _parse_amount_cents(
            row["amount"], "refund %s" % refund_id, max_decimals
        )
        if order["refund_cents"] + refund_cents > order["paid_cents"]:
            raise ValueError(
                "refunds: %s makes refunds exceed paid amount for order %r"
                % (refund_id, order_id)
            )
        order["refund_cents"] += refund_cents

    result_orders = []
    customers = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(orders):
        order = orders[order_id]
        if order["status"] != "paid":
            continue
        if policy == "v2" and order["created_at"] > cutoff:
            continue
        paid = order["paid_cents"]
        refund = order["refund_cents"]
        net = paid - refund
        result_orders.append({
            "order_id": order_id,
            "customer": order["customer"],
            "paid_cents": paid,
            "refund_cents": refund,
            "net_cents": net,
        })
        customers[order["customer"]] = customers.get(order["customer"], 0) + net
        totals["paid_cents"] += paid
        totals["refund_cents"] += refund
        totals["net_cents"] += net

    return {
        "orders": result_orders,
        "customers": [
            {"customer": name, "net_cents": customers[name]}
            for name in sorted(customers)
        ],
        "totals": totals,
    }


def _require_int(value, what):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be an integer, got %r" % (what, value))
    return value


def export_bundle(result):
    """Render a reconcile() result into the release bundle.

    Returns exactly three files: orders.csv, customers.csv, summary.json.
    Amounts are written as integer text; row order follows reconcile's
    sorting; summary.json is exactly result["totals"].
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError("result missing %r" % key)

    orders_buf = io.StringIO()
    orders_writer = csv.writer(orders_buf, lineterminator="\n")
    orders_writer.writerow(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"]
    )
    for row in result["orders"]:
        orders_writer.writerow([
            row["order_id"],
            row["customer"],
            _require_int(row["paid_cents"], "order paid_cents"),
            _require_int(row["refund_cents"], "order refund_cents"),
            _require_int(row["net_cents"], "order net_cents"),
        ])

    customers_buf = io.StringIO()
    customers_writer = csv.writer(customers_buf, lineterminator="\n")
    customers_writer.writerow(["customer", "net_cents"])
    for row in result["customers"]:
        customers_writer.writerow([
            row["customer"],
            _require_int(row["net_cents"], "customer net_cents"),
        ])

    totals = result["totals"]
    summary = {
        "paid_cents": _require_int(totals["paid_cents"], "totals paid_cents"),
        "refund_cents": _require_int(totals["refund_cents"], "totals refund_cents"),
        "net_cents": _require_int(totals["net_cents"], "totals net_cents"),
    }

    return {
        "orders.csv": orders_buf.getvalue(),
        "customers.csv": customers_buf.getvalue(),
        "summary.json": json.dumps(summary),
    }
