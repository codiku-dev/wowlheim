r"""Chaine d'import des modeles Valheim -> client WoW 1.12.1 (cahier : extraction Unity, conversion M2, BLP, MPQ, DBC).

Lit les prefabs dans les AssetBundles de Valheim (UnityPy), exporte la geometrie du LOD0 dans l'etat « neuf »,
convertit en M2 v256 + BLP2 et ecrit l'arborescence MPQ dans OUT (par defaut C:\Wowlheim\wl_assets\mpq).
Ecrit aussi OUT\..\manifest.json (modele -> chemin, boite englobante) pour la generation des DBC et du SQL.

usage : unity_venv\Scripts\python.exe build_assets.py [prefab ...]   (sans argument : la liste par defaut)
Artefacts locaux, assets Valheim : usage prive, ne pas distribuer."""
import sys, os, json, re
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vh_mesh import export_prefab, renderers_of, comp, snap_points
from vh_lib import env
import wowfmt

OUT = r"C:\Wowlheim\wl_assets"
MPQ_ROOT = os.path.join(OUT, "mpq")

# pieces du marteau (etabli / tailleur de pierre / forge), stations et mobilier de base
PIECES = """woodwall wood_wall_half wood_wall_quarter wood_floor wood_floor_1x1 wood_pole wood_pole2 wood_beam wood_beam_1
wood_beam_26 wood_beam_45 wood_roof wood_roof_45 wood_roof_top wood_roof_top_45 wood_roof_icorner wood_roof_icorner_45
wood_roof_ocorner wood_roof_ocorner_45 wood_wall_roof wood_wall_roof_45 wood_wall_roof_upsidedown wood_wall_roof_45_upsidedown
wood_door wood_gate wood_window wood_stair wood_stepladder wood_fence stake_wall piece_sharpstakes wood_pole_log wood_pole_log_4
wood_wall_log wood_wall_log_4x0.5 wood_log_26 wood_log_45 stone_wall_1x1 stone_wall_2x1 stone_wall_4x2 stone_floor_2x2
stone_pillar stone_arch stone_stair piece_workbench piece_workbench_ext1 piece_workbench_ext2 piece_workbench_ext3
piece_workbench_ext4 forge forge_ext1 forge_ext2 forge_ext3 forge_ext4 forge_ext5 forge_ext6 piece_stonecutter fire_pit hearth
bonfire piece_groundtorch_wood piece_walltorch bed piece_bed02 piece_chest_wood piece_chest piece_chair piece_chair02
piece_bench01 piece_logbench01 piece_table piece_table_round sign itemstand rug_deer rug_wolf piece_banner01 wood_stack
stone_pile portal_wood guard_stone smelter charcoal_kiln
wood_wall_roof_top wood_wall_roof_top_45 wood_log_67 wood_fence_gate stone_fence wood_dragon1
woodiron_pole woodiron_beam woodiron_beam_26 woodiron_beam_45 woodiron_beam_67
iron_floor_1x1_v2 iron_floor_2x2 iron_wall_1x1 iron_wall_2x2 iron_grate crystal_wall_1x1
darkwood_decowall darkwood_pole darkwood_pole4 darkwood_beam darkwood_beam4x4 darkwood_beam_26 darkwood_beam_45 darkwood_arch
darkwood_roof darkwood_roof_45 darkwood_roof_icorner darkwood_roof_icorner_45 darkwood_roof_ocorner darkwood_roof_ocorner_45
darkwood_roof_top darkwood_roof_top_45 darkwood_gate darkwood_raven darkwood_wolf
piece_artisanstation piece_spinningwheel blastfurnace
piece_throne01 piece_throne02 piece_chair03 piece_table_oak piece_chest_private piece_chest_blackmetal ArmorStand itemstandh
piece_groundtorch piece_groundtorch_blue piece_groundtorch_green piece_brazierfloor01 piece_brazierfloor02 piece_brazierceiling01
rug_fur rug_straw piece_banner02 piece_banner03 piece_banner04 piece_banner05 piece_banner06 piece_banner07 piece_banner08
piece_banner09 piece_banner10 piece_banner11 piece_CelebrationGarland piece_FairylightGarland piece_ArcheryTarget
wood_fine_stack wood_core_stack flint_pile bar_tin_stack bar_copper_stack bar_bronze_stack bar_iron_stack bar_silver_stack
bar_blackmetal_stack coal_pile bone_stack""".split()
# Pieces de la table du marteau de Valheim (398) NON importees et pourquoi : docs/VALHEIM_ASSETS.md, « Catalogue du marteau ».
TREES = "FirTree_Stub Pinetree_01_Stub BirchStub OakStub Beech1 Birch1 Oak1 FirTree Pinetree_01 beech_log beech_log_half Birch_log Birch_log_half Oak_log Oak_log_half FirTree_log FirTree_log_half PineTree_log PineTree_log_half Beech_Stub SwampTree1 SwampTree1_log SwampTree1_Stub".split()
ROCKS = "MineRock_Stone Rock_4 MineRock_Copper MineRock_Tin MineRock_Iron MineRock_Obsidian silvervein".split()
# ramassables de Valheim (composant Pickable : clic sans outil) -> GameObjects (tools/resources/rules.py PLACEMENTS, gen_server_sql.py)
PICKABLES = """Pickable_Branch Pickable_Stone Pickable_Flint RaspberryBush Pickable_Mushroom Pickable_Dandelion BlueberryBush
Pickable_Thistle Pickable_MountainCaveCrystal Pickable_Flax_Wild Pickable_Barley_Wild CloudberryBush Pickable_TarBig""".split()
TOOLS = "Hammer AxeStone AxeFlint AxeBronze AxeIron PickaxeAntler PickaxeBronze PickaxeIron Hoe".split()

