r"""Segment du cercle de portee des stations (Valheim : CraftingStation.m_areaMarker = CircleProjector).

Valheim (piece_workbench, lu dans les bundles le 2026-10-26) : enfant « AreaMarker », CircleProjector m_radius 20,
m_nrOfSegments 80, m_prefab = Assets/GameElements/Pieces/_res/station_marker/Circle_section.prefab : un cube Unity
(1 x 1 x 1) a l'echelle (0,15 ; 0,10 ; 1,0), materiau station_radius (Unlit/Color, couleur 0,8 gris clair, sans texture).
Chaque segment est pose au sol (rayon vers le bas) et oriente le long du cercle.

Ici : meme pave 1,0 m (long, axe X du modele = tangente) x 0,15 m x 0,10 m (haut), non eclaire, en trois couleurs :
  wl_station_ring.m2      gris 0,8 de Valheim (neutre)
  wl_station_ring_in.m2   vert : le joueur est dans la zone de construction de la station
  wl_station_ring_out.m2  rouge : hors zone
La base du pave est a z = 0 (le serveur donne la hauteur du sol + 5 cm). L'addon les pose avec WowlheimMarkerShow (DLL).
Sortie : C:\Wowlheim\wl_assets\mpq\World\Wowlheim\ ; gen_client_patch.py les met dans patch-3.MPQ (comme les autres modeles).
"""
import os, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wowfmt

MPQ_ROOT = r"C:\Wowlheim\wl_assets\mpq"
SIZE = (1.0, 0.15, 0.10)          # Circle_section : echelle (z=1 long, x=0,15 large, y=0,1 haut) -> repere WoW x long, y large, z haut
VARIANTS = {
    "wl_station_ring": (204, 204, 204),      # station_radius._Color = 0,8
    "wl_station_ring_in": (80, 235, 80),
    "wl_station_ring_out": (240, 70, 60),
}


def box(sx, sy, sz):
    """Pave centre en x/y, base a z = 0 : 24 sommets (normales par face), 12 triangles."""
    hx, hy = sx / 2, sy / 2
    faces = [  # normale, 4 coins
        ((1, 0, 0), [(hx, -hy, 0), (hx, hy, 0), (hx, hy, sz), (hx, -hy, sz)]),
        ((-1, 0, 0), [(-hx, hy, 0), (-hx, -hy, 0), (-hx, -hy, sz), (-hx, hy, sz)]),
        ((0, 1, 0), [(hx, hy, 0), (-hx, hy, 0), (-hx, hy, sz), (hx, hy, sz)]),
        ((0, -1, 0), [(-hx, -hy, 0), (hx, -hy, 0), (hx, -hy, sz), (-hx, -hy, sz)]),
        ((0, 0, 1), [(-hx, -hy, sz), (hx, -hy, sz), (hx, hy, sz), (-hx, hy, sz)]),
        ((0, 0, -1), [(-hx, hy, 0), (hx, hy, 0), (hx, -hy, 0), (-hx, -hy, 0)]),
    ]
    pos, nrm, uv, tris = [], [], [], []
    for n, quad in faces:
        b = len(pos)
        for p in quad:
            pos.append(p); nrm.append(n)
        uv += [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]
        tris += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
    return {'pos': np.array(pos, float), 'nrm': np.array(nrm, float), 'uv': np.array(uv, float),
            'tris': np.array(tris, int), 'tex': 0}


def main():
    out = {}
    for name, rgb in VARIANTS.items():
        tex_rel = "World\\Wowlheim\\Textures\\" + name + ".blp"
        fn = os.path.join(MPQ_ROOT, *tex_rel.split("\\"))
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        wowfmt.write_blp(fn, Image.new("RGBA", (8, 8), rgb + (255,)), alpha=False)
        rel = "World\\Wowlheim\\" + name + ".m2"
        fn = os.path.join(MPQ_ROOT, *rel.split("\\"))
        # materiau : 0x01 non eclaire (Unlit/Color de Valheim) | 0x04 deux faces ; melange opaque
        info = wowfmt.write_m2(fn, "WL_" + name, [box(*SIZE)], [tex_rel], render_flags=[(0x01 | 0x04, 0)])
        out[name] = rel
        print("  %-22s %s  %d sommets  bbox %s" % (name, rel, info['verts'], info['bbox']))
    return out


if __name__ == "__main__":
    main()
