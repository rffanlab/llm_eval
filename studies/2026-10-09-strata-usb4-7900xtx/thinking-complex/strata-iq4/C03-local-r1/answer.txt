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
    adj = {tid: [] for tid in all_ids}
    for t in tasks:
        for dep in t["deps"]:
            adj[dep].append(t["id"])
            in_degree[t["id"]] += 1
    
    queue = [tid for tid in all_ids if in_degree[tid] == 0]
    topo_count = 0
    while queue:
        node = queue.pop(0)
        topo_count += 1
        for neighbor in adj[node]:
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
    # State tracking
    completed = set()
    started = set()
    running = []  # list of (end_time, task_id, units)
    current_time = 0
    result_jobs = []
    
    # Precompute dependencies for quick check
    deps_map = {t["id"]: set(t["deps"]) for t in tasks}
    duration_map = {t["id"]: t["duration"] for t in tasks}
    units_map = {t["id"]: t["units"] for t in tasks}
    
    remaining_tasks = set(all_ids)
    
    while remaining_tasks or running:
        # Release completed tasks at current_time
        new_running = []
        for end_time, tid, units in running:
            if end_time <= current_time:
                completed.add(tid)
                remaining_tasks.discard(tid)
            else:
                new_running.append((end_time, tid, units))
        running = new_running
        
        # Calculate current resource usage
        current_usage = sum(units for _, _, units in running)
        
        # Get available tasks: deps completed, not started, not running
        available = []
        for tid in remaining_tasks:
            if tid in started:
                continue
            if deps_map[tid].issubset(completed):
                available.append(tid)
        
        # Sort by id lexicographically
        available.sort()
        
        # Try to start tasks
        for tid in available:
            u = units_map[tid]
            if current_usage + u <= capacity:
                # Start task
                started.add(tid)
                end_time = current_time + duration_map[tid]
                running.append((end_time, tid, u))
                current_usage += u
                result_jobs.append({"id": tid, "start": current_time, "end": end_time})
        
        # If no tasks are running and no tasks can be started, but there are remaining tasks, something is wrong
        # But we already checked for cycles, so this shouldn't happen unless there's a deadlock due to capacity
        # Actually, if capacity is sufficient for at least one task, we should be able to make progress.
        # If no tasks are running and no tasks can be started, it means all remaining tasks have unmet deps
        # or units > capacity (already checked). Since we checked cycles, deps should eventually be met.
        # But if no task is running and no task can start, we might be stuck.
        # However, if there are remaining tasks and none are running, and none can start, it's a problem.
        # Let's advance time to the next event if there are running tasks.
        
        if not running:
            if remaining_tasks:
                # This should not happen if inputs are valid (no cycles, units <= capacity)
                # But just in case, break to avoid infinite loop
                break
            else:
                break
        
        # Advance to the earliest end time among running tasks
        earliest_end = min(end_time for end_time, _, _ in running)
        current_time = earliest_end
    
    # Sort jobs by id
    result_jobs.sort(key=lambda x: x["id"])
    
    # Calculate makespan
    makespan = max((job["end"] for job in result_jobs), default=0)
    
    return {"jobs": result_jobs, "makespan": makespan}
```