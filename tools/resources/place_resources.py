r"""Positions CREDIBLES des ressources Valheim dans le monde de WoW (cartes 0 et 1), d'apres le terrain du client (terrain_scan.py).
N'ecrit AUCUN SQL et aucune base : lecture de classicmangos (paliers de zone, PNJ) et de C:\Wowlheim\data\wl_terrain.
Sortie : C:\Wowlheim\data\wl_terrain\placements.json  + place_resources_result.txt (journal, a cote de ce script).

usage : C:\Wowlheim\tools\unity_venv\Scripts\python.exe place_resources.py
Prerequis : terrain_scan.py (donnees de terrain), cache/spawns.tsv (build_cache.py), MySQL local (lecture).

Principe (details et preuves : docs/RESOURCES_PLACEMENT.md) :
  - arbres Valheim a 3-15 m d'un arbre de WoW (doodad M2), jamais a moins de 3 m d'un tronc ; essence = biome du palier de zone,
    conifere de WoW -> sapin/pin ; palmiers/cactus : pas d'equivalent, pas d'arbre ;
  - rochers pres des rochers de WoW, en pied de falaise, sur les pentes ; pierres et branches au sol pres des rochers / sous les arbres ;
  - silex, chardon, etain sur les berges (case seche a moins de ~10 m d'une case d'eau, sol au-dessus du niveau de l'eau) ;
  - cuivre en AMAS (3-8 filons sur 20-40 m, peu d'amas, en pied de pente) ; fer bas et humide ; argent/obsidienne en hauteur ; lin en
    terrain plat et degage ; baies pres des buissons de WoW ; champignons pres des champignons de WoW ou au pied des arbres ;
  - exclusions : villes (drapeaux d'aire), interieurs (nom d'aire), points 010 (100 m), PNJ/civils/gardes (50 m), batiments (boite des
    WMO + 6 m), routes (textures de route), eau, trous ; z = hauteur du terrain statique (MCVT) au point."""
import os, sys, json, math, zlib, random, collections, statistics, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import terrain_grid as tg
from common import sql, area_table, read_dbc, zone_of as zone_of_map
import rules, classify, generate
import start_check
import nodes_terrain as nt
from nodes_common import load_nobuild_points, CITY_FLAGS, INDOOR, NPC_FLAG_GUARD_EXTRA

OUT = tg.OUT
UNIT = tg.UNIT
CELL_KM2 = UNIT * UNIT / 1e6
RESULT = os.path.join(HERE, "place_resources_result.txt")
LOG = []


def log(*a):
    s = " ".join(str(v) for v in a)
    print(s, flush=True)
    LOG.append(s)


