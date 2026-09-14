#!/usr/bin/env python3
"""The Last Caretaker — human growth solver.

Answers three kinds of questions:
  1. "What exact food+memory combo grows profession X with minimal risk?"
  2. "If I spend my precious item (Ash Notebook, Oath Token, Ultimate Genesis)
     on this combo, what professions could the pod possibly come out as?"
  3. "Give me a full plan to fill all 10 committees, respecting how many of
     each item actually exist in the world."

Model (from thelaskcaretaker.wiki.gg + Root-DE/LastCaretaker data):
  - 15 stats. Foods give physical (weight,height,life_exp,strength,intellect);
    memories give the 10 mental stats. Totals are summed over all items used.
  - A profession is "satisfied" if every one of its stat requirements is met.
  - When several professions match, the game picks one, favoring higher tiers.
    The exact rule is contested -> we minimise collateral matches, weighted so
    same-tier and higher-tier collateral counts worst.
  - Attribute decay: once a raw stat exceeds 200, further points decay (wiki
    table). Modelled as per-addition decay (cap each item's contribution to
    floor(f(raw_total)) - raw_total_before). This is conservative (undercounts
    what the game might give) so plans stay feasible either way.

Usage:
  solver.py targets                       # list the 40 committee professions
  solver.py solve "Quantum Engineer"      # best combo for one profession
  solver.py combo --food A,B --memory X,Y # evaluate a chosen combo
  solver.py plan                          # whole-committee plan (scarcity-aware)
  solver.py scarcity                      # what the world-counts tell us
"""
import argparse, csv, itertools, json, math, os, sys
from collections import defaultdict

import pulp

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

STATS = ["weight", "height", "life_exp", "strength", "intellect",
         "adaptability", "creativity", "communication", "discipline",
         "empathy", "focus", "leadership", "logic", "patience", "wisdom"]
SI = {s: i for i, s in enumerate(STATS)}
FOOD_STATS = ["weight", "height", "life_exp", "strength", "intellect"]
MEM_STATS = [s for s in STATS if s not in FOOD_STATS]
# CSV headers are display names; map stat -> header used in humans/food CSVs
HEADER = {"weight": "Weight", "height": "Height", "life_exp": "Life Exp",
          "strength": "Strength", "intellect": "Intellect",
          "adaptability": "Adaptability", "creativity": "Creativity",
          "communication": "Communication", "discipline": "Discipline",
          "empathy": "Empathy", "focus": "Focus", "leadership": "Leadership",
          "logic": "Logic", "patience": "Patience", "wisdom": "Wisdom"}

# Wiki decay table: raw added beyond 200 is worth effective[n-200] per wiki.
DECAY_TABLE = {1:1,2:2,3:2,4:2,5:3,6:3,7:3,8:3,9:4,10:4,11:4,12:4,13:5,14:5,
               15:5,16:5,17:5,18:5,19:6,20:6,21:6,22:6,23:7,24:7,25:7,26:7,
               27:7,28:7,29:8,30:8,31:8,32:8,33:8,34:8,35:8,36:9,37:9,38:9,
               39:9,40:9,41:9,42:9,43:10,44:10,45:10,46:10,47:10,48:10,49:10,
               50:10,51:11,52:11,53:11,54:11,55:11,56:11,57:11,58:11,59:12,
               60:12,61:12,62:12,63:12,64:12,65:12,66:12,67:12,68:13,69:13,
               70:13,71:13,72:13,73:13,74:13,75:13,76:13,77:14,78:14,79:14,
               80:14,81:14,82:14,83:14,84:14,85:14,86:14,87:15,88:15,89:15,
               90:15,91:15,92:15,93:15,94:15,95:15,96:15,97:16,98:16,99:16,
               100:16,101:16,102:16,103:16,104:16,105:16,106:16,107:17,108:17,
               109:17,110:17,111:17,112:17,113:17,114:17,115:17,116:17,117:17,
               118:18,119:18,120:18,121:18,122:18,123:18,124:18,125:18,126:18,
               127:18,128:18,129:18,130:19,131:19,132:19,133:19,134:19,135:19,
               136:19,137:19,138:19,139:19,140:19,141:19,142:20}

