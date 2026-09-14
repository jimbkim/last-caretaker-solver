#!/usr/bin/env python3
"""Build data/memory_locations.json: for each memory, which wiki location pages
mention it (insource search). Run: .venv/bin/python fetch_locations.py"""
import urllib.request, urllib.parse, json, time, csv, os

API = "https://thelastcaretaker.wiki.gg/api.php"
HERE = os.path.dirname(os.path.abspath(__file__))

def api(params):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "tlc-solver/1.0"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

names = [m['Memory'] for m in csv.DictReader(
    open(os.path.join(HERE, 'data/memories.csv')), delimiter=';')]
SKIP = {'Memories', 'Humans', 'Food', 'Memory', 'Locations', 'Samples', 'Quests'}

where = {}
for n in names:
    q = 'insource:"' + n + '"'
    try:
        r = api({"action": "query", "list": "search", "srsearch": q,
                 "format": "json", "srlimit": 15})
        hits = [h["title"] for h in r["query"]["search"]]
    except Exception:
        hits = []
    where[n] = [h for h in hits if h not in SKIP and h.replace("_", " ") != n]
    print(n, "->", where[n][:6])
    time.sleep(0.2)

json.dump(where, open(os.path.join(HERE, 'data/memory_locations.json'), 'w'), indent=1)
print("wrote data/memory_locations.json")
