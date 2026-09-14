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
@media(max-width:820px){.cols{grid-template-columns:1fr}}
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
</style></head><body>
<h1>THE LAST CARETAKER <span>· human lab</span></h1>
<div class="tabs">
 <button class="tab on" data-s="tree">Committees → humans → recipes</button>
 <button class="tab" data-s="combo">What would THIS grow?</button>
 <button class="tab" data-s="plan">Full plan (all 40)</button>
</div>

<section id="s-tree" class="on">
 <div class="cols">
  <div>
   <div class="panel" id="committeeList"></div>
   <div class="panel" id="humanList" style="margin-top:.6rem"><span class="small">pick a committee…</span></div>
  </div>
  <div>
   <div class="breadcrumb" id="crumb">committee → human → <b>recipe</b></div>
   <pre id="recipe">pick a committee, then a human — the recipe appears here.</pre>
  </div>
 </div>
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
 d.innerHTML=`<span>${cname}</span><span class="tier${ctier}">committee unlock T${ctier}</span>`;
 d.onclick=()=>showHumans(ci,cname,d); $('committeeList').append(d);});
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
function chips(el,items){items.forEach(it=>{
 const c=document.createElement('span');c.className='chip';
 c.innerHTML=`${it.name} <span class="ct">×${it.avail}</span>`;
 c.dataset.name=it.name;c.onclick=()=>{c.classList.toggle('sel');count()};el.append(c);});}
chips($('foodChips'),DATA.foods); chips($('memChips'),DATA.memories);
function count(){$('selCount').textContent=document.querySelectorAll('.chip.sel').length}
function clearSel(){document.querySelectorAll('.chip.sel').forEach(c=>c.classList.remove('sel'));count()}
async function doCombo(){
 const pick=k=>[...document.querySelectorAll('#'+k+' .chip.sel')].map(c=>c.dataset.name);
 $('result2').textContent='computing…';
 render($('result2'),await post('/api/combo',{foods:pick('foodChips'),memories:pick('memChips')}));}

// ── tab 3: plan ─────────────────────────────────────────────────────
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
   .replace(/^(!! .*)$/,'<b class="warn">$1</b>')).join('\\n');}
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
                  "/api/plan": api_plan}.get(self.path)
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
    lines = [f"RECIPE for {target['name']}:"]
    for k, v in sorted(chosen.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {v:>3} x {k}")
    lines.append("")
    lines.append("stats: " + ", ".join(f"{s}={int(totals[i])}"
                 for i, s in enumerate(solver.STATS) if totals[i] > 0))
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
    lines = [f"{count} items ->", "stats: " + (", ".join(
        f"{s}={int(totals[i])}" for i, s in enumerate(solver.STATS) if totals[i] > 0) or "(none)"), ""]
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
