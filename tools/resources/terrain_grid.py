r"""Acces au terrain extrait par terrain_scan.py (C:\Wowlheim\data\wl_terrain\{m}_grid.npz) en coordonnees monde serveur.
Fonctions vectorisees (numpy) : hauteur (interpolation par triangles, meme formule que GridMap::getHeightFromFloat du serveur),
pente, eau (niveau + type), route, trou. Lecture seule."""
import os
import numpy as np

OUT = r"C:\Wowlheim\data\wl_terrain"
TS = 1600.0 / 3.0
UNIT = TS / 128.0


class Grid:
    def __init__(self, m):
        z = np.load(os.path.join(OUT, "%d_grid.npz" % m))
        self.m = m
        self.tiles = z["tiles"]
        self.v9, self.v8, self.holes = z["v9"], z["v8"], z["holes"]
        self.wl, self.wt, self.road = z["wl"], z["wt"], z["road"]
        self.area = z["area"]                     # (n, 16, 16) : AreaTable.ID de chaque chunk MCNK (lu dans l'ADT)
        self.idx = np.full((64, 64), -1, np.int32)
        for k, (A, B) in enumerate(self.tiles):
            self.idx[A, B] = k
        # pente par case (degres), comme terrain_scan.slope_deg, pour toutes les tuiles
        v9 = self.v9
        dx = ((v9[:, 1:, :-1] - v9[:, :-1, :-1]) + (v9[:, 1:, 1:] - v9[:, :-1, 1:])) / (2 * UNIT)
        dy = ((v9[:, :-1, 1:] - v9[:, :-1, :-1]) + (v9[:, 1:, 1:] - v9[:, 1:, :-1])) / (2 * UNIT)
        self.slope = np.degrees(np.arctan(np.hypot(dx, dy))).astype(np.float32)

    def locate(self, x, y):
        """-> (k tuile ou -1, ligne, colonne, fraction ligne, fraction colonne) ; x, y scalaires ou tableaux."""
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        gx = 32.0 - x / TS
        gy = 32.0 - y / TS
        B = np.floor(gx).astype(np.int64)
        A = np.floor(gy).astype(np.int64)
        ok = (A >= 0) & (A < 64) & (B >= 0) & (B < 64)
        k = np.where(ok, self.idx[np.clip(A, 0, 63), np.clip(B, 0, 63)], -1)
        fx = (gx - B) * 128.0
        fy = (gy - A) * 128.0
        r = np.clip(np.floor(fx).astype(np.int64), 0, 127)
        c = np.clip(np.floor(fy).astype(np.int64), 0, 127)
        return k, r, c, fx - r, fy - c

    def height(self, x, y):
        """Hauteur du terrain statique (NaN hors tuile ou dans un trou)."""
        k, r, c, fx, fy = self.locate(x, y)
        kk = np.maximum(k, 0)
        v9, v8 = self.v9, self.v8
        h1 = v9[kk, r, c]; h2 = v9[kk, r + 1, c]; h3 = v9[kk, r, c + 1]; h4 = v9[kk, r + 1, c + 1]
        h5 = 2.0 * v8[kk, r, c]
        lower = fx + fy < 1
        gt = fx > fy
        a = np.where(lower, np.where(gt, h2 - h1, h5 - h1 - h3), np.where(gt, h2 + h4 - h5, h4 - h3))
        b = np.where(lower, np.where(gt, h5 - h1 - h2, h3 - h1), np.where(gt, h4 - h2, h3 + h4 - h5))
        cc = np.where(lower, h1, h5 - h4)
        h = a * fx + b * fy + cc
        bad = (k < 0) | self.holes[kk, r, c]
        return np.where(bad, np.nan, h)

    def cell(self, x, y):
        k, r, c, _fx, _fy = self.locate(x, y)
        return k, r, c

    def slope_at(self, x, y):
        k, r, c = self.cell(x, y)
        return np.where(k >= 0, self.slope[np.maximum(k, 0), r, c], np.nan)

    def water(self, x, y):
        """(niveau, type) de la case (NaN, 0 sans eau). type 1 riviere/lac, 2 ocean, 3 magma, 4 slime."""
        k, r, c = self.cell(x, y)
        kk = np.maximum(k, 0)
        lvl = np.where(k >= 0, self.wl[kk, r, c], np.nan)
        typ = np.where(k >= 0, self.wt[kk, r, c], 0)
        return lvl, typ

    def road_at(self, x, y):
        k, r, c = self.cell(x, y)
        return np.where(k >= 0, self.road[np.maximum(k, 0), r, c], 0)

    def area_at(self, x, y):
        """AreaTable.ID du chunk MCNK sous le point (0 hors tuile)."""
        k, r, c = self.cell(x, y)
        return np.where(k >= 0, self.area[np.maximum(k, 0), r // 8, c // 8], 0)

    def padded(self, name, k, P, fill):
        """Tableau 128x128 de la tuile k entoure de P cases prises dans les tuiles voisines (fill si absente)."""
        arr = getattr(self, name)
        out = np.full((128 + 2 * P, 128 + 2 * P), fill, arr.dtype)
        A, B = self.tiles[k]
        for dA in (-1, 0, 1):
            for dB in (-1, 0, 1):
                a, b = A + dA, B + dB
                if not (0 <= a < 64 and 0 <= b < 64) or self.idx[a, b] < 0:
                    continue
                src = arr[self.idx[a, b]]
                # ligne = direction B (X), colonne = direction A (Y)
                r0 = P + 128 * dB; c0 = P + 128 * dA
                rs, re_ = max(0, r0), min(128 + 2 * P, r0 + 128)
                cs, ce = max(0, c0), min(128 + 2 * P, c0 + 128)
                if rs < re_ and cs < ce:
                    out[rs:re_, cs:ce] = src[rs - r0:re_ - r0, cs - c0:ce - c0]
        return out

    def cell_centers(self, k):
        """Centres (x, y) des 128x128 cases de la tuile k."""
        A, B = self.tiles[k]
        i = np.arange(128) + 0.5
        X = (32 - B) * TS - i * UNIT
        Y = (32 - A) * TS - i * UNIT
        return np.meshgrid(X, Y, indexing="ij")
