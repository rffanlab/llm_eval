def schedule(tasks, capacity):
    if not isinstance(capacity, int) or capacity <= 0:
        raise ValueError("capacity must be a positive integer")

    if not isinstance(tasks, list):
        raise ValueError("tasks must be a list")

    # Validate tasks
    for t in tasks:
        if not isinstance(t, dict):
            raise ValueError("each task must be a dict")
        if "id" not in t or not isinstance(t["id"], str):
            raise ValueError("each task must have a string id")
        if "duration" not in t or not isinstance(t["duration"], int) or t["duration"] <= 0:
            raise ValueError("each task must have a positive integer duration")
        if "units" not in t or not isinstance(t["units"], int) or t["units"] <= 0:
            raise ValueError("each task must have a positive integer units")
        if "deps" not in t or not isinstance(t["deps"], list):
            raise ValueError("each task must have a deps list")
        if t["units"] > capacity:
            raise ValueError("units must not exceed capacity")

    # Build task info
    task_info = {}
    for t in tasks:
        task_info[t["id"]] = {
            "id": t["id"],
            "duration": t["duration"],
            "units": t["units"],
            "deps": list(t["deps"]),
        }

    # Check for unknown dependencies
    for t in tasks:
        for dep in t["deps"]:
            if dep not in task_info:
                raise ValueError("unknown dependency")

    # Check for cycles
    def has_cycle():
        visited = set()
        in_stack = set()

        def dfs(node):
            if node in in_stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            in_stack.add(node)
            for dep in task_info[node]["deps"]:
                if dfs(dep):
                    return True
            in_stack.remove(node)
            return False

        for tid in task_info:
            if dfs(tid):
                return True
        return False

    if has_cycle():
        raise ValueError("cycle dependency detected")

    # Simulation
    # State:
    # - completed: set of task ids that have finished
    # - running: dict of task id -> end_time
    # - started: set of task ids that have started
    # - current_time: current simulation time
    # - resource_used: total units currently in use

    completed = set()
    running = {}  # task_id -> end_time
    started = set()
    current_time = 0
    resource_used = 0

    # Helper: check if all deps of a task are completed
    def deps_completed(tid):
        for dep in task_info[tid]["deps"]:
            if dep not in completed:
                return False
        return True

    # Helper: get all tasks that are ready (deps completed, not started)
    def ready_tasks():
        ready = []
        for tid in task_info:
            if tid not in started and deps_completed(tid):
                ready.append(tid)
        return ready

    # Main loop
    while True:
        # Step 1: Release all completed tasks at current_time
        # Find tasks that have finished at or before current_time
        finished_at_current = []
        for tid, end_time in running.items():
            if end_time <= current_time:
                finished_at_current.append(tid)

        for tid in finished_at_current:
            completed.add(tid)
            resource_used -= task_info[tid]["units"]
            del running[tid]

        # Step 2: Scan ready tasks in lexicographic order by id
        ready = sorted(ready_tasks())
        for tid in ready:
            if resource_used + task_info[tid]["units"] <= capacity:
                # Start this task
                started.add(tid)
                running[tid] = current_time + task_info[tid]["duration"]
                resource_used += task_info[tid]["units"]

        # Step 3: Check if all tasks are completed
        if len(completed) == len(task_info):
            break

        # Step 4: Advance to the earliest end time among running tasks
        if running:
            earliest_end = min(running.values())
            current_time = earliest_end
        else:
            # No running tasks but not all completed -> deadlock?
            # This shouldn't happen if no cycles and all deps are valid
            # But let's handle it gracefully
            break

    # Build result
    jobs = []
    for tid in sorted(task_info.keys()):
        # Find start time for this task
        # We need to track start times. Let's recompute or store them.
        # Actually, we need to store start times during simulation.
        # Let me redo the simulation to store start times.

    # Redo simulation with start time tracking
    completed = set()
    running = {}  # task_id -> end_time
    started = set()
    start_times = {}
    current_time = 0
    resource_used = 0

    def deps_completed(tid):
        for dep in task_info[tid]["deps"]:
            if dep not in completed:
                return False
        return True

    def ready_tasks():
        ready = []
        for tid in task_info:
            if tid not in started and deps_completed(tid):
                ready.append(tid)
        return ready

    while True:
        # Release completed tasks
        finished_at_current = []
        for tid, end_time in running.items():
            if end_time <= current_time:
                finished_at_current.append(tid)

        for tid in finished_at_current:
            completed.add(tid)
            resource_used -= task_info[tid]["units"]
            del running[tid]

        # Scan ready tasks
        ready = sorted(ready_tasks())
        for tid in ready:
            if resource_used + task_info[tid]["units"] <= capacity:
                started.add(tid)
                start_times[tid] = current_time
                running[tid] = current_time + task_info[tid]["duration"]
                resource_used += task_info[tid]["units"]

        # Check completion
        if len(completed) == len(task_info):
            break

        # Advance time
        if running:
            earliest_end = min(running.values())
            current_time = earliest_end
        else:
            break

    # Build jobs sorted by id
    jobs = []
    for tid in sorted(task_info.keys()):
        jobs.append({
            "id": tid,
            "start": start_times[tid],
            "end": start_times[tid] + task_info[tid]["duration"],
        })

    makespan = max((start_times[tid] + task_info[tid]["duration"]) for tid in task_info) if task_info else 0

    return {"jobs": jobs, "makespan": makespan}