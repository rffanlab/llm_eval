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
    sorted_count = 0
    while queue:
        node = queue.pop(0)
        sorted_count += 1
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    if sorted_count != len(all_ids):
        raise ValueError("Cycle detected in dependencies")
    
    # Check units > capacity
    for t in tasks:
        if t["units"] > capacity:
            raise ValueError(f"Task {t['id']} units {t['units']} exceeds capacity {capacity}")
    
    # Simulation
    # State: for each task, track status: 'pending', 'running', 'done'
    # running: dict of task_id -> (start_time, end_time, units)
    # done: set of task_ids
    # pending: set of task_ids
    
    pending = set(all_ids)
    running = {}  # task_id -> (start, end, units)
    done = set()
    
    current_time = 0
    jobs = []
    
    # Precompute dependency counts for quick checking
    dep_count = {tid: len(task_map[tid]["deps"]) for tid in all_ids}
    # For each task, list of tasks that depend on it (successors)
    successors = {tid: [] for tid in all_ids}
    for t in tasks:
        for dep in t["deps"]:
            successors[dep].append(t["id"])
    
    # Track remaining dependency count for each task
    remaining_deps = {tid: len(task_map[tid]["deps"]) for tid in all_ids}
    
    # Available tasks: tasks with all deps done and not started
    # We'll compute this dynamically
    
    def get_available_tasks():
        avail = []
        for tid in pending:
            if remaining_deps[tid] == 0:
                avail.append(tid)
        return sorted(avail)
    
    while pending or running:
        # Release completed tasks at current_time
        completed = []
        for tid, (start, end, units) in running.items():
            if end <= current_time:
                completed.append(tid)
        
        for tid in completed:
            del running[tid]
            done.add(tid)
            pending.discard(tid)
            # Update remaining deps for successors
            for succ in successors[tid]:
                remaining_deps[succ] -= 1
        
        # Try to start available tasks
        available = get_available_tasks()
        used_capacity = sum(running[tid][2] for tid in running)
        
        for tid in available:
            units = task_map[tid]["units"]
            if used_capacity + units <= capacity:
                # Start this task
                duration = task_map[tid]["duration"]
                start = current_time
                end = current_time + duration
                running[tid] = (start, end, units)
                used_capacity += units
                pending.discard(tid)
        
        # If no tasks are running, we need to advance time
        if not running:
            # This shouldn't happen if there are pending tasks with deps met
            # Check if there are pending tasks with unmet deps
            if pending:
                # Find the earliest end time among running tasks... but running is empty
                # This means we have a deadlock? No, we checked for cycles.
                # If running is empty and pending is not empty, it means no task can start
                # This would be a cycle, which we already checked.
                # So this case should not occur.
                break
        
        # Advance to the earliest end time among running tasks
        if running:
            earliest_end = min(end for (start, end, units) in running.values())
            current_time = earliest_end
    
    # Collect jobs
    for tid in sorted(all_ids):
        # Find the job info
        # We need to track start and end for each task
        # Let's restructure: store job info when task completes
        pass
    
    # Redo: track job info properly
    # Let me rewrite the simulation to track job start/end
    
    # Reset
    pending = set(all_ids)
    running = {}  # task_id -> (start, end, units)
    done = set()
    job_info = {}  # task_id -> (start, end)
    
    current_time = 0
    remaining_deps = {tid: len(task_map[tid]["deps"]) for tid in all_ids}
    
    while pending or running:
        # Release completed tasks at current_time
        completed = []
        for tid, (start, end, units) in running.items():
            if end <= current_time:
                completed.append(tid)
        
        for tid in completed:
            del running[tid]
            done.add(tid)
            pending.discard(tid)
            for succ in successors[tid]:
                remaining_deps[succ] -= 1
        
        # Try to start available tasks
        available = []
        for tid in pending:
            if remaining_deps[tid] == 0:
                available.append(tid)
        available.sort()
        
        used_capacity = sum(running[tid][2] for tid in running)
        
        for tid in available:
            units = task_map[tid]["units"]
            if used_capacity + units <= capacity:
                duration = task_map[tid]["duration"]
                start = current_time
                end = current_time + duration
                running[tid] = (start, end, units)
                job_info[tid] = (start, end)
                used_capacity += units
                pending.discard(tid)
        
        if not running:
            break
        
        # Advance to the earliest end time among running tasks
        earliest_end = min(end for (start, end, units) in running.values())
        current_time = earliest_end
    
    # Build result
    jobs_list = []
    for tid in sorted(all_ids):
        start, end = job_info[tid]
        jobs_list.append({"id": tid, "start": start, "end": end})
    
    makespan = max(end for (start, end) in job_info.values()) if job_info else 0
    
    return {"jobs": jobs_list, "makespan": makespan}
```