#!/usr/bin/env python3
"""Web UI for the Last Caretaker solver:  http://127.0.0.1:8765

Run:  .venv/bin/python webapp.py [host]   (stdlib only, no installs)

Flow: committees -> humans -> recipe for the human you pick.
"""
import json, os, re, signal, subprocess, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import solver

PORT = 8765
VERSION = "1.0.1"
STATE_DIR = os.environ.get("SOLVER_STATE") or os.path.dirname(os.path.abspath(__file__))
def _state(name):
    p = os.path.join(STATE_DIR, name)
    os.makedirs(STATE_DIR, exist_ok=True)
    return p

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
    "Oath Token": "Update 5 hidden location 'Fourth Chamber': collect MAPS at 3 statue sites, triangulate 2 maps to mark the chamber, bring building materials (door/statues need repairs), 3rd map+statue opens it, token is in the vault inside. No quest marker. REUSABLE — confirmed: grew Chancellor + Colonel with one; quick pod-swap recovers it.",
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

def _load_global_plan():
    """The one-shot whole-set allocation (solver.solve_global), if it exists."""
    import os, json
    p = _state("global_plan.json")
    try:
        return json.load(open(p))
    except Exception:
        return None

def _grown():
    """Frozen record of humans the player marked as grown: name ->
    {recipe, stamp, transposium, spare_pct}. The recipe is locked at mark
    time — later re-plans never rewrite what was actually consumed."""
    try:
        return json.load(open(_state("grown.json")))
    except Exception:
        return {}

def _save_grown(g):
    with open(_state("grown.json"), "w") as f:
        json.dump(g, f, indent=1, sort_keys=True)

