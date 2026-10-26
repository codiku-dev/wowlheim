"""Extrait les chaines ASCII (et UTF-16LE) de WoW.exe (lecture seule) correspondant a des motifs.
usage: exe_strings.py <WoW.exe> <regex> [...]"""
import sys, re, struct
data = open(sys.argv[1], "rb").read()
pats = [re.compile(p, re.I) for p in sys.argv[2:]]
# sections PE pour convertir offset -> VA
pe = struct.unpack_from("<I", data, 0x3c)[0]
nsec = struct.unpack_from("<H", data, pe+6)[0]
optsz = struct.unpack_from("<H", data, pe+20)[0]
base = struct.unpack_from("<I", data, pe+24+28)[0]
secs=[]
for i in range(nsec):
    o = pe+24+optsz+i*40
    name=data[o:o+8].rstrip(b"\0").decode(); vs,va,rs,ro = struct.unpack_from("<IIII", data, o+8)
    secs.append((name,va,vs,ro,rs))
def va(off):
    for n,v,vs,ro,rs in secs:
        if ro<=off<ro+rs: return base+v+off-ro, n
    return None, None
for m in re.finditer(rb"[\x20-\x7e]{4,}", data):
    s = m.group().decode()
    if any(p.search(s) for p in pats):
        a,n = va(m.start())
        print(f"off=0x{m.start():06x} va={a and hex(a)} sec={n} : {s}")
