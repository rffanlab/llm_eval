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
    running = {}
    started = set()
    available = capacity
    t = 0
    jobs = []
    all_ids = sorted(task_map.keys())

    while len(completed) < len(tasks):
        to_release = [tid for tid in running if running[tid] <= t]
        for tid in to_release:
            available += task_map[tid]["units"]
            del running[tid]
            completed.add(tid)

        for tid in all_ids:
            if tid in started:
                continue
            task = task_map[tid]
            if all(d in completed for d in task["deps"]):
                if available >= task["units"]:
                    started.add(tid)
                    end_t = t + task["duration"]
                    running[tid] = end_t
                    available -= task["units"]
                    jobs.append({"id": tid, "start": t, "end": end_t})

        if running:
            t = min(running.values())
        else:
            break

    makespan = max(j["end"] for j in jobs) if jobs else 0
    jobs.sort(key=lambda x: x["id"])

    return {"jobs": jobs, "makespan": makespan}
```