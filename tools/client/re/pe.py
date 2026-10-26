"""Petit lecteur PE pour WoW.exe 1.12.1 (lecture seule). Utilise par les scripts re/*.py"""
import struct, re, sys, os
EXE = os.environ.get("WOW_EXE", r"C:\Wowlheim\tools\re_work\WoW.exe")
d = open(EXE, "rb").read()
pe = struct.unpack_from("<I", d, 0x3c)[0]
nsec = struct.unpack_from("<H", d, pe + 6)[0]
optsz = struct.unpack_from("<H", d, pe + 20)[0]
base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
secs = []
for i in range(nsec):
    o = pe + 24 + optsz + i * 40
    n = d[o:o+8].rstrip(b"\0").decode()
    vs, v, rs, ro = struct.unpack_from("<IIII", d, o + 8)
    secs.append((n, base + v, vs, ro, rs))
text = [s for s in secs if s[0] == ".text"][0]
def v2o(va):
    for n, v, vs, ro, rs in secs:
        if v <= va < v + max(vs, rs): return ro + va - v
def o2v(off):
    for n, v, vs, ro, rs in secs:
        if ro <= off < ro + rs: return v + off - ro
def u32(va): return struct.unpack_from("<I", d, v2o(va))[0]
def cstr(va, n=100):
    o = v2o(va)
    if o is None: return None
    e = d.find(b"\0", o, o + n); s = d[o:e]
    return s.decode("latin1") if s and all(32 <= c < 127 for c in s) else None
def istext(x): return text[1] <= x < text[1] + text[2]
def lua_func(name):
    """Retourne la liste des (va_entree_table, va_fonction) pour un nom de fonction Lua enregistre {nom, fn}."""
    out = []
    pat = b"\0" + name.encode() + b"\0"
    for m in re.finditer(re.escape(pat), d):
        sva = o2v(m.start() + 1)
        for r in re.finditer(re.escape(struct.pack("<I", sva)), d):
            nxt = struct.unpack_from("<I", d, r.start() + 4)[0]
            if istext(nxt): out.append((o2v(r.start()), nxt))
    return out
if __name__ == "__main__":
    for n in sys.argv[1:]:
        print(n, [(hex(a), hex(b)) for a, b in lua_func(n)])
