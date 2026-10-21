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
    available = capacity
    t = 0
    jobs = []

    while len(completed) < len(tasks):
        newly_done = [tid for tid, end in running.items() if end <= t]
        for tid in newly_done:
            completed.add(tid)
            available += task_map[tid]["units"]
            del running[tid]

        for tid in all_ids:
            if tid in started:
                continue
            if not all(d in completed for d in task_map[tid]["deps"]):
                continue
            if task_map[tid]["units"] <= available:
                started.add(tid)
                available -= task_map[tid]["units"]
                end_time = t + task_map[tid]["duration"]
                running[tid] = end_time
                jobs.append({"id": tid, "start": t, "end": end_time})

        if running:
            t = min(running.values())
        else:
            if len(completed) < len(tasks):
                raise ValueError("unable to schedule remaining tasks")
            break

    jobs.sort(key=lambda x: x["id"])
    makespan = max((j["end"] for j in jobs), default=0)
    return {"jobs": jobs, "makespan": makespan}
```