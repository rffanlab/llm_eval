```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}
    
    # Validate inputs
    task_map = {}
    for t in tasks:
        tid = t["id"]
        if tid in task_map:
            raise ValueError("Duplicate task id")
        task_map[tid] = t
    
    # Check for unknown dependencies and cycles
    all_ids = set(task_map.keys())
    for t in tasks:
        for dep in t["deps"]:
            if dep not in all_ids:
                raise ValueError(f"Unknown dependency: {dep}")
    
    # Check for cycles using topological sort (Kahn's algorithm)
    in_degree = {tid: 0 for tid in all_ids}
    dependents = {tid: [] for tid in all_ids}
    for t in tasks:
        for dep in t["deps"]:
            in_degree[t["id"]] += 1
            dependents[dep].append(t["id"])
    
    queue = [tid for tid in all_ids if in_degree[tid] == 0]
    topo_count = 0
    while queue:
        node = queue.pop(0)
        topo_count += 1
        for neighbor in dependents[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    if topo_count != len(all_ids):
        raise ValueError("Cycle detected in dependencies")
    
    # Check units > capacity
    for t in tasks:
        if t["units"] > capacity:
            raise ValueError(f"Task {t['id']} units {t['units']} exceeds capacity {capacity}")
    
    # Simulation
    # State: for each task, track if started, if completed, start time, end time
    started = {tid: False for tid in all_ids}
    completed = {tid: False for tid in all_ids}
    start_time = {tid: None for tid in all_ids}
    end_time = {tid: None for tid in all_ids}
    
    current_time = 0
    used_capacity = 0
    running_tasks = []  # list of (end_time, task_id)
    
    # We need to track which tasks are ready (deps completed) and not started
    # At each event time:
    # 1. Release completed tasks (update used_capacity, mark completed)
    # 2. Find all tasks whose deps are all completed and not started, sort by id
    # 3. Try to start them in order if capacity allows
    
    while len(completed) > 0 and not all(completed.values()):
        # Step 1: Release completed tasks at current_time
        new_running = []
        for end_t, tid in running_tasks:
            if end_t <= current_time:
                completed[tid] = True
                used_capacity -= task_map[tid]["units"]
            else:
                new_running.append((end_t, tid))
        running_tasks = new_running
        
        # Step 2: Find ready tasks (deps all completed, not started)
        ready_tasks = []
        for tid in all_ids:
            if not started[tid] and not completed[tid]:
                deps = task_map[tid]["deps"]
                if all(completed[dep] for dep in deps):
                    ready_tasks.append(tid)
        
        # Sort by id lexicographically
        ready_tasks.sort()
        
        # Step 3: Try to start ready tasks
        for tid in ready_tasks:
            units = task_map[tid]["units"]
            if used_capacity + units <= capacity:
                # Start this task
                started[tid] = True
                start_time[tid] = current_time
                duration = task_map[tid]["duration"]
                end_time[tid] = current_time + duration
                used_capacity += units
                running_tasks.append((end_time[tid], tid))
        
        # If no tasks are running and no tasks can be started, but not all completed, something is wrong
        # But with valid input and no cycles, this shouldn't happen unless we're waiting for time to advance
        
        # If there are running tasks, advance to the earliest end time
        if running_tasks:
            next_end = min(end_t for end_t, tid in running_tasks)
            current_time = next_end
        else:
            # No running tasks and no tasks started this round
            # Check if there are still unstarted tasks
            if any(not started[tid] and not completed[tid] for tid in all_ids):
                # This means some tasks are ready but couldn't start due to capacity
                # But we just tried to start all ready tasks. If none started and none running,
                # and there are unstarted tasks, it means they're not ready (deps not met)
                # But we checked deps... Let me re-examine.
                # Actually, if no tasks are running and no tasks were started, and there are unstarted tasks,
                # it means those tasks have deps that aren't completed. But we only advance time when tasks are running.
                # This situation shouldn't occur with valid input.
                # However, if all ready tasks couldn't start due to capacity, and no tasks are running,
                # that's a deadlock. But with valid input and units <= capacity, at least one task should be startable
                # if it's ready. Unless capacity is 0, but capacity is positive.
                # Let's break to avoid infinite loop
                break
            else:
                break
    
    # Build result
    jobs = []
    for tid in sorted(all_ids):
        jobs.append({
            "id": tid,
            "start": start_time[tid],
            "end": end_time[tid]
        })
    
    makespan = max(end_time.values()) if end_time.values() else 0
    
    return {"jobs": jobs, "makespan": makespan}
```