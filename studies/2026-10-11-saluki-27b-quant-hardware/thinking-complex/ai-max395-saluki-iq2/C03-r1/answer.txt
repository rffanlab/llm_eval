```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    for t in tasks:
        tid = t["id"]
        if tid in task_map:
            raise ValueError("duplicate id")
        task_map[tid] = t

    for t in tasks:
        tid = t["id"]
        dur = t["duration"]
        units = t["units"]
        deps = t["deps"]
        if not isinstance(dur, int) or dur <= 0:
            raise ValueError("invalid duration")
        if not isinstance(units, int) or units <= 0:
            raise ValueError("invalid units")
        if units > capacity:
            raise ValueError("units > capacity")
        for d in deps:
            if d not in task_map:
                raise ValueError("unknown dependency")

    indeg = {tid: 0 for tid in task_map}
    children = {tid: [] for tid in task_map}
    for t in tasks:
        tid = t["id"]
        for d in t["deps"]:
            indeg[tid] += 1
            children[d].append(tid)

    # Kahn's algorithm to detect cycles
    from collections import deque  # not allowed? We'll avoid import.
    # Actually, we cannot import. Let's use a list as queue.
    queue = [tid for tid in task_map if indeg[tid] == 0]
    visited = set()
    order = []
    while queue:
        tid = queue.pop(0)
        if tid in visited:
            continue
        visited.add(tid)
        order.append(tid)
        for ch in children[tid]:
            indeg[ch] -= 1
            if indeg[ch] == 0:
                queue.append(ch)
    if len(order) != len(task_map):
        raise ValueError("circular dependency")

    # Simulate
    # We need to track:
    # - running tasks: list of (id, end_time, units)
    # - completed: set of ids
    # - not_started: set of ids
    # - current_time: int
    # - total_units_used: int

    not_started = set(task_map.keys())
    completed = set()
    running = []  # list of [id, end, units]
    current_time = 0
    makespan = 0

    # We'll process events. At each event time, we first release completed,
    # then scan all not_started tasks in id order, start those that can.
    # Then advance to the earliest end time among running tasks.

    # To avoid infinite loop, we track time.
    # We need to be careful: after starting tasks, we advance to the next event.

    # Let's use a while loop.
    # At each step:
    # 1. Release all running tasks that have end <= current_time.
    # 2. Scan not_started in sorted order, start tasks if deps done and units fit.
    # 3. If no running tasks, and not_started is empty, break.
    # 4. If no running tasks, but not_started not empty, this means deadlock? 
    #    But we already checked for cycles. However, it's possible that all remaining
    #    tasks have deps not completed? No, because if there's no cycle, there must be
    #    at least one task with all deps completed. But wait: after releasing, we scan.
    #    If no task can start (because units don't fit), but there are tasks with deps done,
    #    we still need to advance time to when some running task finishes.
    #    If no running tasks at all, and not_started not empty, and no task can start,
    #    that means all remaining tasks have deps not done -> cycle, which we already checked.
    #    So if no running tasks and not_started not empty, there must be at least one task
    #    with all deps done. If units don't fit for any of them, that's a problem? 
    #    Actually, if units > capacity, we already raised. So units <= capacity.
    #    But it's possible that multiple tasks have deps done, and their units sum > capacity,
    #    but individually each <= capacity. In that case, we start as many as fit, and the rest
    #    wait. So there will be at least one running task. So we won't have no running tasks
    #    and not_started not empty with no task startable.
    #    Wait, what if all remaining tasks have deps done, but each has units > capacity? 
    #    We already checked units > capacity raises. So each units <= capacity.
    #    So at least one can start. So we're safe.

    # Let's implement:
    while not_started or running:
        # Step 1: release completed
        new_running = []
        for r in running:
            if r[1] <= current_time:
                completed.add(r[0])
                # release units
            else:
                new_running.append(r)
        running = new_running

        # Step 2: scan not_started in id order
        # We need to track units used by running tasks
        units_used = sum(r[2] for r in running)
        # We'll iterate over sorted(not_started)
        # But we need to be careful: we should only start tasks whose deps are all in completed
        # We'll build a list of candidates first, then sort by id.
        candidates = []
        for tid in not_started:
            t = task_map[tid]
            deps = t["deps"]
            if all(d in completed for d in deps):
                candidates.append(tid)
        # Sort by id
        candidates.sort()
        started = []
        for tid in candidates:
            t = task_map[tid]
            units = t["units"]
            dur = t["duration"]
            if units_used + units <= capacity:
                # Start this task
                start_time = current_time
                end_time = current_time + dur
                running.append([tid, end_time, units])
                units_used += units
                started.append(tid)
                # Remove from not_started
                not_started.remove(tid)
            else:
                # Skip, continue scanning
                pass

        # Step 3: if no running tasks
        if not running:
            if not_started:
                # This should not happen if no cycles, but let's be safe
                # Actually, it could happen if all remaining tasks have deps not done? 
                # But we checked cycles. Let's raise an error to be safe.
                raise ValueError("deadlock")
            else:
                break
        else:
            # Advance to the earliest end time
            min_end = min(r[1] for r in running)
            current_time = min_end
            makespan = max(makespan, current_time)

    return {
        "jobs": [
            {"id": tid, "start": start, "end": end}
            for tid, start, end in sorted(
                [(r[0], r[1] - r[2], r[1]) for r in running]  # This is wrong
            )
        ],
        "makespan": makespan
    }
```

