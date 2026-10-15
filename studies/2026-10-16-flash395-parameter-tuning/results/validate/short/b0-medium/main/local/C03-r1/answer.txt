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
    color = {tid: WHITE for tid in task_map}
    for start in task_map:
        if color[start] != WHITE:
            continue
        stack = [(start, 0)]
        color[start] = GRAY
        while stack:
            node, idx = stack[-1]
            deps = task_map[node]["deps"]
            found = False
            while idx < len(deps):
                dep = deps[idx]
                idx += 1
                if color[dep] == GRAY:
                    raise ValueError("circular dependency")
                if color[dep] == WHITE:
                    color[dep] = GRAY
                    stack[-1] = (node, idx)
                    stack.append((dep, 0))
                    found = True
                    break
            if not found:
                color[node] = BLACK
                stack.pop()

    completed = set()
    started = set()
    running = []
    sched = {}
    time = 0

    while len(completed) < len(tasks):
        new_running = []
        for (end_t, tid, units) in running:
            if end_t <= time:
                completed.add(tid)
            else:
                new_running.append((end_t, tid, units))
        running = new_running

        available = capacity - sum(u for (_, _, u) in running)

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
                end_time = time + t["duration"]
                running.append((end_time, t["id"], t["units"]))
                sched[t["id"]] = (time, end_time)

        if running:
            time = min(end_t for (end_t, _, _) in running)
        elif len(completed) < len(tasks):
            raise ValueError("deadlock detected")

    jobs = sorted(
        [{"id": tid, "start": s, "end": e} for tid, (s, e) in sched.items()],
        key=lambda x: x["id"]
    )
    makespan = max(e for (_, e) in sched.values()) if sched else 0

    return {"jobs": jobs, "makespan": makespan}
```