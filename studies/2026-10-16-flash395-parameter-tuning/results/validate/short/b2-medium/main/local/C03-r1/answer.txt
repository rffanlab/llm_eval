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
        for d in task_map[node]["deps"]:
            if color[d] == GRAY:
                raise ValueError("circular dependency")
            if color[d] == WHITE:
                dfs(d)
        color[node] = BLACK

    for t in tasks:
        if color[t["id"]] == WHITE:
            dfs(t["id"])

    completed = set()
    started = set()
    running = []
    jobs = {}
    t = 0

    while len(completed) < len(tasks):
        new_running = []
        for end_time, tid, units in running:
            if end_time <= t:
                completed.add(tid)
            else:
                new_running.append((end_time, tid, units))
        running = new_running

        ready = []
        for task in tasks:
            tid = task["id"]
            if tid in started:
                continue
            if all(d in completed for d in task["deps"]):
                ready.append(task)

        ready.sort(key=lambda x: x["id"])

        current_used = sum(units for _, _, units in running)
        for task in ready:
            if current_used + task["units"] <= capacity:
                started.add(task["id"])
                end_time = t + task["duration"]
                running.append((end_time, task["id"], task["units"]))
                jobs[task["id"]] = {"id": task["id"], "start": t, "end": end_time}
                current_used += task["units"]

        if not running:
            break

        t = min(end_time for end_time, _, _ in running)

    result_jobs = sorted(jobs.values(), key=lambda x: x["id"])
    makespan = max(j["end"] for j in jobs.values()) if jobs else 0

    return {"jobs": result_jobs, "makespan": makespan}
```