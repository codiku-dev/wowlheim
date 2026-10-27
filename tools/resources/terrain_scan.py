r"""Extraction du terrain du client 1.12.1 (tuiles ADT) pour placer les ressources Valheim de facon credible.
LECTURE SEULE des MPQ du client (priorite des archives : tools/client/mpq_layers.py). N'ecrit que dans C:\Wowlheim\data\wl_terrain.

usage (python du venv tools valheim, qui a numpy ; mpyq est pris dans tools/client/.venv) :
  C:\Wowlheim\tools\unity_venv\Scripts\python.exe terrain_scan.py [--maps 0,1] [--limit N]
  C:\Wowlheim\tools\unity_venv\Scripts\python.exe terrain_scan.py --verify     # controles de la conversion de coordonnees

Sorties (par carte m = 0 Azeroth / 1 Kalimdor), C:\Wowlheim\data\wl_terrain\ :
  {m}_grid.npz    par tuile : hauteurs MCVT (v9 129x129, v8 128x128, absolues), trous (128x128), eau (niveau 128x128, NaN = pas d'eau ;
                  type 128x128 : 1 riviere/lac, 2 ocean, 3 magma, 4 slime), route (128x128, alpha 0-255 des couches de texture de route)
  {m}_trees.json  doodads M2 classes « arbre »   [ [x, y, z, echelle, id_modele], ... ] + table des modeles
  {m}_rocks.json  doodads M2 classes « rocher »  (idem)
  {m}_wmos.json   WMO places (MODF : batiments, ponts, villes) : nom, position, boite englobante monde
  {m}_water.json  resume par chunk de 33,33 m : [x_centre, y_centre, niveau, type, nb_cases_rendues]
  {m}_slopes.json resume par chunk : [x_centre, y_centre, pente_max_deg, part_de_cases > 35 deg, hauteur_moy]

Repere : coordonnees MONDE SERVEUR (celles de la table creature). Tuile ADT Map_A_B ; chunk MCNK (ligne r = indexY, colonne c = indexX) ;
sommet (i, j) de la grille 9x9 :  X = (32 - B) * 533,333 - (8r + i) * 4,1667 ;  Y = (32 - A) * 533,333 - (8c + j) * 4,1667.
Doodads (MDDF/MODF, repere « placement » p0, p1, p2) :  X = 17066,67 - p2 ;  Y = 17066,67 - p0 ;  Z = p1.
Les deux formules sont controlees par --verify (position MCNK lue dans le fichier, hauteurs comparees aux .map du serveur,
doodads de Northshire/Goldshire)."""
import os, sys, re, json, struct, math, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools", "client"))
sys.path.insert(0, os.path.join(REPO, "tools", "client", ".venv", "Lib", "site-packages"))   # mpyq (pur Python)
import numpy as np
import mpq_layers

DATA_DIR = r"C:\Wowlheim\client_test\Data"
OUT = r"C:\Wowlheim\data\wl_terrain"
TS = 1600.0 / 3.0          # 533,333 m : tuile ADT
CH = TS / 16.0             # 33,333 m : chunk MCNK
UNIT = CH / 8.0            # 4,1667 m : case (sous-chunk)
MAX = 32.0 * TS            # 17 066,67
MAPS = {0: "Azeroth", 1: "Kalimdor"}

# ---------------------------------------------------------------- classes de doodads (nom du fichier M2, insensible a la casse)
# Regles dans l'ordre ; la premiere qui correspond gagne. Inventaire complet et classe attribuee : {m}_models.tsv (sortie du scan).
# « Faux amis » ecartes d'abord (decor de batiment ou d'eau contenant un mot d'arbre / de rocher).
NOT_NATURE_RE = re.compile(r"street|lamp|cart|fence|banner|treasure|treant|sign|torch|crate|lantern|christmas|winterveil|xmas|holiday|"
                           r"bucket|stool|barrel|chair|table|bed|shelf|tent|tomb|grave|statue|bridge|wall|brick|stair|arch|pillar|"
                           r"keystone|rune|henge|altar|throne|well|column|cobble|fountain|marker|sculpt|gem|anvil|forge|plaque|"
                           r"trough|bench|tablet|road|grindstone|pyre|harpysnest|nest|underwater|barnacle|steppingstone|seaweed|"
                           r"spine|bone|skull|ruin|post|gate|cage", re.I)
