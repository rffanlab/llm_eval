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
    for start_node in task_map:
        if color[start_node] != WHITE:
            continue
        stack = [(start_node, 0)]
        while stack:
            node, idx = stack[-1]
            if idx == 0:
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
                color[node] = BLACK
                stack.pop()

    all_ids = sorted(task_map.keys())
    started = set()
    completed = set()
    running = []
    available = capacity
    current_time = 0
    result = {}

    while len(completed) < len(tasks):
        new_running = []
        for (end_time, units, tid) in running:
            if end_time <= current_time:
                completed.add(tid)
                available += units
            else:
                new_running.append((end_time, units, tid))
        running = new_running

        for tid in all_ids:
            if tid in started:
                continue
            if all(d in completed for d in task_map[tid]["deps"]):
                units = task_map[tid]["units"]
                if units <= available:
                    started.add(tid)
                    available -= units
                    end_time = current_time + task_map[tid]["duration"]
                    running.append((end_time, units, tid))
                    result[tid] = (current_time, end_time)

        if running:
            current_time = min(e for (e, _, _) in running)
        elif len(completed) < len(tasks):
            raise ValueError("deadlock")

    jobs = []
    for tid in sorted(result.keys()):
        s, e = result[tid]
        jobs.append({"id": tid, "start": s, "end": e})

    makespan = max(e for (_, e) in result.values()) if result else 0
    return {"jobs": jobs, "makespan": makespan}
```