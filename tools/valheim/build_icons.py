r"""Icones Valheim -> Interface\Icons\WL_<nom>.blp (64x64) : objets (materiaux, outils) et pieces du marteau.
Lit valheim_data.json (vh_dump_all.py) pour les noms de sprites ; ecrit dans C:\Wowlheim\wl_assets\mpq et
complete C:\Wowlheim\wl_assets\icons.json (prefab -> nom d'icone WoW). Artefacts locaux, ne pas distribuer.
--only <prefabs...> : seulement ces objets (absents de valheim_data.json), fusionnes dans icons.json."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vh_lib import env
import wowfmt
from PIL import Image

OUT = r"C:\Wowlheim\wl_assets"
DATA = r"C:\Wowlheim\valheim_extract\valheim_data.json"

def main():
    d = json.load(open(DATA, encoding="utf-8"))
    P = d["prefabs"]
    want = {}   # prefab -> nom du sprite
    for n, v in P.items():
        if not v or "monos" not in v: continue
        m = v["monos"]
        if "Piece" in m and m["Piece"][0].get("m_icon"):
            want[n] = m["Piece"][0]["m_icon"]["name"]
        elif "ItemDrop" in m:
            ic = m["ItemDrop"][0]["m_itemData"]["m_shared"].get("m_icons") or []
            if ic and ic[0]: want[n] = ic[0]["name"]
    sprites = {}
    names = set(want.values())
    for o in env().objects:
        if o.type.name != "Sprite": continue
        try:
            nm = o.peek_name()
        except Exception:
            continue
        if nm in names and nm not in sprites:
            sprites[nm] = o
    os.makedirs(os.path.join(OUT, "mpq", "Interface", "Icons"), exist_ok=True)
    res = {}
    for pf, sp in sorted(want.items()):
        o = sprites.get(sp)
        if o is None:
            print("  sprite absent", pf, sp); continue
        try:
            img = o.read().image.convert("RGBA")
        except Exception as ex:
            print("  echec", pf, sp, ex); continue
        # carre centre puis 64x64, fond sombre (les icones WoW sont opaques)
        w, h = img.size; s = max(w, h)
        sq = Image.new("RGBA", (s, s), (24, 20, 16, 255))
        sq.alpha_composite(img, ((s - w) // 2, (s - h) // 2))
        sq = sq.resize((64, 64), Image.LANCZOS)
        icon = "WL_" + sp.replace(" ", "_")
        wowfmt.write_blp(os.path.join(OUT, "mpq", "Interface", "Icons", icon + ".blp"), sq, max_size=64, fmt="palette")
        res[pf] = icon
    json.dump(res, open(os.path.join(OUT, "icons.json"), "w"), indent=1)
    print("icones :", len(res))

def write_icon(o, sp):
    img = o.read().image.convert("RGBA")
    w, h = img.size; s = max(w, h)
    sq = Image.new("RGBA", (s, s), (24, 20, 16, 255))
    sq.alpha_composite(img, ((s - w) // 2, (s - h) // 2))
    sq = sq.resize((64, 64), Image.LANCZOS)
    icon = "WL_" + sp.replace(" ", "_")
    wowfmt.write_blp(os.path.join(OUT, "mpq", "Interface", "Icons", icon + ".blp"), sq, max_size=64, fmt="palette")
    return icon

def only(prefabs):
    """Ajoute les icones d'objets absents de valheim_data.json (ex. minerais : CopperOre...) sans toucher aux autres :
    sprite ItemDrop.m_itemData.m_shared.m_icons[0] lu dans le prefab, fusionne dans icons.json."""
    e = env()
    n2p = {}
    for path in e.container:
        if path.endswith(".prefab"): n2p.setdefault(os.path.basename(path)[:-7], path)
    res = json.load(open(os.path.join(OUT, "icons.json")))
    os.makedirs(os.path.join(OUT, "mpq", "Interface", "Icons"), exist_ok=True)
    for pf in prefabs:
        go = e.container[n2p[pf]].read()
        for c in go.m_Component:
            o = c.component.deref()
            if o.type.name != "MonoBehaviour": continue
            tt = o.read_typetree()
            if "m_itemData" not in tt: continue
            m = o.read()
            spr = m.m_itemData.m_shared.m_icons[0].deref()
            name = spr.peek_name() if hasattr(spr, "peek_name") else spr.read().m_Name
            res[pf] = write_icon(spr, name)
            print(" ", pf, "->", res[pf])
    json.dump(res, open(os.path.join(OUT, "icons.json"), "w"), indent=1)

if __name__ == "__main__":
    if "--only" in sys.argv:
        only(sys.argv[sys.argv.index("--only") + 1:])   # build_icons.py --only CopperOre TinOre IronScrap SilverOre
    else:
        main()
