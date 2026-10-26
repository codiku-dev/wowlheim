"""Genere server/sql/world/008_node_spawns_production.sql : noeuds de ressources de PRODUCTION (cartes 0 et 1).
Lecture seule de classicmangos (creatures) et des fichiers .map du client ; n'ecrit AUCUNE base.
usage : python gen_nodes_production.py [--stats]   (--stats : calcule et affiche sans ecrire le SQL)

Principe (details et limites : docs/RESOURCES_NODES.md) :
  1. candidats = positions de creatures (non elites, ni critter/totem, sans drapeaux PNJ, non civiles, au sol, non en patrouille de
     waypoints) ; z et orientation viennent de la creature ; exclusions : villes/villages/camps, interieurs, eau, ecart au terrain.
  2. palier d'un candidat = palier du niveau median des creatures voisines (bloc 600 m) ; un palier n'est utilise dans une zone que
     s'il est celui de la zone (niveau median de la zone, comme 006/RESOURCES.md) ou un palier voisin present en « poche » (>= 25 candidats).
  3. quota par (zone, palier) proportionnel a la surface couverte, plafonne ; repartition par type de noeud ; tirage deterministe (crc32)
     avec espacements minimaux et plafond par bloc de 1 km2."""
import os, sys, math, zlib, collections, statistics, json
sys.stdout.reconfigure(encoding="utf8")
sys.path.insert(0, os.path.dirname(__file__))
from common import sql, REPO, zone_of, area_table
import rules, classify, generate
import nodes_terrain as nt
from nodes_common import *

OUT = os.path.join(REPO, "server", "sql", "world", "008_node_spawns_production.sql")
RESULT = os.path.join(os.path.dirname(__file__), "gen_nodes_production_result.txt")
STATS_ONLY = "--stats" in sys.argv
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LOG.append(s)


def h32(guid, entry):
    return zlib.crc32(("wlp%d_%d" % (guid, entry)).encode())


