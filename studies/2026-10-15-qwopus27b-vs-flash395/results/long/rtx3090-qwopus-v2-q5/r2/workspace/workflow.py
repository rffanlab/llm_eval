import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import OrderedDict


def _parse_amount_v1(s, field_name="amount"):
    """Parse a decimal string into cents (int). Rejects NaN, Infinity, negatives, >2 decimal places."""
    s = s.strip()
    if not s:
        raise ValueError(f"Empty {field_name}")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"Invalid {field_name}: {s}")
    if d.is_nan() or d.is_infinite():
        raise ValueError(f"Invalid {field_name}: {s}")
    if d < 0:
        raise ValueError(f"Negative {field_name}: {s}")
    quantized = d.quantize(Decimal("0.01"))
    if d != quantized:
        raise ValueError(f"More than 2 decimal places in {field_name}: {s}")
    cents = int(quantized * 100)
    return cents


def _parse_amount_v2(s, field_name="amount"):
    """Parse a decimal string into cents (int). Allows multiple decimal places, rounds HALF_UP to integer cents."""
    s = s.strip()
    if not s:
        raise ValueError(f"Empty {field_name}")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"Invalid {field_name}: {s}")
    if d.is_nan() or d.is_infinite():
        raise ValueError(f"Invalid {field_name}: {s}")
    if d < 0:
        raise ValueError(f"Negative {field_name}: {s}")
    cents = int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return cents


def _read_csv(csv_str):
    """Read CSV string into list of dicts."""
    reader = csv.DictReader(io.StringIO(csv_str))
    rows = []
    for row in reader:
        rows.append(row)
    return rows


def _reconcile_v1(orders_csv, refunds_csv):
    """v1 reconciliation logic."""
    orders_rows = _read_csv(orders_csv)
    refunds_rows = _read_csv(refunds_csv)

    orders_map = {}
    for row in orders_rows:
        oid = row.get("order_id", "").strip()
        customer = row.get("customer", "").strip()
        amount_str = row.get("amount", "").strip()
        status = row.get("status", "").strip()
        created_at = row.get("created_at", "").strip()

        if oid in orders_map:
            existing = orders_map[oid]
            if (existing["customer"] != customer or
                    existing["amount_str"] != amount_str or
                    existing["status"] != status or
                    existing["created_at"] != created_at):
                raise ValueError(f"Duplicate order_id {oid} with different fields")
            continue

        paid_cents = _parse_amount_v1(amount_str, f"order {oid} amount")
        orders_map[oid] = {
            "customer": customer,
            "paid_cents": paid_cents,
            "status": status,
            "created_at": created_at,
            "amount_str": amount_str,
        }

    refunds_map = {}
    for row in refunds_rows:
        rid = row.get("refund_id", "").strip()
        oid = row.get("order_id", "").strip()
        amount_str = row.get("amount", "").strip()

        if rid in refunds_map:
            existing = refunds_map[rid]
            if existing["order_id"] != oid or existing["amount_str"] != amount_str:
                raise ValueError(f"Duplicate refund_id {rid} with different fields")
            continue

        refund_cents = _parse_amount_v1(amount_str, f"refund {rid} amount")
        refunds_map[rid] = {
            "order_id": oid,
            "refund_cents": refund_cents,
            "amount_str": amount_str,
        }

    order_refunds = {}
    for rid, rinfo in refunds_map.items():
        oid = rinfo["order_id"]
        if oid not in orders_map:
            raise ValueError(f"Refund {rid} references unknown order {oid}")
        if orders_map[oid]["status"] != "paid":
            raise ValueError(f"Refund {rid} references non-paid order {oid}")
        order_refunds[oid] = order_refunds.get(oid, 0) + rinfo["refund_cents"]

    for oid, total_refund in order_refunds.items():
        paid = orders_map[oid]["paid_cents"]
        if total_refund > paid:
            raise ValueError(f"Refund for order {oid} exceeds paid amount")

    paid_orders = {oid: info for oid, info in orders_map.items() if info["status"] == "paid"}

    orders_result = []
    for oid in sorted(paid_orders.keys()):
        info = paid_orders[oid]
        paid_cents = info["paid_cents"]
        refund_cents = order_refunds.get(oid, 0)
        net_cents = paid_cents - refund_cents
        orders_result.append({
            "order_id": oid,
            "customer": info["customer"],
            "paid_cents": paid_cents,
            "refund_cents": refund_cents,
            "net_cents": net_cents,
        })

    customer_net = {}
    for oid, info in paid_orders.items():
        cust = info["customer"]
        paid_cents = info["paid_cents"]
        refund_cents = order_refunds.get(oid, 0)
        net_cents = paid_cents - refund_cents
        customer_net[cust] = customer_net.get(cust, 0) + net_cents

    customers_result = []
    for cust in sorted(customer_net.keys()):
        customers_result.append({
            "customer": cust,
            "net_cents": customer_net[cust],
        })

    total_paid = sum(info["paid_cents"] for info in paid_orders.values())
    total_refund = sum(order_refunds.get(oid, 0) for oid in paid_orders)
    total_net = total_paid - total_refund

    return {
        "orders": orders_result,
        "customers": customers_result,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_net,
        },
    }


