```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    for t in tasks:
        task_map[t["id"]] = t

    # Validate units > capacity
    for t in tasks:
        if t["units"] > capacity:
            raise ValueError("units exceeds capacity")

    # Validate unknown deps
    for t in tasks:
        for d in t["deps"]:
            if d not in task_map:
                raise ValueError("unknown dependency")

    # Validate circular deps via Kahn's algorithm
    in_degree = {t["id"]: 0 for t in tasks}
    adj = {t["id"]: [] for t in tasks}
    for t in tasks:
        for d in t["deps"]:
            adj[d].append(t["id"])
            in_degree[t["id"]] += 1

    queue = [tid for tid in in_degree if in_degree[tid] == 0]
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

    # Simulation
    all_ids = sorted(task_map.keys())
    completed = set()
    started = set()
    running = []  # (end_time, id, units)
    available = capacity
    current_time = 0
    jobs = []

    while len(completed) < len(tasks):
        # Release all completed tasks at current_time
        new_running = []
        for (end_time, tid, units) in running:
            if end_time <= current_time:
                completed.add(tid)
                available += units
            else:
                new_running.append((end_time, tid, units))
        running = new_running

        # Scan ready tasks in lexicographic id order
        for tid in all_ids:
            if tid in started or tid in completed:
                continue
            deps_met = True
            for d in task_map[tid]["deps"]:
                if d not in completed:
                    deps_met = False
                    break
            if not deps_met:
                continue
            units = task_map[tid]["units"]
            if units <= available:
                available -= units
                duration = task_map[tid]["duration"]
                end_time = current_time + duration
                running.append((end_time, tid, units))
                started.add(tid)
                jobs.append({"id": tid, "start": current_time, "end": end_time})

        # Advance to earliest running task end
        if running:
            current_time = min(et for (et, _, _) in running)
        elif len(completed) < len(tasks):
            break

    makespan = max(j["end"] for j in jobs) if jobs else 0
    jobs.sort(key=lambda x: x["id"])

    return {"jobs": jobs, "makespan": makespan}
```