CLASS_RULES = [
    ("deadwood", re.compile(r"stump|fallen|log(?!o)|root|deadwood|driftwood|trunk", re.I)),
    ("mushroom", re.compile(r"mushroom|shroom|fungus|toadstool", re.I)),
    ("bush",     re.compile(r"bush|shrub|shurb|plant|fern|hedge|brush|sapling|grass|reed|cactus", re.I)),
    ("tree",     re.compile(r"tree|pine|oak|birch|aspen|palm|willow|elm|canopy|bamboo|cypress|redwood", re.I)),
    ("rock",     re.compile(r"rock|boulder|stone|cliff|crag|pebble|outcrop|monolith|stalag|mesa", re.I)),
]
# Textures de route / chemin (MTEX) : une couche dont le nom correspond est comptee comme route sur son masque alpha.
ROAD_TEX_RE = re.compile(r"road|path|cobble|brick|paved|street|trail", re.I)


def classify_model(name):
    """tree | bush | deadwood | mushroom | rock | None, d'apres le nom du fichier M2 (puis le dossier trees / rocks)."""
    n = name.replace("\\", "/").lower()
    base = n.rsplit("/", 1)[-1]
    if NOT_NATURE_RE.search(base):
        return None
    for cls, rx in CLASS_RULES:
        if rx.search(base):
            return cls
    if "/trees/" in n:
        return "tree"
    if "/rocks/" in n or "/boulders/" in n or "/cliffrocks/" in n:
        return "rock"
    return None


# ---------------------------------------------------------------- lecture d'une ADT
def chunks(d, off=0, end=None):
    end = len(d) if end is None else end
    while off + 8 <= end:
        tag = d[off:off + 4][::-1].decode("latin-1")
        size = struct.unpack_from("<I", d, off + 4)[0]
        yield tag, off + 8, size
        off += 8 + size


def strings_with_offsets(blob):
    out, o = {}, 0
    for s in blob.split(b"\0"):
        out[o] = s.decode("latin-1")
        o += len(s) + 1
    return out


