r"""Ecriture des formats du client WoW 1.12.1 (build 5875) : M2 version 256 (modeles), BLP2 (textures), DBC.

Le format M2 vanilla a ete verifie en relisant des modeles du client legitime (GrainCrate01.m2, Axe_1H_Hatchet_A_01.m2) :
en-tete de 324 octets, tableaux alignes sur 16, sequence 68 o, os 108 o (pistes M2Track de 28 o avec plages
d'interpolation), sommet 48 o, vue embarquee 44 o (4 vues), sous-maillage 32 o, lot de texture 24 o.
Les fichiers produits sont des artefacts locaux (assets Valheim, usage prive non distribue)."""
import struct, math
import numpy as np
from PIL import Image

# ---------------------------------------------------------------- BLP2 (palette 256 couleurs + alpha 8 bits, mipmaps)

def _pow2(n):
    p = 1
    while p < n: p *= 2
    return p

def write_blp(path, img, max_size=512, alpha=None):
    """alpha : None = auto (pixels < 250), False = opaque (canal alpha ignore), True = alpha 8 bits."""
    img = img.convert("RGBA")
    w, h = img.size
    w2, h2 = min(_pow2(w), max_size), min(_pow2(h), max_size)
    if (w2, h2) != (w, h):
        img = img.resize((w2, h2), Image.LANCZOS)
    w, h = img.size
    a = np.array(img)
    has_alpha = bool((a[:, :, 3] < 250).any()) if alpha is None else bool(alpha)
    # Toujours un plan alpha 8 bits : en jeu, le client 1.12 affiche des blocs colores (lu comme du DXT) pour une
    # texture palette sans alpha (alphaDepth 0) ; une texture opaque recoit donc un alpha a 255 (constate le 2026-10-26).
    if not has_alpha:
        a = a.copy(); a[:, :, 3] = 255
        img = Image.fromarray(a)
    has_alpha = True
    rgb = Image.fromarray(a[:, :, :3])
    pal_img = rgb.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.NONE)
    pal = pal_img.getpalette()[:768]
    pal += [0] * (768 - len(pal))
    mips = []
    lw, lh = w, h
    level = img
    while True:
        la = np.array(level)
        idx = Image.fromarray(la[:, :, :3]).quantize(palette=pal_img, dither=Image.NONE)
        data = bytes(np.array(idx, dtype=np.uint8).tobytes())
        if has_alpha:
            data += la[:, :, 3].astype(np.uint8).tobytes()
        mips.append(data)
        if lw == 1 and lh == 1 or len(mips) == 16: break
        lw, lh = max(1, lw // 2), max(1, lh // 2)
        level = img.resize((lw, lh), Image.LANCZOS)
    header_size = 4 + 4 + 4 + 4 + 8 + 64 + 64 + 1024
    offs, sizes, pos = [], [], header_size
    for m in mips:
        offs.append(pos); sizes.append(len(m)); pos += len(m)
    offs += [0] * (16 - len(offs)); sizes += [0] * (16 - len(sizes))
    out = bytearray(b"BLP2")
    out += struct.pack("<I", 1)                                   # type 1 = BLP2 "directx"
    out += struct.pack("<BBBB", 1, 8 if has_alpha else 0, 8 if has_alpha else 0, 1)  # palette, alphaDepth, alphaType, mips
    out += struct.pack("<II", w, h)
    out += struct.pack("<16I", *offs) + struct.pack("<16I", *sizes)
    for i in range(256):
        r, g, b = pal[3 * i:3 * i + 3]
        out += struct.pack("<BBBB", b, g, r, 0)
    for m in mips: out += m
    open(path, "wb").write(out)
    return w, h, has_alpha

# ---------------------------------------------------------------- DBC

class DBC:
    def __init__(self, path):
        d = open(path, "rb").read()
        magic, self.n, self.fc, self.rs, ss = struct.unpack_from("<4sIIII", d, 0)
        assert magic == b"WDBC"
        self.rows = [bytearray(d[20 + i * self.rs:20 + (i + 1) * self.rs]) for i in range(self.n)]
        self.strings = bytearray(d[20 + self.n * self.rs:])
    def get(self, row, f, fmt="I"):
        return struct.unpack_from("<" + fmt, row, 4 * f)[0]
    def set(self, row, f, v, fmt="I"):
        struct.pack_into("<" + fmt, row, 4 * f, v)
    def str(self, row, f):
        o = self.get(row, f); e = self.strings.index(b"\0", o)
        return self.strings[o:e].decode("latin-1")
    def add_string(self, s):
        if not s: return 0
        o = len(self.strings); self.strings += s.encode("latin-1") + b"\0"; return o
    def find(self, id_):
        for r in self.rows:
            if self.get(r, 0) == id_: return r
        return None
    def upsert(self, row):
        id_ = self.get(row, 0)
        for i, r in enumerate(self.rows):
            if self.get(r, 0) == id_:
                self.rows[i] = row; return
        self.rows.append(row)
    def save(self, path):
        self.rows.sort(key=lambda r: self.get(r, 0))
        out = struct.pack("<4sIIII", b"WDBC", len(self.rows), self.fc, self.rs, len(self.strings))
        open(path, "wb").write(out + b"".join(bytes(r) for r in self.rows) + bytes(self.strings))

# ---------------------------------------------------------------- M2 v256

HDR_ARRAYS = ['globalSeq', 'sequences', 'seqLookup', 'playAnimLookup', 'bones', 'keyBoneLookup', 'vertices', 'views',
              'colors', 'textures', 'transparency', 'texFlipbooks', 'uvAnim', 'texReplace', 'renderFlags', 'boneLookup',
              'texLookup', 'texUnitLookup', 'transLookup', 'uvAnimLookup']
TAIL_ARRAYS = ['collIndices', 'collVerts', 'collNormals', 'attachments', 'attachLookup', 'events', 'lights', 'cameras',
               'cameraLookup', 'ribbons', 'particles']
N_PLAYABLE = 203   # taille de la table dans les modeles 1.12.1 relus
# drapeaux de la table des animations jouables, copies d'un modele d'origine (GrainCrate01.m2) : 1 = jouer a l'envers, 3 = figer
PAL_FLAGS = [0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 1, 0, 3, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 1, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 1, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
# os maximum par vue (LOD), comme les modeles d'origine : le client choisit la vue selon les capacites de la carte graphique ;
# avec 256 partout, aucune vue n'est retenue et le modele reste invisible (constate en jeu le 2026-10-26)
VIEW_BONES = (256, 75, 53, 21)

class _Buf:
    def __init__(self): self.b = bytearray(b"\0" * 336)
    def align(self):
        while len(self.b) % 16: self.b += b"\0"
    def put(self, data):
        self.align(); off = len(self.b); self.b += data; return off

def _track(buf, ranges, times, values, vfmt, interp=1):
    """M2Track vanilla (28 o) : interp, globalSeq, plages, timestamps, valeurs -> octets de l'en-tete de piste."""
    if not times:
        return struct.pack("<Hh6I", 0, -1, 0, 0, 0, 0, 0, 0)
    if not ranges:   # piste globale, sans plages (comme la transparence des modeles d'origine)
        to = buf.put(struct.pack("<%dI" % len(times), *times))
        vo = buf.put(b"".join(struct.pack("<" + vfmt, *v) for v in values))
        return struct.pack("<Hh6I", interp, -1, 0, 0, len(times), to, len(values), vo)
    ro = buf.put(b"".join(struct.pack("<II", a, b) for a, b in ranges))
    to = buf.put(struct.pack("<%dI" % len(times), *times))
    vo = buf.put(b"".join(struct.pack("<" + vfmt, *v) for v in values))
    return struct.pack("<Hh6I", interp, -1, len(ranges), ro, len(times), to, len(values), vo)

def quat_axis(axis, ang):
    s = math.sin(ang / 2); x, y, z = axis
    return (x * s, y * s, z * s, math.cos(ang / 2))

def write_m2(path, name, groups, textures, sequences=None, bone_rot=None, collision=None, tex_types=None,
             render_flags=None, scale=1.0, bone_scale=None):
    """groups : liste de dict pos(N,3) nrm(N,3) uv(N,2) tris(M,3) tex(int index) ;
    textures : liste de chemins BLP (\\) ; sequences : [(anim_id, start, end, flags)] (defaut : Stand 0..3333) ;
    bone_rot : (ranges, times, quats) pour l'os racine ; collision : (verts(N,3), tris(M,3)) ou None ;
    render_flags : par texture (flags, blend) ; tex_types : type M2Texture par texture (0 = fichier, 2 = arme/objet)."""
    if sequences is None: sequences = [(0, 0, 3333, 0)]
    buf = _Buf()
    pos = np.vstack([g['pos'] for g in groups]) * scale
    nrm = np.vstack([g['nrm'] for g in groups])
    uv = np.vstack([g['uv'] for g in groups])
    nv = len(pos)
    assert nv < 65536, "trop de sommets pour un M2 vanilla (%d)" % nv
    lo, hi = pos.min(0), pos.max(0)
    radius = float(np.linalg.norm(np.maximum(abs(lo), abs(hi))))
    bbox = struct.pack("<6ff", *lo, *hi, radius)

    off = {}; cnt = {}
    nm = name.encode() + b"\0"
    off['name'] = buf.put(nm)
    # sequences
    seqs = b""
    for i, (aid, s, e, fl) in enumerate(sequences):
        seqs += struct.pack("<HHIIfIhHIII", aid, 0, s, e, 0.0, fl, 0x7fff, 0, 0, 0, 150) + bbox + struct.pack("<hH", -1, i)
    off['sequences'] = buf.put(seqs); cnt['sequences'] = len(sequences)
    maxid = max(a for a, *_ in sequences)
    lookup = [-1] * (maxid + 1)
    for i, (aid, *_r) in enumerate(sequences): lookup[aid] = i
    off['seqLookup'] = buf.put(struct.pack("<%dh" % len(lookup), *lookup)); cnt['seqLookup'] = len(lookup)
    have = {a for a, *_ in sequences}
    pal = []
    for a in range(N_PLAYABLE):
        pal.append((a, 0) if a in have else (0, PAL_FLAGS[a]))
    off['playAnimLookup'] = buf.put(b"".join(struct.pack("<hh", *p) for p in pal)); cnt['playAnimLookup'] = N_PLAYABLE
    # os unique (racine) avec piste de rotation optionnelle
    if bone_rot:
        rot = _track(buf, bone_rot[0], bone_rot[1], bone_rot[2], "4f")
    else:
        rot = _track(buf, [], [], [], "4f")
    empty = _track(buf, [], [], [], "3f")
    scl = _track(buf, bone_scale[0], bone_scale[1], bone_scale[2], "3f") if bone_scale else empty
    bone = struct.pack("<iIhH", -1, 0, -1, 0) + empty + rot + scl + struct.pack("<3f", 0, 0, 0)
    assert len(bone) == 108
    off['bones'] = buf.put(bone); cnt['bones'] = 1
    off['keyBoneLookup'] = buf.put(struct.pack("<h", -1)); cnt['keyBoneLookup'] = 1
    vb = bytearray()
    for i in range(nv):
        vb += struct.pack("<3f4B4B3f2f2f", *pos[i], 255, 0, 0, 0, 0, 0, 0, 0, *nrm[i], *uv[i], 0.0, 0.0)
    off['vertices'] = buf.put(bytes(vb)); cnt['vertices'] = nv
    # vues (4 copies identiques, comme dans les modeles d'origine)
    view_hdr_off = buf.put(b"\0" * 44 * 4); cnt['views'] = 4; off['views'] = view_hdr_off
    for v in range(4):
        vidx = buf.put(struct.pack("<%dH" % nv, *range(nv)))
        tri_all = []; subs = []; batches = []
        vstart = 0; istart = 0
        for gi, g in enumerate(groups):
            t = (np.asarray(g['tris'], int) + vstart).reshape(-1)
            tri_all.append(t)
            c = pos[vstart:vstart + len(g['pos'])].mean(0)
            assert istart + len(t) < 65536, "trop d'indices"
            subs.append(struct.pack("<10H3f", 0, 0, vstart, len(g['pos']), istart, len(t), 1, 0, 1, 0, *c))
            ti = g['tex']
            batches.append(struct.pack("<BbHHHHHHHHHHH", 16, 0, 0, gi, gi, 0xFFFF, ti, 0, 1, ti, 0, 0, 0))
            vstart += len(g['pos']); istart += len(t)
        idx = np.concatenate(tri_all)
        iofs = buf.put(struct.pack("<%dH" % len(idx), *idx))
        bofs = buf.put(b"\0" * 4 * nv)
        sofs = buf.put(b"".join(subs))
        btofs = buf.put(b"".join(batches))
        struct.pack_into("<10II", buf.b, view_hdr_off + 44 * v, nv, vidx, len(idx), iofs, nv, bofs, len(subs), sofs,
                         len(batches), btofs, VIEW_BONES[v])
    # textures
    tb = b""; names = []
    for i, t in enumerate(textures):
        names.append(buf.put((t + "\0").encode("latin-1")) if t else buf.put(b"\0"))
    for i, t in enumerate(textures):
        tt = (tex_types or [0] * len(textures))[i]
        tb += struct.pack("<IIII", tt, 0, len(t) + 1 if t else 1, names[i])
    off['textures'] = buf.put(tb); cnt['textures'] = len(textures)
    # transparence : une piste alpha constante 1.0 (0x7fff)
    # transparence : une valeur 1.0 (0x7fff), sans plage d'interpolation, comme dans les M2 d'origine du client
    trans = _track(buf, [], [0], [(0x7fff,)], "h", interp=0)
    off['transparency'] = buf.put(trans); cnt['transparency'] = 1
    types = tex_types or [0] * len(textures)
    rep = [-1] * (max(types) + 1)
    for i, tt in enumerate(types):
        if rep[tt] == -1: rep[tt] = i
    off['texReplace'] = buf.put(struct.pack("<%dh" % len(rep), *rep)); cnt['texReplace'] = len(rep)
    rf = render_flags or [(0, 0)] * len(textures)
    # un materiau par texture (index du lot = index de texture)
    off['renderFlags'] = buf.put(b"".join(struct.pack("<HH", *f) for f in rf)); cnt['renderFlags'] = len(rf)
    off['boneLookup'] = buf.put(struct.pack("<4h", 0, 0, 0, 0)); cnt['boneLookup'] = 4
    off['texLookup'] = buf.put(struct.pack("<%dh" % len(textures), *range(len(textures)))); cnt['texLookup'] = len(textures)
    off['texUnitLookup'] = buf.put(struct.pack("<h", 0)); cnt['texUnitLookup'] = 1
    off['transLookup'] = buf.put(struct.pack("<h", 0)); cnt['transLookup'] = 1
    off['uvAnimLookup'] = buf.put(struct.pack("<h", -1)); cnt['uvAnimLookup'] = 1
    cbox = struct.pack("<6ff", *lo, *hi, radius)
    if collision is not None:
        cv, ct = collision
        cv = np.asarray(cv, float) * scale; ct = np.asarray(ct, int)
        off['collIndices'] = buf.put(struct.pack("<%dH" % ct.size, *ct.reshape(-1))); cnt['collIndices'] = ct.size
        off['collVerts'] = buf.put(b"".join(struct.pack("<3f", *p) for p in cv)); cnt['collVerts'] = len(cv)
        nn = []
        for a, b, c in ct:
            n = np.cross(cv[b] - cv[a], cv[c] - cv[a]); l = np.linalg.norm(n)
            nn.append(n / l if l > 0 else np.array([0, 0, 1.0]))
        off['collNormals'] = buf.put(b"".join(struct.pack("<3f", *n) for n in nn)); cnt['collNormals'] = len(nn)
        clo, chi = cv.min(0), cv.max(0)
        cbox = struct.pack("<6ff", *clo, *chi, float(np.linalg.norm(np.maximum(abs(clo), abs(chi)))))
    buf.align()
    # en-tete
    h = bytearray(b"MD20" + struct.pack("<I", 256))
    h += struct.pack("<II", len(nm), off['name']) + struct.pack("<I", 0)
    for k in HDR_ARRAYS:
        h += struct.pack("<II", cnt.get(k, 0), off.get(k, 0) if cnt.get(k, 0) else 0)
    h += bbox + cbox
    for k in TAIL_ARRAYS:
        h += struct.pack("<II", cnt.get(k, 0), off.get(k, 0) if cnt.get(k, 0) else 0)
    assert len(h) == 324, len(h)
    buf.b[0:324] = h
    open(path, "wb").write(bytes(buf.b))
    return {'verts': nv, 'tris': sum(len(g['tris']) for g in groups), 'bbox': (lo.tolist(), hi.tolist())}

def read_blp(path):
    """Lecteur BLP2 palette (alpha 0/1/8 bits en plan separe, comme WoW) -> image RGBA du niveau 0."""
    d = open(path, "rb").read()
    assert d[:4] == b"BLP2"
    comp, adepth, atype, mips = struct.unpack_from("<BBBB", d, 8)
    w, h = struct.unpack_from("<II", d, 12)
    off = struct.unpack_from("<16I", d, 20)[0]
    if comp != 1:
        return Image.open(path).convert("RGBA")
    pal = np.frombuffer(d, np.uint8, 1024, 148).reshape(256, 4)
    idx = np.frombuffer(d, np.uint8, w * h, off)
    rgba = np.zeros((w * h, 4), np.uint8)
    rgba[:, 0] = pal[idx, 2]; rgba[:, 1] = pal[idx, 1]; rgba[:, 2] = pal[idx, 0]; rgba[:, 3] = 255
    if adepth == 8:
        rgba[:, 3] = np.frombuffer(d, np.uint8, w * h, off + w * h)
    elif adepth == 1:
        bits = np.unpackbits(np.frombuffer(d, np.uint8, (w * h + 7) // 8, off + w * h), bitorder="little")[:w * h]
        rgba[:, 3] = bits * 255
    return Image.fromarray(rgba.reshape(h, w, 4))
