"""Audit chiffre de la base du jeu pour le butin Wowlheim (lecture seule). usage : python audit.py"""
import os, sys, collections, statistics
sys.stdout.reconfigure(encoding="utf8")
sys.path.insert(0, os.path.dirname(__file__))
import classify, rules
from common import sql

info = classify.load()
ct = info["ct"]
sp = info["spawns"]
print("creature_template : %d modeles ; apparitions sur cartes 0/1 : %d (sur %d modeles)" % (len(ct), sum(len(v) for v in sp.values()), sum(1 for e in sp if e in ct)))
print("\nExclusions (premier motif rencontre) :")
for k, v in info["reasons"].most_common():
    print("  %-52s %5d" % (k, v))
el = [t for t in ct.values() if not t["why_not"]]
print("\nModeles eligibles : %d (%d apparitions) ; LootId distincts eligibles : %d ; LootId partages entre plusieurs modeles : %d" % (
    len(el), sum(t["nspawn"] for t in el), len(info["loot_ok"]), sum(1 for v in info["groups"].values() if len(v) > 1)))
ndup = [lid for lid, v in info["groups"].items() if len(v) > 1]
print("  groupe(s) partage(s) : %s" % [(lid, [m["name"] for m in info["groups"][lid]][:4]) for lid in ndup])
miss = [t for t in ct.values() if t["lootid"] == 0 and t["nspawn"] > 0 and t["rank"] in (0, 1) and t["type"] not in (0, 8, 11) and not t["npcflags"] and not t["civ"]]
print("  creatures vivantes sans aucun butin (LootId=0, hors PNJ) : %d modeles, %d apparitions : non touchees" % (len(miss), sum(t["nspawn"] for t in miss)))
print("\nEligibles par categorie x palier (modeles / apparitions) :")
agg = collections.defaultdict(lambda: [0, 0])
for t in el:
    agg[(t["cat"], t["tier"])][0] += 1
    agg[(t["cat"], t["tier"])][1] += t["nspawn"]
print("%-15s" % "categorie" + "".join("   T%d mod/spawn " % t for t in range(1, 6)))
for cat in rules.ASSIGNABLE:
    print("%-15s" % cat + "".join("  %4d/%-7d" % tuple(agg[(cat, t)]) for t in range(1, 6)))
print("%-15s" % "TOTAL" + "".join("  %4d/%-7d" % (sum(agg[(c, t)][0] for c in rules.ASSIGNABLE), sum(agg[(c, t)][1] for c in rules.ASSIGNABLE)) for t in range(1, 6)))
print("\nTypes de creature bruts (modeles avec LootId>0, apparitions continents) :")
print("  type(CreatureType) -> modeles eligibles : %s" % dict(sorted(collections.Counter(t["type"] for t in el).items())))
print("\nZones (>= 30 apparitions de creatures eligibles) : niveau median, palier, faction (manuelle)")
lv = collections.defaultdict(list)
for e, sps in sp.items():
    t = ct.get(e)
    if not t or t["why_not"]:
        continue
    for s in sps:
        lv[(s[0], s[3], s[4])].append(t["level"])
for k, v in sorted(lv.items(), key=lambda kv: (kv[0][0], statistics.median(kv[1]))):
    if len(v) >= 30 and k[1]:
        print("  carte %d  %-26s apparitions %5d  niveau median %5.1f -> palier %d  faction %s" % (k[0], k[2], len(v), statistics.median(v), rules.tier_of_level(statistics.median(v)), rules.zone_faction(k[1])))