# stations animees (SkinnedMeshRenderer, maillage pris en pose de liaison) et pieces aux materiaux sans texture (couleur unie)
SKINNED = {"piece_artisanstation", "piece_spinningwheel", "blastfurnace"}
FLAT_COLOR = {"crystal_wall_1x1", "Pickable_MountainCaveCrystal", "Pickable_TarBig", "bar_tin_stack", "bar_copper_stack", "bar_bronze_stack", "bar_silver_stack"}

CUTOUT = re.compile(r"leaf|leaves|needle|branch|twig|straw|feather|web|grass|fern|plant|(?<!c)hair|fur", re.I)
# shaders de Valheim a alpha teste (feuillage, herbe, tapis/fourrures, bannieres) ; ecorces exclues (alpha = mousse)
CUTOUT_SHADERS = {"Custom/Vegetation", "Custom/Grass", "Custom/Rug"}
OPAQUE_NAMES = re.compile(r"bark|trunk|_log|stump", re.I)

def is_alpha_tex(img, name="", info=None):
    """Transparence decoupee (alpha teste) : feuillage, chaume, sapins, buissons, bannieres, tapis... Decide d'abord par
    le materiau Valheim (info : vh_mesh.mat_info) : shader de vegetation / herbe / tapis, _Mode 1 (Cutout) ou mot-cle
    _ALPHATEST_ON ; a defaut, par le nom (CUTOUT). Les autres textures (roches, metaux, ecorces) se servent du canal alpha
    pour la brillance ou la mousse : elles restent opaques. Avant le 2026-10-26, seul le nom comptait : sapins (Pine_tree*),
    buissons, bannieres, lin, orge, pissenlit... sortaient en plaques opaques, et « DarkWoodChair » etait decoupe (« hair »)."""
    a = np.array(img.convert("RGBA"))[:, :, 3]
    if (a < 128).mean() <= 0.05: return False
    if CUTOUT.search(name): return True
    if not info or OPAQUE_NAMES.search(name): return False
    if info.get('shader') in CUTOUT_SHADERS: return True
    if "_ALPHATEST_ON" in info.get('keywords', []): return True
    return abs(info.get('mode', 0.0) - 1.0) < 0.01

def fix_winding(g):
    P, N, T = g['pos'], g['nrm'], g['tris']
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    vn = N[T[:, 0]] + N[T[:, 1]] + N[T[:, 2]]
    s = np.sign((fn * vn).sum(1)).sum()
    if s < 0: g['tris'] = T[:, [0, 2, 1]]
    return s

