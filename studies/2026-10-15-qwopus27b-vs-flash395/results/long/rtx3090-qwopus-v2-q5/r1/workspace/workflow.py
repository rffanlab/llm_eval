import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import OrderedDict


def _parse_amount_v1(s):
    """v1: max 2 decimal places, reject NaN/Infinity/negatives."""
    s = s.strip()
    if not s:
        raise ValueError("Empty amount")
    lower = s.lower()
    if lower in ('nan', 'inf', '+inf', '-inf', 'infinity', '+infinity', '-infinity'):
        raise ValueError(f"Invalid amount: {s}")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"Invalid amount: {s}")
    if d.is_nan() or d.is_infinite():
        raise ValueError(f"Invalid amount: {s}")
    if d < 0:
        raise ValueError(f"Negative amount: {s}")
    quantized = d.quantize(Decimal('0.01'))
    if d != quantized:
        raise ValueError(f"More than 2 decimal places: {s}")
    return int(d * 100)


def _parse_amount_v2(s):
    """v2: allow multiple decimals, ROUND_HALF_UP to integer cents."""
    s = s.strip()
    if not s:
        raise ValueError("Empty amount")
    lower = s.lower()
    if lower in ('nan', 'inf', '+inf', '-inf', 'infinity', '+infinity', '-infinity'):
        raise ValueError(f"Invalid amount: {s}")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"Invalid amount: {s}")
    if d.is_nan() or d.is_infinite():
        raise ValueError(f"Invalid amount: {s}")
    if d < 0:
        raise ValueError(f"Negative amount: {s}")
    cents = int((d * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return cents


def _read_csv(text):
    """Read CSV text into list of dicts."""
    if not text or not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        rows.append(row)
    return rows


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """Reconcile orders and refunds per v1/v2 contract."""
    # Validate policy
    if policy not in ('v1', 'v2'):
        raise ValueError(f"Invalid policy: {policy}")
    if policy == 'v2' and cutoff is None:
        raise ValueError("cutoff is required for v2 policy")

    orders_rows = _read_csv(orders_csv)
    refunds_rows = _read_csv(refunds_csv)

    # --- Deduplicate orders by order_id ---
    orders_map = {}  # order_id -> row dict
    for row in orders_rows:
        oid = row.get('order_id', '').strip()
        if oid in orders_map:
            existing = orders_map[oid]
            if existing != row:
                raise ValueError(f"Duplicate order_id {oid} with different fields")
            continue
        orders_map[oid] = row

    # --- Deduplicate refunds by refund_id ---
    refunds_map = {}  # refund_id -> row dict
    for row in refunds_rows:
        rid = row.get('refund_id', '').strip()
        if rid in refunds_map:
            existing = refunds_map[rid]
            if existing != row:
                raise ValueError(f"Duplicate refund_id {rid} with different fields")
            continue
        refunds_map[rid] = row

    # --- Determine which orders are paid and within cutoff ---
    if policy == 'v1':
        paid_orders = {}
        for oid, row in orders_map.items():
            status = row.get('status', '').strip()
            if status == 'paid':
                paid_orders[oid] = row
    else:
        paid_orders = {}
        for oid, row in orders_map.items():
            status = row.get('status', '').strip()
            if status != 'paid':
                continue
            created_at = row.get('created_at', '').strip()
            if created_at <= cutoff:
                paid_orders[oid] = row

    # --- Process refunds ---
    refund_by_order = {}  # order_id -> total refund cents

    if policy == 'v1':
        for rid, row in refunds_map.items():
            oid = row.get('order_id', '').strip()
            if oid not in paid_orders:
                raise ValueError(f"Refund {rid} references unknown or non-paid order {oid}")
            amount_str = row.get('amount', '').strip()
            refund_cents = _parse_amount_v1(amount_str)
            if oid not in refund_by_order:
                refund_by_order[oid] = 0
            refund_by_order[oid] += refund_cents
    else:
        for rid, row in refunds_map.items():
            oid = row.get('order_id', '').strip()
            status = row.get('status', '').strip()
            created_at = row.get('created_at', '').strip()

            # Check if order truly exists (regardless of cutoff)
            if oid not in orders_map:
                raise ValueError(f"Refund {rid} references unknown order {oid}")

            # Check if order is cancelled
            order_status = orders_map[oid].get('status', '').strip()
            if order_status == 'cancelled':
                raise ValueError(f"Refund {rid} references cancelled order {oid}")

            # If order is paid but excluded by cutoff, ignore this refund
            if oid not in paid_orders:
                continue

            # If refund is pending or after cutoff, ignore
            if status != 'succeeded':
                continue
            if created_at > cutoff:
                continue

            # Valid refund - apply it
            amount_str = row.get('amount', '').strip()
            refund_cents = _parse_amount_v2(amount_str)
            if oid not in refund_by_order:
                refund_by_order[oid] = 0
            refund_by_order[oid] += refund_cents

    # --- Check cumulative refund does not exceed paid ---
    for oid, total_refund in refund_by_order.items():
        row = paid_orders[oid]
        amount_str = row.get('amount', '').strip()
        if policy == 'v1':
            paid_cents = _parse_amount_v1(amount_str)
        else:
            paid_cents = _parse_amount_v2(amount_str)
        if total_refund > paid_cents:
            raise ValueError(f"Refund for order {oid} exceeds paid amount")

    # --- Build order results ---
    order_results = []
    for oid in sorted(paid_orders.keys()):
        row = paid_orders[oid]
        customer = row.get('customer', '').strip()
        amount_str = row.get('amount', '').strip()
        if policy == 'v1':
            paid_cents = _parse_amount_v1(amount_str)
        else:
            paid_cents = _parse_amount_v2(amount_str)

        refund_cents = refund_by_order.get(oid, 0)
        net_cents = paid_cents - refund_cents

        order_results.append({
            'order_id': oid,
            'customer': customer,
            'paid_cents': paid_cents,
            'refund_cents': refund_cents,
            'net_cents': net_cents
        })

    # --- Customer summary ---
    customer_map = {}
    for order in order_results:
        cust = order['customer']
        if cust not in customer_map:
            customer_map[cust] = 0
        customer_map[cust] += order['net_cents']

    customers = []
    for cust in sorted(customer_map.keys()):
        customers.append({
            'customer': cust,
            'net_cents': customer_map[cust]
        })

    # --- Totals ---
    total_paid = sum(o['paid_cents'] for o in order_results)
    total_refund = sum(o['refund_cents'] for o in order_results)
    total_net = total_paid - total_refund

    return {
        'orders': order_results,
        'customers': customers,
        'totals': {
            'paid_cents': total_paid,
            'refund_cents': total_refund,
            'net_cents': total_net
        }
    }


def export_bundle(result):
    """Export reconcile result as a dict of three files per release-spec.md."""
    # orders.csv
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    writer.writerow(['order_id', 'customer', 'paid_cents', 'refund_cents', 'net_cents'])
    for order in result['orders']:
        writer.writerow([
            order['order_id'],
            order['customer'],
            str(order['paid_cents']),
            str(order['refund_cents']),
            str(order['net_cents'])
        ])
    orders_csv = buf.getvalue()

    # customers.csv
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    writer.writerow(['customer', 'net_cents'])
    for cust in result['customers']:
        writer.writerow([
            cust['customer'],
            str(cust['net_cents'])
        ])
    customers_csv = buf.getvalue()

    # summary.json
    summary_json = json.dumps(result['totals'], separators=(',', ':'))

    return {
        'orders.csv': orders_csv,
        'customers.csv': customers_csv,
        'summary.json': summary_json
    }
