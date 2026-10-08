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

    completed = set()
    running = []
    started = set()
    result = {}
    t = 0

    while len(completed) < len(tasks):
        new_running = []
        for (end_time, tid, units) in running:
            if end_time <= t:
                completed.add(tid)
            else:
                new_running.append((end_time, tid, units))
        running = new_running

        ready = []
        for tsk in tasks:
            tid = tsk["id"]
            if tid in completed or tid in started:
                continue
            if all(d in completed for d in tsk["deps"]):
                ready.append(tsk)
        ready.sort(key=lambda x: x["id"])

        used = sum(u for (_, _, u) in running)
        for tsk in ready:
            if tsk["units"] <= capacity - used:
                started.add(tsk["id"])
                end = t + tsk["duration"]
                running.append((end, tsk["id"], tsk["units"]))
                result[tsk["id"]] = (t, end)
                used += tsk["units"]

        if running:
            t = min(e for (e, _, _) in running)
        elif len(completed) < len(tasks):
            break

    jobs = sorted(
        [{"id": tid, "start": s, "end": e} for tid, (s, e) in result.items()],
        key=lambda x: x["id"]
    )
    makespan = max(e for (_, _, e) in [(tid, s, e) for tid, (s, e) in result.items()]) if result else 0

    return {"jobs": jobs, "makespan": makespan}
```