```python
def schedule(tasks, capacity):
    if not isinstance(capacity, int) or capacity <= 0:
        raise ValueError("capacity must be a positive integer")
    
    # Validate tasks
    task_map = {}
    for t in tasks:
        tid = t["id"]
        if not isinstance(tid, str):
            raise ValueError("id must be a string")
        if tid in task_map:
            raise ValueError("duplicate id")
        duration = t["duration"]
        units = t["units"]
        deps = t["deps"]
        if not isinstance(duration, int) or duration <= 0:
            raise ValueError("duration must be a positive integer")
        if not isinstance(units, int) or units <= 0:
            raise ValueError("units must be a positive integer")
        if units > capacity:
            raise ValueError("units exceeds capacity")
        if not isinstance(deps, list):
            raise ValueError("deps must be a list")
        for d in deps:
            if not isinstance(d, str):
                raise ValueError("dep must be a string")
        task_map[tid] = {"id": tid, "duration": duration, "units": units, "deps": deps}
    
    if not tasks:
        return {"jobs": [], "makespan": 0}
    
    # Check for unknown dependencies
    for tid, t in task_map.items():
        for d in t["deps"]:
            if d not in task_map:
                raise ValueError(f"unknown dependency: {d}")
    
    # Check for circular dependencies using topological sort (Kahn's algorithm)
    in_degree = {tid: len(t["deps"]) for tid, t in task_map.items()}
    dependents = {tid: [] for tid in task_map}
    for tid, t in task_map.items():
        for d in t["deps"]:
            dependents[d].append(tid)
    
    queue = [tid for tid in sorted(task_map.keys()) if in_degree[tid] == 0]
    topo_order = []
    while queue:
        # Process in sorted order for determinism
        queue.sort()
        node = queue.pop(0)
        topo_order.append(node)
        for dep in dependents[node]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)
    
    if len(topo_order) != len(task_map):
        raise ValueError("circular dependency detected")
    
    # Simulation
    # State:
    # - completed: set of task ids that have finished
    # - running: dict of tid -> (start_time, end_time, units)
    # - started: set of task ids that have been started
    # - current_time: int
    
    completed = set()
    running = {}  # tid -> (start, end, units)
    started = set()
    current_time = 0
    
    # We need to track which tasks are ready (all deps completed) and not started
    # At each event time:
    # 1. Release all completed tasks (those with end <= current_time)
    # 2. Scan all tasks in id lexicographic order: if deps all completed and not started, try to start
    # 3. If no task can be started and there are running tasks, advance to earliest end time
    # 4. If no running tasks and no tasks can be started, we're done (or error if tasks remain)
    
    all_ids = sorted(task_map.keys())
    
    while True:
        # Step 1: Release completed tasks
        finished = []
        for tid in list(running.keys()):
            start, end, units = running[tid]
            if end <= current_time:
                finished.append(tid)
        for tid in finished:
            del running[tid]
            completed.add(tid)
        
        # Step 2: Try to start tasks in id lexicographic order
        # Available resources
        used = sum(units for (s, e, units) in running.values())
        
        for tid in all_ids:
            if tid in started:
                continue
            t = task_map[tid]
            # Check if all deps are completed
            if all(d in completed for d in t["deps"]):
                if t["units"] <= capacity - used:
                    # Start this task
                    start_time = current_time
                    end_time = current_time + t["duration"]
                    running[tid] = (start_time, end_time, t["units"])
                    started.add(tid)
                    used += t["units"]
        
        # Check if all tasks are done
        if len(completed) == len(task_map):
            break
        
        # If no running tasks but not all completed, something is wrong (shouldn't happen with valid input)
        if not running:
            # This means we have tasks that can't be started because their deps aren't met,
            # but no tasks are running. This would indicate a circular dependency or some issue.
            # But we already checked for circular deps, so this shouldn't happen.
            # Actually, it could happen if there are tasks whose deps are never completed.
            # But with valid topological order, this shouldn't happen.
            raise ValueError("unable to schedule all tasks")
        
        # Step 3: Advance to earliest end time among running tasks
        next_time = min(end for (s, end, units) in running.values())
        current_time = next_time
    
    # Build result
    jobs = []
    for tid in all_ids:
        # Find the start and end for this task
        # We need to track when each task started and ended
        # Let's re-derive from the simulation... actually we need to store this
    
    # Hmm, I need to track start/end times for each task. Let me redo this more carefully.
    
    # Let me restart the simulation with proper tracking.
    
    completed = set()
    running = {}  # tid -> (start, end, units)
    started = set()
    current_time = 0
    task_times = {}  # tid -> (start, end)
    
    all_ids = sorted(task_map.keys())
    
    while True:
        # Step 1: Release completed tasks
        finished = []
        for tid in list(running.keys()):
            start, end, units = running[tid]
            if end <= current_time:
                finished.append(tid)
        for tid in finished:
            del running[tid]
            completed.add(tid)
            task_times[tid] = (start, end)
        
        # Step 2: Try to start tasks in id lexicographic order
        used = sum(units for (s, e, units) in running.values())
        
        for tid in all_ids:
            if tid in started:
                continue
            t = task_map[tid]
            if all(d in completed for d in t["deps"]):
                if t["units"] <= capacity - used:
                    start_time = current_time
                    end_time = current_time + t["duration"]
                    running[tid] = (start_time, end_time, t["units"])
                    started.add(tid)
                    used += t["units"]
        
        # Check if all tasks are done
        if len(completed) == len(task_map):
            break
        
        if not running:
            raise ValueError("unable to schedule all tasks")
        
        # Step 3: Advance to earliest end time
        next_time = min(end for (s, end, units) in running.values())
        current_time = next_time
    
    # Build jobs list sorted by id
    jobs = []
    for tid in all_ids:
        start, end = task_times[tid]
        jobs.append({"id": tid, "start": start, "end": end})
    
    makespan = max(end for (s, end) in task_times.values()) if task_times else 0
    
    return {"jobs": jobs, "makespan": makespan}
```