def _consumed():
    """item -> copies already spent by grown humans (gone from the world)."""
    used = {}
    for rec in _grown().values():
        for k, v in rec.get("recipe", {}).items():
            if isinstance(v, int):
                used[k] = used.get(k, 0) + v
    return used

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
.dotc{display:inline-block;width:.65rem;height:.65rem;border-radius:50%;position:relative}
.dotc.grown::after{content:"";position:absolute;inset:-3px;border:1.5px solid #7ee787;border-radius:4px}
.dotc.t1{background:#7d8590}.dotc.t2{background:#7ee787}.dotc.t3{background:#a5d6ff}.dotc.t4{background:#f778ba}
.smalltxt{font-size:.75rem;margin-left:.35rem}
.loc{color:#a5d6ff}
.committee.special{border-style:dashed}
.planbar{margin-top:.8rem;border-top:1px solid #21262d;padding-top:.6rem;display:flex;align-items:center;gap:1rem;flex-wrap:wrap}
.planmode{color:#c9d1d9;cursor:pointer;display:flex;align-items:center;gap:.4rem}
.busy{position:fixed;inset:0;background:rgba(4,7,12,.82);backdrop-filter:blur(2px);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1rem;z-index:50}
.busy.hidden{display:none}
.spinner{width:42px;height:42px;border:4px solid #30363d;border-top-color:#f778ba;border-radius:50%;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.busytxt{text-align:center}
.cancelbtn{background:#21262d;border:1px solid #f85149;color:#ff7b72;padding:.5rem 1.1rem;border-radius:6px;cursor:pointer;font:inherit}
body.locked{pointer-events:none;user-select:none}
body.locked #busy{pointer-events:auto}
.rsv{color:#f2cc60;cursor:help;margin-left:.2rem}
.warnpulse{border-color:#f2cc60 !important;color:#f2cc60;animation:pulse 1.6s ease-in-out infinite}
@keyframes pulse{50%{border-color:#1f6feb}}
</style></head><body>
<h1>THE LAST CARETAKER <span>· human lab · v%%VERSION%%</span></h1>
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
 <span class="loc">⌖ = where to find it</span><span class="dot">·</span>
 <span class="rsv">★</span> = on the reserve list (hover for details)<span class="dot">·</span>
 <span style="display:inline-block;width:.65rem;height:.65rem;border-radius:50%;background:#7d8590;position:relative"><span style="position:absolute;inset:-3px;border:1.5px solid #7ee787;border-radius:4px"></span></span> = that human is GROWN ✓
</div>
<div class="tabs">
 <button class="tab on" data-s="tree">Committees → humans → recipes</button>
 <button class="tab" data-s="combo">What would THIS grow?</button>
 <button class="tab" data-s="hunt">Hunt list</button>
 <button class="tab" data-s="reserve">Reserve list</button>
 <button class="tab" data-s="grown">Grown ✓</button>
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
  <div class="planbar">
   <label class="planmode"><input type="checkbox" id="transposiumMode" onchange="toggleTransposium()">
    <b>Add The Transposium</b> <span class="small">maze (Update 02) — off = solver won't use Transposium-only memories (Ash Notebook)</span></label>
   <label class="planmode">Spare margin
    <input type="number" id="sparePct" value="0" min="0" max="70" step="5" style="width:3.2rem" onchange="marginChanged()">%</label>
   <span class="small">plan may only USE this much less of every memory — leaves slack so one missed loot point doesn't sink the plan (applies on re-calculate).<br>
   Tested JOINT-plan limit: without Transposium the whole set only solves at <b>≤20%</b> spare; with Transposium checked, up to <b>50%</b>. Beyond that the allocation is mathematically infeasible (per-human recipes still exist at higher margins — only the all-40-at-once plan breaks).</span>
   <label class="planmode"><input type="checkbox" id="planMode" onchange="togglePlanMode()">
    <b>Full plan mode</b> — allocate ALL humans at once against real world counts
    <span class="small" id="planStamp"></span></label>
   <button class="tab" id="replanBtn" onclick="startPlan(true)" style="display:none">re-calculate</button>
  </div>
 </div>
 <div class="sep"><span>OUTPUT</span></div>
 <div class="breadcrumb" id="crumb">committee → human → <b>recipe</b>
  <button class="tab" id="grownBtn" style="display:none;margin-left:.8rem"></button></div>
 <pre id="recipe">pick a committee, then a human — the recipe appears here.</pre>
</section>

<div id="busy" class="busy hidden">
 <div class="spinner"></div>
 <div class="busytxt">Calculating the GLOBAL plan for all 40 humans<br>
  <b id="busyT"></b><br>
  <span class="small">the ILP allocates every memory to the human that needs it most — usually a few minutes</span></div>
 <button class="cancelbtn" onclick="cancelPlan()">Cancel — back to single solves</button>
</div>

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

<section id="s-reserve">
 <div class="cols2">
  <div>
   <div class="lbl">RESERVED MEMORIES</div>
   <div class="panel" id="rsvList"><span class="small">loading…</span></div>
  </div>
  <div>
   <div class="lbl">DETAILS</div>
   <pre id="result5" style="min-height:10rem">click an item…</pre>
  </div>
 </div>
</section>

<section id="s-grown">
 <div class="cols2">
  <div>
   <div class="lbl">GROWN HUMANS (frozen recipes)</div>
   <div class="panel" id="grownList"><span class="small">none yet — mark one from its recipe.</span></div>
  </div>
  <div>
   <div class="lbl">DETAILS</div>
   <pre id="result6" style="min-height:10rem">click an item…</pre>
  </div>
 </div>
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
let curCommittee=null, curHuman=null, curFull=null;
let GROWN={};
post('/api/grown',{}).then(r=>{try{GROWN=JSON.parse(r.html);}catch(e){} paintGrown();refreshCurrent();});
DATA.committees.forEach(([cname,ctier,members],ci)=>{
 const d=document.createElement('div');d.className='committee';
 const dots=members.map(base=>{
   const p=profByBase[base];
   return p?`<i class="dotc t${p.tier}" data-base="${esc(base)}" title="T${p.tier} ${base}"></i>`:'';}).join('');
 d.innerHTML=`<span>${cname}</span><span class="dots">${dots}<span class="tier${ctier} smalltxt"> unlock T${ctier}</span></span>`;
 d.onclick=()=>showHumans(ci,cname,d); $('committeeList').append(d);});
// special non-committee humans
DATA.specials.forEach(([name,,notes],si)=>{
 const d=document.createElement('div');d.className='committee special';
 d.innerHTML=`<span>${name}</span><span class="dots"><i class="dotc t4" data-base="${esc(name)}"></i><span class="smalltxt small">not in a committee</span></span>`;
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
  const grown=Object.keys(GROWN).some(n=>n.replace(/ T\\d+$/,'')===base);
  h.innerHTML=`<span class="tier${p.tier}">T${p.tier} ${base}</span>${grown?'<span class="ok">✓ grown</span>':''}`;
  h.onclick=()=>{document.querySelectorAll('.human').forEach(x=>x.classList.toggle('on',x===h));
    showRecipe(p.name,cname,base);};
  hl.append(h);});
}
async function showRecipe(full,committee,base){
 curHuman=base; curFull=full;
 $('crumb').innerHTML=`${committee} → ${base} → <b>recipe</b>`
  +` <button class="tab" id="grownBtn" style="margin-left:.8rem"></button>`;
 syncGrownBtn();
 $('recipe').textContent='solving…';
 render($('recipe'),await post('/api/solve',{target:full,plan:$('planMode').checked,
   include_transposium:$('transposiumMode').checked}));}

function syncGrownBtn(){
 const b=$('grownBtn'); if(!b||!curFull) return;
 const done=!!GROWN[curFull];
 b.textContent=done?'✓ GROWN — un-mark':'mark as GROWN ✓';
 b.classList.toggle('ok',done);
 b.onclick=done?unmarkGrown:markGrown;}
async function markGrown(){
 $('recipe').textContent='recording…';
 render($('recipe'),await post('/api/grown/mark',{target:curFull}));
 GROWN=JSON.parse((await post('/api/grown',{})).html||'{}');
 paintGrown(); repaintHumans();
 showRecipe(curFull,curCommittee,curHuman);}   // shows the FROZEN record
async function unmarkGrown(){
 render($('recipe'),await post('/api/grown/unmark',{target:curFull}));
 GROWN=JSON.parse((await post('/api/grown',{})).html||'{}');
 paintGrown(); repaintHumans();
 showRecipe(curFull,curCommittee,curHuman);}
function repaintHumans(){
 if(!curCommittee) return;
 const i=DATA.committees.findIndex(c=>c[0]===curCommittee);
 if(i<0) return;
 const els=[...document.querySelectorAll('.committee')];
 showHumans(i,curCommittee,els[i]||els[0]);}
function paintGrown(){
 const el=$('grownList');
 const grownBases=new Set(Object.keys(GROWN).map(n=>n.replace(/ T\\d+$/,'')));
 document.querySelectorAll('.dotc[data-base]').forEach(d=>
   d.classList.toggle('grown',grownBases.has(d.dataset.base)));
 document.querySelectorAll('.tabs .tab').forEach(t=>{
  if(t.dataset.s==='grown') t.textContent=`Grown ✓ ${Object.keys(GROWN).length}/41`;});
 if(!el) return; el.innerHTML='';
 const names=Object.keys(GROWN).sort();
 if(!names.length){el.innerHTML='<span class="small">none yet — mark one from its recipe.</span>';return;}
 names.forEach(n=>{
  const rec=GROWN[n];
  const d=document.createElement('div');d.className='human';
  d.innerHTML=`<span class="tier${(n.match(/T(\\d+)$/)||[,'?'])[1]}">${esc(n)}</span><span class="small">${rec.stamp}</span>`;
  d.onclick=()=>{document.querySelectorAll('#grownList .human').forEach(x=>x.classList.toggle('on',x===d));
    $('result6').textContent=fmtGrown(n,rec);};
  el.append(d);});
 document.querySelectorAll('.tabs .tab').forEach(t=>{
  if(t.dataset.s==='grown') t.textContent=`Grown ✓ ${names.length}/41`;});}
function fmtGrown(n,r){
 let t=`${n} — GROWN ✓ (recorded ${r.stamp})\\nmode: Transposium ${r.transposium?'INCLUDED':'excluded'} · spare ${r.spare_pct||0}%\\n\\nITEMS ACTUALLY CONSUMED:\\n`;
 for(const [k,v] of Object.entries(r.recipe).sort((a,b)=>b[1]-a[1])){
   if(k==='_note'){t+='  '+v+'\\n';continue;}
   t+=`  ${String(v).padStart(3)} x ${k}\\n`;}
 return t;}

function setSpareCap(){
 const cap=$('transposiumMode').checked?50:20;
 $('sparePct').max=cap;
 if(+$('sparePct').value>cap)$('sparePct').value=cap;}
function toggleTransposium(){
 setSpareCap(); marginChanged();
 if(curHuman&&curCommittee) refreshCurrent();}

// ── full-plan mode ──────────────────────────────────────────────────
let planTimer=null;
function setLocked(on){
 if(on)$('busyT').textContent='Transposium: '+($('transposiumMode').checked?'INCLUDED':'EXCLUDED')
   +' · spare margin '+($('sparePct').value||0)+'%';
 document.body.classList.toggle('locked',on);
 $('busy').classList.toggle('hidden',!on);}
function togglePlanMode(){
 if($('planMode').checked){
  if(!DATA.hasPlan){startPlan(false);}
  else { $('recipe').textContent='using the cached GLOBAL plan.'; }
 } else {
  if(planTimer){clearInterval(planTimer);planTimer=null;}
  if($('replanBtn'))$('replanBtn').style.display='none';
  if(curHuman&&curCommittee) refreshCurrent();
 }}
function refreshCurrent(){
 const el=document.querySelectorAll('.human.on')[0];
 if(el) el.click();}
async function startPlan(force){
 setLocked(true);
 const r=await post('/api/plan/start',{force:!!force,
   include_transposium:$('transposiumMode').checked,
   spare_pct:+$('sparePct').value||0});
 if(r.status==='stale'){   // cached plan was built for the other mode
  const r2=await post('/api/plan/start',{force:true,
   include_transposium:$('transposiumMode').checked,
   spare_pct:+$('sparePct').value||0});
  if(!r2.started){setLocked(false);$('recipe').textContent='could not recalculate.';return;}
  planTimer=setInterval(pollPlan,1500);return;}
 if(r.error){setLocked(false);$('recipe').textContent='could not start: '+r.error;$('planMode').checked=false;return;}
 planTimer=setInterval(pollPlan,1500);}
function planStampText(r){
 return '  · calculated '+r.stamp+' · '+(r.transposium===false?'Transposium EXCLUDED':'Transposium included')
   +((r.spare_pct||0)?(' · '+r.spare_pct+'% spare margin'):' · 0% spare margin');}
let PLAN_META=null;   // mode flags of the CALCULATED plan on disk
function marginChanged(){
 if(!$('planMode').checked||!PLAN_META) return;
 const want=+$('sparePct').value||0;
 if(want!==PLAN_META.spare_pct||$('transposiumMode').checked!==!!PLAN_META.transposium){
   $('planStamp').className='small warn';
   $('planStamp').textContent=`  · ⚠ settings changed — cached plan still ${PLAN_META.spare_pct||0}%`
     +` · press re-calculate`;
   $('replanBtn').classList.add('warnpulse');
 } else {
   $('planStamp').className='small';
   $('planStamp').textContent=planStampText(PLAN_META)+' — recipes come from the global plan';
   $('replanBtn').classList.remove('warnpulse');}}
async function pollPlan(){
 let r;
 try { r=await post('/api/plan/status',{}); }
 catch(e){ return; }   // transient (server restart) — keep spinning
 if(r.status==='running')return;
 clearInterval(planTimer);planTimer=null;setLocked(false);
 $('planMode').checked=(r.status==='done');
 if(r.status==='done'&&r.transposium!==undefined)$('transposiumMode').checked=!!r.transposium;
 if(r.status==='done'&&r.spare_pct!==undefined)$('sparePct').value=r.spare_pct;
 PLAN_META=r.status==='done'?{transposium:r.transposium,spare_pct:r.spare_pct||0,stamp:r.stamp}:null;
 if(r.status==='done'){$('planStamp').className='small';$('replanBtn').classList.remove('warnpulse');}
 $('replanBtn').style.display=r.status==='done'?'':'none';
 $('planStamp').textContent=r.status==='done'?planStampText(r):'';
 if(r.status==='done'){$('recipe').textContent='GLOBAL plan ready — click a human.';refreshCurrent();}
 else if(r.status==='cancelled'){$('recipe').textContent='plan cancelled — back to single solves.';}
 else {$('planMode').checked=false;$('recipe').textContent='plan failed: '+(r.msg||'unknown error');}}
function initPlanUI(){
 post('/api/plan/status',{}).then(r=>{
  if(r.status==='done'){
   $('planMode').checked=true;$('replanBtn').style.display='';
   if(r.transposium!==undefined)$('transposiumMode').checked=!!r.transposium;
   if(r.spare_pct!==undefined)$('sparePct').value=r.spare_pct;
   PLAN_META={transposium:r.transposium,spare_pct:r.spare_pct||0,stamp:r.stamp};
   $('planStamp').textContent=planStampText(r)+' — recipes come from the global plan';}
  else if(r.status==='running'){
   $('planMode').checked=true;$('recipe').textContent='global plan calculating…';
   startPlan(false);}});}
initPlanUI();setSpareCap();
async function cancelPlan(){
 await post('/api/plan/cancel',{});
 if(planTimer){clearInterval(planTimer);planTimer=null;}
 setLocked(false);$('planMode').checked=false;
 $('recipe').textContent='plan cancelled — back to single solves.';}

// ── tab 2: combo ────────────────────────────────────────────────────
function chips(el,items,mark){items.forEach(it=>{
 const c=document.createElement('span');c.className='chip';
 c.innerHTML=`${mark} ${it.name} <span class="ct">×${it.avail}</span>`
  +` <span class="cq" style="display:none"><button class="qn">−</button><b class="qv">1</b><button class="qp">+</button></span>`;
 c.dataset.name=it.name;
 c.querySelector('.qp').onclick=e=>{e.stopPropagation();setQ(c,q(c)+1);};
 c.querySelector('.qn').onclick=e=>{e.stopPropagation();setQ(c,Math.max(1,q(c)-1));};
 c.onclick=()=>{c.classList.toggle('sel');
   c.querySelector('.cq').style.display=c.classList.contains('sel')?'inline':'none';count()};el.append(c);});}
chips($('foodChips'),DATA.foods,'↻'); chips($('memChips'),DATA.memories,'◆');
function q(c){return +c.querySelector('.qv').textContent||1}
function setQ(c,v){c.querySelector('.qv').textContent=v;count()}
function count(){$('selCount').textContent=[...document.querySelectorAll('.chip.sel')].reduce((a,c)=>a+q(c),0)+' items'}
function clearSel(){document.querySelectorAll('.chip.sel').forEach(c=>{c.classList.remove('sel');c.querySelector('.cq').style.display='none';setQ(c,1)});count()}
async function doCombo(){
 const pick=k=>[...document.querySelectorAll('#'+k+' .chip.sel')].map(c=>({name:c.dataset.name,count:q(c)}));
 $('result2').textContent='computing…';
 render($('result2'),await post('/api/combo',{foods:pick('foodChips'),memories:pick('memChips')}));}

// ── tab 3: plan ─────────────────────────────────────────────────────
async function doReserve(){}   // details pane driven by DATA.reserve, built at load
function buildReserve(){
 const el=$('rsvList'); el.innerHTML='';
 if(!DATA.reserve.length){el.innerHTML='<span class="small">no plan yet — run Full plan mode to generate the allocation.</span>';return;}
 DATA.reserve.forEach(r=>{
  const d=document.createElement('div');d.className='human';
  d.innerHTML=`<span class="${r.slack<=0?'bad':'warn'}">${esc(r.name)}</span>`;
  d.onclick=()=>{
   document.querySelectorAll('#rsvList .human').forEach(x=>x.classList.toggle('on',x===d));
   let t=`${r.name}\\n${r.verdict}\\nworld supply: ${r.world} · plan claims: ${r.plan}\\n`;
   if(r.where) t+=`\\nWhere: ${r.where}\\n`;
   t+='\\nRESERVED FOR:\\n';
   r.claimers.forEach(([h,c])=>{t+=`   ${String(c).padStart(3)}×  ${h.replace(/ T\\d+$/,'')}\\n`;});
   $('result5').textContent=t;};
  el.append(d);});}
buildReserve();
async function doHunt(){
 $('result4').textContent='loading…';
 render($('result4'),await post('/api/hunt',{n:+$('huntn').value||25}));}

async function post(url,body){
 const r=await fetch(url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
 return await r.json();}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;')}
function tipstars(s){ // «tip»★ -> hoverable star (run BEFORE other line rules)
 return s.replace(/«([^»]*)»★/g,(m,tip)=>`<span class="rsv" title="${esc(tip)}">★</span>`);}
function colorProf(s){return s.replace(/T(\\d)/g,'<span class="tier$1">T$1</span>')}
function render(el,o){
 el.innerHTML = o.html.split('\\n').map(l=>
   tipstars(colorProf(esc(l)))
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
                "hasPlan": os.path.exists(_state("global_plan.json")),
                "reserve": reserve_data(),
                "foods": [{"name": f["name"], "avail": f["avail"]} for f in solver.foods_],
                "memories": [{"name": m["name"], "avail": m["avail"]} for m in solver.memories_],
            }
            self._send(200, PAGE.replace("%%DATA%%", json.dumps(data))
                            .replace("%%VERSION%%", VERSION))
        else:
            self._send(404, b"not found", "text/plain")

    def _json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        try:
            body = self._json()
            if self.path == "/api/plan/start":
                self._send(200, json.dumps(plan_start(
                    body.get("force", False),
                    bool(body.get("include_transposium", False)),
                    int(body.get("spare_pct", 0) or 0))))
                return
            if self.path == "/api/plan/status":
                self._send(200, json.dumps(plan_status()))
                return
            if self.path == "/api/plan/cancel":
                self._send(200, json.dumps(plan_cancel()))
                return
            fn = {"/api/solve": api_solve, "/api/combo": api_combo,
                  "/api/hunt": api_hunt, "/api/reserve": api_reserve,
                  "/api/grown": api_grown, "/api/grown/mark": api_grown_mark,
                  "/api/grown/unmark": api_grown_unmark}.get(self.path)
            if fn:
                self._send(200, json.dumps({"html": fn(body)}))
            else:
                self._send(404, json.dumps({"html": "not found"}))
        except Exception as e:
            self._send(500, json.dumps({"html": f"error: {e}"}))


# ── global-plan subprocess manager ──────────────────────────────────
PLAN_PROC = None       # subprocess.Popen for solve_all.py
PLAN_LOG = "/tmp/tlc-plan.log"

def _plan_meta():
    """Mode flags the cached plan was computed under (plans predating a
    feature assumed its default)."""
    try:
        gp = json.load(open(_state("global_plan.json")))
        m = gp.get("_meta", {})
        return {"transposium": bool(m.get("transposium", True)),
                "spare_pct": int(m.get("spare_pct", 0))}
    except Exception:
        return None

def plan_start(force, include_transposium=False, spare_pct=0):
    global PLAN_PROC
    here = os.path.dirname(os.path.abspath(__file__))
    plan_file = _state("global_plan.json")
    if PLAN_PROC and PLAN_PROC.poll() is None:
        return {"started": False, "status": "running"}
    if _orphan_solver_pid():
        return {"started": False, "status": "running"}
    if not force and os.path.exists(plan_file):
        want = {"transposium": bool(include_transposium),
                "spare_pct": int(spare_pct)}
        have = _plan_meta()
        if have and any(have[k] != want[k] for k in want):
            return {"started": False, "status": "stale"}
        return {"started": False, "status": "done"}
    if force:
        try:
            os.remove(plan_file)
        except FileNotFoundError:
            pass
    cmd = [sys.executable, os.path.join(here, "solve_all.py"), "600"]
    if include_transposium:
        cmd.append("--include-transposium")
    if spare_pct:
        cmd += ["--spare-pct", str(int(spare_pct))]
    log = open(PLAN_LOG, "w")
    PLAN_PROC = subprocess.Popen(
        cmd, cwd=here, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True)
    return {"started": True, "status": "running"}

def _orphan_solver_pid():
    """solve_all.py may outlive a webapp restart; find it by cmdline."""
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                cl = open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="replace").split("\0")
            except OSError:
                continue
            if len(cl) >= 2 and cl[1].endswith("solve_all.py") \
                    and os.path.basename(cl[0]).startswith("python"):
                return int(pid)
    except OSError:
        pass
    return None

def plan_status():
    here = os.path.dirname(os.path.abspath(__file__))
    plan_file = _state("global_plan.json")
    if PLAN_PROC and PLAN_PROC.poll() is None:
        return {"status": "running"}
    if _orphan_solver_pid():
        return {"status": "running"}
    if os.path.exists(plan_file):
        stamp = time.strftime("%H:%M", time.localtime(os.path.getmtime(plan_file)))
        return {"status": "done", "stamp": stamp,
                "transposium": (_plan_meta() or {}).get("transposium", True),
                "spare_pct": (_plan_meta() or {}).get("spare_pct", 0)}
    rc = PLAN_PROC.poll() if PLAN_PROC else None
    if rc == 130:
        return {"status": "cancelled"}
    if rc not in (None, 0):
        msg = ""
        try:
            msg = open(PLAN_LOG).read()[-300:]
        except Exception:
            pass
        return {"status": "failed", "msg": msg}
    return {"status": "idle"}

def plan_cancel():
    global PLAN_PROC
    killed = False
    if PLAN_PROC and PLAN_PROC.poll() is None:
        try:
            os.killpg(os.getpgid(PLAN_PROC.pid), signal.SIGTERM)
            killed = True
        except (ProcessLookupError, PermissionError):
            pass
    pid = _orphan_solver_pid()
    if pid:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            killed = True
        except (ProcessLookupError, PermissionError):
            pass
    return {"status": "cancelled" if killed else "idle"}

def by_name(items, name):
    return next((i for i in items if i["name"].lower() == name.lower()), None)

def api_grown(body):
    return json.dumps(_grown(), indent=1)

LAST_RECIPE = {}   # target -> {"chosen":…, "transposium":…, } from the last solve

def api_grown_mark(body):
    """Freeze the recipe currently shown for one human as 'grown'."""
    name = body.get("target", "")
    target = by_name(solver.humans_, name)
    if not target:
        return "pick a profession first"
    name = target["name"]
    rec = LAST_RECIPE.get(name)
    if not rec or not rec.get("chosen"):
        return "nothing to record — show a recipe for this human first"
    recipe = {k: v for k, v in rec["chosen"].items()
              if isinstance(v, int) and v}
    if rec.get("note"):
        recipe["_note"] = rec["note"]
    g = _grown()
    g[name] = {"recipe": recipe,
               "stamp": time.strftime("%Y-%m-%d %H:%M"),
               "transposium": bool(rec.get("transposium", False)),
               "spare_pct": int(rec.get("spare_pct", 0) or 0)}
    _save_grown(g)
    return f"GROWN recorded: {name} ({len(g)} total) — items marked consumed."

def api_grown_unmark(body):
    name = body.get("target", "")
    target = by_name(solver.humans_, name)
    if not target:
        return "pick a profession first"
    g = _grown()
    if target["name"] not in g:
        return f"{target['name']} was not marked grown."
    del g[target["name"]]
    _save_grown(g)
    return f"{target['name']} un-marked — its items are back in the world pool."

def _totals_of(chosen):
    totals = [0.0] * 15
    for name, c in chosen.items():
        it = by_name(solver.foods_, name)
        kind, v = ("food", it) if it else ("mem", by_name(solver.memories_, name))
        if v:
            vec = solver.stat_vec(v, kind)
            for s in range(15):
                totals[s] += c * vec[s]
    return totals

def _global_usage():
    """item -> count across the whole global plan (None if no plan file).
    Rows of already-grown humans are EXCLUDED — their copies live in the
    frozen ledger (_consumed), not in the plan's future claims; counting
    both would double-charge the world supply."""
    gp = _load_global_plan()
    if not gp:
        return None
    grown = _grown()
    used = {}
    for human, items in gp.items():
        if human in grown or not isinstance(items, dict):
            continue
        for k, v in items.items():
            if isinstance(v, int):
                used[k] = used.get(k, 0) + v
    return used

def rsv_star(item):
    """★ marker + hover tooltip for reserve-list items, encoded for render()."""
    rsv = {r["name"]: r for r in reserve_data()}
    r = rsv.get(item)
    if not r:
        return ""
    tip = f"{r['verdict']} · plan uses {r['plan']}/{r['world']} in world"
    if r["where"]:
        tip += " · " + r["where"]
    tip = tip.replace('"', "'").replace("«", "(").replace("»", ")")
    return f" «{tip}»★"

def _fmt_grown(name, rec):
    """Render a frozen grown-record: what was ACTUALLY consumed."""
    mem_names = {m["name"]: m["avail"] for m in solver.memories_}
    lines = [f"{name} — GROWN ✓  (recorded {rec['stamp']},",
             f"  mode: Transposium {'INCLUDED' if rec.get('transposium') else 'excluded'}"
             f" · spare margin {rec.get('spare_pct', 0)}%",
             "  this is the FROZEN recipe — later re-plans do not change it)", ""]
    lines.append("  ITEMS ACTUALLY CONSUMED:")
    if rec["recipe"].get("_note"):
        lines.append("  " + rec["recipe"]["_note"])
    for k, v in sorted(rec["recipe"].items(), key=lambda kv: (-kv[1], kv[0])):
        if k == "_note":
            continue
        if k in mem_names:
            lines.append(f"  ◆ {v:>3} x {k}   (of {mem_names[k]} that ever existed)")
            where = MEMORY_NOTES.get(k) or MEMORY_LOCATIONS.get(k)
            if isinstance(where, str):
                lines.append(f"      ⌖ {where}")
        else:
            lines.append(f"  ↻ {v:>3} x {k}")
    cons = _consumed()
    tight = [f"{k}: {mem_names[k]} exist, {cons.get(k,0)} spent by grown humans, "
             f"{mem_names[k]-cons.get(k,0)} left"
             for k in rec["recipe"] if k in mem_names
             and mem_names[k] - cons.get(k, 0) <= 2]
    if tight:
        lines.append("")
        lines.append("  !! memory supply now critical:")
        for t in tight:
            lines.append("  !! " + t)
    lines.append("")
    lines.append("  (un-mark to return these items to the world pool)")
    return "\n".join(lines)

def api_solve(body):
    target = by_name(solver.humans_, body.get("target", ""))
    if not target:
        return "pick a profession first"
    consumed = _consumed()
    grown = _grown().get(target["name"])
    if grown:
        return _fmt_grown(target["name"], grown)
    include_t = bool(body.get("include_transposium", False))
    memories = solver.memories_
    excl = set()
    if not include_t:
        excl = solver.transposium_only_memories()
        memories = [m for m in memories if m["name"] not in excl]
    avail_full = {i["name"]: i["avail"] for i in solver.foods_ + solver.memories_}
    for n in excl:
        avail_full[n] = 0
    for k, v in consumed.items():          # copies already spent are gone
        if k in avail_full:
            avail_full[k] = max(0, avail_full[k] - v)
    chosen = None
    source = None
    gp = _load_global_plan()
    if gp is not None:
        # a plan computed under the OTHER transposium mode doesn't apply
        plan_t = bool(gp.get("_meta", {}).get("transposium", True))
        if plan_t != include_t:
            gp = None
    want_plan = body.get("plan", True)
    if gp and want_plan and not body.get("solo") and target["name"] in gp:
        chosen = gp[target["name"]]
        source = "from the GLOBAL plan — whole-set allocation against real world counts"
    if chosen is None:
        avail = None if (not want_plan and not gp) else avail_full
        res = solver.solve_combo(target, solver.foods_, memories,
                                 solver.humans_, avail=avail)
        if not res:
            return f"INFEASIBLE: not enough items in the world for {target['name']} at current scarcity"
        chosen, totals, matched = res
        source = "solo solve — ignores what the other 39 humans will take" if not want_plan \
            else "solo solve (global plan did not cover this human)"
        gused = None
    else:
        totals = _totals_of(chosen)
        matched = solver.satisfied(totals, solver.humans_)
        gused = _global_usage()
    if include_t:
        source += " · Transposium INCLUDED"
    else:
        source += " · Transposium excluded"
    mem_names = {m["name"]: m["avail"] for m in solver.memories_}
    LAST_RECIPE[target["name"]] = {
        "chosen": chosen, "transposium": include_t,
        "spare_pct": (_plan_meta() or {}).get("spare_pct", 0)}
    lines = [f"RECIPE for {target['name']}", f"  {source}"]
    exhaust = []
    if consumed and gused:
        over = [f"{k}: the cached plan claims {gused.get(k,0)}, but only "
                f"{mem_names.get(k,0)} exist and {consumed.get(k,0)} "
                f"were already spent by grown humans"
                for k in gused
                if k in mem_names and gused.get(k, 0) + consumed.get(k, 0) > mem_names[k]]
        if over:
            lines.append(f"  !! this GLOBAL plan row ignores grown humans — "
                         "re-calculate to rebalance:")
            for o in over:
                lines.append("  !! " + o)
    mem_lines, food_lines = [], []
    for k, v in sorted(chosen.items(), key=lambda kv: (-kv[1], kv[0])):
        if k in mem_names:
            tot = gused.get(k) if gused else v
            if gused and tot >= mem_names[k]:
                tag = f"  !! LAST ONES — all {mem_names[k]} in the world go to the plan, this human takes {v}"
                exhaust.append(k)
            else:
                tag = f"  {v} used by this human; plan total {tot}/{mem_names[k]} of all that exist" if gused \
                    else f"  {v}/{mem_names[k]} of all that exist"
            mem_lines.append(f"  ◆ {v:>3} x {k}" + rsv_star(k) + tag)
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
        for entry in body.get(key, []):
            if isinstance(entry, dict):
                name, n = entry.get("name", ""), max(1, int(entry.get("count", 1) or 1))
            else:
                name, n = entry, 1
            it = by_name(items, name)
            if not it:
                unknown.append(name); continue
            v = solver.stat_vec(it, kind)
            for s in range(15):
                totals[s] += n * v[s]
            count += n
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

def reserve_data():
    """Structured reserve list from the current plan. Returns list of dicts."""
    plan = _load_global_plan()
    if not plan:
        try:
            pj = json.load(open(_state("plan.json")))
            plan = {x["profession"]: x["items"] for x in pj if x["items"]}
        except Exception:
            return []
    mem_avail = {m["name"]: m["avail"] for m in solver.memories_}
    grown = _grown()
    used_by = {}
    def claim(mem, who, cnt, done=False):
        used_by.setdefault(mem, []).append([who, cnt, done])
    for human, items in plan.items():
        if human in grown:
            continue   # already grown: its copy is history, not a future claim
        for k, v in items.items():
            if k in mem_avail and isinstance(v, int):
                claim(k, human, v)
    for human, rec in grown.items():      # frozen: what was actually spent
        for k, v in rec["recipe"].items():
            if k in mem_avail and isinstance(v, int):
                claim(k, human + " (grown)", v, True)
    out = []
    for m, claimers in used_by.items():
        total = sum(c for _, c, _ in claimers)
        future = sum(c for _, c, d in claimers if not d)
        slack = mem_avail[m] - total
        if future < 0.6 * mem_avail[m] and total < 0.6 * mem_avail[m]:
            continue   # not reserve-worthy; general stash is fine
        if slack <= 0:
            verdict = "ZERO SPARE — reserve every single one"
        elif slack <= 2:
            verdict = f"only {slack} spare in the world — treat as reserved"
        else:
            verdict = f"{slack} spare — reserve these {total}, extras general"
        where = MEMORY_NOTES.get(m) or MEMORY_LOCATIONS.get(m)
        if isinstance(where, list):
            where = ", ".join(where[:6]) + ("…" if len(where) > 6 else "")
        out.append({"name": m, "world": mem_avail[m], "plan": total,
                    "slack": slack, "verdict": verdict, "where": where or "",
                    "claimers": sorted(claimers, key=lambda x: -x[1])})
    out.sort(key=lambda r: r["slack"])
    return out

def api_reserve(body):
    rows = reserve_data()
    if not rows:
        return "no plan available yet"
    lines = ["RESERVE LIST (click a name in the UI for details)"]
    for r in rows:
        lines.append(f"  {r['name']} — {r['verdict']}")
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

if __name__ == "__main__":
    import sys
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    print(f"http://{host}:{PORT}")
    ThreadingHTTPServer((host, PORT), H).serve_forever()
