"""Order reconciliation, v1 + v2 contracts (see spec-v1.md, spec-v2.md).

Pure functions only: no file, network, or process access.
Amounts are parsed with decimal fixed-point (never float*100).
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_FIELDS = ["order_id", "customer", "amount", "status", "created_at"]
_REFUND_FIELDS_V1 = ["refund_id", "order_id", "amount"]
_REFUND_FIELDS_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]

_DIGITS = set("0123456789")


def _is_digits(text):
    return bool(text) and _DIGITS.issuperset(text)


def _is_valid_amount_text(text, max_decimals):
    """True for non-negative decimal strings with at most max_decimals places.

    max_decimals=None means any number of decimal places (v2).
    """
    if not text:
        return False
    if "." in text:
        parts = text.split(".")
        if len(parts) != 2:
            return False
        int_part, frac_part = parts
        if not _is_digits(int_part):
            return False
        if not _is_digits(frac_part):
            return False
        if max_decimals is not None and len(frac_part) > max_decimals:
            return False
        return True
    return _is_digits(text)


def _parse_amount_cents(raw, max_decimals=2):
    """Return integer cents for an amount string, or raise ValueError.

    max_decimals=2 (v1): at most two decimal places, exact cents.
    max_decimals=None (v2): any decimals, rounded HALF_UP to whole cents.
    Always rejects NaN, Infinity, negatives, and empty strings.
    """
    if raw is None:
        raise ValueError("missing amount")
    text = raw.strip()
    if not _is_valid_amount_text(text, max_decimals):
        lowered = text.lower()
        if text.startswith("-"):
            raise ValueError("negative amount: %r" % raw)
        if lowered in ("nan", "+nan", "-nan", "inf", "+inf", "-inf",
                       "infinity", "+infinity", "-infinity"):
            raise ValueError("non-finite amount: %r" % raw)
        raise ValueError("invalid amount: %r" % raw)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % raw)
    if not value.is_finite() or value < 0:
        raise ValueError("invalid amount: %r" % raw)
    cents = (value * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _is_valid_utc_ts(text):
    """True for canonical YYYY-MM-DDTHH:MM:SSZ strings."""
    if not isinstance(text, str) or len(text) != 20:
        return False
    if (text[4] != "-" or text[7] != "-" or text[10] != "T"
            or text[13] != ":" or text[16] != ":" or text[19] != "Z"):
        return False
    for idx in (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18):
        if text[idx] not in _DIGITS:
            return False
    month = int(text[5:7])
    day = int(text[8:10])
    hour = int(text[11:13])
    minute = int(text[14:16])
    second = int(text[17:19])
    if not 1 <= month <= 12:
        return False
    if not 1 <= day <= 31:
        return False
    if hour > 23 or minute > 59 or second > 59:
        return False
    return True


def _read_rows(csv_text, expected_fields, label):
    """Parse a CSV string into a list of dicts keyed by expected fields.

    The header must match expected_fields exactly. Returns [] for an
    empty body (header-only input).
    """
    if csv_text is None:
        raise ValueError("%s input is None" % label)
    reader = csv.reader(io.StringIO(csv_text), skipinitialspace=True)
    rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("%s input missing header" % label)
    header = [cell.strip() for cell in rows[0]]
    if header != expected_fields:
        raise ValueError("%s header mismatch: %r" % (label, header))
    out = []
    for row in rows[1:]:
        if len(row) != len(expected_fields):
            raise ValueError("%s row has wrong field count: %r" % (label, row))
        out.append({name: cell.strip() for name, cell in zip(expected_fields, row)})
    return out


def _dedupe(rows, id_field, label):
    """Dedupe by id: identical rows collapse; conflicting rows raise.

    Runs before any filtering so conflicts in pending or after-cutoff
    rows are still rejected.
    """
    by_id = {}
    for row in rows:
        key = row[id_field]
        if not key:
            raise ValueError("%s row with empty %s" % (label, id_field))
        prev = by_id.get(key)
        if prev is None:
            by_id[key] = row
        elif prev != row:
            raise ValueError("conflicting rows for %s %r in %s"
                             % (id_field, key, label))
    return by_id


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds.

    policy="v1": legacy contract (strict 2-decimal amounts, 3-column
    refunds, no cutoff).
    policy="v2": cutoff (YYYY-MM-DDTHH:MM:SSZ) required; only paid
    orders with created_at <= cutoff count; only succeeded refunds with
    created_at <= cutoff count; amounts may have any decimals and are
    rounded HALF_UP to cents per row before summing.

    Returns {"orders": [...], "customers": [...], "totals": {...}} with
    all money as integer cents. Raises ValueError on any contract
    violation (bad amounts, conflicting duplicate ids, orphan or
    cancelled-order refunds, over-refunds, unknown policy, missing or
    malformed cutoff).
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v2":
        if cutoff is None:
            raise ValueError("v2 policy requires a cutoff")
        cutoff = cutoff.strip() if isinstance(cutoff, str) else cutoff
        if not _is_valid_utc_ts(cutoff):
            raise ValueError("invalid cutoff: %r" % (cutoff,))

    max_decimals = 2 if policy == "v1" else None
    refund_fields = _REFUND_FIELDS_V1 if policy == "v1" else _REFUND_FIELDS_V2

    order_rows = _read_rows(orders_csv, _ORDER_FIELDS, "orders")
    refund_rows = _read_rows(refunds_csv, refund_fields, "refunds")

    # Dedupe first: conflicts are rejected even in rows that are later
    # filtered out (pending / after-cutoff).
    orders_by_id = _dedupe(order_rows, "order_id", "orders")
    refunds_by_id = _dedupe(refund_rows, "refund_id", "refunds")

    paid = {}          # order_id -> {order_id, customer, paid_cents}
    cancelled = set()  # cancelled order ids (any date)
    known_order_ids = set(orders_by_id)
    for order_id, row in orders_by_id.items():
        status = row["status"].lower()
        if status == "cancelled":
            cancelled.add(order_id)
            continue
        if status != "paid":
            raise ValueError("unknown order status: %r" % row["status"])
        created_at = row["created_at"]
        if policy == "v2":
            if not _is_valid_utc_ts(created_at):
                raise ValueError("invalid order created_at: %r" % created_at)
            if created_at > cutoff:
                # After-cutoff orders are excluded entirely.
                continue
        paid[order_id] = {
            "order_id": order_id,
            "customer": row["customer"],
            "paid_cents": _parse_amount_cents(row["amount"], max_decimals),
        }

    refund_cents_by_order = {oid: 0 for oid in paid}
    for refund_id, row in refunds_by_id.items():
        order_id = row["order_id"]
        if policy == "v2":
            status = row["status"].lower()
            if status not in ("succeeded", "pending"):
                raise ValueError("unknown refund status: %r" % row["status"])
            created_at = row["created_at"]
            if not _is_valid_utc_ts(created_at):
                raise ValueError("invalid refund created_at: %r" % created_at)
            if status == "pending" or created_at > cutoff:
                # Pending and after-cutoff refunds do not count; they are
                # not "valid" refunds, so they never raise for orphans.
                continue
        amount = _parse_amount_cents(row["amount"], max_decimals)
        if order_id in cancelled:
            raise ValueError("refund %r targets cancelled order %r"
                             % (refund_id, order_id))
        if order_id not in known_order_ids:
            raise ValueError("refund %r targets unknown order %r"
                             % (refund_id, order_id))
        if order_id not in paid:
            # Order exists but was excluded by the cutoff: ignore.
            continue
        refund_cents_by_order[order_id] += amount

    for order_id, refunded in refund_cents_by_order.items():
        if refunded > paid[order_id]["paid_cents"]:
            raise ValueError("order %r refunded %d cents exceeds paid %d cents"
                             % (order_id, refunded, paid[order_id]["paid_cents"]))

    orders_out = []
    customer_totals = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(paid):
        entry = paid[order_id]
        refunded = refund_cents_by_order[order_id]
        net = entry["paid_cents"] - refunded
        orders_out.append({
            "order_id": order_id,
            "customer": entry["customer"],
            "paid_cents": entry["paid_cents"],
            "refund_cents": refunded,
            "net_cents": net,
        })
        customer_totals[entry["customer"]] = (
            customer_totals.get(entry["customer"], 0) + net)
        total_paid += entry["paid_cents"]
        total_refund += refunded

    customers_out = [
        {"customer": name, "net_cents": customer_totals[name]}
        for name in sorted(customer_totals)
    ]

    return {
        "orders": orders_out,
        "customers": customers_out,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def _csv_text(header, rows):
    """Render rows (list of lists) as CSV text with a header, via csv.writer."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Serialize a reconcile result into the release bundle.

    Per release-spec.md the bundle is exactly three files:
      - orders.csv:    order_id,customer,paid_cents,refund_cents,net_cents
      - customers.csv: customer,net_cents
      - summary.json:  exactly result["totals"]
    Row order follows reconcile ordering; money values are integer text.
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError("result missing %r" % key)

    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [[entry["order_id"], entry["customer"],
          int(entry["paid_cents"]), int(entry["refund_cents"]),
          int(entry["net_cents"])]
         for entry in result["orders"]],
    )
    customers_csv = _csv_text(
        ["customer", "net_cents"],
        [[entry["customer"], int(entry["net_cents"])]
         for entry in result["customers"]],
    )
    summary_json = json.dumps(result["totals"], sort_keys=True)

    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
