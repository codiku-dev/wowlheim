"""Controles automatiques des noeuds de production (008) sur une base ou 003/005/008/010 ont ete appliques (wl_scratch2 pour la validation).

usage : python check_nodes.py [--db wl_scratch2] [--baseline classicmangos]
  --db        base controlee (defaut wl_scratch2)
  --baseline  base de reference SANS 008 : les lignes `gameobject` hors production doivent y etre identiques (compte + somme de controle)
Code retour : 0 = tout OK ; 1 = au moins une erreur de forme ; 3 = formes OK mais constats de couverture (voir « COUVERTURE »).
Rien n'est ecrit dans la base. Les cartes (.map) du client servent a la zone, au terrain et a l'eau (nodes_terrain.py)."""
import os, sys, math, argparse, collections, statistics
sys.stdout.reconfigure(encoding="utf8")
sys.path.insert(0, os.path.dirname(__file__))
from common import sql, zone_of, area_table
import rules, classify, generate
import nodes_terrain as nt
from nodes_common import *

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="wl_scratch2")
ap.add_argument("--baseline", default=None)
args = ap.parse_args()
DB = args.db
errors = []
gaps = []


def err(msg):
    errors.append(msg)
    print("   ECHEC :", msg)


def sect(t):
    print("\n" + "=" * 100 + "\n" + t + "\n" + "=" * 100)


def ok(label, cond, detail=""):
    print("   [%s] %s %s" % ("OK" if cond else "ECHEC", label, detail))
    if not cond:
        errors.append(label + " " + detail)


by_id, _ = area_table()
aflags = area_flags()

# ------------------------------------------------------------------ chargement
sect("0. DONNEES (base : %s)" % DB)
rows = sql("select guid, id, map, position_x, position_y, position_z, orientation, rotation2, rotation3, spawntimesecsmin, spawntimesecsmax, spawnMask "
           "from gameobject where guid >= %d" % GUID_MIN, DB)
prod = [dict(guid=int(r[0]), id=int(r[1]), map=int(r[2]), x=float(r[3]), y=float(r[4]), z=float(r[5]), o=float(r[6]), r2=float(r[7]), r3=float(r[8]),
             smin=int(r[9]), smax=int(r[10]), mask=int(r[11])) for r in rows]
val = sql("select guid, id, map, position_x, position_y from gameobject where guid between 9500001 and 9500999 and id between %d and %d" % (NODE_ENTRY_MIN, NODE_ENTRY_MAX), DB)
print("noeuds de production (guid >= %d) : %d ; noeuds de validation 005 (9500001-9500999, id de noeud ; les pieces de construction posees par le serveur y ont aussi des guid) : %d" % (GUID_MIN, len(prod), len(val)))
tmpl = {int(r[0]): r[1] for r in sql("select entry, name from gameobject_template where entry between %d and %d" % (NODE_ENTRY_MIN, NODE_ENTRY_MAX), DB)}

# ------------------------------------------------------------------ 1. guid, plafond, modeles
sect("1. GUID, PLAFOND, MODELES")
ok("au moins un noeud de production", len(prod) > 0, "(%d)" % len(prod))
ok("guid de production dans %d-%d" % (GUID_MIN, GUID_MAX), all(GUID_MIN <= p["guid"] <= GUID_MAX for p in prod),
   "(min %d, max %d)" % (min(p["guid"] for p in prod), max(p["guid"] for p in prod)))
ok("toute ligne gameobject de guid >= %d est un noeud (id %d-%d)" % (GUID_MIN, NODE_ENTRY_MIN, NODE_ENTRY_MAX),
   all(NODE_ENTRY_MIN <= p["id"] <= NODE_ENTRY_MAX for p in prod))
