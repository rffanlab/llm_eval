def reconcile(events):
    seen_event_ids = set()
    balances = {}
    counts = {}

    for event in events:
        event_id = event["event_id"]
        if event_id in seen_event_ids:
            continue

        seen_event_ids.add(event_id)

        account = event["account"]
        delta_cents = event["delta_cents"]

        balances[account] = balances.get(account, 0) + delta_cents
        counts[account] = counts.get(account, 0) + 1

    return [
        {
            "account": account,
            "balance_cents": balances[account],
            "event_count": counts[account],
        }
        for account in sorted(balances)
    ]