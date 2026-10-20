def schedule(tasks, capacity):
    if len(tasks) == 0:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    id_set = set()
    for task in tasks:
        tid = task["id"]
        id_set.add(tid)
        task_map[tid] = {
            "duration": task["duration"],
            "units": task["units"],
            "deps": list(task["deps"])
        }

    for tid in task_map:
        info = task_map[tid]
        if info["units"] > capacity:
            raise ValueError
        for dep in info["deps"]:
            if dep not in id_set:
                raise ValueError

    dep_count = {tid: len(task_map[tid]["deps"]) for tid in id_set}
    dependents = {tid: [] for tid in id_set}

    for tid in task_map:
        for dep in task_map[tid]["deps"]:
            dependents[dep].append(tid)

    queue = [tid for tid in id_set if dep_count[tid] == 0]
    processed = 0
    qi = 0

    while qi < len(queue):
        tid = queue[qi]
        qi += 1
        processed += 1
        for child in dependents[tid]:
            dep_count[child] -= 1
            if dep_count[child] == 0:
                queue.append(child)

    if processed != len(tasks):
        raise ValueError

    sorted_ids = sorted(id_set)
    remaining = {tid: len(task_map[tid]["deps"]) for tid in id_set}
    running = []
    started = set()
    finished = set()
    jobs = {}
    available = capacity
    current = 0

    while len(finished) < len(tasks):
        still_running = []
        for end, tid, units in running:
            if end <= current:
                available += units
                finished.add(tid)
                for child in dependents[tid]:
                    remaining[child] -= 1
            else:
                still_running.append([end, tid, units])
        running = still_running

        if len(finished) == len(tasks):
            break

        candidates = []
        for tid in sorted_ids:
            if tid not in started and remaining[tid] == 0:
                candidates.append(tid)

        for tid in candidates:
            info = task_map[tid]
            units = info["units"]
            if units <= available:
                start = current
                end = current + info["duration"]
                jobs[tid] = {"id": tid, "start": start, "end": end}
                started.add(tid)
                running.append([end, tid, units])
                available -= units

        if not running:
            if len(finished) < len(tasks):
                raise ValueError
            break

        next_time = running[0][0]
        for item in running[1:]:
            if item[0] < next_time:
                next_time = item[0]
        current = next_time

    job_list = [jobs[tid] for tid in sorted(jobs.keys())]
    makespan = 0
    for job in job_list:
        if job["end"] > makespan:
            makespan = job["end"]

    return {"jobs": job_list, "makespan": makespan}