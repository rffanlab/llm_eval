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

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {t["id"]: WHITE for t in tasks}

    def dfs(node):
        color[node] = GRAY
        for dep in task_map[node]["deps"]:
            if color[dep] == GRAY:
                raise ValueError("circular dependency")
            if color[dep] == WHITE:
                dfs(dep)
        color[node] = BLACK

    for t in tasks:
        if color[t["id"]] == WHITE:
            dfs(t["id"])

    completed = set()
    started = set()
    running = {}
    available = capacity
    t = 0
    result = {}

    while len(completed) < len(tasks):
        newly_completed = [tid for tid, end in running.items() if end <= t]
        for tid in newly_completed:
            completed.add(tid)
            available += task_map[tid]["units"]
            del running[tid]

        ready = []
        for tid in task_map:
            if tid in started:
                continue
            if all(d in completed for d in task_map[tid]["deps"]):
                ready.append(tid)

        ready.sort()

        for tid in ready:
            if available >= task_map[tid]["units"]:
                available -= task_map[tid]["units"]
                started.add(tid)
                end_time = t + task_map[tid]["duration"]
                running[tid] = end_time
                result[tid] = (t, end_time)

        if running:
            t = min(running.values())
        elif len(completed) < len(tasks):
            raise ValueError("deadlock detected")

    jobs = sorted(
        [{"id": tid, "start": s, "end": e} for tid, (s, e) in result.items()],
        key=lambda x: x["id"]
    )
    makespan = max(e for _, e in result.values()) if result else 0

    return {"jobs": jobs, "makespan": makespan}
```