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

    state = {tid: 0 for tid in task_map}

    def _dfs(tid):
        if state[tid] == 1:
            raise ValueError("circular dependency")
        if state[tid] == 2:
            return
        state[tid] = 1
        for d in task_map[tid]["deps"]:
            _dfs(d)
        state[tid] = 2

    for tid in task_map:
        _dfs(tid)

    all_ids = sorted(task_map.keys())
    completed = set()
    started = set()
    running = []
    available = capacity
    current_time = 0
    result = {}

    while len(completed) < len(task_map):
        new_running = []
        for entry in running:
            end, tid, units = entry
            if end <= current_time:
                completed.add(tid)
                available += units
            else:
                new_running.append(entry)
        running = new_running

        for tid in all_ids:
            if tid in started:
                continue
            if all(d in completed for d in task_map[tid]["deps"]):
                units = task_map[tid]["units"]
                if units <= available:
                    available -= units
                    end_time = current_time + task_map[tid]["duration"]
                    running.append((end_time, tid, units))
                    started.add(tid)
                    result[tid] = (current_time, end_time)

        if running:
            current_time = min(e for e, _, _ in running)
        elif len(completed) < len(task_map):
            raise ValueError("deadlock")

    jobs = [{"id": tid, "start": result[tid][0], "end": result[tid][1]} for tid in all_ids]
    makespan = max(r[1] for r in result.values()) if result else 0

    return {"jobs": jobs, "makespan": makespan}
```