import csv
import io
import json
from decimal import Decimal, ROUND_HALF_UP

# v1 contract: fixed-point decimal money, at most 2 decimal places,
# non-negative, no NaN/Infinity, no scientific notation.
# v2 adds: cutoff filtering, refund status/created_at, and amounts with any
# number of decimals rounded HALF_UP to integer cents (per line, then summed).


def _is_valid_amount_text(text, max_decimals=None):
    """Plain validation of an amount string: digits with optional dot.

    max_decimals=None allows any number of decimals (v2); an int limits the
    number of digits after the dot (v1 uses 2).
    """
    if not text:
        return False
    digits_seen = False
    decimal_places = -1  # -1 means no dot seen yet
    for ch in text:
        if "0" <= ch <= "9":
            if decimal_places == -1:
                digits_seen = True
            elif decimal_places > 0:
                decimal_places -= 1
                digits_seen = True
            else:
                return False
        elif ch == "." and decimal_places == -1:
            if max_decimals == 0:
                return False
            decimal_places = max_decimals if max_decimals is not None else 10 ** 9
        else:
            return False
    return digits_seen


def _parse_amount_cents(raw, max_decimals=2):
    """Return integer cents for a validated amount string.

    max_decimals=2 enforces the v1 rule (at most two decimals, exact cents);
    max_decimals=None allows any decimals and rounds HALF_UP to cents.
    """
    if raw is None:
        raise ValueError("missing amount")
    text = raw.strip()
    if not _is_valid_amount_text(text, max_decimals):
        # Rejects negatives, NaN/Infinity, exponent forms, empty, bad decimals.
        raise ValueError("invalid amount: %r" % (raw,))
    value = Decimal(text)
    scaled = value.scaleb(2)
    if max_decimals is None:
        cents = scaled.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    else:
        if scaled != scaled.to_integral_value():
            raise ValueError("amount not representable in cents: %r" % (raw,))
        cents = scaled.to_integral_value()
    return int(cents)


def _is_valid_cutoff(text):
    """Validate canonical UTC cutoff: YYYY-MM-DDTHH:MM:SSZ."""
    if not text or len(text) != 20 or text[-1] != "Z" or text[4] != "-" \
            or text[7] != "-" or text[10] != "T" or text[13] != ":" \
            or text[16] != ":":
        return False
    for pos in (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18):
        if not ("0" <= text[pos] <= "9"):
            return False
    return True


def _read_rows(csv_text):
    """Parse a CSV string into (header, rows); tolerate trailing blank lines."""
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows:
        return None, []
    return rows[0], rows[1:]


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds per the v1/v2 contract.

    Pure function: operates only on the given strings; inputs are never mutated.
    Returns a dict with "orders", "customers" and "totals"; all money values are
    integer cents.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v2":
        if not cutoff or not _is_valid_cutoff(cutoff):
            raise ValueError("v2 requires a valid cutoff (YYYY-MM-DDTHH:MM:SSZ)")
    max_decimals = 2 if policy == "v1" else None
    refund_cols = 3 if policy == "v1" else 5

    orders_header, order_rows = _read_rows(orders_csv)
    refunds_header, refund_rows = _read_rows(refunds_csv)

    # Empty inputs (header-only or fully empty) yield an empty result.
    if not orders_header:
        order_rows = []
    if not refunds_header:
        refund_rows = []

    # --- Orders: dedupe by order_id, conflict => ValueError -----------------
    orders = {}  # order_id -> (customer, amount_raw, status, created_at)
    for row in order_rows:
        if len(row) != 5:
            raise ValueError("bad order row: %r" % (row,))
        order_id, customer, amount, status, created_at = row
        key = (customer, amount, status, created_at)
        seen = orders.get(order_id)
        if seen is not None:
            if seen != key:
                raise ValueError(
                    "conflicting duplicate order: %s" % (order_id,)
                )
            continue
        orders[order_id] = key

    # --- Refunds: dedupe by refund_id, conflict => ValueError ---------------
    # Conflict detection covers pending/after-cutoff rows too (v2).
    refunds = {}  # refund_id -> tuple of remaining raw fields
    for row in refund_rows:
        if len(row) != refund_cols:
            raise ValueError("bad refund row: %r" % (row,))
        refund_id = row[0]
        key = tuple(row[1:])
        seen = refunds.get(refund_id)
        if seen is not None:
            if seen != key:
                raise ValueError(
                    "conflicting duplicate refund: %s" % (refund_id,)
                )
            continue
        refunds[refund_id] = key

    # --- Select orders in scope ----------------------------------------------
    paid_by_order = {}
    refund_by_order = {}
    for order_id, (customer, amount, status, created_at) in orders.items():
        if status == "paid":
            if policy == "v2" and created_at > cutoff:
                continue  # after-cutoff orders are excluded entirely
            paid_by_order[order_id] = _parse_amount_cents(
                amount, max_decimals=max_decimals
            )
        refund_by_order.setdefault(order_id, 0)

    # --- Select refunds in scope ----------------------------------------------
    for refund_id, fields in refunds.items():
        if policy == "v1":
            order_id, amount = fields
            status, created_at = "succeeded", None
        else:
            order_id, amount, status, created_at = fields
        if status != "succeeded":
            continue  # pending refunds are not effective
        if policy == "v2" and created_at > cutoff:
            continue  # after-cutoff refunds are not effective
        if order_id not in orders:
            raise ValueError("refund for unknown order: %s" % (order_id,))
        if orders[order_id][2] != "paid":
            raise ValueError("refund for cancelled order: %s" % (order_id,))
        if order_id not in paid_by_order:
            continue  # order exists but excluded by cutoff: ignore refund
        cents = _parse_amount_cents(amount, max_decimals=max_decimals)
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + cents
        if refund_by_order[order_id] > paid_by_order[order_id]:
            raise ValueError(
                "refunds exceed paid amount for order: %s" % (order_id,)
            )

    # --- Aggregate -------------------------------------------------------------
    order_entries = []
    customer_net = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(paid_by_order):
        customer = orders[order_id][0]
        paid = paid_by_order[order_id]
        refund = refund_by_order.get(order_id, 0)
        net = paid - refund
        order_entries.append(
            {
                "order_id": order_id,
                "customer": customer,
                "paid_cents": paid,
                "refund_cents": refund,
                "net_cents": net,
            }
        )
        customer_net[customer] = customer_net.get(customer, 0) + net
        total_paid += paid
        total_refund += refund

    customer_entries = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]

    return {
        "orders": order_entries,
        "customers": customer_entries,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def _rows_to_csv(header, rows):
    """Render rows with the standard csv writer (CRLF line endings)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Render a reconcile result into the release bundle files.

    Returns exactly three files: orders.csv, customers.csv and summary.json.
    Row order follows the reconcile ordering; money values are integer text;
    summary.json parses to exactly result["totals"].
    """
    orders_csv = _rows_to_csv(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            [
                entry["order_id"],
                entry["customer"],
                str(entry["paid_cents"]),
                str(entry["refund_cents"]),
                str(entry["net_cents"]),
            ]
            for entry in result["orders"]
        ],
    )
    customers_csv = _rows_to_csv(
        ["customer", "net_cents"],
        [
            [entry["customer"], str(entry["net_cents"])]
            for entry in result["customers"]
        ],
    )
    summary_json = json.dumps(result["totals"])
    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
