```python
def schedule(tasks, capacity):
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
        raise ValueError("capacity must be a positive integer")

    durations = {}
    resources = {}
    dependencies = {}
    dependents = {}

    for task in tasks:
        task_id = task["id"]
        duration = task["duration"]
        units = task["units"]

        if not isinstance(task_id, str):
            raise ValueError("id must be a string")
        if task_id in durations:
            raise ValueError("duplicate task id")
        if (
            not isinstance(duration, int)
            or isinstance(duration, bool)
            or duration <= 0
        ):
            raise ValueError("duration must be a positive integer")
        if (
            not isinstance(units, int)
            or isinstance(units, bool)
            or units <= 0
        ):
            raise ValueError("units must be a positive integer")
        if units > capacity:
            raise ValueError("units exceed capacity")

        durations[task_id] = duration
        resources[task_id] = units
        dependencies[task_id] = set(task["deps"])
        dependents[task_id] = []

    for task_id, prerequisites in dependencies.items():
        for prerequisite in prerequisites:
            if prerequisite not in durations:
                raise ValueError("unknown dependency")
            dependents[prerequisite].append(task_id)

    dependency_counts = {
        task_id: len(prerequisites)
        for task_id, prerequisites in dependencies.items()
    }

    cycle_counts = dict(dependency_counts)
    ready = [
        task_id
        for task_id in sorted(dependencies)
        if cycle_counts[task_id] == 0
    ]
    visited = 0

    while ready:
        task_id = ready.pop()
        visited += 1
        for dependent_id in dependents[task_id]:
            cycle_counts[dependent_id] -= 1
            if cycle_counts[dependent_id] == 0:
                ready.append(dependent_id)

    if visited != len(dependencies):
        raise ValueError("cyclic dependency")

    ordered_ids = sorted(dependencies)
    remaining_dependencies = dict(dependency_counts)
    unstarted = set(ordered_ids)
    running = []
    jobs = []
    now = 0

    while True:
        still_running = []

        for running_task in running:
            task_id, end_time = running_task
            if end_time == now:
                unstarted.remove(task_id)
                for dependent_id in dependents[task_id]:
                    remaining_dependencies[dependent_id] -= 1
            else:
                still_running.append(running_task)

        running = still_running
        available = capacity

        for task_id in ordered_ids:
            if task_id not in unstarted:
                continue
            if remaining_dependencies[task_id] != 0:
                continue

            units = resources[task_id]
            if units <= available:
                end_time = now + durations[task_id]
                running.append((task_id, end_time))
                jobs.append({
                    "id": task_id,
                    "start": now,
                    "end": end_time,
                })
                unstarted.remove(task_id)
                available -= units

        if not running:
            if unstarted:
                raise ValueError("cyclic dependency")
            break

        now = min(running_task[1] for running_task in running)

    jobs.sort(key=lambda job: job["id"])
    return {"jobs": jobs, "makespan": now}
```