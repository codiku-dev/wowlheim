r"""Patch client Wowlheim : DBC (modeles d'objets, creatures-arbres, affichages d'objets) + archive MPQ.

Entrees : C:\Wowlheim\wl_assets\{manifest.json, icons.json, mpq\...} (build_assets.py, build_icons.py),
          DBC d'origine du client extraits dans C:\Wowlheim\data\dbc (sauvegardes une fois dans dbc_orig).
Sorties : C:\Wowlheim\wl_assets\wl_ids.json (identifiants stables, lus par gen_server_sql.py),
          DBC modifies dans mpq\DBFilesClient et dans C:\Wowlheim\data\dbc (le serveur lit les memes),
          C:\Wowlheim\wl_assets\patch-3.MPQ ; --install le copie dans C:\Wowlheim\client_test\Data.
Identifiants : GameObjectDisplayInfo 20000+, CreatureModelData 3000+, CreatureDisplayInfo 25000+, ItemDisplayInfo 70000+."""
import sys, os, json, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "client"))
import numpy as np
from wowfmt import DBC
from mpq_write import write_mpq

A = r"C:\Wowlheim\wl_assets"
DBC_SRV = r"C:\Wowlheim\data\dbc"
DBC_ORIG = r"C:\Wowlheim\data\dbc_orig"
CLIENT = r"C:\Wowlheim\client_test\Data"
WL_PLACE_SPELL = 40001   # lu aussi par le serveur (BuildingMgr.h)
WL_ICON = 3000

# objets Wowlheim -> prefab Valheim (icone, et modele tenu en main pour les outils)
ITEM_PREFAB = {
    9200001: "Wood", 9200002: "Stone", 9200003: "Flint", 9200004: "Resin", 9200005: "DeerHide",
    9200006: "LeatherScraps", 9200009: "HardAntler", 9200011: "FineWood", 9200012: "RoundLog", 9200013: "Copper",
    9200014: "Tin", 9200015: "Bronze", 9200016: "TrollHide", 9200019: "GreydwarfEye", 9200021: "Iron",
    9200022: "ElderBark", 9200023: "BoneFragments", 9200024: "Entrails", 9200029: "SurtlingCore", 9200031: "Silver",
    9200032: "Obsidian", 9200033: "WolfPelt", 9200034: "Crystal", 9200041: "BlackMetal", 9200043: "LinenThread",
    9200044: "LoxPelt", 9200042: "Flax", 9200039: "FreezeGland", 9200049: "BlackCore",
    9200082: "Mushroom",   # ramassable de la prairie (Pickable_Mushroom)
    # materiaux des pieces du marteau ajoutees (gen_server_sql.py ITEM, tools/resources/rules.py)
    9200070: "Raspberry", 9200071: "Dandelion", 9200072: "Blueberries", 9200073: "Thistle", 9200074: "Carrot",
    9200075: "Guck", 9200076: "Bloodbag", 9200077: "WolfClaw", 9200078: "DragonTear", 9200079: "Cloudberry",
    9200080: "Barley", 9200081: "BlackMetalScrap",
    9201100: "Hammer", 9201011: "AxeFlint", 9201012: "PickaxeAntler", 9201021: "AxeBronze", 9201022: "PickaxeBronze",
    9201031: "AxeIron", 9201032: "PickaxeIron", 9201051: "AxeBlackMetal", 9201010: "AxeStone",
    # 9201041/9201042 (« argent ») et 9201052 (pioche en sombracier : recette Valheim en bois d'Yggdrasil, absent) supprimes
    9200051: "Coal", 9200052: "Chain", 9200053: "BronzeNails", 9200054: "IronNails", 9200055: "Feathers",
    9200056: "SharpeningStone", 9200057: "Tar",
    # minerais a fondre a la fonderie (Smelter de Valheim)
    9200060: "CopperOre", 9200061: "TinOre", 9200062: "IronScrap", 9200063: "SilverOre", 9200064: "IronOre",
}

