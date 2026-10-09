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

    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    count = 0
    while queue:
        node = queue.pop(0)
        count += 1
        for nb in adj[node]:
            in_degree[nb] -= 1
            if in_degree[nb] == 0:
                queue.append(nb)

    if count < len(tasks):
        raise ValueError("circular dependency")

    completed = set()
    running = {}
    started = set()
    jobs = {}
    t = 0

    while len(completed) < len(tasks):
        finished = [tid for tid, end in running.items() if end <= t]
        for tid in finished:
            completed.add(tid)
            del running[tid]

        ready = []
        for task in tasks:
            tid = task["id"]
            if tid in started:
                continue
            if all(d in completed for d in task["deps"]):
                ready.append(task)

        ready.sort(key=lambda x: x["id"])

        used = sum(task_map[tid]["units"] for tid in running)
        for task in ready:
            if used + task["units"] <= capacity:
                started.add(task["id"])
                end_time = t + task["duration"]
                running[task["id"]] = end_time
                jobs[task["id"]] = (t, end_time)
                used += task["units"]

        if running:
            t = min(running.values())
        elif len(completed) < len(tasks):
            raise ValueError("deadlock")

    result_jobs = sorted(
        [{"id": tid, "start": s, "end": e} for tid, (s, e) in jobs.items()],
        key=lambda x: x["id"]
    )
    makespan = max(e for _, e in jobs.values()) if jobs else 0

    return {"jobs": result_jobs, "makespan": makespan}
```