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

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {t["id"]: WHITE for t in tasks}

    def _dfs(node):
        color[node] = GRAY
        for dep in task_map[node]["deps"]:
            if color[dep] == GRAY:
                raise ValueError("circular dependency")
            if color[dep] == WHITE:
                _dfs(dep)
        color[node] = BLACK

    for t in tasks:
        if color[t["id"]] == WHITE:
            _dfs(t["id"])

    current_time = 0
    running = []
    completed = set()
    started = set()
    available = capacity
    results = []
    total = len(tasks)

    while len(completed) < total:
        new_running = []
        for (end_time, units, tid) in running:
            if end_time <= current_time:
                completed.add(tid)
                available += units
            else:
                new_running.append((end_time, units, tid))
        running = new_running

        eligible = []
        for t in tasks:
            tid = t["id"]
            if tid in started:
                continue
            if all(d in completed for d in t["deps"]):
                eligible.append(t)

        eligible.sort(key=lambda x: x["id"])

        for t in eligible:
            if t["units"] <= available:
                available -= t["units"]
                started.add(t["id"])
                end_time = current_time + t["duration"]
                running.append((end_time, t["units"], t["id"]))
                results.append({"id": t["id"], "start": current_time, "end": end_time})

        if running:
            current_time = min(r[0] for r in running)
        elif len(completed) < total:
            raise ValueError("deadlock detected")

    results.sort(key=lambda x: x["id"])
    makespan = max(r["end"] for r in results) if results else 0

    return {"jobs": results, "makespan": makespan}
```