"""Affiche l'en-tete brut (lecture seule) de chaque MPQ : taille d'en-tete, version de format, tailles de blocs, tables.
usage: mpq_headers.py <DataDir>"""
import sys, glob, os, struct
seen=set()
for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.[mM][pP][qQ]"))):
    if p.lower() in seen: continue
    seen.add(p.lower())
    with open(p, "rb") as f: h = f.read(0x2c)
    magic, hsz, asz, fmt, bs, hto, bto, hte, bte = struct.unpack_from("<4sIIHHIIII", h, 0)
    ext = ""
    if fmt >= 1 and hsz >= 0x2c:
        hi_bt, hi_ht, hi_bt2 = struct.unpack_from("<QHH", h, 0x20)[0:1] + struct.unpack_from("<HH", h, 0x28)
        ext = f" v2:hiBlockTablePos={struct.unpack_from('<Q', h, 0x20)[0]}"
    print(f"{os.path.basename(p):14s} magic={magic} header_size={hsz:#x} archive_size={asz} format={fmt} blocksize_shift={bs} "
          f"hash@{hto:#x}x{hte} block@{bto:#x}x{bte} file_size={os.path.getsize(p)}{ext}")
