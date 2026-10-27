r"""Controles de placements.json (place_resources.py) : statistiques, verifications recalculees independamment du generateur
(force brute numpy sur les doodads et la grille du terrain, sans les index ni les candidats du generateur), 5 verifications
ponctuelles, et cartes PNG des zones de depart. Lecture seule.
usage : C:\Wowlheim\tools\unity_venv\Scripts\python.exe place_check.py
Sorties : C:\Wowlheim\data\wl_terrain\checks.txt, C:\Wowlheim\data\wl_terrain\maps\*.png"""
import os, sys, json, math, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from PIL import Image, ImageDraw
import terrain_grid as tg
from common import area_table

OUT = tg.OUT
MAPS_DIR = os.path.join(OUT, "maps")
LINES = []
TREES = {"beech", "birch", "oak", "fir", "pine"}
SHORE = {"flint", "thistle", "tin"}
COLORS = {"beech": (60, 220, 60), "birch": (240, 240, 240), "oak": (150, 110, 40), "fir": (0, 120, 70), "pine": (120, 200, 120),
          "rock": (150, 150, 150), "stone": (200, 200, 170), "branch": (170, 120, 70), "flint": (255, 255, 0), "raspberry": (230, 0, 80),
          "blueberry": (60, 60, 255), "mushroom": (255, 140, 0), "thistle": (200, 80, 255), "tin": (0, 255, 255), "copper": (255, 90, 0),
          "iron": (120, 40, 20), "silver": (220, 220, 255), "obsidian": (20, 20, 20), "flax": (255, 220, 120),
          "swamp": (80, 90, 40), "dandelion": (255, 255, 120), "cloudberry": (255, 170, 60), "barley": (230, 200, 90), "tar": (40, 30, 30),
          "crystal": (160, 220, 255)}
ZONES = [(0, 12, "Elwynn Forest"), (0, 1, "Dun Morogh"), (0, 85, "Tirisfal Glades"), (1, 14, "Durotar"), (1, 215, "Mulgore"),
         (1, 141, "Teldrassil"), (0, 10, "Duskwood"), (1, 331, "Ashenvale")]


def log(*a):
    s = " ".join(str(v) for v in a)
    print(s, flush=True)
    LINES.append(s)


def nearest_brute(px, py, ax, ay):
    """Pour chaque point (px, py) : (distance, index) du point d'ancrage le plus proche (force brute par blocs)."""
    d_out = np.empty(len(px)); i_out = np.empty(len(px), np.int64)
    for s in range(0, len(px), 512):
        dx = px[s:s + 512, None] - ax[None, :]
        dy = py[s:s + 512, None] - ay[None, :]
        d2 = dx * dx + dy * dy
        i = d2.argmin(1)
        i_out[s:s + 512] = i
        d_out[s:s + 512] = np.sqrt(d2[np.arange(len(i)), i])
    return d_out, i_out


def water_ring(g, x, y, rmax=12.0):
    """Distance a la premiere case d'eau (riviere/lac/ocean, niveau >= sol) sur des anneaux de 1 m, 24 directions ; et son niveau."""
    best_d = np.full(len(x), np.inf); best_l = np.full(len(x), np.nan)
    ang = np.linspace(0, 2 * np.pi, 24, endpoint=False)
    for r in np.arange(1.0, rmax + 0.01, 1.0):
        for a in ang:
            qx, qy = x + r * np.cos(a), y + r * np.sin(a)
            lvl, typ = g.water(qx, qy)
            h = g.height(qx, qy)
            wet = (~np.isnan(lvl)) & (lvl >= h - 0.3) & ((typ == 1) | (typ == 2))
            upd = wet & (r < best_d)
            best_d[upd] = r
            best_l[upd] = lvl[upd]
    return best_d, best_l


