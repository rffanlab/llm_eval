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

    all_ids = sorted(task_map.keys())
    completed = set()
    started = set()
    running = []
    current_time = 0
    jobs = []

    while len(completed) < len(tasks):
        new_running = []
        for (end_time, tid, units) in running:
            if end_time <= current_time:
                completed.add(tid)
            else:
                new_running.append((end_time, tid, units))
        running = new_running

        available = capacity - sum(u for (_, _, u) in running)

        for tid in all_ids:
            if tid in started:
                continue
            t = task_map[tid]
            if all(d in completed for d in t["deps"]):
                if t["units"] <= available:
                    started.add(tid)
                    end_time = current_time + t["duration"]
                    running.append((end_time, tid, t["units"]))
                    available -= t["units"]
                    jobs.append({"id": tid, "start": current_time, "end": end_time})

        if running:
            current_time = min(et for (et, _, _) in running)
        elif len(completed) < len(tasks):
            break

    jobs.sort(key=lambda x: x["id"])
    makespan = max(j["end"] for j in jobs) if jobs else 0
    return {"jobs": jobs, "makespan": makespan}
```