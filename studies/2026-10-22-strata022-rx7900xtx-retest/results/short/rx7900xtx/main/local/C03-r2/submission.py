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
    running = {}
    started = set()
    jobs = []
    t = 0
    available = capacity

    while len(completed) < len(tasks):
        newly_done = [tid for tid, end in running.items() if end <= t]
        for tid in newly_done:
            completed.add(tid)
            available += task_map[tid]["units"]
            del running[tid]

        for tid in all_ids:
            if tid in started:
                continue
            task = task_map[tid]
            if not all(d in completed for d in task["deps"]):
                continue
            if task["units"] <= available:
                started.add(tid)
                end_time = t + task["duration"]
                running[tid] = end_time
                available -= task["units"]
                jobs.append({"id": tid, "start": t, "end": end_time})

        if running:
            t = min(running.values())
        else:
            break

    jobs.sort(key=lambda x: x["id"])
    makespan = max((j["end"] for j in jobs), default=0)
    return {"jobs": jobs, "makespan": makespan}
```