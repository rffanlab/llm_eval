```python
def schedule(tasks, capacity):
    if not isinstance(tasks, list):
        raise ValueError
    if not isinstance(capacity, int) or capacity <= 0:
        raise ValueError

    ids = set()
    info = {}
    for t in tasks:
        if not isinstance(t, dict):
            raise ValueError
        tid = t.get("id")
        dur = t.get("duration")
        units = t.get("units")
        deps = t.get("deps")
        if not isinstance(tid, str) or not tid:
            raise ValueError
        if not isinstance(dur, int) or dur <= 0:
            raise ValueError
        if not isinstance(units, int) or units <= 0:
            raise ValueError
        if not isinstance(deps, list):
            raise ValueError
        if tid in ids:
            raise ValueError
        ids.add(tid)
        info[tid] = {"duration": dur, "units": units, "deps": list(deps)}

    for tid in ids:
        for d in info[tid]["deps"]:
            if not isinstance(d, str) or d not in ids:
                raise ValueError
        if info[tid]["units"] > capacity:
            raise ValueError

    indeg = {tid: 0 for tid in ids}
    children = {tid: [] for tid in ids}
    for tid in ids:
        for d in info[tid]["deps"]:
            indeg[tid] += 1
            children[d].append(tid)

    def has_cycle():
        state = {tid: 0 for tid in ids}
        def dfs(u):
            if state[u] == 1:
                return True
            state[u] = 1
            for v in children[u]:
                if dfs(v):
                    return True
            state[u] = 2
            return False
        for u in sorted(ids):
            if state[u] == 0 and dfs(u):
                return True
        return False

    if has_cycle():
        raise ValueError

    remaining = set(ids)
    finished = set()
    running = {}
    used = 0
    t = 0
    jobs = []

    while remaining or running:
        while finished:
            for tid in sorted(finished):
                used -= info[tid]["units"]
                jobs.append({"id": tid, "start": t, "end": t})
            finished.clear()

        for tid in sorted(remaining):
            if all(d in finished for d in info[tid]["deps"]):
                if used + info[tid]["units"] <= capacity:
                    used += info[tid]["units"]
                    running[tid] = t + info[tid]["duration"]
                    remaining.remove(tid)

        if running:
            t = min(running.values())
            for tid in list(running):
                if running[tid] == t:
                    finished.add(tid)
                    del running[tid]

    return {"jobs": sorted(jobs, key=lambda x: x["id"]), "makespan": t}
```