def schedule(tasks, capacity):
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
        raise ValueError("capacity must be a positive integer")

    task_map = {}
    for task in tasks:
        task_id = task["id"]
        if task_id in task_map:
            raise ValueError("duplicate task id")
        duration = task["duration"]
        units = task["units"]
        if not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
            raise ValueError("duration must be a positive integer")
        if not isinstance(units, int) or isinstance(units, bool) or units <= 0:
            raise ValueError("units must be a positive integer")
        if units > capacity:
            raise ValueError("units exceed capacity")
        task_map[task_id] = {
            "id": task_id,
            "duration": duration,
            "units": units,
            "deps": list(task["deps"]),
        }

    for task_id, task in task_map.items():
        for dep in task["deps"]:
            if dep not in task_map:
                raise ValueError("unknown dependency")

    unresolved = {
        task_id: len(task["deps"])
        for task_id, task in task_map.items()
    }
    dependents = {task_id: [] for task_id in task_map}
    for task_id, task in task_map.items():
        for dep in task["deps"]:
            dependents[dep].append(task_id)

    ready = [task_id for task_id, count in unresolved.items() if count == 0]
    visited = 0
    while ready:
        task_id = ready.pop()
        visited += 1
        for dependent in dependents[task_id]:
            unresolved[dependent] -= 1
            if unresolved[dependent] == 0:
                ready.append(dependent)

    if visited != len(task_map):
        raise ValueError("cyclic dependency")

    sorted_ids = sorted(task_map)
    completed = set()
    started = set()
    running = []
    used = 0
    now = 0
    jobs = []

    while len(started) < len(task_map):
        if running:
            next_time = min(item[1] for item in running)
            now = next_time
            still_running = []
            for task_id, end_time, units in running:
                if end_time == now:
                    completed.add(task_id)
                    used -= units
                else:
                    still_running.append((task_id, end_time, units))
            running = still_running

        for task_id in sorted_ids:
            if task_id in started:
                continue
            task = task_map[task_id]
            if all(dep in completed for dep in task["deps"]):
                if used + task["units"] <= capacity:
                    started.add(task_id)
                    end_time = now + task["duration"]
                    running.append((task_id, end_time, task["units"]))
                    used += task["units"]
                    jobs.append({
                        "id": task_id,
                        "start": now,
                        "end": end_time,
                    })

        if len(started) == len(task_map):
            break

        if not running:
            raise ValueError("cyclic dependency")

    jobs.sort(key=lambda job: job["id"])
    makespan = max((job["end"] for job in jobs), default=0)
    return {"jobs": jobs, "makespan": makespan}