r"""Controle automatique des POINTS DE DEPART (progression Valheim : un personnage neuf n'a que le marteau).

Pour chaque point de depart de race (classicmangos.playercreateinfo, races regroupees par position : Comte du Nord, Coldridge,
Vallee des epreuves, Camp Narache, Shadowglen, Deathknell), mesure ce que le joueur trouve autour de lui :
  - branches et pierres (ramassables) a moins de 150 m           : de quoi faire etabli (10 Bois) + hache en pierre (5 Bois, 4 Pierre)
  - arbres de palier 0 (hetre, sapin, pin : TreeBase.m_minToolTier = 0 dans Valheim) et hetres a moins de 300 m
  - rochers (MineRock_Stone / Rock_4) a moins de 300 m
  - silex a moins de 400 m, au bord de l'eau (eau a < 15 m)       : hache en silex = 6 Silex
  - chardon a moins de 500 m, au bord de l'eau
  - cuivre / etain : aucun dans la zone de depart, aucun a moins de 1 000 m de marche ; le plus proche est dans une zone de palier >= 2
  (silex et chardon : si la premiere eau atteignable sans danger est plus loin que le rayon, rayon = cette distance + 250 / 350 m ;
  les rayons sont des distances de MARCHE.) Puis la couverture continent x faction x type (nodes_common.coverage_report).
Un ramassable/arbre/rocher n'est compte que s'il est
  - ATTEIGNABLE : chemin a pied depuis le depart sur le terrain (recherche sur une grille de 4,17 m, marche refusee si la pente entre
    deux cases depasse 50 deg, trous exclus, nage permise) de longueur <= 1,5 x le rayon ;
  - SANS DANGER : aucune creature hostile de niveau >= 6 (le joueur est niveau 1 ; les monstres de depart sont 1-5) a moins de 40 m
    (classicmangos.creature : sans drapeau PNJ, non civile, non garde, ni critter ni totem, hors ressources Wowlheim).

Sources : --source json (defaut) = C:\Wowlheim\data\wl_terrain\placements.json ; --source db = la base (creature guid 9600001-9699999,
gameobject 9130001-9130013 : ce que le serveur a reellement). Terrain : wl_terrain (ADT, chemin) et fichiers .map du serveur (eau).
Rien n'est ecrit en base. Sortie : stdout + start_check_result.txt (a cote du script). Code retour 0 = tous les departs passent, 2 sinon.

usage : C:\Wowlheim\tools\unity_venv\Scripts\python.exe start_check.py [--source json|db] [--db classicmangos] [--json chemin]"""
import os, sys, math, json, heapq, argparse, collections, ast
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import terrain_grid as tg
import nodes_terrain as nt
import rules, classify, generate
from common import sql, zone_of, area_table, REPO
from nodes_common import NPC_FLAG_GUARD_EXTRA, coverage_report, MIN_COUNTED, MIN_ZONES

START_NAMES = {(0, 12): "Comte du Nord (Northshire)", (0, 1): "Coldridge (Dun Morogh)", (1, 14): "Vallee des epreuves (Durotar)",
               (1, 215): "Camp Narache (Mulgore)", (1, 141): "Shadowglen (Teldrassil)", (0, 85): "Deathknell (Tirisfal)"}
TIER0_TREES = ("beech", "fir", "pine")          # Valheim : Beech1 / FirTree / Pinetree_01 ont m_minToolTier 0 (hache en pierre)
# (cle, libelle, types comptes, rayon m, minimum, au bord de l'eau)
CRITERIA = [
    ("branch", "branches < 150 m", ("branch",), 150.0, 15, False),
    ("stone", "pierres < 150 m", ("stone",), 150.0, 8, False),
    ("beech", "hetres < 300 m", ("beech",), 300.0, 5, False),
    ("tree0", "arbres palier 0 < 300 m", TIER0_TREES, 300.0, 10, False),
    ("rock", "rochers < 300 m", ("rock",), 300.0, 3, False),
    ("flint", "silex berge < 400 m", ("flint",), 400.0, 6, True),
    ("thistle", "chardon berge < 500 m", ("thistle",), 500.0, 3, True),
]
ORE_MIN_DIST = 1000.0                           # cuivre / etain : rien a moins de 1 000 m de marche du depart
SHORE_EXTRA = {"flint": 250.0, "thistle": 350.0}   # depart sans eau proche (Coldridge) : premiere berge atteignable + marge
REACH_R = 1600.0                                # rayon de la grille de marche
MAX_STEP_SLOPE = 50.0
DANGER_LEVEL, DANGER_R = 6, 40.0
WATER_R = 15.0
RESULT = os.path.join(HERE, "start_check_result.txt")


