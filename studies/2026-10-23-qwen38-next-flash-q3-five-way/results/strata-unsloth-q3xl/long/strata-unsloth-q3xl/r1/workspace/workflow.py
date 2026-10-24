"""Order reconciliation pipeline (v1 + v2 contracts).

Pure functions only: parses CSV *strings*, uses decimal fixed-point,
performs no file/network/process access.
"""

import csv
import io
import json
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _read_rows(csv_text, required_columns, kind):
    """Parse a CSV string into a list of dict rows (values are strings)."""
    if csv_text is None:
        raise ValueError("%s csv must not be None" % kind)
    if not isinstance(csv_text, str):
        raise ValueError("%s csv must be a string" % kind)
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        return []
    for col in required_columns:
        if col not in reader.fieldnames:
            raise ValueError("%s csv missing column: %s" % (kind, col))
    rows = []
    for raw in reader:
        row = {}
        for key, value in raw.items():
            if key is None:
                continue  # ignore extra unnamed columns
            row[key] = "" if value is None else value
        rows.append(row)
    return rows


def _dedupe(rows, id_field, kind):
    """Same id + identical row -> counted once; same id + any diff -> error.

    Runs over *all* rows (including pending / after-cutoff rows) so that
    duplicate-id conflicts are always rejected.
    """
    seen = {}
    out = []
    for row in rows:
        rid = row.get(id_field, "").strip()
        if rid == "":
            raise ValueError("%s row missing %s" % (kind, id_field))
        signature = tuple(sorted((k, v.strip()) for k, v in row.items()))
        if rid in seen:
            if seen[rid] == signature:
                continue
            raise ValueError(
                "conflicting duplicate %s id %s" % (kind, rid)
            )
        seen[rid] = signature
        out.append(row)
    return out


