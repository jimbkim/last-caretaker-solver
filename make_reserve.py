#!/usr/bin/env python3
"""Reserve list: which specific humans claim the zero-slack memories.
Reads global_plan.json if present (preferred), else plan.json.
Writes RESERVE.md and is also served by webapp.py /api/reserve."""
import json, os, re, sys
import solver
from webapp import MEMORY_NOTES, MEMORY_LOCATIONS

HERE = os.path.dirname(os.path.abspath(__file__))

def load_plan():
    for f in ("global_plan.json", "plan.json"):
        p = os.path.join(HERE, "data", "..", f)
        try:
            d = json.load(open(p))
            if f == "plan.json":
                d = {x["profession"]: x["items"] for x in d if x["items"]}
            return d, f
        except Exception:
            continue
    sys.exit("no plan file found")

def main():
    plan, src = load_plan()
    mem_avail = {m["name"]: m["avail"] for m in solver.memories_}
    used_by = {}   # memory -> [(human, count)]
    for human, items in plan.items():
        for k, v in items.items():
            if k in mem_avail and isinstance(v, int):
                used_by.setdefault(k, []).append((human, v))
    scarce = []
    for m, total in ((m, sum(c for _, c in hs)) for m, hs in used_by.items()):
        if total >= 0.6 * mem_avail[m]:   # >=60% of world supply goes to the plan
            scarce.append((mem_avail[m] - total, m, used_by[m]))
    scarce.sort()
    lines = [
        "# RESERVE LIST", "",
        f"Source: `{src}` — regenerate: `.venv/bin/python make_reserve.py`",
        "",
        "When you loot one of these, do NOT put it in the general stash.", ""]
    for slack, m, claimers in scarce:
        total = sum(c for _, c in claimers)
        if slack <= 0:
            verdict = "**ZERO SPARE — reserve every single one.**"
        elif slack <= 2:
            verdict = f"only {slack} spare in the world — treat as reserved."
        else:
            verdict = f"{slack} spare — reserve these {total}, extras can be general."
        lines.append(f"## {m}  (world: {mem_avail[m]} · plan: {total})")
        lines.append(f"{verdict}")
        note = MEMORY_NOTES.get(m) or MEMORY_LOCATIONS.get(m)
        if note:
            lines.append(f"*Where:* {note if isinstance(note, str) else ', '.join(note[:6])}")
        lines.append("")
        for human, c in sorted(claimers, key=lambda x: -x[1]):
            t = re.search(r"T(\d+)", human)
            ttag = f"T{t.group(1)} " if t else ""
            lines.append(f"- **{c:>2}×** → {ttag}{human.replace(' T'+(t.group(1) if t else ''),'').strip() if t else human}")
        lines.append("")
    out = os.path.join(HERE, "RESERVE.md")
    open(out, "w").write("\n".join(lines))
    print(f"wrote {out} ({len(scarce)} reserved memories, from {src})")

if __name__ == "__main__":
    main()
