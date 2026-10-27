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
def renderers_of(root_go,attach_only=False,skinned=False):
    """liste (go, matrice monde) des MeshRenderer a exporter (LOD0, etat neuf).
    attach_only : seulement le sous-arbre « attach » (modele tenu en main), dans son propre repere.
    skinned : accepte aussi les SkinnedMeshRenderer (maillage en pose de liaison ; stations animees de Valheim)."""
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
            if o.type.name=='MeshRenderer' or (skinned and o.type.name=='SkinnedMeshRenderer'):
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

def mat_color(mat):
    """Couleur _Color d'un materiau (Standard sans texture : barres de metal, vitre de cristal) -> image unie 8x8."""
    from PIL import Image
    c=(1,1,1,1)
    try:
        for k,v in mat.m_SavedProperties.m_Colors:
            if k=='_Color': c=(v.r,v.g,v.b,1.0)
    except Exception: pass
    return Image.new('RGBA',(8,8),tuple(int(max(0,min(1,x))*255) for x in c))

def mat_tint(mat):
    """Teinte _Color (RVB) d'un materiau texture, None si blanche (a 2 % pres)."""
    try:
        for k,v in mat.m_SavedProperties.m_Colors:
            if k=='_Color':
                c=tuple(max(0.0,min(1.0,x)) for x in (v.r,v.g,v.b))
                return None if min(c)>0.98 else c
    except Exception: pass
    return None

def mat_info(mat):
    """Ce qui decide de l'alpha teste dans Valheim : shader, _Mode (1 = Cutout), mot-cle _ALPHATEST_ON."""
    info={'shader':None,'mode':0.0,'keywords':[]}
    try:
        if mat.m_Shader.m_PathID: info['shader']=mat.m_Shader.read().m_ParsedForm.m_Name
    except Exception: pass
    try:
        for k,v in mat.m_SavedProperties.m_Floats:
            if k=='_Mode': info['mode']=float(v)
    except Exception: pass
    kw=getattr(mat,'m_ShaderKeywords',None) or getattr(mat,'m_ValidKeywords',None) or []
    info['keywords']=kw.split() if isinstance(kw,str) else list(kw)
    return info

# Placement de _MainTex selon le shader Valheim (releve des materiaux le 2026-10-26) :
#  - Standard / Custom/StaticRock (_TriplanarMap 0 partout) : UV0 * _MainTex_ST (tuilage + decalage, TRANSFORM_TEX).
#    Ignore avant : filon d'argent (x2.5), rocher (x2), rock4_* (x8), silex (x0.2) etiraient la texture.
#  - Custom/Piece : _MainTex_ST n'y sert PAS au placement (planches : -0.56 x 0.12, rendu juste sans) -> UV0 brutes.
#  - Custom/Trilinearmap (tas de boue) : projection triplanaire en espace objet, echelle _UVScale (UV0 sans rapport).
ST_SHADERS={'Standard','Standard (Specular setup)','Custom/StaticRock'}
TRIPLANAR_SHADERS={'Custom/Trilinearmap'}

def main_st(mat):
    """(sx, sy, ox, oy) de _MainTex, None si identite."""
    try:
        for k,v in mat.m_SavedProperties.m_TexEnvs:
            if k=='_MainTex':
                st=(v.m_Scale.x,v.m_Scale.y,v.m_Offset.x,v.m_Offset.y)
                return None if st==(1.0,1.0,0.0,0.0) else st
    except Exception: pass
    return None

def mat_float(mat,name,default=None):
    try:
        for k,v in mat.m_SavedProperties.m_Floats:
            if k==name: return float(v)
    except Exception: pass
    return default

