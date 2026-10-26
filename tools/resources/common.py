"""Outils communs Wowlheim/ressources : acces MySQL local (client mysql.exe), lecture DBC et zones (fichiers .map)."""
import os, struct, subprocess

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
DATA = r"C:\Wowlheim\data"
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GAME_DB = "classicmangos"


def sql(query, db=GAME_DB, rows=True):
    """Execute une requete (127.0.0.1, root sans mdp). Retourne une liste de tuples de chaines (NULL -> None)."""
    cmd = [MYSQL, "--user=root", "--host=127.0.0.1", "--default-character-set=utf8mb4", "-B", "-N", "--raw", db, "-e", query]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf8", "replace"))
    if not rows:
        return None
    out = []
    for line in r.stdout.decode("utf8").splitlines():
        out.append(tuple(None if c == "NULL" else c for c in line.split("\t")))
    return out


def sql_file(path, db):
    """Applique un fichier .sql sur la base `db` (utilise par les validations sur wl_scratch uniquement)."""
    with open(path, "rb") as f:
        r = subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "--default-character-set=utf8mb4", db], stdin=f, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf8", "replace"))


# ---------------------------------------------------------------- DBC
def read_dbc(name):
    d = open(os.path.join(DATA, "dbc", name), "rb").read()
    magic, rc, fc, rs, ss = struct.unpack_from("<4sIIII", d, 0)
    assert magic == b"WDBC"
    recs = [struct.unpack_from("<%dI" % fc, d, 20 + i * rs) for i in range(rc)]
    sb = d[20 + rc * rs:]
    def s(o):
        return sb[o:sb.find(b"\0", o)].decode("utf8", "replace")
    return recs, s


_area_cache = None
def area_table():
    """AreaTable.dbc : id -> dict(map, zone, bit, name) ; index (map, bit) -> id."""
    global _area_cache
    if _area_cache:
        return _area_cache
    recs, s = read_dbc("AreaTable.dbc")
    by_id, by_bit = {}, {}
    for r in recs:
        by_id[r[0]] = dict(id=r[0], map=r[1], zone=r[2], bit=r[3], name=s(r[11]))
        by_bit[(r[1], r[3])] = r[0]
    _area_cache = (by_id, by_bit)
    return _area_cache


# ---------------------------------------------------------------- zones d'apres les fichiers .map (meme algorithme que GridMap::getArea)
SIZE_OF_GRIDS = 533.33333
_grid_cache = {}
def _grid_area(mapid, gx, gy):
    k = (mapid, gx, gy)
    if k in _grid_cache:
        return _grid_cache[k]
    p = os.path.join(DATA, "maps", "%03u%02u%02u.map" % k)
    res = None
    if os.path.exists(p):
        d = open(p, "rb").read()
        hdr = struct.unpack_from("<10I", d, 0)
        off = hdr[2]
        if off:
            fourcc, flags, grid_area = struct.unpack_from("<IHH", d, off)
            if flags & 1:
                res = grid_area
            else:
                res = struct.unpack_from("<256H", d, off + 8)
    _grid_cache[k] = res
    return res


def area_flag(mapid, x, y):
    gx = int(32 - x / SIZE_OF_GRIDS)
    gy = int(32 - y / SIZE_OF_GRIDS)
    g = _grid_area(mapid, gx, gy)
    if g is None:
        return None
    if isinstance(g, int):
        return g
    fx = int(16 * (32 - x / SIZE_OF_GRIDS)) & 15
    fy = int(16 * (32 - y / SIZE_OF_GRIDS)) & 15
    return g[fx * 16 + fy]


def zone_of(mapid, x, y):
    """(zone_id, zone_name, area_id, area_name) ou None. Zone = AreaTable.zone (parent) sinon l'aire elle-meme."""
    by_id, by_bit = area_table()
    fl = area_flag(mapid, x, y)
    if fl is None:
        return None
    aid = by_bit.get((mapid, fl))
    if aid is None:
        return None
    a = by_id[aid]
    z = by_id.get(a["zone"], a) if a["zone"] else a
    return (z["id"], z["name"], a["id"], a["name"])
