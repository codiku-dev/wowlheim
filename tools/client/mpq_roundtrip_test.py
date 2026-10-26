"""Test d'aller-retour : construit un patch-Z.mpq de test (DBC modifie) avec mpq_write, puis le relit avec mpyq
(lecteur independant) et compare octet par octet. N'ecrit QUE dans tools/client/extracted/out/.
usage: mpq_roundtrip_test.py"""
import os, sys, subprocess, struct, hashlib
import mpyq
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from mpq_write import write_mpq
ex = os.path.join(here, "extracted"); out = os.path.join(ex, "out"); os.makedirs(out, exist_ok=True)
base = os.path.join(ex, "DBFilesClient", "GameObjectDisplayInfo.dbc")
new = os.path.join(out, "GameObjectDisplayInfo.dbc")
subprocess.check_call([sys.executable, "-I", os.path.join(here, "dbc_append.py"), base, new, "7000",
                       r"World\Generic\ActiveDoodads\Chest02\Chest02.mdx"])
payload = {r"DBFilesClient\GameObjectDisplayInfo.dbc": open(new, "rb").read(),
           r"Wowlheim\readme_test.txt": b"x" * 10000 + b"fin"}
ok = True
for compress in (True,):
    p = os.path.join(out, "patch-Z_%s.mpq" % ("zlib"))
    size = write_mpq(p, payload, compress=compress)
    a = mpyq.MPQArchive(p)
    print(p.split("extracted")[1], "taille", size, "header", {k: a.header[k] for k in ("header_size", "format_version", "hash_table_entries", "block_table_entries")})
    for name, data in payload.items():
        got = a.read_file(name)
        same = got == data
        ok &= same
        print("   ", name, "relu par mpyq:", "IDENTIQUE" if same else "DIFFERENT", len(data), "octets")
    print("    (listfile) =", a.read_file("(listfile)").decode().split())
    # insensibilite a la casse et a / vs \ (hash)
    ok &= a.read_file(r"dbfilesclient\gameobjectdisplayinfo.dbc") == payload[r"DBFilesClient\GameObjectDisplayInfo.dbc"]
print("RESULTAT:", "OK" if ok else "ECHEC")
sys.exit(0 if ok else 1)