def triplanar_uv(P,T,scale):
    """Projection « boite » par face : axe dominant de la normale de la face, UV = coordonnees des deux autres axes
    x scale. Sommets dedoubles par face (pas de couture etiree). -> (index des sommets d'origine (3M,), uv (3M,2), tris)."""
    A,B,C=P[T[:,0]],P[T[:,1]],P[T[:,2]]
    ax=np.abs(np.cross(B-A,C-A)).argmax(1)
    idx=T.reshape(-1)
    Q=P[idx]; axr=np.repeat(ax,3)
    other=np.array([[1,2],[0,2],[0,1]])[axr]
    uv=np.stack([Q[np.arange(len(Q)),other[:,0]],Q[np.arange(len(Q)),other[:,1]]],1)*scale
    return idx,uv,np.arange(len(idx)).reshape(-1,3)

def export_prefab(name,path=None,attach_only=False,skinned=False,flat_color=False):
    """skinned / flat_color : options (desactivees par defaut, les modeles existants ne changent pas) ;
    flat_color : un sous-maillage sans _MainTex recoit une texture unie de la couleur _Color du materiau."""
    e=env()
    if path is None:
        cands=[p for p in e.container if p.endswith('/'+name+'.prefab')]
        cands.sort(key=lambda p:(0 if '/GameElements/' in p or '/world/' in p else 1,len(p)))
        path=cands[0]
    go=e.container[path].read()
    groups={}; textures={}; matinfo={}
    for g,M,mr in renderers_of(go,attach_only,skinned):
        if skinned and hasattr(mr,'m_Bones'):
            if mr.m_Mesh.m_PathID==0: continue
            mesh=mr.m_Mesh.read()
        else:
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
            tint=mat_tint(mat) if (tex and mat is not None) else None
            if tint is not None:
                tname='%s_c%02x%02x%02x'%((tname,)+tuple(int(round(x*255)) for x in tint))
            if tex and tname not in textures:
                img=tex.image
                if tint is not None:
                    # Valheim multiplie _MainTex par _Color (etabli 0.62, ecorce de chene 0.69...) : on cuit la teinte
                    a=np.array(img.convert('RGBA')).astype(float); a[:,:,:3]*=np.array(tint)
                    from PIL import Image
                    img=Image.fromarray(np.clip(np.rint(a),0,255).astype(np.uint8))
                textures[tname]=img
                matinfo[tname]=mat_info(mat)
            if not tex and flat_color and mat is not None:
                tname='col_'+mat.m_Name
                if tname not in textures: textures[tname]=mat_color(mat)
            T=np.array(tris,int)
            sm=mesh.m_SubMeshes[si]
            if getattr(sm,'baseVertex',0): T=T+sm.baseVertex
            G=groups.setdefault(tname,{'pos':[],'nrm':[],'uv':[],'tris':[],'tex':tname,'mat':mat.m_Name if mat else None,'n':0})
            sh=matinfo.get(tname,{}).get('shader') if tex else None
            if sh in TRIPLANAR_SHADERS:
                Po=(np.c_[V,np.ones(len(V))]@M.T)[:,:3]          # espace objet du prefab (Unity, metres)
                idx,uvt,Tn=triplanar_uv(Po,T,mat_float(mat,'_UVScale',1.0))
                G['pos'].append(Vw[idx]); G['nrm'].append(Nw[idx]); G['uv'].append(uvt)
                G['tris'].append(Tn+G['n']); G['n']+=len(idx)
                continue
            used=np.unique(T)
            remap=-np.ones(len(V),int); remap[used]=np.arange(len(used))
            uvs=UV[used]
            st=main_st(mat) if (tex and sh in ST_SHADERS) else None
            if st: uvs=uvs*np.array(st[:2])+np.array(st[2:])
            G['pos'].append(Vw[used]); G['nrm'].append(Nw[used]); G['uv'].append(uvs)
            G['tris'].append(remap[T]+G['n']); G['n']+=len(used)
    out=[]
    for G in groups.values():
        out.append({'pos':np.vstack(G['pos']),'nrm':np.vstack(G['nrm']),'uv':np.vstack(G['uv']),
                    'tris':np.vstack(G['tris']),'tex':G['tex'],'mat':G['mat']})
    return {'groups':out,'textures':textures,'path':path,'matinfo':matinfo}

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
