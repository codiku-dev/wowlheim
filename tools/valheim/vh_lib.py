import UnityPy,json,glob,os
B=r"C:\Program Files (x86)\Steam\steamapps\common\Valheim\valheim_Data\StreamingAssets\SoftRef\Bundles"
R=r"C:\Program Files (x86)\Steam\steamapps\common\Valheim\valheim_Data\Resources"
_env=None
def env():
    global _env
    if _env is None:
        _env=UnityPy.load(*glob.glob(B+"/*"))
        # meshes/textures integres (Cube, Plane...) references par les prefabs
        _env.load_file(os.path.join(R,"unity default resources"),name="unity default resources")
    return _env
def prefab(path):
    return env().container[path].read()
def comps(go):
    for c in go.m_Component:
        yield c.component.deref()
def monos(go):
    out=[]
    for o in comps(go):
        if o.type.name=='MonoBehaviour':
            out.append((o,o.read_typetree()))
    return out
def classify(tt):
    k=set(tt)
    if 'm_resources' in k and 'm_category' in k: return 'Piece'
    if 'm_materialType' in k and 'm_health' in k and 'm_noRoofWear' in k: return 'WearNTear'
    if 'm_itemData' in k: return 'ItemDrop'
    if 'm_minToolTier' in k and 'm_logPrefab' in k: return 'TreeBase'
    if 'm_minToolTier' in k and 'm_subLogPrefab' in k: return 'TreeLog'
    if 'm_minToolTier' in k: return 'Destructible/Mine'
    if 'm_pieces' in k: return 'PieceTable'
    return '?'