def starts():
    """[(map, x, y, z, zone, [races])] : positions distinctes de playercreateinfo."""
    g = collections.OrderedDict()
    for race, m, zone, x, y, z in sql("select race, map, zone, position_x, position_y, position_z from playercreateinfo group by race, map, zone, position_x, position_y, position_z order by race"):
        k = (int(m), round(float(x), 1), round(float(y), 1))
        if k not in g:
            g[k] = [int(m), float(x), float(y), float(z), int(zone), []]
        g[k][5].append(int(race))
    return list(g.values())


def load_json(path):
    d = json.load(open(path, encoding="utf8"))
    return [(int(i["map"]), float(i["x"]), float(i["y"]), i["kind"]) for i in d["items"]]


def load_db(db):
    """Entrees -> type, avec la meme numerotation que tools/valheim/gen_server_sql.py (TREE_SPECIES, ROCK_PREFABS, PICK_IDS)."""
    src = open(os.path.join(REPO, "tools", "valheim", "gen_server_sql.py"), encoding="utf8").read()
    tree = ast.parse(src)
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in ("TREE_SPECIES", "PICK_IDS"):
            consts[node.targets[0].id] = node.value
    species = [ast.literal_eval(k) for k in consts["TREE_SPECIES"].keys]          # ordre d'insertion = ordre des entrees
    halves = [ast.literal_eval(v) for v in consts["TREE_SPECIES"].values]
    pick_ids = ast.literal_eval(consts["PICK_IDS"])
    key_of_prefab = {pf: p["key"] for p in rules.PLACEMENTS for pf, _w in p["prefabs"]}
    ent = {}
    e = 9300001
    for t, (log, half, _stub, _drop) in zip(species, halves):
        ent[e] = key_of_prefab.get(t)
        e += 2 + (1 if half else 0)
    rock_prefabs = sorted({pf for p in rules.PLACEMENTS if p["kind"] == "creature" for pf, _w in p["prefabs"] if pf not in species})
    for i, pf in enumerate(rock_prefabs):
        ent[9300101 + i] = key_of_prefab[pf]
    go = {v: key_of_prefab[k] for k, v in pick_ids.items() if k in key_of_prefab}
    out = []
    for i, m, x, y in sql("select id, map, position_x, position_y from creature where guid between 9600001 and 9699999 and map in (0,1)", db):
        if ent.get(int(i)):
            out.append((int(m), float(x), float(y), ent[int(i)]))
    for i, m, x, y in sql("select id, map, position_x, position_y from gameobject where id between 9130001 and 9130099 and map in (0,1)", db):
        if go.get(int(i)):
            out.append((int(m), float(x), float(y), go[int(i)]))
    return out


def dangers(db):
    rows = sql("select c.map, c.position_x, c.position_y, t.MaxLevel from creature c left join creature_spawn_entry e on c.id=0 and e.guid=c.guid "
               "join creature_template t on t.Entry = if(c.id=0, e.entry, c.id) where c.map in (0,1) and c.guid not between 9600001 and 9699999 "
               "and t.NpcFlags=0 and t.Civilian=0 and (t.ExtraFlags & %d)=0 and t.CreatureType not in (8,11) and t.MaxLevel >= %d"
               % (NPC_FLAG_GUARD_EXTRA, DANGER_LEVEL), db)
    return [(int(m), float(x), float(y), int(lv)) for m, x, y, lv in rows]


