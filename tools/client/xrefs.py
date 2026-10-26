"""Cherche les references (imm32) a des VA dans WoW.exe et desassemble autour (capstone). Lecture seule.
usage: xrefs.py <WoW.exe> <va_hex> [<va_hex>...]  [--ctx N_instr_before,N_after]"""
import sys, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
exe=sys.argv[1]; vas=[int(x,16) for x in sys.argv[2:]]
data=open(exe,"rb").read()
pe=struct.unpack_from("<I",data,0x3c)[0]; nsec=struct.unpack_from("<H",data,pe+6)[0]
optsz=struct.unpack_from("<H",data,pe+20)[0]; base=struct.unpack_from("<I",data,pe+24+28)[0]
secs=[]
for i in range(nsec):
    o=pe+24+optsz+i*40
    n=data[o:o+8].rstrip(b"\0").decode(); vs,v,rs,ro=struct.unpack_from("<IIII",data,o+8); secs.append((n,v,vs,ro,rs))
def off2va(off):
    for n,v,vs,ro,rs in secs:
        if ro<=off<ro+rs: return base+v+off-ro
def va2off(va):
    for n,v,vs,ro,rs in secs:
        if base+v<=va<base+v+max(vs,rs): return ro+va-base-v
text=[s for s in secs if s[0]==".text"][0]
md=Cs(CS_ARCH_X86,CS_MODE_32)
for target in vas:
    pat=struct.pack("<I",target)
    i=text[3]
    end=text[3]+text[4]
    while True:
        i=data.find(pat,i,end)
        if i<0: break
        print(f"== xref to {target:#x} at va {off2va(i):#x}")
        start_va=off2va(i)-0x60
        so=va2off(start_va)
        # resync: disassemble from earlier and print the ones near the xref
        for ins in md.disasm(data[so:so+0x140], start_va):
            if abs(ins.address-off2va(i))<=0x50:
                print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
        i+=1
