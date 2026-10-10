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
    # 4. If no running tasks and no tasks can be started, we're done (but this shouldn't happen if all tasks are scheduled)
    
    # Actually, let me re-read the spec:
    # "每个事件时刻先释放全部已完成任务，再从所有依赖完成且未启动的任务按id字典序扫描：资源够就立即启动，不够就跳过并继续扫描其他任务。全部扫描后，推进到最早运行任务结束。"
    
    # So the algorithm is:
    # - At each event time:
    #   1. Release all tasks that have completed (end <= current_time)
    #   2. Scan all tasks in id order: for each task that has all deps completed and is not started:
    #      - If available resources >= units, start it (add to running, mark as started)
    #      - Else skip
    #   3. After scanning all tasks, if there are running tasks, advance to the earliest end time among running tasks
    #   4. If no running tasks and all tasks are started/completed, we're done
    
    # Let me implement this:
    
    all_ids = sorted(task_map.keys())
    
    while True:
        # Step 1: Release completed tasks
        to_remove = []
        for tid in running:
            if running[tid][1] <= current_time:
                to_remove.append(tid)
        for tid in to_remove:
            del running[tid]
            completed.add(tid)
        
        # Check if all tasks are completed
        if len(completed) == len(task_map):
            break
        
        # Step 2: Scan tasks in id order, try to start
        # Calculate current available resources
        used = sum(running[tid][2] for tid in running)
        available = capacity - used
        
        for tid in all_ids:
            if tid in started:
                continue
            t = task_map[tid]
            # Check if all deps are completed
            if all(d in completed for d in t["deps"]):
                if t["units"] <= available:
                    # Start the task
                    start_time = current_time
                    end_time = start_time + t["duration"]
                    running[tid] = (start_time, end_time, t["units"])
                    started.add(tid)
                    available -= t["units"]
        
        # Step 3: If no running tasks, but there are still tasks to start, something is wrong
        # (shouldn't happen if no circular deps and all deps are valid)
        if not running:
            # Check if there are tasks that can't be started due to unmet deps
            # This would indicate a problem, but we already checked for circular deps
            # Actually, if no running tasks and not all completed, it means some tasks have unmet deps
            # but those deps are not completed and not running - this shouldn't happen
            # Let's just break to avoid infinite loop
            break
        
        # Step 4: Advance to earliest end time
        min_end = min(running[tid][1] for tid in running)
        current_time = min_end
    
    # Build result
    jobs = []
    makespan = 0
    for tid in all_ids:
        if tid in running:
            start, end, _ = running[tid]
        else:
            # Task was completed, we need to find its start and end
            # We didn't store completed task info, let me fix this
            pass
    
    # I need to store the start and end times for all tasks. Let me redo this.
    
    # Let me restart with a cleaner implementation.
    
    # Actually, let me just rewrite the whole function properly.
    
    # I'll collect job info as we go.
    
    # Let me redo:
    
    completed = set()
    running = {}  # tid -> (start, end, units)
    started = set()
    current_time = 0
    job_info = {}  # tid -> (start, end)
    
    all_ids = sorted(task_map.keys())
    
    while True:
        # Step 1: Release completed tasks
        to_remove = []
        for tid in running:
            if running[tid][1] <= current_time:
                to_remove.append(tid)
        for tid in to_remove:
            start, end, _ = running[tid]
            job_info[tid] = (start, end)
            del running[tid]
            completed.add(tid)
        
        # Check if all tasks are completed
        if len(completed) == len(task_map):
            break
        
        # Step 2: Scan tasks in id order, try to start
        used = sum(running[tid][2] for tid in running)
        available = capacity - used
        
        for tid in all_ids:
            if tid in started:
                continue
            t = task_map[tid]
            if all(d in completed for d in t["deps"]):
                if t["units"] <= available:
                    start_time = current_time
                    end_time = start_time + t["duration"]
                    running[tid] = (start_time, end_time, t["units"])
                    started.add(tid)
                    available -= t["units"]
        
        # Step 3: If no running tasks, break (shouldn't happen normally)
        if not running:
            break
        
        # Step 4: Advance to earliest end time
        min_end = min(running[tid][1] for tid in running)
        current_time = min_end
    
    # Any remaining running tasks should be added to job_info
    for tid in running:
        start, end, _ = running[tid]
        job_info[tid] = (start, end)
    
    # Build result
    jobs = []
    makespan = 0
    for tid in all_ids:
        if tid in job_info:
            start, end = job_info[tid]
            jobs.append({"id": tid, "start": start, "end": end})
            if end > makespan:
                makespan = end
    
    return {"jobs": jobs, "makespan": makespan}
```