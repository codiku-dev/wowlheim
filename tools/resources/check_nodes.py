"""Controles automatiques du monde Valheim (arbres, roches, filons, ramassables) sur une base ou 001-012 ont ete appliques
(wl_scratch2, voir validate_nodes_scratch.py), compares a C:\\Wowlheim\\data\\wl_terrain\\placements.json et aux regles (rules.py).

usage : python check_nodes.py [--db wl_scratch2] [--baseline classicmangos]
  --db        base controlee (defaut wl_scratch2)
  --baseline  base de reference (lignes `gameobject` hors plages Wowlheim identiques ; PNJ et departs lus ici)
Code retour : 0 = tout OK ; 1 = au moins une erreur de forme ; 3 = formes OK mais constats de couverture.
Rien n'est ecrit dans aucune base. Zones et terrain : fichiers .map du serveur (nodes_terrain.py, common.zone_of), INDEPENDANTS des ADT
du client lus par place_resources.py."""
import os, sys, math, argparse, collections, json
sys.stdout.reconfigure(encoding="utf8")
sys.path.insert(0, os.path.dirname(__file__))
from common import sql, zone_of, area_table, read_dbc
import rules, classify, generate
import nodes_terrain as nt
from nodes_common import *

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="wl_scratch2")
ap.add_argument("--baseline", default="classicmangos")
args = ap.parse_args()
DB, BASE = args.db, args.baseline
errors, gaps = [], []
PICK_MIN, PICK_MAX = 9130001, 9130099
CRE_MIN, CRE_MAX = 9600001, 9699999


def sect(t):
    print("\n" + "=" * 100 + "\n" + t + "\n" + "=" * 100)


def ok(label, cond, detail=""):
    print("   [%s] %s %s" % ("OK" if cond else "ECHEC", label, detail))
    if not cond:
        errors.append(label + " " + detail)


by_id, _ = area_table()
pls = read_placements()
kinds = collections.Counter(p["key"] for p in pls)
n_pick = sum(1 for p in pls if rules.PLACEMENT[p["key"]]["kind"] == "pickable")
n_cre = len(pls) - n_pick

sect("0. DONNEES : placements.json (%d) ; base %s" % (len(pls), DB))
print("   creatures-ressources %d, ramassables %d ; par type : %s" % (n_cre, n_pick, dict(sorted(kinds.items()))))
print("   par palier : %s" % dict(sorted(collections.Counter(p["tier"] for p in pls).items())))

sect("1. ANCIENS NOEUDS GAMEOBJECT AUX MODELES WoW (9101001-9101999) : SUPPRIMES")
for t, col in (("gameobject_template", "entry"), ("gameobject_loot_template", "entry"), ("gameobject", "id")):
    n = int(sql("select count(*) from %s where %s between %d and %d" % (t, col, NODE_ENTRY_MIN, NODE_ENTRY_MAX), DB)[0][0])
    ok("%s : aucune ligne 9101xxx" % t, n == 0, "(%d)" % n)
n = int(sql("select count(*) from wowlheim_node", DB)[0][0])
ok("wowlheim_node vide (plus aucun noeud a outil requis)", n == 0, "(%d)" % n)

sect("2. RAMASSABLES (GameObjects coffre sans verrou, un clic sans outil)")
gdisp = {r[0] for r in read_dbc("GameObjectDisplayInfo.dbc")[0]}
tm = {int(r[0]): r for r in sql("select entry, type, displayId, name, data0, data1, data3 from gameobject_template where entry between %d and %d" % (PICK_MIN, PICK_MAX), DB)}
ok("modeles de ramassables presents", len(tm) == len({pf for p in rules.PLACEMENTS if p["kind"] == "pickable" for pf, _w in p["prefabs"]}), "(%d)" % len(tm))
for e, r in sorted(tm.items()):
    ok("%d %s : type 3, sans verrou, butin = entree, disparait une fois pris" % (e, r[3]),
       r[1] == "3" and r[4] == "0" and int(r[5]) == e and r[6] == "1")
    ok("%d : displayId %s present dans GameObjectDisplayInfo.dbc (patch Valheim)" % (e, r[2]), int(r[2]) in gdisp)
loot = sql("select l.entry, l.item, l.mincountOrRef, i.name from gameobject_loot_template l left join item_template i on i.entry = l.item "
           "where l.entry between %d and %d" % (PICK_MIN, PICK_MAX), DB)
ok("chaque ramassable a un butin d'objet existant", {int(r[0]) for r in loot} == set(tm) and all(r[3] for r in loot),
   "(%s)" % ", ".join("%s x%s" % (r[3], r[2]) for r in loot))
