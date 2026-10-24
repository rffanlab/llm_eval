"""Order reconciliation, v1 + v2 contracts.

Pure functions only: parses CSV strings, returns plain dicts.
Fixed-point decimal money; all outputs are integer cents.
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


_SUPPORTED_POLICIES = ("v1", "v2")

_ORDER_FIELDS = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_FIELDS_V1 = ("refund_id", "order_id", "amount")
_REFUND_FIELDS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")

_REFUND_STATUSES = ("succeeded", "pending")


def _parse_amount_cents(raw, context, policy):
    """Parse a money string to integer cents.

    Common: rejects empty/non-numeric, NaN, Infinity, negatives.
    v1: at most two decimal places (exact conversion).
    v2: any number of decimals; value*100 rounded to whole cents
        with ROUND_HALF_UP (per-line rounding before summing).
    Uses Decimal only (no float arithmetic).
    """
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = raw.strip()
    if not text:
        raise ValueError("%s: empty amount" % context)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if not value.is_finite():
        raise ValueError("%s: non-finite amount %r" % (context, raw))
    if value < 0:
        raise ValueError("%s: negative amount %r" % (context, raw))
    if policy == "v1":
        _sign, _digits, exponent = value.as_tuple()
        if exponent < -2:
            raise ValueError(
                "%s: more than two decimal places in %r" % (context, raw)
            )
        cents = value * Decimal(100)
        return int(cents.to_integral_value())
    # v2: scale to cents, then round half-up to a whole number of cents
    cents = (value * Decimal(100)).quantize(
        Decimal(1), rounding=ROUND_HALF_UP
    )
    return int(cents)


def _read_rows(csv_text, expected_fields, table_name):
    if csv_text is None:
        raise ValueError("%s: input is None" % table_name)
    reader = csv.DictReader(io.StringIO(csv_text, newline=""))
    if reader.fieldnames is None:
        raise ValueError("%s: missing header" % table_name)
    header = [name.strip() for name in reader.fieldnames]
    for field in expected_fields:
        if field not in header:
            raise ValueError("%s: missing column %r" % (table_name, field))
    rows = []
    for line_no, row in enumerate(reader, start=2):
        if all(
            (cell is None or str(cell).strip() == "")
            for cell in row.values()
        ):
            continue  # skip blank lines
        rows.append((line_no, row))
    return rows


def _validate_cutoff(cutoff):
    """Check YYYY-MM-DDTHH:MM:SSZ shape without regex."""
    if not isinstance(cutoff, str):
        raise ValueError(
            "cutoff must be YYYY-MM-DDTHH:MM:SSZ, got %r" % (cutoff,)
        )
    text = cutoff.strip()
    ok = (
        len(text) == 20
        and text[4] == "-"
        and text[7] == "-"
        and text[10] == "T"
        and text[13] == ":"
        and text[16] == ":"
        and text[19] == "Z"
        and all(ch.isdigit() for ch in text[0:4] + text[5:7] + text[8:10]
                + text[11:13] + text[14:16] + text[17:19])
    )
    if not ok:
        raise ValueError(
            "cutoff must be YYYY-MM-DDTHH:MM:SSZ, got %r" % (cutoff,)
        )
    return text


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds.

    policy="v1": legacy contract (two-decimal amounts, no refund
        status/created_at columns required, no cutoff).
    policy="v2": cutoff required; only paid orders with
        created_at <= cutoff count; only succeeded refunds with
        created_at <= cutoff count. Amounts may have any decimals,
        rounded to cents ROUND_HALF_UP per line before summing.

    Returns:
        {
          "orders": [{"order_id", "customer", "paid_cents",
                      "refund_cents", "net_cents"}, ...],  # by order_id
          "customers": [{"customer", "net_cents"}, ...],   # by customer
          "totals": {"paid_cents", "refund_cents", "net_cents"},
        }
    """
    if policy not in _SUPPORTED_POLICIES:
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v2":
        if cutoff is None:
            raise ValueError("cutoff is required for policy v2")
        cutoff = _validate_cutoff(cutoff)

    # ---- orders ----
    orders = {}  # order_id -> record dict
    for line_no, row in _read_rows(orders_csv, _ORDER_FIELDS, "orders"):
        order_id = (row.get("order_id") or "").strip()
        if not order_id:
            raise ValueError("orders line %d: empty order_id" % line_no)
        customer = row.get("customer") or ""
        status = (row.get("status") or "").strip()
        created_at = (row.get("created_at") or "").strip()
        paid_cents = _parse_amount_cents(
            row.get("amount"), "orders line %d" % line_no, policy
        )
        record = {
            "order_id": order_id,
            "customer": customer,
            "status": status,
            "paid_cents": paid_cents,
            "created_at": created_at,
        }
        if order_id in orders:
            existing = orders[order_id]
            if existing == record:
                continue  # exact duplicate row counts once
            raise ValueError(
                "duplicate order_id %r with conflicting fields" % order_id
            )
        orders[order_id] = record

    # ---- refunds: parse, dedup (conflicts always rejected) ----
    refunds = {}  # refund_id -> record dict
    for line_no, row in _read_rows(
        refunds_csv,
        _REFUND_FIELDS_V2 if policy == "v2" else _REFUND_FIELDS_V1,
        "refunds",
    ):
        refund_id = (row.get("refund_id") or "").strip()
        if not refund_id:
            raise ValueError("refunds line %d: empty refund_id" % line_no)
        order_id = (row.get("order_id") or "").strip()
        refund_cents = _parse_amount_cents(
            row.get("amount"), "refunds line %d" % line_no, policy
        )
        record = {
            "refund_id": refund_id,
            "order_id": order_id,
            "amount_cents": refund_cents,
        }
        if policy == "v2":
            status = (row.get("status") or "").strip()
            if status not in _REFUND_STATUSES:
                raise ValueError(
                    "refunds line %d: invalid refund status %r"
                    % (line_no, row.get("status"))
                )
            record["status"] = status
            record["created_at"] = (row.get("created_at") or "").strip()
        if refund_id in refunds:
            existing = refunds[refund_id]
            if existing == record:
                continue  # exact duplicate row counts once
            raise ValueError(
                "duplicate refund_id %r with conflicting fields" % refund_id
            )
        refunds[refund_id] = record

    # ---- validate refunds against orders, then apply v2 filters ----
    refund_by_order = {}  # order_id -> counted refund cents
    for refund_id in sorted(refunds):
        record = refunds[refund_id]
        order_id = record["order_id"]
        order = orders.get(order_id)
        if order is None:
            raise ValueError(
                "refund %r references unknown order %r" % (refund_id, order_id)
            )
        if order["status"] == "cancelled":
            raise ValueError(
                "refund %r targets cancelled order %r" % (refund_id, order_id)
            )
        if order["status"] != "paid":
            raise ValueError(
                "refund %r targets non-paid order %r (%s)"
                % (refund_id, order_id, order["status"] or "missing status")
            )
        if policy == "v2":
            # pending refunds never count
            if record["status"] != "succeeded":
                continue
            # refunds created after cutoff are ignored
            if record["created_at"] > cutoff:
                continue
            # orders created after cutoff are excluded entirely;
            # refunds pointing at them are ignored too
            if order["created_at"] > cutoff:
                continue
        cumulative = refund_by_order.get(order_id, 0) + record["amount_cents"]
        if cumulative > order["paid_cents"]:
            raise ValueError(
                "refunds for order %r (%d cents) exceed paid amount %d cents"
                % (order_id, cumulative, order["paid_cents"])
            )
        refund_by_order[order_id] = cumulative

    # ---- results ----
    order_rows = []
    customer_net = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(orders):
        order = orders[order_id]
        if order["status"] != "paid":
            continue  # cancelled and other statuses are excluded
        if policy == "v2" and order["created_at"] > cutoff:
            continue  # order created after cutoff is excluded
        paid_cents = order["paid_cents"]
        refund_cents = refund_by_order.get(order_id, 0)
        net_cents = paid_cents - refund_cents
        order_rows.append({
            "order_id": order_id,
            "customer": order["customer"],
            "paid_cents": paid_cents,
            "refund_cents": refund_cents,
            "net_cents": net_cents,
        })
        customer_net[order["customer"]] = (
            customer_net.get(order["customer"], 0) + net_cents
        )
        total_paid += paid_cents
        total_refund += refund_cents

    customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]
    return {
        "orders": order_rows,
        "customers": customers,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def export_bundle(result):
    """Render a reconcile result into the release bundle files.

    Returns exactly {"orders.csv", "customers.csv", "summary.json"}
    as text strings, per release-spec.md:
      - orders.csv header: order_id,customer,paid_cents,refund_cents,net_cents
      - customers.csv header: customer,net_cents
      - row order follows reconcile ordering; amounts are integer text
      - summary.json parses to exactly result["totals"]
    """
    orders_csv = io.StringIO(newline="")
    orders_writer = csv.writer(orders_csv)
    orders_writer.writerow(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"]
    )
    for row in result["orders"]:
        orders_writer.writerow([
            str(row["order_id"]),
            str(row["customer"]),
            "%d" % int(row["paid_cents"]),
            "%d" % int(row["refund_cents"]),
            "%d" % int(row["net_cents"]),
        ])

    customers_csv = io.StringIO(newline="")
    customers_writer = csv.writer(customers_csv)
    customers_writer.writerow(["customer", "net_cents"])
    for row in result["customers"]:
        customers_writer.writerow([
            str(row["customer"]),
            "%d" % int(row["net_cents"]),
        ])

    summary_json = json.dumps(result["totals"], sort_keys=True)

    return {
        "orders.csv": orders_csv.getvalue(),
        "customers.csv": customers_csv.getvalue(),
        "summary.json": summary_json,
    }
