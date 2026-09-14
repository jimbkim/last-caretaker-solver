#!/usr/bin/env python3
"""Web UI for the Last Caretaker solver:  http://127.0.0.1:8765

Run:  .venv/bin/python webapp.py [host]   (stdlib only, no installs)

Flow: committees -> humans -> recipe for the human you pick.
"""
import json, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import solver

PORT = 8765

# From wiki /Committees — the four members of each of the 10 committees,
# with each committee's unlock tier.
COMMITTEES = [
    ("Deck Operations", 1, ["Maintenance Engineer", "Basic Supplier", "Nutrient Handler", "Door Jammer"]),
    ("Habitat Care", 1, ["Room Supervisor", "Health Assistant", "Teacher", "Lab Technician"]),
    ("Transit & Distribution", 1, ["Systems Engineer", "Distributor", "Growth Specialist", "Guard"]),
    ("Power & Security", 1, ["Energy Engineer", "Resource Director", "Station Quartermaster", "Station Protector"]),
    ("Cognitive Resilience", 2, ["Theoretical Scientist", "Neuro Specialist", "Professor", "Star Analyzer"]),
    ("Culture & Memory", 2, ["Visual Technician", "Sculptor", "Cultural Archivist", "Manual Holder"]),
    ("Governance & Logistics", 2, ["Settlement Governor", "Logistics High Command", "Biosphere Director", "Guardian of Humanity"]),
    ("Deep Systems", 3, ["Quantum Engineer", "Quantum Physicist", "Neural Architect", "Sustenance Architect"]),
    ("Meaning & Frontier", 3, ["Existential Expressionist", "Frontier Explorer", "Mission Seeker", "Colonel of Humanity"]),
    ("Field Continuance", 3, ["Field Research Scientist", "Existential Chancellor", "Station Roamer", "Doctor"]),
]

# Humans that exist outside the committee structure.
SPECIAL = [
    ("Star Child", "Special",
     "Grown by inserting the Star Child MEMORY itself (not a stat recipe).\n"
     "HOW TO GET IT: complete committee work until the quest 'True Choices' fires\n"
     "  (reported to unlock after Habitat Care is formed). It reveals a map marker:\n"
     "  Courier Sieve Node Facility, eastern map, coords 169,-2 (guarded by an\n"
     "  Arch Angel + Talon Shipshark). Grab the Star Child memory there.\n"
     "THE CHOICE: the grown Star Child can be DESTROYED or LAUNCHED — both close\n"
     "  the quest; players report different dialogue reactions. Decide on purpose.\n"
     "  Note: a Steam player found being 9 seeds short late-game painful, so grow\n"
     "  your committee humans BEFORE using the last seeds on this one."),
]

# Curated hunt notes for memories the wiki location-scrape can't answer.
MEMORY_NOTES = {
    "Ash Notebook": "ALL 10 are in the maze at The Transposium — one trip, no luck needed.",
    "Oath Token": "Not on the wiki yet. Community reports: unmarked mystery — scan the statue(s) to trigger it; NOT the 'Before the Archives' quest. Reportedly REUSABLE (survives growth).",
    "Star Child": "Quest 'True Choices' -> Courier Sieve Node Facility (169,-2), east map.",
    "Porcine Vocal Interface": "Helios Reserve Lyra.",
}

def _load_locations():
    import os, json
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "memory_locations.json")
    try:
        return json.load(open(p))
    except Exception:
        return {}