ok("guid uniques et contigus (generateur)", len({p["guid"] for p in prod}) == len(prod) and max(p["guid"] for p in prod) - GUID_MIN + 1 == len(prod))
ok("plafond total <= %d noeuds" % TOTAL_CAP, len(prod) <= TOTAL_CAP, "(%d)" % len(prod))
ids = {p["id"] for p in prod}
ok("chaque id existe dans gameobject_template", ids <= set(tmpl), "(ids absents : %s)" % sorted(ids - set(tmpl)))
ok("chaque id est un modele de noeud de rules.py", ids <= set(rules.NODE), "(%s)" % sorted(ids - set(rules.NODE)))
print("   types de noeuds utilises : %d / %d" % (len(ids), len(rules.NODES)))
bad = [p["guid"] for p in prod if (p["smin"], p["smax"]) != tuple(rules.NODE[p["id"]]["respawn"]) or p["mask"] != 1]
ok("reapparition = celle du type (courte) et spawnMask 1", not bad, "(%d ecarts)" % len(bad))
bad = [p["guid"] for p in prod if abs(p["r2"] - math.sin(p["o"] / 2)) > 1e-5 or abs(p["r3"] - math.cos(p["o"] / 2)) > 1e-5]
ok("rotation derivee de l'orientation", not bad, "(%d ecarts)" % len(bad))
ok("validation 005 intacte : 118 noeuds, guid 9500001-9500118", len(val) == 118 and min(int(v[0]) for v in val) == 9500001 and max(int(v[0]) for v in val) == 9500118)
cmx = sql("select max(guid) from gameobject where guid < %d" % GUID_MIN, DB)[0][0]
print("   max(guid) hors production dans %s : %s (< %d : plage libre)" % (DB, cmx, GUID_MIN))
if args.baseline:
    r0 = sql("select max(guid), count(*) from gameobject", args.baseline)[0]
    print("   %s : max(guid) = %s, %s lignes (aucune ligne de production avant application : %s)" % (
        args.baseline, r0[0], r0[1], "OUI" if int(sql("select count(*) from gameobject where guid >= %d" % GUID_MIN, args.baseline)[0][0]) == 0 else "NON (008 deja appliquee ?)"))
    q = ("select count(*), coalesce(sum(crc32(concat_ws('|',guid,id,map,position_x,position_y,position_z,orientation,rotation0,rotation1,rotation2,rotation3,spawntimesecsmin,spawntimesecsmax,spawnMask))),0) "
         "from gameobject where not (guid >= %d and id between %d and %d) and id not between 9100001 and 9100999" % (GUID_MIN, NODE_ENTRY_MIN, NODE_ENTRY_MAX))
    a, b = sql(q, DB)[0], sql(q, args.baseline)[0]
    ok("lignes gameobject hors production et hors pieces de construction (id 9100001-9100999, posees en direct par le serveur) identiques a %s (compte + somme crc32)" % args.baseline, a == b, "(%s lignes, somme %s)" % (a[0], a[1]))

# ------------------------------------------------------------------ 2. exclusions
sect("2. EXCLUSIONS (villes, villages, camps)")
pts = [(int(r[0]), float(r[1]), float(r[2]), float(r[3]), r[4]) for r in sql("select map, x, y, radius, name from wowlheim_no_build_point", DB)]
print("points d'exclusion lus dans %s.wowlheim_no_build_point : %d (rayon de la table %s m ; rayon cote noeuds %.0f m)" % (
    DB, len(pts), sorted({p[3] for p in pts}), NODE_EXCL_RADIUS))
ok("table des points d'exclusion = fichier 010 (%d points)" % len(load_nobuild_points()), len(pts) == len(load_nobuild_points()))
mind = {}
for p in prod:
    for (m, x, y, rad, nm) in pts:
        if m == p["map"]:
            d = math.hypot(p["x"] - x, p["y"] - y)
            if d < mind.get(p["guid"], (1e9,))[0]:
                mind[p["guid"]] = (d, nm)
viol = [(g, v) for g, v in mind.items() if v[0] < NODE_EXCL_RADIUS]
ok("aucun noeud a moins de %.0f m d'un point d'exclusion (010)" % NODE_EXCL_RADIUS, not viol,
   "(plus proche : %.1f m de « %s »)" % min((v for v in mind.values()), key=lambda v: v[0]) if mind else "")
viol70 = [g for g, v in mind.items() if v[0] < 70]
ok("aucun noeud dans le rayon 70 m de la table (010)", not viol70)
# creatures a drapeaux PNJ
npcs = sql("select c.map, c.position_x, c.position_y from creature c left join creature_spawn_entry e on c.id=0 and e.guid=c.guid "
           "join creature_template t on t.Entry = if(c.id=0, e.entry, c.id) where c.map in (0,1) and (t.NpcFlags<>0 or t.Civilian<>0 or (t.ExtraFlags & %d)<>0)" % NPC_FLAG_GUARD_EXTRA, DB)
npc_idx = PointIndex()
for m, x, y in npcs:
    npc_idx.add(int(m), float(x), float(y))
viol = [p["guid"] for p in prod if npc_idx.near(p["map"], p["x"], p["y"], NPC_EXCL_RADIUS - 0.01)]
ok("aucun noeud a moins de %.0f m d'une creature a drapeaux PNJ / civile / garde (%d creatures)" % (NPC_EXCL_RADIUS, len(npcs)), not viol, "(%d violations)" % len(viol))

