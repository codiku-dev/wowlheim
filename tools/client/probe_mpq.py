"""Sonde: ouvre chaque MPQ du client (lecture seule) avec mpyq et affiche header + (listfile)."""
import sys, glob, os
import mpyq
D = sys.argv[1]
for p in sorted(glob.glob(os.path.join(D, "*.MPQ")) + glob.glob(os.path.join(D, "*.mpq"))):
    try:
        a = mpyq.MPQArchive(p, listfile=True)
        h = a.header
        lf = a.files
        print(os.path.basename(p), "fmt", h.get("format_version"), "hash", h["hash_table_entries"], "block", h["block_table_entries"], "listfile", None if lf is None else len(lf))
    except Exception as e:
        print(os.path.basename(p), "ERR", repr(e))