def main():
    by_id, _ = area_table()
    aflags = area_flags()
    info = classify.load()
    zt = generate.zone_tiers(info)                      # (map, zone) -> (palier, niveau median, nb)
    zone_name = {z: by_id[z]["name"] for (_m, z) in zt if z in by_id}

    # ---- creatures (toutes les apparitions des cartes 0/1 ; une apparition a entrees multiples doit toutes les satisfaire)
    rows = sql("select c.guid, if(c.id=0, e.entry, c.id), c.map, c.position_x, c.position_y, c.position_z, c.orientation, c.MovementType, "
               "t.`Rank`, t.CreatureType, t.NpcFlags, t.Civilian, t.ExtraFlags, t.InhabitType, t.MaxLevel "
               "from creature c left join creature_spawn_entry e on c.id=0 and e.guid=c.guid "
               "join creature_template t on t.Entry = if(c.id=0, e.entry, c.id) where c.map in (0,1)")
    cre = {}
    bad = collections.Counter()
    npc_pts = []
    for r in rows:
        g = int(r[0])
        m, x, y, z, o = int(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[6])
        mv, rank, ctype, nf, civ, extra, inh, maxlvl = int(r[7]), int(r[8]), int(r[9]), int(r[10]), int(r[11]), int(r[12]), int(r[13]), int(r[14])
        # points d'exclusion « PNJ » (camps, villages) : toute creature a drapeaux PNJ / civile / garde, tous rangs
        if nf or civ or extra & NPC_FLAG_GUARD_EXTRA:
            npc_pts.append((m, x, y))
        why = None
        if rank != 0:
            why = "rang != 0"
        elif ctype in (8, 11):
            why = "critter/totem"
        elif nf or civ or extra & NPC_FLAG_GUARD_EXTRA:
            why = "PNJ/civil/garde"
        elif not inh & 1:
            why = "pas de deplacement au sol (eau seule)"
        elif inh & 4:
            why = "vol"
        elif mv == 2:
            why = "patrouille (waypoints)"
        elif maxlvl <= 1 and ctype in (9, 10):
            why = "assistant invisible / cible d'entrainement (niveau <= 1, type 9/10)"
        if g in cre:
            if why and not cre[g][0]:
                cre[g] = (why,) + cre[g][1:]
            continue
        cre[g] = (why, m, x, y, z, o)
    for g, v in cre.items():
        if v[0]:
            bad[v[0]] += 1
    log("creatures cartes 0/1 :", len(cre), "| ecartees (premier motif) :", dict(bad))

    excl = PointIndex()
    for (m, x, y, rad, nm) in load_nobuild_points():
        excl.add(m, x, y, ("010", nm, rad))
    npc_idx = PointIndex()
    for (m, x, y) in npc_pts:
        npc_idx.add(m, x, y)
    log("points d'exclusion : %d (010, rayon %.0f m) + %d creatures a drapeaux PNJ/civiles/gardes (rayon %.0f m)"
        % (len(load_nobuild_points()), NODE_EXCL_RADIUS, len(npc_pts), NPC_EXCL_RADIUS))

    samples = level_samples()
    lvl_idx = local_level_index(samples)
    disc_idx = disc_index(samples)

    # ---- candidats
    rej = collections.Counter()
    cands = collections.defaultdict(list)       # (map, zone, palier local) -> [(guid, x, y, z, o)]
    for g, (why, m, x, y, z, o) in sorted(cre.items()):
        if why:
            continue
        zz = zone_of(m, x, y)
        if zz is None or zz[0] == 0 or zz[0] not in by_id:
            rej["sans zone"] += 1
            continue
        zid, zn, aid, an = zz
        if INDOOR.search(an):
            rej["aire interieure (nom)"] += 1
            continue
        if aflags.get(aid, 0) & CITY_FLAGS or aflags.get(zid, 0) & CITY_FLAGS:
            rej["ville/capitale/arene (drapeaux d'aire)"] += 1
            continue
        if (m, zid) not in zt:
            rej["zone sans palier (< 30 apparitions)"] += 1
            continue
        if excl.near(m, x, y, NODE_EXCL_RADIUS):
            rej["rayon d'exclusion 010 (100 m)"] += 1
            continue
        if npc_idx.near(m, x, y, NPC_EXCL_RADIUS):
            rej["proche d'un PNJ (50 m)"] += 1
            continue
        h = nt.height(m, x, y)
        if h is None:
            rej["trou / pas de terrain"] += 1
            continue
        if not (Z_TOL_DOWN <= z - h <= Z_TOL_UP):
            rej["z creature hors terrain statique (-1/+1,5 m)"] += 1
            continue
        if nt.near_water(m, x, y, WATER_MARGIN):
            rej["eau a moins de 6 m"] += 1
            continue
        t = local_tier(lvl_idx, m, x, y)
        if t is None:
            t = zt[(m, zid)][0]
            rej["(info) palier de zone par defaut (peu de creatures voisines)"] += 1
        td = local_tier_disc(disc_idx, m, x, y)
        if td is not None and abs(td - t) > 1:
            rej["palier local ambigu (bloc 600 m et disque 300 m a plus d'un palier d'ecart)"] += 1
            continue
        cands[(m, zid, t)].append((g, x, y, z, o))
    log("candidats retenus :", sum(len(v) for v in cands.values()))
    log("rejets :", dict(rej))

    # ---- regions (zone, palier) autorisees et surface couverte
    regions = {}
    pockets = []
    for (m, zid, t), lst in sorted(cands.items()):
        zt0 = zt[(m, zid)][0]
        if t == zt0:
            kind = "zone"
        elif abs(t - zt0) == 1 and len(lst) >= POCKET_MIN:
            kind = "poche"
            pockets.append((m, zid, t, len(lst)))
        else:
            if len(lst) >= 5:
                log("   (info) region non autorisee : map %d zone %s palier %d (palier de zone %d) : %d candidats" % (m, zone_name.get(zid), t, zt0, len(lst)))
            continue
        cells = {(int(math.floor(x / CELL_AREA)), int(math.floor(y / CELL_AREA))) for (_g, x, y, _z, _o) in lst}
        regions[(m, zid, t)] = dict(kind=kind, n=len(lst), area=len(cells) * (CELL_AREA / 1000.0) ** 2)
    # regions retenues : surface >= MIN_AREA ; une plus petite n'est ajoutee (par ordre de surface decroissante) que si le (continent, faction, palier)
    # a moins de MIN_ZONES zones sans elle
    included = {k for k, r in regions.items() if r["area"] >= MIN_AREA}
    cover_short = []
    forced = set()
    for m in (0, 1):
        for fac in "AH":
            for t in range(1, 6):
                zs = {k[1] for k in included if k[0] == m and k[2] == t and faction_zones_ok(rules.zone_faction(k[1]), fac)}
                extra = sorted((k for k in regions if k not in included and k[0] == m and k[2] == t and k[1] not in zs
                                and faction_zones_ok(rules.zone_faction(k[1]), fac)), key=lambda k: -regions[k]["area"])
                while len(zs) < MIN_ZONES and extra:
                    k = extra.pop(0)
                    included.add(k)
                    forced.add(k)
                    zs.add(k[1])
                if len(zs) < MIN_ZONES:
                    cover_short.append((m, fac, t, sorted(zone_name.get(z, z) for z in zs)))
    log("regions retenues : %d / %d (dont %d petites regions ajoutees pour la couverture)" % (len(included), len(regions), len(forced)))
    for c in cover_short:
        log("   COUVERTURE IMPOSSIBLE (aucune region admissible supplementaire) : carte %d faction %s palier %d : %d zone(s) %s" % (c[0], c[1], c[2], len(c[3]), c[3]))
    regions = {k: r for k, r in regions.items() if k in included}
    total_area = sum(r["area"] * TIER_DENSITY_MULT[k[2]] for k, r in regions.items())
    log("regions (zone, palier) : %d dont %d poches ; surface couverte totale %.1f km2" % (len(regions), len(pockets), total_area))

    # ---- quotas
    d = TOTAL_TARGET / total_area
    d = min(d, REGION_DENSITY_CAP)
    quotas = {}
    for k, r in regions.items():
        n = r["area"] * d * TIER_DENSITY_MULT[k[2]]
        n = min(n, REGION_DENSITY_CAP * r["area"])
        w = TIER_WEIGHTS[k[2]]
        tq = {}
        for entry, wt in w.items():
            q = int(round(n * wt))
            if r["n"] >= POCKET_MIN:
                q = max(q, MIN_PER_TYPE)
            tq[entry] = q
        quotas[k] = tq
    log("densite moyenne visee : %.2f noeuds/km2 (plafond region %.0f) ; quotas totaux avant tirage : %d" % (d, REGION_DENSITY_CAP, sum(sum(q.values()) for q in quotas.values())))

    # ---- tirage
    existing = sql("select map, position_x, position_y from gameobject where id between %d and %d and guid < %d" % (NODE_ENTRY_MIN, NODE_ENTRY_MAX, GUID_MIN))
    any_idx = PointIndex(SPACING_ANY * 2)
    for m, x, y in existing:
        any_idx.add(int(m), float(x), float(y))
    same_idx = collections.defaultdict(lambda: PointIndex(150.0))
    block = collections.Counter()
    gridc = collections.Counter()
    chosen = []   # (map, zone, tier, entry, guid, x, y, z, o)
    short = []
    for k in sorted(regions):
        m, zid, t = k
        lst = cands[k]
        for entry in sorted(quotas[k], key=lambda e: (rules.NODE[e]["kind"] != "passage", e)):
            want = quotas[k][entry]
            node = rules.NODE[entry]
            sp = SPACING_SAME[node["kind"]]
            got = 0
            for (g, x, y, z, o) in sorted(lst, key=lambda c: h32(c[0], entry)):
                if got >= want or len(chosen) >= TOTAL_CAP:
                    break
                b = (m, int(math.floor(x / BLOCK_SIZE)), int(math.floor(y / BLOCK_SIZE)))
                gk = (m, int(32 - x / GRID_SIZE), int(32 - y / GRID_SIZE))
                if block[b] >= BLOCK_CAP or gridc[gk] >= GRID_CAP:
                    continue
                if any_idx.near(m, x, y, SPACING_ANY) or same_idx[entry].near(m, x, y, sp):
                    continue
                any_idx.add(m, x, y)
                same_idx[entry].add(m, x, y)
                block[b] += 1
                gridc[gk] += 1
                chosen.append((m, zid, t, entry, g, x, y, z, o))
                got += 1
            if got < want:
                short.append((m, zid, zone_name.get(zid), t, entry, want, got))
    assert len(chosen) <= TOTAL_CAP, len(chosen)
    log("noeuds tires :", len(chosen), "(plafond %d)" % TOTAL_CAP)
    if short:
        log("quotas non atteints (%d types/regions ; faute de position libre) :" % len(short))
        for s in short[:60]:
            log("   map %d zone %s (%s) palier %d noeud %d : voulu %d, obtenu %d" % s)

    # ---- couverture reelle (apres tirage)
    by_type, by_res = coverage((c[0], c[1], c[3]) for c in chosen)
    low = []
    for m in (0, 1):
        for fac in "AH":
            for n in rules.NODES:
                zs = by_type.get((m, fac, n["entry"]), set())
                if len(zs) < MIN_ZONES:
                    low.append((m, fac, n["entry"], n["name"], len(zs)))
    log("\ncouverture par type de noeud x continent x faction (>= %d zones comptant >= %d noeuds) : %d combinaisons insuffisantes sur %d" % (MIN_ZONES, MIN_COUNTED, len(low), 2 * 2 * len(rules.NODES)))
    for l in low:
        log("   INSUFFISANT : carte %d faction %s type %d (%s) : %d zone(s)" % l)

    # ---- statistiques
    byc = collections.Counter((c[0], c[1], c[2]) for c in chosen)
    log("\nnoeuds par continent :", dict(collections.Counter(c[0] for c in chosen)))
    log("noeuds par palier :", dict(sorted(collections.Counter(c[2] for c in chosen).items())))
    log("noeuds par type :", dict(sorted(collections.Counter(c[3] for c in chosen).items())))
    log("grilles serveur (533 m) occupees : %d ; max %d noeuds / grille ; moyenne %.1f" % (len(gridc), max(gridc.values()), statistics.mean(gridc.values())))
    log("blocs de 1 km2 occupes : %d ; max %d / bloc ; moyenne %.1f" % (len(block), max(block.values()), statistics.mean(block.values())))
    log("\n%-4s %-22s %-5s %-6s %8s %8s %7s %9s" % ("map", "zone", "pal.", "type", "candidats", "surface", "noeuds", "noeuds/km2"))
    for k in sorted(regions):
        r = regions[k]
        log("%-4d %-22s T%-4d %-6s %8d %8.2f %7d %9.2f" % (k[0], zone_name.get(k[1], k[1]), k[2], r["kind"], r["n"], r["area"], byc[k], byc[k] / r["area"]))

    # ---- SQL
    chosen.sort(key=lambda c: (c[0], c[1], c[2], c[3], c[4]))
    guid = GUID_MIN
    out_rows = []
    for (m, zid, t, entry, g, x, y, z, o) in chosen:
        n = rules.NODE[entry]
        out_rows.append([guid, entry, m, 1, round(x, 4), round(y, 4), round(z, 4), round(o, 6), 0, 0,
                         round(math.sin(o / 2), 8), round(math.cos(o / 2), 8), n["respawn"][0], n["respawn"][1]])
        guid += 1
    assert guid - 1 <= GUID_MAX
    log("guid %d - %d" % (GUID_MIN, guid - 1))
    if STATS_ONLY:
        return
    text = generate.HEADER + (
        "-- 008 : noeuds de ressources de PRODUCTION, cartes 0 et 1 (%d noeuds ; plafond %d). Genere par tools/resources/gen_nodes_production.py\n"
        "-- Positions = positions de creatures de la table `creature` (jamais inventees) ; z et orientation = ceux de la creature.\n"
        "-- Plage de guid 9510001-9599999. La validation 005 (9500001-9500999) n'est pas touchee. Le DELETE ne vise que des guid de la plage ET\n"
        "-- des entrees de noeuds (9101001-9101999) : des pieces de construction posees ensuite (guid attribues apres le max) ne sont pas effacees.\n"
        "-- Exclusions : points 010 (100 m), creatures a drapeaux PNJ (50 m), aires de villes/interieurs, eau (6 m), z hors terrain.\n"
        % (len(out_rows), TOTAL_CAP))
    text += "DELETE FROM `gameobject` WHERE `guid` BETWEEN %d AND %d AND `id` BETWEEN %d AND %d;\n" % (GUID_MIN, GUID_MAX, NODE_ENTRY_MIN, NODE_ENTRY_MAX)
    text += generate.insert("gameobject", ["guid", "id", "map", "spawnMask", "position_x", "position_y", "position_z", "orientation",
                                           "rotation0", "rotation1", "rotation2", "rotation3", "spawntimesecsmin", "spawntimesecsmax"], out_rows, 200) + "\n"
    with open(OUT, "w", encoding="utf8", newline="\n") as f:
        f.write(text)
    log("ecrit", OUT, len(text), "octets")
    with open(RESULT, "w", encoding="utf8") as f:
        f.write("\n".join(LOG) + "\n")


if __name__ == "__main__":
    main()
