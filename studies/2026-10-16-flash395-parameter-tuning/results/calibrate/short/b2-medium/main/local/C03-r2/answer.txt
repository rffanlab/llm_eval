```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    id_set = set()
    for t in tasks:
        id_set.add(t["id"])

    for t in tasks:
        if t["units"] > capacity:
            raise ValueError("units exceeds capacity")
        for d in t["deps"]:
            if d not in id_set:
                raise ValueError("unknown dependency")

    in_degree = {t["id"]: 0 for t in tasks}
    adj = {t["id"]: [] for t in tasks}
    for t in tasks:
        for d in t["deps"]:
            adj[d].append(t["id"])
            in_degree[t["id"]] += 1

    queue = [tid for tid in in_degree if in_degree[tid] == 0]
    topo_count = 0
    while queue:
        node = queue.pop(0)
        topo_count += 1
        for nb in adj[node]:
            in_degree[nb] -= 1
            if in_degree[nb] == 0:
                queue.append(nb)

    if topo_count != len(tasks):
        raise ValueError("circular dependency")

    task_map = {t["id"]: t for t in tasks}
    completed = set()
    started = set()
    running = []
    available = capacity
    current_time = 0
    jobs = []

    while len(completed) < len(tasks):
        new_running = []
        for entry in running:
            end_time, tid, units = entry
            if end_time <= current_time:
                available += units
                completed.add(tid)
            else:
                new_running.append(entry)
        running = new_running

        candidates = sorted(
            t["id"] for t in tasks
            if t["id"] not in started and all(d in completed for d in t["deps"])
        )
        for tid in candidates:
            t = task_map[tid]
            if t["units"] <= available:
                available -= t["units"]
                started.add(tid)
                end_time = current_time + t["duration"]
                running.append((end_time, tid, t["units"]))
                jobs.append({"id": tid, "start": current_time, "end": end_time})

        if running:
            current_time = min(e for e, _, _ in running)
        elif len(completed) < len(tasks):
            raise ValueError("circular dependency")

    jobs.sort(key=lambda x: x["id"])
    makespan = max(j["end"] for j in jobs) if jobs else 0

    return {"jobs": jobs, "makespan": makespan}
```