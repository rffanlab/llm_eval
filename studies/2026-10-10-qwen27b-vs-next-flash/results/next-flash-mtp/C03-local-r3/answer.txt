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

    state = {t["id"]: 0 for t in tasks}

    def _dfs(tid):
        if state[tid] == 1:
            raise ValueError("circular dependency")
        if state[tid] == 2:
            return
        state[tid] = 1
        for d in task_map[tid]["deps"]:
            _dfs(d)
        state[tid] = 2

    for t in tasks:
        _dfs(t["id"])

    completed = set()
    started = set()
    running = []
    jobs = {}
    t = 0
    available = capacity

    while len(completed) < len(tasks):
        new_running = []
        for (end_time, tid, units) in running:
            if end_time <= t:
                completed.add(tid)
                available += units
            else:
                new_running.append((end_time, tid, units))
        running = new_running

        ready = []
        for tid in task_map:
            if tid in started or tid in completed:
                continue
            if all(d in completed for d in task_map[tid]["deps"]):
                ready.append(tid)

        ready.sort()

        for tid in ready:
            units = task_map[tid]["units"]
            if units <= available:
                available -= units
                started.add(tid)
                end_time = t + task_map[tid]["duration"]
                running.append((end_time, tid, units))
                jobs[tid] = {"id": tid, "start": t, "end": end_time}

        if running:
            t = min(e for (e, _, _) in running)
        elif len(completed) < len(tasks):
            raise ValueError("deadlock")

    result_jobs = sorted(jobs.values(), key=lambda x: x["id"])
    makespan = max(j["end"] for j in jobs.values()) if jobs else 0
    return {"jobs": result_jobs, "makespan": makespan}
```