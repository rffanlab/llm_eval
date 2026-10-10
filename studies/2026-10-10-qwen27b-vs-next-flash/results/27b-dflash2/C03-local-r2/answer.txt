```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_info = {}
    for t in tasks:
        task_info[t["id"]] = {
            "duration": t["duration"],
            "units": t["units"],
            "deps": list(t["deps"]),
        }

    for tid, info in task_info.items():
        if info["units"] > capacity:
            raise ValueError("units exceeds capacity")

    for tid, info in task_info.items():
        for dep in info["deps"]:
            if dep not in task_info:
                raise ValueError("unknown dependency")

    in_deg = {tid: 0 for tid in task_info}
    dependents = {tid: [] for tid in task_info}
    for tid, info in task_info.items():
        for dep in info["deps"]:
            in_deg[tid] += 1
            dependents[dep].append(tid)
    queue = [tid for tid in task_info if in_deg[tid] == 0]
    cnt = 0
    while queue:
        node = queue.pop(0)
        cnt += 1
        for d in dependents[node]:
            in_deg[d] -= 1
            if in_deg[d] == 0:
                queue.append(d)
    if cnt != len(task_info):
        raise ValueError("circular dependency")

    completed = set()
    running = {}
    started = set()
    current_time = 0
    used = 0
    jobs = {}

    while len(completed) < len(task_info):
        for tid in list(running):
            if running[tid] <= current_time:
                used -= task_info[tid]["units"]
                del running[tid]
                completed.add(tid)

        eligible = sorted(
            tid for tid in task_info
            if tid not in started and all(d in completed for d in task_info[tid]["deps"])
        )

        for tid in eligible:
            if used + task_info[tid]["units"] <= capacity:
                end = current_time + task_info[tid]["duration"]
                running[tid] = end
                started.add(tid)
                used += task_info[tid]["units"]
                jobs[tid] = {"id": tid, "start": current_time, "end": end}

        if not running:
            break

        current_time = min(running.values())

    sorted_jobs = [jobs[tid] for tid in sorted(jobs)]
    makespan = max((j["end"] for j in sorted_jobs), default=0)
    return {"jobs": sorted_jobs, "makespan": makespan}
```