Wait, I need to track start times properly. Let me redo this more carefully.

```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    for t in tasks:
        tid = t["id"]
        if tid in task_map:
            raise ValueError("duplicate id")
        task_map[tid] = t

    for t in tasks:
        tid = t["id"]
        dur = t["duration"]
        units = t["units"]
        deps = t["deps"]
        if not isinstance(dur, int) or dur <= 0:
            raise ValueError("invalid duration")
        if not isinstance(units, int) or units <= 0:
            raise ValueError("invalid units")
        if units > capacity:
            raise ValueError("units > capacity")
        for d in deps:
            if d not in task_map:
                raise ValueError("unknown dependency")

    indeg = {tid: 0 for tid in task_map}
    children = {tid: [] for tid in task_map}
    for t in tasks:
        tid = t["id"]
        for d in t["deps"]:
            indeg[tid] += 1
            children[d].append(tid)

    # Kahn's algorithm
    queue = [tid for tid in task_map if indeg[tid] == 0]
    visited = set()
    order = []
    while queue:
        tid = queue.pop(0)
        if tid in visited:
            continue
        visited.add(tid)
        order.append(tid)
        for ch in children[tid]:
            indeg[ch] -= 1
            if indeg[ch] == 0:
                queue.append(ch)
    if len(order) != len(task_map):
        raise ValueError("circular dependency")

    # Simulation
    not_started = set(task_map.keys())
    completed = set()
    running = []  # list of [id, end_time, units]
    current_time = 0
    makespan = 0
    job_records = {}  # id -> (start, end)

    while not_started or running:
        # Step 1: release completed tasks
        new_running = []
        for r in running:
            if r[1] <= current_time:
                completed.add(r[0])
            else:
                new_running.append(r)
        running = new_running

        # Step 2: scan not_started in id order
        units_used = sum(r[2] for r in running)
        candidates = []
        for tid in not_started:
            t = task_map[tid]
            deps = t["deps"]
            if all(d in completed for d in deps):
                candidates.append(tid)
        candidates.sort()
        for tid in candidates:
            t = task_map[tid]
            units = t["units"]
            dur = t["duration"]
            if units_used + units <= capacity:
                start_time = current_time
                end_time = current_time + dur
                running.append([tid, end_time, units])
                units_used += units
                not_started.remove(tid)
                job_records[tid] = (start_time, end_time)
            else:
                pass

        # Step 3: advance time
        if not running:
            if not_started:
                raise ValueError("deadlock")
            break
        else:
            min_end = min(r[1] for r in running)
            current_time = min_end
            makespan = max(makespan, current_time)

    # Build jobs sorted by id
    jobs = []
    for tid in sorted(job_records.keys()):
        start, end = job_records[tid]
        jobs.append({"id": tid, "start": start, "end": end})

    return {"jobs": jobs, "makespan": makespan}
```