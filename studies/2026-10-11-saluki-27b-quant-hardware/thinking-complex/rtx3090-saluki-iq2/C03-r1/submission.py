```python
def schedule(tasks, capacity):
    if not tasks:
        return {"jobs": [], "makespan": 0}

    task_map = {}
    for t in tasks:
        tid = t["id"]
        if tid in task_map:
            raise ValueError("duplicate id")
        task_map[tid] = t

    for t in tasks:
        tid = t["id"]
        dur = t["duration"]
        units = t["units"]
        deps = t["deps"]
        if not isinstance(dur, int) or dur <= 0:
            raise ValueError("invalid duration")
        if not isinstance(units, int) or units <= 0:
            raise ValueError("invalid units")
        if units > capacity:
            raise ValueError("units > capacity")
        for d in deps:
            if d not in task_map:
                raise ValueError("unknown dependency")

    indeg = {tid: 0 for tid in task_map}
    children = {tid: [] for tid in task_map}
    for t in tasks:
        tid = t["id"]
        for d in t["deps"]:
            indeg[tid] += 1
            children[d].append(tid)

    # Kahn's algorithm to detect cycles
    from collections import deque  # not allowed? We'll avoid import.
    # Actually, we cannot import. Let's use a list as queue.
    queue = [tid for tid in task_map if indeg[tid] == 0]
    visited = set()
    order = []
    while queue:
        tid = queue.pop(0)
        if tid in visited:
            continue
        visited.add(tid)
        order.append(tid)
        for ch in children[tid]:
            indeg[ch] -= 1
            if indeg[ch] == 0:
                queue.append(ch)
    if len(order) != len(task_map):
        raise ValueError("circular dependency")

    # Simulate
    # State:
    # running: list of (end_time, units, id)
    # completed: set of ids
    # not_started: set of ids
    # current_time: int
    # jobs: list of dicts
    # total_units_used: int

    running = []  # list of [end, units, id]
    completed = set()
    not_started = set(task_map.keys())
    current_time = 0
    jobs = []
    total_units = 0

    # We need to process events. At each event time:
    # 1. Release all completed tasks (those with end == current_time)
    # 2. From all tasks whose deps are all in completed and not in not_started... wait, not in running either.
    #    Actually, a task is "available" if all its deps are completed and it hasn't started.
    #    We scan by id lexicographically.
    # 3. If resources enough, start it.
    # 4. After scanning, if no task started, advance to earliest running end.

    # But we need to be careful: at time 0, no tasks are running, completed is empty.
    # We need to find tasks with no deps (indeg 0 originally, but deps must be completed).
    # Since completed is empty, only tasks with no deps are available.

    # Let's precompute deps for each task.
    deps_map = {tid: t["deps"] for t in tasks}
    dur_map = {tid: t["duration"] for t in tasks}
    units_map = {tid: t["units"] for t in tasks}

    # We'll use a loop. To avoid infinite loop, we track time.
    # Since all durations are positive integers, time strictly increases when we advance.
    # When we start a task, time doesn't change but we add to running.
    # We need to ensure progress.

    # Let's use a while loop with a flag.
    # Actually, we can process as follows:
    # At each step, we are at some time t.
    # First, release all tasks with end == t.
    # Then, scan available tasks by id.
    # If we start any task, we stay at time t (since we can start multiple tasks at same time if resources allow).
    # Wait, the problem says: "from all tasks whose deps are completed and not started, scan by id lexicographically: if resources enough, start immediately; if not, skip and continue scanning."
    # This means at a given time, we might start multiple tasks. After scanning all, if we started at least one, we stay at the same time? 
    # No, we start them at the current time. Their end times are current_time + duration.
    # Then we need to advance to the next event time, which is the earliest end among running tasks.
    # But wait, could there be more tasks that become available at the same time? No, because we just released tasks at time t, and we started some tasks at time t. The newly started tasks have end > t. The tasks that were already running have end >= t (some might be t, but we released them). So the next event time is min(end of running tasks).
    # However, what if after starting some tasks, there are still available tasks that we didn't start because resources were full? They remain not started. They will be considered again at the next event time.
    # So the algorithm is:
    # while not_started or running:
    #   release all tasks with end == current_time
    #   scan available tasks (deps in completed, id in not_started) by id
    #   for each, if total_units + units <= capacity: start it, add to running, remove from not_started, add to jobs, total_units += units
    #   if no task started:
    #       if running: current_time = min(end for running)
    #       else: break (should not happen if not_started is empty and running is empty)
    #   else:
    #       # We started some tasks. But we might have started tasks that end at current_time? No, duration > 0, so end > current_time.
    #       # So we stay at current_time? No, we need to advance to the next event time.
    #       # Wait, the problem says: "After scanning all, advance to the earliest running task's end."
    #       # This implies that after the scan, we always advance to the earliest running end, regardless of whether we started tasks or not?
    #       # Let's re-read: "After scanning all, advance to the earliest running task's end."
    #       # This suggests that the scan happens at a time, and then we advance. But if we started tasks, their end is current_time + duration > current_time. The earliest running end could be from previously running tasks or newly started ones.
    #       # Actually, I think the intended algorithm is:
    #       # At each time t:
    #       #   1. Release tasks ending at t.
    #       #   2. Scan available tasks, start as many as possible.
    #       #   3. If running is not empty, set t = min(end of running).
    #       #   4. If running is empty and not_started is not empty, this is a deadlock (should not happen if no cycles).
    #       #   5. If running is empty and not_started is empty, done.
    #       # But wait, if we start tasks at time t, and there are no other running tasks, then the next time is t + min(duration of started tasks).
    #       # If we start tasks and there are already running tasks, the next time is min(existing running ends, new ends).
    #       # So the step 3 is correct: after scanning, advance to earliest running end.
    #       # But what if we didn't start any task and running is not empty? We still advance to earliest running end.
    #       # What if we didn't start any task and running is empty? Then we must have not_started non-empty, which means deadlock. But we already checked for cycles, so this shouldn't happen. Actually, it could happen if there's a task with deps that are never completed? No, because we check for cycles. If no cycles, all tasks will eventually be completed.
    #       # So the loop should be:
    #       while not_started or running:
    #           # release
    #           # scan and start
    #           # if running:
    #               current_time = min(end for end, units, id in running)
    #           else:
    #               # no running, but not_started non-empty -> error (should not happen)
    #               raise ValueError("deadlock")
    #           # But wait, if we started tasks, we should not advance immediately if there are more available tasks that can be started at the same time? 
    #           # No, because we already scanned all available tasks at this time. The newly started tasks have end > current_time, so they are not available at current_time.
    #           # So we advance to the next event time.
    #           # However, consider this: at time t, we start task A (duration 10) and task B (duration 5). The next event time is t+5 (B ends). At t+5, we release B, and then scan available tasks. Task A is still running.
    #           # This is correct.
    #           # But what if at time t, we start task A (duration 10), and there is task C that depends on A. C is not available at time t. At time t+10, A ends, C becomes available.
    #           # This is correct.
    #           # So the algorithm is sound.
    #           # However, there's a subtlety: when we advance to the earliest running end, we might skip over times where no event happens. That's fine.
    #           # But we must ensure that we don't miss tasks that become available at the same time as we advance. 
    #           # Example: At time t, running has task A ending at t+5. We start task B (duration 3) at time t. So running now has A (end t+5) and B (end t+3). Next time is t+3. At t+3, B ends. We release B. Then scan available tasks. A is still running.
    #           # This is correct.
    #           # Another example: At time t, running has task A ending at t+5. We start task B (duration 5) at time t. So running has A (end t+5) and B (end t+5). Next time is t+5. At t+5, both A and B end. We release both. Then scan available tasks.
    #           # This is correct.
    #           # So the algorithm is:
    #           while not_started or running:
    #               # Release all tasks with end == current_time
    #               to_release = [task for task in running if task[0] == current_time]
    #               for task in to_release:
    #                   running.remove(task)
    #                   completed.add(task[2])
    #                   total_units -= task[1]
    #               # Scan available tasks
    #               available = [tid for tid in not_started if all(d in completed for d in deps_map[tid])]
    #               available.sort()
    #               started_any = False
    #               for tid in available:
    #                   if total_units + units_map[tid] <= capacity:
    #                       start_time = current_time
    #                       end_time = start_time + dur_map[tid]
    #                       running.append([end_time, units_map[tid], tid])
    #                       not_started.remove(tid)
    #                       jobs.append({"id": tid, "start": start_time, "end": end_time})
    #                       total_units += units_map[tid]
    #                       started_any = True
    #               # Advance
    #               if running:
    #                   current_time = min(end for end, units, id in running)
    #               else:
    #                   # No running tasks. If not_started is not empty, it's a deadlock.
    #                   if not_started:
    #                       raise ValueError("deadlock")
    #                   break
    #           # But wait, if we started tasks, we should not advance if there are more tasks that can be started at the same time? 
    #           # No, because we already scanned all available tasks at this time. The newly started tasks have end > current_time, so they are not available at current_time.
    #           # So we advance to the next event time.
    #           # However, consider this: at time t, we start task A (duration 10). There is task B that depends on A. B is not available at time t. At time t+10, A ends, B becomes available.
    #           # This is correct.
    #           # But what if at time t, we start task A (duration 10), and there is task C that has no deps and can be started at time t, but we didn't start it because resources were full? 
    #           # Then at time t, we start A, and C is still not started. At time t+10, A ends, and C becomes available (if it was not started before). We start C at time t+10.
    #           # This is correct.
    #           # So the algorithm is correct.
    #           # However, there's a potential issue: when we advance to the earliest running end, we might have multiple tasks ending at that time. We release all of them.
    #           # This is handled by the release step.
    #           # Also, when we scan available tasks, we sort by id. This is required.
    #           # Let's test with a simple case.
    #           # tasks = [{"id": "A", "duration": 5, "units": 1, "deps": []}, {"id": "B", "duration": 5, "units": 1, "deps": []}]
    #           # capacity = 2
    #           # At time 0: release none. available = ["A", "B"]. Start A (total_units=1), start B (total_units=2). running = [(5,1,"A"), (5,1,"B")]. current_time = 5.
    #           # At time 5: release A and B. completed = {"A","B"}. not_started = empty. running = empty. break.
    #           # jobs = [{"id":"A","start":0,"end":5}, {"id":"B","start":0,"end":5}]. makespan = 5.
    #           # Correct.
    #           # Another case: capacity = 1.
    #           # At time 0: available = ["A","B"]. Start A (total_units=1). B cannot be started. running = [(5,1,"A")]. current_time = 5.
    #           # At time 5: release A. completed = {"A"}. not_started = {"B"}. available = ["B"]. Start B (total_units=1). running = [(10,1,"B")]. current_time = 10.
    #           # At time 10: release B. completed = {"A","B"}. not_started = empty. running = empty. break.
    #           # jobs = [{"id":"A","start":0,"end":5}, {"id":"B","start":5,"end":10}]. makespan = 10.
    #           # Correct.
    #           # Now, the problem says: "After scanning all, advance to the earliest running task's end."
    #           # In the above, after scanning at time 0, we advanced to 5. After scanning at time 5, we advanced to 10.
    #           # This matches.
    #           # But what if after scanning, we started no tasks and running is not empty? We still advance to the earliest running end.
    #           # Example: capacity = 1. tasks = [{"id":"A","duration":5,"units":1,"deps":[]}, {"id":"B","duration":5,"units":1,"deps":["A"]}]
    #           # At time 0: available = ["A"]. Start A. running = [(5,1,"A")]. current_time = 5.
    #           # At time 5: release A. completed = {"A"}. not_started = {"B"}. available = ["B"]. Start B. running = [(10,1,"B")]. current_time = 10.
    #           # At time 10: release B. break.
    #           # Correct.
    #           # Now, consider a case where after scanning, we started no tasks and running is not empty, but there are available tasks that cannot be started due to resources.
    #           # Example: capacity = 2. tasks = [{"id":"A","duration":5,"units":2,"deps":[]}, {"id":"B","duration":5,"units":1,"deps":[]}]
    #           # At time 0: available = ["A","B"]. Start A (total_units=2). B cannot be started (2+1>2). running = [(5,2,"A")]. current_time = 5.
    #           # At time 5: release A. completed = {"A"}. not_started = {"B"}. available = ["B"]. Start B (total_units=1). running = [(10,1,"B")]. current_time = 10.
    #           # At time 10: release B. break.
    #           # jobs = [{"id":"A","start":0,"end":5}, {"id":"B","start":5,"end":10}]. makespan = 10.
    #           # Correct.
    #           # Now, consider a case where after scanning, we started no tasks and running is empty, but not_started is not empty. This should not happen if no cycles.
    #           # Example: tasks = [{"id":"A","duration":5,"units":1,"deps":["B"]}, {"id":"B","duration":5,"units":1,"deps":["A"]}] -> cycle, detected earlier.
    #           # So we are safe.
    #           # However, there's a subtle bug: when we advance to the earliest running end, we might have multiple tasks ending at that time. We release all of them in the next iteration.
    #           # This is correct.
    #           # But what if we start a task with duration 0? The problem says duration is a positive integer, so duration >= 1.
    #           # So end > start.
    #           # Now, let's consider the case where we start multiple tasks at the same time, and some of them have the same end time.
    #           # Example: capacity = 2. tasks = [{"id":"A","duration":5,"units":1,"deps":[]}, {"id":"B","duration":5,"units":1,"deps":[]}]
    #           # At time 0: start A and B. running = [(5,1,"A"), (5,1,"B")]. current_time = 5.
    #           # At time 5: release A and B. break.
    #           # Correct.
    #           # Now, let's consider the case where we start a task, and then at the same time, another task becomes available? 
    #           # No, because a task becomes available only when its deps are completed. Completing a task happens at its end time, which is > current_time.
    #           # So no new tasks become available at the same time we start tasks.
    #           # Therefore, the algorithm is correct.
    #           # However, we must be careful with the order of operations:
    #           # 1. Release tasks ending at current_time.
    #           # 2. Scan available tasks and start as many as possible.
    #           # 3. Advance to earliest running end.
    #           # This order is important. If we advanced before releasing, we might miss tasks that become available at current_time.
    #           # So the order is correct.
    #           # Now, let's implement this.
    #           # But wait, the problem says: "At each event time, first release all completed tasks, then from all tasks whose deps are completed and not started, scan by id lexicographically: if resources enough, start immediately; if not, skip and continue scanning."
    #           # "After scanning all, advance to the earliest running task's end."
    #           # This matches our algorithm.
    #           # However, there's a potential issue: when we advance to the earliest running end, we might skip over times where no event happens. That's fine.
    #           # But we must ensure that we don't miss tasks that become available at the same time as we advance. 
    #           # Example: At time t, running has task A ending at t+5. We start task B (duration 3) at time t. So running now has A (end t+5) and B (end t+3). Next time is t+3. At t+3, B ends. We release B. Then scan available tasks. A is still running.
    #           # This is correct.
    #           # Another example: At time t, running has task A ending at t+5. We start task B (duration 5) at time t. So running has A (end t+5) and B (end t+5). Next time is t+5. At t+5, both A and B end. We release both. Then scan available tasks.
    #           # This is correct.
    #           # So the algorithm is sound.
    #           # Let's code it.

    # Initialize
    running = []  # list of [end_time, units, id]
    completed = set()
    not_started = set(task_map.keys())
    current_time = 0
    jobs = []
    total_units = 0

    while not_started or running:
        # Step 1: Release all tasks with end == current_time
        to_release = []
        for task in running:
            if task[0] == current_time:
                to_release.append(task)
        for task in to_release:
            running.remove(task)
            completed.add(task[2])
            total_units -= task[1]

        # Step 2: Scan available tasks by id
        available = []
        for tid in not_started:
            if all(d in completed for d in deps_map[tid]):
                available.append(tid)
        available.sort()

        started_any = False
        for tid in available:
            if total_units + units_map[tid] <= capacity:
                start_time = current_time
                end_time = start_time + dur_map[tid]
                running.append([end_time, units_map[tid], tid])
                not_started.remove(tid)
                jobs.append({"id": tid, "start": start_time, "end": end_time})
                total_units += units_map[tid]
                started_any = True

        # Step 3: Advance to earliest running end
        if running:
            current_time = min(end for end, units, id in running)
        else:
            # No running tasks. If not_started is not empty, it's a deadlock.
            if not_started:
                raise ValueError("deadlock")
            break

    # Sort jobs by id
    jobs.sort(key=lambda x: x["id"])
    makespan = max(job["end"] for job in jobs) if jobs else 0
    return {"jobs": jobs, "makespan": makespan}
```