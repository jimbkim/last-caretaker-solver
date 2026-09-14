#!/usr/bin/env python3
"""One global allocation for the entire human set (40 committee + Star Child),
against real world scarcity. Output: global_plan.json read by webapp.py.

Usage: .venv/bin/python solve_all.py [time_limit_s]
"""
import json, os, signal, sys, time
import solver

def _die(*_):
    # cancelled by the web UI: never leave a half-written plan behind
    tmp = "global_plan.json.part"
    if os.path.exists(tmp):
        os.remove(tmp)
    sys.exit(130)
signal.signal(signal.SIGTERM, _die)

TL = int(sys.argv[1]) if len(sys.argv) > 1 else 600

avail = {i["name"]: i["avail"] for i in solver.foods_ + solver.memories_}

warm = None
try:
    prev = json.load(open("global_plan.json"))
    warm = prev
except Exception:
    try:
        warm = {p["profession"]: p["items"] for p in json.load(open("plan.json"))
                if p["items"]}
    except Exception:
        warm = None

t0 = time.time()
res = solver.solve_global(solver.humans_, solver.foods_, solver.memories_,
                          solver.humans_, avail, time_limit=TL, warm_start=warm)
print("elapsed", round(time.time() - t0), "s; solved:", res is not None)
if res:
    # Star Child: no stat recipe — it consumes the Star Child memory itself
    # (quest reward, not from the item pool) plus one human seed.
    res["Star Child"] = {"_note": "insert the Star Child MEMORY (quest 'True Choices' "
                       "-> Courier Sieve Node Facility 169,-2). No food/memories from "
                       "the shared pool; costs one Lazarus seed."}
    used = {}
    for h, items in res.items():
        for k, v in items.items():
            used[k] = used.get(k, 0) + v
    tight = [f"{i['name']} {used.get(i['name'],0)}/{i['avail']}"
             for i in solver.memories_ if used.get(i["name"], 0) >= i["avail"] and used.get(i["name"], 0)]
    print("memories FULLY consumed:", tight or "none")
    json.dump(res, open("global_plan.json", "w"), indent=1)
    print("wrote global_plan.json")