def _amount_to_cents(raw, kind, policy):
    """Parse a decimal amount string to integer cents (no float math).

    v1: at most two decimals allowed.
    v2: any number of decimals, ROUND_HALF_UP to integer cents.
    Both reject empty / NaN / Infinity / negative values.
    """
    text = "" if raw is None else str(raw).strip()
    if text == "":
        raise ValueError("%s amount missing" % kind)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s invalid amount: %r" % (kind, raw))
    if not value.is_finite():
        raise ValueError("%s non-finite amount: %r" % (kind, raw))
    if value < 0:
        raise ValueError("%s negative amount: %r" % (kind, raw))
    if policy == "v1":
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -2:
            raise ValueError(
                "%s amount has more than 2 decimals: %r" % (kind, raw)
            )
        cents = (value * Decimal(100)).to_integral_exact()
        if not cents == cents.to_integral_value():
            raise ValueError(
                "%s amount has more than 2 decimals: %r" % (kind, raw)
            )
        return int(cents)
    # v2: fixed-point multiply then ROUND_HALF_UP to whole cents
    cents = (value * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _validate_cutoff(cutoff):
    """cutoff must be a canonical UTC string YYYY-MM-DDTHH:MM:SSZ."""
    if cutoff is None:
        raise ValueError("policy v2 requires a cutoff")
    if not isinstance(cutoff, str) or len(cutoff) != 20:
        raise ValueError("invalid cutoff format: %r" % (cutoff,))
    expected_shape = (
        cutoff[0:4].isdigit() and cutoff[4] == "-"
        and cutoff[5:7].isdigit() and cutoff[7] == "-"
        and cutoff[8:10].isdigit() and cutoff[10] == "T"
        and cutoff[11:13].isdigit() and cutoff[13] == ":"
        and cutoff[14:16].isdigit() and cutoff[16] == ":"
        and cutoff[17:19].isdigit() and cutoff[19] == "Z"
    )
    if not expected_shape:
        raise ValueError("invalid cutoff format: %r" % (cutoff,))
    try:
        datetime.datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("invalid cutoff format: %r" % (cutoff,))
    return cutoff


def _finalize(orders, refund_cents_by_order):
    """Build the v1-shaped output from parsed orders + per-order refund cents."""
    result_orders = []
    customer_totals = {}
    total_paid = 0
    total_refund = 0
    for oid in sorted(orders):
        order = orders[oid]
        if not order["include"]:
            continue
        paid = order["paid_cents"]
        refund = refund_cents_by_order.get(oid, 0)
        if refund > paid:
            raise ValueError(
                "order %s refunds (%d cents) exceed paid (%d cents)"
                % (oid, refund, paid)
            )
        net = paid - refund
        result_orders.append({
            "order_id": oid,
            "customer": order["customer"],
            "paid_cents": paid,
            "refund_cents": refund,
            "net_cents": net,
        })
        customer_totals[order["customer"]] = (
            customer_totals.get(order["customer"], 0) + net
        )
        total_paid += paid
        total_refund += refund

    customers = [
        {"customer": name, "net_cents": customer_totals[name]}
        for name in sorted(customer_totals)
    ]
    return {
        "orders": result_orders,
        "customers": customers,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def _rows_to_csv(header, rows):
    """Render rows (ints become integer text) with the standard csv writer."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile orders against refunds per the v1/v2 contracts.

    Returns {"orders": [...], "customers": [...], "totals": {...}} with all
    amounts as integer cents.  ``cutoff`` is required for policy v2 and
    ignored by v1.
    """
    if policy == "v1":
        return _reconcile(orders_csv, refunds_csv, "v1", None)
    if policy == "v2":
        return _reconcile(
            orders_csv, refunds_csv, "v2", _validate_cutoff(cutoff)
        )
    raise ValueError("unsupported policy: %r" % (policy,))


def _reconcile(orders_csv, refunds_csv, policy, cutoff):
    order_columns = ["order_id", "customer", "amount", "status"]
    refund_columns = ["refund_id", "order_id", "amount"]
    if policy == "v2":
        order_columns = order_columns + ["created_at"]
        refund_columns = refund_columns + ["status", "created_at"]

    order_rows = _dedupe(
        _read_rows(orders_csv, order_columns, "order"), "order_id", "order"
    )
    refund_rows = _dedupe(
        _read_rows(refunds_csv, refund_columns, "refund"), "refund_id", "refund"
    )

    orders = {}
    for row in order_rows:
        oid = row["order_id"].strip()
        status = row["status"].strip().lower()
        if status not in ("paid", "cancelled"):
            raise ValueError(
                "order %s has unknown status: %r" % (oid, row["status"])
            )
        paid_cents = _amount_to_cents(row["amount"], "order %s" % oid, policy)
        include = status == "paid"
        created = ""
        if policy == "v2":
            created = row.get("created_at", "").strip()
            if created == "":
                raise ValueError("order %s missing created_at" % oid)
            if include and created > cutoff:
                include = False  # after-cutoff orders are not counted
        orders[oid] = {
            "order_id": oid,
            "customer": row["customer"].strip(),
            "status": status,
            "paid_cents": paid_cents,
            "created_at": created,
            "include": include,
        }

    refund_cents_by_order = {}
    for row in refund_rows:
        rid = row["refund_id"].strip()
        oid = row["order_id"].strip()
        if policy == "v2":
            status = row.get("status", "").strip().lower()
            if status not in ("succeeded", "pending"):
                raise ValueError(
                    "refund %s has unknown status: %r" % (rid, row["status"])
                )
            created = row.get("created_at", "").strip()
            if created == "":
                raise ValueError("refund %s missing created_at" % rid)
            valid = status == "succeeded" and created <= cutoff
            if not valid:
                continue  # pending / after-cutoff refunds are ignored
        if oid not in orders:
            raise ValueError("refund %s references unknown order %s" % (rid, oid))
        if orders[oid]["status"] != "paid":
            raise ValueError("refund %s targets non-paid order %s" % (rid, oid))
        if policy == "v2" and not orders[oid]["include"]:
            continue  # order exists but was excluded by the cutoff -> ignore
        rc = _amount_to_cents(row["amount"], "refund %s" % rid, policy)
        refund_cents_by_order[oid] = refund_cents_by_order.get(oid, 0) + rc

    return _finalize(orders, refund_cents_by_order)


def export_bundle(result):
    """Serialize a reconcile result into the release bundle (release-spec).

    Returns exactly {"orders.csv", "customers.csv", "summary.json"} as
    str -> str.  Row order follows reconcile ordering; amounts are integer
    text; summary.json parses back to result["totals"] exactly.
    """
    orders_csv = _rows_to_csv(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            [o["order_id"], o["customer"],
             int(o["paid_cents"]), int(o["refund_cents"]), int(o["net_cents"])]
            for o in result["orders"]
        ],
    )
    customers_csv = _rows_to_csv(
        ["customer", "net_cents"],
        [[c["customer"], int(c["net_cents"])] for c in result["customers"]],
    )
    summary_json = json.dumps(
        {
            "paid_cents": int(result["totals"]["paid_cents"]),
            "refund_cents": int(result["totals"]["refund_cents"]),
            "net_cents": int(result["totals"]["net_cents"]),
        },
        sort_keys=True,
    )
    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
