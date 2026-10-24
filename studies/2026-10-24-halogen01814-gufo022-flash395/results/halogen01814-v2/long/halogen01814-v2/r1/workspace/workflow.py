"""Order reconciliation, v1 + v2 contracts (see spec-v1.md, spec-v2.md).

Pure functions only: parse CSV text, validate, aggregate into integer cents.
No file/network/process access; only stdlib csv/io/decimal/datetime/json.
"""

import csv
import io
import json
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _parse_amount_cents_v1(raw, label="amount"):
    """v1: non-negative decimal with at most 2 decimals, exact conversion to cents."""
    cents = _parse_amount_common(raw, label)
    sign, digits, exp = cents.as_tuple()
    if exp < -2:
        raise ValueError("%s has more than 2 decimal places: %r" % (label, raw))
    return int(cents.scaleb(2))


def _parse_amount_cents_v2(raw, label="amount"):
    """v2: non-negative decimal, any number of decimals, ROUND_HALF_UP to cents."""
    cents = _parse_amount_common(raw, label)
    return int(cents.scaleb(2).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _parse_amount_common(raw, label):
    """Shared validation: non-empty, finite, non-negative Decimal."""
    if raw is None:
        raise ValueError("%s is missing" % label)
    s = str(raw).strip()
    if s == "":
        raise ValueError("%s is empty" % label)
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        raise ValueError("invalid %s: %r" % (label, raw))
    if not d.is_finite():
        raise ValueError("non-finite %s: %r" % (label, raw))
    if d < 0:
        raise ValueError("negative %s: %r" % (label, raw))
    return d


def _read_rows(csv_text, required_headers, label):
    """Parse CSV text into a list of dicts keyed by header. Returns [] if empty."""
    if csv_text is None:
        raise ValueError("%s input is required" % label)
    if not isinstance(csv_text, str):
        raise ValueError("%s input must be a string" % label)
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    for h in required_headers:
        if h not in header:
            raise ValueError("%s is missing column: %s" % (label, h))
    out = []
    for row in rows[1:]:
        if len(row) != len(header):
            raise ValueError("%s has a malformed row: %r" % (label, row))
        out.append({h: v.strip() for h, v in zip(header, row)})
    return out


def _dedupe(rows, id_field, label):
    """Drop exact duplicate rows sharing an id; raise on conflicting duplicates.

    Runs before any filtering so conflicts involving pending/after-cutoff rows
    are still rejected.
    """
    seen = {}
    out = []
    for row in rows:
        rid = row[id_field]
        if rid in seen:
            if seen[rid] != row:
                raise ValueError(
                    "conflicting duplicate %s id: %s" % (label, rid)
                )
            continue
        seen[rid] = row
        out.append(row)
    return out


def _validate_cutoff(cutoff):
    """Validate strict UTC format YYYY-MM-DDTHH:MM:SSZ and real calendar date."""
    if not isinstance(cutoff, str):
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ, got: %r" % (cutoff,))
    s = cutoff.strip()
    ok = (
        len(s) == 20
        and s[4] == "-" and s[7] == "-" and s[10] == "T"
        and s[13] == ":" and s[16] == ":" and s[19] == "Z"
        and all(ch.isdigit() for ch in s[0:4] + s[5:7] + s[8:10]
                + s[11:13] + s[14:16] + s[17:19])
    )
    if not ok:
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ, got: %r" % (cutoff,))
    try:
        datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("cutoff is not a valid UTC datetime: %r" % (cutoff,))
    return s


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds.

    policy="v1": legacy contract (max 2 decimals, refunds without status).
    policy="v2": cutoff required; created_at filtering; refund status;
                 multi-decimal amounts rounded HALF_UP per row to cents.

    Returns dict with:
      orders: sorted by order_id, paid orders only,
              {order_id, customer, paid_cents, refund_cents, net_cents}
      customers: sorted by customer, {customer, net_cents}
      totals: {paid_cents, refund_cents, net_cents}
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %r" % (policy,))

    if policy == "v2":
        if cutoff is None:
            raise ValueError("cutoff is required for policy v2")
        cutoff = _validate_cutoff(cutoff)
        amount_parser = _parse_amount_cents_v2
        refund_required = ["refund_id", "order_id", "amount", "status", "created_at"]
    else:
        amount_parser = _parse_amount_cents_v1
        refund_required = ["refund_id", "order_id", "amount"]

    order_rows = _read_rows(
        orders_csv,
        ["order_id", "customer", "amount", "status", "created_at"],
        "orders",
    )
    refund_rows = _read_rows(refunds_csv, refund_required, "refunds")

    # Dedupe first: conflicts must be rejected even for rows later filtered out.
    order_rows = _dedupe(order_rows, "order_id", "order")
    refund_rows = _dedupe(refund_rows, "refund_id", "refund")

    orders = {}
    orders_in_window = {}
    for r in order_rows:
        cents = amount_parser(r["amount"], "order amount for %s" % r["order_id"])
        status = r["status"].strip().lower()
        orders[r["order_id"]] = {
            "customer": r["customer"],
            "paid_cents": cents,
            "status": status,
        }
        if policy == "v2" and r["created_at"].strip() > cutoff:
            continue  # after-cutoff order: excluded from results
        if status == "paid":
            orders_in_window[r["order_id"]] = orders[r["order_id"]]

    refund_by_order = {}
    for r in refund_rows:
        oid = r["order_id"]
        if policy == "v2":
            status = r["status"].strip().lower()
            if status not in ("succeeded", "pending"):
                raise ValueError(
                    "invalid refund status for %s: %r" % (r["refund_id"], r["status"])
                )
            # pending or after-cutoff refunds are not counted at all
            if status != "succeeded" or r["created_at"].strip() > cutoff:
                continue
        if oid not in orders:
            raise ValueError(
                "refund %s references unknown order: %s" % (r["refund_id"], oid)
            )
        if orders[oid]["status"] != "paid":
            raise ValueError(
                "refund %s references non-paid order: %s" % (r["refund_id"], oid)
            )
        if oid not in orders_in_window:
            # order exists and is paid but excluded by cutoff: ignore refund
            continue
        cents = amount_parser(
            r["amount"], "refund amount for %s" % r["refund_id"]
        )
        refund_by_order[oid] = refund_by_order.get(oid, 0) + cents

    for oid, total_ref in refund_by_order.items():
        if total_ref > orders[oid]["paid_cents"]:
            raise ValueError(
                "refunds exceed paid amount for order %s" % oid
            )

    order_entries = []
    customer_net = {}
    total_paid = 0
    total_refund = 0
    for oid in sorted(orders_in_window):
        order = orders_in_window[oid]
        ref = refund_by_order.get(oid, 0)
        net = order["paid_cents"] - ref
        order_entries.append(
            {
                "order_id": oid,
                "customer": order["customer"],
                "paid_cents": order["paid_cents"],
                "refund_cents": ref,
                "net_cents": net,
            }
        )
        customer_net[order["customer"]] = (
            customer_net.get(order["customer"], 0) + net
        )
        total_paid += order["paid_cents"]
        total_refund += ref

    customers = [
        {"customer": name, "net_cents": net}
        for name, net in sorted(customer_net.items())
    ]
    totals = {
        "paid_cents": total_paid,
        "refund_cents": total_refund,
        "net_cents": total_paid - total_refund,
    }
    return {"orders": order_entries, "customers": customers, "totals": totals}


def _csv_text(header, rows):
    """Render rows (list of lists) to CSV text using the standard writer."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """Build the release bundle per release-spec.md.

    Returns exactly three files as dict[str, str]:
      orders.csv    - order_id,customer,paid_cents,refund_cents,net_cents
      customers.csv - customer,net_cents
      summary.json  - exactly result["totals"]
    Row order follows the reconcile ordering; amounts are integer text.
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a reconcile output dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError("result is missing key: %s" % key)

    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            [
                e["order_id"],
                e["customer"],
                "%d" % e["paid_cents"],
                "%d" % e["refund_cents"],
                "%d" % e["net_cents"],
            ]
            for e in result["orders"]
        ],
    )
    customers_csv = _csv_text(
        ["customer", "net_cents"],
        [["%s" % c["customer"], "%d" % c["net_cents"]] for c in result["customers"]],
    )
    summary_json = json.dumps(result["totals"])
    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
