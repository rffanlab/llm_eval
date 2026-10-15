```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}
    
    task_map = {}
    for t in tasks:
        tid = t["id"]
        task_map[tid] = {
            "duration": t["duration"],
            "units": t["units"],
            "deps": t["deps"]
        }
    
    for t in tasks:
        if t["units"] > capacity:
            raise ValueError(f"Task {t['id']} units {t['units']} exceeds capacity {capacity}")
    
    for t in tasks:
        for dep in t["deps"]:
            if dep not in task_map:
                raise ValueError(f"Unknown dependency {dep} for task {t['id']}")
    
    state = {tid: 0 for tid in task_map}
    def has_cycle(node):
        if state[node] == 1:
            return True
        if state[node] == 2:
            return False
        state[node] = 1
        for dep in task_map[node]["deps"]:
            if has_cycle(dep):
                return True
        state[node] = 2
        return False
    
    for tid in task_map:
        if state[tid] == 0:
            if has_cycle(tid):
                raise ValueError("Circular dependency detected")
    
    current_time = 0
    running = {}
    completed = set()
    started = set()
    available = capacity
    job_info = {}
    all_ids = sorted(task_map.keys())
    
    while len(started) < len(tasks):
        finished = [tid for tid, end in running.items() if end <= current_time]
        for tid in finished:
            del running[tid]
            completed.add(tid)
            available += task_map[tid]["units"]
        
        for tid in all_ids:
            if tid in started:
                continue
            if all(dep in completed for dep in task_map[tid]["deps"]):
                if available >= task_map[tid]["units"]:
                    started.add(tid)
                    end_time = current_time + task_map[tid]["duration"]
                    running[tid] = end_time
                    available -= task_map[tid]["units"]
                    job_info[tid] = (current_time, end_time)
        
        if not running:
            break
        
        current_time = min(running.values())
    
    jobs = []
    for tid in sorted(job_info.keys()):
        start, end = job_info[tid]
        jobs.append({"id": tid, "start": start, "end": end})
    
    makespan = max(end for _, end in job_info.values()) if job_info else 0
    
    return {"jobs": jobs, "makespan": makespan}
```