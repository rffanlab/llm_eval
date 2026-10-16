"""Order reconciliation per spec-v1 and spec-v2.

Pure functions only. Inputs are UTF-8 CSV strings; monetary outputs are integer cents.
Uses decimal fixed-point; never float*100.
"""

import csv
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_COLUMNS = ("order_id", "customer", "amount", "status", "created_at")
_REFUND_COLUMNS_V1 = ("refund_id", "order_id", "amount")
_REFUND_COLUMNS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")

_CUTOFF_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _parse_amount_cents(text, context, policy):
    """Parse a non-negative decimal amount into integer cents.

    v1: at most two decimals, exact conversion required.
    v2: any number of decimals, rounded to cents with ROUND_HALF_UP.
    """
    if text is None:
        raise ValueError("%s: missing amount" % context)
    raw = text.strip()
    if raw == "":
        raise ValueError("%s: empty amount" % context)
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, text))
    if not value.is_finite():
        raise ValueError("%s: non-finite amount %r" % (context, text))
    if value < 0:
        raise ValueError("%s: negative amount %r" % (context, text))
    if policy == "v1":
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("%s: more than two decimals %r" % (context, text))
        cents = value.scaleb(2)
        if cents != cents.to_integral_value():
            raise ValueError("%s: cannot convert to integer cents %r" % (context, text))
        return int(cents)
    # v2: fixed-point rounding, half-up, per row.
    return int(value.scaleb(2).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _validate_cutoff(cutoff):
    if cutoff is None or not isinstance(cutoff, str):
        raise ValueError("policy v2 requires cutoff in YYYY-MM-DDTHH:MM:SSZ format")
    try:
        parsed = datetime.strptime(cutoff, _CUTOFF_FORMAT)
    except ValueError:
        raise ValueError("policy v2 requires cutoff in YYYY-MM-DDTHH:MM:SSZ format")
    # Reject non-canonical strings that strptime tolerated.
    if parsed.strftime(_CUTOFF_FORMAT) != cutoff:
        raise ValueError("policy v2 requires cutoff in YYYY-MM-DDTHH:MM:SSZ format")
    return cutoff


def _read_rows(csv_text, columns, kind):
    """Parse CSV text into a list of dicts keyed by required columns.

    Returns [] for header-only or empty input. Raises ValueError on structural
    problems (missing header, missing/extra fields).
    """
    if csv_text is None:
        raise ValueError("%s csv is None" % kind)
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        # Completely empty input: treat like header-only empty dataset.
        return []
    # Strip a possible UTF-8 BOM on the first header cell.
    if header and header[0].startswith("\ufeff"):
        header[0] = header[0].lstrip("\ufeff")
    header = [h.strip() for h in header]
    if header != list(columns):
        raise ValueError(
            "%s csv header mismatch: expected %s got %s" % (kind, list(columns), header)
        )
    rows = []
    for line_no, fields in enumerate(reader, start=2):
        if not fields or (len(fields) == 1 and fields[0].strip() == ""):
            continue  # skip blank lines
        if len(fields) != len(header):
            raise ValueError(
                "%s csv line %d: expected %d fields, got %d"
                % (kind, line_no, len(header), len(fields))
            )
        rows.append(dict(zip(header, (f.strip() for f in fields))))
    return rows


def _index_unique(rows, key, kind):
    """Deduplicate rows by key: exact duplicates collapse; conflicts raise."""
    index = {}
    for row in rows:
        k = row.get(key, "")
        if k == "":
            raise ValueError("%s csv: empty %s" % (kind, key))
        if k in index:
            if index[k] == row:
                continue  # exact duplicate, count once
            raise ValueError(
                "%s csv: duplicate %s %r with conflicting fields" % (kind, key, k)
            )
        index[k] = row
    return index


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile paid orders against refunds. Returns contract dict.

    policy="v1": legacy column contract and amount rules; cutoff must be None.
    policy="v2": cutoff required; refunds carry status/created_at; amounts are
    rounded to cents with ROUND_HALF_UP per row.
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v1":
        if cutoff is not None:
            raise ValueError("cutoff is not supported by policy v1")
    else:
        cutoff = _validate_cutoff(cutoff)

    refund_columns = _REFUND_COLUMNS_V1 if policy == "v1" else _REFUND_COLUMNS_V2
    order_rows = _read_rows(orders_csv, _ORDER_COLUMNS, "orders")
    refund_rows = _read_rows(refunds_csv, refund_columns, "refunds")

    # Deduplicate first: conflicts are rejected even for rows that would be
    # ignored (pending / after-cutoff).
    orders = _index_unique(order_rows, "order_id", "orders")
    refunds = _index_unique(refund_rows, "refund_id", "refunds")

    # Validate orders and keep the paid ones within the cutoff window.
    paid = {}  # order_id -> {"customer": str, "paid_cents": int}
    for order_id, row in sorted(orders.items()):
        status = row.get("status", "").lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("order %s: unknown status %r" % (order_id, row.get("status")))
        customer = row.get("customer", "")
        if customer == "":
            raise ValueError("order %s: empty customer" % order_id)
        paid_cents = _parse_amount_cents(
            row.get("amount"), "order %s" % order_id, policy
        )
        if status != "paid":
            continue
        if policy == "v2" and row.get("created_at", "") > cutoff:
            continue  # after-cutoff orders are not counted
        paid[order_id] = {"customer": customer, "paid_cents": paid_cents}

    # Apply refunds.
    refund_cents_by_order = {order_id: 0 for order_id in paid}
    for refund_id, row in sorted(refunds.items()):
        order_id = row.get("order_id", "")
        if policy == "v2":
            status = row.get("status", "").lower()
            if status not in ("succeeded", "pending"):
                raise ValueError(
                    "refund %s: unknown status %r" % (refund_id, row.get("status"))
                )
            if status == "pending" or row.get("created_at", "") > cutoff:
                continue  # not counted
        # From here the refund is effective; its order must be known.
        if order_id not in orders:
            raise ValueError("refund %s: unknown order %r" % (refund_id, order_id))
        if order_id not in paid:
            if policy == "v2":
                order_row = orders[order_id]
                if (
                    order_row.get("status", "").lower() == "paid"
                    and order_row.get("created_at", "") > cutoff
                ):
                    continue  # order exists but excluded by cutoff: ignore
            raise ValueError(
                "refund %s: order %s is not paid" % (refund_id, order_id)
            )
        amount_cents = _parse_amount_cents(
            row.get("amount"), "refund %s" % refund_id, policy
        )
        refund_cents_by_order[order_id] += amount_cents
        if refund_cents_by_order[order_id] > paid[order_id]["paid_cents"]:
            raise ValueError(
                "refund %s: cumulative refunds exceed paid amount for order %s"
                % (refund_id, order_id)
            )

    # Build outputs (orders by order_id, customers by customer).
    result_orders = []
    customers_total = {}
    total_paid = total_refund = 0
    for order_id in sorted(paid):
        info = paid[order_id]
        refund_cents = refund_cents_by_order[order_id]
        paid_cents = info["paid_cents"]
        net_cents = paid_cents - refund_cents
        result_orders.append(
            {
                "order_id": order_id,
                "customer": info["customer"],
                "paid_cents": paid_cents,
                "refund_cents": refund_cents,
                "net_cents": net_cents,
            }
        )
        total_paid += paid_cents
        total_refund += refund_cents
        customer = info["customer"]
        customers_total[customer] = customers_total.get(customer, 0) + net_cents

    result_customers = [
        {"customer": name, "net_cents": customers_total[name]}
        for name in sorted(customers_total)
    ]

    return {
        "orders": result_orders,
        "customers": result_customers,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def export_bundle(result):
    """Serialize a reconcile result into the release bundle.

    Returns dict[str, str] with exactly three files per release-spec:
    - orders.csv: header order_id,customer,paid_cents,refund_cents,net_cents,
      rows in reconcile order, integer amounts as text.
    - customers.csv: header customer,net_cents, rows in reconcile order.
    - summary.json: JSON that parses to exactly result["totals"].
    """
    if not isinstance(result, dict) or "orders" not in result or "customers" not in result or "totals" not in result:
        raise ValueError("export_bundle: expected a reconcile result dict")

    orders_buf = io.StringIO()
    orders_writer = csv.writer(orders_buf)
    orders_writer.writerow(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"]
    )
    for row in result["orders"]:
        orders_writer.writerow(
            [
                str(row["order_id"]),
                str(row["customer"]),
                str(int(row["paid_cents"])),
                str(int(row["refund_cents"])),
                str(int(row["net_cents"])),
            ]
        )

    customers_buf = io.StringIO()
    customers_writer = csv.writer(customers_buf)
    customers_writer.writerow(["customer", "net_cents"])
    for row in result["customers"]:
        customers_writer.writerow([str(row["customer"]), str(int(row["net_cents"]))])

    return {
        "orders.csv": orders_buf.getvalue(),
        "customers.csv": customers_buf.getvalue(),
        "summary.json": json.dumps(result["totals"], sort_keys=True, separators=(",", ":")),
    }
