def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    # TODO: broken prototype; replace using the documented contract.
    return {"orders": [], "customers": [], "totals": {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}}

def export_bundle(result):
    return {"summary.json": "{}"}
