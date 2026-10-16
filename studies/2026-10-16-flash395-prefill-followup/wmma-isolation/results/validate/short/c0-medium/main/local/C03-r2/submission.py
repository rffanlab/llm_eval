```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {t["id"]: t for t in tasks}
    all_ids = set(task_map.keys())

    for t in tasks:
        if t["units"] > capacity:
            raise ValueError("units exceeds capacity")

    for t in tasks:
        for d in t["deps"]:
            if d not in all_ids:
                raise ValueError("unknown dependency")

    in_degree = {tid: 0 for tid in all_ids}
    adj = {tid: [] for tid in all_ids}
    for t in tasks:
        for d in t["deps"]:
            adj[d].append(t["id"])
            in_degree[t["id"]] += 1

    queue = [tid for tid in all_ids if in_degree[tid] == 0]
    topo_count = 0
    while queue:
        node = queue.pop()
        topo_count += 1
        for nb in adj[node]:
            in_degree[nb] -= 1
            if in_degree[nb] == 0:
                queue.append(nb)

    if topo_count != len(all_ids):
        raise ValueError("circular dependency")

    time = 0
    running = {}
    completed = set()
    started = set()
    scheduled = {}
    available = capacity

    while len(completed) < len(all_ids):
        to_release = [tid for tid, end in running.items() if end <= time]
        for tid in to_release:
            available += task_map[tid]["units"]
            completed.add(tid)
            del running[tid]

        candidates = sorted(
            tid for tid in all_ids
            if tid not in started and all(d in completed for d in task_map[tid]["deps"])
        )

        for tid in candidates:
            if available >= task_map[tid]["units"]:
                available -= task_map[tid]["units"]
                started.add(tid)
                end_time = time + task_map[tid]["duration"]
                running[tid] = end_time
                scheduled[tid] = (time, end_time)

        if running:
            time = min(running.values())
        else:
            break

    jobs = sorted(
        [{"id": tid, "start": scheduled[tid][0], "end": scheduled[tid][1]} for tid in all_ids],
        key=lambda x: x["id"],
    )
    makespan = max(scheduled[tid][1] for tid in all_ids)

    return {"jobs": jobs, "makespan": makespan}
```