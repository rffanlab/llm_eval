```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    for t in tasks:
        if t['units'] > capacity:
            raise ValueError("units exceeds capacity")
        task_map[t['id']] = t

    for t in tasks:
        for d in t['deps']:
            if d not in task_map:
                raise ValueError("unknown dependency")

    in_degree = {t['id']: 0 for t in tasks}
    adj = {t['id']: [] for t in tasks}
    for t in tasks:
        for d in t['deps']:
            adj[d].append(t['id'])
            in_degree[t['id']] += 1

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

    not_started = set(t['id'] for t in tasks)
    running = {}
    completed = set()
    available = capacity
    t = 0
    jobs = []

    while not_started or running:
        to_release = [tid for tid, end in running.items() if end <= t]
        for tid in to_release:
            available += task_map[tid]['units']
            completed.add(tid)
            del running[tid]

        ready = []
        for tid in not_started:
            if all(d in completed for d in task_map[tid]['deps']):
                ready.append(tid)
        ready.sort()

        for tid in ready:
            if task_map[tid]['units'] <= available:
                available -= task_map[tid]['units']
                end_time = t + task_map[tid]['duration']
                running[tid] = end_time
                not_started.discard(tid)
                jobs.append({"id": tid, "start": t, "end": end_time})

        if not_started or running:
            if running:
                t = min(running.values())
            else:
                break

    makespan = max(j['end'] for j in jobs) if jobs else 0
    jobs.sort(key=lambda x: x['id'])

    return {"jobs": jobs, "makespan": makespan}
```