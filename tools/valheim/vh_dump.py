"""Dump des donnees de prefabs Valheim (MonoBehaviours avec typetree) -> JSON.
Usage: vh_dump.py out.json"""
import sys,json; import os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from vh_lib import *
from UnityPy.classes import PPtr
e=env()
cache={}
def pname(p):
    if p.m_PathID==0: return None
    key=(id(p.assetsfile) if hasattr(p,'assetsfile') else 0,p.m_FileID,p.m_PathID)
    try:
        r=p.deref()
        n=r.peek_name() if hasattr(r,'peek_name') else None
        if not n:
            ob=r.read(); n=getattr(ob,'m_Name',None)
            if not n and hasattr(ob,'m_GameObject'):
                n=ob.m_GameObject.deref().read().m_Name
        return {'ref':r.type.name,'name':n,'pid':p.m_PathID}
    except Exception as ex:
        return {'ref':'?','pid':p.m_PathID}
def conv(v,depth=0):
    if isinstance(v,PPtr): return pname(v)
    if isinstance(v,(int,float,str,bool)) or v is None: return v
    if isinstance(v,bytes): return '<bytes>'
    if isinstance(v,(list,tuple)): return [conv(x,depth+1) for x in v[:400]]
    if isinstance(v,dict): return {k:conv(x,depth+1) for k,x in v.items()}
    if depth>12: return str(v)[:80]
    d={}
    for k in getattr(v,'__dict__',{}):
        if k.startswith('_') or k in ('object_reader','assets_file'): continue
        d[k]=conv(getattr(v,k),depth+1)
    return d
def go_monos(go):
    res={}
    for c in go.m_Component:
        o=c.component.deref()
        if o.type.name!='MonoBehaviour': continue
        m=o.read()
        try: cls=m.m_Script.deref().read().m_ClassName
        except Exception: cls=None
        tt=o.read_typetree(); cls=cls or classify(tt)
        d=conv(m); d.pop('m_GameObject',None); d.pop('m_Script',None)
        res.setdefault(cls,[]).append(d)
    return res
name2path={}
for path in e.container:
    if path.endswith('.prefab'):
        name2path.setdefault(os.path.basename(path)[:-7],path)
def hit_areas(go):
    """Zones d'un MineRock5 : MineRock5.Awake cree une HitArea par Collider de GetComponentsInChildren<Collider>()
    (GameObjects actifs seulement ; les renderers « extra » enfants d'un collider ne comptent pas).
    Renvoie, par zone, la hauteur (Unity y, metres, racine du prefab a l'origine = niveau du sol ou Valheim pose le prefab)
    du point le plus haut de son maillage de collision : une zone dont le haut est <= 0 est enterree (atteignable seulement en creusant)."""
    import numpy as np
    from vh_mesh import trs, comp
    from UnityPy.helpers.MeshHelper import MeshHandler
    tops=[]
    def w(t,M,on):
        g=t.m_GameObject.read(); on=on and g.m_IsActive; Mw=M@trs(t)
        if on:
            for c in g.m_Component:
                o=c.component.deref()
                if 'Collider' not in o.type.name: continue
                col=o.read()
                if o.type.name=='MeshCollider' and col.m_Mesh.m_PathID: mesh=col.m_Mesh.read()
                else:
                    mf=comp(g,'MeshFilter'); mesh=mf.m_Mesh.read() if mf and mf.m_Mesh.m_PathID else None
                if mesh is None: tops.append(None); continue
                h=MeshHandler(mesh); h.process(); V=np.array(h.m_Vertices,float)[:,:3]
                tops.append(round(float((np.c_[V,np.ones(len(V))]@Mw.T)[:,1].max()),3))
        for ch in t.m_Children: w(ch.read(),Mw,on)
    tr=comp(go,'Transform')
    w(tr,np.linalg.inv(trs(tr)),True)
    return tops
def dump(name):
    p=name2path.get(name)
    if not p: return None
    go=e.container[p].read()
    out={'path':p,'monos':go_monos(go)}
    if 'MineRock5' in out['monos'] or 'MineRock' in out['monos']: out['hit_area_tops']=hit_areas(go); out['hit_areas']=len(out['hit_area_tops'])   # MineRock.Start : idem (m_areaRoot nul)
    return out
if __name__=='__main__':
    names=sys.argv[2:]
    out={n:dump(n) for n in names}
    json.dump(out,open(sys.argv[1],'w',encoding='utf-8'),indent=1,ensure_ascii=False,default=str)
