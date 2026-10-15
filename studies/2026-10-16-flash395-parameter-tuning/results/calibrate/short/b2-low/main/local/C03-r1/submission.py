```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    for t in tasks:
        task_map[t["id"]] = t

    for t in tasks:
        if t["units"] > capacity:
            raise ValueError("units exceed capacity")

    for t in tasks:
        for d in t["deps"]:
            if d not in task_map:
                raise ValueError("unknown dependency")

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {t["id"]: WHITE for t in tasks}

    def dfs(node):
        color[node] = GRAY
        for d in task_map[node]["deps"]:
            if color[d] == GRAY:
                raise ValueError("circular dependency")
            if color[d] == WHITE:
                dfs(d)
        color[node] = BLACK

    for t in tasks:
        if color[t["id"]] == WHITE:
            dfs(t["id"])

    all_ids = sorted(task_map.keys())
    started = {}
    completed = set()
    running = {}
    used = 0
    time = 0

    while len(completed) < len(tasks):
        newly_completed = [tid for tid, end in running.items() if end <= time]
        for tid in newly_completed:
            completed.add(tid)
            used -= task_map[tid]["units"]
            del running[tid]

        for tid in all_ids:
            if tid in started:
                continue
            t = task_map[tid]
            if all(d in completed for d in t["deps"]):
                if used + t["units"] <= capacity:
                    started[tid] = time
                    running[tid] = time + t["duration"]
                    used += t["units"]

        if not running:
            break

        time = min(running.values())

    jobs = sorted(
        [{"id": tid, "start": started[tid], "end": started[tid] + task_map[tid]["duration"]} for tid in started],
        key=lambda x: x["id"]
    )
    makespan = max(job["end"] for job in jobs) if jobs else 0

    return {"jobs": jobs, "makespan": makespan}
```