def tool_space(res, name):
    """Outils : geometrie du sous-arbre « attach » dans son propre repere, axe long -> +X (tete vers +X)."""
    allp = np.vstack([g['pos'] for g in res['groups']])
    c = allp.mean(0)
    u, s, vt = np.linalg.svd(allp - c, full_matrices=False)
    ax = vt[0]; ax2 = vt[1]
    proj = (allp - c) @ ax
    # la tete (la plus large) du cote +X
    lo_w = np.ptp(((allp - c) @ ax2)[proj < np.percentile(proj, 20)])
    hi_w = np.ptp(((allp - c) @ ax2)[proj > np.percentile(proj, 80)])
    if lo_w > hi_w: ax = -ax
    ax3 = np.cross(ax, ax2)
    R = np.array([ax, ax3, -ax2])           # lignes : nouvelles bases X, Y, Z (la tete s'etend vers -Z)
    for g in res['groups']:
        g['pos'] = (g['pos'] - c) @ R.T
        g['nrm'] = g['nrm'] @ R.T
    allp = np.vstack([g['pos'] for g in res['groups']])
    L = np.ptp(allp[:, 0])
    shift = np.array([allp[:, 0].min() + 0.25 * L, 0, 0])
    for g in res['groups']: g['pos'] = g['pos'] - shift

TOOL_SCALE = 1.3   # les outils de Valheim sont petits a cote des armes de WoW

def lay_down(res):
    """Buches : le prefab est vertical (il tombe avec la physique) ; on le couche le long de +X, pose sur le sol."""
    R = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float)   # Z -> X
    for g in res['groups']:
        g['pos'] = g['pos'] @ R.T; g['nrm'] = g['nrm'] @ R.T
    zmin = min(g['pos'][:, 2].min() for g in res['groups'])
    for g in res['groups']: g['pos'][:, 2] -= zmin

# Apparence des filons : le prefab de jeu (PV, zones, butin lus par gen_server_sql.py) garde son nom, mais son modele
# vient du prefab que Valheim place reellement dans le monde. MineRock_Copper / MineRock_Iron / MineRock_Stone sont des
# prototypes inutilises de Valheim (24 galets « default », texture 64 px ocre/vert ou orange) : ce sont eux qui
# ressortaient en aplats pastel en jeu (texture claire et saturee, etiree sur de gros galets). Valheim montre :
#  - cuivre : rock4_copper (roche grise, veines cuivre/vert-de-gris, copper_ore_big_d tuilee x8) ;
#  - pierre : rock4_coast (meme roche, gouacherock_big) ;
#  - fer : mudpile (tas de boue des cryptes, boue en projection triplanaire + ferraille, boucliers, ossements).
# (prefab source, echelle uniforme, coupe : triangles entierement sous z = coupe retires apres mise a l'echelle).
# rock4_* mesure 24 x 28 m pour 4 m hors sol (17 m enterres) : ramene a ~9 x 11 m, 1,6 m de haut, jupe de 1 m sous le sol.
VISUAL = {"MineRock_Copper": ("rock4_copper", 0.4, -1.0), "MineRock_Stone": ("rock4_coast", 0.4, -1.0),
          "MineRock_Iron": ("mudpile", 1.0, None)}

def apply_visual(res, scale, zclip):
    for g in res['groups']:
        g['pos'] = g['pos'] * scale
        if zclip is None: continue
        T = g['tris']
        T = T[g['pos'][T][:, :, 2].max(1) >= zclip]
        used = np.unique(T); remap = -np.ones(len(g['pos']), int); remap[used] = np.arange(len(used))
        for k in ('pos', 'nrm', 'uv'): g[k] = g[k][used]
        g['tris'] = remap[T]
    res['groups'] = [g for g in res['groups'] if len(g['tris'])]

