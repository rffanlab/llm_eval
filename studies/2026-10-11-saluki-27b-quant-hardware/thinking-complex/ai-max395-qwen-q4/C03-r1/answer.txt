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
        started_any = False
        for tid in all_ids:
            if tid in started:
                continue
            t = task_map[tid]
            # Check if all deps are completed
            if all(d in completed for d in t["deps"]):
                # Check if resources are available
                current_units = sum(running[tid2][2] for tid2 in running)
                if current_units + t["units"] <= capacity:
                    # Start the task
                    start_time = current_time
                    end_time = start_time + t["duration"]
                    running[tid] = (start_time, end_time, t["units"])
                    started.add(tid)
                    started_any = True
        
        # Step 3: Check if all tasks are done
        if len(started) == len(task_map):
            # All tasks have been started. Wait for all running to finish.
            if running:
                # Advance to the latest end time among running tasks
                max_end = max(running[tid][1] for tid in running)
                current_time = max_end
                # Release all
                for tid in list(running.keys()):
                    completed.add(tid)
                    del running[tid]
            break
        
        # If no running tasks and no task could be started, but not all tasks are started
        if not running and not started_any:
            # This should not happen if there are no circular deps and all deps are valid
            # But let's check: are there tasks that can never be started?
            # Actually, if there are no running tasks and we couldn't start any, 
            # it means all remaining tasks have unmet dependencies, which would be a cycle.
            # But we already checked for cycles. So this shouldn't happen.
            # However, it could happen if a task's deps are all completed but units > capacity?
            # No, we already checked units <= capacity.
            # Let's just raise an error to be safe.
            raise ValueError("unable to schedule remaining tasks")
        
        # Step 4: Advance to earliest end time among running tasks
        if running:
            min_end = min(running[tid][1] for tid in running)
            current_time = min_end
        else:
            # No running tasks, but we started some in this iteration? That can't happen
            # because if we started a task, it would be in running.
            # If started_any is True but running is empty, that's impossible.
            # If started_any is False and running is empty, we already handled above.
            # So this branch shouldn't be reached.
            break
    
    # Build result
    jobs = []
    for tid in all_ids:
        # Find the start and end time
        # We need to track when each task started and ended
        # Let's re-derive from the simulation... actually we lost that info.
        # Let me redo this more carefully.
    
    # Actually, I need to track start and end times for each task. Let me redo.
    
    # Let me restart the simulation with proper tracking.
    
    completed = set()
    running = {}  # tid -> (start, end, units)
    started = set()
    current_time = 0
    task_start = {}
    task_end = {}
    
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
        started_any = False
        for tid in all_ids:
            if tid in started:
                continue
            t = task_map[tid]
            if all(d in completed for d in t["deps"]):
                current_units = sum(running[tid2][2] for tid2 in running)
                if current_units + t["units"] <= capacity:
                    start_time = current_time
                    end_time = start_time + t["duration"]
                    running[tid] = (start_time, end_time, t["units"])
                    started.add(tid)
                    task_start[tid] = start_time
                    task_end[tid] = end_time
                    started_any = True
        
        # Step 3: Check if all tasks are done
        if len(started) == len(task_map):
            if running:
                max_end = max(running[tid][1] for tid in running)
                current_time = max_end
                for tid in list(running.keys()):
                    completed.add(tid)
                    del running[tid]
            break
        
        if not running and not started_any:
            raise ValueError("unable to schedule remaining tasks")
        
        if running:
            min_end = min(running[tid][1] for tid in running)
            current_time = min_end
        else:
            break
    
    jobs = []
    for tid in all_ids:
        jobs.append({"id": tid, "start": task_start[tid], "end": task_end[tid]})
    
    makespan = max(task_end.values()) if task_end else 0
    
    return {"jobs": jobs, "makespan": makespan}
```