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
        for d in t["deps"]:
            if d not in task_map:
                raise ValueError("unknown dependency")

    in_degree = {t["id"]: 0 for t in tasks}
    adj = {t["id"]: [] for t in tasks}
    for t in tasks:
        for d in t["deps"]:
            adj[d].append(t["id"])
            in_degree[t["id"]] += 1

    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    count = 0
    while queue:
        node = queue.pop(0)
        count += 1
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if count != len(tasks):
        raise ValueError("circular dependency")

    completed = set()
    started = set()
    running = {}
    used = 0
    current_time = 0
    jobs = []
    all_ids = sorted(task_map.keys())

    while len(completed) < len(tasks):
        newly_completed = [tid for tid, end in running.items() if end <= current_time]
        for tid in newly_completed:
            completed.add(tid)
            used -= task_map[tid]["units"]
            del running[tid]

        for tid in all_ids:
            if tid in started:
                continue
            t = task_map[tid]
            if all(d in completed for d in t["deps"]):
                if used + t["units"] <= capacity:
                    started.add(tid)
                    end_time = current_time + t["duration"]
                    running[tid] = end_time
                    used += t["units"]
                    jobs.append({"id": tid, "start": current_time, "end": end_time})

        if running:
            current_time = min(running.values())
        else:
            break

    jobs.sort(key=lambda x: x["id"])
    makespan = max(j["end"] for j in jobs) if jobs else 0
    return {"jobs": jobs, "makespan": makespan}
```