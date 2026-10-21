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
    for start_node in task_map:
        if color[start_node] != WHITE:
            continue
        stack = [(start_node, False)]
        while stack:
            node, processed = stack.pop()
            if processed:
                color[node] = BLACK
                continue
            if color[node] == GRAY:
                raise ValueError("circular dependency")
            if color[node] == BLACK:
                continue
            color[node] = GRAY
            stack.append((node, True))
            for d in task_map[node]["deps"]:
                if color[d] == GRAY:
                    raise ValueError("circular dependency")
                if color[d] == WHITE:
                    stack.append((d, False))

    all_ids = sorted(task_map.keys())
    completed = set()
    running = {}
    started = set()
    available = capacity
    t = 0
    jobs = []

    while len(completed) < len(tasks):
        newly_completed = [tid for tid, end in list(running.items()) if end <= t]
        for tid in newly_completed:
            completed.add(tid)
            available += task_map[tid]["units"]
            del running[tid]

        for tid in all_ids:
            if tid in started:
                continue
            if all(d in completed for d in task_map[tid]["deps"]):
                if available >= task_map[tid]["units"]:
                    started.add(tid)
                    available -= task_map[tid]["units"]
                    end_time = t + task_map[tid]["duration"]
                    running[tid] = end_time
                    jobs.append({"id": tid, "start": t, "end": end_time})

        if running:
            t = min(running.values())
        elif len(completed) < len(tasks):
            raise ValueError("deadlock")

    makespan = max(j["end"] for j in jobs) if jobs else 0
    jobs.sort(key=lambda x: x["id"])
    return {"jobs": jobs, "makespan": makespan}
```