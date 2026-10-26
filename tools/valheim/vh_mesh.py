"""Export d'un prefab Valheim -> geometrie (espace WoW) + textures.
export_prefab(name) -> {'groups':[{'pos','nrm','uv','tris','tex'}], 'textures':{texname: PIL.Image}}"""
import sys,math,os; import os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from vh_lib import env
from UnityPy.helpers.MeshHelper import MeshHandler

def trs(t):
    p=t.m_LocalPosition; q=t.m_LocalRotation; s=t.m_LocalScale
    x,y,z,w=q.x,q.y,q.z,q.w
    R=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
    M=np.eye(4); M[:3,:3]=R*np.array([s.x,s.y,s.z]); M[:3,3]=[p.x,p.y,p.z]
    return M

def comp(go,tname):
    for c in go.m_Component:
        o=c.component.deref()
        if o.type.name==tname: return o.read()
    return None

def walk(tr,M,out,skip):
    go=tr.m_GameObject.read()
    if go.m_Name in skip: return
    if not go.m_IsActive: return
    Mw=M@trs(tr)
    out.append((go,Mw))
    for ch in tr.m_Children:
        walk(ch.read(),Mw,out,skip)

SKIP={'Worn','Broken','WET','collider','collider (1)','viewblock','leaf_particles','UpgraderGlow','equiped','trail'}
def renderers_of(root_go,attach_only=False):
    """liste (go, matrice monde) des MeshRenderer a exporter (LOD0, etat neuf).
    attach_only : seulement le sous-arbre « attach » (modele tenu en main), dans son propre repere."""
    tr=comp(root_go,'Transform')
    if attach_only:
        for ch in tr.m_Children:
            c=ch.read()
            if c.m_GameObject.read().m_Name=='attach': tr=c; break
    allg=[]
    rootM=np.linalg.inv(trs(tr))  # racine exportee a l'origine
    walk(tr,rootM,allg,SKIP)
    # LODGroups : garder seulement les renderers du LOD0, exclure ceux des autres LOD
    excl=set(); lod0=set()
    for go,_ in allg:
        lg=comp(go,'LODGroup')
        if lg:
            for i,l in enumerate(lg.m_LODs):
                for r in l.renderers:
                    if r.renderer.m_PathID==0: continue
                    pid=r.renderer.m_PathID
                    (lod0 if i==0 else excl).add(pid)
    excl-=lod0
    res=[]
    for go,M in allg:
        for c in go.m_Component:
            o=c.component.deref()
            if o.type.name=='MeshRenderer':
                if c.component.m_PathID in excl: continue
                if not o.read().m_Enabled: continue
                res.append((go,M,o.read()))
    return res

def snap_points(name):
    """Points d'accroche Valheim (enfants « $hud_snappoint_* » / « _snappoint ») en coordonnees WoW du prefab."""
    e=env()
    cands=[p for p in e.container if p.endswith('/'+name+'.prefab')]
    cands.sort(key=lambda p:(0 if '/GameElements/' in p or '/world/' in p else 1,len(p)))
    go=e.container[cands[0]].read()
    tr=comp(go,'Transform')
    out=[]
    def w(t,M):
        g=t.m_GameObject.read()
        Mw=M@trs(t)
        if 'snappoint' in g.m_Name.lower():
            out.append((Mw[:3,3]@U2W.T).tolist())
        for ch in t.m_Children: w(ch.read(),Mw)
    w(tr,np.linalg.inv(trs(tr)))
    return out

def tex_of(mat):
    try:
        for k,v in mat.m_SavedProperties.m_TexEnvs:
            if k=='_MainTex' and v.m_Texture.m_PathID!=0:
                return v.m_Texture.deref().read()
    except Exception as ex:
        pass
    return None

U2W=np.array([[0,0,1],[-1,0,0],[0,1,0]],float)  # unity(x,y,z) -> wow(x fwd,y left,z up)

def export_prefab(name,path=None,attach_only=False):
    e=env()
    if path is None:
        cands=[p for p in e.container if p.endswith('/'+name+'.prefab')]
        cands.sort(key=lambda p:(0 if '/GameElements/' in p or '/world/' in p else 1,len(p)))
        path=cands[0]
    go=e.container[path].read()
    groups={}; textures={}
    for g,M,mr in renderers_of(go,attach_only):
        mf=comp(g,'MeshFilter')
        if not mf or mf.m_Mesh.m_PathID==0: continue
        mesh=mf.m_Mesh.read()
        h=MeshHandler(mesh); h.process()
        V=np.array(h.m_Vertices,float)[:,:3]
        N=np.array(h.m_Normals,float)[:,:3] if h.m_Normals else np.zeros_like(V)
        UV=np.array(h.m_UV0,float)[:,:2] if h.m_UV0 else np.zeros((len(V),2))
        Vh=np.c_[V,np.ones(len(V))]@M.T
        Vw=Vh[:,:3]@U2W.T
        Nw=(N@np.linalg.inv(M[:3,:3]))@U2W.T
        nn=np.linalg.norm(Nw,axis=1,keepdims=True); nn[nn==0]=1; Nw/=nn
        subs=h.get_triangles()
        mats=mr.m_Materials
        for si,tris in enumerate(subs):
            if not tris: continue
            mat=mats[min(si,len(mats)-1)].read() if mats else None
            tex=tex_of(mat) if mat else None
            tname=tex.m_Name if tex else '__white'
            if tex and tname not in textures:
                textures[tname]=tex.image
            T=np.array(tris,int)
            sm=mesh.m_SubMeshes[si]
            if getattr(sm,'baseVertex',0): T=T+sm.baseVertex
            used=np.unique(T)
            remap=-np.ones(len(V),int); remap[used]=np.arange(len(used))
            G=groups.setdefault(tname,{'pos':[],'nrm':[],'uv':[],'tris':[],'tex':tname,'mat':mat.m_Name if mat else None,'n':0})
            G['pos'].append(Vw[used]); G['nrm'].append(Nw[used]); G['uv'].append(UV[used])
            G['tris'].append(remap[T]+G['n']); G['n']+=len(used)
    out=[]
    for G in groups.values():
        out.append({'pos':np.vstack(G['pos']),'nrm':np.vstack(G['nrm']),'uv':np.vstack(G['uv']),
                    'tris':np.vstack(G['tris']),'tex':G['tex'],'mat':G['mat']})
    return {'groups':out,'textures':textures,'path':path}

def write_obj(res,fn):
    with open(fn,'w') as f:
        off=1
        for g in res['groups']:
            f.write(f"o {g['tex']}\n")
            for p in g['pos']: f.write("v %f %f %f\n"%tuple(p))
            for u in g['uv']: f.write("vt %f %f\n"%tuple(u))
            for t in g['tris']: f.write("f %d/%d %d/%d %d/%d\n"%(t[0]+off,t[0]+off,t[1]+off,t[1]+off,t[2]+off,t[2]+off))
            off+=len(g['pos'])

if __name__=='__main__':
    od=sys.argv[1]; os.makedirs(od,exist_ok=True)
    for n in sys.argv[2:]:
        r=export_prefab(n)
        tot=sum(len(g['tris']) for g in r['groups'])
        allp=np.vstack([g['pos'] for g in r['groups']])
        print(n,r['path'],'groups',[(g['tex'],len(g['pos']),len(g['tris'])) for g in r['groups']],'tris',tot,'bbox',allp.min(0).round(2),allp.max(0).round(2))
        write_obj(r,os.path.join(od,n+'.obj'))
        for tn,im in r['textures'].items(): print('  tex',tn,im.size,im.mode); im.save(os.path.join(od,tn+'.png'))
