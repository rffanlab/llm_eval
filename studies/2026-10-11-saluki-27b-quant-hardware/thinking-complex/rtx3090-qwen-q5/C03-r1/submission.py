```python
def schedule(tasks, capacity):
    if capacity <= 0:
        raise ValueError("capacity must be positive")
    
    if not tasks:
        return {"jobs": [], "makespan": 0}
    
    # Build task info
    task_map = {}
    for t in tasks:
        tid = t["id"]
        if tid in task_map:
            raise ValueError("duplicate id")
        duration = t["duration"]
        units = t["units"]
        deps = t["deps"]
        if not isinstance(duration, int) or duration <= 0:
            raise ValueError("duration must be positive integer")
        if not isinstance(units, int) or units <= 0:
            raise ValueError("units must be positive integer")
        if units > capacity:
            raise ValueError("units exceeds capacity")
        task_map[tid] = {"duration": duration, "units": units, "deps": list(deps)}
    
    # Check for unknown dependencies
    for tid, info in task_map.items():
        for dep in info["deps"]:
            if dep not in task_map:
                raise ValueError("unknown dependency")
    
    # Check for circular dependencies using topological sort (Kahn's algorithm)
    in_degree = {tid: 0 for tid in task_map}
    dependents = {tid: [] for tid in task_map}
    for tid, info in task_map.items():
        for dep in info["deps"]:
            in_degree[tid] += 1
            dependents[dep].append(tid)
    
    from collections import deque
    queue = deque([tid for tid in task_map if in_degree[tid] == 0])
    topo_order = []
    while queue:
        node = queue.popleft()
        topo_order.append(node)
        for child in dependents[node]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
    
    if len(topo_order) != len(task_map):
        raise ValueError("circular dependency")
    
    # Simulation
    # State:
    # - completed: set of task ids that have finished
    # - running: dict of tid -> (start, end, units)
    # - started: set of task ids that have been started
    # - current_time: int
    
    completed = set()
    running = {}  # tid -> (start, end, units)
    started = set()
    current_time = 0
    
    # We need to process events. At each event time:
    # 1. Release all completed tasks (those with end <= current_time)
    # 2. Scan all tasks in id-sorted order: if not started, all deps completed, and resources available, start it
    # 3. If no tasks can be started and there are running tasks, advance to earliest end time
    # 4. If no tasks can be started and no running tasks, but there are unstarted tasks -> deadlock (shouldn't happen if no cycles)
    
    all_ids_sorted = sorted(task_map.keys())
    
    while len(started) < len(task_map):
        # Step 1: Release completed tasks
        finished_now = []
        for tid in list(running.keys()):
            if running[tid][1] <= current_time:
                finished_now.append(tid)
        for tid in finished_now:
            del running[tid]
            completed.add(tid)
        
        # Step 2: Try to start tasks in id-sorted order
        started_any = False
        for tid in all_ids_sorted:
            if tid in started:
                continue
            info = task_map[tid]
            # Check all deps are completed
            if not all(dep in completed for dep in info["deps"]):
                continue
            # Check resource availability
            current_used = sum(running[t][2] for t in running)
            if current_used + info["units"] <= capacity:
                # Start the task
                start = current_time
                end = start + info["duration"]
                running[tid] = (start, end, info["units"])
                started.add(tid)
                started_any = True
        
        # Step 3: If no tasks started, advance time
        if not started_any:
            if not running:
                # No running tasks and no tasks can be started -> deadlock
                raise ValueError("deadlock detected")
            # Advance to earliest end time
            next_time = min(running[tid][1] for tid in running)
            current_time = next_time
    
    # All tasks started. Now we need to wait for all to complete.
    # Actually, the loop above only exits when all tasks are started.
    # We need to continue until all are completed.
    
    while running:
        # Release completed tasks
        finished_now = []
        for tid in list(running.keys()):
            if running[tid][1] <= current_time:
                finished_now.append(tid)
        for tid in finished_now:
            del running[tid]
            completed.add(tid)
        
        if running:
            next_time = min(running[tid][1] for tid in running)
            current_time = next_time
    
    makespan = current_time
    
    # Build result
    jobs = []
    for tid in all_ids_sorted:
        # Find start and end
        # We need to track start/end for each task
        pass
    
    # We need to re-track start and end times. Let me redo this more carefully.
    
    # Actually, let me restructure to track start/end for each task.
    
    return {"jobs": jobs, "makespan": makespan}
```

