# Diagnostic : hierarchie d un prefab Valheim (renderers, maillages, LOD). usage : vh_dbg.py <prefab> [...]
import sys; import os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from vh_mesh import *
e=env()
for n in sys.argv[1:]:
    path=[p for p in e.container if p.endswith('/'+n+'.prefab')][0]
    go=e.container[path].read()
    allg=[]
    tr=[c.component.deref().read() for c in go.m_Component if c.component.deref().type.name=="Transform"][0]
    def w(tr,d):
        g=tr.m_GameObject.read()
        cs=[]
        for c in g.m_Component:
            o=c.component.deref(); t=o.type.name
            if t=='MeshRenderer': cs.append(f'MR{c.component.m_PathID%100000}:{o.read().m_Enabled}')
            elif t=='MeshFilter':
                mf=o.read(); 
                if mf.m_Mesh.m_PathID: 
                    m=mf.m_Mesh.read(); cs.append(f'MF:{m.m_Name}:{m.m_VertexData.m_VertexCount}')
            elif t=='LODGroup':
                lg=o.read(); cs.append('LOD:'+str([[r.renderer.m_PathID%100000 for r in l.renderers] for l in lg.m_LODs]))
        print('  '*d+g.m_Name,g.m_IsActive,cs)
        for ch in tr.m_Children: w(ch.read(),d+1)
    w(tr,0)
