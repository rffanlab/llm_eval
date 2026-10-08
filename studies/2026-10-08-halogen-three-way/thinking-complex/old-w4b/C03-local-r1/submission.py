```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}
    
    # Validate and build lookup
    task_map = {}
    for t in tasks:
        tid = t["id"]
        if tid in task_map:
            raise ValueError("Duplicate task id")
        task_map[tid] = t
    
    # Validate dependencies exist and check for cycles
    # Also validate units <= capacity
    for t in tasks:
        if t["units"] > capacity:
            raise ValueError("units exceeds capacity")
        for dep in t["deps"]:
            if dep not in task_map:
                raise ValueError("Unknown dependency")
    
    # Detect cycles using DFS
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in task_map}
    
    def has_cycle(node):
        color[node] = GRAY
        for dep in task_map[node]["deps"]:
            if color[dep] == GRAY:
                return True
            if color[dep] == WHITE:
                if has_cycle(dep):
                    return True
        color[node] = BLACK
        return False
    
    for tid in task_map:
        if color[tid] == WHITE:
            if has_cycle(tid):
                raise ValueError("Circular dependency detected")
    
    # Simulation
    # State: time, running tasks (list of (end_time, task_id, units)), completed set, started set
    time = 0
    running = []  # list of (end_time, task_id, units)
    completed = set()
    started = set()
    jobs = []
    
    # All task ids sorted for deterministic scanning
    all_ids = sorted(task_map.keys())
    
    while len(completed) < len(task_map):
        # Release all completed tasks at current time
        new_running = []
        for end_time, tid, units in running:
            if end_time <= time:
                completed.add(tid)
            else:
                new_running.append((end_time, tid, units))
        running = new_running
        
        # Calculate current used capacity
        used = sum(units for _, _, units in running)
        
        # Scan all tasks in id order
        for tid in all_ids:
            if tid in started:
                continue
            # Check if all deps are completed
            deps = task_map[tid]["deps"]
            if all(d in completed for d in deps):
                units = task_map[tid]["units"]
                duration = task_map[tid]["duration"]
                if used + units <= capacity:
                    # Start this task
                    start_time = time
                    end_time = time + duration
                    running.append((end_time, tid, units))
                    started.add(tid)
                    jobs.append({"id": tid, "start": start_time, "end": end_time})
                    used += units
        
        # If all tasks are started and running is empty, we're done
        if len(started) == len(task_map) and not running:
            break
        
        # Advance time to the earliest end time among running tasks
        if running:
            min_end = min(end_time for end_time, _, _ in running)
            time = min_end
        else:
            # No running tasks but not all completed - this shouldn't happen if no cycles
            # But if there are tasks that can't start due to deps not met, and no running tasks,
            # it means we're stuck. But we already checked for cycles.
            # This case means all remaining tasks have deps that are not completed,
            # but no tasks are running to complete them. This is a deadlock.
            # However, with cycle detection, this shouldn't happen.
            # Let's break to avoid infinite loop
            break
    
    makespan = max((j["end"] for j in jobs), default=0)
    
    # Sort jobs by id
    jobs.sort(key=lambda x: x["id"])
    
    return {"jobs": jobs, "makespan": makespan}
```