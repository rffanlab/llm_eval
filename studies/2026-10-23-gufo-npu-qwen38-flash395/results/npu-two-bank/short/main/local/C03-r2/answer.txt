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
        for dep in t["deps"]:
            if dep not in task_map:
                raise ValueError("unknown dependency")

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in task_map}
    for start in task_map:
        if color[start] != WHITE:
            continue
        stack = [(start, iter(task_map[start]["deps"]))]
        color[start] = GRAY
        while stack:
            node, it = stack[-1]
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
                color[node] = BLACK
                stack.pop()

    all_ids = sorted(task_map.keys())
    completed = set()
    running = {}
    started = set()
    start_times = {}
    t = 0

    while len(completed) < len(tasks):
        newly_completed = [rid for rid, end in running.items() if end <= t]
        for rid in newly_completed:
            completed.add(rid)
            del running[rid]

        for tid in all_ids:
            if tid in started:
                continue
            task = task_map[tid]
            if all(dep in completed for dep in task["deps"]):
                used = sum(task_map[rid]["units"] for rid in running)
                if used + task["units"] <= capacity:
                    started.add(tid)
                    start_times[tid] = t
                    running[tid] = t + task["duration"]

        if running:
            t = min(running.values())
        else:
            break

    jobs = [
        {"id": tid, "start": start_times[tid], "end": start_times[tid] + task_map[tid]["duration"]}
        for tid in all_ids
    ]
    makespan = max(j["end"] for j in jobs) if jobs else 0

    return {"jobs": jobs, "makespan": makespan}
```