# ---------------------------------------------------------------- parametres (biomes de Valheim par palier, voir RESOURCES_PLACEMENT.md)
# Essences par palier : (feuillu de WoW -> [(essence, poids)], conifere de WoW -> [...])
SPECIES = {
    # Prairie : hetres, quelques chenes et bouleaux ; pres d'un conifere de WoW (Dun Morogh, Silverpine) : sapins et 20 % de hetres
    # (2026-10-26 : le hetre est l'arbre de palier 0 de la Prairie ; sans lui, Coldridge n'avait aucun hetre et Silverpine 3)
    1: ([("beech", 75), ("birch", 13), ("oak", 12)], [("fir", 80), ("beech", 20)]),
    # Foret noire : sapins et pins ; quelques hetres aussi pres des coniferes (Hillsbrad n'avait aucun hetre)
    2: ([("fir", 50), ("pine", 35), ("beech", 15)], [("fir", 50), ("pine", 40), ("beech", 10)]),
    3: ([("swamp", 100)], [("swamp", 100)]),                                    # Marais : arbres anciens de Valheim (SwampTree1, ajoute le 2026-10-26)
    4: ([("fir", 100)], [("fir", 100)]),                                       # Montagne : sapins (Valheim : pas de bouleau en montagne)
    5: ([("birch", 70), ("oak", 30)], [("birch", 70), ("oak", 30)]),            # Plaines : bouleaux, chenes (pas de pin dans les plaines)
}
CONIFER_RE = __import__("re").compile(r"pine|fir\d|firtree|snow|winter|spruce|conifer|alterac|ironforge|mountain", __import__("re").I)
EXOTIC_RE = __import__("re").compile(r"palm|cactus|bamboo|jungle|stranglethorn|ungoro|tanaris|silithus|kalidartree0[67]|mushroomtree", __import__("re").I)
NOT_TREE_RE = __import__("re").compile(r"\\armor\\|armorhelm", __import__("re").I)
# part des arbres de WoW (zones a palier, hors exclusions) qui recoivent un arbre Valheim voisin, PAR PALIER : budget de charge
# (~15 000 creatures-ressources + ramassables au total) en gardant la prairie (zones de depart) la plus dense (2026-10-26)
TREE_RATIO = {1: 0.18, 2: 0.12, 3: 0.25, 4: 0.08, 5: 0.10}
# multiplicateur des densites de KINDS par palier (meme budget ; le palier 1 garde la densite pleine : ramassables de depart)
TIER_DENSITY = {1: 1.0, 2: 0.55, 3: 0.8, 4: 0.6, 5: 0.6}
TREE_DMIN, TREE_DMAX = 3.0, 15.0
TREE_KINDS = ("beech", "birch", "oak", "fir", "pine", "swamp")
SPECIES_MIN = 4             # essences feuillues du biome : au moins 4 par zone boisee (= MIN_COUNTED de la couverture)
# densites (par km2 de terre de la zone) et espacements (m) ; « tiers » = paliers ou le type existe
KINDS = {
    #  kind        tiers        dens/km2  espacement  pente max     (les zones de WoW sont petites : Elwynn = 3,8 km2 de terre)
    "rock":      ((1, 2, 3, 4, 5), 14.0, 12.0, 40.0),   # 25 -> 14 (budget de charge, 2026-10-26)
    "stone":     ((1, 2),          20.0, 15.0, 25.0),
    "branch":    ((1, 2),          25.0, 12.0, 25.0),
    "flint":     ((1, 2),          10.0, 15.0, 30.0),
    "raspberry": ((1,),            10.0, 12.0, 25.0),
    "blueberry": ((2,),            10.0, 12.0, 25.0),
    "mushroom":  ((1, 2),          8.0,  15.0, 25.0),
    "thistle":   ((2, 3),          8.0,  20.0, 30.0),
    "dandelion": ((1,),            8.0,  15.0, 25.0),    # Valheim : Pickable_Dandelion (prairie)
    "cloudberry": ((5,),           8.0,  15.0, 25.0),    # Valheim : CloudberryBush (plaines)
    "barley":    ((5,),            3.0,  120.0, 8.0),    # Valheim : Pickable_Barley_Wild, en touffes comme le lin
    "tar":       ((5,),            1.0,  150.0, 15.0),   # Valheim : Pickable_TarBig, en MARES de 4-7 (TarPit des plaines) ; densite = mares / km2
    "crystal":   ((4,),            3.0,  40.0, 40.0),    # Valheim : Pickable_MountainCaveCrystal (adaptation : en surface, pas de grotte)
    "tin":       ((2,),            5.0,  25.0, 30.0),    # densite = groupes de 1-2 filons
    "copper":    ((2,),            1.0,  300.0, 35.0),   # densite = AMAS / km2 (3-8 filons chacun) ; espacement entre amas
    "iron":      ((3,),            8.0,  40.0, 15.0),
    "silver":    ((4,),            3.0,  60.0, 40.0),
    "obsidian":  ((4,),            3.0,  40.0, 40.0),
    "flax":      ((5,),            4.0,  120.0, 8.0),    # densite = touffes / km2 (3-6 plants chacune)
}
SPACING_ANY = 3.0
MIN_PER_ZONE = {"copper": 2, "flax": 2, "barley": 2, "tar": 1}
# ---------------------------------------------------------------- points de depart (2026-10-26, controle : start_check.py)
# Un personnage neuf n'a que le marteau. Autour de CHAQUE depart de race, passe dediee AVANT le reste : branches et pierres a moins de
# 150 m de marche, hetres et rochers a moins de 300 m, silex et chardon sur la premiere berge atteignable sans danger. Memes exclusions
# que partout (PNJ 50 m, 010, routes, batiments, eau, pente, palier .map) + chemin a pied et aucune creature de niveau >= 6 a 40 m.
# Quotas = minimums de start_check.CRITERIA avec une marge (~1,5x).
START_QUOTA = {"beech": 12, "rock": 5, "branch": 22, "stone": 12, "flint": 9, "thistle": 5}
START_SPACING = {"beech": 5.0, "rock": 8.0, "branch": 5.0, "stone": 5.0, "flint": 6.0, "thistle": 8.0}
ORE_START_EXCL = 1100.0     # cuivre / etain : jamais a moins de 1 100 m d'un depart (start_check : 0 a moins de 1 000 m de marche)
NOBUILD_R, NPC_R, WMO_MARGIN, WMO_MAX_SIDE = 100.0, 50.0, 6.0, 300.0


def h32(*a):
    return zlib.crc32(("|".join(str(v) for v in a)).encode())


