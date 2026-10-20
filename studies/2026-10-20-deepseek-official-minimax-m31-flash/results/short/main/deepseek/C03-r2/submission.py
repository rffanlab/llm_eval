def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    by_id = {}
    for task in tasks:
        tid = task["id"]
        if tid in by_id:
            raise ValueError
        by_id[tid] = task

    ids = sorted(by_id.keys())
    n = len(ids)

    indegree = {}
    children = {}
    for tid in ids:
        if by_id[tid]["units"] > capacity:
            raise ValueError
        indegree[tid] = 0
        children[tid] = []

    for tid in ids:
        seen = set()
        for dep in by_id[tid]["deps"]:
            if dep not in by_id:
                raise ValueError
            if dep not in seen:
                seen.add(dep)
                indegree[tid] += 1
                children[dep].append(tid)

    queue = []
    for tid in ids:
        if indegree[tid] == 0:
            queue.append(tid)

    head = 0
    processed = 0
    while head < len(queue):
        tid = queue[head]
        head += 1
        processed += 1
        for child in children[tid]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if processed != n:
        raise ValueError

    completed = set()
    started = set()
    jobs = {}
    running = []
    now = 0
    finished_count = 0

    while finished_count < n:
        still_running = []
        for end, units, tid in running:
            if end <= now:
                completed.add(tid)
                finished_count += 1
            else:
                still_running.append((end, units, tid))
        running = still_running

        if finished_count == n:
            break

        used = 0
        for end, units, tid in running:
            used += units

        for tid in ids:
            if tid in started:
                continue

            ready = True
            for dep in by_id[tid]["deps"]:
                if dep not in completed:
                    ready = False
                    break
            if not ready:
                continue

            units = by_id[tid]["units"]
            if units <= capacity - used:
                start = now
                end = now + by_id[tid]["duration"]
                jobs[tid] = {"id": tid, "start": start, "end": end}
                started.add(tid)
                used += units
                running.append((end, units, tid))

        if not running:
            raise ValueError

        next_time = running[0][0]
        for end, units, tid in running[1:]:
            if end < next_time:
                next_time = end
        now = next_time

    ordered_jobs = []
    for tid in ids:
        ordered_jobs.append(jobs[tid])

    return {"jobs": ordered_jobs, "makespan": now}