def eff_marginal(raw_total_before, added):
    """Effective gain from adding `added` to a stat already at raw_total_before,
    using per-addition decay (conservative reading of the wiki rule)."""
    if raw_total_before + added <= 200:
        return added
    total = 0.0
    cur = raw_total_before
    left = added
    while left > 0:
        step = min(left, DECAY_TABLE.get(1, 1) if cur < 200 else
                   DECAY_TABLE.get(min(int(cur) - 199, max(DECAY_TABLE)), 20))
        # one raw point at a time is fine here; stat totals are <= a few hundred
        if cur < 200:
            cur += 1
        else:
            cur += 1
            total += DECAY_TABLE.get(min(int(cur) - 200, max(DECAY_TABLE)), 20) - 0
        left -= 1
        if left > 0 and cur >= 200:
            n = min(int(cur) - 200, max(DECAY_TABLE))
            # remaining points at current marginal rate, batch it
            marginal = DECAY_TABLE.get(n, 20)
            batch = min(left, max(1, int(left)))
            total += min(left, batch) * marginal / 1.0
            cur += batch
            left -= batch
    return total

def decay_effective(raw):
    """Wiki-table value of a raw stat total (cap of what the stat is worth)."""
    if raw <= 200:
        return raw
    return 200 + DECAY_TABLE.get(min(int(raw) - 200, max(DECAY_TABLE)), 20)

def tier(name):
    import re
    m = re.search(r" T(\d+)$", name)
    return int(m.group(1)) if m else 0