gos = sql("select guid, id, map, position_x, position_y, position_z, spawntimesecsmin from gameobject where id between %d and %d" % (PICK_MIN, PICK_MAX), DB)
ok("nombre de ramassables en base = placements", len(gos) == n_pick, "(%d / %d)" % (len(gos), n_pick))
ok("guid des ramassables dans %d-%d (sous les pieces posees)" % (PICKABLE_GUID_MIN, PICKABLE_GUID_MAX),
   all(PICKABLE_GUID_MIN <= int(g[0]) <= PICKABLE_GUID_MAX for g in gos))
ok("reapparition > 0", all(int(g[6]) > 0 for g in gos), "(%s s)" % sorted({int(g[6]) for g in gos}))

sect("3. CREATURES-RESSOURCES (arbres, roches, filons)")
cre = sql("select c.guid, c.id, c.map, c.position_x, c.position_y, c.position_z, t.Entry, w.entry, m.modelid from creature c "
          "left join creature_template t on t.Entry = c.id left join wowlheim_tree w on w.entry = c.id "
          "left join creature_model_info m on m.modelid = t.DisplayId1 where c.guid between %d and %d" % (CRE_MIN, CRE_MAX), DB)
ok("nombre de creatures-ressources en base = placements", len(cre) == n_cre, "(%d / %d)" % (len(cre), n_cre))
ok("chaque creature-ressource a un modele, une entree wowlheim_tree et un creature_model_info", all(r[6] and r[7] and r[8] for r in cre))
db_pos = collections.Counter((int(r[2]), round(float(r[3]), 1), round(float(r[4]), 1)) for r in list(cre) + [(0, 0) + tuple(g[2:5]) for g in gos])
js_pos = collections.Counter((p["map"], round(p["x"], 1), round(p["y"], 1)) for p in pls)
ok("positions en base = positions de placements.json", db_pos == js_pos, "(%d ecarts)" % sum((db_pos - js_pos).values()))

sect("4. PALIERS : type autorise au palier, palier = palier de la zone (zone recalculee avec les .map du serveur)")
info = classify.load()
zt = generate.zone_tiers(info)
bad_tier = [p for p in pls if p["tier"] not in rules.PLACEMENT[p["key"]]["tiers"]]
ok("chaque type est dans un de ses paliers (rules.PLACEMENTS)", not bad_tier, "(%d)" % len(bad_tier))
mism = collections.Counter()
higher = []
for p in pls:
    z = zone_of(p["map"], p["x"], p["y"])
    t = zt.get((p["map"], z[0]))[0] if z and (p["map"], z[0]) in zt else None
    if t != p["tier"]:
        mism[(p["key"], p["tier"], t)] += 1
        if t is not None and rules.PLACEMENT[p["key"]]["tier"] > t:
            higher.append((p["key"], p["tier"], t, z[1] if z else None))
print("   palier de placements.json different du palier recalcule (zone .map) : %d sur %d %s" % (sum(mism.values()), len(pls), dict(mism.most_common(8))))
ok("AUCUN type d'un palier superieur dans une zone de palier inferieur (zone .map)", not higher,
   "(%d : %s)" % (len(higher), collections.Counter((h[0], h[3]) for h in higher).most_common(5)))

