import csv
import io
import json
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


def money(value, policy):
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError('invalid amount')
    if not number.is_finite() or number < 0:
        raise ValueError('invalid amount')
    if policy == 'v1':
        exponent = number.as_tuple().exponent
        if exponent < -2:
            raise ValueError('v1 precision')
        return int((number * 100).to_integral_value(rounding=ROUND_HALF_UP))
    return int((number * 100).to_integral_value(rounding=ROUND_HALF_UP))


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def reconcile(orders_csv, refunds_csv, policy='v1', cutoff=None):
    if policy not in ('v1', 'v2'):
        raise ValueError('policy')
    if policy == 'v2' and not cutoff:
        raise ValueError('cutoff required')
    orders = rows(orders_csv)
    refunds = rows(refunds_csv)
    order_map = {}
    for row in orders:
        oid = row['order_id']
        values = tuple(row.values())
        if oid in order_map and order_map[oid] != values:
            raise ValueError('order conflict')
        order_map[oid] = values
    refund_map = {}
    for row in refunds:
        rid = row['refund_id']
        values = tuple(row.values())
        if rid in refund_map and refund_map[rid] != values:
            raise ValueError('refund conflict')
        refund_map[rid] = values
    paid = {}
    for oid, values in order_map.items():
        row = dict(zip(orders[0].keys() if orders else [], values))
        amount = money(row['amount'], policy)
        if policy == 'v1':
            included = row['status'] == 'paid'
        else:
            included = row['status'] == 'paid' and row['created_at'] <= cutoff
        paid[oid] = {'row': row, 'paid': amount, 'included': included}
    refund_totals = dict((oid, 0) for oid in paid)
    for rid, values in refund_map.items():
        row = dict(zip(refunds[0].keys() if refunds else [], values))
        oid = row['order_id']
        if oid not in paid or paid[oid]['row']['status'] == 'cancelled':
            raise ValueError('invalid refund order')
        if policy == 'v1':
            active = True
        else:
            if row['status'] not in ('succeeded', 'pending'):
                raise ValueError('refund status')
            active = row['status'] == 'succeeded' and row['created_at'] <= cutoff and paid[oid]['included']
        amount = money(row['amount'], policy)
        if active:
            refund_totals[oid] += amount
            if refund_totals[oid] > paid[oid]['paid']:
                raise ValueError('excess refund')
    result_orders = []
    for oid in sorted(paid):
        item = paid[oid]
        if not item['included']:
            continue
        refund = refund_totals[oid]
        result_orders.append({'order_id': oid, 'customer': item['row']['customer'], 'paid_cents': item['paid'], 'refund_cents': refund, 'net_cents': item['paid'] - refund})
    customers = {}
    for row in result_orders:
        customers[row['customer']] = customers.get(row['customer'], 0) + row['net_cents']
    result_customers = [{'customer': name, 'net_cents': customers[name]} for name in sorted(customers)]
    totals = {'paid_cents': sum(row['paid_cents'] for row in result_orders), 'refund_cents': sum(row['refund_cents'] for row in result_orders), 'net_cents': sum(row['net_cents'] for row in result_orders)}
    return {'orders': result_orders, 'customers': result_customers, 'totals': totals}


def export_bundle(result):
    output = {}
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=['order_id', 'customer', 'paid_cents', 'refund_cents', 'net_cents'], lineterminator='\n')
    writer.writeheader()
    writer.writerows(result['orders'])
    output['orders.csv'] = stream.getvalue()
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=['customer', 'net_cents'], lineterminator='\n')
    writer.writeheader()
    writer.writerows(result['customers'])
    output['customers.csv'] = stream.getvalue()
    output['summary.json'] = json.dumps(result['totals'], ensure_ascii=False, separators=(',', ':'))
    return output