class Hash:
    def __init__(self, cell=20.0):
        self.c = cell
        self.g = collections.defaultdict(list)

    def add(self, x, y, p=None):
        self.g[(int(x // self.c), int(y // self.c))].append((x, y, p))

    def nearest(self, x, y, r):
        """(distance, payload) du point le plus proche a moins de r, ou None."""
        k = int(math.ceil(r / self.c))
        cx, cy = int(x // self.c), int(y // self.c)
        best = None
        for i in range(cx - k, cx + k + 1):
            for j in range(cy - k, cy + k + 1):
                for (px, py, pl) in self.g.get((i, j), ()):
                    d = math.hypot(px - x, py - y)
                    if d < r and (best is None or d < best[0]):
                        best = (d, pl)
        return best


# ---------------------------------------------------------------- contexte par carte
class Ctx:
    def __init__(self, m, zt, by_id, aflags, nobuild, npc, starts=(), dang=()):
        self.m = m
        self.starts = list(starts)          # [(x, y, zone, nom)] des departs de cette carte (start_check.starts)
        self.dang = list(dang)              # creatures dangereuses pour un niveau 1 (start_check.dangers)
        self.g = tg.Grid(m)
        self.by_id, self.aflags = by_id, aflags
        self.zt = zt
        lut = np.zeros(max(by_id) + 1, np.int32)
        for aid, a in by_id.items():
            lut[aid] = a["zone"] or aid
        self.zone_lut = lut
        self.nobuild, self.npc = nobuild, npc
        # WMO : boites englobantes (petites seulement : les villes sont exclues par les drapeaux d'aire)
        self.wmo = Hash(100.0)
        for w in json.load(open(os.path.join(OUT, "%d_wmos.json" % m)))["items"]:
            name, x, y, z, x0, x1, y0, y1, z0, z1 = w
            if x1 - x0 <= WMO_MAX_SIDE and y1 - y0 <= WMO_MAX_SIDE:
                self.wmo.add(x, y, (name.rsplit("\\", 1)[-1], x0 - WMO_MARGIN, x1 + WMO_MARGIN, y0 - WMO_MARGIN, y1 + WMO_MARGIN))
        # ancres (doodads de WoW)
        self.anchors = {}
        tr = json.load(open(os.path.join(OUT, "%d_trees.json" % m)))
        # (« armorhelm*.mdx » : casques de decor classes « tree » par terrain_scan, le mot-cle « elm » ; ce ne sont pas des arbres)
        self.anchors["tree"] = [(t[0], t[1], t[2], t[3], tr["models"][t[4]].rsplit("\\", 1)[-1]) for t in tr["items"]
                                if not NOT_TREE_RE.search(tr["models"][t[4]])]
        rk = json.load(open(os.path.join(OUT, "%d_rocks.json" % m)))
        self.anchors["rock"] = [(t[0], t[1], t[2], t[3], rk["models"][t[4]].rsplit("\\", 1)[-1]) for t in rk["items"]]
        fl = json.load(open(os.path.join(OUT, "%d_flora.json" % m)))
        for cls in ("bush", "deadwood", "mushroom"):
            self.anchors[cls] = [(t[0], t[1], t[2], t[3], fl["models"][t[4]].rsplit("\\", 1)[-1]) for t in fl["items"] if t[5] == cls]
        self.tree_hash = Hash(20.0)
        for a in self.anchors["tree"] + self.anchors["deadwood"]:
            self.tree_hash.add(a[0], a[1], a[4])
        self.rej = collections.Counter()

    def zone_of(self, x, y):
        aid = int(self.g.area_at(x, y))
        if aid <= 0 or aid >= len(self.zone_lut):
            return 0, 0
        return int(self.zone_lut[aid]), aid

    def tier_of(self, x, y):
        z, aid = self.zone_of(x, y)
        t = self.zt.get((self.m, z)) if z else None
        return (t[0] if t else None), z, aid

    def check(self, x, y, max_slope=40.0):
        """None si la position est utilisable, sinon le motif du rejet. Retourne aussi z."""
        h = float(self.g.height(x, y))
        if math.isnan(h):
            return "hors terrain / trou", None
        lvl, typ = self.g.water(x, y)
        lvl = float(lvl)
        if not math.isnan(lvl) and lvl >= h - 0.3:
            return "eau", None
        if float(self.g.slope_at(x, y)) > max_slope:
            return "pente", None
        for dx, dy in ((0, 0), (4, 0), (-4, 0), (0, 4), (0, -4)):
            if int(self.g.road_at(x + dx, y + dy)) >= 100:
                return "route", None
        z, aid = self.zone_of(x, y)
        if self.aflags.get(aid, 0) & CITY_FLAGS or self.aflags.get(z, 0) & CITY_FLAGS:
            return "ville (drapeaux d'aire)", None
        if aid in self.by_id and INDOOR.search(self.by_id[aid]["name"]):
            return "aire interieure (nom)", None
        if self.nobuild.nearest(x, y, NOBUILD_R):
            return "point 010 (100 m)", None
        if self.npc.nearest(x, y, NPC_R):
            return "PNJ/civil/garde (50 m)", None
        k = int(math.ceil((WMO_MAX_SIDE / 2 + WMO_MARGIN) / self.wmo.c))
        cx, cy = int(x // self.wmo.c), int(y // self.wmo.c)
        for i in range(cx - k, cx + k + 1):
            for j in range(cy - k, cy + k + 1):
                for (_px, _py, (nm, x0, x1, y0, y1)) in self.wmo.g.get((i, j), ()):
                    if x0 <= x <= x1 and y0 <= y <= y1:
                        return "batiment (WMO + 6 m)", None
        return None, h


# ---------------------------------------------------------------- candidats issus du terrain (par tuile, vectorise)
def shift(a, di, dj, P):
    n = a.shape[0] - 2 * P
    return a[P + di:P + di + n, P + dj:P + dj + n]


def terrain_candidates(ctx, tiers_of_zone):
    """-> dict categorie -> liste (x, y, z, zone, info). Categories : shore, cliff, slope, high, lowwet, flat."""
    g = ctx.g
    out = collections.defaultdict(list)
    rnd = np.random.default_rng(ctx.m + 7)
    zone_heights = collections.defaultdict(list)
    zone_land = collections.Counter()
    per_tile = []
    for k in range(len(g.tiles)):
        zc = ctx.zone_lut[np.clip(g.area[k], 0, len(ctx.zone_lut) - 1)]          # zone par chunk 16x16
        zcell = np.repeat(np.repeat(zc, 8, 0), 8, 1)
        h = g.v8[k]
        wl, wt = g.wl[k], g.wt[k]
        wet = (~np.isnan(wl)) & (wl >= h - 0.3)
        dry = ~wet & ~g.holes[k]
        zs, cnt = np.unique(zcell[dry], return_counts=True)
        for z, c in zip(zs, cnt):
            zone_land[int(z)] += int(c)
        for r in range(16):
            for c in range(16):
                if dry[r * 8 + 4, c * 8 + 4]:          # terre seulement (le fond de la mer fausserait la mediane)
                    zone_heights[int(zc[r, c])].append(float(h[r * 8 + 4, c * 8 + 4]))
        tiers = {tiers_of_zone.get(int(z)) for z in np.unique(zc)} - {None}
        if tiers:
            per_tile.append((k, zcell, tiers))
    zone_p = {z: (np.percentile(v, 50), np.percentile(v, 75)) for z, v in zone_heights.items()}
    for (k, zcell, tiers) in per_tile:
        X, Y = g.cell_centers(k)
        P = 7
        hp = g.padded("v8", k, P, np.float32(np.nan))
        wlp = g.padded("wl", k, P, np.float32(np.nan))
        wtp = g.padded("wt", k, P, np.uint8(0))
        slp = g.padded("slope", k, P, np.float32(0))
        holes = g.holes[k]
        wetp = (~np.isnan(wlp)) & (wlp >= hp - 0.3) & ((wtp == 1) | (wtp == 2))
        h = shift(hp, 0, 0, P)
        sl = shift(slp, 0, 0, P)
        wet = shift(wetp, 0, 0, P)
        wl0 = shift(wlp, 0, 0, P)
        wet_any = (~np.isnan(wl0)) & (wl0 >= h - 0.3)                 # tout liquide (magma et slime compris)
        dry = ~wet_any & ~holes & ~np.isnan(h)
        # berge : eau a 1-2 cases (4-10 m), niveau de l'eau voisine < sol - 0,3 m
        near_lvl = np.full(h.shape, -np.inf, np.float32)
        near_ocean = np.zeros(h.shape, bool)
        near_wet2 = np.zeros(h.shape, bool)
        for di in range(-2, 3):
            for dj in range(-2, 3):
                if di * di + dj * dj > 5:                     # disque de 2,24 cases (9,3 m) : pas les coins du carre 5x5
                    continue
                w = shift(wetp, di, dj, P)
                near_wet2 |= w
                near_lvl = np.maximum(near_lvl, np.where(w, shift(wlp, di, dj, P), -np.inf))
                near_ocean |= w & (shift(wtp, di, dj, P) == 2)
        shore = dry & near_wet2 & (h > near_lvl + 0.3) & (sl < 30)
        # pied de falaise : case peu pentue, case tres pentue (> 45 deg) et plus haute de 3 m a moins de 2 cases
        cliff = np.zeros(h.shape, bool)
        for di in range(-2, 3):
            for dj in range(-2, 3):
                cliff |= (shift(slp, di, dj, P) > 45) & (shift(hp, di, dj, P) > h + 3)
        cliff &= dry & (sl < 25)
        slope_c = dry & (sl >= 25) & (sl <= 40)
        # eau a moins de 7 cases (~30 m) : bas et humide (fer du marais)
        near_wet7 = np.zeros(h.shape, bool)
        for di in range(-7, 8, 2):
            for dj in range(-7, 8, 2):
                near_wet7 |= shift(wetp, di, dj, P)
        zc16 = zcell[::8, ::8]
        p50 = np.repeat(np.repeat(np.array([[zone_p.get(int(z), (1e9, 1e9))[0] for z in row] for row in zc16]), 8, 0), 8, 1)
        p75 = np.repeat(np.repeat(np.array([[zone_p.get(int(z), (1e9, 1e9))[1] for z in row] for row in zc16]), 8, 0), 8, 1)
        lowwet = dry & near_wet7 & (sl < 12) & (h <= p50)
        high = dry & (h >= p75) & (sl >= 12) & (sl <= 40)
        flat = dry & (sl < 8) & ~near_wet7
        for name, mask, cap in (("shore", shore, 400), ("cliff", cliff, 200), ("slope", slope_c, 150), ("lowwet", lowwet, 150),
                                ("high", high, 200), ("flat", flat, 150)):
            idx = np.flatnonzero(mask)
            if len(idx) > cap:
                idx = rnd.choice(idx, cap, replace=False)
            for q in idx:
                r, c = divmod(int(q), 128)
                info = ""
                if name == "shore":
                    info = "berge : sol %.1f m, eau %s au niveau %.1f m" % (h[r, c], "ocean" if near_ocean[r, c] else "riviere/lac", near_lvl[r, c])
                elif name == "cliff":
                    info = "pied de falaise (pente > 45 deg a < 9 m)"
                elif name == "slope":
                    info = "pente %.0f deg" % sl[r, c]
                elif name == "high":
                    info = "hauteur %.0f m (>= 75e centile de la zone %.0f m), pente %.0f deg" % (h[r, c], p75[r, c], sl[r, c])
                elif name == "lowwet":
                    info = "bas (%.0f m <= mediane %.0f m), eau a < 30 m" % (h[r, c], p50[r, c])
                elif name == "flat":
                    info = "plat (pente %.0f deg), pas d'eau a < 30 m" % sl[r, c]
                # petit decalage aleatoire dans la case
                x = float(X[r, c]) + float(rnd.uniform(-1.0, 1.0))
                y = float(Y[r, c]) + float(rnd.uniform(-1.0, 1.0))
                out[name].append((x, y, int(zcell[r, c]), info, bool(near_ocean[r, c]) if name == "shore" else False))
    return out, zone_land


# ---------------------------------------------------------------- selection
class Placer:
    def __init__(self, ctx):
        self.ctx = ctx
        self.all = Hash(10.0)
        self.same = collections.defaultdict(lambda: Hash(50.0))
        self.out = []
        self.count = collections.Counter()

    def try_add(self, x, y, kind, tier, zone, anchor, spacing, max_slope, any_spacing=SPACING_ANY, same_key=None, rnd=None):
        why, z = self.ctx.check(x, y, max_slope)
        if why:
            self.ctx.rej[(kind, why)] += 1
            return False
        if kind in ("copper", "tin") and any(math.hypot(x - sx, y - sy) < ORE_START_EXCL for (sx, sy, _z, _n) in self.ctx.starts):
            self.ctx.rej[(kind, "minerai a moins de %.0f m d'un depart" % ORE_START_EXCL)] += 1
            return False
        # zone recalculee avec les .map du serveur (comme le serveur et check_nodes.py) : au bord d'une zone, l'aire ADT et l'aire .map
        # peuvent differer ; on refuse tout point ou le palier .map n'est pas celui du placement (jamais de palier superieur trop tot)
        zm = zone_of_map(self.ctx.m, x, y)
        tm = self.ctx.zt.get((self.ctx.m, zm[0])) if zm else None
        if not tm or tm[0] != tier:
            self.ctx.rej[(kind, "bordure de zone (palier .map different)")] += 1
            return False
        if self.all.nearest(x, y, any_spacing):
            self.ctx.rej[(kind, "trop pres d'une autre ressource")] += 1
            return False
        sk = same_key or kind
        if spacing and self.same[sk].nearest(x, y, spacing):
            self.ctx.rej[(kind, "espacement du type")] += 1
            return False
        o = round((h32(self.ctx.m, x, y, kind) % 6283) / 1000.0, 3)
        self.out.append({"map": self.ctx.m, "x": round(x, 2), "y": round(y, 2), "z": round(z, 2), "o": o, "kind": kind, "tier": tier,
                         "zone": zone, "anchor": anchor})
        self.all.add(x, y, kind)
        self.same[sk].add(x, y, kind)
        self.count[(zone, kind)] += 1
        return True


def pick(rnd, weights):
    tot = sum(w for _k, w in weights)
    v = rnd.random() * tot
    for k, w in weights:
        v -= w
        if v < 0:
            return k
    return weights[-1][0]


def place_map(ctx):
    m = ctx.m
    zt_m = {z: t[0] for (mm, z), t in ctx.zt.items() if mm == m and z}      # zone 0 (aire inconnue) exclue
    cand, zone_land = terrain_candidates(ctx, zt_m)
    log("carte %d : candidats terrain %s" % (m, {k: len(v) for k, v in cand.items()}))
    km2 = {z: n * CELL_KM2 for z, n in zone_land.items()}
    pl = Placer(ctx)
    name = lambda z: ctx.by_id.get(z, {}).get("name", str(z))

    def cap(z, kind):
        d = KINDS[kind][1]
        return max(MIN_PER_ZONE.get(kind, 1), int(round(d * TIER_DENSITY.get(zt_m.get(z), 1.0) * km2.get(z, 0.0))))

    # 0. points de depart : passe dediee, prioritaire (espacements reserves avant le reste)
    for st in ctx.starts:
        start_pass(ctx, pl, zt_m, st)

    # 1. arbres : autour des arbres de WoW
    rnd = random.Random(1000 + m)
    trees = list(ctx.anchors["tree"])
    rnd.shuffle(trees)
    skipped = collections.Counter()
    for (ax, ay, az, sc, mdl) in trees:
        tier, z, _aid = ctx.tier_of(ax, ay)
        if tier is None:
            skipped["zone sans palier"] += 1
            continue
        if EXOTIC_RE.search(mdl):
            skipped["arbre exotique (palmier, jungle...) : pas d'essence Valheim"] += 1
            continue
        if rnd.random() > TREE_RATIO[tier]:
            continue
        sp = pick(rnd, SPECIES[tier][1 if CONIFER_RE.search(mdl) else 0])
        dmin = max(TREE_DMIN, 2.0 * sc)
        for _try in range(5):
            d = rnd.uniform(dmin, TREE_DMAX)
            a = rnd.uniform(0, 2 * math.pi)
            x, y = ax + d * math.cos(a), ay + d * math.sin(a)
            near = ctx.tree_hash.nearest(x, y, TREE_DMIN + 0.05)      # + 5 cm : marge d'arrondi des coordonnees (0,01 m)
            if near:
                ctx.rej[(sp, "a moins de 3 m d'un tronc de WoW")] += 1
                continue
            if pl.try_add(x, y, sp, tier, z, "a %.1f m de l'arbre WoW %s (%.1f, %.1f)" % (d, mdl, ax, ay), 5.0, 35.0, same_key="tree"):
                break
    log("carte %d : arbres ignores %s" % (m, dict(skipped)))
    # 1b. chaque essence feuillue du biome presente dans chaque zone boisee (>= SPECIES_MIN) : le tirage au sort seul laissait p. ex.
    # 3 chenes a Durotar (peu d'arbres non exotiques) ; on change l'essence d'arbres deja places de l'essence la plus frequente de la
    # zone (meme position, memes controles : l'essence est autorisee au palier). Les arbres du depart (hetres) ne sont pas touches.
    relabeled = collections.Counter()
    by_zone_tree = collections.defaultdict(list)
    for p in pl.out:
        if p["kind"] in TREE_KINDS and not p["anchor"].startswith("depart"):
            by_zone_tree[p["zone"]].append(p)
    for z, lst in sorted(by_zone_tree.items()):
        tier = zt_m.get(z)
        if tier is None or len(lst) < 4 * SPECIES_MIN:
            continue
        for sp, _w in SPECIES[tier][0]:
            have = sum(1 for p in lst if p["kind"] == sp)
            while have < SPECIES_MIN:
                cnt = collections.Counter(p["kind"] for p in lst)
                donor, nd = cnt.most_common(1)[0]
                if donor == sp or nd <= 2 * SPECIES_MIN:
                    break
                p = next(p for p in lst if p["kind"] == donor)
                p["kind"] = sp
                p["anchor"] += " (essence %s -> %s : au moins %d %s par zone)" % (donor, sp, SPECIES_MIN, sp)
                relabeled[(z, donor, sp)] += 1
                have += 1
    log("carte %d : essences completees %s" % (m, {"%s %s->%s" % (ctx.by_id.get(z, {}).get("name", z), a, b): n
                                                    for (z, a, b), n in relabeled.items()}))

    # 2. types a ancres et types de terrain, par zone
    by_zone = collections.defaultdict(lambda: collections.defaultdict(list))   # zone -> kind -> [(x, y, anchor)]
    def anchor_cands(cls, kinds, dmin, dmax, scale_mul=1.0):
        for (ax, ay, az, sc, mdl) in ctx.anchors[cls]:
            tier, z, _ = ctx.tier_of(ax, ay)
            if tier is None:
                continue
            for kind in kinds:
                if tier not in KINDS[kind][0]:
                    continue
                r = h32(m, ax, ay, kind)
                d = dmin * max(1.0, sc * scale_mul) + (r % 1000) / 1000.0 * (dmax - dmin)
                a = (r // 1000 % 6283) / 1000.0
                by_zone[z][kind].append((ax + d * math.cos(a), ay + d * math.sin(a), "a %.1f m du %s WoW %s (%.1f, %.1f)"
                                         % (d, {"rock": "rocher", "tree": "arbre", "bush": "buisson", "mushroom": "champignon",
                                                "deadwood": "tronc mort"}[cls], mdl, ax, ay)))
    anchor_cands("rock", ("rock",), 2.5, 8.0)
    anchor_cands("rock", ("stone",), 1.5, 5.0)
    anchor_cands("rock", ("copper",), 3.0, 10.0)
    anchor_cands("rock", ("silver", "obsidian"), 3.0, 10.0)
    anchor_cands("tree", ("branch",), 2.0, 7.0, 0.5)
    anchor_cands("deadwood", ("branch",), 1.0, 3.0)
    anchor_cands("bush", ("raspberry", "blueberry", "cloudberry"), 1.0, 3.0)
    anchor_cands("mushroom", ("mushroom",), 1.0, 4.0)
    anchor_cands("tree", ("mushroom",), 2.0, 5.0, 0.5)
    TERRAIN_FOR = {"shore": ("flint", "thistle", "tin"), "cliff": ("rock", "copper", "obsidian", "crystal"), "slope": ("rock", "silver"),
                   "high": ("silver", "obsidian", "crystal"), "lowwet": ("iron",),
                   "flat": ("flax", "stone", "dandelion", "barley", "tar", "cloudberry")}
    for cat, lst in cand.items():
        for (x, y, z, info, ocean) in lst:
            tier = zt_m.get(z)
            if tier is None:
                continue
            for kind in TERRAIN_FOR[cat]:
                if tier in KINDS[kind][0]:
                    if kind == "thistle" and ocean:
                        continue                    # chardon : bord des rivieres et lacs seulement
                    by_zone[z][kind].append((x, y, info))

    for z in sorted(by_zone):
        tier = zt_m.get(z)
        for kind in sorted(by_zone[z]):
            lst = by_zone[z][kind]
            r = random.Random(h32(m, z, kind))
            r.shuffle(lst)
            # priorite aux ancres de WoW : champignons pres des champignons, rochers/pierres pres des rochers, puis le terrain
            if kind == "mushroom":
                lst.sort(key=lambda t: 0 if "champignon" in t[2] else 1)
            elif kind in ("rock", "stone", "copper", "obsidian"):
                lst.sort(key=lambda t: 0 if "rocher WoW" in t[2] else (1 if "falaise" in t[2] else 2))
            elif kind == "branch":
                lst.sort(key=lambda t: 0 if "tronc mort" in t[2] else 1)
            n_cap = cap(z, kind)
            _tiers, _d, spacing, max_slope = KINDS[kind]
            got = 0
            for (x, y, info) in lst:
                if got >= n_cap:
                    break
                if kind == "copper":
                    got += place_cluster(pl, r, x, y, "copper", tier, z, info, 3, 8, 6.0, 18.0, 5.0, max_slope, spacing)
                elif kind in ("flax", "barley"):
                    got += place_cluster(pl, r, x, y, kind, tier, z, info, 3, 6, 1.5, 6.0, 1.5, max_slope, spacing)
                elif kind == "tar":
                    got += place_cluster(pl, r, x, y, kind, tier, z, info, 4, 7, 2.0, 8.0, 2.0, max_slope, spacing)
                elif kind == "tin":
                    got += place_cluster(pl, r, x, y, "tin", tier, z, info, 1, 2, 3.0, 6.0, 4.0, max_slope, spacing, need=1)
                else:
                    got += pl.try_add(x, y, kind, tier, z, info, spacing, max_slope)
    log("carte %d : %d placements" % (m, len(pl.out)))
    return pl, km2


def start_pass(ctx, pl, zt_m, st):
    """Ressources du depart (sx, sy, zone, nom) : voir START_QUOTA. Candidats : ancres de WoW proches (arbres, troncs morts, buissons,
    rochers), pentes, puis toute case de terrain atteignable ; berges (silex, chardon) = cases seches a moins de 2 cases (8 m) d'une
    case d'eau, sol au-dessus de l'eau (chardon : riviere/lac d'abord, ocean a defaut), par distance de marche croissante."""
    m = ctx.m
    sx, sy, zone, sname = st
    tier = zt_m.get(zone)
    if tier is None:
        log("depart %s : zone %s sans palier, ignore" % (sname, zone))
        return
    reach, near_d, water = start_check.context(m, sx, sy, ctx.g, ctx.dang)
    water_d = water[0] if water else None
    crit = {c[0]: c for c in start_check.CRITERIA}
    rnd = random.Random(h32(m, round(sx), round(sy), "depart"))
    n = reach.n
    X, Y, H, D = reach.X, reach.Y, reach.H, reach.dist
    wet = reach.wet
    lvl = np.where(wet, reach.lvl, -np.inf)
    near_lvl = np.full(H.shape, -np.inf)
    near_river = np.zeros(H.shape, bool)
    for di in range(-2, 3):
        for dj in range(-2, 3):
            if di * di + dj * dj > 5:
                continue
            near_lvl = np.maximum(near_lvl, np.roll(np.roll(lvl, di, 0), dj, 1))
            near_river |= np.roll(np.roll(wet & (reach.typ == 1), di, 0), dj, 1)
    dry = ~wet & ~np.isnan(H)
    shore = dry & np.isfinite(near_lvl) & (H > near_lvl + 0.3)
    slope = np.nan_to_num(ctx.g.slope_at(X.ravel(), Y.ravel()).reshape(n, n), nan=90.0)

    def cells(mask, R, order="random"):
        idx = np.flatnonzero(mask & dry & (D <= R * 0.95))
        if order == "near":
            idx = list(idx[np.argsort(D.flat[idx], kind="stable")])
        else:
            idx = list(idx)
            rnd.shuffle(idx)
        return [(float(X.flat[k]) + rnd.uniform(-1.5, 1.5), float(Y.flat[k]) + rnd.uniform(-1.5, 1.5),
                 "%.0f m de marche du depart" % D.flat[k]) for k in idx]

    def anchors(classes, R, dmin, dmax, per=3):
        out = []
        for cls in classes:
            for (ax, ay, az, sc, mdl) in ctx.anchors[cls]:
                if abs(ax - sx) > R or abs(ay - sy) > R or math.hypot(ax - sx, ay - sy) > R:
                    continue
                for _ in range(per):
                    d = rnd.uniform(dmin * max(1.0, 0.5 * sc), max(dmax, dmin * max(1.0, 0.5 * sc) + 1.0))
                    a = rnd.uniform(0, 2 * math.pi)
                    out.append((ax + d * math.cos(a), ay + d * math.sin(a), "a %.1f m du %s WoW %s (%.1f, %.1f)" % (
                        d, {"tree": "arbre", "rock": "rocher", "deadwood": "tronc mort", "bush": "buisson"}[cls], mdl, ax, ay)))
        rnd.shuffle(out)
        return out

    R = {k: start_check.radius_of(crit[k], water_d) for k in START_QUOTA}
    plan = [
        ("beech", anchors(("tree", "deadwood", "bush"), R["beech"], 3.0, 15.0) + cells(slope < 20, R["beech"]), 35.0),
        ("rock", anchors(("rock",), R["rock"], 2.5, 8.0) + cells(slope >= 25, R["rock"]) + cells(slope < 25, R["rock"]), 40.0),
        ("branch", anchors(("deadwood", "tree"), R["branch"], 1.0, 7.0) + cells(slope < 25, R["branch"]), 25.0),
        ("stone", anchors(("rock",), R["stone"], 1.5, 5.0) + cells(slope < 25, R["stone"]), 25.0),
        ("flint", cells(shore & (slope < 30), R["flint"], "near"), 30.0),
        ("thistle", cells(shore & near_river & (slope < 30), R["thistle"], "near")
         + cells(shore & ~near_river & (slope < 30), R["thistle"], "near"), 30.0),
    ]
    got = collections.Counter()
    for kind, cands, max_slope in plan:
        Rk = R[kind]
        for (x, y, info) in cands:
            if got[kind] >= START_QUOTA[kind]:
                break
            if math.hypot(x - sx, y - sy) > Rk or reach.at(x, y) > Rk * 0.95:
                continue
            if start_check.is_dangerous(near_d, x, y):
                ctx.rej[(kind, "depart : creature dangereuse a < %.0f m" % start_check.DANGER_R)] += 1
                continue
            if kind in ("flint", "thistle") and nt.water_distance(m, x, y, start_check.WATER_R - 3.0) is None:
                ctx.rej[(kind, "depart : pas d'eau (.map) a < 12 m")] += 1
                continue
            if kind == "beech" and ctx.tree_hash.nearest(x, y, TREE_DMIN + 0.05):
                ctx.rej[(kind, "a moins de 3 m d'un tronc de WoW")] += 1
                continue
            zp = ctx.zone_of(x, y)[0]                 # zone du point (berge d'une zone voisine de meme palier : Deathknell -> Silverpine)
            if zt_m.get(zp) != tier:
                ctx.rej[(kind, "depart : zone voisine de palier different")] += 1
                continue
            if pl.try_add(x, y, kind, tier, zp, "depart %s : %s" % (sname, info), START_SPACING[kind], max_slope,
                          same_key="tree" if kind == "beech" else None):
                got[kind] += 1
    log("depart %s (carte %d) : eau sans danger a %s ; places %s" % (
        sname, m, "%.0f m de marche" % water_d if water_d is not None else "-", dict(got)))


def place_cluster(pl, r, cx, cy, kind, tier, z, info, nmin, nmax, rmin, rmax, inner, max_slope, spacing, need=None):
    """Amas : centre + n-1 elements a rmin-rmax du centre, espaces de `inner` m. Retourne 1 si l'amas est garde (>= need elements)."""
    need = nmin if need is None else need
    if pl.same[kind + "_amas"].nearest(cx, cy, spacing):
        return 0
    why, _z = pl.ctx.check(cx, cy, max_slope)
    if why:
        pl.ctx.rej[(kind, why)] += 1
        return 0
    n = r.randint(nmin, nmax)
    pts = [(cx, cy)]
    for _ in range(n * 6):
        if len(pts) >= n:
            break
        d, a = r.uniform(rmin, rmax), r.uniform(0, 2 * math.pi)
        x, y = cx + d * math.cos(a), cy + d * math.sin(a)
        if all(math.hypot(x - px, y - py) >= inner for px, py in pts):
            why, _z = pl.ctx.check(x, y, max_slope)
            if not why:
                pts.append((x, y))
    if len(pts) < need:
        pl.ctx.rej[(kind, "amas trop petit")] += 1
        return 0
    cid = "amas %s (%.0f, %.0f) de %d" % (kind, cx, cy, len(pts))
    k0 = len(pl.out)
    for (x, y) in pts:
        if not pl.try_add(x, y, kind, tier, z, cid + " ; " + info, 0.0, max_slope, any_spacing=min(SPACING_ANY, inner)):
            pass
    if len(pl.out) - k0 < need:
        for p in pl.out[k0:]:
            pl.count[(p["zone"], p["kind"])] -= 1
        del pl.out[k0:]                     # (les index spatiaux gardent ces points : ils bloquent seulement le voisinage)
        return 0
    pl.same[kind + "_amas"].add(cx, cy)
    return 1


def main():
    t0 = time.time()
    by_id, _ = area_table()
    recs, _s = read_dbc("AreaTable.dbc")
    aflags = {r[0]: r[4] for r in recs}
    info = classify.load()
    zt = generate.zone_tiers(info)
    log("paliers de zone (generate.zone_tiers) : %d zones" % len(zt))
    rows = sql("select c.map, c.position_x, c.position_y from creature c left join creature_spawn_entry e on c.id=0 and e.guid=c.guid "
               "join creature_template t on t.Entry = if(c.id=0, e.entry, c.id) where c.map in (0,1) and "
               "(t.NpcFlags<>0 or t.Civilian<>0 or (t.ExtraFlags & %d)<>0)" % NPC_FLAG_GUARD_EXTRA)
    st_all = start_check.starts()
    dang = start_check.dangers("classicmangos")
    allp = []
    for m in (0, 1):
        nob = Hash(100.0)
        for (mm, x, y, rad, nm) in load_nobuild_points():
            if mm == m:
                nob.add(x, y, nm)
        npc = Hash(50.0)
        for (mm, x, y) in rows:
            if int(mm) == m:
                npc.add(float(x), float(y))
        sts = [(x, y, zone, start_check.START_NAMES.get((mm, zone), "zone %d" % zone)) for (mm, x, y, _z, zone, _r) in st_all if mm == m]
        ctx = Ctx(m, zt, by_id, aflags, nob, npc, sts, dang)
        pl, km2 = place_map(ctx)
        allp += pl.out
        # journal par zone
        cnt = collections.defaultdict(collections.Counter)
        for p in pl.out:
            cnt[p["zone"]][p["kind"]] += 1
        for z in sorted(cnt, key=lambda z: (ctx.zt.get((m, z), (9,))[0], by_id.get(z, {}).get("name", ""))):
            log("  carte %d palier %s %-28s %6.1f km2 : %s" % (m, ctx.zt.get((m, z), ("?",))[0], by_id.get(z, {}).get("name", z), km2.get(z, 0),
                                                              ", ".join("%s %d" % kv for kv in sorted(cnt[z].items()))))
        rej = collections.defaultdict(collections.Counter)
        for (kind, why), n in ctx.rej.items():
            rej[why][kind] += n
        log("carte %d : rejets (motif : total) %s" % (m, {w: sum(c.values()) for w, c in sorted(rej.items())}))
        del ctx, pl
        __import__("gc").collect()
    json.dump({"fields": "map,x,y,z,o,kind,tier,zone,anchor", "generator": "tools/resources/place_resources.py", "items": allp},
              open(os.path.join(OUT, "placements.json"), "w"), ensure_ascii=False)
    tot = collections.Counter(p["kind"] for p in allp)
    log("TOTAL %d placements : %s" % (len(allp), ", ".join("%s %d" % kv for kv in sorted(tot.items()))))
    tt = collections.Counter((p["tier"], p["kind"]) for p in allp)
    for t in range(1, 6):
        log("  palier %d : %s" % (t, ", ".join("%s %d" % (k, n) for (tt_, k), n in sorted(tt.items()) if tt_ == t)))
    log("duree %.0f s" % (time.time() - t0))
    open(RESULT, "w", encoding="utf8").write("\n".join(LOG) + "\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf8")
    main()
