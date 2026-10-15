"""Order reconciliation (spec v1 + v2) and release bundle (release-spec).

Pure functions only: no file, network or process access.
Amounts are handled as decimal strings and converted to integer cents
without using binary floating point.
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_HEADER = ["order_id", "customer", "amount", "status", "created_at"]
_REFUND_HEADER_V1 = ["refund_id", "order_id", "amount"]
_REFUND_HEADER_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]

_DIGITS = "0123456789"
_CUTOFF_LEN = len("2026-10-04T00:00:00Z")


def _is_amount_text(text, max_dp=None):
    """Strict check: unsigned decimal, optional fraction up to max_dp."""
    if text == "":
        return False
    int_part, dot, frac_part = text.partition(".")
    if int_part == "":
        return False
    for ch in int_part:
        if ch not in _DIGITS:
            return False
    if dot == "":
        return True
    if len(frac_part) == 0:
        return False
    if max_dp is not None and len(frac_part) > max_dp:
        return False
    for ch in frac_part:
        if ch not in _DIGITS:
            return False
    return True


def _parse_amount_cents(raw, what, max_dp=None):
    """Return integer cents for a non-negative decimal string.

    With max_dp set (v1) more decimals are rejected; otherwise (v2) the
    value is rounded to cents with Decimal ROUND_HALF_UP.
    """
    if raw is None:
        raise ValueError("%s: missing amount" % what)
    text = str(raw).strip()
    if not _is_amount_text(text, max_dp):
        # Rejects NaN, Infinity, negatives, too many decimals, exotic forms.
        raise ValueError("%s: invalid amount %r" % (what, raw))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (what, raw))
    if not value.is_finite() or value < 0:
        raise ValueError("%s: invalid amount %r" % (what, raw))
    cents = value.scaleb(2)
    if max_dp is not None:
        if cents != cents.to_integral_value():
            raise ValueError("%s: more than two decimals %r" % (what, raw))
        return int(cents)
    return int(cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _validate_cutoff(cutoff):
    if not isinstance(cutoff, str) or len(cutoff) != _CUTOFF_LEN:
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ, got %r" % (cutoff,))
    ok = (
        cutoff[4] == "-" and cutoff[7] == "-"
        and cutoff[10] == "T" and cutoff[13] == ":" and cutoff[16] == ":"
        and cutoff[19] == "Z"
    )
    digits_at = [0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18]
    if not ok or any(cutoff[i] not in _DIGITS for i in digits_at):
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ, got %r" % (cutoff,))
    return cutoff


def _read_rows(csv_text, expected_header, what):
    """Return list of row tuples (raw stripped strings) for a CSV string."""
    if csv_text is None:
        raise ValueError("%s: input must be a string" % what)
    text = csv_text
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.reader(text.splitlines())
    rows = []
    header = None
    for line in reader:
        if not line or all((cell is None or cell.strip() == "") for cell in line):
            continue
        if header is None:
            header = tuple(cell.strip() for cell in line)
            if header != tuple(expected_header):
                raise ValueError(
                    "%s: expected header %s, got %s" % (what, list(expected_header), list(header))
                )
            continue
        if len(line) != len(expected_header):
            raise ValueError(
                "%s: row has %d fields, expected %d" % (what, len(line), len(expected_header))
            )
        rows.append(tuple(cell.strip() for cell in line))
    if header is None:
        raise ValueError("%s: header row is required" % what)
    return rows


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile orders against refunds (policies v1 and v2).

    Returns a dict with ``orders`` (sorted by order_id), ``customers``
    (sorted by customer) and ``totals``; all money values are integer cents.
    v2 adds a required UTC cutoff, refund status and ROUND_HALF_UP amounts.
    """
    if policy == "v1":
        max_dp = 2
        refund_header = _REFUND_HEADER_V1
        cutoff = None  # cutoff is not part of v1 semantics
    elif policy == "v2":
        if cutoff is None:
            raise ValueError("policy v2 requires a cutoff")
        max_dp = None
        refund_header = _REFUND_HEADER_V2
        _validate_cutoff(cutoff)
    else:
        raise ValueError("unsupported policy %r" % (policy,))

    order_header = _ORDER_HEADER

    def within_cutoff(created_at):
        if cutoff is None:
            return True
        return created_at <= cutoff  # canonical UTC strings: lexicographic

    # ---- orders: dedupe by order_id -------------------------------------
    orders = {}
    for row in _read_rows(orders_csv, order_header, "orders"):
        record = dict(zip(order_header, row))
        order_id = record["order_id"]
        if order_id == "":
            raise ValueError("orders: order_id is required")
        if record["customer"] == "":
            raise ValueError("orders: customer is required for order %s" % order_id)
        if record["status"] not in ("paid", "cancelled"):
            raise ValueError(
                "orders: unknown status %r for order %s" % (record["status"], order_id)
            )
        paid_cents = _parse_amount_cents(
            record["amount"], "orders %s amount" % order_id, max_dp
        )
        existing = orders.get(order_id)
        if existing is not None:
            if existing[0] != row:
                raise ValueError("orders: conflicting rows for order_id %s" % order_id)
            continue
        orders[order_id] = (row, record["customer"], record["status"],
                            paid_cents, record["created_at"])

    # ---- refunds: dedupe by refund_id -------------------------------------
    refunds = {}
    for row in _read_rows(refunds_csv, refund_header, "refunds"):
        record = dict(zip(refund_header, row))
        refund_id = record["refund_id"]
        if refund_id == "":
            raise ValueError("refunds: refund_id is required")
        if policy == "v2" and record["status"] not in ("succeeded", "pending"):
            raise ValueError(
                "refunds: unknown status %r for refund %s" % (record["status"], refund_id)
            )
        refund_cents = _parse_amount_cents(
            record["amount"], "refunds %s amount" % refund_id, max_dp
        )
        existing = refunds.get(refund_id)
        if existing is not None:
            if existing[0] != row:
                raise ValueError("refunds: conflicting rows for refund_id %s" % refund_id)
            continue
        status = record["status"] if policy == "v2" else "succeeded"
        created_at = record["created_at"] if policy == "v2" else ""
        refunds[refund_id] = (row, record["order_id"], refund_cents,
                              status, created_at)

    # ---- validate refunds against orders -----------------------------------
    refund_by_order = {}
    for refund_id in sorted(refunds):
        _, order_id, refund_cents, status, created_at = refunds[refund_id]
        effective = (status == "succeeded") and within_cutoff(created_at)
        order = orders.get(order_id)
        if order is None:
            # v2: pending / post-cutoff refunds referencing unknown orders
            # are ignored; effective (succeeded, in-window) ones are errors.
            if policy == "v2" and not effective:
                continue
            raise ValueError("refunds: unknown order %s for refund %s" % (order_id, refund_id))
        _, _, order_status, paid_cents, order_created = order
        if order_status != "paid":
            if policy == "v2" and not effective:
                continue
            raise ValueError("refunds: order %s is not paid (refund %s)" % (order_id, refund_id))
        if not effective:
            continue  # pending or post-cutoff refund: not counted
        if not within_cutoff(order_created):
            continue  # order excluded by cutoff: ignore its refunds
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + refund_cents
        if refund_by_order[order_id] > paid_cents:
            raise ValueError(
                "refunds: refund total %d exceeds paid %d for order %s"
                % (refund_by_order[order_id], paid_cents, order_id)
            )

    # ---- build result ---------------------------------------------------------
    result_orders = []
    totals_paid = 0
    totals_refund = 0
    for order_id in sorted(orders):
        _, customer, order_status, paid_cents, order_created = orders[order_id]
        if order_status != "paid":
            continue
        if not within_cutoff(order_created):
            continue
        refund_cents = refund_by_order.get(order_id, 0)
        result_orders.append(
            {
                "order_id": order_id,
                "customer": customer,
                "paid_cents": paid_cents,
                "refund_cents": refund_cents,
                "net_cents": paid_cents - refund_cents,
            }
        )
        totals_paid += paid_cents
        totals_refund += refund_cents

    customer_totals = {}
    for item in result_orders:
        customer_totals[item["customer"]] = (
            customer_totals.get(item["customer"], 0) + item["net_cents"]
        )

    customers = [
        {"customer": name, "net_cents": customer_totals[name]}
        for name in sorted(customer_totals)
    ]

    return {
        "orders": result_orders,
        "customers": customers,
        "totals": {
            "paid_cents": totals_paid,
            "refund_cents": totals_refund,
            "net_cents": totals_paid - totals_refund,
        },
    }


