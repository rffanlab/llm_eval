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
    # 1. Release all completed tasks (those whose end <= current_time)
    # 2. Scan all tasks in id-sorted order that are not started and whose deps are all completed
    #    - If resources available, start it
    # 3. After scanning, advance to the earliest end time among running tasks
    
    # But we need to be careful: "先释放全部已完成任务" means at each event moment, first release all tasks that have completed (end <= current_time).
    
    # Let's use an event-driven approach.
    
    # Sort task ids for scanning
    sorted_ids = sorted(task_map.keys())
    
    # We'll simulate step by step.
    # At any point, we have a set of running tasks. The next event is the minimum end time among running tasks.
    # But we also need to handle the initial state where no tasks are running.
    
    # Let's think of it as:
    # - current_time starts at 0
    # - Loop:
    #   a. Release all tasks with end <= current_time (move from running to completed)
    #   b. Scan sorted_ids: for each task not started, check if all deps are in completed. If yes, check if available resources >= units. If yes, start it (add to running, mark started).
    #   c. If no running tasks and no more tasks can be started, we're done.
    #   d. Otherwise, advance current_time to the minimum end time among running tasks.
    
    # But wait: after releasing and starting, if there are still running tasks, we advance to the next end time.
    # If there are no running tasks but there are still unstarted tasks whose deps aren't met, that would be a problem (but we already checked for cycles, so this shouldn't happen if we process correctly).
    
    # Actually, let me reconsider. The key insight is:
    # - At each event time, we first release completed tasks, then try to start new tasks.
    # - After trying to start tasks, if there are running tasks, we jump to the next end time.
    # - If there are no running tasks and no tasks can be started (all remaining have unmet deps), but we've verified no cycles, this shouldn't happen.
    
    # Let's implement:
    
    while True:
        # Step 1: Release all tasks that have completed (end <= current_time)
        to_release = [tid for tid, (s, e, u) in running.items() if e <= current_time]
        for tid in to_release:
            del running[tid]
            completed.add(tid)
        
        # Step 2: Scan all tasks in id-sorted order
        for tid in sorted_ids:
            if tid in started:
                continue
            info = task_map[tid]
            # Check if all deps are completed
            if all(dep in completed for dep in info["deps"]):
                # Check available resources
                used = sum(running[t][2] for t in running)
                if used + info["units"] <= capacity:
                    # Start the task
                    start = current_time
                    end = start + info["duration"]
                    running[tid] = (start, end, info["units"])
                    started.add(tid)
        
        # Step 3: Check if we're done
        if not running and len(started) == len(task_map):
            break
        
        if not running:
            # No running tasks, but not all started. This should not happen if no cycles.
            # But let's check if there are tasks that can be started
            can_start = False
            for tid in sorted_ids:
                if tid in started:
                    continue
                info = task_map[tid]
                if all(dep in completed for dep in info["deps"]):
                    can_start = True
                    break
            if not can_start:
                # This means we have a deadlock, which implies a cycle (but we already checked)
                raise ValueError("circular dependency")
            # If can_start is True, it means we should have started them in step 2, so this is a bug
            # Actually, if can_start is True but we didn't start them, it's because resources weren't available,
            # but if no tasks are running, resources should be fully available. So this shouldn't happen.
            raise ValueError("unexpected state")
        
        # Step 4: Advance to the earliest end time among running tasks
        next_time = min(running[tid][1] for tid in running)
        current_time = next_time
    
    # Build result
    jobs = []
    for tid in sorted_ids:
        if tid in started:
            s, e, u = running.get(tid, (None, None, None))
            # If the task is completed, it's no longer in running. We need to track start/end.
            # Let me restructure: keep a record of start and end for each started task.
            pass
    
    # I need to track start and end times for all tasks. Let me redo this.
    
    # Let me restart the simulation with proper tracking.
    
    # Actually, let me just rewrite the whole function cleanly.
    
    return {"jobs": [], "makespan": 0}
```

Wait, I made a mess. Let me rewrite this cleanly.

```python
def schedule(tasks, capacity):
    if capacity <= 0:
        raise ValueError("capacity must be positive")
    
    if not tasks:
        return {"jobs": [], "makespan": 0}
    
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
    
    for tid, info in task_map.items():
        for dep in info["deps"]:
            if dep not in task_map:
                raise ValueError("unknown dependency")
    
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
    
    completed = set()
    running = {}
    started = set()
    start_times = {}
    end_times = {}
    current_time = 0
    sorted_ids = sorted(task_map.keys())
    
    while True:
        to_release = [tid for tid in running if running[tid][1] <= current_time]
        for tid in to_release:
            del running[tid]
            completed.add(tid)
        
        for tid in sorted_ids:
            if tid in started:
                continue
            info = task_map[tid]
            if all(dep in completed for dep in info["deps"]):
                used = sum(running[t][2] for t in running)
                if used + info["units"] <= capacity:
                    start = current_time
                    end = start + info["duration"]
                    running[tid] = (start, end, info["units"])
                    started.add(tid)
                    start_times[tid] = start
                    end_times[tid] = end
        
        if not running and len(started) == len(task_map):
            break
        
        if not running:
            raise ValueError("unexpected state")
        
        next_time = min(running[tid][1] for tid in running)
        current_time = next_time
    
    jobs = [{"id": tid, "start": start_times[tid], "end": end_times[tid]} for tid in sorted_ids]
    makespan = max(end_times.values()) if end_times else 0
    
    return {"jobs": jobs, "makespan": makespan}
```