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
        stack = [(node, iter(task_map[node]["deps"]))]
        color[node] = GRAY
        while stack:
            cur, it = stack[-1]
            advanced = False
            for dep in it:
                if color[dep] == GRAY:
                    raise ValueError("circular dependency")
                if color[dep] == WHITE:
                    color[dep] = GRAY
                    stack.append((dep, iter(task_map[dep]["deps"])))
                    advanced = True
                    break
            if not advanced:
                color[cur] = BLACK
                stack.pop()

    for t in tasks:
        if color[t["id"]] == WHITE:
            _dfs(t["id"])

    current_time = 0
    running = []
    completed = set()
    started = set()
    scheduled = {}
    used = 0
    total = len(tasks)

    while len(completed) < total:
        new_running = []
        for end_time, tid, units in running:
            if end_time <= current_time:
                completed.add(tid)
                used -= units
            else:
                new_running.append((end_time, tid, units))
        running = new_running

        ready = []
        for t in tasks:
            tid = t["id"]
            if tid in started:
                continue
            if all(d in completed for d in t["deps"]):
                ready.append(t)

        ready.sort(key=lambda x: x["id"])

        for t in ready:
            tid = t["id"]
            if t["units"] <= capacity - used:
                started.add(tid)
                end_time = current_time + t["duration"]
                running.append((end_time, tid, t["units"]))
                used += t["units"]
                scheduled[tid] = (current_time, end_time)

        if running:
            current_time = min(e for e, _, _ in running)
        elif len(completed) < total:
            raise ValueError("deadlock")

    jobs = sorted(
        [{"id": tid, "start": s, "end": e} for tid, (s, e) in scheduled.items()],
        key=lambda x: x["id"],
    )
    makespan = max(e for _, e in scheduled.values()) if scheduled else 0

    return {"jobs": jobs, "makespan": makespan}
```