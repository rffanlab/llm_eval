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
        # Release completed tasks at current_time
        new_running = []
        for end_time, tid, units in running:
            if end_time <= current_time:
                completed.add(tid)
            else:
                new_running.append((end_time, tid, units))
        running = new_running
        
        # Calculate available capacity
        used_capacity = sum(units for _, _, units in running)
        available_capacity = capacity - used_capacity
        
        # Find ready tasks: deps completed, not started, not running
        ready_tasks = []
        for tid in all_ids:
            if tid in started or tid in completed:
                continue
            t = task_map[tid]
            # Check if all deps are completed
            if all(dep in completed for dep in t["deps"]):
                ready_tasks.append(tid)
        
        # Sort ready tasks by id (already sorted since all_ids is sorted and we iterate in order)
        # ready_tasks is already in sorted order because all_ids is sorted
        
        # Try to start tasks
        started_this_round = False
        for tid in ready_tasks:
            t = task_map[tid]
            units_needed = t["units"]
            if units_needed <= available_capacity:
                # Start this task
                start_time = current_time
                end_time = current_time + t["duration"]
                job_results[tid] = {"id": tid, "start": start_time, "end": end_time}
                started.add(tid)
                running.append((end_time, tid, units_needed))
                available_capacity -= units_needed
                started_this_round = True
        
        # If no tasks were started and there are still tasks to complete, advance time
        if not started_this_round:
            if not running:
                # This shouldn't happen if there are no cycles and all deps are satisfied
                # But if there are tasks that can't start due to deps not being met, it's a cycle issue
                # We already checked for cycles, so this shouldn't happen
                break
            # Advance to the earliest end time among running tasks
            earliest_end = min(end_time for end_time, _, _ in running)
            current_time = earliest_end
    
    # Build result
    jobs = [job_results[tid] for tid in all_ids]
    makespan = max(job["end"] for job in jobs) if jobs else 0
    
    return {"jobs": jobs, "makespan": makespan}
```