def load():
    foods, memories, humans = [], [], []
    with open(os.path.join(DATA, "food.csv"), newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            foods.append({"name": r["Food"],
                          "vec": [float(r.get(HEADER[s]) or 0) for s in FOOD_STATS],
                          "avail": int(float(r.get("TotalAvailability") or 0))})
    with open(os.path.join(DATA, "memories.csv"), newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            memories.append({"name": r["Memory"],
                             "vec": [float(r.get(HEADER[s]) or 0) for s in MEM_STATS],
                             "avail": int(float(r.get("WorldCount") or 0))})
    with open(os.path.join(DATA, "humans.csv"), newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            req = {s: float(r[HEADER[s]]) for s in STATS
                   if (r.get(HEADER[s]) or "").strip()}
            humans.append({"name": r["Profession"], "cat": r["Category"],
                           "req": req, "tier": tier(r["Profession"])})
    return foods, memories, humans

def stat_vec(item, kind):
    v = [0.0] * 15
    names = FOOD_STATS if kind == "food" else MEM_STATS
    for s, val in zip(names, item["vec"]):
        v[SI[s]] = val
    return v

def satisfied(totals, humans):
    out = []
    for h in humans:
        if all(totals[SI[s]] >= val for s, val in h["req"].items()):
            out.append(h)
    return out

# Collateral weights: what hurts. Same tier = coin flip. Higher tier (any cat)
# = the game may prefer it over your target. Lower tier = safe under either
# reading of the favoring rule, so it's nearly free.
def collat_weight(target, other):
    if other["name"] == target["name"]:
        return 0.0
    if other["tier"] == target["tier"]:
        return 100.0
    if other["tier"] > target["tier"]:
        return 50.0
    return 1.0

def solve_combo(target, foods, memories, humans, avail=None,
                item_penalty=1.0):
    """ILP: integer counts of each item s.t. target is satisfied, weighted
    collateral minimised, then item count minimised. Exact indicator for
    'profession h is matched' (totals are integers; shortfall <=> totals<=val-1).
    Returns (chosen, totals, matched) or None if infeasible."""
    items = ([("food", f) for f in foods] + [("mem", m) for m in memories])
    vecs = [stat_vec(it, kind) for kind, it in items]
    prob = pulp.LpProblem("grow", pulp.LpMinimize)
    x = [pulp.LpVariable(f"x{i}", lowBound=0, cat="Integer")
         for i in range(len(items))]
    if avail:
        for i, (kind, it) in enumerate(items):
            prob += x[i] <= avail.get(it["name"], it["avail"])
    totals = [pulp.lpSum(x[i] * vecs[i][s] for i in range(len(items)))
              for s in range(15)]
    for s, val in target["req"].items():
        prob += totals[SI[s]] >= val
    M = 1_000_000
    cost_terms = []
    for hi, h in enumerate(humans):
        if h["name"] == target["name"]:
            continue
        w = collat_weight(target, h)
        if w == 0:
            continue
        d = [pulp.LpVariable(f"d{hi}_{SI[s]}", cat="Binary") for s in h["req"]]
        z = pulp.LpVariable(f"z{hi}", cat="Binary")  # 1 = NOT matched
        for dd, (s, val) in zip(d, h["req"].items()):
            prob += totals[SI[s]] >= val - M * dd          # dd=0 -> satisfied
            prob += totals[SI[s]] <= val - 1 + M * (1 - dd)  # dd=1 -> short
            prob += z >= dd                                # any short -> z=1
        prob += z <= pulp.lpSum(d)                         # all satisfied -> z=0
        cost_terms.append(w * (1 - z))
    prob += pulp.lpSum(cost_terms) + item_penalty * pulp.lpSum(x)
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if prob.status != 1:
        return None
    counts = [int(round(v.value() or 0)) for v in x]
    totals_f = [0.0] * 15
    for i, c in enumerate(counts):
        for s in range(15):
            totals_f[s] += c * vecs[i][s]
    chosen = defaultdict(int)
    for i, c in enumerate(counts):
        if c:
            chosen[items[i][1]["name"]] = c
    return dict(chosen), totals_f, satisfied(totals_f, humans)

def fmt_totals(totals):
    return {STATS[s]: int(totals[s]) for s in range(15) if totals[s] > 0}

def cmd_targets(args):
    for h in humans_:
        print(f"T{h['tier']}  {h['name'][:-3]:32} [{h['cat']}]  req: "
              + ", ".join(f"{s}={v:g}" for s, v in h["req"].items()))

def find_target(name):
    cands = [h for h in humans_ if name.lower() in h["name"].lower()]
    if not cands:
        sys.exit(f"no profession matches {name!r}")
    if len(cands) > 1:
        for h in cands:
            print("  candidate:", h["name"], file=sys.stderr)
        sys.exit("ambiguous")
    return cands[0]

def cmd_solve(args):
    t = find_target(args.profession)
    res = solve_combo(t, foods_, memories_, humans_, avail=None,
                      item_penalty=args.item_penalty)
    if not res:
        sys.exit("infeasible")
    chosen, totals, matched = res
    print(f"TARGET: {t['name']}")
    print("ITEMS:")
    for k, v in sorted(chosen.items()):
        print(f"  {v:>3} x {k}")
    print("TOTALS:", fmt_totals(totals))
    print("PROFESSIONS SATISFIED (what the pod could come out as):")
    for h in sorted(matched, key=lambda h: -h["tier"]):
        flag = "  <-- target" if h["name"] == t["name"] else ""
        print(f"  T{h['tier']} {h['name']}{flag}")
    risky = [h for h in matched
             if collat_weight(t, h) >= 50]
    print(f"\nrisk: {len(risky)} same/higher-tier collateral "
          f"({'DANGER — the pod may pick one of these' if risky else 'safe: all collateral is lower-tier, game favors your target'})")

def cmd_combo(args):
    f_names = [f.strip() for f in (args.food or "").split(",") if f.strip()]
    m_names = [m.strip() for m in (args.memory or "").split(",") if m.strip()]
    totals = [0.0] * 15
    for name in f_names:
        it = next((f for f in foods_ if f["name"].lower() == name.lower()), None)
        if not it: sys.exit(f"unknown food {name!r}")
        v = stat_vec(it, "food")
        for s in range(15): totals[s] += v[s]
    for name in m_names:
        it = next((m for m in memories_ if m["name"].lower() == name.lower()), None)
        if not it: sys.exit(f"unknown memory {name!r}")
        v = stat_vec(it, "mem")
        for s in range(15): totals[s] += v[s]
    if args.decay:
        totals = [float(decay_effective(t)) for t in totals]
    print("TOTALS:", fmt_totals(totals))
    matched = satisfied(totals, humans_)
    print("SATISFIED:")
    for h in sorted(matched, key=lambda h: -h["tier"]):
        print(f"  T{h['tier']} {h['name']} [{h['cat']}]")
    if not matched:
        best = sorted(humans_, key=lambda h: -sum(
            min(1.0, totals[SI[s]]/v) for s, v in h["req"].items()))[:5]
        print("nothing satisfied; closest:")
        for h in best:
            gaps = {s: v - totals[SI[s]] for s, v in h["req"].items()
                    if totals[SI[s]] < v}
            print(f"  T{h['tier']} {h['name']}: short {gaps}")

def cmd_scarcity(args):
    print("=== rare foods (TotalAvailability) ===")
    for f in sorted(foods_, key=lambda f: f["avail"]):
        print(f"  {f['avail']:>4}  {f['name']}")
    print("=== rare memories (WorldCount; ~times findable in world) ===")
    for m in sorted(memories_, key=lambda m: m["avail"])[:15]:
        print(f"  {m['avail']:>4}  {m['name']}")

# Committees per wiki: the 10 committees need 40 distinct professions =
# every T1-T4 of all 10 categories.
def cmd_plan(args):
    inv = {}
    for f in foods_: inv[f["name"]] = args.cap * f["avail"] if args.cap else f["avail"]
    for m in memories_: inv[m["name"]] = args.cap * m["avail"] if args.cap else m["avail"]
    order = sorted(humans_, key=lambda h: (-h["tier"], h["cat"], h["name"]))
    plan = []
    for t in order:
        res = solve_combo(t, foods_, memories_, humans_, avail=inv)
        if not res:
            plan.append((t["name"], None, "INFEASIBLE with remaining stock"))
            continue
        chosen, totals, matched = res
        for k, v in chosen.items():
            inv[k] -= v
        risky = [h["name"] for h in matched if collat_weight(t, h) >= 50]
        plan.append((t["name"], chosen, risky))
    print("=== FULL COMMITTEE PLAN (grown highest-tier first) ===")
    for name, chosen, risky in plan:
        print(f"\n--- {name} ---")
        if chosen is None:
            print("  " + risky)
            continue
        for k, v in sorted(chosen.items(), key=lambda kv: -kv[1]):
            print(f"  {v:>3} x {k}")
        if risky:
            print(f"  !! same/higher-tier collateral: {', '.join(risky)}")
    print("\n=== remaining inventory ===")
    for k, v in sorted(inv.items(), key=lambda kv: kv[1]):
        if v <= 2:
            print(f"  {v:>5}  {k}")
    with open("plan.json", "w") as f:
        json.dump([{"profession": n, "items": c,
                    "collateral_risk": r if isinstance(r, list) else None}
                   for n, c, r in plan], f, indent=2)
    print("\nwrote plan.json")

p = argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter)
sub = p.add_subparsers(dest="cmd", required=True)
sub.add_parser("targets")
s = sub.add_parser("solve"); s.add_argument("profession"); s.add_argument("--item-penalty", type=float, default=1.0)
c = sub.add_parser("combo"); c.add_argument("--food"); c.add_argument("--memory"); c.add_argument("--decay", action="store_true")
sub.add_parser("scarcity")
pl = sub.add_parser("plan"); pl.add_argument("--cap", type=int, default=0,
    help="multiply world availability (e.g. re-run saves) to test plan depth")
foods_, memories_, humans_ = load()
args = p.parse_args()
{"targets": cmd_targets, "solve": cmd_solve, "combo": cmd_combo,
 "scarcity": cmd_scarcity, "plan": cmd_plan}[args.cmd](args)