def parse_adt(d, A, B):
    top = {}
    for tag, o, size in chunks(d):
        if tag == "MCNK":
            top.setdefault("MCNK", []).append((o, size))
        else:
            top[tag] = (o, size)
    res = {}
    mmdx = strings_with_offsets(d[top["MMDX"][0]:top["MMDX"][0] + top["MMDX"][1]])
    mmid = struct.unpack_from("<%dI" % (top["MMID"][1] // 4), d, top["MMID"][0])
    mwmo = strings_with_offsets(d[top["MWMO"][0]:top["MWMO"][0] + top["MWMO"][1]])
    mwid = struct.unpack_from("<%dI" % (top["MWID"][1] // 4), d, top["MWID"][0])
    mtex = [s for s in d[top["MTEX"][0]:top["MTEX"][0] + top["MTEX"][1]].decode("latin-1").split("\0") if s]
    doodads = []
    o, size = top["MDDF"]
    for k in range(size // 36):
        nid, uid, p0, p1, p2, r0, r1, r2, scale, flags = struct.unpack_from("<II6fHH", d, o + 36 * k)
        doodads.append((uid, mmdx[mmid[nid]], MAX - p2, MAX - p0, p1, scale / 1024.0, r1))
    wmos = []
    o, size = top["MODF"]
    for k in range(size // 64):
        v = struct.unpack_from("<II3f3f3f3fHHHH", d, o + 64 * k)
        nid, uid = v[0], v[1]
        p, lo, hi = v[2:5], v[8:11], v[11:14]
        xs = sorted((MAX - lo[2], MAX - hi[2])); ys = sorted((MAX - lo[0], MAX - hi[0])); zs = sorted((lo[1], hi[1]))
        wmos.append((uid, mwmo[mwid[nid]], MAX - p[2], MAX - p[0], p[1], xs[0], xs[1], ys[0], ys[1], zs[0], zs[1]))
    v9 = np.zeros((129, 129), np.float32)
    v8 = np.zeros((128, 128), np.float32)
    holes = np.zeros((128, 128), bool)
    wl = np.full((128, 128), np.nan, np.float32)
    wt = np.zeros((128, 128), np.uint8)
    road = np.zeros((128, 128), np.uint8)
    road_tex = [bool(ROAD_TEX_RE.search(t.rsplit("\\", 1)[-1])) for t in mtex]
    chk = []                                      # controle : (r, c, posX, posY, X calcule, Y calcule)
    area = np.zeros((16, 16), np.uint32)
    for (o, size) in top["MCNK"]:
        h = struct.unpack_from("<32I", d, o)
        flags, ix, iy, nlay = h[0], h[1], h[2], h[3]
        ofs_h, ofs_lay, ofs_alpha, size_alpha = h[5], h[7], h[9], h[10]
        area[iy, ix] = h[13]
        holes_bits = h[15] & 0xFFFF
        ofs_liq, size_liq = h[24], h[25]
        posx, posy, posz = struct.unpack_from("<3f", d, o + 104)
        base = o - 8                              # les offsets du MCNK sont relatifs au debut du chunk (en-tete compris)
        r, c = iy, ix
        chk.append((r, c, posx, posy, (32 - B) * TS - r * CH, (32 - A) * TS - c * CH))
        mcvt = struct.unpack_from("<145f", d, base + ofs_h + 8)
        for i in range(9):
            v9[r * 8 + i, c * 8:c * 8 + 9] = np.array(mcvt[i * 17:i * 17 + 9], np.float32) + posz
        for i in range(8):
            v8[r * 8 + i, c * 8:c * 8 + 8] = np.array(mcvt[i * 17 + 9:i * 17 + 17], np.float32) + posz
        if holes_bits:
            for hb in range(16):
                if holes_bits & (1 << hb):
                    hr, hc = hb // 4, hb % 4
                    holes[r * 8 + hr * 2:r * 8 + hr * 2 + 2, c * 8 + hc * 2:c * 8 + hc * 2 + 2] = True
        # liquides MCLQ (1.12 : dans le MCNK, une instance par drapeau 0x04 riviere/lac, 0x08 ocean, 0x10 magma, 0x20 slime)
        kinds = [k for bit, k in ((0x04, 1), (0x08, 2), (0x10, 3), (0x20, 4)) if flags & bit]
        if kinds and ofs_liq:
            lo = base + ofs_liq + 8
            for kd in kinds:
                verts = [struct.unpack_from("<f", d, lo + 8 + 8 * q + 4)[0] for q in range(81)]
                tiles = d[lo + 8 + 648:lo + 8 + 648 + 64]
                for ti in range(8):
                    for tj in range(8):
                        if (tiles[ti * 8 + tj] & 0x0F) == 0x0F:
                            continue
                        lvl = (verts[ti * 9 + tj] + verts[ti * 9 + tj + 1] + verts[ti * 9 + tj + 9] + verts[ti * 9 + tj + 10]) / 4.0
                        R, C = r * 8 + ti, c * 8 + tj
                        if np.isnan(wl[R, C]) or kd != 2:
                            wl[R, C] = lvl
                            wt[R, C] = kd
                lo += 8 + 648 + 64 + 4 + 80
        # routes : couches MCLY dont la texture est une route ; alpha 4 bits 64x64 (2048 octets) par couche > 0
        if nlay > 1 and any(road_tex):
            lay = base + ofs_lay + 8
            for L in range(1, nlay):
                tex, lflags, aofs, _eff = struct.unpack_from("<4I", d, lay + 16 * L)
                if tex >= len(road_tex) or not road_tex[tex]:
                    continue
                a = np.frombuffer(d, np.uint8, 2048, base + ofs_alpha + 8 + aofs)
                al = np.empty(4096, np.uint8)
                al[0::2] = (a & 0x0F) * 17
                al[1::2] = (a >> 4) * 17
                al = al.reshape(64, 64)[:, :].reshape(8, 8, 8, 8).mean(axis=(1, 3)).astype(np.uint8)
                sub = road[r * 8:r * 8 + 8, c * 8:c * 8 + 8]
                np.maximum(sub, al, out=sub)
    res.update(doodads=doodads, wmos=wmos, v9=v9, v8=v8, holes=holes, wl=wl, wt=wt, road=road, chk=chk, area=area, mtex=mtex)
    return res


def tile_list(L, mapname):
    """Tuiles presentes d'apres le WDT (MAIN : 64x64 entrees de 8 octets, drapeau 1 = ADT presente)."""
    _an, wdt = L.read("World\\Maps\\%s\\%s.wdt" % (mapname, mapname))
    for tag, o, size in chunks(wdt):
        if tag == "MAIN":
            out = []
            for k in range(4096):
                if struct.unpack_from("<I", wdt, o + 8 * k)[0] & 1:
                    out.append((k % 64, k // 64))     # (A, B) : Map_A_B, entree MAIN[B][A]
            return out
    return []


# ---------------------------------------------------------------- pente
def slope_deg(v9):
    """Pente (degres) par case de 4,17 m : gradient de la grille 9x9 (moyenne des deux aretes de chaque direction)."""
    dx = ((v9[1:, :-1] - v9[:-1, :-1]) + (v9[1:, 1:] - v9[:-1, 1:])) / (2 * UNIT)
    dy = ((v9[:-1, 1:] - v9[:-1, :-1]) + (v9[1:, 1:] - v9[1:, :-1])) / (2 * UNIT)
    return np.degrees(np.arctan(np.hypot(dx, dy))).astype(np.float32)


# ---------------------------------------------------------------- programme
def scan_map(L, m, limit=None):
    mapname = MAPS[m]
    tiles = tile_list(L, mapname)
    if limit:
        tiles = tiles[:limit]
    t0 = time.time()
    trees, rocks, flora, wmos = {}, {}, {}, {}
    models = {}
    model_count = collections.Counter()
    grid = {"tiles": [], "v9": [], "v8": [], "holes": [], "wl": [], "wt": [], "road": [], "area": []}
    water_js, slope_js, bad_chk = [], [], 0
    road_names = set()
    for n, (A, B) in enumerate(tiles):
        name = "World\\Maps\\%s\\%s_%d_%d.adt" % (mapname, mapname, A, B)
        try:
            _an, d = L.read(name)
        except Exception as e:
            print("  ECHEC", name, e)
            continue
        t = parse_adt(d, A, B)
        for (r, c, px, py, cx, cy) in t["chk"]:
            if abs(px - cx) > 0.05 or abs(py - cy) > 0.05:
                bad_chk += 1
        for tx in t["mtex"]:
            if ROAD_TEX_RE.search(tx.rsplit("\\", 1)[-1]):
                road_names.add(tx)
        for (uid, mdl, x, y, z, sc, rot) in t["doodads"]:
            model_count[mdl.lower()] += 1
            k = classify_model(mdl)
            if not k:
                continue
            mid = models.setdefault(mdl.lower(), len(models))
            rec = [round(x, 2), round(y, 2), round(z, 2), round(sc, 3), mid]
            if k == "tree":
                trees[uid] = rec
            elif k == "rock":
                rocks[uid] = rec
            else:
                flora[uid] = rec + [k]
        for w in t["wmos"]:
            wmos[w[0]] = [w[1]] + [round(v, 1) for v in w[2:]]
        grid["tiles"].append((A, B))
        for k in ("v9", "v8", "holes", "wl", "wt", "road", "area"):
            grid[k].append(t[k])
        sl = slope_deg(t["v9"])
        for r in range(16):
            for c in range(16):
                X = (32 - B) * TS - (r + 0.5) * CH
                Y = (32 - A) * TS - (c + 0.5) * CH
                blk = t["wl"][r * 8:r * 8 + 8, c * 8:c * 8 + 8]
                ok = ~np.isnan(blk)
                if ok.any():
                    typ = int(np.bincount(t["wt"][r * 8:r * 8 + 8, c * 8:c * 8 + 8][ok]).argmax())
                    water_js.append([round(X, 1), round(Y, 1), round(float(np.nanmean(blk)), 2), typ, int(ok.sum())])
                s = sl[r * 8:r * 8 + 8, c * 8:c * 8 + 8]
                slope_js.append([round(X, 1), round(Y, 1), round(float(s.max()), 1), round(float((s > 35).mean()), 3),
                                 round(float(t["v9"][r * 8:r * 8 + 9, c * 8:c * 8 + 9].mean()), 1)])
        if n % 50 == 0:
            print("  %s %d/%d tuiles, %.0f s" % (mapname, n, len(tiles), time.time() - t0), flush=True)
    inv = {v: k for k, v in models.items()}
    mdl_tab = [inv[i] for i in range(len(inv))]
    for kind, dct in (("trees", trees), ("rocks", rocks)):
        json.dump({"map": m, "fields": ["x", "y", "z", "scale", "model"], "models": mdl_tab, "items": list(dct.values())},
                  open(os.path.join(OUT, "%d_%s.json" % (m, kind)), "w"))
    json.dump({"map": m, "fields": ["x", "y", "z", "scale", "model", "class"], "models": mdl_tab, "items": list(flora.values())},
              open(os.path.join(OUT, "%d_flora.json" % m), "w"))
    json.dump({"map": m, "fields": ["name", "x", "y", "z", "xmin", "xmax", "ymin", "ymax", "zmin", "zmax"], "items": list(wmos.values())},
              open(os.path.join(OUT, "%d_wmos.json" % m), "w"))
    json.dump({"map": m, "fields": ["x", "y", "level", "type(1 riviere/lac,2 ocean,3 magma,4 slime)", "cases"], "items": water_js},
              open(os.path.join(OUT, "%d_water.json" % m), "w"))
    json.dump({"map": m, "fields": ["x", "y", "pente_max_deg", "part_cases_sup_35deg", "hauteur_moy"], "items": slope_js},
              open(os.path.join(OUT, "%d_slopes.json" % m), "w"))
    np.savez_compressed(os.path.join(OUT, "%d_grid.npz" % m), tiles=np.array(grid["tiles"], np.int16),
                        **{k: np.stack(grid[k]) for k in ("v9", "v8", "holes", "wl", "wt", "road", "area")})
    # inventaire des modeles (pour documenter/ajuster la classification)
    with open(os.path.join(OUT, "%d_models.tsv" % m), "w", encoding="utf8") as f:
        for mdl, cnt in model_count.most_common():
            f.write("%d\t%s\t%s\n" % (cnt, classify_model(mdl) or "-", mdl))
    with open(os.path.join(OUT, "%d_road_textures.txt" % m), "w") as f:
        f.write("\n".join(sorted(road_names)))
    print("%s : %d tuiles, %d arbres, %d rochers, %d buissons/souches/champignons, %d WMO, %d chunks d'eau, controle position MCNK : %d ecarts, %.0f s"
          % (mapname, len(grid["tiles"]), len(trees), len(rocks), len(flora), len(wmos), len(water_js), bad_chk, time.time() - t0))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf8")
    os.makedirs(OUT, exist_ok=True)
    args = sys.argv[1:]
    maps = [0, 1]
    limit = None
    if "--maps" in args:
        maps = [int(v) for v in args[args.index("--maps") + 1].split(",")]
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    if "--verify" in args:
        import terrain_verify
        terrain_verify.main()
        sys.exit(0)
    L = mpq_layers.Layers(DATA_DIR)
    for m in maps:
        scan_map(L, m, limit)