# ------------------------------------------------------------------ 3. positions : provenance, doublons, espacements
sect("3. POSITIONS : PROVENANCE, DOUBLONS, ESPACEMENTS")
cre = collections.defaultdict(list)
for r in sql("select c.guid, c.map, c.position_x, c.position_y, c.position_z, c.orientation, if(c.id=0, e.entry, c.id) from creature c "
             "left join creature_spawn_entry e on c.id=0 and e.guid=c.guid where c.map in (0,1) and (c.id>0 or e.entry is not null)", DB):
    cre[(int(r[1]), int(math.floor(float(r[2]))), int(math.floor(float(r[3]))))].append((int(r[0]), float(r[4]), float(r[5]), int(r[6]), float(r[2]), float(r[3])))
tinfo = {int(r[0]): r for r in sql("select Entry, `Rank`, CreatureType, NpcFlags, Civilian, InhabitType, MinLevel, MaxLevel from creature_template", DB)}
nomatch = []
src = {}
for p in prod:
    c = None
    fx, fy = int(math.floor(p["x"])), int(math.floor(p["y"]))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for cand in cre.get((p["map"], fx + dx, fy + dy), ()):
                if abs(cand[4] - p["x"]) < 0.001 and abs(cand[5] - p["y"]) < 0.001 and abs(cand[1] - p["z"]) < 0.001 and abs(cand[2] - p["o"]) < 0.001:
                    c = cand
    if c is None:
        nomatch.append(p["guid"])
    else:
        src[p["guid"]] = c
ok("chaque noeud est a la position (x, y), z et orientation d'une creature de `creature` (rien d'invente)", not nomatch, "(%d / %d, %d sans creature)" % (len(prod) - len(nomatch), len(prod), len(nomatch)))
badc = [g for g, c in src.items() if int(tinfo[c[3]][1]) != 0 or int(tinfo[c[3]][2]) in (8, 11) or int(tinfo[c[3]][3]) != 0 or not int(tinfo[c[3]][5]) & 1 or int(tinfo[c[3]][5]) & 4 or (int(tinfo[c[3]][7]) <= 1 and int(tinfo[c[3]][2]) in (9, 10))]
ok("creature source : non elite, ni critter ni totem, sans drapeaux PNJ, au sol, ni assistant invisible (niveau <= 1, type 9/10)", not badc, "(%d ecarts)" % len(badc))
dup = collections.Counter((p["map"], round(p["x"], 2), round(p["y"], 2)) for p in prod)
dup.update((int(v[2]), round(float(v[3]), 2), round(float(v[4]), 2)) for v in val)
ok("aucun doublon de position (a 1 cm pres) entre noeuds de production et de validation", all(n == 1 for n in dup.values()), "(%d doublons)" % sum(1 for n in dup.values() if n > 1))
allp = [(p["map"], p["x"], p["y"], p["id"]) for p in prod] + [(int(v[2]), float(v[3]), float(v[4]), int(v[1])) for v in val]
mn = 1e9
# espacement minimal : parcours par cellule (voisins de la cellule 50 m, 25 suffisent pour 12 m ; on teste jusqu'a 60 m pour le meme type)
by_cell = collections.defaultdict(list)
for m, x, y, i in allp:
    by_cell[(m, int(math.floor(x / 160)), int(math.floor(y / 160)))].append((x, y, i))
close_any = []
for (m, cx, cy), lst in by_cell.items():
    for a in range(len(lst)):
        x, y, i = lst[a]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for (x2, y2, i2) in by_cell.get((m, cx + dx, cy + dy), ()):
                    if (x2, y2, i2) == (x, y, i):
                        continue
                    d = math.hypot(x - x2, y - y2)
                    mn = min(mn, d)
                    if d < SPACING_ANY - 0.01:
                        close_any.append((m, round(x), round(y), d))
ok("espacement minimal entre deux noeuds quelconques >= %.0f m (production et 005)" % SPACING_ANY, not close_any, "(plus petit : %.1f m)" % mn)
# entre noeuds de production de meme type (l'espacement par type ne vise que la production)
prod_cell = collections.defaultdict(list)
for p in prod:
    prod_cell[(p["map"], p["id"], int(math.floor(p["x"] / 160)), int(math.floor(p["y"] / 160)))].append((p["x"], p["y"]))
bad_same = 0
mins = {}
for (m, i, cx, cy), lst in prod_cell.items():
    sp = SPACING_SAME[rules.NODE[i]["kind"]]
    for (x, y) in lst:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for (x2, y2) in prod_cell.get((m, i, cx + dx, cy + dy), ()):
                    if (x2, y2) != (x, y):
                        d = math.hypot(x - x2, y - y2)
                        mins[i] = min(mins.get(i, 1e9), d)
                        if d < sp - 0.01:
                            bad_same += 1
