def schedule(tasks, capacity):
    if type(capacity) is not int or capacity <= 0:
        raise ValueError("capacity must be a positive integer")

    by_id = {}
    for task in tasks:
        task_id = task["id"]
        duration = task["duration"]
        units = task["units"]
        deps = task["deps"]

        if not isinstance(task_id, str):
            raise ValueError("task id must be a string")
        if task_id in by_id:
            raise ValueError("duplicate task id")
        if type(duration) is not int or duration <= 0:
            raise ValueError("duration must be a positive integer")
        if type(units) is not int or units <= 0:
            raise ValueError("units must be a positive integer")
        if units > capacity:
            raise ValueError("task units exceed capacity")

        by_id[task_id] = (duration, units, tuple(deps))

    task_ids = sorted(by_id)
    indegree = {}
    dependents = {task_id: [] for task_id in task_ids}

    for task_id in task_ids:
        dependencies = set(by_id[task_id][2])
        indegree[task_id] = len(dependencies)
        for dependency in dependencies:
            if dependency not in by_id:
                raise ValueError("unknown dependency")
            dependents[dependency].append(task_id)

    ready = [task_id for task_id in task_ids if indegree[task_id] == 0]
    processed = 0
    while ready:
        task_id = ready.pop()
        processed += 1
        for dependent in dependents[task_id]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)

    if processed != len(task_ids):
        raise ValueError("cyclic dependency")

    now = 0
    available = capacity
    completed = set()
    running = {}
    jobs_by_id = {}

    while True:
        finished = [
            task_id
            for task_id, (_, end) in running.items()
            if end <= now
        ]
        for task_id in finished:
            units, _ = running.pop(task_id)
            available += units
            completed.add(task_id)

        for task_id in task_ids:
            if task_id in jobs_by_id:
                continue

            duration, units, deps = by_id[task_id]
            if all(dependency in completed for dependency in deps):
                if units <= available:
                    end = now + duration
                    available -= units
                    running[task_id] = (units, end)
                    jobs_by_id[task_id] = {
                        "id": task_id,
                        "start": now,
                        "end": end,
                    }

        if len(completed) == len(task_ids):
            break

        if not running:
            raise ValueError("cyclic dependency")

        now = min(end for _, end in running.values())

    return {
        "jobs": [jobs_by_id[task_id] for task_id in task_ids],
        "makespan": now,
    }