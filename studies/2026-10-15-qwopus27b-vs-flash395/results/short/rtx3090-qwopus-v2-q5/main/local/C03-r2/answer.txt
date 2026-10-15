```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_info = {}
    for t in tasks:
        tid = t["id"]
        task_info[tid] = {
            "duration": t["duration"],
            "units": t["units"],
            "deps": list(t["deps"])
        }

    for tid, info in task_info.items():
        if info["units"] > capacity:
            raise ValueError("units exceeds capacity")

    for tid, info in task_info.items():
        for dep in info["deps"]:
            if dep not in task_info:
                raise ValueError("unknown dependency")

    in_degree = {tid: len(info["deps"]) for tid, info in task_info.items()}
    dependents = {tid: [] for tid in task_info}
    for tid, info in task_info.items():
        for dep in info["deps"]:
            dependents[dep].append(tid)

    queue = sorted([tid for tid in task_info if in_degree[tid] == 0])
    topo_count = 0
    while queue:
        tid = queue.pop(0)
        topo_count += 1
        for dep_tid in dependents[tid]:
            in_degree[dep_tid] -= 1
            if in_degree[dep_tid] == 0:
                queue.append(dep_tid)
        queue.sort()

    if topo_count != len(task_info):
        raise ValueError("circular dependency")

    current_time = 0
    completed = set()
    started = set()
    running = []
    jobs = []

    while len(started) < len(task_info):
        still_running = []
        for end_time, tid in running:
            if end_time <= current_time:
                completed.add(tid)
            else:
                still_running.append((end_time, tid))
        running = still_running

        used = sum(task_info[tid]["units"] for _, tid in running)
        available = capacity - used

        candidates = sorted(
            tid for tid in task_info
            if tid not in started and all(dep in completed for dep in task_info[tid]["deps"])
        )

        for tid in candidates:
            if task_info[tid]["units"] <= available:
                started.add(tid)
                start = current_time
                end = current_time + task_info[tid]["duration"]
                jobs.append({"id": tid, "start": start, "end": end})
                running.append((end, tid))
                available -= task_info[tid]["units"]

        if not running:
            break

        current_time = min(end for end, _ in running)

    makespan = max(end for _, end in jobs) if jobs else 0
    jobs.sort(key=lambda x: x["id"])

    return {"jobs": jobs, "makespan": makespan}
```