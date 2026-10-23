import csv
import io
import json
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _is_valid_utc_stamp(text):
    """Validate canonical UTC stamp YYYY-MM-DDTHH:MM:SSZ without regex."""
    if len(text) != 20 or text[4] != "-" or text[7] != "-" or \
            text[10] != "T" or text[13] != ":" or text[16] != ":" or text[19] != "Z":
        return False
    digits = text[:4] + text[5:7] + text[8:10] + text[11:13] + text[14:16] + text[17:19]
    if not digits.isdigit():
        return False
    try:
        datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _parse_cutoff(cutoff):
    text = str(cutoff).strip()
    if not _is_valid_utc_stamp(text):
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ: %r" % cutoff)
    return text


def _amount_cents(raw, max_exponent):
    """Parse a decimal amount string to integer cents using Decimal only.

    max_exponent: minimum allowed exponent (v1: -2, v2: any).
    Rounding to cents uses ROUND_HALF_UP.
    """
    if raw is None:
        raise ValueError("amount is missing")
    text = str(raw).strip()
    if text == "":
        raise ValueError("amount is empty")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % raw)
    if not value.is_finite():
        raise ValueError("non-finite amount: %r" % raw)
    if value < 0:
        raise ValueError("negative amount: %r" % raw)
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise ValueError("invalid amount: %r" % raw)
    if max_exponent is not None and exponent < max_exponent:
        raise ValueError("amount has more than %d decimal places: %r"
                         % (-max_exponent, raw))
    return int((value * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _read_rows(csv_text, required_headers, kind):
    if csv_text is None:
        raise ValueError("%s csv is missing" % kind)
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row and any(cell.strip() != "" for cell in row)]
    if not rows:
        raise ValueError("%s csv must have a header" % kind)
    header = [h.strip() for h in rows[0]]
    for name in required_headers:
        if name not in header:
            raise ValueError("%s csv missing column: %s" % (kind, name))
    out = []
    for row in rows[1:]:
        if len(row) != len(header):
            raise ValueError("%s csv row has wrong field count: %r" % (kind, row))
        out.append({name: row[i].strip() for i, name in enumerate(header)})
    return out


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds.

    policy="v1": legacy contract (max two decimals, no created_at/status on
    refunds, no cutoff).
    policy="v2": adds cutoff filtering, refund status/created_at and
    ROUND_HALF_UP rounding of arbitrary decimal amounts to integer cents.
    Output structure and ordering are identical to v1.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % policy)

    cutoff_text = None
    if policy == "v2":
        if cutoff is None or str(cutoff).strip() == "":
            raise ValueError("cutoff is required for policy v2")
        cutoff_text = _parse_cutoff(cutoff)

    max_exponent = -2 if policy == "v1" else None

    order_headers = ("order_id", "customer", "amount", "status")
    refund_headers = ("refund_id", "order_id", "amount")
    if policy == "v2":
        order_headers = order_headers + ("created_at",)
        refund_headers = refund_headers + ("status", "created_at")

    order_rows = _read_rows(orders_csv, order_headers, "orders")
    refund_rows = _read_rows(refunds_csv, refund_headers, "refunds")

    # Deduplicate orders by order_id (conflicts rejected regardless of
    # inclusion filters).
    orders = {}
    for row in order_rows:
        order_id = row["order_id"]
        if order_id == "":
            raise ValueError("empty order_id")
        status = row["status"].lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("unknown order status: %r" % row["status"])
        cents = _amount_cents(row["amount"], max_exponent)
        record = {
            "order_id": order_id,
            "customer": row["customer"],
            "amount_cents": cents,
            "status": status,
        }
        if policy == "v2":
            created = row["created_at"]
            if not _is_valid_utc_stamp(created):
                raise ValueError("invalid order created_at: %r" % created)
            record["created_at"] = created
        if order_id in orders:
            if orders[order_id] == record:
                continue  # exact duplicate row, count once
            raise ValueError("conflicting rows for order_id: %s" % order_id)
        orders[order_id] = record

    def _order_included(order):
        if order["status"] != "paid":
            return False
        if policy == "v2" and order["created_at"] > cutoff_text:
            return False
        return True

    # Deduplicate refunds by refund_id and validate targets.
    refunds = {}
    refund_by_order = {}
    for row in refund_rows:
        refund_id = row["refund_id"]
        if refund_id == "":
            raise ValueError("empty refund_id")
        cents = _amount_cents(row["amount"], max_exponent)
        record = {
            "refund_id": refund_id,
            "order_id": row["order_id"],
            "amount_cents": cents,
        }
        if policy == "v2":
            status = row["status"].lower()
            if status not in ("succeeded", "pending"):
                raise ValueError("unknown refund status: %r" % row["status"])
            created = row["created_at"]
            if not _is_valid_utc_stamp(created):
                raise ValueError("invalid refund created_at: %r" % created)
            record["status"] = status
            record["created_at"] = created
        if refund_id in refunds:
            if refunds[refund_id] == record:
                continue  # exact duplicate row, count once
            raise ValueError("conflicting rows for refund_id: %s" % refund_id)
        refunds[refund_id] = record

    for refund_id in sorted(refunds):
        record = refunds[refund_id]
        if policy == "v2" and (record["status"] != "succeeded"
                               or record["created_at"] > cutoff_text):
            continue  # pending or after-cutoff refunds are not counted
        target = orders.get(record["order_id"])
        if target is None:
            raise ValueError("refund %s references unknown order %s"
                             % (refund_id, record["order_id"]))
        if target["status"] != "paid":
            raise ValueError("refund %s references non-paid order %s"
                             % (refund_id, record["order_id"]))
        if policy == "v2" and target["created_at"] > cutoff_text:
            continue  # order exists but excluded by cutoff: ignore refund
        refund_by_order.setdefault(record["order_id"], 0)
        refund_by_order[record["order_id"]] += record["amount_cents"]
        if refund_by_order[record["order_id"]] > target["amount_cents"]:
            raise ValueError("refunds exceed paid amount for order %s"
                             % record["order_id"])

    order_results = []
    customer_net = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(orders):
        order = orders[order_id]
        if not _order_included(order):
            continue
        paid = order["amount_cents"]
        refund = refund_by_order.get(order_id, 0)
        net = paid - refund
        order_results.append({
            "order_id": order_id,
            "customer": order["customer"],
            "paid_cents": paid,
            "refund_cents": refund,
            "net_cents": net,
        })
        customer_net[order["customer"]] = customer_net.get(order["customer"], 0) + net
        total_paid += paid
        total_refund += refund

    customers = [{"customer": name, "net_cents": customer_net[name]}
                 for name in sorted(customer_net)]

    return {
        "orders": order_results,
        "customers": customers,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def _csv_text(header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Render a reconcile result into the release bundle files.

    Returns exactly three files: orders.csv, customers.csv and summary.json.
    CSV rows follow the reconcile ordering; amounts are integer text;
    summary.json is exactly result["totals"].
    """
    if not isinstance(result, dict) or \
            not all(key in result for key in ("orders", "customers", "totals")):
        raise ValueError("result must contain orders, customers and totals")

    order_rows = []
    for item in result["orders"]:
        order_rows.append([
            str(item["order_id"]),
            str(item["customer"]),
            str(int(item["paid_cents"])),
            str(int(item["refund_cents"])),
            str(int(item["net_cents"])),
        ])

    customer_rows = []
    for item in result["customers"]:
        customer_rows.append([str(item["customer"]), str(int(item["net_cents"]))])

    totals = result["totals"]
    summary = {
        "paid_cents": int(totals["paid_cents"]),
        "refund_cents": int(totals["refund_cents"]),
        "net_cents": int(totals["net_cents"]),
    }

    return {
        "orders.csv": _csv_text(
            ("order_id", "customer", "paid_cents", "refund_cents", "net_cents"),
            order_rows),
        "customers.csv": _csv_text(("customer", "net_cents"), customer_rows),
        "summary.json": json.dumps(summary),
    }
