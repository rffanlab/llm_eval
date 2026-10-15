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

    in_degree = {t["id"]: 0 for t in tasks}
    adj = {t["id"]: [] for t in tasks}
    for t in tasks:
        for d in t["deps"]:
            adj[d].append(t["id"])
            in_degree[t["id"]] += 1

    queue = [tid for tid in in_degree if in_degree[tid] == 0]
    topo_count = 0
    while queue:
        node = queue.pop(0)
        topo_count += 1
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if topo_count != len(tasks):
        raise ValueError("circular dependency")

    all_ids = sorted(task_map.keys())
    completed = set()
    running = {}
    started = set()
    used = 0
    t = 0
    result = {}

    while len(completed) < len(tasks):
        to_release = [rid for rid, end in running.items() if end <= t]
        for rid in to_release:
            used -= task_map[rid]["units"]
            completed.add(rid)
            del running[rid]

        for tid in all_ids:
            if tid in started:
                continue
            task = task_map[tid]
            if all(d in completed for d in task["deps"]):
                if used + task["units"] <= capacity:
                    started.add(tid)
                    end_time = t + task["duration"]
                    running[tid] = end_time
                    result[tid] = (t, end_time)
                    used += task["units"]

        if running:
            t = min(running.values())
        elif len(completed) < len(tasks):
            raise ValueError("circular dependency")

    jobs = [{"id": tid, "start": result[tid][0], "end": result[tid][1]} for tid in sorted(result.keys())]
    makespan = max(v[1] for v in result.values()) if result else 0

    return {"jobs": jobs, "makespan": makespan}
```