def _reconcile_v2(orders_csv, refunds_csv, cutoff):
    """v2 reconciliation logic with cutoff, refund status, and HALF_UP rounding."""
    orders_rows = _read_csv(orders_csv)
    refunds_rows = _read_csv(refunds_csv)

    orders_map = {}
    for row in orders_rows:
        oid = row.get("order_id", "").strip()
        customer = row.get("customer", "").strip()
        amount_str = row.get("amount", "").strip()
        status = row.get("status", "").strip()
        created_at = row.get("created_at", "").strip()

        if oid in orders_map:
            existing = orders_map[oid]
            if (existing["customer"] != customer or
                    existing["amount_str"] != amount_str or
                    existing["status"] != status or
                    existing["created_at"] != created_at):
                raise ValueError(f"Duplicate order_id {oid} with different fields")
            continue

        paid_cents = _parse_amount_v2(amount_str, f"order {oid} amount")
        orders_map[oid] = {
            "customer": customer,
            "paid_cents": paid_cents,
            "status": status,
            "created_at": created_at,
            "amount_str": amount_str,
        }

    refunds_map = {}
    for row in refunds_rows:
        rid = row.get("refund_id", "").strip()
        oid = row.get("order_id", "").strip()
        amount_str = row.get("amount", "").strip()
        status = row.get("status", "").strip()
        created_at = row.get("created_at", "").strip()

        if rid in refunds_map:
            existing = refunds_map[rid]
            if (existing["order_id"] != oid or
                    existing["amount_str"] != amount_str or
                    existing["status"] != status or
                    existing["created_at"] != created_at):
                raise ValueError(f"Duplicate refund_id {rid} with different fields")
            continue

        refund_cents = _parse_amount_v2(amount_str, f"refund {rid} amount")
        refunds_map[rid] = {
            "order_id": oid,
            "refund_cents": refund_cents,
            "status": status,
            "created_at": created_at,
            "amount_str": amount_str,
        }

    for rid, rinfo in refunds_map.items():
        oid = rinfo["order_id"]
        if oid not in orders_map:
            raise ValueError(f"Refund {rid} references unknown order {oid}")
        if orders_map[oid]["status"] != "paid":
            raise ValueError(f"Refund {rid} references non-paid order {oid}")

    active_orders = {}
    for oid, info in orders_map.items():
        if info["status"] == "paid" and info["created_at"] <= cutoff:
            active_orders[oid] = info

    active_refunds = {}
    for rid, rinfo in refunds_map.items():
        if rinfo["status"] == "succeeded" and rinfo["created_at"] <= cutoff:
            active_refunds[rid] = rinfo

    order_refunds = {}
    for rid, rinfo in active_refunds.items():
        oid = rinfo["order_id"]
        if oid not in active_orders:
            continue
        order_refunds[oid] = order_refunds.get(oid, 0) + rinfo["refund_cents"]

    for oid, total_refund in order_refunds.items():
        paid = active_orders[oid]["paid_cents"]
        if total_refund > paid:
            raise ValueError(f"Refund for order {oid} exceeds paid amount")

    orders_result = []
    for oid in sorted(active_orders.keys()):
        info = active_orders[oid]
        paid_cents = info["paid_cents"]
        refund_cents = order_refunds.get(oid, 0)
        net_cents = paid_cents - refund_cents
        orders_result.append({
            "order_id": oid,
            "customer": info["customer"],
            "paid_cents": paid_cents,
            "refund_cents": refund_cents,
            "net_cents": net_cents,
        })

    customer_net = {}
    for oid, info in active_orders.items():
        cust = info["customer"]
        paid_cents = info["paid_cents"]
        refund_cents = order_refunds.get(oid, 0)
        net_cents = paid_cents - refund_cents
        customer_net[cust] = customer_net.get(cust, 0) + net_cents

    customers_result = []
    for cust in sorted(customer_net.keys()):
        customers_result.append({
            "customer": cust,
            "net_cents": customer_net[cust],
        })

    total_paid = sum(info["paid_cents"] for info in active_orders.values())
    total_refund = sum(order_refunds.get(oid, 0) for oid in active_orders)
    total_net = total_paid - total_refund

    return {
        "orders": orders_result,
        "customers": customers_result,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_net,
        },
    }


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile orders and refunds per v1/v2 contract."""
    if policy == "v1":
        return _reconcile_v1(orders_csv, refunds_csv)
    elif policy == "v2":
        if cutoff is None:
            raise ValueError("cutoff is required for policy v2")
        return _reconcile_v2(orders_csv, refunds_csv, cutoff)
    else:
        raise ValueError(f"Unsupported policy: {policy}")


def export_bundle(result):
    """Export reconciliation result as a bundle of three files.
    
    Returns dict with exactly three keys:
      - "orders.csv": CSV with header order_id,customer,paid_cents,refund_cents,net_cents
      - "customers.csv": CSV with header customer,net_cents
      - "summary.json": JSON of result["totals"]
    """
    # orders.csv
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["order_id", "customer", "paid_cents", "refund_cents", "net_cents"])
    for order in result["orders"]:
        writer.writerow([
            order["order_id"],
            order["customer"],
            str(order["paid_cents"]),
            str(order["refund_cents"]),
            str(order["net_cents"]),
        ])
    orders_csv = buf.getvalue()

    # customers.csv
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["customer", "net_cents"])
    for cust in result["customers"]:
        writer.writerow([
            cust["customer"],
            str(cust["net_cents"]),
        ])
    customers_csv = buf.getvalue()

    # summary.json
    summary_json = json.dumps(result["totals"], separators=(",", ":"))

    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
