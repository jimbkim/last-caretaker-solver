#!/usr/bin/env python3
"""Reserve list: which specific humans claim the zero-slack memories.
Reads global_plan.json if present (preferred), else plan.json.
Writes RESERVE.md and is also served by webapp.py /api/reserve."""
import json, os, re, sys
import solver
from webapp import reserve_data as webapp_reserve

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
    # ONE source of truth: webapp.reserve_data() applies the grown ledger
    # (frozen consumption counts as history, plan rows of grown humans are
    # skipped) exactly as the UI does.
    rows = webapp_reserve()
    lines = [
        "# RESERVE LIST", "",
        f"Source: `{src}` + `grown.json` — regenerate: `.venv/bin/python make_reserve.py`",
        "",
        "When you loot one of these, do NOT put it in the general stash.", ""]
    for r in rows:
        lines.append(f"## {r['name']}  (world: {r['world']} · plan: {r['plan']})")
        lines.append(f"**{r['verdict']}**")
        if r["where"]:
            lines.append(f"*Where:* {r['where']}")
        lines.append("")
        for human, c, done in r["claimers"]:
            t = re.search(r"T(\d+)", human)
            ttag = f"T{t.group(1)} " if t else ""
            base = human.replace(" T" + (t.group(1) if t else ""), "").strip() if t else human
            lines.append(f"- **{c:>2}×** → {ttag}{base}" + (" _(already grown)_" if done else ""))
        lines.append("")
    out = os.path.join(HERE, "RESERVE.md")
    open(out, "w").write("\n".join(lines))
    print(f"wrote {out} ({len(rows)} reserved memories, from {src})")

if __name__ == "__main__":
    main()
