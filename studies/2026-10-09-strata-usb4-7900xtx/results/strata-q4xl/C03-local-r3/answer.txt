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

    def dfs(tid):
        if state[tid] == 1:
            raise ValueError("circular dependency")
        if state[tid] == 2:
            return
        state[tid] = 1
        for d in task_map[tid]["deps"]:
            dfs(d)
        state[tid] = 2

    for t in tasks:
        dfs(t["id"])

    completed = set()
    started = set()
    running = {}
    used = 0
    t = 0
    result = {}

    while len(completed) < len(tasks):
        newly_done = [tid for tid, end in running.items() if end <= t]
        for tid in newly_done:
            completed.add(tid)
            used -= task_map[tid]["units"]
            del running[tid]

        ready = []
        for tid in task_map:
            if tid in started:
                continue
            if all(d in completed for d in task_map[tid]["deps"]):
                ready.append(tid)

        ready.sort()

        for tid in ready:
            if used + task_map[tid]["units"] <= capacity:
                started.add(tid)
                end_t = t + task_map[tid]["duration"]
                running[tid] = end_t
                used += task_map[tid]["units"]
                result[tid] = (t, end_t)

        if len(completed) == len(tasks):
            break

        if running:
            t = min(running.values())
        else:
            raise ValueError("deadlock")

    jobs = [{"id": tid, "start": result[tid][0], "end": result[tid][1]} for tid in sorted(result)]
    makespan = max(end for _, end in result.values()) if result else 0

    return {"jobs": jobs, "makespan": makespan}
```