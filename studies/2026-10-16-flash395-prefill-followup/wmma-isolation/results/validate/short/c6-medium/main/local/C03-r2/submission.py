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
            if idx < len(deps):
                stack[-1] = (node, idx + 1)
                dep = deps[idx]
                if color[dep] == GRAY:
                    raise ValueError("circular dependency")
                if color[dep] == WHITE:
                    color[dep] = GRAY
                    stack.append((dep, 0))
            else:
                color[node] = BLACK
                stack.pop()

    pending = set(task_map.keys())
    running = {}
    completed = set()
    used_units = 0
    t = 0
    result = {}

    while pending or running:
        to_release = [tid for tid, end in running.items() if end <= t]
        for tid in to_release:
            used_units -= task_map[tid]["units"]
            completed.add(tid)
            del running[tid]

        for tid in sorted(pending):
            task = task_map[tid]
            if all(d in completed for d in task["deps"]):
                if used_units + task["units"] <= capacity:
                    result[tid] = (t, t + task["duration"])
                    running[tid] = t + task["duration"]
                    used_units += task["units"]
                    pending.discard(tid)

        if running:
            t = min(running.values())
        elif pending:
            break

    jobs = sorted(
        [{"id": tid, "start": s, "end": e} for tid, (s, e) in result.items()],
        key=lambda x: x["id"]
    )
    makespan = max(e for _, (_, e) in result.items()) if result else 0

    return {"jobs": jobs, "makespan": makespan}
```