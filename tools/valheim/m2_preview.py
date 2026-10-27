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
    nrf, rfo = arr(14)
    rfl = [struct.unpack_from("<HH", d, rfo + 4 * i) for i in range(nrf)]
    tris = []
    for b in bats:
        s = subs[b[3]]
        tex = texs[look[b[9]]]
        flags, blend = rfl[b[6]] if b[6] < len(rfl) else (0, 0)
        for i in range(s[4], s[4] + s[5], 3):
            tris.append((vl[idx[i]], vl[idx[i + 1]], vl[idx[i + 2]], tex, flags, blend))
    return P, N, UV, tris

def render(root, rel, size=360, yaw=35, pitch=20, bg=(120, 150, 180)):
    """Rendu par pixel (tampon de profondeur, UV interpolees, eclairage diffus) avec les regles du client : texture
    absente -> magenta, blend 1 (alpha teste) -> texels alpha < 128 ecartes, drapeau 0x04 -> deux faces (sinon culling)."""
    P, N, UV, tris = load_m2(root, rel)
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    R1 = np.array([[cy, sy, 0], [-sy, cy, 0], [0, 0, 1]])
    Q = P @ R1.T
    depth = Q[:, 0] * cp + Q[:, 2] * sp
    sx, syy = -Q[:, 1], Q[:, 2] * cp - Q[:, 0] * sp
    lo = np.array([sx.min(), syy.min()]); hi = np.array([sx.max(), syy.max()])
    sc = (size - 20) / max(max(hi - lo), 1e-6)
    X = 10 + (sx - lo[0]) * sc; Y = size - 10 - (syy - lo[1]) * sc
    img = np.zeros((size, size, 3)); img[:] = bg
    zb = np.full((size, size), -np.inf)
    texcache = {}
    def tex(t):
        if t not in texcache:
            p = os.path.join(root, *t.split("\\")) if t else ""
            texcache[t] = np.array(wowfmt.read_blp(p)).astype(float) if t and os.path.exists(p) else None
        return texcache[t]
    light = np.array([0.4, 0.3, 0.85]); light /= np.linalg.norm(light)
    cam = np.array([cp, 0, sp]) @ R1
    for a, b, c, t, flags, blend in tris:
        fn = np.cross(P[b] - P[a], P[c] - P[a])
        nl = np.linalg.norm(fn)
        if nl == 0: continue
        facing = fn @ cam > 0
        if not facing and not (flags & 0x04): continue
        nn = fn / nl
        if not facing: nn = -nn
        k = 0.45 + 0.55 * max(0.0, nn @ light)
        xs, ys = np.array([X[a], X[b], X[c]]), np.array([Y[a], Y[b], Y[c]])
        x0, x1 = max(int(xs.min()), 0), min(int(xs.max()) + 1, size - 1)
        y0, y1 = max(int(ys.min()), 0), min(int(ys.max()) + 1, size - 1)
        if x1 < x0 or y1 < y0: continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(den) < 1e-9: continue
        w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / den
        w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / den
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not m.any(): continue
        z = w0 * depth[a] + w1 * depth[b] + w2 * depth[c]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        m &= z > sub
        if not m.any(): continue
        T = tex(t)
        if T is None:
            col = np.broadcast_to(np.array([200.0, 0, 200]), m.shape + (3,)); keep = m
        else:
            u = w0 * UV[a, 0] + w1 * UV[b, 0] + w2 * UV[c, 0]
            v = w0 * UV[a, 1] + w1 * UV[b, 1] + w2 * UV[c, 1]
            h, w = T.shape[:2]
            px = T[(np.mod(v, 1) * (h - 1)).astype(int), (np.mod(u, 1) * (w - 1)).astype(int)]
            col = px[..., :3]
            keep = m & ((px[..., 3] >= 128) if blend == 1 else True)
        sub[keep] = z[keep]
        img[y0:y1 + 1, x0:x1 + 1][keep] = col[keep] * k
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    ImageDraw.Draw(out).text((4, 4), rel.split("\\")[-1], fill=(255, 255, 255))
    return out

if __name__ == "__main__":
    root, out, rels = sys.argv[1], sys.argv[2], sys.argv[3:]
    ims = [render(root, r) for r in rels]
    cols = min(4, len(ims)); rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (360 * cols, 360 * rows))
    for i, im in enumerate(ims): sheet.paste(im, (360 * (i % cols), 360 * (i // cols)))
    sheet.save(out)
