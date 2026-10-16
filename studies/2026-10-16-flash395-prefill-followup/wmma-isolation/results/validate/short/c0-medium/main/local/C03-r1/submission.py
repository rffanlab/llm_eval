```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    ids = set()
    for t in tasks:
        task_map[t["id"]] = t
        ids.add(t["id"])

    for t in tasks:
        if t["units"] > capacity:
            raise ValueError("units exceeds capacity")

    for t in tasks:
        for d in t["deps"]:
            if d not in ids:
                raise ValueError("unknown dependency")

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in ids}
    for tid in ids:
        if color[tid] != WHITE:
            continue
        stack = [(tid, 0)]
        while stack:
            node, idx = stack[-1]
            if color[node] == WHITE:
                color[node] = GRAY
            deps = task_map[node]["deps"]
            if idx < len(deps):
                stack[-1] = (node, idx + 1)
                d = deps[idx]
                if color[d] == GRAY:
                    raise ValueError("circular dependency")
                if color[d] == WHITE:
                    stack.append((d, 0))
            else:
                stack.pop()
                color[node] = BLACK

    completed = set()
    started = set()
    running = {}
    used = 0
    time = 0
    result = {}
    all_ids = sorted(ids)

    while len(completed) < len(tasks):
        to_release = [tid for tid in running if running[tid] <= time]
        for tid in to_release:
            used -= task_map[tid]["units"]
            completed.add(tid)
            del running[tid]

        for tid in all_ids:
            if tid in started:
                continue
            if all(d in completed for d in task_map[tid]["deps"]):
                if used + task_map[tid]["units"] <= capacity:
                    started.add(tid)
                    end_time = time + task_map[tid]["duration"]
                    running[tid] = end_time
                    used += task_map[tid]["units"]
                    result[tid] = (time, end_time)

        if running:
            time = min(running.values())
        elif len(completed) < len(tasks):
            raise ValueError("deadlock")

    jobs = [{"id": tid, "start": result[tid][0], "end": result[tid][1]} for tid in sorted(result)]
    makespan = max(v[1] for v in result.values()) if result else 0
    return {"jobs": jobs, "makespan": makespan}
```