def _csv_text(header, rows):
    """Render rows (list of lists of strings) with the standard csv writer."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Render a reconcile result as the release bundle (release-spec).

    Returns exactly three files: orders.csv, customers.csv and summary.json.
    Row order follows the reconcile ordering; money values are integer text;
    summary.json parses back to exactly result["totals"].
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError("result is missing %r" % key)
    totals = result["totals"]
    for key in ("paid_cents", "refund_cents", "net_cents"):
        if key not in totals or not isinstance(totals[key], int):
            raise ValueError("totals.%s must be an integer" % key)

    order_rows = []
    for item in result["orders"]:
        order_rows.append(
            [
                str(item["order_id"]),
                str(item["customer"]),
                str(int(item["paid_cents"])),
                str(int(item["refund_cents"])),
                str(int(item["net_cents"])),
            ]
        )
    customer_rows = []
    for item in result["customers"]:
        customer_rows.append([str(item["customer"]), str(int(item["net_cents"]))])

    summary = json.dumps(
        {
            "paid_cents": totals["paid_cents"],
            "refund_cents": totals["refund_cents"],
            "net_cents": totals["net_cents"],
        },
        sort_keys=True,
    )

    return {
        "orders.csv": _csv_text(
            ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
            order_rows,
        ),
        "customers.csv": _csv_text(["customer", "net_cents"], customer_rows),
        "summary.json": summary,
    }
