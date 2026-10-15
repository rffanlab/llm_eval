```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    for t in tasks:
        task_map[t["id"]] = t

    all_ids = set(task_map.keys())

    for t in tasks:
        if t["units"] > capacity:
            raise ValueError("units exceeds capacity")

    for t in tasks:
        for d in t["deps"]:
            if d not in all_ids:
                raise ValueError("unknown dependency")

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in all_ids}

    def _dfs(tid):
        color[tid] = GRAY
        for d in task_map[tid]["deps"]:
            if color[d] == GRAY:
                raise ValueError("circular dependency")
            if color[d] == WHITE:
                _dfs(d)
        color[tid] = BLACK

    for tid in all_ids:
        if color[tid] == WHITE:
            _dfs(tid)

    sorted_ids = sorted(all_ids)
    current_time = 0
    running = []
    completed = set()
    started = set()
    available = capacity
    result = {}

    while len(completed) < len(tasks):
        new_running = []
        for end_time, tid, units in running:
            if end_time <= current_time:
                completed.add(tid)
                available += units
            else:
                new_running.append((end_time, tid, units))
        running = new_running

        for tid in sorted_ids:
            if tid in started:
                continue
            t = task_map[tid]
            if all(d in completed for d in t["deps"]):
                if t["units"] <= available:
                    started.add(tid)
                    end_time = current_time + t["duration"]
                    running.append((end_time, tid, t["units"]))
                    available -= t["units"]
                    result[tid] = (current_time, end_time)

        if running:
            current_time = min(e for e, _, _ in running)
        else:
            break

    jobs = []
    for tid in sorted(result.keys()):
        jobs.append({"id": tid, "start": result[tid][0], "end": result[tid][1]})

    makespan = max((e for _, e in result.values()), default=0)

    return {"jobs": jobs, "makespan": makespan}
```