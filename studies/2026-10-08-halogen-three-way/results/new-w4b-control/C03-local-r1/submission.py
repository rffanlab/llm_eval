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
                raise ValueError("unknown dependency: " + d)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {t["id"]: WHITE for t in tasks}

    def _dfs(node):
        color[node] = GRAY
        for dep in task_map[node]["deps"]:
            if color[dep] == GRAY:
                raise ValueError("circular dependency detected")
            if color[dep] == WHITE:
                _dfs(dep)
        color[node] = BLACK

    for t in tasks:
        if color[t["id"]] == WHITE:
            _dfs(t["id"])

    all_ids = sorted(task_map.keys())
    started = set()
    completed = set()
    running = []
    current_time = 0
    available = capacity
    jobs = []

    while len(completed) < len(tasks):
        new_running = []
        for end_time, tid, units in running:
            if end_time <= current_time:
                completed.add(tid)
                available += units
            else:
                new_running.append((end_time, tid, units))
        running = new_running

        for tid in all_ids:
            if tid in started:
                continue
            deps = task_map[tid]["deps"]
            if all(d in completed for d in deps):
                need = task_map[tid]["units"]
                if available >= need:
                    started.add(tid)
                    end_time = current_time + task_map[tid]["duration"]
                    running.append((end_time, tid, need))
                    available -= need
                    jobs.append({"id": tid, "start": current_time, "end": end_time})

        if running:
            current_time = min(et for et, _, _ in running)
        elif len(completed) < len(tasks):
            raise ValueError("unable to schedule remaining tasks")

    jobs.sort(key=lambda x: x["id"])
    makespan = max(j["end"] for j in jobs) if jobs else 0

    return {"jobs": jobs, "makespan": makespan}
```