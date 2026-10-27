"""Constantes et fonctions partagees par gen_nodes_production.py (generation de 008) et check_nodes.py (controle).
Ce fichier ne modifie rien : il importe rules.py / classify.py / common.py existants.

Parametres de la production des noeuds (voir docs/RESOURCES_NODES.md pour la justification)."""
import os, re, math, collections, statistics
from common import sql, REPO, zone_of, read_dbc, area_table
import rules

GUID_MIN, GUID_MAX = 9510001, 9599999         # ancienne plage de 008 (noeuds WoW, supprimes)
NODE_ENTRY_MIN, NODE_ENTRY_MAX = rules.OLD_NODE_ENTRY_MIN, rules.OLD_NODE_ENTRY_MAX
# Budget de charge du monde Valheim (place_resources.py : TREE_RATIO / TIER_DENSITY / KINDS) : creatures-ressources + ramassables
TOTAL_CAP = 20000
PICKABLE_GUID_MIN, PICKABLE_GUID_MAX = 9501001, 9514664   # ramassables (GameObjects) : sous les pieces posees, 13 664 places
NODE_EXCL_RADIUS = 100.0                      # rayon d'exclusion autour des points de 010 (010 : 70 m ; 100 m cote ressources)
NPC_EXCL_RADIUS = 50.0                        # rayon autour de toute creature a drapeaux PNJ / civile / garde
MIN_COUNTED = 4                               # un type compte pour une zone s'il y en a >= 4 dans la zone (couverture)
MIN_ZONES = 3                                 # zones par continent et par faction
CITY_FLAGS = 0x100 | 0x200 | 0x08 | 0x20 | 0x80   # AREA_FLAG_CAPITAL|CITY|SLAVE_CAPITAL(2)|ARENA (comme BuildingMgr.cpp)
NPC_FLAG_GUARD_EXTRA = 0x400 | 0x10000        # ExtraFlags garde / civil (comme classify.py)
LOCAL_CELL = 200.0                            # cellule de lissage du niveau local (m) ; bloc 3 x 3 cellules
LOCAL_MIN_SAMPLES = 5

INDOOR = re.compile(rules.INDOOR_AREA_RE, re.I)


def load_nobuild_points():
    """Points de server/sql/world/010_nobuild_points.sql (lus dans le fichier, pas dans la base) : [(map, x, y, radius, name)]."""
    p = os.path.join(REPO, "server", "sql", "world", "010_nobuild_points.sql")
    pts = []
    for m in re.finditer(r"^\((\d+), (-?[\d.]+), (-?[\d.]+), (\d+), '((?:[^']|'')*)'\)", open(p, encoding="utf8").read(), re.M):
        pts.append((int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)), m.group(5).replace("''", "'")))
    return pts


