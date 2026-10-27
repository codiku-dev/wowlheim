"""Terrain statique (hauteur, trous, eau) lu dans les fichiers .map extraits du client (C:\\Wowlheim\\data\\maps).

Reimplementation en Python de GridMap::getHeightFromFloat/Uint16/Uint8, isHole et de la detection d'eau de GridMap::getLiquidStatus
(source lu : C:\\Wowlheim\\src\\mangos-classic\\src\\game\\Maps\\GridMap.cpp). Terrain SEULEMENT : les modeles (vmaps : batiments, ponts,
arbres de decor) ne sont pas pris en compte. Utilise par gen_nodes_production.py et check_nodes.py. Lecture seule."""
import os, struct
from common import DATA

SIZE_OF_GRIDS = 533.33333
RES = 128
INVALID = -200000.0
HOLETAB_H = (0x1111, 0x2222, 0x4444, 0x8888)
HOLETAB_V = (0x000F, 0x00F0, 0x0F00, 0xF000)


class Tile:
    __slots__ = ("kind", "grid_h", "mult", "v9", "v8", "holes", "liq_flags_g", "liq_off", "liq_wh", "liq_level", "liq_cells", "liq_map")


_cache = {}


def _load(mapid, gx, gy):
    k = (mapid, gx, gy)
    if k in _cache:
        return _cache[k]
    t = None
    p = os.path.join(DATA, "maps", "%03u%02u%02u.map" % k)
    if os.path.exists(p):
        d = open(p, "rb").read()
        hdr = struct.unpack_from("<10I", d, 0)
        _mm, _vm, _ao, _as, ho, _hs, lo, _ls, holo, _hols = hdr
        t = Tile()
        t.kind, t.grid_h, t.mult, t.v9, t.v8, t.holes = "none", INVALID, 0.0, None, None, None
        t.liq_flags_g, t.liq_off, t.liq_wh, t.liq_level, t.liq_cells, t.liq_map = 0, (0, 0), (0, 0), INVALID, None, None
        if ho:
            fourcc, flags, gh, gmax = struct.unpack_from("<IIff", d, ho)
            o = ho + 16
            t.grid_h = gh
            if flags & 1:
                t.kind = "flat"
            elif flags & 2:
                t.kind = "u16"
                t.v9 = struct.unpack_from("<%dH" % (129 * 129), d, o)
                t.v8 = struct.unpack_from("<%dH" % (128 * 128), d, o + 129 * 129 * 2)
                t.mult = (gmax - gh) / 65535
            elif flags & 4:
                t.kind = "u8"
                t.v9 = d[o:o + 129 * 129]
                t.v8 = d[o + 129 * 129:o + 129 * 129 + 128 * 128]
                t.mult = (gmax - gh) / 255
            else:
                t.kind = "f"
                t.v9 = struct.unpack_from("<%df" % (129 * 129), d, o)
                t.v8 = struct.unpack_from("<%df" % (128 * 128), d, o + 129 * 129 * 4)
        if holo:
            t.holes = struct.unpack_from("<256H", d, holo)
        if lo:
            fourcc, fl, lflags, ltype, offx, offy, w, h, lvl = struct.unpack_from("<IBBHBBBBf", d, lo)
            o = lo + 16
            t.liq_flags_g, t.liq_off, t.liq_wh, t.liq_level = lflags, (offx, offy), (w, h), lvl
            if not (fl & 1):
                o += 256 * 2
                t.liq_cells = d[o:o + 256]
                o += 256
            if not (fl & 2):
                t.liq_map = struct.unpack_from("<%df" % (w * h), d, o)
    _cache[k] = t
    return t


def _tile(mapid, x, y):
    return _load(mapid, int(32 - x / SIZE_OF_GRIDS), int(32 - y / SIZE_OF_GRIDS))


def height(mapid, x, y):
    """Hauteur du terrain statique, ou None (pas de carte / trou)."""
    t = _tile(mapid, x, y)
    if t is None or t.kind == "none":
        return None
    if t.kind == "flat":
        return t.grid_h
    fx = RES * (32 - x / SIZE_OF_GRIDS)
    fy = RES * (32 - y / SIZE_OF_GRIDS)
    xi, yi = int(fx), int(fy)
    fx -= xi
    fy -= yi
    xi &= RES - 1
    yi &= RES - 1
    if t.kind == "f" and t.holes is not None:
        cr, cc = xi // 8, yi // 8
        hr, hc = xi % 8 // 2, (yi - cc * 8) // 2
        if t.holes[cr * 16 + cc] & HOLETAB_H[hc] & HOLETAB_V[hr]:
            return None
    v9, v8 = t.v9, t.v8
    i = xi * 129 + yi
    h5 = 2 * v8[xi * 128 + yi]
    if fx + fy < 1:
        if fx > fy:
            h1, h2 = v9[i], v9[i + 129]
            a, b, c = h2 - h1, h5 - h1 - h2, h1
        else:
            h1, h3 = v9[i], v9[i + 1]
            a, b, c = h5 - h1 - h3, h3 - h1, h1
    else:
        if fx > fy:
            h2, h4 = v9[i + 129], v9[i + 130]
            a, b, c = h2 + h4 - h5, h4 - h2, h5 - h4
        else:
            h3, h4 = v9[i + 1], v9[i + 130]
            a, b, c = h4 - h3, h3 + h4 - h5, h5 - h4
    r = a * fx + b * fy + c
    return r * t.mult + t.grid_h if t.kind != "f" else r


def has_water(mapid, x, y):
    """True si la cellule contient un liquide dont le niveau est au-dessus du sol (meme test que getLiquidStatus, sans le type)."""
    t = _tile(mapid, x, y)
    if t is None or (t.liq_cells is None and not t.liq_flags_g):
        return False
    cx = RES * (32 - x / SIZE_OF_GRIDS)
    cy = RES * (32 - y / SIZE_OF_GRIDS)
    xi, yi = int(cx) & (RES - 1), int(cy) & (RES - 1)
    idx = (xi >> 3) * 16 + (yi >> 3)
    flag = t.liq_cells[idx] if t.liq_cells is not None else t.liq_flags_g
    if not flag:
        return False
    lx, ly = xi - t.liq_off[1], yi - t.liq_off[0]
    w, h = t.liq_wh
    if lx < 0 or lx >= h or ly < 0 or ly >= w:
        return False
    lvl = t.liq_map[lx * w + ly] if t.liq_map is not None else t.liq_level
    g = height(mapid, x, y)
    if g is None:
        return True
    return lvl >= g


def near_water(mapid, x, y, r=6.0):
    """Eau au point ou a r metres (N/S/E/O)."""
    return any(has_water(mapid, x + dx, y + dy) for dx, dy in ((0, 0), (r, 0), (-r, 0), (0, r), (0, -r)))


def water_distance(mapid, x, y, r=15.0, step=3.0):
    """Distance approchee (pas de 3 m, 8 directions) a la plus proche eau du terrain jusqu'a r metres ; None si aucune.
    Liquide du terrain (.map) seulement : l'eau des modeles (WMO) n'est pas vue ; le type de liquide (eau / magma / slime) n'est pas distingue."""
    if has_water(mapid, x, y):
        return 0.0
    d = step
    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1), (0.7071, 0.7071), (0.7071, -0.7071), (-0.7071, 0.7071), (-0.7071, -0.7071)]
    while d <= r + 1e-6:
        if any(has_water(mapid, x + dx * d, y + dy * d) for dx, dy in dirs):
            return d
        d += step
    return None