def load_ids():
    p = os.path.join(A, "wl_ids.json")
    ids = json.load(open(p)) if os.path.exists(p) else {}
    for k in ("go", "cmd", "cdi", "idi"): ids.setdefault(k, {})
    return ids

def alloc(table, key, base):
    if key not in table:
        table[key] = max(list(table.values()) + [base - 1]) + 1
    return table[key]

def main(install):
    man = json.load(open(os.path.join(A, "manifest.json")))
    icons = json.load(open(os.path.join(A, "icons.json")))
    ids = load_ids()
    if not os.path.isdir(DBC_ORIG):
        shutil.copytree(DBC_SRV, DBC_ORIG)
    go = DBC(os.path.join(DBC_ORIG, "GameObjectDisplayInfo.dbc"))
    cmd = DBC(os.path.join(DBC_ORIG, "CreatureModelData.dbc"))
    cdi = DBC(os.path.join(DBC_ORIG, "CreatureDisplayInfo.dbc"))
    idi = DBC(os.path.join(DBC_ORIG, "ItemDisplayInfo.dbc"))
    tpl_go = go.rows[0]; tpl_cmd = cmd.find(1); tpl_cdi = cdi.find(4); tpl_idi = idi.find(8568)

    for name, m in sorted(man.items()):
        if m["kind"] in ("piece", "tree", "rock", "pickable"):
            gid = alloc(ids["go"], name, 20000)
            r = bytearray(tpl_go)
            go.set(r, 0, gid); go.set(r, 1, go.add_string(m["m2"][:-3] + ".mdx"))
            for f in range(2, 12): go.set(r, f, 0)
            go.upsert(r)
        if m["kind"] in ("tree", "rock"):
            # creature : arbres et buches (on les frappe a la hache comme dans Valheim)
            mid = alloc(ids["cmd"], name, 3000)
            r = bytearray(tpl_cmd)
            lo, hi = np.array(m["bbox"][0]), np.array(m["bbox"][1])
            cmd.set(r, 0, mid); cmd.set(r, 1, 0); cmd.set(r, 2, cmd.add_string(m["m2"][:-3] + ".mdx"))
            cmd.set(r, 3, 2)                                  # SizeClass
            cmd.set(r, 4, 1.0, "f")                           # ModelScale
            cmd.set(r, 5, 0xFFFFFFFF)                         # BloodID : aucun (pas de sang sur du bois)
            cmd.set(r, 6, 0xFFFFFFFF)                         # empreintes : aucune
            for f in (7, 8, 9): cmd.set(r, f, 0.0, "f")
            cmd.set(r, 10, 0); cmd.set(r, 11, 0); cmd.set(r, 12, 0); cmd.set(r, 13, 0)
            trunk = 1.2 if not name.endswith(("_log", "_log_half")) else float(max(hi[1] - lo[1], 0.6))
            cmd.set(r, 14, trunk, "f")                        # CollisionWidth
            cmd.set(r, 15, float(min(hi[2], 6.0)), "f")       # CollisionHeight
            cmd.upsert(r)
            did = alloc(ids["cdi"], name, 25000)
            r = bytearray(tpl_cdi)
            cdi.set(r, 0, did); cdi.set(r, 1, mid); cdi.set(r, 2, 0); cdi.set(r, 3, 0); cdi.set(r, 4, 1.0, "f")
            cdi.set(r, 5, 255)
            for f in range(6, 12): cdi.set(r, f, 0)
            cdi.set(r, 9, 1)                                  # meme valeur que les modeles d'origine (taille)
            cdi.upsert(r)

    # affichages d'objets : icones Valheim, et modele 3D Valheim pour les outils tenus en main
    for entry, pf in sorted(ITEM_PREFAB.items()):
        iid = alloc(ids["idi"], str(entry), 70000)
        r = bytearray(tpl_idi)
        for f in range(1, idi.fc): idi.set(r, f, 0)
        idi.set(r, 0, iid)
        m = man.get(pf)
        if m and m["kind"] == "tool":
            idi.set(r, 1, idi.add_string(m["m2"].split("\\")[-1][:-3] + ".mdx"))
        idi.set(r, 11, idi.get(tpl_idi, 11))                  # meme groupe de sons que la masse d'origine
        ic = icons.get(pf)
        if ic: idi.set(r, 5, idi.add_string(ic))
        idi.upsert(r)
    ids["item_prefab"] = {str(k): v for k, v in ITEM_PREFAB.items()}

    # sort de pose du marteau : clone de Fusee eclairante (1543, cible au sol -> cercle de ciblage du client),
    # effet factice ; le serveur pose la piece choisie au point clique (Spell::cast, BuildingMgr::PlaceFromSpell)
    spell = DBC(os.path.join(DBC_ORIG, "Spell.dbc")); sicon = DBC(os.path.join(DBC_ORIG, "SpellIcon.dbc"))
    r = bytearray(sicon.rows[0]); sicon.set(r, 0, WL_ICON); sicon.set(r, 1, sicon.add_string("Interface\\Icons\\" + icons.get("Hammer", "WL_hammer")))
    sicon.upsert(r)
    r = bytearray(spell.find(1543))
    for f in range(1, spell.fc): spell.set(r, f, 0)
    spell.set(r, 0, WL_PLACE_SPELL)
    spell.set(r, 13, 0x40)            # Targets : TARGET_FLAG_DEST_LOCATION
    spell.set(r, 18, 1)               # instantane
    spell.set(r, 25, 101)
    spell.set(r, 36, 3)               # portee 20 m
    for f in (58, 59, 60): spell.set(r, f, 0xFFFFFFFF)
    spell.set(r, 61, 76)              # SPELL_EFFECT_SUMMON_OBJECT_WILD : le client affiche le GameObject sous le curseur (fantome)
    spell.set(r, 106, 9110001)        # EffectMiscValue1 : piece par defaut ; la DLL la change selon le menu (WowlheimSetPlaceObject)
    spell.set(r, 76, 0xFFFFFFFF)
    spell.set(r, 82, 28)              # meme cible que Fusee eclairante (zone au point vise)
    spell.set(r, 88, 7)               # rayon 2 m : taille du cercle au sol
    spell.set(r, 117, WL_ICON)
    spell.set(r, 120, spell.add_string("Construire"))
    spell.set(r, 128, spell.get(spell.find(1543), 128))
    spell.set(r, 137, spell.get(spell.find(1543), 137))
    spell.set(r, 146, spell.get(spell.find(1543), 146)); spell.set(r, 155, spell.get(spell.find(1543), 155))
    spell.set(r, 166, 0xFFFFFFFF)
    for f in (167, 168, 169): spell.set(r, f, 1.0, "f")
    spell.upsert(r)

    out_dbc = os.path.join(A, "mpq", "DBFilesClient"); os.makedirs(out_dbc, exist_ok=True)
    for n, d in (("GameObjectDisplayInfo", go), ("CreatureModelData", cmd), ("CreatureDisplayInfo", cdi),
                 ("ItemDisplayInfo", idi), ("Spell", spell), ("SpellIcon", sicon)):
        d.save(os.path.join(out_dbc, n + ".dbc"))
        shutil.copy(os.path.join(out_dbc, n + ".dbc"), os.path.join(DBC_SRV, n + ".dbc"))
    json.dump(ids, open(os.path.join(A, "wl_ids.json"), "w"), indent=1)

    files = {}
    root = os.path.join(A, "mpq")
    for dp, dn, fn in os.walk(root):
        for f in fn:
            full = os.path.join(dp, f)
            files[os.path.relpath(full, root).replace("/", "\\")] = open(full, "rb").read()
    out = os.path.join(A, "patch-3.MPQ")
    size = write_mpq(out, files)
    print("patch :", out, len(files), "fichiers,", size // 1024, "Kio ; ids :",
          {k: len(v) for k, v in ids.items() if isinstance(v, dict)})
    if install:
        shutil.copy(out, os.path.join(CLIENT, "patch-3.MPQ"))
        print("installe dans", CLIENT)

if __name__ == "__main__":
    main("--install" in sys.argv)
