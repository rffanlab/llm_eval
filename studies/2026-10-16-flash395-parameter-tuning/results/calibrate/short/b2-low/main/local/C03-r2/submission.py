```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    for t in tasks:
        task_map[t['id']] = t

    for t in tasks:
        if t['units'] > capacity:
            raise ValueError("units exceeds capacity")

    for t in tasks:
        for d in t['deps']:
            if d not in task_map:
                raise ValueError("unknown dependency")

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {t['id']: WHITE for t in tasks}

    def dfs(node):
        color[node] = GRAY
        for dep in task_map[node]['deps']:
            if color[dep] == GRAY:
                raise ValueError("circular dependency")
            if color[dep] == WHITE:
                dfs(dep)
        color[node] = BLACK

    for t in tasks:
        if color[t['id']] == WHITE:
            dfs(t['id'])

    current_time = 0
    completed = set()
    started = set()
    running = []
    result = {}
    remaining_units = capacity
    all_ids = sorted(task_map.keys())

    while len(completed) < len(tasks):
        new_running = []
        for (end_time, tid, units) in running:
            if end_time <= current_time:
                completed.add(tid)
                remaining_units += units
            else:
                new_running.append((end_time, tid, units))
        running = new_running

        ready = []
        for tid in all_ids:
            if tid not in started and tid not in completed:
                if all(d in completed for d in task_map[tid]['deps']):
                    ready.append(tid)

        for tid in ready:
            units_needed = task_map[tid]['units']
            if units_needed <= remaining_units:
                remaining_units -= units_needed
                duration = task_map[tid]['duration']
                end_time = current_time + duration
                running.append((end_time, tid, units_needed))
                started.add(tid)
                result[tid] = (current_time, end_time)

        if running:
            current_time = min(e for e, _, _ in running)
        elif len(completed) < len(tasks):
            raise ValueError("deadlock")

    jobs = []
    for tid in sorted(result.keys()):
        start, end = result[tid]
        jobs.append({"id": tid, "start": start, "end": end})

    makespan = max(end for _, end in result.values()) if result else 0

    return {"jobs": jobs, "makespan": makespan}
```