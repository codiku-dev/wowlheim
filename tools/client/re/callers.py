"""Cherche les CALL/JMP rel32 vers une VA dans .text de WoW.exe. usage: callers.py <va_hex>..."""
import sys, struct, pe
txt = pe.d[pe.text[3]:pe.text[3] + pe.text[2]]
for a in sys.argv[1:]:
    t = int(a, 16); res = []
    i = 0
    while True:
        i = txt.find(b"\xe8", i)
        if i < 0: break
        va = pe.text[1] + i
        rel = struct.unpack_from("<i", txt, i + 1)[0] if i + 5 <= len(txt) else 0
        if (va + 5 + rel) & 0xffffffff == t: res.append(("call", hex(va)))
        i += 1
    print(a, res)
