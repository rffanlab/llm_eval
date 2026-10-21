```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    for t in tasks:
        task_map[t["id"]] = t

    for t in tasks:
        if t["units"] > capacity:
            raise ValueError("units exceeds capacity")
        for d in t["deps"]:
            if d not in task_map:
                raise ValueError("unknown dependency")

    in_degree = {t["id"]: 0 for t in tasks}
    adj = {t["id"]: [] for t in tasks}
    for t in tasks:
        for d in t["deps"]:
            adj[d].append(t["id"])
            in_degree[t["id"]] += 1

    queue = [tid for tid in in_degree if in_degree[tid] == 0]
    count = 0
    while queue:
        node = queue.pop(0)
        count += 1
        for nb in adj[node]:
            in_degree[nb] -= 1
            if in_degree[nb] == 0:
                queue.append(nb)
    if count != len(tasks):
        raise ValueError("circular dependency")

    current_time = 0
    running = []
    completed = set()
    started = set()
    result = {}
    remaining = capacity

    while len(completed) < len(tasks):
        new_running = []
        for end_time, tid, units in running:
            if end_time <= current_time:
                completed.add(tid)
                remaining += units
            else:
                new_running.append((end_time, tid, units))
        running = new_running

        candidates = []
        for t in tasks:
            tid = t["id"]
            if tid in started:
                continue
            if all(d in completed for d in t["deps"]):
                candidates.append(tid)
        candidates.sort()

        for tid in candidates:
            t = task_map[tid]
            if t["units"] <= remaining:
                started.add(tid)
                remaining -= t["units"]
                end_time = current_time + t["duration"]
                running.append((end_time, tid, t["units"]))
                result[tid] = (current_time, end_time)

        if running:
            current_time = min(e for e, _, _ in running)
        elif len(completed) < len(tasks):
            break

    jobs = sorted(
        [{"id": tid, "start": s, "end": e} for tid, (s, e) in result.items()],
        key=lambda x: x["id"],
    )
    makespan = max(e for _, e in result.values()) if result else 0

    return {"jobs": jobs, "makespan": makespan}
```