```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    for t in tasks:
        if t["units"] > capacity:
            raise ValueError("units exceeds capacity")
        task_map[t["id"]] = t

    for t in tasks:
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

    completed = set()
    started = set()
    running = []
    available = capacity
    t = 0
    jobs = []
    all_ids = sorted(task_map.keys())

    while len(completed) < len(tasks):
        new_running = []
        for (end_time, tid, units) in running:
            if end_time <= t:
                completed.add(tid)
                available += units
            else:
                new_running.append((end_time, tid, units))
        running = new_running

        ready = []
        for tid in all_ids:
            if tid not in started and tid not in completed:
                if all(d in completed for d in task_map[tid]["deps"]):
                    ready.append(tid)

        for tid in ready:
            units = task_map[tid]["units"]
            if units <= available:
                available -= units
                duration = task_map[tid]["duration"]
                end_time = t + duration
                running.append((end_time, tid, units))
                started.add(tid)
                jobs.append({"id": tid, "start": t, "end": end_time})

        if running:
            t = min(et for (et, _, _) in running)
        elif len(completed) < len(tasks):
            break

    makespan = max(j["end"] for j in jobs) if jobs else 0
    jobs.sort(key=lambda x: x["id"])
    return {"jobs": jobs, "makespan": makespan}
```