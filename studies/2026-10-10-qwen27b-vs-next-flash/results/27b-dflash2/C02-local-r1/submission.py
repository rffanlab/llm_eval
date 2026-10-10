```python
def reconcile(events):
    seen = set()
    balances = {}
    counts = {}

    for e in events:
        eid = e["event_id"]
        if eid in seen:
            continue
        seen.add(eid)
        acct = e["account"]
        balances[acct] = balances.get(acct, 0) + e["delta_cents"]
        counts[acct] = counts.get(acct, 0) + 1

    return [
        {"account": a, "balance_cents": balances[a], "event_count": counts[a]}
        for a in sorted(balances)
    ]
```