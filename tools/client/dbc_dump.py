"""Lecture d'un DBC WDBC (1.12) : en-tete, heuristique de typage des colonnes, apercu des enregistrements.
usage: dbc_dump.py <fichier.dbc> [nb_records=8]
Heuristique (le DBC n'embarque PAS son schema) : colonne 'chaine' si toutes les valeurs non nulles sont des
offsets valides dans le bloc de chaines pointant sur une chaine ASCII lisible ; 'float' si bits plausibles ; sinon 'int'."""
import sys, struct, collections
p = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
d = open(p, "rb").read()
magic, rc, fc, rs, ss = struct.unpack_from("<4sIIII", d, 0)
assert magic == b"WDBC", magic
print(f"magic={magic.decode()} records={rc} fields={fc} record_size={rs} string_block={ss} (taille fichier {len(d)} = 20+{rc*rs}+{ss}: {20+rc*rs+ss==len(d)})")
recs = [struct.unpack_from("<%dI" % fc, d, 20 + i * rs) for i in range(rc)]
sb = d[20 + rc * rs:]
def s_at(o):
    e = sb.find(b"\0", o); return sb[o:e].decode("latin-1")
def is_str(col):
    nz = [r[col] for r in recs if r[col]]
    if not nz: return False
    for o in nz:
        if o >= len(sb): return False
        t = sb[o:sb.find(b"\0", o)]
        if not t or any(c < 32 or c > 126 for c in t) or (o > 0 and sb[o-1] != 0): return False
    return True
def is_float(col):
    nz = [r[col] for r in recs if r[col]]
    if not nz: return False
    ok = 0
    for v in nz:
        f = struct.unpack("<f", struct.pack("<I", v))[0]
        if f == f and 1e-6 < abs(f) < 1e7: ok += 1
    return ok == len(nz) and any(v > 0xFFFF for v in nz)
types = []
for c in range(fc):
    types.append("str" if is_str(c) else "float" if is_float(c) else "int")
print("colonnes (devine):", " ".join(f"{i}:{t}" for i, t in enumerate(types)))
for r in recs[:n]:
    out = []
    for c, v in enumerate(r):
        if types[c] == "str": out.append(repr(s_at(v)) if v else "''")
        elif types[c] == "float": out.append("%.3f" % struct.unpack("<f", struct.pack("<I", v))[0])
        else: out.append(str(v))
    print("  ", out)
strs = [s_at(r[c]) for r in recs for c in range(fc) if types[c] == "str" and r[c]]
ext = collections.Counter(x.rsplit(".", 1)[-1].lower() if "." in x else "(sans ext)" for x in strs)
print("extensions des chaines:", dict(ext))
ids = [r[0] for r in recs]
print(f"IDs: min={min(ids)} max={max(ids)} (ids uniques={len(set(ids))})")
