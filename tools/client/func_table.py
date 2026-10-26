"""Verifie qu'un nom de fonction Lua est enregistre dans WoW.exe : cherche un dword pointant vers la chaine
suivi (dword suivant) d'un pointeur dans .text. usage: func_table.py <exe> <Nom> [<Nom>...]"""
import sys, struct, re
exe=sys.argv[1]; names=sys.argv[2:]
d=open(exe,"rb").read()
pe=struct.unpack_from("<I",d,0x3c)[0]; nsec=struct.unpack_from("<H",d,pe+6)[0]
optsz=struct.unpack_from("<H",d,pe+20)[0]; base=struct.unpack_from("<I",d,pe+24+28)[0]
secs=[]
for i in range(nsec):
    o=pe+24+optsz+i*40; n=d[o:o+8].rstrip(b"\0").decode(); vs,v,rs,ro=struct.unpack_from("<IIII",d,o+8); secs.append((n,v,vs,ro,rs))
def o2v(off):
    for n,v,vs,ro,rs in secs:
        if ro<=off<ro+rs: return base+v+off-ro
text=[s for s in secs if s[0]==".text"][0]; tlo=base+text[1]; thi=tlo+text[2]
for nm in names:
    pat=b"\0"+nm.encode()+b"\0"
    hits=[m.start()+1 for m in re.finditer(re.escape(pat),d)]
    if not hits: print(f"{nm}: chaine ABSENTE de WoW.exe"); continue
    for h in hits:
        sva=o2v(h)
        refs=[m.start() for m in re.finditer(re.escape(struct.pack("<I",sva)),d)]
        for r in refs:
            nxt=struct.unpack_from("<I",d,r+4)[0] if r+8<=len(d) else 0
            kind="TABLE(nom,fonction)" if tlo<=nxt<thi else "autre"
            print(f"{nm}: chaine va={sva:#x}; ref data off={r:#x} va={o2v(r):#x}; dword suivant={nxt:#x} -> {kind}")
        if not refs: print(f"{nm}: chaine va={sva:#x}; aucune reference directe (dword)")
