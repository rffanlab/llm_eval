```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    for t in tasks:
        if t["units"] > capacity:
            raise ValueError("units exceeds capacity")
        task_map[t["id"]] = t

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

    all_ids = sorted(task_map.keys())
    completed = set()
    started = set()
    running = {}
    results = {}
    available = capacity
    t = 0

    while len(completed) < len(tasks):
        newly_completed = [tid for tid, end in running.items() if end <= t]
        for tid in newly_completed:
            completed.add(tid)
            available += task_map[tid]["units"]
            del running[tid]

        for tid in all_ids:
            if tid in started:
                continue
            if all(d in completed for d in task_map[tid]["deps"]):
                if task_map[tid]["units"] <= available:
                    started.add(tid)
                    end_time = t + task_map[tid]["duration"]
                    running[tid] = end_time
                    results[tid] = (t, end_time)
                    available -= task_map[tid]["units"]

        if running:
            t = min(running.values())
        else:
            break

    jobs = [{"id": tid, "start": results[tid][0], "end": results[tid][1]} for tid in all_ids]
    makespan = max(r[1] for r in results.values()) if results else 0

    return {"jobs": jobs, "makespan": makespan}
```