class Reach:
    """Distance de MARCHE depuis le depart (Dijkstra 8 voisins sur une grille de UNIT = 4,17 m centree sur le depart, rayon R) :
    pas refuse si la pente entre deux cases depasse MAX_STEP_SLOPE, trous exclus, eau traversee a la nage."""
    def __init__(self, g, sx, sy, R):
        n = int(R / tg.UNIT) * 2 + 1
        self.n, self.sx, self.sy, self.u = n, sx, sy, tg.UNIT
        half = n // 2
        ii = (np.arange(n) - half) * tg.UNIT
        X, Y = np.meshgrid(sx + ii, sy + ii, indexing="ij")
        self.X, self.Y = X, Y
        H = g.height(X.ravel(), Y.ravel()).reshape(n, n)
        lvl, typ = g.water(X.ravel(), Y.ravel())
        lvl, typ = lvl.reshape(n, n), typ.reshape(n, n)
        self.H, self.lvl, self.typ = H, lvl, typ
        # case d'eau (riviere/lac ou ocean ; ni magma ni slime) : niveau au-dessus du sol
        self.wet = (~np.isnan(lvl)) & (lvl >= H - 0.3) & ((typ == 1) | (typ == 2))
        tanmax = math.tan(math.radians(MAX_STEP_SLOPE))
        ok = ~np.isnan(H)
        Hf = np.where(ok, H, 0.0).ravel()
        okf = ok.ravel()
        dist = np.full(n * n, np.inf)
        cand = np.argwhere(ok)
        d0 = np.hypot(cand[:, 0] - half, cand[:, 1] - half)
        a, b = cand[int(np.argmin(d0))]          # case praticable la plus proche (depart dans un WMO : crypte, abbaye...)
        s0 = int(a) * n + int(b)
        dist[s0] = 0.0
        pq = [(0.0, s0)]
        u = tg.UNIT
        nb = [(-1, 0, u), (1, 0, u), (0, -1, u), (0, 1, u), (-1, -1, u * 1.4142), (-1, 1, u * 1.4142), (1, -1, u * 1.4142), (1, 1, u * 1.4142)]
        nb = [(di, dj, w, w * tanmax) for di, dj, w in nb]
        pop, push = heapq.heappop, heapq.heappush
        while pq:
            d, k = pop(pq)
            if d > dist[k]:
                continue
            i, j = divmod(k, n)
            h0 = Hf[k]
            for di, dj, w, dh in nb:
                p, q = i + di, j + dj
                if p < 0 or q < 0 or p >= n or q >= n:
                    continue
                kk = p * n + q
                if not okf[kk] or abs(Hf[kk] - h0) > dh:
                    continue
                nd = d + w
                if nd < dist[kk]:
                    dist[kk] = nd
                    push(pq, (nd, kk))
        self.dist = dist.reshape(n, n)

    def at(self, x, y):
        """Distance de marche jusqu'au point (meilleure des 3 x 3 cases autour : l'objet est pose dans une case)."""
        half = self.n // 2
        i = int(round((x - self.sx) / self.u)) + half
        j = int(round((y - self.sy) / self.u)) + half
        best = math.inf
        for p in (i - 1, i, i + 1):
            for q in (j - 1, j, j + 1):
                if 0 <= p < self.n and 0 <= q < self.n:
                    best = min(best, self.dist[p, q])
        return best

    def nearest_safe_water(self, danger_pts):
        """(distance de marche, x, y) de la plus proche case d'eau atteignable sans creature dangereuse a moins de DANGER_R."""
        D = np.where(self.wet, self.dist, np.inf)
        order = np.argsort(D, axis=None)
        for k in order[:20000]:
            d = D.flat[k]
            if not np.isfinite(d):
                break
            x, y = float(self.X.flat[k]), float(self.Y.flat[k])
            if not is_dangerous(danger_pts, x, y):
                return d, x, y
        return None


def is_dangerous(danger_pts, x, y):
    return any((x - a) ** 2 + (y - b) ** 2 < DANGER_R ** 2 for a, b in danger_pts)