def main():
    by_id, _ = area_table()
    P = json.load(open(os.path.join(OUT, "placements.json"), encoding="utf8"))["items"]
    log("placements.json : %d positions" % len(P))
    # ---- statistiques
    tot = collections.Counter(p["kind"] for p in P)
    log("par type : " + ", ".join("%s %d" % kv for kv in sorted(tot.items())))
    pt = collections.defaultdict(collections.Counter)
    for p in P:
        pt[p["tier"]][p["kind"]] += 1
    for t in sorted(pt):
        log("palier %d (%d) : %s" % (t, sum(pt[t].values()), ", ".join("%s %d" % kv for kv in sorted(pt[t].items()))))
    pz = collections.defaultdict(collections.Counter)
    for p in P:
        pz[(p["map"], p["tier"], p["zone"])][p["kind"]] += 1
    log("par zone (carte, palier, zone : total ; arbres / rochers+pierres / minerais / cueillette) :")
    for k in sorted(pz):
        c = pz[k]
        log("  %d T%d %-24s %5d ; arbres %d / rochers %d / minerais %d / cueillette %d" % (
            k[0], k[1], by_id.get(k[2], {}).get("name", k[2]), sum(c.values()), sum(c[x] for x in TREES), c["rock"] + c["stone"],
            sum(c[x] for x in ("copper", "tin", "iron", "silver", "obsidian")),
            sum(c[x] for x in ("flint", "thistle", "raspberry", "blueberry", "mushroom", "branch", "flax"))))
    # ---- verifications globales, recalculees
    fails = collections.Counter()
    ex = {}
    for m in (0, 1):
        g = tg.Grid(m)
        Q = [p for p in P if p["map"] == m]
        x = np.array([p["x"] for p in Q]); y = np.array([p["y"] for p in Q]); z = np.array([p["z"] for p in Q])
        kinds = np.array([p["kind"] for p in Q])
        # passe des departs (place_resources.start_pass) : hetres et rochers places aussi en terrain ouvert quand WoW n'a pas assez
        # d'arbres/rochers pres du depart (Vallee des epreuves...) : comptes a part, pas en echec (controle : start_check.py)
        dep = np.array([p.get("anchor", "").startswith("depart") for p in Q])
        h = g.height(x, y)
        dz = np.abs(h - z)
        log("carte %d : |z - hauteur MCVT| max %.3f m (%d > 0,05 m)" % (m, np.nanmax(dz), int((dz > 0.05).sum())))
        lvl, typ = g.water(x, y)
        inw = (~np.isnan(lvl)) & (lvl >= h - 0.3)
        log("carte %d : positions dans l'eau (niveau >= sol - 0,3 m) : %d" % (m, int(inw.sum())))
        fails["eau"] += int(inw.sum())
        # arbres : 3-15 m de l'arbre WoW le plus proche (arbres + souches/troncs pour le minimum de 3 m)
        tr = json.load(open(os.path.join(OUT, "%d_trees.json" % m)))
        fl = json.load(open(os.path.join(OUT, "%d_flora.json" % m)))
        ax = np.array([t[0] for t in tr["items"]]); ay = np.array([t[1] for t in tr["items"]])
        dw = np.array([t[0] for t in fl["items"] if t[5] == "deadwood"]); dwy = np.array([t[1] for t in fl["items"] if t[5] == "deadwood"])
        sel = np.isin(kinds, list(TREES))
        d, i = nearest_brute(x[sel], y[sel], ax, ay)
        d2, _ = nearest_brute(x[sel], y[sel], np.concatenate([ax, dw]), np.concatenate([ay, dwy]))
        log("carte %d : %d arbres Valheim ; distance a l'arbre WoW le plus proche : min %.2f, mediane %.2f, max %.2f m ; "
            "< 3 m d'un tronc (arbre ou souche) : %d ; > 15 m : %d" % (m, sel.sum(), d.min(), np.median(d), d.max(), int((d2 < 3).sum()), int((d > 15.01).sum())))
        fails["arbre < 3 m"] += int((d2 < 2.999).sum()); fails["arbre > 15 m"] += int(((d > 15.01) & ~dep[sel]).sum())
        log("carte %d : dont arbres de la passe des departs a plus de 15 m d'un arbre WoW (terrain ouvert, voulu) : %d"
            % (m, int(((d > 15.01) & dep[sel]).sum())))
        ex[(m, "tree")] = [(Q[np.flatnonzero(sel)[j]], d[j], tr["models"][tr["items"][i[j]][4]], tr["items"][i[j]]) for j in range(len(d))]
        # berges
        sel = np.isin(kinds, list(SHORE))
        wd, wl = water_ring(g, x[sel], y[sel])
        above = z[sel] - wl
        log("carte %d : %d silex/chardons/etain ; eau a <= 12 m : %d ; distance a l'eau mediane %.0f m, max %.0f m ; sol - niveau de l'eau : "
            "min %.2f, mediane %.2f m" % (m, sel.sum(), int(np.isfinite(wd).sum()), np.median(wd[np.isfinite(wd)]), np.max(wd[np.isfinite(wd)]),
                                         np.nanmin(above), np.nanmedian(above)))
        fails["berge sans eau a 12 m"] += int((~np.isfinite(wd)).sum())
        ex[(m, "shore")] = [(Q[np.flatnonzero(sel)[j]], wd[j], wl[j]) for j in range(sel.sum())]
        # rochers : pres d'un rocher WoW, ou pente / pied de falaise
        rk = json.load(open(os.path.join(OUT, "%d_rocks.json" % m)))
        rx = np.array([t[0] for t in rk["items"]]); ry = np.array([t[1] for t in rk["items"]])
        sel = kinds == "rock"
        dr, ir = nearest_brute(x[sel], y[sel], rx, ry)
        # pente max dans un rayon de 9 m (recalculee sur la grille)
        smax = np.zeros(sel.sum())
        for ddx in (-8, -4, 0, 4, 8):
            for ddy in (-8, -4, 0, 4, 8):
                smax = np.maximum(smax, np.nan_to_num(g.slope_at(x[sel] + ddx, y[sel] + ddy)))
        ok = (dr <= 12) | (smax >= 25)
        log("carte %d : %d rochers ; a <= 12 m d'un rocher WoW : %d ; pente >= 25 deg a <= 9 m : %d ; ni l'un ni l'autre : %d"
            % (m, sel.sum(), int((dr <= 12).sum()), int((smax >= 25).sum()), int((~ok).sum())))
        fails["rocher isole en plat"] += int((~ok & ~dep[sel]).sum())
        log("carte %d : dont rochers de la passe des departs en terrain plat sans rocher WoW (voulu) : %d" % (m, int((~ok & dep[sel]).sum())))
        ex[(m, "rock")] = [(Q[np.flatnonzero(sel)[j]], dr[j], rk["models"][rk["items"][ir[j]][4]], smax[j]) for j in range(sel.sum())]
        # amas de cuivre
        cl = collections.defaultdict(list)
        for p in Q:
            if p["kind"] == "copper":
                cl[p["anchor"].split(" ; ")[0]].append((p["x"], p["y"]))
        if cl:
            sizes = [len(v) for v in cl.values()]
            spans = [max(math.hypot(a[0] - b[0], a[1] - b[1]) for a in v for b in v) for v in cl.values()]
            log("carte %d : cuivre %d filons en %d amas ; filons par amas %d-%d (moy %.1f) ; etendue d'un amas %.0f-%.0f m (moy %.0f)"
                % (m, sum(sizes), len(cl), min(sizes), max(sizes), np.mean(sizes), min(spans), max(spans), np.mean(spans)))
            ex[(m, "copper")] = list(cl.items())
        ex[(m, "grid")] = g
    log("ECHECS : %s" % dict(fails))
    # ---- 5 verifications ponctuelles (premier element de chaque cas dans Elwynn / Durotar / Ashenvale / Duskwood)
    log("verifications ponctuelles :")
    def first(lst, pred):
        for e in lst:
            if pred(e):
                return e
    e = first(ex[(0, "tree")], lambda e: e[0]["kind"] == "beech" and e[0]["zone"] == 12)
    log("  1. %s (%.1f, %.1f, z %.1f) Elwynn : arbre WoW le plus proche %s a (%.1f, %.1f), a %.1f m (recalcule par force brute)"
        % (e[0]["kind"], e[0]["x"], e[0]["y"], e[0]["z"], e[2].rsplit("\\", 1)[-1], e[3][0], e[3][1], e[1]))
    e = first(ex[(1, "tree")], lambda e: e[0]["kind"] == "fir" and e[0]["zone"] == 331)
    log("  2. %s (%.1f, %.1f, z %.1f) Ashenvale : arbre WoW le plus proche %s a (%.1f, %.1f), a %.1f m"
        % (e[0]["kind"], e[0]["x"], e[0]["y"], e[0]["z"], e[2].rsplit("\\", 1)[-1], e[3][0], e[3][1], e[1]))
    e = first(ex[(0, "shore")], lambda e: e[0]["kind"] == "flint" and e[0]["zone"] == 12)
    log("  3. silex (%.1f, %.1f, z %.2f) Elwynn : premiere case d'eau a %.0f m, niveau %.2f m -> sol %.2f m au-dessus de l'eau"
        % (e[0]["x"], e[0]["y"], e[0]["z"], e[1], e[2], e[0]["z"] - e[2]))
    e = first(ex[(1, "rock")], lambda e: e[0]["zone"] == 14)
    log("  4. rocher (%.1f, %.1f, z %.1f) Durotar : rocher WoW le plus proche %s a %.1f m ; pente max a <= 9 m %.0f deg"
        % (e[0]["x"], e[0]["y"], e[0]["z"], e[2].rsplit("\\", 1)[-1], e[1], e[3]))
    nm, pts = ex[(0, "copper")][0]
    span = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a in pts for b in pts)
    log("  5. %s : %d filons, etendue %.0f m : %s" % (nm, len(pts), span, "; ".join("(%.0f, %.0f)" % p for p in pts)))
    e = first(ex[(1, "shore")], lambda e: e[0]["kind"] == "tin")
    log("  6. etain (%.1f, %.1f, z %.2f) zone %s : eau a %.0f m, niveau %.2f m (sol %.2f m au-dessus)"
        % (e[0]["x"], e[0]["y"], e[0]["z"], by_id.get(e[0]["zone"], {}).get("name"), e[1], e[2], e[0]["z"] - e[2]))
    # ---- cartes
    os.makedirs(MAPS_DIR, exist_ok=True)
    for (m, zid, name) in ZONES:
        render(ex[(m, "grid")], m, zid, name, [p for p in P if p["map"] == m and p["zone"] == zid], by_id)
    open(os.path.join(OUT, "checks.txt"), "w", encoding="utf8").write("\n".join(LINES) + "\n")


