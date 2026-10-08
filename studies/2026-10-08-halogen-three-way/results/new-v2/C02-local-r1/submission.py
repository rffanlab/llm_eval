```python
def reconcile(events):
    seen_ids = set()
    accounts = {}

    for event in events:
        eid = event["event_id"]
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        account = event["account"]
        delta = event["delta_cents"]
        if account not in accounts:
            accounts[account] = {"balance_cents": 0, "event_count": 0}
        accounts[account]["balance_cents"] += delta
        accounts[account]["event_count"] += 1

    return [
        {
            "account": acct,
            "balance_cents": accounts[acct]["balance_cents"],
            "event_count": accounts[acct]["event_count"],
        }
        for acct in sorted(accounts)
    ]
```