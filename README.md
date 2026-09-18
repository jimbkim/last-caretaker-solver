# The Last Caretaker — Human Recipe Solver

> *Independent fan-made tool. Not affiliated with, endorsed by, or sponsored by the creators or publishers of The Last Caretaker.*

A local web tool for [The Last Caretaker](https://store.steampowered.com/app/1783560/) that answers one question:

> **What exact memories and foods do I need to grow each committee human — and which of those items are so rare that I must not waste a single one?**

## What it does

Growing a human means feeding a seed a mix of **memories** and **crafted foods** whose stats add up to the profession's requirements. The catch: foods are renewable (craft from farmable organics), but **memories are fixed** — the world contains exactly N of each. Ash Notebooks exist exactly 10 times, total. Spend one on the wrong human and a T4 committee member is gone forever.

This tool:

- **Recipes for all 40 committee humans** — pick a committee, pick a human, get the exact item list.
- **Global allocation** — instead of solving each human alone (which happily spends all 10 Ash Notebooks twice), an ILP (integer linear program) allocates *all humans at once* against real world counts, and proves which items have **zero slack**.
- **Reserve list** — the items you should treat as sacred, which human each copy is saved for, and where to find them in the world.
- **Collateral safety** — for each recipe it tells you whether a *different* profession could match the same stats (SAFE / RISK), using the game's tier-favoring rule.
- **Transposium toggle** — off by default: recipes never require The Transposium (the Update 02 maze), so the plan works without visiting it. Check the box to let the solver use maze-only memories (Ash Notebook).
- **Spare margin** — tell the plan to use only (100−N)% of every memory's world count, so a missed loot point doesn't sink the whole allocation. The UI states the tested joint-plan limits: **≤20% without Transposium, up to 50% with it** — beyond that an all-40 allocation is mathematically infeasible (per-human recipes still exist at higher margins; only the global plan breaks). Verified with `margin_probe.py`.
- **Grown tracker** — as you grow humans in-game, `mark as GROWN ✓` freezes the exact recipe you followed (item counts + timestamp + solver mode) into `grown.json`, so later re-plans can never rewrite what was actually spent. Spent copies are subtracted from world supply in every later solve, the committee dots ring green as you progress, and the reserve list splits each rare memory into grown-history vs still-to-loot.

## Screenshots

Pick a committee (dots = each member's tier), then a human:

![committees](docs/shot_humans.png)

The recipe splits into **memories you must hunt** (fixed in the world) and **foods you just craft**. ★ marks reserve-list items — hover for why. Mental stats come from memories, physical from food:

![recipe](docs/shot_recipe.png)

The reserve tab: zero-slack items in red, click any for the human-by-human allocation:

![reserve](docs/shot_reserve.png)

## Quick start

**Docker:**

```bash
git clone https://github.com/jimbkim/last-caretaker-solver && cd last-caretaker-solver
docker build -t tlc . && docker run -p 8765:8765 -v tlc-state:/app/state tlc
```

**No Docker:**

```bash
python3 -m venv .venv
.venv/bin/pip install pulp          # the ILP solver (CBC ships with it)
.venv/bin/python webapp.py 0.0.0.0  # → http://localhost:8765
```

That's it. Everything runs locally — no accounts, no network calls, no telemetry. The web UI reads CSVs in `data/` (scraped from the community wiki) and serves a single-page app.

State lives in the run directory (or `$SOLVER_STATE` for Docker): `global_plan.json` is the cached global plan, `grown.json` is your grown-humans ledger. Back both up alongside your notes — they're your save-file.

**Full plan mode** (the checkbox) runs the global ILP in a subprocess — a few minutes on first run, results cached to `global_plan.json`. The cached plan remembers the mode it was built for (Transposium on/off, spare margin) — every recipe header says `Transposium included/EXCLUDED` alongside its source, the plan stamp shows the mode, and changing the mode marks the cached plan stale so re-calculating rebuilds it. Without full plan mode, recipes use a greedy plan that's still 40/40 feasible, just less optimal on rare items.

## How the solver works (one paragraph)

For each human, it picks a multiset of foods and memories minimizing a weighted cost of *items used, scarcity burned, and collateral risk*, subject to: stat sums ≥ requirements, at most one same-or-higher-tier profession matching (else the pod might grow into something else), and — in global mode — a hard cap that **no memory is used more times than exists in the world, across the entire plan**. CBC (bundled with `pulp`) solves it to proven optimality in minutes; if it times out it keeps the best found solution and says so.

## Known game facts it encodes

- Foods are **craftable** → effectively infinite. Memories are **fixed** (`WorldCount` = literal copies in the world).
- The game **favors higher tiers**: a T4 recipe is SAFE if every other profession its stats satisfy is lower-tier.
- Grow **rare first**: T4s consume the scarce memories; T1s can substitute commons.

## Files

| file | what |
|---|---|
| `webapp.py` | the whole web UI + API (stdlib `http.server`, no deps) |
| `solver.py` | the ILP model (PuLP/CBC) — also a CLI: `solve`, `combo`, `hunt` |
| `solve_all.py` | global all-humans solve (`--include-transposium`, `--spare-pct N`), writes `global_plan.json` |
| `margin_probe.py` | re-verifies the max feasible spare margin per mode (joint ILP scan) |
| `make_reserve.py` | renders `RESERVE.md` from the current plan |
| `data/*.csv` | foods, memories, humans (from the [wiki](https://thelastcaretaker.wiki.gg/)) |

## Releases

Versioned tags (`v1.0.0`, …); the web UI header shows the running version.

- **v1.1.0** — **Grown tracker**: 'mark as GROWN ✓' on any recipe freezes the exact item list + solve mode into `grown.json` (un-mark restores the items); grown humans show their frozen record, get a ✓ badge and a green ring on their committee dot, and their consumed copies are subtracted from world supply in every other solve, the reserve list, and RESERVE.md (which now renders from the same source as the UI, with grown-history vs future-need split). New `Grown ✓ N/41` tab. Spare-margin box now warns 'settings changed — press re-calculate' when it no longer matches the cached plan, and pre-fills from the plan's metadata.
- **v1.0.1** — "What would THIS grow?" chips now carry −/+ counts, so a full recipe (e.g. Ultimate Genesis ×3) replays exactly instead of matching nothing. Confirmed in-game: the growth-prediction list ranks by stat fit, but the pod still grows the highest-tier satisfied profession (tier-favoring rule holds).
- **v1.0.0** — recipes for all 40 committee humans, global ILP allocation, reserve list, collateral SAFE/RISK, Transposium toggle (off by default), spare-margin mode (≤20% w/o Transposium / 50% with), Docker image.

## Credits

Game data from the [Last Caretaker wiki](https://thelastcaretaker.wiki.gg/) and [Root-DE/LastCaretaker](https://github.com/Root-DE/LastCaretaker). Location and Oath Token details from community wiki/Reddit/Steam findings — the game is in active development, so treat in-game behavior as ground truth over this tool.

---

*Built with AI assistance (Hermes/Qwen). Game data scraped from the community wiki — accuracy follows the community, not an authority.*