Wait, I need to track start and end times for each task. Let me rewrite this properly.

```python
def schedule(tasks, capacity):
    if capacity <= 0:
        raise ValueError("capacity must be positive")
    
    if not tasks:
        return {"jobs": [], "makespan": 0}
    
    # Build task info
    task_map = {}
    for t in tasks:
        tid = t["id"]
        if tid in task_map:
            raise ValueError("duplicate id")
        duration = t["duration"]
        units = t["units"]
        deps = t["deps"]
        if not isinstance(duration, int) or duration <= 0:
            raise ValueError("duration must be positive integer")
        if not isinstance(units, int) or units <= 0:
            raise ValueError("units must be positive integer")
        if units > capacity:
            raise ValueError("units exceeds capacity")
        task_map[tid] = {"duration": duration, "units": units, "deps": list(deps)}
    
    # Check for unknown dependencies
    for tid, info in task_map.items():
        for dep in info["deps"]:
            if dep not in task_map:
                raise ValueError("unknown dependency")
    
    # Check for circular dependencies using topological sort (Kahn's algorithm)
    in_degree = {tid: 0 for tid in task_map}
    dependents = {tid: [] for tid in task_map}
    for tid, info in task_map.items():
        for dep in info["deps"]:
            in_degree[tid] += 1
            dependents[dep].append(tid)
    
    queue = []
    for tid in task_map:
        if in_degree[tid] == 0:
            queue.append(tid)
    
    topo_order = []
    while queue:
        node = queue.pop(0)
        topo_order.append(node)
        for child in dependents[node]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
    
    if len(topo_order) != len(task_map):
        raise ValueError("circular dependency")
    
    # Simulation
    completed = set()
    running = {}  # tid -> (start, end, units)
    started = set()
    current_time = 0
    start_end = {}  # tid -> (start, end)
    
    all_ids_sorted = sorted(task_map.keys())
    
    while len(started) < len(task_map):
        # Step 1: Release completed tasks
        finished_now = []
        for tid in list(running.keys()):
            if running[tid][1] <= current_time:
                finished_now.append(tid)
        for tid in finished_now:
            del running[tid]
            completed.add(tid)
        
        # Step 2: Try to start tasks in id-sorted order
        started_any = False
        for tid in all_ids_sorted:
            if tid in started:
                continue
            info = task_map[tid]
            # Check all deps are completed
            if not all(dep in completed for dep in info["deps"]):
                continue
            # Check resource availability
            current_used = sum(running[t][2] for t in running)
            if current_used + info["units"] <= capacity:
                # Start the task
                start = current_time
                end = start + info["duration"]
                running[tid] = (start, end, info["units"])
                started.add(tid)
                start_end[tid] = (start, end)
                started_any = True
        
        # Step 3: If no tasks started, advance time
        if not started_any:
            if not running:
                raise ValueError("deadlock detected")
            next_time = min(running[tid][1] for tid in running)
            current_time = next_time
    
    # Wait for all running tasks to complete
    while running:
        finished_now = []
        for tid in list(running.keys()):
            if running[tid][1] <= current_time:
                finished_now.append(tid)
        for tid in finished_now:
            del running[tid]
            completed.add(tid)
        
        if running:
            next_time = min(running[tid][1] for tid in running)
            current_time = next_time
    
    makespan = current_time
    
    jobs = []
    for tid in all_ids_sorted:
        s, e = start_end[tid]
        jobs.append({"id": tid, "start": s, "end": e})
    
    return {"jobs": jobs, "makespan": makespan}
```