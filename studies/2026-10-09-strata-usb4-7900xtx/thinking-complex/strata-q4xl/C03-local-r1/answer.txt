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
    # First, check all deps exist
    for t in tasks:
        for dep in t["deps"]:
            if dep not in task_map:
                raise ValueError(f"Unknown dependency: {dep}")
    
    # Check for cycles using topological sort (Kahn's algorithm)
    in_degree = {tid: 0 for tid in task_map}
    adj = {tid: [] for tid in task_map}
    for t in tasks:
        for dep in t["deps"]:
            adj[dep].append(t["id"])
            in_degree[t["id"]] += 1
    
    queue = [tid for tid in task_map if in_degree[tid] == 0]
    sorted_count = 0
    while queue:
        node = queue.pop(0)
        sorted_count += 1
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    if sorted_count != len(task_map):
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
    job_results = {}  # id -> {"id": id, "start": start, "end": end}
    
    # Sort task ids for deterministic scanning
    all_ids = sorted(task_map.keys())
    
    while len(completed) < len(task_map):
        # 1. Release all completed tasks at current_time
        new_running = []
        for end_time, tid, units in running:
            if end_time <= current_time:
                completed.add(tid)
            else:
                new_running.append((end_time, tid, units))
        running = new_running
        
        # 2. Calculate available capacity
        used_capacity = sum(units for _, _, units in running)
        available_capacity = capacity - used_capacity
        
        # 3. Scan all tasks in id dictionary order
        # Find tasks that are not started, not completed, and all deps are completed
        candidates = []
        for tid in all_ids:
            if tid in started or tid in completed:
                continue
            deps = task_map[tid]["deps"]
            if all(dep in completed for dep in deps):
                candidates.append(tid)
        
        # Try to start candidates in order
        for tid in candidates:
            units = task_map[tid]["units"]
            if units <= available_capacity:
                # Start this task
                duration = task_map[tid]["duration"]
                start_time = current_time
                end_time = current_time + duration
                started.add(tid)
                running.append((end_time, tid, units))
                job_results[tid] = {"id": tid, "start": start_time, "end": end_time}
                available_capacity -= units
        
        # 4. If no tasks can be started and there are running tasks, advance time
        if not running:
            # This shouldn't happen if there are still incomplete tasks and no cycles
            # But if all remaining tasks have unmet deps that are never completed, it's a bug
            # Since we checked for cycles, this shouldn't happen
            break
        
        # Advance to the earliest end time among running tasks
        if running:
            earliest_end = min(end_time for end_time, _, _ in running)
            current_time = earliest_end
    
    # Build result
    jobs = [job_results[tid] for tid in all_ids if tid in job_results]
    # Sort by id (already in order since all_ids is sorted)
    makespan = max((job["end"] for job in jobs), default=0)
    
    return {"jobs": jobs, "makespan": makespan}
```