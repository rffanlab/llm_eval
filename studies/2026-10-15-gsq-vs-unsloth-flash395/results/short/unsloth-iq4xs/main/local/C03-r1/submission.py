```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    for t in tasks:
        task_map[t["id"]] = t

    for t in tasks:
        if t["units"] > capacity:
            raise ValueError("units > capacity")

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
        for nb in adj[node]:
            in_degree[nb] -= 1
            if in_degree[nb] == 0:
                queue.append(nb)

    if topo_count != len(tasks):
        raise ValueError("circular dependency")

    current_time = 0
    running = {}
    completed = set()
    started = set()
    scheduled = {}
    available = capacity
    all_ids = sorted(task_map.keys())

    while len(completed) < len(tasks):
        to_release = [tid for tid, end in running.items() if end <= current_time]
        for tid in to_release:
            del running[tid]
            completed.add(tid)
            available += task_map[tid]["units"]

        for tid in all_ids:
            if tid in started:
                continue
            t = task_map[tid]
            if all(d in completed for d in t["deps"]):
                if t["units"] <= available:
                    started.add(tid)
                    end_time = current_time + t["duration"]
                    running[tid] = end_time
                    scheduled[tid] = (current_time, end_time)
                    available -= t["units"]

        if len(completed) == len(tasks):
            break

        if running:
            current_time = min(running.values())
        else:
            break

    jobs = sorted(
        [{"id": tid, "start": scheduled[tid][0], "end": scheduled[tid][1]} for tid in scheduled],
        key=lambda x: x["id"],
    )
    makespan = max(scheduled[tid][1] for tid in scheduled) if scheduled else 0

    return {"jobs": jobs, "makespan": makespan}
```