class PointIndex:
    """Index spatial (grille) pour tester la proximite de points par carte."""
    def __init__(self, cell=100.0):
        self.cell = cell
        self.g = collections.defaultdict(list)

    def add(self, m, x, y, payload=None):
        self.g[(m, int(math.floor(x / self.cell)), int(math.floor(y / self.cell)))].append((x, y, payload))

    def near(self, m, x, y, r):
        """Premier point a moins de r metres, ou None."""
        c = self.cell
        k = int(math.ceil(r / c))
        cx, cy = int(math.floor(x / c)), int(math.floor(y / c))
        r2 = r * r
        for i in range(cx - k, cx + k + 1):
            for j in range(cy - k, cy + k + 1):
                for (px, py, pl) in self.g.get((m, i, j), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < r2:
                        return (px, py, pl)
        return None


def area_flags():
    recs, _s = read_dbc("AreaTable.dbc")
    return {r[0]: r[4] for r in recs}


def local_level_index(samples):
    """samples : [(map, x, y, level)] -> dict (map, cx, cy) -> [levels] pour le lissage."""
    idx = collections.defaultdict(list)
    for m, x, y, lv in samples:
        idx[(m, int(math.floor(x / LOCAL_CELL)), int(math.floor(y / LOCAL_CELL)))].append(lv)
    return idx


def local_tier(idx, m, x, y):
    """Palier du niveau median des creatures dans le bloc 3x3 cellules de 200 m autour de (x, y), ou None (< 5 echantillons)."""
    cx, cy = int(math.floor(x / LOCAL_CELL)), int(math.floor(y / LOCAL_CELL))
    lv = []
    for i in (cx - 1, cx, cx + 1):
        for j in (cy - 1, cy, cy + 1):
            lv.extend(idx.get((m, i, j), ()))
    if len(lv) < LOCAL_MIN_SAMPLES:
        return None
    return rules.tier_of_level(statistics.median(lv))


def level_samples():
    """Creatures de reference pour le niveau local : rang 0, ni critter ni totem, sans drapeaux PNJ, non civiles ; cartes 0/1 ;
    hors « assistants » invisibles / cibles d'entrainement (niveau <= 1 et type Mecanique ou Non specifie : p. ex. 1 129 apparitions de
    « Scourge Invasion Minion, finder », niveau 1, dans des zones de niveau 50+, qui faussaient le niveau local)."""
    rows = sql("select c.map, c.position_x, c.position_y, (t.MinLevel+t.MaxLevel)/2 "
               "from creature c left join creature_spawn_entry e on c.id=0 and e.guid=c.guid "
               "join creature_template t on t.Entry = if(c.id=0, e.entry, c.id) "
               "where c.map in (0,1) and t.`Rank`=0 and t.CreatureType not in (8,11) and t.NpcFlags=0 and t.Civilian=0 "
               "and (t.ExtraFlags & %d)=0 and t.MaxLevel>0 and not (t.MaxLevel<=1 and t.CreatureType in (9,10))" % NPC_FLAG_GUARD_EXTRA)
    return [(int(m), float(x), float(y), float(lv)) for m, x, y, lv in rows]


def faction_zones_ok(f, fac):
    """Une zone de faction de classement f (A/H/C, rules.zone_faction) est accessible a la faction fac."""
    return f in (fac, "C")


def node_resources():
    """{type de placement : [(item, 100)]} : materiaux que le type donne (rules.PLACEMENTS, gives)."""
    return {p["key"]: [(it, 100) for it in p["gives"]] for p in rules.PLACEMENTS}


def read_placements(path=None):
    """placements.json (place_resources.py) -> [dict(key, map, zone, tier, x, y, z, o, anchor)] ; key = « kind » = cle de rules.PLACEMENT."""
    import json
    d = json.load(open(path or rules.PLACEMENTS_JSON, encoding="utf8"))
    return [dict(key=it["kind"], map=int(it["map"]), zone=int(it["zone"]), tier=int(it["tier"]), x=float(it["x"]), y=float(it["y"]),
                 z=float(it["z"]), o=float(it["o"]), anchor=it.get("anchor", "")) for it in d["items"]]


def coverage(nodes, min_counted=MIN_COUNTED):
    """nodes : iterable de (map, zone_id, entree). Retourne (par_type, par_ressource) :
    par_type[(map, faction, entree)] = ensemble de zones ou le type compte >= min_counted noeuds ;
    par_ressource[(map, faction, item)] = zones ou la somme des noeuds donnant l'item (chance >= 20 %) est >= min_counted."""
    cnt = collections.Counter(nodes)
    res_of = node_resources()
    by_type = collections.defaultdict(set)
    res_cnt = collections.Counter()
    for (m, z, e), n in cnt.items():
        for it, ch in res_of.get(e, ()):
            if ch >= 20:
                res_cnt[(m, z, it)] += n
        if n >= min_counted:
            for fac in "AH":
                if faction_zones_ok(rules.zone_faction(z), fac):
                    by_type[(m, fac, e)].add(z)
    by_res = collections.defaultdict(set)
    for (m, z, it), n in res_cnt.items():
        if n >= min_counted:
            for fac in "AH":
                if faction_zones_ok(rules.zone_faction(z), fac):
                    by_res[(m, fac, it)].add(z)
    return by_type, by_res


TREE_KEYS = ("beech", "birch", "oak", "fir", "pine", "swamp")
MIN_WOW_TREES = 10        # un type d'arbre n'est exigible que dans une zone ou WoW a au moins 10 arbres (non exotiques)
# Paliers ou un type est place PARTOUT (densite de zone) ; rules.PLACEMENTS peut en autoriser davantage (chardon au palier 1 :
# berge du depart seulement), ces paliers-la ne rendent pas une zone exigible.
COVERAGE_TIERS = {"thistle": (2, 3)}


def wow_tree_zones():
    """{(map, zone) : nombre d'arbres WoW non exotiques} d'apres wl_terrain/{m}_trees.json (zone = aire ADT du point)."""
    import json
    import terrain_grid as tg
    import numpy as np
    exotic = re.compile(r"palm|cactus|bamboo|jungle|stranglethorn|ungoro|tanaris|silithus|kalidartree0[67]|mushroomtree|\\armor\\|armorhelm", re.I)
    by_id, _ = area_table()
    out = collections.Counter()
    for m in (0, 1):
        tr = json.load(open(os.path.join(tg.OUT, "%d_trees.json" % m)))
        g = tg.Grid(m)
        keep = [t for t in tr["items"] if not exotic.search(tr["models"][t[4]])]
        if not keep:
            continue
        aids = g.area_at(np.array([t[0] for t in keep]), np.array([t[1] for t in keep]))
        for a in aids:
            a = int(a)
            z = by_id.get(a, {}).get("zone") or a
            out[(m, z)] += 1
        del g
    return out


def coverage_report(pls, zone_tiers, wow_trees=None):
    """Couverture continent x faction x type. Une zone est EXIGIBLE pour un type si elle est accessible a la faction, que son palier
    est un palier ou le type est place partout (COVERAGE_TIERS sinon rules.PLACEMENTS) et, pour un arbre, que WoW y a >= MIN_WOW_TREES
    arbres. Exige : min(MIN_ZONES, zones exigibles) zones avec >= MIN_COUNTED placements, ET chaque zone exigible couverte quand il y a
    moins de MIN_ZONES zones exigibles (on ne peut pas faire mieux que toutes).
    -> (gaps, structurels) : listes de (map, faction, type, couvertes, exigibles, noms)."""
    by_id, _ = area_table()
    by_type, _r = coverage((p["map"], p["zone"], p["key"]) for p in pls)
    if wow_trees is None:
        wow_trees = wow_tree_zones()
    gaps, structural = [], []
    for m in (0, 1):
        for fac in "AH":
            for pl in rules.PLACEMENTS:
                k = pl["key"]
                tiers = COVERAGE_TIERS.get(k, pl["tiers"])
                elig = {z for (mm, z), t in zone_tiers.items() if mm == m and z and t[0] in tiers and faction_zones_ok(rules.zone_faction(z), fac)
                        and (k not in TREE_KEYS or wow_trees.get((m, z), 0) >= MIN_WOW_TREES)}
                cov = by_type.get((m, fac, k), set()) & elig
                need = min(MIN_ZONES, len(elig))
                name = lambda zs: sorted(by_id.get(z, {}).get("name", str(z)) for z in zs)
                row = (m, fac, k, name(cov), name(elig))
                if len(cov) < need:
                    gaps.append(row)
                elif len(elig) < MIN_ZONES:
                    structural.append(row)
    return gaps, structural


def disc_index(samples, cell=300.0):
    idx = collections.defaultdict(list)
    for m, x, y, lv in samples:
        idx[(m, int(x // cell), int(y // cell))].append((x, y, lv))
    return idx


def local_tier_disc(idx, m, x, y, radius=300.0):
    """Second estimateur (independant du premier) : palier du niveau median des creatures a moins de 300 m (disque)."""
    lv = []
    cx, cy = int(x // radius), int(y // radius)
    for i in (cx - 1, cx, cx + 1):
        for j in (cy - 1, cy, cy + 1):
            for (px, py, l) in idx.get((m, i, j), ()):
                if (px - x) ** 2 + (py - y) ** 2 <= radius * radius:
                    lv.append(l)
    return rules.tier_of_level(statistics.median(lv)) if len(lv) >= LOCAL_MIN_SAMPLES else None
