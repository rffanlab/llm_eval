"""Order reconciliation, v1 and v2 contracts (see spec-v1.md / spec-v2.md).

Also implements export_bundle per release-spec.md.
"""

import csv
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _is_valid_cutoff(text):
    """Validate YYYY-MM-DDTHH:MM:SSZ without regex."""
    if not isinstance(text, str) or len(text) != 20:
        return False
    if text[4] != "-" or text[7] != "-" or text[10] != "T" or text[19] != "Z":
        return False
    if text[13] != ":" or text[16] != ":":
        return False
    digits = text[0:4] + text[5:7] + text[8:10] + text[11:13] + text[14:16] + text[17:19]
    if not digits.isdigit():
        return False
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    hour = int(text[11:13])
    minute = int(text[14:16])
    second = int(text[17:19])
    if not 1 <= month <= 12:
        return False
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    days_in_month = [31, 29 if leap else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    if not 1 <= day <= days_in_month:
        return False
    return hour <= 23 and minute <= 59 and second <= 59


def _parse_amount_cents(raw, what, max_two_decimals):
    """Parse a decimal amount string to integer cents.

    Rules shared by v1/v2: non-negative, finite (no NaN/Infinity).
    v1 (max_two_decimals=True): at most two decimal places.
    v2: any number of decimals, rounded to cents with ROUND_HALF_UP.
    Uses Decimal fixed-point; never float multiplication.
    """
    if raw is None:
        raise ValueError("%s is missing" % what)
    text = raw.strip()
    if text == "":
        raise ValueError("%s is empty" % what)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s is not a valid number: %r" % (what, raw))
    if not value.is_finite():
        raise ValueError("%s is not finite: %r" % (what, raw))
    if value < 0:
        raise ValueError("%s is negative: %r" % (what, raw))
    if max_two_decimals:
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -2:
            raise ValueError(
                "%s has more than two decimal places: %r" % (what, raw)
            )
        cents = value.scaleb(2).to_integral_value()
    else:
        cents = value.scaleb(2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _read_rows(csv_text, required, what):
    if csv_text is None:
        raise ValueError("%s input is None" % what)
    reader = csv.reader(csv_text.splitlines())
    rows = list(reader)
    # Drop fully blank lines.
    rows = [r for r in rows if any(cell.strip() != "" for cell in r)]
    if not rows:
        raise ValueError("%s input must contain a header row" % what)
    header = [h.strip() for h in rows[0]]
    if header != required:
        raise ValueError(
            "%s header mismatch: expected %r, got %r" % (what, required, header)
        )
    out = []
    for line_no, row in enumerate(rows[1:], start=2):
        if len(row) != len(required):
            raise ValueError(
                "%s row %d has %d fields, expected %d"
                % (what, line_no, len(row), len(required))
            )
        out.append({key: cell.strip() for key, cell in zip(required, row)})
    return out


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds.

    policy="v1": legacy contract (two-decimal amounts, 3-column refunds).
    policy="v2": cutoff required (YYYY-MM-DDTHH:MM:SSZ); refunds carry
      status/created_at; only paid orders and succeeded refunds with
      created_at <= cutoff count; amounts may have many decimals and are
      rounded to cents with ROUND_HALF_UP per row before summing.

    Returns {"orders": [...], "customers": [...], "totals": {...}} with
    integer cents. Raises ValueError on any contract violation.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    if policy == "v1":
        if cutoff is not None:
            raise ValueError("cutoff is not supported in policy v1")
    else:
        if cutoff is None:
            raise ValueError("policy v2 requires a cutoff")
        cutoff = cutoff.strip() if isinstance(cutoff, str) else cutoff
        if not _is_valid_cutoff(cutoff):
            raise ValueError("invalid cutoff format: %r" % (cutoff,))

    max_two = policy == "v1"
    refund_fields = ["refund_id", "order_id", "amount"]
    if policy == "v2":
        refund_fields += ["status", "created_at"]

    order_rows = _read_rows(
        orders_csv,
        ["order_id", "customer", "amount", "status", "created_at"],
        "orders",
    )
    refund_rows = _read_rows(refunds_csv, refund_fields, "refunds")

    # ---- Orders: dedupe by order_id (conflicts rejected even for rows
    # excluded by cutoff/status), then keep paid (and in-window) orders. ----
    orders = {}  # order_id -> dict, counted orders
    order_state = {}  # order_id -> "paid" | "cancelled" (any row seen)
    order_seen = {}  # order_id -> first raw row, for exact-dup check
    for row in order_rows:
        oid = row["order_id"]
        if oid == "":
            raise ValueError("order row with empty order_id")
        status = row["status"].lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("unknown order status: %r" % row["status"])
        cents = _parse_amount_cents(row["amount"], "order amount for %s" % oid, max_two)
        if oid in order_seen:
            if order_seen[oid] == row:
                continue  # exact duplicate, count once
            raise ValueError("conflicting rows for order_id %s" % oid)
        order_seen[oid] = row
        order_state[oid] = status
        in_window = cutoff is None or row["created_at"] <= cutoff
        if status == "paid" and in_window:
            orders[oid] = {
                "order_id": oid,
                "customer": row["customer"],
                "paid_cents": cents,
                "refund_cents": 0,
            }

    # ---- Refunds: dedupe by refund_id, validate targets, apply filters. ----
    refund_seen = {}  # refund_id -> first raw row
    for row in refund_rows:
        rid = row["refund_id"]
        if rid == "":
            raise ValueError("refund row with empty refund_id")
        if rid in refund_seen:
            if refund_seen[rid] == row:
                continue  # exact duplicate, count once
            raise ValueError("conflicting rows for refund_id %s" % rid)
        refund_seen[rid] = row

        if policy == "v2":
            rstatus = row["status"].lower()
            if rstatus not in ("succeeded", "pending"):
                raise ValueError("unknown refund status: %r" % row["status"])
            if rstatus != "succeeded":
                continue  # pending refunds never count
            if row["created_at"] > cutoff:
                continue  # after-cutoff refunds do not count
        oid = row["order_id"]
        cents = _parse_amount_cents(row["amount"], "refund amount for %s" % rid, max_two)

        if oid not in order_seen:
            raise ValueError("refund %s references unknown order %s" % (rid, oid))
        if order_state[oid] == "cancelled":
            raise ValueError("refund %s references cancelled order %s" % (rid, oid))
        if oid not in orders:
            # Order exists and is paid but excluded by cutoff -> ignore refund.
            continue

        order = orders[oid]
        if order["refund_cents"] + cents > order["paid_cents"]:
            raise ValueError("refunds exceed paid amount for order %s" % oid)
        order["refund_cents"] += cents

    # ---- Build result (structure and ordering identical to v1). ----
    result_orders = []
    customers_total = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for oid in sorted(orders):
        order = orders[oid]
        net = order["paid_cents"] - order["refund_cents"]
        result_orders.append(
            {
                "order_id": order["order_id"],
                "customer": order["customer"],
                "paid_cents": order["paid_cents"],
                "refund_cents": order["refund_cents"],
                "net_cents": net,
            }
        )
        customers_total[order["customer"]] = (
            customers_total.get(order["customer"], 0) + net
        )
        totals["paid_cents"] += order["paid_cents"]
        totals["refund_cents"] += order["refund_cents"]
        totals["net_cents"] += net

    result_customers = [
        {"customer": name, "net_cents": customers_total[name]}
        for name in sorted(customers_total)
    ]

    return {"orders": result_orders, "customers": result_customers, "totals": totals}


def _csv_text(rows):
    """Render rows to CSV text with the standard csv writer."""
    import io

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Export a reconcile result to the release bundle (release-spec.md).

    Returns exactly three files: orders.csv, customers.csv, summary.json.
    Row order follows the reconcile ordering; amounts are integer text;
    summary.json is exactly result["totals"].
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError("result missing key: %s" % key)

    order_rows = [["order_id", "customer", "paid_cents", "refund_cents", "net_cents"]]
    for order in result["orders"]:
        order_rows.append([
            str(order["order_id"]),
            str(order["customer"]),
            str(int(order["paid_cents"])),
            str(int(order["refund_cents"])),
            str(int(order["net_cents"])),
        ])

    customer_rows = [["customer", "net_cents"]]
    for customer in result["customers"]:
        customer_rows.append([
            str(customer["customer"]),
            str(int(customer["net_cents"])),
        ])

    summary = json.dumps(result["totals"], sort_keys=True)

    return {
        "orders.csv": _csv_text(order_rows),
        "customers.csv": _csv_text(customer_rows),
        "summary.json": summary,
    }
