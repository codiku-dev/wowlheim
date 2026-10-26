# Diagnostic : materiaux et textures des renderers exportes d un prefab Valheim. usage : vh_mat.py <prefab> [...]
import sys; import os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from vh_mesh import *
for n in sys.argv[1:]:
    r=renderers_of(env().container[[p for p in env().container if p.endswith('/'+n+'.prefab')][0]].read())
    for g,M,mr in r:
        for mp in mr.m_Materials:
            mat=mp.read()
            print(n,g.m_Name,mat.m_Name,mat.m_Shader.read().m_ParsedForm.m_Name if mat.m_Shader.m_PathID else None)
            for k,v in mat.m_SavedProperties.m_TexEnvs:
                if v.m_Texture.m_PathID:
                    t=v.m_Texture.read(); print('   ',k,t.m_Name,t.m_Width,t.m_Height)
            print('    colors',[(k,(round(c.r,2),round(c.g,2),round(c.b,2),round(c.a,2))) for k,c in mat.m_SavedProperties.m_Colors][:6])
