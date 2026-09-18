#!/usr/bin/env python3
"""Max spare margin at which the GLOBAL plan stays feasible, per mode.
Joint ILP (solve_global), not per-human proxy. Scans down in 5% steps
from each mode's cap; first feasible = the maximum (slack is monotone).
Never writes global_plan.json."""
import math, sys, time
import solver

TL = 240  # per-probe ILP cap; time-limit incumbents count as feasible

def probe(include_t, pct):
    memories = solver.memories_
    avail = {i["name"]: i["avail"] for i in solver.foods_ + solver.memories_}
    excl = set()
    if not include_t:
        excl = solver.transposium_only_memories()
        memories = [m for m in memories if m["name"] not in excl]
    world = {i["name"]: i["avail"] for i in solver.memories_}
    capped = {k: v for k, v in avail.items() if k not in world}   # foods
    for m in solver.memories_:
        capped[m["name"]] = (0 if m["name"] in excl else
                             math.floor(m["avail"] * (100 - pct) / 100))
    avail = capped
    t0 = time.time()
    res = solver.solve_global(solver.humans_, solver.foods_, memories,
                              solver.humans_, avail, time_limit=TL)
    el = round(time.time() - t0)
    if res is None:
        return False, el
    res.pop("_meta", None)
    empty = [t["name"] for t in solver.humans_ if not res.get(t["name"])]
    return (not empty), el

def scan(include_t, start):
    mode = "WITH transposium" if include_t else "NO transposium"
    for pct in range(start, 4, -5):
        ok, el = probe(include_t, pct)
        print(f"[{mode}] spare {pct}%: {'FEASIBLE' if ok else 'infeasible'} ({el}s)",
              flush=True)
        if ok:
            print(f"[{mode}] MAX spare margin = {pct}%", flush=True)
            return pct
    print(f"[{mode}] no feasible margin above 5% found", flush=True)
    return None

# no-T cap: individual boundary is 70 (Guardian of Humanity breaks at 80)
scan(False, 70)
# with-T cap: start at the same 70; if feasible, push above
r = scan(True, 70)
if r == 70:
    # probe upward: 75, 80... until infeasible; last feasible is the max
    mode = "WITH transposium"
    last = 70
    for pct in range(75, 96, 5):
        ok, el = probe(True, pct)
        print(f"[{mode}] spare {pct}%: {'FEASIBLE' if ok else 'infeasible'} ({el}s)",
              flush=True)
        if not ok:
            break
        last = pct
    print(f"[{mode}] MAX spare margin = {last}%", flush=True)
