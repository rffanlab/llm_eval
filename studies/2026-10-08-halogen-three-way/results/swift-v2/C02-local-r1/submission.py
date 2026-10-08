```python
def reconcile(events):
    seen = set()
    accounts = {}
    for event in events:
        eid = event["event_id"]
        if eid in seen:
            continue
        seen.add(eid)
        acct = event["account"]
        delta = event["delta_cents"]
        if acct not in accounts:
            accounts[acct] = {"balance_cents": 0, "event_count": 0}
        accounts[acct]["balance_cents"] += delta
        accounts[acct]["event_count"] += 1
    result = []
    for acct in sorted(accounts):
        result.append({
            "account": acct,
            "balance_cents": accounts[acct]["balance_cents"],
            "event_count": accounts[acct]["event_count"],
        })
    return result
```