def build(name, kind, manifest, texcache):
    src, vscale, zclip = VISUAL.get(name, (name, 1.0, None))
    res = export_prefab(src, attach_only=(kind == 'tool'), skinned=name in SKINNED, flat_color=name in FLAT_COLOR)
    if not res['groups']:
        print("  (vide)", name); return
    if src != name: apply_visual(res, vscale, zclip)
    if kind == 'tool': tool_space(res, name)
    # buches tombees des arbres seulement : les pieces wood_pole_log / wood_wall_log restent debout (avant le
    # 2026-10-26 tout « *_log » etait couche, poteau en rondin construit allonge le long de X)
    if kind == 'tree' and name.endswith(('_log', '_log_half')): lay_down(res)
    offset = [0.0, 0.0, 0.0]
    snaps = []
    if kind == 'piece':
        # base au sol, centree en x/y : le serveur pose la piece par sa base (boite logique, Geometry.cpp)
        allp = np.vstack([g['pos'] for g in res['groups']])
        lo, hi = allp.min(0), allp.max(0)
        offset = [-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]]
        for g in res['groups']: g['pos'] = g['pos'] + np.array(offset)
        snaps = [[round(a + b, 3) for a, b in zip(p, offset)] for p in snap_points(name)]
    groups = []; texpaths = []; rflags = []; ttypes = []
    for g in res['groups']:
        tn = g['tex']
        if tn not in texcache:
            img = res['textures'].get(tn)
            if img is None:
                texcache[tn] = None
            else:
                sub = "Item\\ObjectComponents\\Weapon" if kind == 'tool' else "World\\Wowlheim\\Textures"
                rel = sub + "\\" + ("WL_" if kind == 'tool' else "") + tn.replace(" ", "_") + ".blp"
                fn = os.path.join(MPQ_ROOT, *rel.split("\\")); os.makedirs(os.path.dirname(fn), exist_ok=True)
                cut = is_alpha_tex(img, tn, res.get('matinfo', {}).get(tn))
                wowfmt.write_blp(fn, img, max_size=256 if kind == 'tool' else 512, alpha=cut)
                texcache[tn] = (rel, cut)
        if texcache[tn] is None: continue
        rel, alpha = texcache[tn]
        fix_winding(g)
        uv = g['uv'].copy(); uv[:, 1] = 1.0 - uv[:, 1]
        if rel not in texpaths:
            texpaths.append(rel)
            # feuillage : alpha teste + deux faces ; reste : opaque, deux faces pour les plans fins
            rflags.append((0x04, 1) if alpha else (0x04, 0))
            ttypes.append(0)                    # textures a chemin fixe (aussi pour les outils tenus en main)
        groups.append({'pos': g['pos'], 'nrm': g['nrm'], 'uv': uv, 'tris': g['tris'], 'tex': texpaths.index(rel),
                       'alpha': alpha})
    if not groups:
        print("  (sans texture)", name); return
    # collision : les groupes opaques (troncs, planches, pierres), pas le feuillage
    coll = None
    if kind in ('piece', 'tree', 'rock'):
        cv, ct, base = [], [], 0
        for g in groups:
            if g['alpha']: continue
            cv.append(g['pos']); ct.append(g['tris'] + base); base += len(g['pos'])
        if cv:
            coll = (np.vstack(cv), np.vstack(ct))
            if len(coll[1]) > 4000: coll = None
    seqs = None; rot = None; scl = None
    if kind == 'tree' and not name.endswith(('_log', '_log_half', '_Stub')):
        seqs, rot = tree_anims()
    if kind == 'rock':
        seqs, rot, scl = rock_anims()
    if kind == 'tool':
        rel = "Item\\ObjectComponents\\Weapon\\WL_" + name + ".m2"
        # Chemin fixe (type 0) comme les autres modeles. Avant le 2026-10-26 : nom vide ici avec type 0 (pas de type 2 ni de
        # ModelTexture dans ItemDisplayInfo) -> aucun fichier charge, outils tenus en main tout BLANCS en jeu.
        texpaths_m2 = texpaths
    else:
        rel = "World\\Wowlheim\\" + name + ".m2"
        texpaths_m2 = texpaths
    fn = os.path.join(MPQ_ROOT, *rel.split("\\")); os.makedirs(os.path.dirname(fn), exist_ok=True)
    info = wowfmt.write_m2(fn, "WL_" + name, groups, texpaths_m2, sequences=seqs, bone_rot=rot, collision=coll,
                           tex_types=ttypes, render_flags=rflags, scale=TOOL_SCALE if kind == 'tool' else 1.0,
                           bone_scale=scl)
    manifest[name] = {'kind': kind, 'm2': rel, 'textures': texpaths, 'bbox': info['bbox'], 'verts': info['verts'],
                      'tris': info['tris'], 'path': res['path'], 'collision': coll is not None,
                      'offset': offset, 'snaps': snaps}
    print("  %-28s %-6s %5d sommets %5d tri  bbox %s" % (name, kind, info['verts'], info['tris'],
          [[round(x, 2) for x in v] for v in info['bbox']]))

