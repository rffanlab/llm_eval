```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    ids = set()
    for t in tasks:
        ids.add(t["id"])

    for t in tasks:
        if t["units"] > capacity:
            raise ValueError("units exceeds capacity")
        for d in t["deps"]:
            if d not in ids:
                raise ValueError("unknown dependency")

    in_degree = {t["id"]: 0 for t in tasks}
    dependents = {t["id"]: [] for t in tasks}
    for t in tasks:
        for d in t["deps"]:
            in_degree[t["id"]] += 1
            dependents[d].append(t["id"])

    queue = [tid for tid in in_degree if in_degree[tid] == 0]
    count = 0
    while queue:
        node = queue.pop(0)
        count += 1
        for dep in dependents[node]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    if count != len(tasks):
        raise ValueError("circular dependency")

    completed = set()
    started = set()
    running = []
    results = {}
    t = 0

    while len(completed) < len(tasks):
        new_running = []
        for (end_time, tid, units) in running:
            if end_time <= t:
                completed.add(tid)
            else:
                new_running.append((end_time, tid, units))
        running = new_running

        used = sum(u for (_, _, u) in running)
        available = capacity - used

        eligible = []
        for task in tasks:
            tid = task["id"]
            if tid in started:
                continue
            if all(d in completed for d in task["deps"]):
                eligible.append(task)

        eligible.sort(key=lambda x: x["id"])

        for task in eligible:
            if task["units"] <= available:
                started.add(task["id"])
                results[task["id"]] = (t, t + task["duration"])
                running.append((t + task["duration"], task["id"], task["units"]))
                available -= task["units"]

        if running:
            t = min(end_time for (end_time, _, _) in running)
        else:
            break

    jobs = [{"id": tid, "start": results[tid][0], "end": results[tid][1]}
            for tid in sorted(results.keys())]
    makespan = max((end for (_, end) in results.values()), default=0)

    return {"jobs": jobs, "makespan": makespan}
```