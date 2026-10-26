"""Constantes et fonctions partagees par gen_nodes_production.py (generation de 008) et check_nodes.py (controle).
Ce fichier ne modifie rien : il importe rules.py / classify.py / common.py existants.

Parametres de la production des noeuds (voir docs/RESOURCES_NODES.md pour la justification)."""
import os, re, math, collections, statistics
from common import sql, REPO, zone_of, read_dbc, area_table
import rules

GUID_MIN, GUID_MAX = 9510001, 9599999         # plage de production (9500001-9500999 = validation 005, intouchee)
NODE_ENTRY_MIN, NODE_ENTRY_MAX = 9101001, 9101999
TOTAL_CAP = 6000                              # plafond dur de noeuds de production
TOTAL_TARGET = 4600                           # cible de generation (marge sous le plafond)
BLOCK_SIZE = 1000.0                           # bloc de 1 km x 1 km (coordonnees monde) pour le plafond de densite
GRID_CAP = 32                                 # noeuds de production max par grille serveur de 533,33 m (unite de chargement des GameObjects)
GRID_SIZE = 533.33333
BLOCK_CAP = 45                                # noeuds de production max par bloc de 1 km2
REGION_DENSITY_CAP = 30.0                     # noeuds / km2 max par (zone, palier)
NODE_EXCL_RADIUS = 100.0                      # rayon d'exclusion autour des points de 010 (010 : 70 m ; 100 m cote noeuds)
NPC_EXCL_RADIUS = 50.0                        # rayon autour de toute creature a drapeaux PNJ / civile / garde
SPACING_ANY = 12.0                            # espacement minimal entre deux noeuds quelconques (inclut ceux de 005)
SPACING_SAME = {"bois": 40.0, "pierre": 40.0, "plante": 40.0, "minerai": 60.0, "passage": 150.0}
Z_TOL_DOWN, Z_TOL_UP = -1.0, 1.5              # ecart admis entre le z de la creature et le terrain statique (m)
WATER_MARGIN = 6.0                            # pas d'eau a moins de 6 m
LOCAL_CELL = 200.0                            # cellule de lissage du niveau local (m) ; bloc 3 x 3 cellules
LOCAL_MIN_SAMPLES = 5
POCKET_MIN = 25                               # candidats minimum pour qu'un palier voisin du palier de la zone soit autorise
CELL_AREA = 250.0                             # cellule de 250 m : la surface « couverte » d une region = nb de cellules contenant >= 1 candidat
MIN_AREA = 0.75                               # km2 : une region plus petite n'est retenue que si elle est necessaire a la couverture (3 zones / faction)
MIN_COUNTED = 4                               # un noeud-type compte pour une zone s'il y en a >= 4 dans la zone (couverture)
MIN_ZONES = 3                                 # zones par continent et par faction
CITY_FLAGS = 0x100 | 0x200 | 0x08 | 0x20 | 0x80   # AREA_FLAG_CAPITAL|CITY|SLAVE_CAPITAL(2)|ARENA (comme BuildingMgr.cpp)
NPC_FLAG_GUARD_EXTRA = 0x400 | 0x10000        # ExtraFlags garde / civil (comme classify.py)

# repartition des types de noeuds par palier (somme = 1)
TIER_WEIGHTS = {
    1: {9101001: .46, 9101011: .46, 9101041: .08},
    2: {9101002: .30, 9101012: .22, 9101021: .21, 9101022: .21, 9101042: .06},
    3: {9101003: .30, 9101013: .24, 9101023: .40, 9101043: .06},
    4: {9101004: .21, 9101014: .15, 9101024: .28, 9101026: .15, 9101027: .15, 9101044: .06},
    5: {9101005: .24, 9101015: .18, 9101025: .28, 9101031: .24, 9101045: .06},
}
TIER_DENSITY_MULT = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0}
MIN_PER_TYPE = 5                              # minimum par (zone, palier, type) quand la region est assez grande

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
    """{entree de noeud : [(item, chance %)]} : tout ce que le noeud peut donner (rules.NODES)."""
    return {n["entry"]: [(it, ch) for it, ch, _mn, _mx in n["loot"]] for n in rules.NODES}


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
