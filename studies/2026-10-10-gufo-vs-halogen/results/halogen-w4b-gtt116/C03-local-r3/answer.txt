```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    for t in tasks:
        task_map[t["id"]] = t

    for t in tasks:
        if t["units"] > capacity:
            raise ValueError("units exceeds capacity for task " + t["id"])

    for t in tasks:
        for d in t["deps"]:
            if d not in task_map:
                raise ValueError("unknown dependency " + d)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {t["id"]: WHITE for t in tasks}

    def dfs(node):
        color[node] = GRAY
        for dep in task_map[node]["deps"]:
            if color[dep] == GRAY:
                raise ValueError("circular dependency detected")
            if color[dep] == WHITE:
                dfs(dep)
        color[node] = BLACK

    for t in tasks:
        if color[t["id"]] == WHITE:
            dfs(t["id"])

    all_ids = sorted(task_map.keys())
    current_time = 0
    running = []
    completed = set()
    started = set()
    jobs = []

    while len(completed) < len(tasks):
        new_running = []
        for end_time, units, tid in running:
            if end_time <= current_time:
                completed.add(tid)
            else:
                new_running.append((end_time, units, tid))
        running = new_running

        used = sum(u for _, u, _ in running)

        for tid in all_ids:
            if tid in started:
                continue
            t = task_map[tid]
            if all(d in completed for d in t["deps"]):
                if used + t["units"] <= capacity:
                    started.add(tid)
                    end = current_time + t["duration"]
                    running.append((end, t["units"], tid))
                    used += t["units"]
                    jobs.append({"id": tid, "start": current_time, "end": end})

        if running:
            current_time = min(e for e, _, _ in running)
        elif len(completed) < len(tasks):
            raise ValueError("deadlock: unable to schedule remaining tasks")

    jobs.sort(key=lambda x: x["id"])
    makespan = max((j["end"] for j in jobs), default=0)

    return {"jobs": jobs, "makespan": makespan}
```