sect("5. TERRAIN : z, eau, berges")
dz = [abs(p["z"] - nt.height(p["map"], p["x"], p["y"])) for p in pls if nt.height(p["map"], p["x"], p["y"]) is not None]
ok("z a moins de 1,5 m du terrain statique (.map)", sum(1 for d in dz if d > 1.5) <= len(dz) // 100,
   "(%d au-dela sur %d ; mediane %.2f m)" % (sum(1 for d in dz if d > 1.5), len(dz), sorted(dz)[len(dz) // 2]))
wet = [p for p in pls if nt.has_water(p["map"], p["x"], p["y"])]
ok("aucun placement dans l'eau (.map)", len(wet) <= len(pls) // 500, "(%d)" % len(wet))
for k in ("flint", "thistle", "tin"):
    lst = [p for p in pls if p["key"] == k]
    far = [p for p in lst if nt.water_distance(p["map"], p["x"], p["y"], 15.0) is None]
    ok("%s sur les berges : eau a moins de 15 m (.map)" % k, len(far) <= max(1, len(lst) // 10), "(%d sur %d sans eau a 15 m)" % (len(far), len(lst)))

sect("6. EXCLUSIONS (recalculees depuis %s et 010)" % BASE)
npc = PointIndex(100.0)
for m, x, y in sql("select c.map, c.position_x, c.position_y from creature c join creature_template t on t.Entry = c.id "
                   "where c.map in (0,1) and (t.NpcFlags <> 0 or t.Civilian <> 0 or (t.ExtraFlags & %d))" % NPC_FLAG_GUARD_EXTRA, BASE):
    npc.add(int(m), float(x), float(y))
nb = PointIndex(100.0)
for (m, x, y, rad, nm) in load_nobuild_points():
    nb.add(m, x, y)
near_npc = sum(1 for p in pls if npc.near(p["map"], p["x"], p["y"], NPC_EXCL_RADIUS - 0.5))
near_nb = sum(1 for p in pls if nb.near(p["map"], p["x"], p["y"], NODE_EXCL_RADIUS - 0.5))
ok("aucun placement a moins de 50 m d'un PNJ/civil/garde", near_npc == 0, "(%d)" % near_npc)
ok("aucun placement a moins de 100 m d'un point 010", near_nb == 0, "(%d)" % near_nb)

sect("7. DEPART ET PROGRESSION")
kit = sql("select itemid, count(*) from playercreateinfo_item where itemid between 9200001 and 9299999 or itemid = 9201100 group by itemid", DB)
ok("kit de depart = le marteau seul", [r[0] for r in kit] == ["9201100"], "(%s)" % kit)
nv = int(sql("select count(*) from npc_vendor where item between 9200001 and 9299999", DB)[0][0])
ok("aucun vendeur de materiaux/outils Wowlheim", nv == 0, "(%d)" % nv)
ok("plus d'outils inventes (argent, pioche en sombracier)", not sql("select entry from item_template where entry in (9201041, 9201042, 9201052)", DB))
axe = sql("select r.station from wowlheim_recipe r where r.output_item = 9201010", DB)
ok("hache en pierre fabricable a la main (sans station)", axe == [("",)], "(%s)" % axe)
wb = sql("select item_id, count from wowlheim_piece_cost c join wowlheim_piece_template t on t.id = c.piece_id where t.prefab = 'piece_workbench'", DB)
ok("etabli = 10 Bois", wb == [("9200001", "10")], "(%s)" % wb)
rec = sql("select r.id, r.name, r.station, r.min_station_level, (select count(*) from wowlheim_recipe_ingredient i left join item_template it on it.entry = i.item_id "
          "where i.recipe_id = r.id and it.entry is null), (select count(*) from item_template it where it.entry = r.output_item) from wowlheim_recipe r order by r.id", DB)
ok("recettes : ingredients et sorties existent", all(r[4] == "0" and r[5] == "1" for r in rec), "(%d recettes)" % len(rec))
for r in rec:
    print("      %s %-24s station %-12s niveau %s" % (r[0], r[1], r[2] or "(a la main)", r[3]))
starts = sql("select distinct race, map, position_x, position_y from playercreateinfo", BASE)
for race, m, x, y in starts:
    m, x, y = int(m), float(x), float(y)
    c = collections.Counter(p["key"] for p in pls if p["map"] == m and math.hypot(p["x"] - x, p["y"] - y) < 600)
    print("   race %s : a moins de 600 m du depart : branches %d, pierres %d, hetres %d, silex %d, framboises %d, champignons %d"
          % (race, c["branch"], c["stone"], c["beech"], c["flint"], c["raspberry"], c["mushroom"]))
    if c["branch"] < 15:
        gaps.append("depart de la race %s : %d branches a moins de 600 m (15 Bois necessaires : etabli 10 + hache en pierre 5)" % (race, c["branch"]))

sect("8. BASE : lignes `gameobject` hors plages Wowlheim identiques a %s" % BASE)
cond = "not (id between %d and %d) and not (id between %d and %d) and not (id between 9100001 and 9119999)" % (NODE_ENTRY_MIN, NODE_ENTRY_MAX, PICK_MIN, PICK_MAX)
a = sql("select count(*), sum(crc32(guid)) from gameobject where %s" % cond, DB)[0]
b = sql("select count(*), sum(crc32(guid)) from gameobject where %s" % cond, BASE)[0]
ok("gameobject hors plages Wowlheim identiques", a == b, "(%s lignes)" % a[0])

sect("COUVERTURE (constats) : zones par continent x faction x type (>= %d placements dans la zone ; exige min(%d, zones exigibles))" % (MIN_COUNTED, MIN_ZONES))
cov_gaps, cov_struct = coverage_report(pls, zt)
for (m, fac, k, cov, elig) in cov_struct:
    print("   structurel (moins de %d zones exigibles, toutes couvertes) : carte %d faction %s type %s : %s" % (MIN_ZONES, m, fac, k, cov))
for (m, fac, k, cov, elig) in cov_gaps:
    gaps.append("carte %d faction %s type %s (paliers %s) : %d zone(s) couverte(s) %s sur %d exigible(s) %s" % (
        m, fac, k, rules.PLACEMENT[k]["tiers"], len(cov), cov, len(elig), elig))
for g in gaps:
    print("   CONSTAT :", g)

sect("RESULTAT")
if errors:
    print("ECHEC : %d erreur(s) de forme" % len(errors))
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("Formes : TOUTES OK ; %d constat(s) de couverture." % len(gaps))
sys.exit(3 if gaps else 0)
