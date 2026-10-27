"""Boites de collision des pieces du marteau d'apres les colliders Unity de Valheim (et non la bbox de rendu).
Valheim teste chevauchement / fumee (SmokeSpawner) / abri (Cover) / toit contre les colliders : les effets, particules,
LOD ou decors sans collider gonflent la bbox de rendu (four a charbon : 4,9 x 4,7 m de rendu pour ~2,5 m de collider).

Pour chaque piece du manifeste (C:\\Wowlheim\\wl_assets\\manifest.json, kind == 'piece') : parcours des GameObjects ACTIFS
(transforms vh_mesh.trs, racine a l'origine comme pour le rendu), colliders actives (m_Enabled) et non-triggers (m_IsTrigger),
Box/Sphere/Capsule/Mesh -> sommets en espace WoW (vh_mesh.U2W), puis decalage de recentrage du modele (manifest 'offset',
build_assets.py) : boite englobante dans le repere de la piece (base du modele au sol, centre x/y du modele a l'origine).
Couches : solides (Default, piece, static_solid, Default_small, vehicle) ; a defaut piece_nonsolid ; a defaut rien (le
generateur garde alors la bbox de rendu).
Sortie : C:\\Wowlheim\\wl_assets\\colliders.json  {prefab: {'src': 'solid'|'nonsolid', 'lo': [x,y,z], 'hi': [x,y,z], 'n': nb}}
usage : C:\\Wowlheim\\tools\\unity_venv\\Scripts\\python.exe vh_colliders.py [prefab ...]"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from vh_lib import env
from vh_mesh import trs, U2W, export_prefab
from UnityPy.helpers.MeshHelper import MeshHandler

A = r"C:\Wowlheim\wl_assets"
# TagManager de Valheim (globalgamemanagers)
SOLID = {0, 10, 15, 20, 28}         # Default, piece, static_solid, Default_small, vehicle
NONSOLID = {16}                     # piece_nonsolid (tapis, bannieres... : traverses par le joueur et les rayons)
_mesh_cache = {}

def _corners(c, e):
    c = np.asarray(c, float); e = np.asarray(e, float)
    return np.array([c + e * np.array([sx, sy, sz]) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])

def _mesh_pts(pptr):
    pid = (pptr.m_FileID, pptr.m_PathID)
    if pid not in _mesh_cache:
        mesh = pptr.read()
        try:
            h = MeshHandler(mesh); h.process()
            V = np.array(h.m_Vertices, float)[:, :3]
            if not len(V): raise ValueError
        except Exception:
            b = mesh.m_LocalAABB
            V = _corners([b.m_Center.x, b.m_Center.y, b.m_Center.z], [b.m_Extent.x, b.m_Extent.y, b.m_Extent.z])
        _mesh_cache[pid] = V
    return _mesh_cache[pid]

def local_pts(o):
    """Points (repere local du GameObject, Unity) englobant le collider o."""
    t = o.type.name
    c = o.read()
    if t == 'BoxCollider':
        return _corners([c.m_Center.x, c.m_Center.y, c.m_Center.z], [c.m_Size.x / 2, c.m_Size.y / 2, c.m_Size.z / 2])
    if t == 'SphereCollider':
        return _corners([c.m_Center.x, c.m_Center.y, c.m_Center.z], [c.m_Radius] * 3)
    if t == 'CapsuleCollider':
        r = c.m_Radius; e = [r, r, r]; e[c.m_Direction] = max(r, c.m_Height / 2)
        return _corners([c.m_Center.x, c.m_Center.y, c.m_Center.z], e)
    if t == 'MeshCollider':
        if c.m_Mesh.m_PathID == 0: return None
        return _mesh_pts(c.m_Mesh)
    return None

COLLIDERS = {'BoxCollider', 'SphereCollider', 'CapsuleCollider', 'MeshCollider'}

def colliders_of(go):
    """[(couche, type, nom du GameObject, points WoW)] des colliders actifs non-triggers ; racine du prefab a l'origine."""
    root = None
    for cc in go.m_Component:
        o = cc.component.deref()
        if o.type.name == 'Transform': root = o.read(); break
    out = []
    def walk(tr, M):
        g = tr.m_GameObject.read()
        if not g.m_IsActive: return
        Mw = M @ trs(tr)
        for cc in g.m_Component:
            o = cc.component.deref()
            if o.type.name not in COLLIDERS: continue
            c = o.read()
            if not getattr(c, 'm_Enabled', True) or getattr(c, 'm_IsTrigger', False): continue
            P = local_pts(o)
            if P is None: continue
            Pw = (np.c_[P, np.ones(len(P))] @ Mw.T)[:, :3] @ U2W.T
            out.append((g.m_Layer, o.type.name, g.m_Name, Pw))
        for ch in tr.m_Children: walk(ch.read(), Mw)
    walk(root, np.linalg.inv(trs(root)))
    return out

def box_of(name, m):
    e = env()
    path = m.get('path') or sorted([p for p in e.container if p.endswith('/' + name + '.prefab')], key=len)[0]
    cols = colliders_of(e.container[path].read())
    # Pas de rotation : depuis le 2026-10-26 soir, build_assets.py ne couche (lay_down) que les buches d'arbres (genre
    # 'tree') ; les pieces wood_pole_log / wood_wall_log sont construites debout, comme dans Valheim.
    off = np.array(m.get('offset', [0, 0, 0]), float)
    for src, layers in (('solid', SOLID), ('nonsolid', NONSOLID)):
        sel = [c for c in cols if c[0] in layers]
        if sel:
            P = np.vstack([c[3] for c in sel]) + off
            return {'src': src, 'lo': P.min(0).round(4).tolist(), 'hi': P.max(0).round(4).tolist(), 'n': len(sel),
                    'parts': sorted({'%s:%s@%d' % (c[1][:-8], c[2], c[0]) for c in sel})[:12]}
    return {'src': 'none', 'n': 0, 'layers': sorted({c[0] for c in cols})}

def main():
    man = json.load(open(os.path.join(A, 'manifest.json')))
    names = sys.argv[1:] or sorted(n for n, v in man.items() if v['kind'] == 'piece')
    fn = os.path.join(A, 'colliders.json')
    res = json.load(open(fn)) if sys.argv[1:] and os.path.exists(fn) else {}
    for n in names:
        try:
            res[n] = box_of(n, man[n])
        except Exception as ex:
            res[n] = {'src': 'error', 'n': 0, 'err': repr(ex)}
        r = res[n]
        if 'lo' in r:
            print('%-28s %-8s n=%-3d size %s' % (n, r['src'], r['n'], [round(b - a, 2) for a, b in zip(r['lo'], r['hi'])]))
        else:
            print('%-28s %s %s' % (n, r['src'], r.get('err', r.get('layers', ''))))
    json.dump(res, open(fn, 'w'), indent=1)
    print('->', fn, len(res))

if __name__ == '__main__':
    main()