def rock_anims():
    """Stand (0), Death (1 : la roche se brise -> retrecit), Dead (6), Wound (9 : secousse au coup de pioche)."""
    I = (0, 0, 0, 1)
    q = lambda deg: wowfmt.quat_axis((1, 0, 0), np.radians(deg))
    seqs = [(0, 0, 3333, 0), (1, 3400, 4000, 0), (6, 4100, 5100, 0), (9, 5200, 5500, 0)]
    rt, rv, rr, st, sv, sr = [], [], [], [], [], []
    def key(T, V, R, frames):
        s0 = len(T)
        for t, v in frames: T.append(t); V.append(v)
        R.append((s0, len(T) - 1))
    one, tiny = (1.0, 1.0, 1.0), (0.02, 0.02, 0.02)
    key(rt, rv, rr, [(0, I), (3333, I)]); key(st, sv, sr, [(0, one), (3333, one)])
    key(rt, rv, rr, [(3400, I), (4000, q(6))]); key(st, sv, sr, [(3400, one), (3550, (1.08, 1.08, 1.08)), (4000, tiny)])
    key(rt, rv, rr, [(4100, I), (5100, I)]); key(st, sv, sr, [(4100, tiny), (5100, tiny)])
    key(rt, rv, rr, [(5200, I), (5280, q(2)), (5380, q(-1.5)), (5500, I)]); key(st, sv, sr, [(5200, one), (5500, one)])
    return seqs, (rr, rt, rv), (sr, st, sv)

def tree_anims():
    """Stand (0), Death (1 : chute de 90 deg vers +X), Dead (6 : couche), Wound (9 : secousse au coup de hache)."""
    I = (0, 0, 0, 1)
    q = lambda deg: wowfmt.quat_axis((0, 1, 0), np.radians(deg))
    seqs = [(0, 0, 3333, 0), (1, 3400, 5400, 0), (6, 5500, 6500, 0), (9, 6600, 7000, 0)]
    times, vals, ranges = [], [], []
    def key(frames):
        s = len(times)
        for t, v in frames: times.append(t); vals.append(v)
        ranges.append((s, len(times) - 1))
    key([(0, I), (3333, I)])
    key([(3400, I), (3900, q(8)), (4600, q(45)), (5100, q(88)), (5250, q(84)), (5400, q(90))])
    key([(5500, q(90)), (6500, q(90))])
    key([(6600, I), (6700, q(2.5)), (6800, q(-1.5)), (6900, q(0.7)), (7000, I)])
    return seqs, (ranges, times, vals)

if __name__ == "__main__":
    os.makedirs(MPQ_ROOT, exist_ok=True)
    mf_path = os.path.join(OUT, "manifest.json")
    manifest = json.load(open(mf_path)) if os.path.exists(mf_path) else {}
    texcache = {}
    todo = [(n, 'piece') for n in PIECES] + [(n, 'tree') for n in TREES] + [(n, 'rock') for n in ROCKS] + [(n, 'tool') for n in TOOLS] + [(n, 'pickable') for n in PICKABLES]
    if len(sys.argv) > 1:
        todo = [t for t in todo if t[0] in sys.argv[1:]]
    for n, k in todo:
        try:
            build(n, k, manifest, texcache)
        except Exception as ex:
            import traceback; traceback.print_exc()
            print("  ECHEC", n, repr(ex))
    json.dump(manifest, open(mf_path, "w"), indent=1)
    print("modeles :", len(manifest))
