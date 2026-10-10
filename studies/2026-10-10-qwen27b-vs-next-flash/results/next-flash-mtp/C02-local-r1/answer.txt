```python
def reconcile(events):
    if not events:
        return []

    seen_ids = set()
    deduped = []
    for event in events:
        eid = event["event_id"]
        if eid not in seen_ids:
            seen_ids.add(eid)
            deduped.append(event)

    accounts = {}
    for event in deduped:
        acct = event["account"]
        if acct not in accounts:
            accounts[acct] = {"balance_cents": 0, "event_count": 0}
        accounts[acct]["balance_cents"] += event["delta_cents"]
        accounts[acct]["event_count"] += 1

    result = []
    for acct in sorted(accounts.keys()):
        result.append({
            "account": acct,
            "balance_cents": accounts[acct]["balance_cents"],
            "event_count": accounts[acct]["event_count"],
        })

    return result
```