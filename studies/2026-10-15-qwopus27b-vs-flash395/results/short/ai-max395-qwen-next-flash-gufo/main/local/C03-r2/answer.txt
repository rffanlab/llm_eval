```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    ids = set()
    task_map = {}
    for t in tasks:
        tid = t["id"]
        ids.add(tid)
        task_map[tid] = t
        if t["units"] > capacity:
            raise ValueError("units > capacity")

    for t in tasks:
        for d in t["deps"]:
            if d not in ids:
                raise ValueError("unknown dependency")

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in ids}
    for start_node in ids:
        if color[start_node] != WHITE:
            continue
        color[start_node] = GRAY
        stack = [(start_node, 0)]
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

    current_time = 0
    completed = set()
    started = set()
    running = []
    remaining = capacity
    job_times = {}

    while len(completed) < len(tasks):
        new_running = []
        for (end_time, units, tid) in running:
            if end_time <= current_time:
                completed.add(tid)
                remaining += units
            else:
                new_running.append((end_time, units, tid))
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
            if t["units"] <= remaining:
                tid = t["id"]
                started.add(tid)
                remaining -= t["units"]
                end_time = current_time + t["duration"]
                running.append((end_time, t["units"], tid))
                job_times[tid] = (current_time, end_time)

        if running:
            current_time = min(e for (e, u, tid) in running)
        elif len(completed) < len(tasks):
            raise ValueError("deadlock")

    jobs = []
    for tid in sorted(job_times.keys()):
        s, e = job_times[tid]
        jobs.append({"id": tid, "start": s, "end": e})

    makespan = max(e for (s, e) in job_times.values()) if job_times else 0

    return {"jobs": jobs, "makespan": makespan}
```