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
        for dep in t["deps"]:
            if dep not in task_map:
                raise ValueError("unknown dependency")

    in_degree = {t["id"]: 0 for t in tasks}
    adj = {t["id"]: [] for t in tasks}
    for t in tasks:
        for dep in t["deps"]:
            adj[dep].append(t["id"])
            in_degree[t["id"]] += 1

    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for nb in adj[node]:
            in_degree[nb] -= 1
            if in_degree[nb] == 0:
                queue.append(nb)

    if visited != len(tasks):
        raise ValueError("circular dependency")

    completed = set()
    running = {}
    pending = set(t["id"] for t in tasks)
    used = 0
    now = 0
    jobs = []

    while pending or running:
        finished = [tid for tid, end in running.items() if end <= now]
        for tid in finished:
            completed.add(tid)
            used -= task_map[tid]["units"]
            del running[tid]

        ready = sorted(
            tid for tid in pending
            if all(dep in completed for dep in task_map[tid]["deps"])
        )
        for tid in ready:
            u = task_map[tid]["units"]
            if used + u <= capacity:
                end = now + task_map[tid]["duration"]
                running[tid] = end
                used += u
                pending.discard(tid)
                jobs.append({"id": tid, "start": now, "end": end})

        if running:
            now = min(running.values())
        elif pending:
            break

    makespan = max((j["end"] for j in jobs), default=0)
    jobs.sort(key=lambda x: x["id"])
    return {"jobs": jobs, "makespan": makespan}
```