def radius_of(crit, water_d):
    """Rayon (distance de marche) d'un critere ; pour silex et chardon (berges) : si la premiere eau atteignable sans danger est plus
    loin que le rayon nominal, rayon = cette distance + SHORE_EXTRA (on va jusqu'a la premiere berge, pas au-dela)."""
    key, _l, _k, R, _n, shore = crit
    if shore and water_d is not None:
        return max(R, water_d + SHORE_EXTRA[key])
    return R


def context(m, sx, sy, grid, dang_all):
    reach = Reach(grid, sx, sy, REACH_R)
    near_d = [(x, y) for (mm, x, y, lv) in dang_all if mm == m and abs(x - sx) < REACH_R + 100 and abs(y - sy) < REACH_R + 100]
    w = reach.nearest_safe_water(near_d)
    return reach, near_d, w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=("json", "db"), default="json")
    ap.add_argument("--db", default="classicmangos")
    ap.add_argument("--json", default=rules.PLACEMENTS_JSON)
    args = ap.parse_args()
    lines = []

    def out(s=""):
        print(s, flush=True)
        lines.append(s)

    items = load_json(args.json) if args.source == "json" else load_db(args.db)
    out("Controle des departs : source %s (%s), %d ressources" % (args.source, args.json if args.source == "json" else args.db, len(items)))
    zt = generate.zone_tiers(classify.load())
    by_id, _ = area_table()
    dang = dangers(args.db)
    grids = {}
    fails = 0
    summary = []
    for (m, sx, sy, sz, zone, races) in starts():
        name = START_NAMES.get((m, zone), "carte %d zone %d" % (m, zone))
        out("\n=== %s : races %s, carte %d (%.1f, %.1f), zone %s (palier %s)"
            % (name, races, m, sx, sy, by_id.get(zone, {}).get("name", zone), zt.get((m, zone), ("?",))[0]))
        if m not in grids:
            grids[m] = tg.Grid(m)
        reach, near_d, water = context(m, sx, sy, grids[m], dang)
        water_d = water[0] if water else None
        out("   premiere eau atteignable sans danger : %s" % ("%.0f m de marche (%.0f, %.0f)" % water if water else "aucune a moins de %.0f m" % REACH_R))
        local = [(x, y, k, math.hypot(x - sx, y - sy)) for (mm, x, y, k) in items if mm == m and abs(x - sx) < REACH_R and abs(y - sy) < REACH_R]
        res = {}
        ok_all = True
        for crit in CRITERIA:
            key, label, kinds, _R, need, shore = crit
            R = radius_of(crit, water_d)
            tot = good = 0
            why = collections.Counter()
            nearest = None
            for (x, y, k, d) in local:
                if k not in kinds or d > R:
                    continue
                tot += 1
                pd = reach.at(x, y)
                if pd > R:
                    why["chemin > %.0f m" % R] += 1
                    continue
                if is_dangerous(near_d, x, y):
                    why["danger (creature >= niv %d a < %d m)" % (DANGER_LEVEL, DANGER_R)] += 1
                    continue
                if shore and nt.water_distance(m, x, y, WATER_R) is None:
                    why["pas d'eau a < %d m" % WATER_R] += 1
                    continue
                good += 1
                nearest = pd if nearest is None or pd < nearest else nearest
            passed = good >= need
            ok_all &= passed
            res[key] = good
            out("   [%s] %-24s %3d valides (minimum %d) a moins de %.0f m de marche (%d a vol d'oiseau)%s%s" % (
                "OK" if passed else "ECHEC", label, good, need, R, tot,
                " ; plus proche %.0f m" % nearest if nearest is not None else "",
                " ; ecartes : " + ", ".join("%s %d" % kv for kv in why.items()) if why else ""))
        # cuivre / etain : jamais dans la zone de depart ni a moins de 1 000 m de marche ; le plus proche en zone de palier >= 2
        for k in ("copper", "tin"):
            same = [(x, y) for (mm, x, y, kk) in items if kk == k and mm == m]
            in_zone = sum(1 for (x, y) in same if abs(x - sx) < 8000 and abs(y - sy) < 8000 and (zone_of(m, x, y) or (None,))[0] == zone)
            walk = [reach.at(x, y) for (x, y) in same if abs(x - sx) < REACH_R and abs(y - sy) < REACH_R]
            n_walk = sum(1 for d in walk if d <= ORE_MIN_DIST)
            dmin, pmin = None, None
            for (x, y) in same:
                d = math.hypot(x - sx, y - sy)
                if dmin is None or d < dmin:
                    dmin, pmin = d, (x, y)
            zt_n = None
            if pmin:
                zn = zone_of(m, *pmin)
                zt_n = (zn[1] if zn else "?", zt.get((m, zn[0]), ("?",))[0] if zn else "?")
            wmin = min([d for d in walk if np.isfinite(d)], default=None)
            passed = in_zone == 0 and n_walk == 0 and (zt_n is None or (zt_n[1] != "?" and zt_n[1] >= 2))
            ok_all &= passed
            res[k] = wmin if wmin is not None else math.inf
            out("   [%s] %-24s %d dans la zone de depart, %d a moins de %.0f m de marche ; plus proche : %s m a vol d'oiseau%s, %s" % (
                "OK" if passed else "ECHEC", {"copper": "cuivre", "tin": "etain"}[k], in_zone, n_walk, ORE_MIN_DIST,
                "%.0f" % dmin if dmin is not None else "-", " (%s, palier %s)" % zt_n if zt_n else "",
                "%.0f m de marche" % wmin if wmin is not None else "pas de chemin a moins de %.0f m" % REACH_R))
        out("   => %s" % ("DEPART OK" if ok_all else "DEPART EN ECHEC"))
        fails += 0 if ok_all else 1
        summary.append((name, res, ok_all, water_d))
    out("\n=== RESUME (valides : chemin a pied, sans danger, berge pour silex/chardon ; cuivre/etain : distance de marche du plus proche)")
    hdr = "%-30s" % "depart" + "".join("%8s" % c[0] for c in CRITERIA) + "%8s%9s%9s  %s" % ("eau m", "cuivre m", "etain m", "resultat")
    out(hdr)
    f = lambda v: "%.0f" % v if v is not None and np.isfinite(v) else ">%.0f" % REACH_R
    for name, res, ok, wd in summary:
        out("%-30s" % name + "".join("%8d" % res[c[0]] for c in CRITERIA) + "%8s" % f(wd)
            + "".join("%9s" % f(res[k]) for k in ("copper", "tin")) + "  " + ("OK" if ok else "ECHEC"))
    out("minimums : " + ", ".join("%s %d (%.0f m)" % (c[0], c[4], c[3]) for c in CRITERIA)
        + " ; silex/chardon : rayon porte a (premiere eau + %s m) si l'eau est plus loin ; cuivre/etain : 0 a moins de %.0f m de marche et hors zone de depart"
        % ("/".join("%.0f" % v for v in SHORE_EXTRA.values()), ORE_MIN_DIST))
    out("%d depart(s) en echec sur %d" % (fails, len(summary)))
    # couverture continent x faction x type (meme critere que check_nodes.py, calcule ici sur la source controlee)
    pls = []
    for (m, x, y, k) in items:
        z = zone_of(m, x, y)
        pls.append(dict(map=m, zone=z[0] if z else 0, key=k))
    cov_gaps, cov_struct = coverage_report(pls, zt)
    out("\n=== COUVERTURE (zones par continent x faction x type, >= %d placements par zone ; exige min(%d, zones exigibles))" % (MIN_COUNTED, MIN_ZONES))
    for (m, fac, k, cov, elig) in cov_struct:
        out("   structurel : carte %d faction %s %-10s %d zone(s) exigible(s), toutes couvertes : %s" % (m, fac, k, len(elig), cov))
    for (m, fac, k, cov, elig) in cov_gaps:
        out("   MANQUE     : carte %d faction %s %-10s %d couverte(s) %s sur %d exigible(s) %s" % (m, fac, k, len(cov), cov, len(elig), elig))
    out("%d manque(s) de couverture" % len(cov_gaps))
    fails += len(cov_gaps)
    open(RESULT, "w", encoding="utf8").write("\n".join(lines) + "\n")
    sys.exit(2 if fails else 0)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf8")
    main()