def render(g, m, zid, name, P, by_id):
    lut = np.zeros(max(by_id) + 1, np.int32)
    for a, v in by_id.items():
        lut[a] = v["zone"] or a
    ks = [k for k in range(len(g.tiles)) if (lut[np.clip(g.area[k], 0, len(lut) - 1)] == zid).any()]
    if not ks:
        return
    xs, ys = [], []
    for k in ks:
        zc = lut[np.clip(g.area[k], 0, len(lut) - 1)] == zid
        A, B = g.tiles[k]
        rr, cc = np.nonzero(zc)
        xs += list((32 - B) * tg.TS - rr * tg.TS / 16); ys += list((32 - A) * tg.TS - cc * tg.TS / 16)
    xmax, xmin = max(xs) + 60, min(xs) - tg.TS / 16 - 60
    ymax, ymin = max(ys) + 60, min(ys) - tg.TS / 16 - 60
    W = int((ymax - ymin) / tg.UNIT); H = int((xmax - xmin) / tg.UNIT)
    img = np.zeros((H, W, 3), np.float32)
    # terrain : grille des centres de cases
    rows = xmax - (np.arange(H) + 0.5) * tg.UNIT
    cols = ymax - (np.arange(W) + 0.5) * tg.UNIT
    X, Y = np.meshgrid(rows, cols, indexing="ij")
    h = g.height(X, Y)
    sl = g.slope_at(X, Y)
    lvl, typ = g.water(X, Y)
    road = g.road_at(X, Y)
    aid = g.area_at(X, Y)
    inz = lut[np.clip(aid, 0, len(lut) - 1)] == zid
    hn = np.nan_to_num((h - np.nanpercentile(h, 2)) / max(1.0, np.nanpercentile(h, 98) - np.nanpercentile(h, 2)), nan=0.0).clip(0, 1)
    gy, gx = np.gradient(np.nan_to_num(h))
    shade = (0.75 + 0.25 * np.clip((gx - gy) / 3.0, -1, 1))
    base = np.stack([0.35 + 0.45 * hn, 0.45 + 0.35 * hn, 0.25 + 0.3 * hn], -1)
    steep = np.clip((np.nan_to_num(sl) - 25) / 20, 0, 1)[..., None]
    base = base * (1 - steep) + np.array([0.55, 0.45, 0.4]) * steep
    img = base * shade[..., None]
    wet = (~np.isnan(lvl)) & (lvl >= h - 0.3)
    img[wet & (typ == 2)] = (0.1, 0.2, 0.55)
    img[wet & (typ != 2)] = (0.2, 0.45, 0.9)
    img[(road >= 100) & ~wet] = (0.8, 0.7, 0.5)
    img[~inz] *= 0.45
    im = Image.fromarray((img.clip(0, 1) * 255).astype(np.uint8)).resize((W * 2, H * 2), Image.NEAREST)
    dr = ImageDraw.Draw(im)
    def pix(x, y):
        return (ymax - y) / tg.UNIT * 2, (xmax - x) / tg.UNIT * 2
    for cls, fn, col in (("tree", "%d_trees.json", (10, 60, 10)), ("rock", "%d_rocks.json", (90, 90, 90))):
        for t in json.load(open(os.path.join(OUT, fn % m)))["items"]:
            if xmin <= t[0] <= xmax and ymin <= t[1] <= ymax:
                px, py = pix(t[0], t[1])
                dr.rectangle([px - 1, py - 1, px + 1, py + 1], fill=col)
    for w in json.load(open(os.path.join(OUT, "%d_wmos.json" % m)))["items"]:
        if xmin <= w[1] <= xmax and ymin <= w[2] <= ymax and w[5] - w[4] < 300 and w[7] - w[6] < 300:
            a = pix(w[5], w[7]); b = pix(w[4], w[6])
            dr.rectangle([a[0], a[1], b[0], b[1]], outline=(255, 60, 60))
    cnt = collections.Counter()
    for p in P:
        px, py = pix(p["x"], p["y"])
        r = 4 if p["kind"] in ("copper", "tin", "iron", "silver", "obsidian") else 3
        dr.ellipse([px - r, py - r, px + r, py + r], fill=COLORS[p["kind"]], outline=(0, 0, 0))
        cnt[p["kind"]] += 1
    # legende
    items = sorted(cnt.items())
    lh = 14 * (len(items) + 5) + 8
    dr.rectangle([4, 4, 250, 4 + lh], fill=(255, 255, 255), outline=(0, 0, 0))
    dr.text((10, 8), "%s (carte %d) - nord en haut" % (name, m), fill=(0, 0, 0))
    yy = 24
    for k, n in items:
        dr.ellipse([10, yy + 2, 18, yy + 10], fill=COLORS[k], outline=(0, 0, 0))
        dr.text((24, yy), "%s %d" % (k, n), fill=(0, 0, 0))
        yy += 14
    for txt, col in (("arbre WoW (doodad)", (10, 60, 10)), ("rocher WoW (doodad)", (90, 90, 90)), ("batiment (boite WMO)", (255, 60, 60)),
                     ("eau bleue, route beige, falaise brune", (0, 0, 0))):
        dr.rectangle([10, yy + 3, 18, yy + 9], fill=col)
        dr.text((24, yy), txt, fill=(0, 0, 0))
        yy += 14
    fn = os.path.join(MAPS_DIR, "%d_%s.png" % (m, name.replace(" ", "_").replace("'", "")))
    im.save(fn)
    log("carte PNG : %s (%dx%d px, 1 px = %.2f m)" % (fn, im.size[0], im.size[1], tg.UNIT / 2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf8")
    main()