MEMORY_LOCATIONS = _load_locations()

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Last Caretaker — Human Lab</title>
<style>
:root{color-scheme:dark}
body{font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:#0b0e13;color:#c9d1d9;max-width:1080px;margin:1.5rem auto;padding:0 1rem}
h1{font-size:1.25rem;color:#e6edf3;margin-bottom:.2rem} h1 span{color:#7d8590;font-weight:normal}
.tabs{display:flex;gap:.5rem;margin:1rem 0;flex-wrap:wrap}
button.tab{background:#21262d;color:#c9d1d9;border:1px solid #30363d;padding:.45rem .9rem;border-radius:6px;cursor:pointer;font:inherit}
button.tab.on{background:#1f6feb;border-color:#1f6feb;color:#fff}
section{display:none} section.on{display:block}
.cols{display:grid;grid-template-columns:minmax(300px,1fr) minmax(420px,1.4fr);gap:1rem}
.cols2{display:grid;grid-template-columns:minmax(300px,1fr) minmax(360px,1.2fr);gap:1rem;align-items:start}
@media(max-width:820px){.cols,.cols2{grid-template-columns:1fr}}
.inputs{background:#10141b;border:1px solid #21262d;border-radius:10px;padding:1rem}
.lbl{color:#7d8590;font-size:.75rem;letter-spacing:.12em;margin-bottom:.45rem}
.sep{display:flex;align-items:center;gap:.8rem;margin:1.3rem 0 .8rem;color:#7d8590;font-size:.75rem;letter-spacing:.2em}
.sep::before,.sep::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,transparent,#30363d,transparent)}
.sep span{border:1px solid #30363d;border-radius:999px;padding:.15rem .9rem;background:#0d1117}
.panel{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:.7rem}
.committee{border:1px solid #30363d;border-radius:6px;padding:.5rem .7rem;margin-bottom:.45rem;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:.5rem}
.committee:hover{border-color:#1f6feb}
.committee.on{border-color:#1f6feb;background:#161b22}
.human{border:1px solid #30363d;border-radius:6px;padding:.4rem .7rem;margin-bottom:.4rem;cursor:pointer;display:flex;justify-content:space-between}
.human:hover{border-color:#f778ba}
.human.on{border-color:#f778ba;background:#161b22}
.req{color:#7d8590;font-size:.82em}
pre{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:.8rem;white-space:pre-wrap;overflow:auto;margin:0}
.tier4{color:#f778ba;font-weight:bold}.tier3{color:#a5d6ff}.tier2{color:#7ee787}.tier1{color:#7d8590}
.ok{color:#7ee787}.bad{color:#ff7b72}.warn{color:#f2cc60}
.small{color:#7d8590;font-size:.85em}
.chips{display:flex;flex-wrap:wrap;gap:.35rem;max-height:180px;overflow:auto;border:1px solid #30363d;padding:.5rem;border-radius:6px;background:#0d1117}
.chip{border:1px solid #30363d;border-radius:999px;padding:.1rem .6rem;cursor:pointer;user-select:none;background:#161b22}
.chip.sel{background:#1f6feb;border-color:#1f6feb;color:#fff}
.chip .ct{color:#7d8590;font-size:.8em}
.row{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-bottom:.8rem}
button.go{background:#238636;border:1px solid #2ea043;color:#fff;padding:.45rem 1rem;border-radius:6px;cursor:pointer;font:inherit}
input[type=number]{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:.4rem;width:4rem;border-radius:6px;font:inherit}
.breadcrumb{margin-bottom:.6rem;color:#7d8590}
.breadcrumb b{color:#e6edf3}
#recipe{min-height:10rem}
.legend{display:flex;flex-wrap:wrap;gap:.45rem;align-items:center;color:#7d8590;font-size:.8rem;margin:.2rem 0 .6rem}
.legend .dot{opacity:.5}
.dots{display:flex;align-items:center;gap:.3rem}
.dotc{display:inline-block;width:.65rem;height:.65rem;border-radius:50%}
.dotc.t1{background:#7d8590}.dotc.t2{background:#7ee787}.dotc.t3{background:#a5d6ff}.dotc.t4{background:#f778ba}
.smalltxt{font-size:.75rem;margin-left:.35rem}
.loc{color:#a5d6ff}
.committee.special{border-style:dashed}
</style></head><body>
<h1>THE LAST CARETAKER <span>· human lab</span></h1>
<div class="legend">
 <span><span class="tier1">T1</span> common</span><span class="dot">·</span>
 <span><span class="tier2">T2</span> skilled</span><span class="dot">·</span>
 <span><span class="tier3">T3</span> expert</span><span class="dot">·</span>
 <span><span class="tier4">T4</span> apex — rarest items</span><span class="dot">·</span>
 <span class="ok">SAFE</span> = no same-or-higher-tier match, target guaranteed<span class="dot">·</span>
 <span class="bad">RISK</span> = pod may come out as something else<span class="dot">·</span>
 <span class="warn">!!</span> = collateral to watch<span class="dot">·</span>
 <span>◆ = memory — only WorldCount exist, fixed</span><span class="dot">·</span>
 <span>↻ = food — renewable, craft from organics</span><span class="dot">·</span>
 <span class="loc">⌖ = where to find it</span>
</div>
<div class="tabs">
 <button class="tab on" data-s="tree">Committees → humans → recipes</button>
 <button class="tab" data-s="combo">What would THIS grow?</button>
 <button class="tab" data-s="hunt">Hunt list</button>
 <button class="tab" data-s="plan">Full plan (all 40)</button>
</div>

<section id="s-tree" class="on">
 <div class="inputs">
  <div class="cols2">
   <div>
    <div class="lbl">1 · COMMITTEE</div>
    <div class="panel" id="committeeList"></div>
   </div>
   <div>
    <div class="lbl">2 · HUMAN</div>
    <div class="panel" id="humanList" style="min-height:4rem"><span class="small">pick a committee…</span></div>
   </div>
  </div>
 </div>
 <div class="sep"><span>OUTPUT</span></div>
 <div class="breadcrumb" id="crumb">committee → human → <b>recipe</b></div>
 <pre id="recipe">pick a committee, then a human — the recipe appears here.</pre>
</section>

<section id="s-combo">
 <div class="small">Foods (physical stats):</div>
 <div class="chips" id="foodChips"></div>
 <div class="small" style="margin-top:.6rem">Memories (mental stats):</div>
 <div class="chips" id="memChips"></div>
 <div class="row" style="margin-top:.8rem">
   <span class="small">selected: <b id="selCount">0</b> items</span>
   <button class="go" onclick="doCombo()">Evaluate</button>
   <button class="tab" onclick="clearSel()">clear</button></div>
 <pre id="result2" style="min-height:8rem">tap items, then Evaluate…</pre>
</section>

<section id="s-hunt">
 <div class="row"><label class="small">rarest N memories
 <input type="number" id="huntn" value="25" min="5" max="60" style="width:4rem"></label>
 <button class="go" onclick="doHunt()">Show hunt list</button></div>
 <div class="small">Every memory, scarcest first, with where the wiki/community says to find it.</div>
 <pre id="result4" style="min-height:10rem">press Show hunt list…</pre>
</section>

<section id="s-plan">
 <div class="row"><label class="small">availability multiplier (saves re-run)
 <input type="number" id="cap" value="1" min="1" max="20"></label>
 <button class="go" onclick="doPlan()">Generate plan</button></div>
 <div class="small">All 40 committee humans, T4 first, respecting world item counts. Takes ~1 min.</div>
 <pre id="result3" style="min-height:10rem">press Generate…</pre>
</section>

<script>
const DATA = %%DATA%%;
const $ = id => document.getElementById(id);
document.querySelectorAll('.tabs .tab').forEach(b=>b.onclick=()=>{
 document.querySelectorAll('.tabs .tab').forEach(x=>x.classList.toggle('on',x===b));
 document.querySelectorAll('section').forEach(s=>s.classList.toggle('on',s.id==='s-'+b.dataset.s));
});
const profByBase = {};
DATA.professions.forEach(p=>{profByBase[p.name.replace(/ T\\d+$/,'')]=p;});

// ── tab 1: committees -> humans -> recipe ──────────────────────────
let curCommittee=null, curHuman=null;
DATA.committees.forEach(([cname,ctier,members],ci)=>{
 const d=document.createElement('div');d.className='committee';
 const dots=members.map(base=>{
   const p=profByBase[base];
   return p?`<i class="dotc t${p.tier}" title="T${p.tier} ${base}"></i>`:'';}).join('');
 d.innerHTML=`<span>${cname}</span><span class="dots">${dots}<span class="tier${ctier} smalltxt"> unlock T${ctier}</span></span>`;
 d.onclick=()=>showHumans(ci,cname,d); $('committeeList').append(d);});
// special non-committee humans
DATA.specials.forEach(([name,,notes],si)=>{
 const d=document.createElement('div');d.className='committee special';
 d.innerHTML=`<span>${name}</span><span class="dots"><i class="dotc t4"></i><span class="smalltxt small">not in a committee</span></span>`;
 d.onclick=()=>{
  document.querySelectorAll('.committee').forEach(x=>x.classList.toggle('on',x===d));
  $('humanList').innerHTML='<span class="small">special — no tier recipe</span>';
  document.querySelectorAll('.human').forEach(x=>x.classList.remove('on'));
  $('crumb').innerHTML=`Special → ${name} → <b>notes</b>`;
  $('recipe').textContent=notes;};
 $('committeeList').append(d);});
function showHumans(ci,cname,el){
 document.querySelectorAll('.committee').forEach(x=>x.classList.toggle('on',x===el));
 curCommittee=cname; curHuman=null;
 const hl=$('humanList'); hl.innerHTML='';
 DATA.committees[ci][2].forEach(base=>{
  const p=profByBase[base]; if(!p) return;
  const h=document.createElement('div');h.className='human';
  const reqs=Object.entries(p.req).map(([k,v])=>`${k}≥${v}`).join('  ');
  h.innerHTML=`<span class="tier${p.tier}">T${p.tier} ${base}</span>`;
  h.onclick=()=>{document.querySelectorAll('.human').forEach(x=>x.classList.toggle('on',x===h));
    showRecipe(p.name,cname,base);};
  const sub=document.createElement('div');sub.className='req';sub.textContent=reqs;
  h.append(sub); hl.append(h);});
}
async function showRecipe(full,committee,base){
 curHuman=base;
 $('crumb').innerHTML=`${committee} → ${base} → <b>recipe</b>`;
 $('recipe').textContent='solving…';
 render($('recipe'),await post('/api/solve',{target:full}));}

// ── tab 2: combo ────────────────────────────────────────────────────
function chips(el,items,mark){items.forEach(it=>{
 const c=document.createElement('span');c.className='chip';
 c.innerHTML=`${mark} ${it.name} <span class="ct">×${it.avail}</span>`;
 c.dataset.name=it.name;c.onclick=()=>{c.classList.toggle('sel');count()};el.append(c);});}
chips($('foodChips'),DATA.foods,'↻'); chips($('memChips'),DATA.memories,'◆');
function count(){$('selCount').textContent=document.querySelectorAll('.chip.sel').length}
function clearSel(){document.querySelectorAll('.chip.sel').forEach(c=>c.classList.remove('sel'));count()}
async function doCombo(){
 const pick=k=>[...document.querySelectorAll('#'+k+' .chip.sel')].map(c=>c.dataset.name);
 $('result2').textContent='computing…';
 render($('result2'),await post('/api/combo',{foods:pick('foodChips'),memories:pick('memChips')}));}

// ── tab 3: plan ─────────────────────────────────────────────────────
async function doHunt(){
 $('result4').textContent='loading…';
 render($('result4'),await post('/api/hunt',{n:+$('huntn').value||25}));}

async function doPlan(){
 $('result3').textContent='planning 40 humans — ~1 minute, hold tight…';
 render($('result3'),await post('/api/plan',{cap:+$('cap').value||1}));}

async function post(url,body){
 const r=await fetch(url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
 return await r.json();}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;')}
function colorProf(s){return s.replace(/T(\\d)/g,'<span class="tier$1">T$1</span>')}
function render(el,o){
 el.innerHTML = o.html.split('\\n').map(l=>
   colorProf(esc(l))
   .replace(/^(SAFE:.*)$/,'<b class="ok">$1</b>')
   .replace(/^(RISK:.*)$/,'<b class="bad">$1</b>')
   .replace(/^(!! .*)$/,'<b class="warn">$1</b>')
   .replace(/^(NOTE:.*)$/,'<b class="warn">$1</b>')
   .replace(/^(  MEMORIES — .*)$/,'<b>$1</b>')
   .replace(/^(  FOODS — .*)$/,'<b class="ok">$1</b>')
   .replace(/^(      ⌖ .*)$/,'<span class="loc">$1</span>')
   .replace(/^(mental stats .*)$/,'<b>$1</b>')).join('\\n');}
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            data = {
                "committees": COMMITTEES,
                "specials": SPECIAL,
                "professions": [{"name": h["name"], "tier": h["tier"],
                                 "req": {k: int(v) for k, v in h["req"].items()}}
                                for h in solver.humans_],
                "foods": [{"name": f["name"], "avail": f["avail"]} for f in solver.foods_],
                "memories": [{"name": m["name"], "avail": m["avail"]} for m in solver.memories_],
            }
            self._send(200, PAGE.replace("%%DATA%%", json.dumps(data)))
        else:
            self._send(404, b"not found", "text/plain")

    def _json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        try:
            body = self._json()
            fn = {"/api/solve": api_solve, "/api/combo": api_combo,
                  "/api/hunt": api_hunt, "/api/plan": api_plan}.get(self.path)
            if fn:
                self._send(200, json.dumps({"html": fn(body)}))
            else:
                self._send(404, json.dumps({"html": "not found"}))
        except Exception as e:
            self._send(500, json.dumps({"html": f"error: {e}"}))

def by_name(items, name):
    return next((i for i in items if i["name"].lower() == name.lower()), None)

def api_solve(body):
    target = by_name(solver.humans_, body.get("target", ""))
    if not target:
        return "pick a profession first"
    avail = None if body.get("unlimited", True) else {
        i["name"]: i["avail"] for i in solver.foods_ + solver.memories_}
    res = solver.solve_combo(target, solver.foods_, solver.memories_,
                             solver.humans_, avail=avail)
    if not res:
        return f"INFEASIBLE: not enough items in the world for {target['name']} at current scarcity"
    chosen, totals, matched = res
    mem_names = {m["name"]: m["avail"] for m in solver.memories_}
    food_names = {f["name"]: f["avail"] for f in solver.foods_}
    lines = [f"RECIPE for {target['name']}:"]
    exhaust = []
    mem_lines, food_lines = [], []
    for k, v in sorted(chosen.items(), key=lambda kv: (-kv[1], kv[0])):
        if k in mem_names:
            tag = f"  {v}/{mem_names[k]} of all that exist"
            if v >= mem_names[k]:
                tag = "  !! ENTIRE world supply"
                exhaust.append(k)
            mem_lines.append(f"  ◆ {v:>3} x {k}{tag}")
            where = MEMORY_LOCATIONS.get(k)
            note = MEMORY_NOTES.get(k)
            if note:
                mem_lines.append(f"      ⌖ {note}")
            elif where:
                mem_lines.append(f"      ⌖ reported at: {', '.join(where[:5])}"
                                 + ("…" if len(where) > 5 else ""))
        else:
            food_lines.append(f"  ↻ {v:>3} x {k}")
    lines.append("")
    lines.append("  MEMORIES — must be found in the world:")
    lines.extend(mem_lines or ["    (none)"])
    lines.append("")
    lines.append("  FOODS — craft at Food Processor (organics are farmable):")
    lines.extend(food_lines or ["    (none)"])
    if exhaust:
        lines.append("")
        lines.append(f"NOTE: this consumes the ENTIRE world supply of: {', '.join(exhaust)}")
    lines.append("")
    mem_stats = ["adaptability", "creativity", "communication", "discipline",
                 "empathy", "focus", "leadership", "logic", "patience", "wisdom"]
    food_stats = ["weight", "height", "life_exp", "strength", "intellect"]
    def statline(names):
        parts = [f"{s}={int(totals[i])}" for i, s in enumerate(solver.STATS)
                 if s in names and totals[i] > 0]
        return ", ".join(parts) or "(none)"
    lines.append("mental stats (from MEMORIES):  " + statline(mem_stats))
    lines.append("physical stats (from FOODS):   " + statline(food_stats))
    lines.append("")
    lines.append("the pod could come out as:")
    for h in sorted(matched, key=lambda h: -h["tier"]):
        flag = "   <-- YOUR TARGET" if h["name"] == target["name"] else ""
        lines.append(f"  T{h['tier']} {h['name']}{flag}")
    risky = [h["name"] for h in matched if solver.collat_weight(target, h) >= 50]
    lines.append("")
    if risky:
        lines.append(f"RISK: {len(risky)} same/higher-tier match — pod may pick one instead!")
        for r in risky:
            lines.append(f"  !! {r}")
    else:
        lines.append("SAFE: every other match is lower-tier — the game's favoring rule picks your target.")
    return "\n".join(lines)

def api_combo(body):
    totals = [0.0] * 15
    unknown, count = [], 0
    for kind, key, items in (("food", "foods", solver.foods_),
                             ("mem", "memories", solver.memories_)):
        for name in body.get(key, []):
            it = by_name(items, name)
            if not it:
                unknown.append(name); continue
            v = solver.stat_vec(it, kind)
            for s in range(15):
                totals[s] += v[s]
            count += 1
    if not count:
        return "select some items first"
    mem_stats = ["adaptability", "creativity", "communication", "discipline",
                 "empathy", "focus", "leadership", "logic", "patience", "wisdom"]
    food_stats = ["weight", "height", "life_exp", "strength", "intellect"]
    def statline(names):
        parts = [f"{s}={int(totals[i])}" for i, s in enumerate(solver.STATS)
                 if s in names and totals[i] > 0]
        return ", ".join(parts) or "(none)"
    lines = [f"{count} items ->",
             "mental stats (from MEMORIES):  " + statline(mem_stats),
             "physical stats (from FOODS):   " + statline(food_stats), ""]
    matched = solver.satisfied(totals, solver.humans_)
    if matched:
        lines.append("the pod could come out as:")
        tmax = max(h["tier"] for h in matched)
        for h in sorted(matched, key=lambda h: -h["tier"]):
            star = "  <-- likely pick (highest tier)" if h["tier"] == tmax else ""
            lines.append(f"  T{h['tier']} {h['name']} [{h['cat']}]{star}")
        lines.append("")
        if len(matched) == 1:
            lines.append("SAFE: exactly one profession matches — you get what you see.")
        elif len([h for h in matched if h["tier"] == tmax]) > 1:
            lines.append(f"RISK: {len([h for h in matched if h['tier']==tmax])} tied at T{tmax} — the game picks among them.")
        else:
            lines.append("moderate: one highest-tier match, favoring rule should pick it.")
    else:
        best = sorted(solver.humans_, key=lambda h: -sum(
            min(1.0, totals[solver.SI[s]] / v) for s, v in h["req"].items()))[:6]
        lines.append("nothing satisfied yet. closest:")
        for h in best:
            gaps = {s: round(v - totals[solver.SI[s]]) for s, v in h["req"].items()
                    if totals[solver.SI[s]] < v}
            lines.append(f"  T{h['tier']} {h['name']}: short {gaps}")
    if unknown:
        lines.append(f"\n(unknown items ignored: {', '.join(unknown)})")
    return "\n".join(lines)

def api_hunt(body):
    n = max(5, int(body.get("n", 25)))
    lines = [f"HUNT LIST — scarcest {n} memories (all counts are the TOTAL that exist):", ""]
    for m in sorted(solver.memories_, key=lambda m: m["avail"])[:n]:
        note = MEMORY_NOTES.get(m["name"])
        where = MEMORY_LOCATIONS.get(m["name"])
        lines.append(f"  ×{m['avail']:<3} ◆ {m['name']}")
        if note:
            lines.append(f"      ⌖ {note}")
        elif where:
            lines.append(f"      ⌖ reported at: {', '.join(where[:6])}"
                         + ("…" if len(where) > 6 else ""))
        else:
            lines.append("      ⌖ no wiki location recorded yet — check the map while exploring")
    return "\n".join(lines)

def api_plan(body):
    cap = max(1, int(body.get("cap", 1)))
    inv = {i["name"]: cap * i["avail"] for i in solver.foods_ + solver.memories_}
    order = sorted(solver.humans_, key=lambda h: (-h["tier"], h["cat"], h["name"]))
    lines, fails = [], []
    for t in order:
        res = solver.solve_combo(t, solver.foods_, solver.memories_,
                                 solver.humans_, avail=inv)
        if not res:
            fails.append(t["name"]); continue
        chosen, totals, matched = res
        for k, v in chosen.items():
            inv[k] -= v
        risky = [h["name"] for h in matched
                 if solver.collat_weight(t, h) >= 50]
        lines.append(f"T{t['tier']} {t['name']}")
        for k, v in sorted(chosen.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"   {v:>3} x {k}")
        if risky:
            lines.append(f"   !! collateral: {', '.join(risky)}")
    head = [f"{'SAFE' if not fails else 'PARTIAL'}: {len(order)-len(fails)}/{len(order)} humans planned"
            + (" — all recipes risk-free" if not any('!!' in l for l in lines) else "")]
    if fails:
        head.append("not feasible at this scarcity: " + ", ".join(fails))
    head.append("")
    return "\n".join(head + lines)

if __name__ == "__main__":
    import sys
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    print(f"http://{host}:{PORT}")
    ThreadingHTTPServer((host, PORT), H).serve_forever()