ok("espacement minimal entre noeuds de production du meme type (bois/pierre/plante 40 m, minerai 60 m, cache 150 m)", bad_same == 0,
   "(%d paires trop proches ; plus petit par type : %s)" % (bad_same, {k: round(v) for k, v in sorted(mins.items())}))

# ------------------------------------------------------------------ 4. terrain, eau, interieurs, villes
sect("4. TERRAIN, EAU, INTERIEURS (cartes .map du client)")
zd, nowater_bad, indoor_bad, city_bad, holes = [], 0, 0, 0, 0
zone_of_node = {}
for p in prod:
    h = nt.height(p["map"], p["x"], p["y"])
    if h is None:
        holes += 1
    else:
        zd.append(p["z"] - h)
    if nt.near_water(p["map"], p["x"], p["y"], WATER_MARGIN):
        nowater_bad += 1
    zz = zone_of(p["map"], p["x"], p["y"])
    zone_of_node[p["guid"]] = zz
    if zz is None:
        city_bad += 1
        continue
    if INDOOR.search(zz[3]):
        indoor_bad += 1
    if aflags.get(zz[2], 0) & CITY_FLAGS or aflags.get(zz[0], 0) & CITY_FLAGS:
        city_bad += 1
ok("terrain defini sous chaque noeud (pas de trou)", holes == 0, "(%d trous)" % holes)
ok("z de la creature a %.1f / +%.1f m du terrain statique" % (Z_TOL_DOWN, Z_TOL_UP), bool(zd) and all(Z_TOL_DOWN - 1e-6 <= d <= Z_TOL_UP + 1e-6 for d in zd),
   "(ecart min %.2f, max %.2f, moyenne %.2f ; terrain seul : modeles/vmaps non pris en compte)" % (min(zd), max(zd), statistics.mean(zd)))
ok("pas d'eau (%.0f m autour, test getLiquidStatus sans type)" % WATER_MARGIN, nowater_bad == 0, "(%d en eau)" % nowater_bad)
ok("aucune aire interieure (nom : Mine, Cave, Abbey, Crypt...)", indoor_bad == 0, "(%d)" % indoor_bad)
ok("aucune aire/zone de ville, capitale ou arene (drapeaux AreaTable, comme BuildingMgr.cpp)", city_bad == 0, "(%d)" % city_bad)

# ------------------------------------------------------------------ 5. zones, paliers, faction
sect("5. ZONES ET PALIERS")
zt = generate.zone_tiers(classify.load())
samples = [(m, x, y, lv) for (m, x, y, lv) in level_samples()]
disc_idx = disc_index(samples)


def tier_local(m, x, y):
    return local_tier_disc(disc_idx, m, x, y)


dz = collections.Counter()
dl = collections.Counter()
nozt = 0
for p in prod:
    t = rules.NODE[p["id"]]["tier"]
    zz = zone_of_node[p["guid"]]
    zti = zt.get((p["map"], zz[0]))
    if zti is None:
        nozt += 1
    else:
        dz[t - zti[0]] += 1
    tl = tier_local(p["map"], p["x"], p["y"])
    if tl is not None:
        dl[t - tl] += 1
ok("chaque noeud est dans une zone dotee d'un palier (niveau median >= 30 apparitions)", nozt == 0, "(%d sans)" % nozt)
print("   ecart (palier du noeud - palier de la zone) : %s" % dict(sorted(dz.items())))
ok("palier du noeud = palier de la zone ou un palier voisin (poche)", all(abs(k) <= 1 for k in dz), "(%d noeuds a l'ecart 0, %d a +/-1)" % (dz[0], sum(v for k, v in dz.items() if k)))
print("   ecart (palier du noeud - palier du niveau median des creatures a 300 m, controle independant) : %s" % dict(sorted(dl.items())))
ok("palier du noeud a +/-1 du niveau local (rayon 300 m)", all(abs(k) <= 1 for k in dl), "(%d exacts sur %d)" % (dl[0], sum(dl.values())))
zc = collections.Counter((p["map"], zone_of_node[p["guid"]][0]) for p in prod)
print("   noeuds par zone (%d zones) :" % len(zc))
for (m, z), n in sorted(zc.items()):
    print("      carte %d %-24s faction %s palier de zone T%s : %4d noeuds" % (m, by_id[z]["name"], rules.zone_faction(z), zt[(m, z)][0], n))

