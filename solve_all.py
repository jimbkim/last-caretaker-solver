#!/usr/bin/env python3
"""One global allocation for the entire human set (40 committee + Star Child),
against real world scarcity. Output: global_plan.json read by webapp.py.

Usage: .venv/bin/python solve_all.py [time_limit_s]
"""
import json
import math
import os
import signal, sys, time
STATE_DIR = os.environ.get("SOLVER_STATE") or os.path.dirname(os.path.abspath(__file__))
def _state(n):
    return os.path.join(STATE_DIR, n)
import solver

def _die(*_):
    # cancelled by the web UI: never leave a half-written plan behind
    tmp = _state("global_plan.json.part")
    if os.path.exists(tmp):
        os.remove(tmp)
    sys.exit(130)
signal.signal(signal.SIGTERM, _die)

TL = int(sys.argv[1]) if len(sys.argv) > 1 else 600
INC_T = "--include-transposium" in sys.argv   # default: EXCLUDE the maze
def _arg_val(flag, default):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default
SPARE_PCT = int(_arg_val("--spare-pct", "0"))

memories = solver.memories_
avail = {i["name"]: i["avail"] for i in solver.foods_ + solver.memories_}
excl = set()
if not INC_T:
    excl = solver.transposium_only_memories()
    memories = [m for m in memories if m["name"] not in excl]
    for n in excl:
        avail[n] = 0
if excl:
    print("transposium EXCLUDED:", sorted(excl) or "none")
if SPARE_PCT:
    # hold back SPARE_PCT% of every memory so one missed loot point doesn't
    # sink the plan; count-1 memories (Oath Token) floor to 0 = unused, which
    # is exactly right — you can't keep a spare of a single unique item.
    world = {i["name"]: i["avail"] for i in solver.memories_}
    keep = {k: v for k, v in avail.items() if k not in world}   # foods
    for m in solver.memories_:
        keep[m["name"]] = (0 if m["name"] in excl else
                           math.floor(m["avail"] * (100 - SPARE_PCT) / 100))
    avail = keep
    dropped = sorted(k for k, v in avail.items()
                     if v == 0 and world.get(k, 0) > 0)
    print(f"spare margin {SPARE_PCT}%: plan usable counts capped;"
          f" fully dropped: {dropped or 'none'}")

warm = None
try:
    prev = json.load(open(_state("global_plan.json")))
    warm = prev
except Exception:
    try:
        warm = {p["profession"]: p["items"] for p in json.load(open(_state("plan.json")))
                if p["items"]}
    except Exception:
        warm = None
# a warm start that leans on excluded memories is infeasible — drop it
if warm and excl and any(isinstance(v, int) and v and k in excl
                         for items in warm.values() if isinstance(items, dict)
                         for k, v in items.items()):
    warm = None

t0 = time.time()
res = solver.solve_global(solver.humans_, solver.foods_, memories,
                          solver.humans_, avail, time_limit=TL, warm_start=warm)
print("elapsed", round(time.time() - t0), "s; solved:", res is not None)
if res:
    meta = res.pop("_meta", {})
    meta["transposium"] = bool(INC_T)
    meta["spare_pct"] = SPARE_PCT
    res["_meta"] = meta          # travels in the plan file: webapp honours the mode
    print("quality:", meta.get("status", "unknown"))
    # Star Child: no stat recipe — it consumes the Star Child memory itself
    # (quest reward, not from the item pool) plus one human seed.
    res["Star Child"] = {"_note": "insert the Star Child MEMORY (quest 'True Choices' "
                       "-> Courier Sieve Node Facility 169,-2). No food/memories from "
                       "the shared pool; costs one Lazarus seed."}
    used = {}
    for h, items in res.items():
        for k, v in items.items():
            if isinstance(v, int):
                used[k] = used.get(k, 0) + v
    tight = [f"{i['name']} {used.get(i['name'],0)}/{i['avail']}"
             for i in solver.memories_ if used.get(i["name"], 0) >= i["avail"] and used.get(i["name"], 0)]
    print("memories FULLY consumed:", tight or "none")
    json.dump(res, open(_state("global_plan.json"), "w"), indent=1)
    print("wrote global_plan.json")
