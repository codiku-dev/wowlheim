r"""Ajoute un enregistrement a GameObjectDisplayInfo.dbc (1.12 : 12 champs = ID, ModelName(chaine), Sound[10]).
usage: dbc_append.py <in.dbc> <out.dbc> <new_id> <model_name>"""
import sys, struct
src, dst, nid, model = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
d = open(src, "rb").read()
magic, rc, fc, rs, ss = struct.unpack_from("<4sIIII", d, 0)
assert magic == b"WDBC" and fc == 12 and rs == 48
recs = d[20:20 + rc * rs]; sb = d[20 + rc * rs:]
ids = {struct.unpack_from("<I", recs, i * rs)[0] for i in range(rc)}
assert nid not in ids, "ID deja present"
off = len(sb)
sb2 = sb + model.encode("latin-1") + b"\0"
newrec = struct.pack("<II10I", nid, off, *([0] * 10))
open(dst, "wb").write(struct.pack("<4sIIII", b"WDBC", rc + 1, fc, rs, len(sb2)) + recs + newrec + sb2)
print(f"OK {dst}: {rc}->{rc+1} enregistrements, bloc de chaines {ss}->{len(sb2)}")