# ------------------------------------------------------------------ 6. densite
sect("6. DENSITE ET CHARGE")
blocks = collections.Counter((p["map"], int(math.floor(p["x"] / BLOCK_SIZE)), int(math.floor(p["y"] / BLOCK_SIZE))) for p in prod)
grids = collections.Counter((p["map"], int(32 - p["x"] / GRID_SIZE), int(32 - p["y"] / GRID_SIZE)) for p in prod)
ok("au plus %d noeuds de production par bloc de 1 km2" % BLOCK_CAP, max(blocks.values()) <= BLOCK_CAP, "(max %d, moyenne %.1f sur %d blocs occupes)" % (max(blocks.values()), statistics.mean(blocks.values()), len(blocks)))
ok("au plus %d noeuds de production par grille serveur (533 m)" % GRID_CAP, max(grids.values()) <= GRID_CAP, "(max %d, moyenne %.1f sur %d grilles occupees)" % (max(grids.values()), statistics.mean(grids.values()), len(grids)))
tot = int(sql("select count(*) from gameobject", DB)[0][0])
base_n = tot - len(prod)
print("   charge : %d GameObjects au total (%d hors production) ; +%.1f %% avec la production" % (tot, base_n, 100.0 * len(prod) / base_n))
print("   par continent : %s ; par palier : %s" % (dict(collections.Counter(p["map"] for p in prod)), dict(sorted(collections.Counter(rules.NODE[p["id"]]["tier"] for p in prod).items()))))
print("   par type : %s" % dict(sorted(collections.Counter(p["id"] for p in prod).items())))

# ------------------------------------------------------------------ 7. couverture
sect("7. COUVERTURE : >= %d zones par continent et par faction (une zone compte si >= %d noeuds du type)" % (MIN_ZONES, MIN_COUNTED))
nodes = [(p["map"], zone_of_node[p["guid"]][0], p["id"]) for p in prod]
by_type, by_res = coverage(nodes)
names = {n["entry"]: n["name"] for n in rules.NODES}
print("%-34s %-4s %s" % ("type de noeud", "pal.", "Royaumes de l'Est A / H | Kalimdor A / H  (nombre de zones)"))
for n in rules.NODES:
    cells = [len(by_type.get((m, f, n["entry"]), ())) for m in (0, 1) for f in "AH"]
    print("%-34s T%-3d %2d / %2d | %2d / %2d" % ("%d %s" % (n["entry"], n["name"]), n["tier"], *cells))
    for (m, f), c in zip(((0, "A"), (0, "H"), (1, "A"), (1, "H")), cells):
        if c < MIN_ZONES:
            gaps.append("type %d (%s) : continent %d, faction %s : %d zone(s)" % (n["entry"], n["name"], m, f, c))
print("\n%-34s %s" % ("ressource (noeuds a chance >= 20 %)", "Royaumes de l'Est A / H | Kalimdor A / H"))
res_items = sorted({it for (m, f, it) in by_res})
for it in res_items:
    cells = [len(by_res.get((m, f, it), ())) for m in (0, 1) for f in "AH"]
    print("%-34s %2d / %2d | %2d / %2d" % ("%d %s" % (it, rules.MAT[it]["name"]), *cells))
    for (m, f), c in zip(((0, "A"), (0, "H"), (1, "A"), (1, "H")), cells):
        if c < MIN_ZONES:
            gaps.append("ressource %d (%s) : continent %d, faction %s : %d zone(s)" % (it, rules.MAT[it]["name"], m, f, c))
missing = [it for n in rules.NODES for it, ch, _a, _b in n["loot"] if ch >= 20 and it not in res_items]
ok("toute ressource de nœud (chance >= 20 %) est couverte quelque part", not missing, "(%s)" % sorted(set(missing)))
print("\nZones par continent et palier (au moins un type compte) :")
tz = collections.defaultdict(set)
for (m, f, e), zs in by_type.items():
    for z in zs:
        tz[(m, rules.NODE[e]["tier"])].add(by_id[z]["name"])
for k in sorted(tz):
    print("   carte %d palier T%d : %d zones : %s" % (k[0], k[1], len(tz[k]), ", ".join(sorted(tz[k]))))
sect("RESULTAT")
if gaps:
    print("COUVERTURE : %d constat(s) < %d zones :" % (len(gaps), MIN_ZONES))
    for g in gaps:
        print("   MANQUE :", g)
else:
    print("COUVERTURE : toutes les combinaisons (type, continent, faction) et (ressource, continent, faction) ont >= %d zones" % MIN_ZONES)
print("ERREURS DE FORME : %d" % len(errors))
for e in errors:
    print("   -", e)
sys.exit(1 if errors else (3 if gaps else 0))
