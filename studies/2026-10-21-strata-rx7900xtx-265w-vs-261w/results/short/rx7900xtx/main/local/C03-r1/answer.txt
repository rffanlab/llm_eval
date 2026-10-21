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
    completed = set()
    started = set()
    running = []
    available = capacity
    current_time = 0
    result = {}

    while len(completed) < len(tasks):
        new_running = []
        for (end_time, tid, units) in running:
            if end_time <= current_time:
                completed.add(tid)
                available += units
            else:
                new_running.append((end_time, tid, units))
        running = new_running

        for tid in all_ids:
            if tid in started:
                continue
            t = task_map[tid]
            if all(d in completed for d in t["deps"]):
                if t["units"] <= available:
                    started.add(tid)
                    available -= t["units"]
                    end_time = current_time + t["duration"]
                    running.append((end_time, tid, t["units"]))
                    result[tid] = (current_time, end_time)

        if running:
            current_time = min(e for e, _, _ in running)
        elif len(completed) < len(tasks):
            raise ValueError("deadlock")

    jobs = [{"id": tid, "start": result[tid][0], "end": result[tid][1]} for tid in sorted(result.keys())]
    makespan = max(end for _, end in result.values()) if result else 0

    return {"jobs": jobs, "makespan": makespan}
```