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
    for t in tasks:
        if color[t["id"]] != WHITE:
            continue
        stack = [(t["id"], 0)]
        while stack:
            node, idx = stack[-1]
            if idx == 0:
                color[node] = GRAY
            deps = task_map[node]["deps"]
            advanced = False
            for i in range(idx, len(deps)):
                d = deps[i]
                if color[d] == GRAY:
                    raise ValueError("circular dependency")
                if color[d] == WHITE:
                    stack[-1] = (node, i + 1)
                    stack.append((d, 0))
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
        newly_done = [tid for tid, end in running.items() if end == t]
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
            break

    jobs.sort(key=lambda x: x["id"])
    makespan = max((j["end"] for j in jobs), default=0)
    return {"jobs": jobs, "makespan": makespan}
```