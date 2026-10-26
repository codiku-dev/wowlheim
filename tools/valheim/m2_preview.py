r"""Apercu logiciel d'un M2 v256 genere (relit le fichier : en-tete, vue 0, sommets, textures BLP) -> PNG.
Sert a verifier hors jeu la geometrie, l'orientation (Z en haut, X devant), les UV et les textures.
usage : m2_preview.py <racine_mpq> <sortie.png> <chemin\modele.m2> [...]"""
import sys, os, struct, math
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wowfmt

def load_m2(root, rel):
    d = open(os.path.join(root, *rel.split("\\")), "rb").read()
    assert d[:4] == b"MD20" and struct.unpack_from("<I", d, 4)[0] == 256
    arr = lambda i: struct.unpack_from("<II", d, 20 + 8 * i)
    nv, vo = arr(6)
    V = np.array([struct.unpack_from("<3f4B4B3f2f", d, vo + 48 * i) for i in range(nv)])
    P, N, UV = V[:, 0:3], V[:, 11:14], V[:, 14:16]
    _, vh = arr(7)
    vv = struct.unpack_from("<10II", d, vh)
    vl = np.array(struct.unpack_from("<%dH" % vv[0], d, vv[1]))
    idx = np.array(struct.unpack_from("<%dH" % vv[2], d, vv[3]))
    subs = [struct.unpack_from("<10H3f", d, vv[7] + 32 * s) for s in range(vv[6])]
    bats = [struct.unpack_from("<BbHHHHHHHHHHH", d, vv[9] + 24 * s) for s in range(vv[8])]
    nt, to = arr(9)
    texs = []
    for t in range(nt):
        ty, fl, ln, no = struct.unpack_from("<IIII", d, to + 16 * t)
        texs.append(d[no:no + ln - 1].decode("latin-1"))
    nlk, lko = arr(16)
    look = struct.unpack_from("<%dh" % nlk, d, lko)
    tris = []
    for b in bats:
        s = subs[b[3]]
        tex = texs[look[b[9]]]
        for i in range(s[4], s[4] + s[5], 3):
            tris.append((vl[idx[i]], vl[idx[i + 1]], vl[idx[i + 2]], tex))
    return P, N, UV, tris

def render(root, rel, size=360, yaw=35, pitch=20):
    P, N, UV, tris = load_m2(root, rel)
    img = Image.new("RGB", (size, size), (120, 150, 180))
    dr = ImageDraw.Draw(img)
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    # camera : regarde vers -X depuis +X tourne de yaw, Z en haut
    R1 = np.array([[cy, sy, 0], [-sy, cy, 0], [0, 0, 1]])
    Q = P @ R1.T
    depth = Q[:, 0] * cp + Q[:, 2] * sp
    sx, syy = -Q[:, 1], Q[:, 2] * cp - Q[:, 0] * sp
    lo = np.array([sx.min(), syy.min()]); hi = np.array([sx.max(), syy.max()])
    sc = (size - 20) / max(hi - lo)
    X = 10 + (sx - lo[0]) * sc; Y = size - 10 - (syy - lo[1]) * sc
    texcache = {}
    def texcol(t, u, v):
        if t not in texcache:
            p = os.path.join(root, *t.split("\\"))
            texcache[t] = np.array(wowfmt.read_blp(p)) if t and os.path.exists(p) else None
        a = texcache[t]
        if a is None: return (200, 0, 200)
        h, w = a.shape[:2]
        c = a[int((v % 1) * (h - 1)), int((u % 1) * (w - 1))]
        if c[3] < 100: return None
        return tuple(int(x) for x in c[:3])
    light = np.array([0.4, 0.3, 0.85]); light /= np.linalg.norm(light)
    order = sorted(tris, key=lambda t: -(depth[t[0]] + depth[t[1]] + depth[t[2]]))
    for a, b, c, t in order:
        fn = np.cross(P[b] - P[a], P[c] - P[a])
        # culling arriere : face visible si la normale (sens CCW) pointe vers la camera
        cam = np.array([cp, 0, sp]) @ R1
        if fn @ cam <= 0: continue
        uvc = (UV[a] + UV[b] + UV[c]) / 3
        col = texcol(t, uvc[0], uvc[1])
        if col is None: continue
        nn = fn / (np.linalg.norm(fn) + 1e-9)
        k = 0.45 + 0.55 * max(0, nn @ light)
        dr.polygon([(X[a], Y[a]), (X[b], Y[b]), (X[c], Y[c])], fill=tuple(int(x * k) for x in col))
    dr.text((4, 4), rel.split("\\")[-1], fill=(255, 255, 255))
    return img

if __name__ == "__main__":
    root, out, rels = sys.argv[1], sys.argv[2], sys.argv[3:]
    ims = [render(root, r) for r in rels]
    cols = min(4, len(ims)); rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (360 * cols, 360 * rows))
    for i, im in enumerate(ims): sheet.paste(im, (360 * (i % cols), 360 * (i // cols)))
    sheet.save(out)
