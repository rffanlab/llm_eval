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

    def _dfs(node):
        color[node] = GRAY
        for d in task_map[node]["deps"]:
            if color[d] == GRAY:
                raise ValueError("circular dependency")
            if color[d] == WHITE:
                _dfs(d)
        color[node] = BLACK

    for t in tasks:
        if color[t["id"]] == WHITE:
            _dfs(t["id"])

    all_ids = sorted(task_map.keys())
    completed = set()
    running = {}
    started = set()
    start_times = {}
    end_times = {}
    t = 0

    while len(completed) < len(tasks):
        newly_done = [tid for tid, end in running.items() if end == t]
        for tid in newly_done:
            del running[tid]
            completed.add(tid)

        available = capacity - sum(task_map[tid]["units"] for tid in running)

        for tid in all_ids:
            if tid in started:
                continue
            if not all(d in completed for d in task_map[tid]["deps"]):
                continue
            if task_map[tid]["units"] <= available:
                started.add(tid)
                end_time = t + task_map[tid]["duration"]
                running[tid] = end_time
                start_times[tid] = t
                end_times[tid] = end_time
                available -= task_map[tid]["units"]

        if running:
            t = min(running.values())
        else:
            break

    jobs = [{"id": tid, "start": start_times[tid], "end": end_times[tid]} for tid in all_ids]
    makespan = max(end_times.values()) if end_times else 0

    return {"jobs": jobs, "makespan": makespan}
```