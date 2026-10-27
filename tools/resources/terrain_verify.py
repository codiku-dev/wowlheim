r"""Controles de la conversion ADT -> coordonnees monde serveur (terrain_scan.py). Lecture seule.
usage : C:\Wowlheim\tools\unity_venv\Scripts\python.exe terrain_verify.py   -> C:\Wowlheim\data\wl_terrain\verify.txt

1. Hauteurs : terrain_grid.height (MCVT des ADT) contre nodes_terrain.height (fichiers .map du serveur, extracteur de mangos) sur des
   points tires au hasard : meme repere => ecart ~0.
2. Eau : masque MCLQ contre nodes_terrain.has_water (meme point).
3. Doodads : z de l'arbre (MDDF) contre la hauteur du terrain sous lui, avec la conversion retenue et avec les conversions fautives
   (axes permutes, signes inverses) : seule la bonne colle au sol.
4. Points connus : PNJ de la base (aubergistes, Northshire) contre le WMO le plus proche (auberges de Goldshire, Brill, Razor Hill ;
   abbaye de Northshire)."""
import os, sys, json, math, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import terrain_grid as tg
import nodes_terrain as nt

OUT = tg.OUT
LINES = []


def log(*a):
    s = " ".join(str(v) for v in a)
    print(s)
    LINES.append(s)


def main():
    rnd = random.Random(1)
    for m in (0, 1):
        g = tg.Grid(m)
        # 1 + 2 : hauteurs et eau sur 3000 points
        xs, ys = [], []
        while len(xs) < 3000:
            k = rnd.randrange(len(g.tiles))
            A, B = g.tiles[k]
            x = (32 - B) * tg.TS - rnd.random() * tg.TS
            y = (32 - A) * tg.TS - rnd.random() * tg.TS
            xs.append(x); ys.append(y)
        xs, ys = np.array(xs), np.array(ys)
        h = g.height(xs, ys)
        diffs, wat_ok, wat_n, wat_both, clamp = [], 0, 0, 0, 0
        lvl, typ = g.water(xs, ys)
        for i in range(len(xs)):
            hs = nt.height(m, xs[i], ys[i])
            if hs is None or np.isnan(h[i]):
                continue
            if hs <= -499.9:          # fond marin : l'extracteur de mangos borne les hauteurs a -500 (CONF_use_minHeight)
                clamp += 1
                continue
            diffs.append(abs(hs - h[i]))
            a = bool(nt.has_water(m, xs[i], ys[i]))
            b = bool(not np.isnan(lvl[i]) and lvl[i] >= h[i])
            wat_n += 1
            wat_ok += a == b
            wat_both += a and b
        d = np.array(diffs)
        log("carte %d : hauteur ADT vs .map serveur sur %d points : mediane %.3f m, 99e centile %.3f m, max %.3f m "
            "(%d points de fond marin exclus : .map borne a -500 m)" % (m, len(d), np.median(d), np.percentile(d, 99), d.max(), clamp))
        log("carte %d : eau (MCLQ, niveau >= sol) vs nodes_terrain.has_water : accord %d/%d (%.1f %%), dont %d points d'eau communs"
            % (m, wat_ok, wat_n, 100.0 * wat_ok / max(1, wat_n), wat_both))
        # 3 : doodads au sol
        tr = json.load(open(os.path.join(OUT, "%d_trees.json" % m)))["items"]
        sample = rnd.sample(tr, min(3000, len(tr)))
        X = np.array([t[0] for t in sample]); Y = np.array([t[1] for t in sample]); Z = np.array([t[2] for t in sample])
        M = 32 * tg.TS
        variants = {
            "retenue  X=M-p2, Y=M-p0": (X, Y),
            "permutee X=M-p0, Y=M-p2": (Y, X),
            "signe    X=p2-M, Y=p0-M": (-X, -Y),
        }
        for nm, (vx, vy) in variants.items():
            hh = g.height(vx, vy)
            ok = ~np.isnan(hh)
            dz = np.abs(hh[ok] - Z[ok])
            log("carte %d : arbres WoW, conversion %s : %d/%d sur une tuile, |z_arbre - sol| mediane %.2f m, < 2 m : %.1f %%"
                % (m, nm, ok.sum(), len(X), np.median(dz) if len(dz) else float("nan"), 100.0 * (dz < 2).mean() if len(dz) else 0))
    # 4 : points connus
    try:
        from common import sql
        rows = sql("select t.Name, c.map, c.position_x, c.position_y, c.position_z from creature c join creature_template t on t.Entry=c.id "
                   "where t.Name in ('Innkeeper Farley','Innkeeper Renee','Innkeeper Grosk','Deputy Willem','Brother Sammuel','Marshal McBride')")
    except Exception as e:
        rows = []
        log("base indisponible :", e)
    wm = {m: json.load(open(os.path.join(OUT, "%d_wmos.json" % m)))["items"] for m in (0, 1)}
    for name, m, x, y, z in rows:
        m, x, y, z = int(m), float(x), float(y), float(z)
        best = min(wm[m], key=lambda w: (w[1] - x) ** 2 + (w[2] - y) ** 2)
        inside = [w[0].rsplit("\\", 1)[-1] for w in wm[m] if w[4] <= x <= w[5] and w[6] <= y <= w[7] and w[8] - 5 <= z <= w[9] + 5]
        log("PNJ %-18s (%d, %.1f, %.1f, %.1f) : WMO le plus proche %s a %.1f m ; dans la boite englobante de : %s"
            % (name, m, x, y, z, best[0].rsplit("\\", 1)[-1], math.hypot(best[1] - x, best[2] - y), ", ".join(sorted(set(inside))) or "-"))
    open(os.path.join(OUT, "verify.txt"), "w", encoding="utf8").write("\n".join(LINES) + "\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf8")
    main()
