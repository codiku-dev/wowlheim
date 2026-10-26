"""Desassemble une plage de VA de WoW.exe (lecture seule). usage: disasm_range.py <exe> <va_start_hex> <nbytes_hex>
Annote les adresses .data pointant vers des chaines ASCII."""
import sys, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
exe,vs,n=sys.argv[1],int(sys.argv[2],16),int(sys.argv[3],16)
data=open(exe,"rb").read()
pe=struct.unpack_from("<I",data,0x3c)[0]; nsec=struct.unpack_from("<H",data,pe+6)[0]
optsz=struct.unpack_from("<H",data,pe+20)[0]; base=struct.unpack_from("<I",data,pe+24+28)[0]
secs=[]
for i in range(nsec):
    o=pe+24+optsz+i*40
    nm=data[o:o+8].rstrip(b"\0").decode(); a,v,rs,ro=struct.unpack_from("<IIII",data,o+8); secs.append((nm,v,a,ro,rs))
def va2off(va):
    for nm,v,a,ro,rs in secs:
        if base+v<=va<base+v+max(a,rs): return ro+va-base-v
def cstr(va):
    o=va2off(va)
    if o is None: return None
    e=data.find(b"\0",o,o+120); s=data[o:e]
    if len(s)>=3 and all(32<=c<127 for c in s): return s.decode()
md=Cs(CS_ARCH_X86,CS_MODE_32)
o=va2off(vs)
import re
for ins in md.disasm(data[o:o+n],vs):
    note=""
    for m in re.finditer(r"0x([0-9a-f]{6,8})",ins.op_str):
        s=cstr(int(m.group(1),16))
        if s: note=f"   ; \"{s}\""
    print(f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}{note}")
