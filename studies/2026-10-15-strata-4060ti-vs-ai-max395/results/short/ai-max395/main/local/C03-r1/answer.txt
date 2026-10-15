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
        for d in t["deps"]:
            if d not in all_ids:
                raise ValueError("unknown dependency")

    in_degree = {tid: 0 for tid in all_ids}
    dependents = {tid: [] for tid in all_ids}
    for t in tasks:
        for d in t["deps"]:
            in_degree[t["id"]] += 1
            dependents[d].append(t["id"])

    queue = [tid for tid in all_ids if in_degree[tid] == 0]
    topo_count = 0
    while queue:
        node = queue.pop()
        topo_count += 1
        for dep in dependents[node]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    if topo_count != len(all_ids):
        raise ValueError("circular dependency")

    completed = set()
    started = set()
    running = {}
    available = capacity
    t = 0
    result = {}

    while len(completed) < len(all_ids):
        newly_done = [rid for rid, end in running.items() if end <= t]
        for rid in newly_done:
            completed.add(rid)
            available += task_map[rid]["units"]
            del running[rid]

        eligible = sorted(
            [tid for tid in all_ids
             if tid not in started
             and all(d in completed for d in task_map[tid]["deps"])],
            key=lambda x: x
        )

        for tid in eligible:
            if task_map[tid]["units"] <= available:
                started.add(tid)
                available -= task_map[tid]["units"]
                end_time = t + task_map[tid]["duration"]
                running[tid] = end_time
                result[tid] = (t, end_time)

        if running:
            t = min(running.values())
        else:
            break

    jobs = sorted(
        [{"id": tid, "start": s, "end": e} for tid, (s, e) in result.items()],
        key=lambda x: x["id"]
    )
    makespan = max(e for _, e in result.values()) if result else 0

    return {"jobs": jobs, "makespan": makespan}
```