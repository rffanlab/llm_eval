"""Order reconciliation, v1 and v2 contracts (see spec-v1.md / spec-v2.md).

Pure functions only: no file, network or process access.
Amounts are handled as decimal fixed-point; never float*100.
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_VALID_STATUSES = {"paid", "cancelled"}
_VALID_REFUND_STATUSES = {"succeeded", "pending"}


def _is_amount_text(text):
    """Digits with optional single decimal point; no sign, exponent, NaN/Inf."""
    if not text:
        return False
    seen_dot = False
    for ch in text:
        if ch == ".":
            if seen_dot:
                return False
            seen_dot = True
        elif ch < "0" or ch > "9":
            return False
    if text.startswith(".") or text.endswith("."):
        return False
    return True


def _parse_amount_cents(raw, allow_many_decimals):
    """Parse a non-negative amount string to integer cents.

    v1: at most two decimals. v2: any number of decimals, ROUND_HALF_UP.
    Rejects NaN, Infinity, negatives, exponents and empty strings.
    """
    if raw is None:
        raise ValueError("amount is missing")
    text = raw.strip()
    if not _is_amount_text(text):
        raise ValueError("invalid amount: %r" % (raw,))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid amount: %r" % (raw,))
    if not value.is_finite() or value < 0:
        raise ValueError("invalid amount: %r" % (raw,))
    if not allow_many_decimals and value != value.quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    ):
        raise ValueError("amount has more than two decimals: %r" % (raw,))
    cents = (value * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _is_valid_cutoff(text):
    """Strictly validate YYYY-MM-DDTHH:MM:SSZ (canonical UTC string)."""
    if not isinstance(text, str) or len(text) != 20:
        return False
    if text[4] != "-" or text[7] != "-" or text[10] != "T" or text[19] != "Z":
        return False
    if text[13] != ":" or text[16] != ":":
        return False
    for pos in (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18):
        ch = text[pos]
        if ch < "0" or ch > "9":
            return False
    month = int(text[5:7])
    day = int(text[8:10])
    hour = int(text[11:13])
    minute = int(text[14:16])
    second = int(text[17:19])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    if hour > 23 or minute > 59 or second > 59:
        return False
    return True


def _read_rows(csv_text, required_headers):
    """Parse a CSV string into a list of dicts; validate the header row."""
    if csv_text is None:
        raise ValueError("csv must contain a header row")
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    # Drop fully blank rows (e.g. from trailing newlines).
    rows = [r for r in rows if any(field.strip() != "" for field in r)]
    if not rows:
        raise ValueError("csv must contain a header row")
    header = [h.strip() for h in rows[0]]
    for name in required_headers:
        if name not in header:
            raise ValueError("missing required column: %s" % name)
    out = []
    for row in rows[1:]:
        if len(row) != len(header):
            raise ValueError("row has %d fields, expected %d" % (len(row), len(header)))
        out.append({header[i]: row[i].strip() for i in range(len(header))})
    return out


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds.

    Returns {"orders": [...], "customers": [...], "totals": {...}} with all
    amounts as integer cents. See spec-v1.md and spec-v2.md.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))
    is_v2 = policy == "v2"
    if is_v2:
        if cutoff is None:
            raise ValueError("cutoff is required for policy v2")
        if not _is_valid_cutoff(cutoff):
            raise ValueError("invalid cutoff: %r" % (cutoff,))

    # ---- Orders -----------------------------------------------------------
    order_headers = ["order_id", "customer", "amount", "status"]
    if is_v2:
        order_headers.append("created_at")
    order_rows = _read_rows(orders_csv, order_headers)
    orders_by_id = {}  # order_id -> signature dict (first occurrence)
    for row in order_rows:
        order_id = row["order_id"]
        if not order_id:
            raise ValueError("order row with empty order_id")
        status = row["status"]
        if status not in _VALID_STATUSES:
            raise ValueError("unknown order status: %r" % (status,))
        paid_cents = _parse_amount_cents(row["amount"], allow_many_decimals=is_v2)
        created_at = row.get("created_at", "")
        if is_v2 and not _is_valid_cutoff(created_at):
            raise ValueError("invalid order created_at: %r" % (created_at,))
        signature = {
            "order_id": order_id,
            "customer": row["customer"],
            "amount_cents": paid_cents,
            "status": status,
            "created_at": created_at,
        }
        previous = orders_by_id.get(order_id)
        if previous is not None:
            if previous != signature:
                raise ValueError(
                    "conflicting duplicate rows for order_id %r" % (order_id,)
                )
            continue  # exact duplicate: count once
        orders_by_id[order_id] = signature

    # ---- Refunds ----------------------------------------------------------
    refund_headers = ["refund_id", "order_id", "amount"]
    if is_v2:
        refund_headers.extend(["status", "created_at"])
    refund_rows = _read_rows(refunds_csv, refund_headers)
    refunds_by_id = {}  # refund_id -> signature dict
    refund_cents_by_order = {}
    for row in refund_rows:
        refund_id = row["refund_id"]
        if not refund_id:
            raise ValueError("refund row with empty refund_id")
        refund_cents = _parse_amount_cents(row["amount"], allow_many_decimals=is_v2)
        status = row.get("status", "succeeded") if is_v2 else "succeeded"
        created_at = row.get("created_at", "") if is_v2 else ""
        if is_v2:
            if status not in _VALID_REFUND_STATUSES:
                raise ValueError("unknown refund status: %r" % (status,))
            if not _is_valid_cutoff(created_at):
                raise ValueError("invalid refund created_at: %r" % (created_at,))
        signature = {
            "refund_id": refund_id,
            "order_id": row["order_id"],
            "amount_cents": refund_cents,
            "status": status,
            "created_at": created_at,
        }
        previous = refunds_by_id.get(refund_id)
        if previous is not None:
            # Conflicts must be rejected even for pending / after-cutoff rows.
            if previous != signature:
                raise ValueError(
                    "conflicting duplicate rows for refund_id %r" % (refund_id,)
                )
            continue  # exact duplicate: count once
        refunds_by_id[refund_id] = signature

        if is_v2:
            # Only succeeded refunds within the cutoff are "effective".
            if status != "succeeded" or created_at > cutoff:
                continue

        target = orders_by_id.get(signature["order_id"])
        if target is None:
            raise ValueError(
                "refund %s references unknown order %r"
                % (refund_id, signature["order_id"])
            )
        if target["status"] != "paid":
            raise ValueError(
                "refund %s references cancelled order %r"
                % (refund_id, signature["order_id"])
            )
        if is_v2:
            # Order exists but is excluded by the cutoff: ignore the refund.
            if target["created_at"] > cutoff:
                continue
        refund_cents_by_order[signature["order_id"]] = (
            refund_cents_by_order.get(signature["order_id"], 0) + refund_cents
        )

    # ---- Build results ----------------------------------------------------
    paid_orders = [
        info
        for info in orders_by_id.values()
        if info["status"] == "paid"
        and (not is_v2 or info["created_at"] <= cutoff)
    ]

    order_results = []
    totals_paid = 0
    totals_refund = 0
    customer_net = {}
    for info in paid_orders:
        refund_cents = refund_cents_by_order.get(info["order_id"], 0)
        if refund_cents > info["amount_cents"]:
            raise ValueError(
                "refunds exceed paid amount for order %r" % (info["order_id"],)
            )
        net_cents = info["amount_cents"] - refund_cents
        order_results.append(
            {
                "order_id": info["order_id"],
                "customer": info["customer"],
                "paid_cents": info["amount_cents"],
                "refund_cents": refund_cents,
                "net_cents": net_cents,
            }
        )
        totals_paid += info["amount_cents"]
        totals_refund += refund_cents
        customer_net[info["customer"]] = (
            customer_net.get(info["customer"], 0) + net_cents
        )

    order_results.sort(key=lambda item: item["order_id"])
    customer_results = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]

    return {
        "orders": order_results,
        "customers": customer_results,
        "totals": {
            "paid_cents": totals_paid,
            "refund_cents": totals_refund,
            "net_cents": totals_paid - totals_refund,
        },
    }


def _csv_text(header, rows):
    """Render rows (list of lists) as CSV text with a header, via csv.writer."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """Build the release bundle for a reconcile result.

    Returns exactly three files (release-spec.md):
      - orders.csv:    order_id,customer,paid_cents,refund_cents,net_cents
      - customers.csv: customer,net_cents
      - summary.json:  exactly result["totals"]
    Row order follows the reconcile ordering; amounts are integer text.
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a reconcile output dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError("result missing key: %s" % key)

    orders_rows = []
    for item in result["orders"]:
        orders_rows.append(
            [
                str(item["order_id"]),
                str(item["customer"]),
                str(int(item["paid_cents"])),
                str(int(item["refund_cents"])),
                str(int(item["net_cents"])),
            ]
        )
    customers_rows = []
    for item in result["customers"]:
        customers_rows.append(
            [str(item["customer"]), str(int(item["net_cents"]))]
        )

    return {
        "orders.csv": _csv_text(
            ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
            orders_rows,
        ),
        "customers.csv": _csv_text(
            ["customer", "net_cents"],
            customers_rows,
        ),
        "summary.json": json.dumps(
            result["totals"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
    }
