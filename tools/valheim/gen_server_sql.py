r"""Contenu serveur et addon tires des donnees reelles de Valheim (prefabs lus par vh_dump_all.py) :
- server/sql/world/012_valheim_content.sql : catalogue des pieces du marteau (noms francais de Valheim, categories, couts,
  PV, materiau, station requise, extensions, points d'accroche), modeles Valheim des pieces et des objets, arbres/buches,
  roches et filons a frapper (creatures), ramassables de Valheim (GameObjects), TOUTES les recettes de Valheim realisables ici,
  outils de Valheim (palier, degats, durabilite), noms francais exacts de Valheim pour tous les objets.
- tools/client/addon/Wowlheim/WowlheimData.lua : le meme catalogue pour le menu du marteau (icones, categories).
Entrees : C:\Wowlheim\valheim_extract\{valheim_data.json, localization.txt}, C:\Wowlheim\wl_assets\{manifest,icons,wl_ids,colliders}.json (colliders : vh_colliders.py)
et C:\Wowlheim\data\wl_terrain\placements.json (positions d'apres le terrain, palier de zone : tools/resources/place_resources.py).
usage : python gen_server_sql.py"""
import csv, json, os, re, subprocess, zlib, math
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
VX = r"C:\Wowlheim\valheim_extract"
A = r"C:\Wowlheim\wl_assets"
MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"

D = json.load(open(os.path.join(VX, "valheim_data.json"), encoding="utf-8"))
P = D["prefabs"]
MAN = json.load(open(os.path.join(A, "manifest.json")))
ICONS = json.load(open(os.path.join(A, "icons.json")))
IDS = json.load(open(os.path.join(A, "wl_ids.json")))
# boites des colliders solides de Valheim, repere de la piece (vh_colliders.py) ; a defaut, bbox de rendu du manifeste
COLL = json.load(open(os.path.join(A, "colliders.json"))) if os.path.exists(os.path.join(A, "colliders.json")) else {}
LOC = {}
with open(os.path.join(VX, "localization.txt"), encoding="utf-8") as f:
    for r in csv.reader(f):
        if len(r) > 3: LOC[r[0]] = r[3] or r[1]

def fr(token):
    """Traduction francaise de Valheim ; les chaines composees (« $piece_forge $piece_upgrade – ... ») jeton par jeton."""
    if not token: return ""
    if "$" not in token: return LOC.get(token, token).replace("\xa0", " ")
    out = re.sub(r"\$(\w+)", lambda m: LOC.get(m.group(1), m.group(1)), token)
    return out.replace("\xa0", " ")

def mono(name, cls):
    v = P.get(name) or {}
    l = (v.get("monos") or {}).get(cls)
    return l[0] if l else None

def q(s):
    return "'" + str(s).replace("\\", "\\\\").replace("'", "''") + "'"

# --------------------------------------------------------------------------------------------- objets
ITEM = {  # prefab Valheim -> objet Wowlheim
    "Wood": 9200001, "Stone": 9200002, "Flint": 9200003, "Resin": 9200004, "DeerHide": 9200005, "LeatherScraps": 9200006,
    "HardAntler": 9200009, "FineWood": 9200011, "RoundLog": 9200012, "Copper": 9200013, "Tin": 9200014, "Bronze": 9200015,
    "TrollHide": 9200016, "GreydwarfEye": 9200019, "Iron": 9200021, "ElderBark": 9200022, "BoneFragments": 9200023,
    "SurtlingCore": 9200029, "Silver": 9200031, "Obsidian": 9200032, "WolfPelt": 9200033, "Crystal": 9200034,
    "BlackMetal": 9200041, "LinenThread": 9200043, "LoxPelt": 9200044,
    # nouveaux materiaux (pieces et recettes de Valheim qui les demandent)
    "Coal": 9200051, "Chain": 9200052, "BronzeNails": 9200053, "IronNails": 9200054, "Feathers": 9200055,
    "SharpeningStone": 9200056, "Tar": 9200057,
    # materiaux de passage de Valheim (butin de monstres) : Glande gelee, Noyau noir ; ramassable de la prairie : Champignon
    "FreezeGland": 9200039, "BlackCore": 9200049, "Mushroom": 9200082,
    # minerais (filons de Valheim) a fondre a la fonderie
    "CopperOre": 9200060, "TinOre": 9200061, "IronScrap": 9200062, "SilverOre": 9200063, "IronOre": 9200064,
    # materiaux existants (002) sous leur prefab Valheim
    "Entrails": 9200024, "Flax": 9200042,
    # materiaux des pieces du marteau ajoutees (plage 9200070-9200199 ; sources : tools/resources/rules.py, 003/004/006)
    "Raspberry": 9200070, "Dandelion": 9200071, "Blueberries": 9200072, "Thistle": 9200073, "Carrot": 9200074,
    "Guck": 9200075, "Bloodbag": 9200076, "WolfClaw": 9200077, "DragonTear": 9200078, "Cloudberry": 9200079, "Barley": 9200080,
    # haut fourneau (Smelter de blastfurnace : BlackMetalScrap -> BlackMetal) ; sources : tools/resources/rules.py
    "BlackMetalScrap": 9200081,
}
NEW_ITEMS = ["Coal", "Chain", "BronzeNails", "IronNails", "Feathers", "SharpeningStone", "Tar",
             "CopperOre", "TinOre", "IronScrap", "SilverOre", "IronOre",
             "Raspberry", "Dandelion", "Blueberries", "Thistle", "Carrot", "Guck", "Bloodbag", "WolfClaw", "DragonTear",
             "Cloudberry", "Barley", "BlackMetalScrap", "Mushroom"]
# palier, qualite et prix des materiaux definis dans le systeme de ressources (meme source que 002 / 004)
import sys as _sys
_sys.path.insert(0, os.path.join(REPO, "tools", "resources"))
import rules as RES_RULES
# outils : UNIQUEMENT ceux de Valheim realisables ici. Palier serveur lu dans le prefab (ItemDrop.m_shared.m_toolTier) :
# hache = m_toolTier (compare a TreeBase.m_minToolTier), pioche = m_toolTier + 1 (compare a MineRock.m_minToolTier + 1, build_rocks).
# Supprimes : 9201041/9201042 (« argent », n'existent pas dans Valheim), 9201052 (pioche en sombracier : bois d'Yggdrasil absent).
TOOL_PREFABS = {9201010: ("AxeStone", "axe"), 9201011: ("AxeFlint", "axe"), 9201021: ("AxeBronze", "axe"), 9201031: ("AxeIron", "axe"),
                9201051: ("AxeBlackMetal", "axe"), 9201012: ("PickaxeAntler", "pick"), 9201022: ("PickaxeBronze", "pick"),
                9201032: ("PickaxeIron", "pick")}
REMOVED_TOOLS = (9201041, 9201042, 9201052)

def _shared(pf):
    return mono(pf, "ItemDrop")["m_itemData"]["m_shared"]

TOOLS = {it: (pf, kind, int(_shared(pf)["m_toolTier"]) + (1 if kind == "pick" else 0)) for it, (pf, kind) in TOOL_PREFABS.items()}
STATION = {None: "", "piece_workbench": "workbench", "forge": "forge", "piece_stonecutter": "stonecutter",
           "piece_artisanstation": "artisan", "blackforge": "blackforge"}

def tool_damage(prefab, kind):
    sh = mono(prefab, "ItemDrop")["m_itemData"]["m_shared"]
    return float(sh["m_damages"]["m_chop" if kind == "axe" else "m_pickaxe"])

# --------------------------------------------------------------------------------------------- pieces
PIECE_IDS = {  # identifiants STABLES (pieces deja posees en base) : 1-83 = catalogue initial, 84+ = extension ; ajouter a la suite
    "wood_floor": 1, "woodwall": 2, "wood_roof": 3, "wood_pole2": 4, "fire_pit": 5, "piece_workbench": 6, "forge": 7,
    "piece_workbench_ext1": 8, "piece_workbench_ext2": 9, "forge_ext1": 10, "forge_ext2": 11, "forge_ext3": 12, "bed": 13,
    "bonfire": 14, "charcoal_kiln": 15, "forge_ext4": 16, "forge_ext5": 17, "forge_ext6": 18, "guard_stone": 19,
    "hearth": 20, "itemstand": 21, "piece_banner01": 22, "piece_bed02": 23, "piece_bench01": 24, "piece_chair": 25,
    "piece_chair02": 26, "piece_chest": 27, "piece_chest_wood": 28, "piece_groundtorch_wood": 29, "piece_logbench01": 30,
    "piece_sharpstakes": 31, "piece_stonecutter": 32, "piece_table": 33, "piece_table_round": 34, "piece_walltorch": 35,
    "piece_workbench_ext3": 36, "piece_workbench_ext4": 37, "portal_wood": 38, "rug_deer": 39, "rug_wolf": 40, "sign": 41,
    "smelter": 42, "stake_wall": 43, "stone_arch": 44, "stone_floor_2x2": 45, "stone_pile": 46, "stone_pillar": 47,
    "stone_stair": 48, "stone_wall_1x1": 49, "stone_wall_2x1": 50, "stone_wall_4x2": 51, "wood_beam": 52, "wood_beam_1": 53,
    "wood_beam_26": 54, "wood_beam_45": 55, "wood_door": 56, "wood_fence": 57, "wood_floor_1x1": 58, "wood_gate": 59,
    "wood_log_26": 60, "wood_log_45": 61, "wood_pole": 62, "wood_pole_log": 63, "wood_pole_log_4": 64, "wood_roof_45": 65,
    "wood_roof_icorner": 66, "wood_roof_icorner_45": 67, "wood_roof_ocorner": 68, "wood_roof_ocorner_45": 69,
    "wood_roof_top": 70, "wood_roof_top_45": 71, "wood_stack": 72, "wood_stair": 73, "wood_stepladder": 74,
    "wood_wall_half": 75, "wood_wall_log": 76, "wood_wall_log_4x0.5": 77, "wood_wall_quarter": 78, "wood_wall_roof": 79,
    "wood_wall_roof_45": 80, "wood_wall_roof_45_upsidedown": 81, "wood_wall_roof_upsidedown": 82, "wood_window": 83,
    "wood_wall_roof_top": 84, "wood_wall_roof_top_45": 85, "wood_log_67": 86, "wood_fence_gate": 87, "stone_fence": 88,
    "wood_dragon1": 89, "woodiron_pole": 90, "woodiron_beam": 91, "woodiron_beam_26": 92, "woodiron_beam_45": 93,
    "woodiron_beam_67": 94, "iron_floor_1x1_v2": 95, "iron_floor_2x2": 96, "iron_wall_1x1": 97, "iron_wall_2x2": 98,
    "iron_grate": 99, "crystal_wall_1x1": 100, "darkwood_decowall": 101, "darkwood_pole": 102, "darkwood_pole4": 103,
    "darkwood_beam": 104, "darkwood_beam4x4": 105, "darkwood_beam_26": 106, "darkwood_beam_45": 107, "darkwood_arch": 108,
    "darkwood_roof": 109, "darkwood_roof_45": 110, "darkwood_roof_icorner": 111, "darkwood_roof_icorner_45": 112,
    "darkwood_roof_ocorner": 113, "darkwood_roof_ocorner_45": 114, "darkwood_roof_top": 115, "darkwood_roof_top_45": 116,
    "darkwood_gate": 117, "darkwood_raven": 118, "darkwood_wolf": 119, "piece_artisanstation": 120,
    "piece_spinningwheel": 121, "blastfurnace": 122, "piece_throne01": 123, "piece_throne02": 124, "piece_chair03": 125,
    "piece_table_oak": 126, "piece_chest_private": 127, "piece_chest_blackmetal": 128, "ArmorStand": 129, "itemstandh": 130,
    "piece_groundtorch": 131, "piece_groundtorch_blue": 132, "piece_groundtorch_green": 133, "piece_brazierfloor01": 134,
    "piece_brazierfloor02": 135, "piece_brazierceiling01": 136, "rug_fur": 137, "rug_straw": 138, "piece_banner02": 139,
    "piece_banner03": 140, "piece_banner04": 141, "piece_banner05": 142, "piece_banner06": 143, "piece_banner07": 144,
    "piece_banner08": 145, "piece_banner09": 146, "piece_banner10": 147, "piece_banner11": 148,
    "piece_CelebrationGarland": 149, "piece_FairylightGarland": 150, "piece_ArcheryTarget": 151, "wood_fine_stack": 152,
    "wood_core_stack": 153, "flint_pile": 154, "bar_tin_stack": 155, "bar_copper_stack": 156, "bar_bronze_stack": 157,
    "bar_iron_stack": 158, "bar_silver_stack": 159, "bar_blackmetal_stack": 160, "coal_pile": 161, "bone_stack": 162,
}
KEEP_IDS = PIECE_IDS

def piece_kind(name, piece):
    n = name.lower()
    if mono(name, "StationExtension"): return "extension"
    if name in ("charcoal_kiln", "smelter"): return name
    # autres machines Smelter (haut fourneau, rouet) : nom du prefab sans « piece_ » (kind : VARCHAR(16))
    if mono(name, "Smelter"): return name[6:] if name.startswith("piece_") else name
    if mono(name, "CraftingStation"):
        return STATION.get(name, name)   # meme nom que Piece.m_craftingStation des pieces qui l'exigent (FindStationInRange)
    if mono(name, "Fireplace") or "fire" in n or "torch" in n or "hearth" in n: return "fire"
    if "roof" in n: return "roof"
    if "floor" in n or "stair" in n or "ladder" in n: return "floor"
    if any(k in n for k in ("pole", "beam", "pillar", "log_")): return "pillar"
    if "archery" not in n and any(k in n for k in ("wall", "door", "gate", "window", "fence", "stake", "arch", "grate")): return "wall"
    return "furniture" if piece["m_category"] == 4 else "misc"

def piece_box(name, m):
    """(sx, sy, sz) de la boite logique : colliders non-triggers de Valheim (vh_colliders.py) plutot que la bbox de rendu
    (effets, particules, LOD, decors sans collider la gonflent). Le serveur centre la boite en x/y sur la piece et la pose
    sur sa base (Geometry.cpp BoxOf) : largeur/profondeur = etendue des colliders, hauteur = sommet des colliders au-dessus
    de la base du modele (le dessus d'un plancher reste a sa hauteur visible). Repli : bbox de rendu."""
    c = COLL.get(name)
    if c and c.get("lo"):
        lo, hi = c["lo"], c["hi"]
        return round(hi[0] - lo[0], 3), round(hi[1] - lo[1], 3), round(hi[2], 3), c["src"]
    lo, hi = m["bbox"]
    return round(hi[0] - lo[0], 3), round(hi[1] - lo[1], 3), round(hi[2] - lo[2], 3), "render"

def main():
    pieces = []
    next_id = max(KEEP_IDS.values()) + 1
    for name in sorted(MAN, key=lambda n: (KEEP_IDS.get(n, 999), n)):
        m = MAN[name]
        if m["kind"] != "piece": continue
        pc = mono(name, "Piece")
        if not pc: continue
        res = [(r["m_resItem"]["name"], r["m_amount"], r["m_recover"]) for r in pc["m_resources"] if r["m_resItem"] and r["m_amount"] > 0]
        if any(r[0] not in ITEM for r in res):
            print("  piece ignoree (materiau sans equivalent) :", name, [r[0] for r in res if r[0] not in ITEM])
            continue
        pid = KEEP_IDS.get(name)
        if pid is None:
            pid = next_id; next_id += 1
        w = mono(name, "WearNTear") or {}
        ext = mono(name, "StationExtension")
        sx, sy, sz, box_src = piece_box(name, m)
        cs = pc.get("m_craftingStation")
        pieces.append({
            "id": pid, "prefab": name, "name": fr(pc["m_name"]), "desc": fr(pc["m_description"]),
            "category": pc["m_category"], "kind": piece_kind(name, pc), "station": STATION.get(cs["name"] if cs else None, cs and cs["name"]),
            "health": int(w.get("m_health", 100)), "material": int(w.get("m_materialType", 0)),
            "supports": 1 if w.get("m_supports", 1) else 0,
            "sx": sx, "sy": sy, "sz": sz, "box_src": box_src,
            "ext_station": STATION.get(ext["m_craftingStation"]["name"], "") if ext and ext.get("m_craftingStation") else "",
            "ext_distance": float(ext.get("m_maxStationDistance", 5)) if ext else 5.0,
            "ext_stack": 1 if ext and ext.get("m_stack") else 0,
            "costs": [(ITEM[r[0]], r[1]) for r in res], "icon": ICONS.get(name, ""),
            "go": 9110000 + pid, "display": IDS["go"][name], "snaps": m.get("snaps", []),
            "comfort": pc.get("m_comfort", 0),
        })
    out = []
    w = out.append
    w("-- GENERE par tools/valheim/gen_server_sql.py depuis les prefabs de Valheim : NE PAS EDITER A LA MAIN. Rejouable.")
    w("-- Assets et donnees de Valheim : usage prive, non distribue (cahier des charges, Droits).")
    w("SET NAMES utf8mb4;")
    # schema etendu du catalogue (001 recree la table a chaque passage d'apply_sql.py)
    w("ALTER TABLE `wowlheim_piece_template` ADD COLUMN `prefab` VARCHAR(64) NOT NULL DEFAULT '', ADD COLUMN `category` TINYINT UNSIGNED NOT NULL DEFAULT 0,"
      " ADD COLUMN `icon` VARCHAR(64) NOT NULL DEFAULT '', ADD COLUMN `station` VARCHAR(16) NOT NULL DEFAULT '' COMMENT 'Piece.m_craftingStation',"
      " ADD COLUMN `description` VARCHAR(255) NOT NULL DEFAULT '';")
    w("DROP TABLE IF EXISTS `wowlheim_piece_snap`;")
    w("CREATE TABLE `wowlheim_piece_snap` (`piece_id` INT UNSIGNED NOT NULL, `idx` TINYINT UNSIGNED NOT NULL, `x` FLOAT NOT NULL, `y` FLOAT NOT NULL, `z` FLOAT NOT NULL,"
      " PRIMARY KEY (`piece_id`,`idx`)) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='points d accroche Valheim ($hud_snappoint), repere de la piece';")
    w("DELETE FROM `wowlheim_piece_cost`; DELETE FROM `wowlheim_piece_template`;")
    w("DELETE FROM `gameobject_template` WHERE `entry` BETWEEN 9100001 AND 9100099 OR `entry` BETWEEN 9110000 AND 9119999;")
    for p in pieces:
        if p["kind"] == "fire":
            w(f"INSERT INTO `gameobject_template` (`entry`,`type`,`displayId`,`name`,`faction`,`size`,`data0`,`data1`,`data2`) SELECT {p['go']}, `type`, {p['display']}, {q(p['name'])}, `faction`, 1, `data0`, `data1`, `data2` FROM `gameobject_template` WHERE `entry` = 29784;")
        else:
            # type 10 (goober) : cliquable -> demolition / reparation au marteau (GameObject::Use)
            w(f"INSERT INTO `gameobject_template` (`entry`,`type`,`displayId`,`name`,`size`) VALUES ({p['go']}, 10, {p['display']}, {q(p['name'])}, 1);")
        w("INSERT INTO `wowlheim_piece_template` (`id`,`name`,`gameobject_entry`,`material`,`max_health`,`supports`,`requires_workbench`,`kind`,`sx`,`sy`,`sz`,"
          "`ext_station`,`ext_distance`,`ext_stack`,`prefab`,`category`,`icon`,`station`,`description`) VALUES "
          f"({p['id']}, {q(p['name'])}, {p['go']}, {p['material']}, {p['health']}, {p['supports']}, {1 if p['station'] == 'workbench' else 0}, {q(p['kind'])}, "
          f"{max(p['sx'], 0.1)}, {max(p['sy'], 0.1)}, {max(p['sz'], 0.1)}, {q(p['ext_station'])}, {p['ext_distance']}, {p['ext_stack']}, {q(p['prefab'])}, "
          f"{p['category']}, {q(p['icon'])}, {q(p['station'])}, {q(p['desc'][:255])});")
        for it, n in p["costs"]:
            w(f"INSERT INTO `wowlheim_piece_cost` (`piece_id`,`item_id`,`count`) VALUES ({p['id']}, {it}, {n});")
        for i, s in enumerate(p["snaps"]):
            w(f"INSERT INTO `wowlheim_piece_snap` VALUES ({p['id']}, {i}, {s[0]}, {s[1]}, {s[2]});")

    # ---------------- objets : nouveaux materiaux, outil en pierre, affichages Valheim (icones + modeles en main)
    w("DELETE FROM `item_template` WHERE `entry` BETWEEN 9200051 AND 9200069 OR `entry` = 9201010;")
    w("DELETE FROM `item_template` WHERE `entry` IN (" + ",".join(map(str, REMOVED_TOOLS)) + ");")
    w("DELETE FROM `item_template` WHERE `entry` BETWEEN 9200070 AND 9200199;")
    for pf in NEW_ITEMS:
        sh = mono(pf, "ItemDrop")["m_itemData"]["m_shared"]
        rm = RES_RULES.MAT.get(ITEM[pf])
        if rm:
            # materiau du systeme de ressources : palier (niveau d'objet), qualite et prix de rules.py, pile de Valheim
            lvl = max(1, {t: lo for t, _n, lo, _h in RES_RULES.TIERS}[rm["tier"]])
            w(f"INSERT INTO `item_template` (`entry`,`class`,`subclass`,`name`,`displayid`,`Quality`,`BuyCount`,`BuyPrice`,`SellPrice`,`InventoryType`,`ItemLevel`,`RequiredLevel`,`stackable`,`delay`,`description`,`Material`,`bonding`)"
              f" VALUES ({ITEM[pf]},7,11,{q(fr(sh['m_name']))},{rm['display']},{rm['quality']},1,{RES_RULES.buy_price(rm)},{RES_RULES.sell_price(rm)},0,{lvl},0,{min(200, max(1, int(sh.get('m_maxStackSize', 50))))},0,'Wowlheim',0,0);")
            continue
        w(f"INSERT INTO `item_template` (`entry`,`class`,`subclass`,`name`,`displayid`,`Quality`,`BuyCount`,`BuyPrice`,`SellPrice`,`InventoryType`,`ItemLevel`,`RequiredLevel`,`stackable`,`delay`,`description`,`Material`,`bonding`)"
          f" VALUES ({ITEM[pf]},7,11,{q(fr(sh['m_name']))},7375,1,1,120,12,0,15,0,{min(200, max(1, int(sh.get('m_maxStackSize', 50))))},0,'Wowlheim',0,0);")
    w("CREATE TEMPORARY TABLE `tmp_axe` SELECT * FROM `item_template` WHERE `entry` = 9201011;")
    w(f"UPDATE `tmp_axe` SET `entry` = 9201010, `name` = {q(fr('item_axe_stone'))};")
    w("INSERT INTO `item_template` SELECT * FROM `tmp_axe`; DROP TEMPORARY TABLE `tmp_axe`;")
    for k, v in IDS["idi"].items():
        if int(k) in REMOVED_TOOLS: continue
        w(f"UPDATE `item_template` SET `displayid` = {v} WHERE `entry` = {int(k)};")
    w(f"UPDATE `item_template` SET `name` = {q(fr('item_hammer'))}, `sheath` = 3 WHERE `entry` = 9201100;")
    # durabilite du marteau (ItemDrop m_maxDurability) : usee a chaque pose / demolition (Player.GetPlaceDurability) et reparation
    # (m_useDurabilityDrain), reparable a l'etabli (Recipe_Hammer sans station -> m_repairStation = piece_workbench)
    hs = _shared("Hammer")
    # constantes du serveur (ValheimSkills.cpp WearHammer : 1 - m_placementDurabilityMax x facteur ; BuildPlacement.cpp : -1 par reparation)
    assert hs["m_useDurability"] and float(hs["m_useDurabilityDrain"]) == 1.0 and float(hs["m_placementDurabilityMax"]) == 0.5, hs
    w(f"UPDATE `item_template` SET `MaxDurability` = {int(hs['m_maxDurability'])} WHERE `entry` = 9201100;")
    w("UPDATE `item_template` SET `sheath` = 3 WHERE `entry` BETWEEN 9201010 AND 9201099;")
    # noms de Valheim pour les outils qui en ont un (les outils d'argent n'existent pas dans Valheim)
    for it, (pf, kind, tier) in TOOLS.items():
        sh = _shared(pf)
        # durabilite de Valheim (m_maxDurability) : reparable a l'etabli / a la forge (Recipe.m_repairStation) ; aucun niveau requis
        w(f"UPDATE `item_template` SET `name` = {q(fr(sh['m_name']))}, `MaxDurability` = {int(sh['m_maxDurability'])}, `RequiredLevel` = 0 WHERE `entry` = {it};")
    # sort de pose (meme definition que dans le Spell.dbc du patch client, gen_client_patch.py) : CMaNGOS lit spell_template.
    # Pose continue facon Valheim : aucun delai -> Category/RecoveryTime/CategoryRecoveryTime = 0, StartRecoveryCategory/Time = 0
    # (pas de GCD 133), instantane ; le marteau utilise spelltrigger 5 (ITEM_SPELLTRIGGER_ON_NO_DELAY_USE : pas de delai
    # d'equipement de 30 s, Player::ApplyEquipCooldown)
    w("DELETE FROM `spell_template` WHERE `Id` = 40001;")
    w("CREATE TEMPORARY TABLE `tmp_sp` SELECT * FROM `spell_template` WHERE `Id` = 1543;")
    w("UPDATE `tmp_sp` SET `Id` = 40001, `School` = 0, `Category` = 0, `Attributes` = 0, `AttributesEx` = 0, `AttributesEx2` = 0, `AttributesEx3` = 0, `AttributesEx4` = 0, `InterruptFlags` = 0, `Targets` = 64,"
      " `CastingTimeIndex` = 1, `RecoveryTime` = 0, `CategoryRecoveryTime` = 0, `MaxLevel` = 0, `BaseLevel` = 0, `SpellLevel` = 0, `DurationIndex` = 0,"
      " `ManaCost` = 0, `RangeIndex` = 3, `Effect1` = 76, `Effect2` = 0, `EffectImplicitTargetA1` = 28, `EffectImplicitTargetA2` = 0, `EffectRadiusIndex1` = 7,"
      " `EffectRadiusIndex2` = 0, `EffectApplyAuraName1` = 0, `EffectApplyAuraName2` = 0, `EffectMiscValue1` = 9110001, `EffectMiscValue2` = 0, `SpellVisual` = 0,"
      " `SpellIconID` = 3000, `SpellName` = 'Construire', `StartRecoveryCategory` = 0, `StartRecoveryTime` = 0, `SpellFamilyName` = 0;")
    w("INSERT INTO `spell_template` SELECT * FROM `tmp_sp`; DROP TEMPORARY TABLE `tmp_sp`;")
    # marteau : utilisation (spelltrigger 0, le seul que le client 1.12 propose a UseInventoryItem ; 5 le rend inutilisable, constate en jeu)
    # sans delai d equipement : ITEM_FLAG_NO_EQUIPCOOLDOWN (0x80, Player::ApplyEquipCooldown)
    # marteau : utilisation = sort de pose a cible au sol (40001, patch client) -> cercle de ciblage, pose au point clique
    w("UPDATE `item_template` SET `spellid_1` = 40001, `spelltrigger_1` = 0, `Flags` = `Flags` | 128, `spellcharges_1` = 0, `spellcooldown_1` = 0, `spellcategory_1` = 0, `spellcategorycooldown_1` = 0 WHERE `entry` = 9201100;")
    # noms francais de Valheim pour les materiaux
    # noms francais EXACTS et taille de pile de Valheim pour TOUS les materiaux
    for pf, it in ITEM.items():
        sh = (mono(pf, "ItemDrop") or {}).get("m_itemData", {}).get("m_shared", {})
        assert sh.get("m_name"), ("objet sans nom de Valheim", pf)
        w(f"UPDATE `item_template` SET `name` = {q(fr(sh['m_name']))}, `stackable` = {min(200, max(1, int(sh.get('m_maxStackSize', 50))))} WHERE `entry` = {it};")
    w("DROP TABLE IF EXISTS `wowlheim_tool`;")
    w("CREATE TABLE `wowlheim_tool` (`item_id` INT UNSIGNED NOT NULL PRIMARY KEY, `kind` VARCHAR(8) NOT NULL COMMENT 'axe | pick', `tier` TINYINT UNSIGNED NOT NULL DEFAULT 1,"
      " `damage` FLOAT NOT NULL DEFAULT 0 COMMENT 'Valheim m_damages.m_chop (hache) / m_pickaxe (pic)') ENGINE=InnoDB DEFAULT CHARSET=utf8;")
    for it, (pf, kind, tier) in sorted(TOOLS.items()):
        w(f"INSERT INTO `wowlheim_tool` (`item_id`,`kind`,`tier`,`damage`) VALUES ({it}, {q(kind)}, {tier}, {tool_damage(pf, kind)});")

    # ---------------- recettes : UNIQUEMENT les Recipe_* de Valheim (actives) dont la sortie et tous les ingredients existent ici
    # (station, niveau de station m_minStationLevel, quantite produite de Valheim). Toute autre recette est supprimee (dont celles
    # inventees par la premiere version : outils d'argent, bois precieux/robuste, silex, bouts de cuir, toile de lin a l'etabli).
    w("ALTER TABLE `wowlheim_recipe` MODIFY `station` VARCHAR(16) NOT NULL DEFAULT '' COMMENT 'vide = sans station (Valheim : fabrication a la main)';")
    w("DELETE FROM `wowlheim_recipe_ingredient`; DELETE FROM `wowlheim_recipe`;")
    out_items = dict(ITEM)
    out_items["Hammer"] = 9201100
    for it, (pf, kind, tier) in TOOLS.items():
        out_items[pf] = it
    recipes = []
    for r in D["recipes"]:
        it = r.get("m_item") or {}
        pf = it.get("name")
        if not r.get("m_enabled", 1) or pf not in out_items: continue
        ings = [(x["m_resItem"]["name"], x["m_amount"]) for x in r["m_resources"] if x["m_resItem"] and x["m_amount"] > 0
                and not x["m_resItem"]["name"].startswith("Upgrader")]
        missing = [i[0] for i in ings if i[0] not in ITEM]
        if missing:
            print("  recette de Valheim non realisable ici :", r["m_Name"], "(manque", missing, ")")
            continue
        st = (r.get("m_craftingStation") or {}).get("name")
        if st not in STATION:
            print("  recette de Valheim non realisable ici :", r["m_Name"], "(station", st, ")")
            continue
        recipes.append((r["m_Name"], pf, out_items[pf], STATION[st], max(1, r.get("m_minStationLevel", 1)), r.get("m_amount", 1), ings))
    for rname, pf, out_item, st, lvl, amount, ings in sorted(recipes):
        rid = RECIPE_IDS[rname]                 # identifiant stable (KeyError = nouvelle recette : lui donner un id dans RECIPE_IDS)
        nm = fr(_shared(pf)["m_name"])
        if amount > 1:
            nm = f"{nm} x{amount}"
        w(f"INSERT INTO `wowlheim_recipe` (`id`,`name`,`station`,`output_item`,`output_count`,`min_station_level`) VALUES ({rid}, {q(nm)}, {q(st)}, {out_item}, {amount}, {lvl});")
        RECIPES_LUA.append((rid, nm, out_item, amount, st))
        for i, n in ings:
            w(f"INSERT INTO `wowlheim_recipe_ingredient` VALUES ({rid}, {ITEM[i]}, {n});")
    RECIPES_OUT[:] = [(RECIPE_IDS[r[0]], r[0], fr(_shared(r[1])["m_name"]), r[3], r[4], r[5], 0, r[6]) for r in sorted(recipes)]
    # charbon : produit par le four a charbon pose (Smelter du prefab charcoal_kiln, server/Wowlheim/Smelter.cpp) ;
    # l'ancienne recette approchee 214 (1 Bois -> 1 Charbon a la commande) est retiree
    build_smelters(w)
    # coffres, portes, lits : composants Container / Door / Bed des pieces du catalogue (server/Wowlheim/Pieces.cpp)
    build_piece_use(w, pieces)

    # ---------------- arbres et buches : creatures a abattre a la hache
    trees = build_trees(w)
    picks = build_pickables(w)
    open(os.path.join(REPO, "server", "sql", "world", "012_valheim_content.sql"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    write_lua(pieces)
    print("pieces :", len(pieces), "; creatures-ressources :", trees, "; ramassables :", picks)
    print("recettes :")
    for rid, rname, nm, st, lvl, amount, _f, ings in sorted(RECIPES_OUT):
        print("  %3d %-24s %-28s station %-12s niveau %d" % (rid, rname, nm, st or "(a la main)", lvl))
    print("outils :")
    for it, (pf, kind, tier) in sorted(TOOLS.items()):
        sh = _shared(pf)
        print("  %d %-26s %-4s palier serveur %d (Valheim m_toolTier %d) degats %s durabilite %d" % (
            it, fr(sh["m_name"]), kind, tier, sh["m_toolTier"], tool_damage(pf, kind), sh["m_maxDurability"]))

# identifiants STABLES des recettes (nom de l'asset Recipe_* de Valheim) ; 99-106/201/210-213 = identifiants deja en base
RECIPE_IDS = {"Recipe_Hammer": 99, "Recipe_AxeStone": 100, "Recipe_AxeFlint": 101, "Recipe_PickaxeAntler": 102, "Recipe_AxeBronze": 103,
              "Recipe_PickaxeBronze": 104, "Recipe_AxeIron": 105, "Recipe_PickaxeIron": 106, "Recipe_AxeBlackMetal": 109,
              "Recipe_Bronze": 201, "Recipe_Bronze5": 202, "Recipe_BronzeNails": 210, "Recipe_IronNails": 211,
              "Recipe_SharpeningStone": 213}
RECIPES_OUT = []
RECIPES_LUA = []   # (id, nom serveur, objet produit, quantite, station) -> WowlheimData.recipes (noms des annonces « Nouvelle recette »)

TREE_SPECIES = {  # prefab arbre -> (buche, demi-buche, souche, butin direct (objet, chance, min, max))
    "Beech1": ("beech_log", "beech_log_half", "Beech_Stub", ("Resin", 0.31, 1, 2)),
    "FirTree": ("FirTree_log", "FirTree_log_half", "FirTree_Stub", ("Resin", 0.2, 1, 1)),
    "Pinetree_01": ("PineTree_log", "PineTree_log_half", "Pinetree_01_Stub", ("Resin", 0.4, 1, 2)),
    "Birch1": ("Birch_log", "Birch_log_half", "BirchStub", ("Resin", 0.2, 1, 1)),
    "Oak1": ("Oak_log", "Oak_log_half", "OakStub", ("Resin", 0.3, 1, 2)),
    # arbre ancien du marais : le tronc (SwampTree1_log, sans m_subLogPrefab) se brise directement en Bois / Ecorce ancienne
    "SwampTree1": ("SwampTree1_log", None, "SwampTree1_Stub", None),
}
TREE_NAMES = {"Beech1": "prop_beech", "FirTree": "prop_fir", "Pinetree_01": "prop_pine", "Birch1": "prop_birch", "Oak1": "prop_oak",
              "SwampTree1": "prop_ancienttree"}
# placement : types de tools/resources/rules.py PLACEMENTS (palier de zone, berges) -> prefabs de Valheim ponderes
PLACEMENTS = {pl["key"]: pl for pl in RES_RULES.PLACEMENTS}
ROCK_PREFABS = sorted({pf for pl in RES_RULES.PLACEMENTS if pl["kind"] == "creature" for pf, _w in pl["prefabs"] if pf not in TREE_SPECIES})
# ramassables -> gameobject_template (identifiants STABLES : en ajouter a la suite)
PICK_IDS = {"BlueberryBush": 9130001, "CloudberryBush": 9130002, "Pickable_Barley_Wild": 9130003, "Pickable_Branch": 9130004,
            "Pickable_Dandelion": 9130005, "Pickable_Flax_Wild": 9130006, "Pickable_Flint": 9130007, "Pickable_MountainCaveCrystal": 9130008,
            "Pickable_Mushroom": 9130009, "Pickable_Stone": 9130010, "Pickable_TarBig": 9130011, "Pickable_Thistle": 9130012,
            "RaspberryBush": 9130013}
PICKABLE_PREFABS = sorted({pf for pl in RES_RULES.PLACEMENTS if pl["kind"] == "pickable" for pf, _w in pl["prefabs"]}, key=lambda pf: PICK_IDS[pf])
# roche placee -> prefab que Valheim place REELLEMENT (meme table que build_assets.VISUAL) : les anciens MineRock_Copper / _Stone /
# _Iron (composant MineRock) sont des prototypes inutilises du jeu ; le visuel ET les stats viennent du prefab du monde.
ROCK_SOURCE = {"MineRock_Copper": "rock4_copper", "MineRock_Stone": "rock4_coast", "MineRock_Iron": "mudpile"}
# Un prefab du monde intact (Destructible, 1 PV, m_spawnWhenDestroyed) se brise au premier coup en MineRock5 « *_frac » : PV, palier et
# DropTable PAR ZONE ; nombre de zones = colliders actifs du prefab *_frac (MineRock5.Awake : une HitArea par Collider de
# GetComponentsInChildren<Collider>()), ne gardant que celles qui depassent du sol (reachable_areas) -- jamais les sommets du visuel.
ROCK_NAMES = {"MineRock_Stone": "Rocher", "Rock_4": "Pierre", "MineRock_Copper": "Gisement de cuivre", "MineRock_Tin": "Gisement d'étain",
              "MineRock_Iron": "Tas de boue", "MineRock_Obsidian": "Obsidienne", "silvervein": None}
PICK_GO_BASE = 9130001                      # gameobject_template des ramassables
PICK_GUID_MIN, PICK_GUID_MAX = 8100001, 8199999   # trou libre sous tout le contenu ; le serveur numérote les pièces posées à max(guid)+1, donc toujours au-dessus
PLACEMENTS_JSON = RES_RULES.PLACEMENTS_JSON
# Valheim : le filon donne le minerai (objets 9200060+), fondu ensuite a la fonderie (build_smelters). Plus de raccourci minerai -> metal.
ORE = {"IronOre": "IronScrap"}   # modèle mudpile (tas de boue de Valheim) : il donne de la Ferraille, fondue en Fer

# SmokeSpawner des stations (enfant « _enabled/SmokeSpawner » du prefab : m_LocalPosition Unity (x, y haut, z), m_testRadius),
# lu dans les bundles (absent de valheim_data.json, qui ne garde que les composants de la racine) : voir docs/VALHEIM_RULES.md §9
# prefabs a composant Smelter -> SmokeSpawner (enfant « _enabled/SmokeSpawner ») : position locale Unity (relative a la racine du
# prefab) et m_testRadius, lus par script UnityPy (docs/VALHEIM_RULES.md 9.1) ; rouet : m_smokeSpawner nul -> rayon 0 (jamais bloque)
SMOKE = {"smelter": ((0.0, 4.58, 0.0), 0.75), "charcoal_kiln": ((0.0, 3.48, 0.0), 0.75),
         "blastfurnace": ((0.0, 5.318, 0.652), 0.75), "piece_spinningwheel": ((0.0, 0.0, 0.0), 0.0)}

def smelter_kind(prefab):
    return piece_kind(prefab, None)          # meme kind que wowlheim_piece_template (smelter, charcoal_kiln, blastfurnace, spinningwheel)

def build_smelters(w):
    """Fonderie, four a charbon, haut fourneau, rouet : composant Smelter des prefabs (valeurs de Valheim) -> wowlheim_smelter(_conversion)."""
    w("DROP TABLE IF EXISTS `wowlheim_smelter`;")
    w("CREATE TABLE `wowlheim_smelter` (`kind` VARCHAR(16) NOT NULL PRIMARY KEY COMMENT 'wowlheim_piece_template.kind', `name` VARCHAR(64) NOT NULL,"
      " `fuel_item` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'm_fuelItem', `max_ore` INT UNSIGNED NOT NULL COMMENT 'm_maxOre',"
      " `max_fuel` INT UNSIGNED NOT NULL COMMENT 'm_maxFuel', `fuel_per_product` INT UNSIGNED NOT NULL COMMENT 'm_fuelPerProduct',"
      " `sec_per_product` FLOAT NOT NULL COMMENT 'm_secPerProduct', `requires_roof` TINYINT UNSIGNED NOT NULL COMMENT 'm_requiresRoof',"
      " `spawn_stack` TINYINT UNSIGNED NOT NULL COMMENT 'm_spawnStack', `smoke_x` FLOAT NOT NULL, `smoke_y` FLOAT NOT NULL, `smoke_z` FLOAT NOT NULL,"
      " `smoke_radius` FLOAT NOT NULL COMMENT 'SmokeSpawner.m_testRadius') ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='composant Smelter de Valheim';")
    w("DROP TABLE IF EXISTS `wowlheim_smelter_conversion`;")
    w("CREATE TABLE `wowlheim_smelter_conversion` (`kind` VARCHAR(16) NOT NULL, `idx` TINYINT UNSIGNED NOT NULL, `from_item` INT UNSIGNED NOT NULL,"
      " `to_item` INT UNSIGNED NOT NULL, PRIMARY KEY (`kind`,`idx`)) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='Smelter.m_conversion (ordre de Valheim)';")
    for pf, ((ux, uy, uz), rad) in SMOKE.items():
        kind = smelter_kind(pf)
        sm = mono(pf, "Smelter")
        fuel = (sm.get("m_fuelItem") or {}).get("name")
        off = MAN[pf]["offset"]                   # recentrage du modele (build_assets.py)
        # Unity -> WoW (vh_mesh.U2W) : x WoW = z Unity, y WoW = -x Unity, z WoW = y Unity
        w(f"INSERT INTO `wowlheim_smelter` VALUES ({q(kind)}, {q(fr(sm['m_name']))}, {ITEM.get(fuel, 0) if fuel else 0}, {sm['m_maxOre']}, {sm['m_maxFuel']},"
          f" {sm['m_fuelPerProduct']}, {sm['m_secPerProduct']}, {1 if sm['m_requiresRoof'] else 0}, {1 if sm['m_spawnStack'] else 0},"
          f" {round(uz + off[0], 3)}, {round(-ux + off[1], 3)}, {round(uy + off[2], 3)}, {rad});")
        idx = 0
        for c in sm["m_conversion"]:
            a, b = (c.get("m_from") or {}).get("name"), (c.get("m_to") or {}).get("name")
            if a in ITEM and b in ITEM:           # BronzeScrap, CopperScrap, FlametalOreNew, GoldOre : objets absents du serveur
                w(f"INSERT INTO `wowlheim_smelter_conversion` VALUES ({q(kind)}, {idx}, {ITEM[a]}, {ITEM[b]});")
                idx += 1

def build_piece_use(w, pieces):
    """Pieces utilisables sans marteau : Container (m_width, m_height, m_privacy, m_checkGuardStone), Door (m_canNotBeClosed, m_keyItem,
    m_consumeKey, m_checkGuardStone), Bed -> wowlheim_piece_use (un composant par piece). Regles : docs/VALHEIM_RULES.md §14."""
    w("DROP TABLE IF EXISTS `wowlheim_piece_use`;")
    w("CREATE TABLE `wowlheim_piece_use` (`piece_id` INT UNSIGNED NOT NULL PRIMARY KEY COMMENT 'wowlheim_piece_template.id',"
      " `kind` VARCHAR(16) NOT NULL COMMENT 'container | door | bed', `name` VARCHAR(64) NOT NULL COMMENT 'm_name traduit',"
      " `width` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Container.m_width', `height` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Container.m_height',"
      " `privacy` TINYINT UNSIGNED NOT NULL DEFAULT 2 COMMENT 'Container.m_privacy : 0 Private, 1 Group, 2 Public',"
      " `check_guard` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'm_checkGuardStone', `can_not_be_closed` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Door.m_canNotBeClosed',"
      " `key_item` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Door.m_keyItem', `consume_key` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Door.m_consumeKey')"
      " ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='composants Container / Door / Bed de Valheim';")
    n = {"container": 0, "door": 0, "bed": 0}
    for p in pieces:
        pf = p["prefab"]
        c, d, b = mono(pf, "Container"), mono(pf, "Door"), mono(pf, "Bed")
        if c:
            w(f"INSERT INTO `wowlheim_piece_use` (`piece_id`,`kind`,`name`,`width`,`height`,`privacy`,`check_guard`) VALUES ({p['id']}, 'container',"
              f" {q(fr(c['m_name']) or p['name'])}, {int(c['m_width'])}, {int(c['m_height'])}, {int(c['m_privacy'])}, {1 if c['m_checkGuardStone'] else 0});")
            n["container"] += 1
        elif d:
            key = (d.get("m_keyItem") or {}).get("name")
            if key and key not in ITEM:
                print("  porte ignoree (cle sans equivalent) :", pf, key)
                continue
            w(f"INSERT INTO `wowlheim_piece_use` (`piece_id`,`kind`,`name`,`check_guard`,`can_not_be_closed`,`key_item`,`consume_key`) VALUES ({p['id']}, 'door',"
              f" {q(fr(d['m_name']) or p['name'])}, {1 if d['m_checkGuardStone'] else 0}, {1 if d['m_canNotBeClosed'] else 0}, {ITEM[key] if key else 0},"
              f" {1 if d['m_consumeKey'] else 0});")
            n["door"] += 1
        elif b:
            w(f"INSERT INTO `wowlheim_piece_use` (`piece_id`,`kind`,`name`) VALUES ({p['id']}, 'bed', {q(p['name'])});")
            n["bed"] += 1
    print("pieces utilisables :", n)

ROCK_STATS = {}   # prefab -> stats retenues (journal de generation, docs/RESOURCES.md « Roches »)

def total_rolls(areas, dmin, dmax, chance):
    """Nombre total de tirages d'une roche de `areas` zones : par zone, DropTable.GetDropList tire Random.Range(dmin, dmax + 1) objets
    avec la probabilite m_dropChance (sinon rien). Le serveur tire un entier uniforme [rolls_min, rolls_max] : bornes choisies pour la
    MEME moyenne et la MEME variance que la somme des zones de Valheim (une zone : rolls = [dmin, dmax] exactement)."""
    if areas == 1 and chance >= 1:
        return dmin, dmax
    m = (dmin + dmax) / 2.0
    eu2 = ((dmax - dmin + 1) ** 2 - 1) / 12.0 + m * m           # E[U^2], U uniforme entier [dmin, dmax]
    mean = areas * chance * m
    var = areas * (chance * eu2 - (chance * m) ** 2)
    h = ((12 * var + 1) ** 0.5 - 1) / 2                       # uniforme entiere de demi-largeur h : variance ((2h+1)^2-1)/12
    lo, hi = max(0, int(round(mean - h))), int(round(mean + h))
    return lo, max(lo, hi)

def reachable_areas(prefab):
    """Zones ATTEIGNABLES sans creuser : colliders du MineRock5 dont le point le plus haut depasse le sol (« hit_area_tops » de
    valheim_data.json, vh_dump.hit_areas : Unity y, racine du prefab = sol). Le M2 pose ici (build_assets.VISUAL : echelle
    uniforme 0,4 pour rock4_*, 1 pour mudpile / silvervein ; racine du modele = position de la creature = sol) garde ce plan :
    une echelle uniforme positive ne change pas le signe de la hauteur, donc le test « haut > 0 » est le meme dans les deux reperes.
    Dans Valheim la pioche creuse aussi le terrain et atteint les zones enterrees ; ici le terrain WoW ne se creuse pas."""
    tops = P[prefab]["hit_area_tops"]
    assert None not in tops, prefab
    return sum(1 for t in tops if t > 0)

def build_rocks(w, respawn):
    """Roches et filons de Valheim (MineRock / Destructible + DropOnDestroyed) : creatures frappees a la pioche."""
    rock_entry = {}
    rocks = ROCK_PREFABS
    w("DELETE FROM `creature_template` WHERE `Entry` BETWEEN 9300101 AND 9300199;")
    for i, n in enumerate(rocks):
        e = 9300101 + i
        rock_entry[n] = e
        src = ROCK_SOURCE.get(n, n)
        mr = mono(src, "MineRock5") or mono(src, "MineRock") or mono(src, "Destructible")
        dd = (mono(src, "MineRock5") or mono(src, "MineRock") or mono(src, "DropOnDestroyed") or {})
        areas = reachable_areas(src) if (mono(src, "MineRock5") or mono(src, "MineRock")) else 1
        intact = mono(src, "Destructible")
        frac = ((intact or {}).get("m_spawnWhenDestroyed") or {}).get("name")
        if frac and mono(frac, "MineRock5"):
            # prefab intact (Destructible) -> fracture MineRock5 : PV, palier et butin par zone, zones = colliders du *_frac
            assert intact["m_health"] <= 1 and intact["m_minToolTier"] <= mono(frac, "MineRock5")["m_minToolTier"], (n, src)
            mr = dd = mono(frac, "MineRock5")
            areas = reachable_areas(frac)
        assert areas >= 1, (n, src, frac)
        dw = dd.get("m_dropItems") or dd.get("m_dropWhenDestroyed") or {"m_dropMin": 0, "m_dropMax": 0, "m_drops": [], "m_dropChance": 1.0}
        hp, tier = mr["m_health"], mr["m_minToolTier"] + 1          # paliers de pioche du serveur = Valheim + 1
        # chaque zone a m_health PV et tire sa propre DropTable ; la creature regroupe les zones : PV et tirages cumules
        # zones « abattues » par coup : la pioche de Valheim frappe plusieurs zones (Attack.m_multiHit, arc de 120 deg) -> 3 zones
        # par coup [INFERE, non mesure] ; MineRock5 a soutien (m_supportCheck 1 : rock4_*_frac, silvervein_frac) : les zones qui
        # ne sont plus soutenues tombent aussi -> 8 zones par coup, CALAGE sur la duree de jeu de Valheim (~60 coups pour un gisement
        # au depart, decision de coordination 2026-10-26), non mesure. PV effectifs = PV d'une zone x zones / diviseur ; le butin
        # reste celui de toutes les zones comptees.
        div = 1 if areas <= 1 else (8 if mr.get("m_supportCheck") else 3)
        hp_total = hp * areas / div
        rmin, rmax = total_rolls(areas, dw["m_dropMin"], dw["m_dropMax"], dw.get("m_dropChance", 1.0))
        ROCK_STATS[n] = dict(src=src, frac=frac, hp_zone=hp, tier=tier, areas=areas, div=div, all_areas=P[frac or src].get("hit_areas", 1),
                             hp=int(hp_total), rolls=(rmin, rmax))
        GIVES[n] = set()
        disp = IDS["cdi"][n]
        nm = ROCK_NAMES.get(n) or fr(mr.get("m_name") or n)
        w("INSERT INTO `creature_template` (`Entry`,`Name`,`SubName`,`MinLevel`,`MaxLevel`,`DisplayId1`,`DisplayIdProbability1`,`Faction`,`Scale`,`CreatureType`,"
          "`InhabitType`,`RegenerateStats`,`UnitFlags`,`ExtraFlags`,`SpeedWalk`,`SpeedRun`,`HealthMultiplier`,`DamageMultiplier`,`ArmorMultiplier`,`ExperienceMultiplier`,"
          "`MinLevelHealth`,`MaxLevelHealth`,`MinMeleeDmg`,`MaxMeleeDmg`,`Armor`,`MeleeBaseAttackTime`,`UnitClass`,`LootId`,`SchoolImmuneMask`,`MechanicImmuneMask`,`MovementType`,`AIName`)"
          f" VALUES ({e}, {q(nm)}, '', 1, 1, {disp}, 100, 7, 1, 10, 1, 0, 0, {2 | 4 | 16 | 131072}, 0.01, 0.01, {round((hp_total + 0.2) / 42.0, 5)}, 0, 0, 0,"
          f" {int(hp_total)}, {int(hp_total)}, 0, 0, 0, 2000, 1, 0, 126, 2147483647, 0, 'NullAI');")
        lo, hi = MAN[n]["bbox"]
        w(f"INSERT INTO `creature_model_info` (`modelid`,`bounding_radius`,`combat_reach`,`gender`,`modelid_other_gender`,`modelid_alternative`) VALUES ({disp}, 0.8, {round(max(hi[0] - lo[0], hi[1] - lo[1]) / 2 + 1.0, 2)}, 2, 0, 0);")
        w(f"INSERT INTO `wowlheim_tree` VALUES ({e}, 'rock', {tier}, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'pick', {rmin}, {rmax});")
        agg = {}
        for x in dw["m_drops"]:
            if not x["m_item"]: continue
            it = ORE.get(x["m_item"]["name"], x["m_item"]["name"])
            if it not in ITEM: continue
            a = agg.setdefault(ITEM[it], [0.0, x["m_stackMin"], x["m_stackMax"]])
            a[0] += x["m_weight"]
        # DropTable.GetDropList : poids total nul (rock4_coast_frac : Stone poids 0) -> Random.Range(0, 0) = 0 <= 0 : 1re entree
        # toujours tiree. Le serveur (TreeMgr) ne tire rien si le total est nul : poids 1 sur la 1re entree, meme resultat.
        if agg and sum(v[0] for v in agg.values()) <= 0:
            agg[next(iter(agg))][0] = 1.0
        for it, (wgt, smin, smax) in agg.items():
            w(f"INSERT INTO `wowlheim_tree_drop` VALUES ({e}, {it}, {wgt}, {smin}, {smax});")
            if wgt > 0: GIVES[n].add(it)
    for n, st in ROCK_STATS.items():
        print("  roche %-18s <- %-18s zones %3d/%3d x %4.0f PV / %d -> %5d PV, palier %d, tirages %d-%d" % (
            n, st["frac"] or st["src"], st["areas"], st["all_areas"], st["hp_zone"], st["div"], st["hp"], st["tier"], st["rolls"][0], st["rolls"][1]))
    return rock_entry

def droptable(name):
    tl = mono(name, "TreeLog")
    dw = tl["m_dropWhenDestroyed"]
    items = [(x["m_item"]["name"], x["m_weight"], x["m_stackMin"], x["m_stackMax"]) for x in dw["m_drops"] if x["m_item"]]
    return dw["m_dropMin"], dw["m_dropMax"], items

def build_trees(w):
    entry = {}
    nxt = 9300001
    names = []
    for t, (log, half, stub, drop) in TREE_SPECIES.items():
        names += [t, log] + ([half] if half else [])
    for n in names:
        entry[n] = nxt; nxt += 1
    w("DROP TABLE IF EXISTS `wowlheim_tree`;")
    w("CREATE TABLE `wowlheim_tree` (`entry` INT UNSIGNED NOT NULL PRIMARY KEY, `kind` VARCHAR(8) NOT NULL, `min_tier` TINYINT UNSIGNED NOT NULL DEFAULT 0,"
      " `next_entry` INT UNSIGNED NOT NULL DEFAULT 0, `next_count` TINYINT UNSIGNED NOT NULL DEFAULT 0, `next_spacing` FLOAT NOT NULL DEFAULT 0,"
      " `next_distance` FLOAT NOT NULL DEFAULT 0, `stump_go` INT UNSIGNED NOT NULL DEFAULT 0, `stump_seconds` INT UNSIGNED NOT NULL DEFAULT 0,"
      " `drop_item` INT UNSIGNED NOT NULL DEFAULT 0, `drop_min` INT UNSIGNED NOT NULL DEFAULT 0, `drop_max` INT UNSIGNED NOT NULL DEFAULT 0,"
      " `drop_chance` FLOAT NOT NULL DEFAULT 0, `tool` VARCHAR(8) NOT NULL DEFAULT 'axe', `rolls_min` INT UNSIGNED NOT NULL DEFAULT 0,"
      " `rolls_max` INT UNSIGNED NOT NULL DEFAULT 0) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='TreeBase/TreeLog/MineRock/Destructible de Valheim';")
    w("DROP TABLE IF EXISTS `wowlheim_tree_drop`;")
    w("CREATE TABLE `wowlheim_tree_drop` (`entry` INT UNSIGNED NOT NULL, `item` INT UNSIGNED NOT NULL, `weight` FLOAT NOT NULL, `stack_min` INT UNSIGNED NOT NULL,"
      " `stack_max` INT UNSIGNED NOT NULL, PRIMARY KEY (`entry`,`item`)) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='DropTable de Valheim (m_drops)';")
    w("DELETE FROM `creature_loot_template` WHERE `entry` BETWEEN 9300001 AND 9300099;")
    w("DELETE FROM `creature_model_info` WHERE `modelid` BETWEEN 25000 AND 25999;")
    w("DELETE FROM `creature_template` WHERE `Entry` BETWEEN 9300001 AND 9300099;")
    w("DELETE FROM `gameobject_template` WHERE `entry` BETWEEN 9120001 AND 9120099;")
    respawn = 600
    for i, (t, (log, half, stub, drop)) in enumerate(TREE_SPECIES.items()):
        tb = mono(t, "TreeBase"); tl = mono(log, "TreeLog"); th = mono(half, "TreeLog") if half else None
        GIVES[t] = set()
        if drop and drop[0] in ITEM: GIVES[t].add(ITEM[drop[0]])
        stub_go = 9120001 + i
        w(f"INSERT INTO `gameobject_template` (`entry`,`type`,`displayId`,`name`,`size`) VALUES ({stub_go}, 5, {IDS['go'][stub]}, {q(fr('prop_stub') if 'prop_stub' in LOC else 'Souche')}, 1);")
        loglen = MAN[log]["bbox"][1][0] - MAN[log]["bbox"][0][0]
        halflen = MAN[half]["bbox"][1][0] - MAN[half]["bbox"][0][0] if half else 0
        tname = fr(TREE_NAMES[t])
        parts = [(t, "tree", tb["m_health"], tb["m_minToolTier"])]
        if half:
            parts += [(log, "log", tl["m_health"], tl["m_minToolTier"]), (half, "half", th["m_health"], th["m_minToolTier"])]
        else:
            parts += [(log, "half", tl["m_health"], tl["m_minToolTier"])]     # tronc final : se brise directement en butin
        for n, kind, hp, tier in parts:
            disp = IDS["cdi"][n]
            nm = {"tree": tname, "log": "Tronc", "half": "Bûche" if half else "Tronc"}[kind] + ("" if kind == "tree" else " (" + tname.lower() + ")")
            loot = 0   # Valheim : la buche brisee lache son bois au sol, ramasse automatiquement -> remis directement (wowlheim_tree_drop)
            w("INSERT INTO `creature_template` (`Entry`,`Name`,`SubName`,`MinLevel`,`MaxLevel`,`DisplayId1`,`DisplayIdProbability1`,`Faction`,`Scale`,`CreatureType`,"
              "`InhabitType`,`RegenerateStats`,`UnitFlags`,`ExtraFlags`,`SpeedWalk`,`SpeedRun`,`HealthMultiplier`,`DamageMultiplier`,`ArmorMultiplier`,`ExperienceMultiplier`,"
              "`MinLevelHealth`,`MaxLevelHealth`,`MinMeleeDmg`,`MaxMeleeDmg`,`Armor`,`MeleeBaseAttackTime`,`UnitClass`,`LootId`,`SchoolImmuneMask`,`MechanicImmuneMask`,`MovementType`,`AIName`)"
              f" VALUES ({entry[n]}, {q(nm)}, '', 1, 1, {disp}, 100, 7, 1, 10, 1, 0, 0, {2 | 4 | 16 | 131072}, 0.01, 0.01, {round((hp + 0.2) / 42.0, 5)}, 0, 0, 0,"
              f" {int(hp)}, {int(hp)}, 0, 0, 0, 2000, 1, {loot}, 126, 2147483647, 0, 'NullAI');")
            lo, hi = MAN[n]["bbox"]
            # Valheim : le coup touche n'importe quel point du collider ; ici portee de melee = demi-longueur pour une buche couchee
            reach = 3.0 if kind == "tree" else round((hi[0] - lo[0]) / 2 + 1.0, 2)
            reach_r = 1.0 if kind == "tree" else 0.8
            w(f"INSERT INTO `creature_model_info` (`modelid`,`bounding_radius`,`combat_reach`,`gender`,`modelid_other_gender`,`modelid_alternative`) VALUES ({disp}, {reach_r}, {reach}, 2, 0, 0);")
            if kind == "tree":
                di = ITEM.get(drop[0], 0) if drop else 0
                dmn, dmx, dch = (drop[2], drop[3], drop[1]) if drop else (0, 0, 0)
                w(f"INSERT INTO `wowlheim_tree` VALUES ({entry[n]}, 'tree', {tier}, {entry[log]}, 1, 0, {round(loglen / 2 + 1.0, 2)}, {stub_go}, {respawn}, {di}, {dmn}, {dmx}, {dch}, 'axe', 0, 0);")
            elif kind == "log":
                w(f"INSERT INTO `wowlheim_tree` VALUES ({entry[n]}, 'log', {tier}, {entry[half]}, 2, {round(halflen + 0.3, 2)}, 0, 0, 0, 0, 0, 0, 0, 'axe', 0, 0);")
            else:
                # TreeLog.m_dropWhenDestroyed : m_dropMin..m_dropMax tirages ponderes (meme mecanique que les roches)
                dmin, dmax, items = droptable(n)
                w(f"INSERT INTO `wowlheim_tree` VALUES ({entry[n]}, 'half', {tier}, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'axe', {dmin}, {dmax});")
                agg = {}
                for it, wgt, smin, smax in items:
                    if it not in ITEM: continue
                    a = agg.setdefault(ITEM[it], [0.0, smin, smax]); a[0] += wgt
                for it, (wgt, smin, smax) in agg.items():
                    w(f"INSERT INTO `wowlheim_tree_drop` VALUES ({entry[n]}, {it}, {wgt}, {smin}, {smax});")
                    if wgt > 0: GIVES[t].add(it)
    rock_entry = build_rocks(w, respawn)
    # placement : positions et types de placements.json (terrain du client, palier de ZONE) -> creatures de Valheim
    w("DELETE FROM `creature` WHERE `guid` BETWEEN 9600001 AND 9699999;")
    w("DELETE FROM `gameobject` WHERE `id` BETWEEN 9101001 AND 9101999;")
    n = 0
    vals = []
    for pl in read_placements():
        P_ = PLACEMENTS[pl["key"]]
        if P_["kind"] != "creature": continue
        species = pick_prefab(P_, pl["src"])
        ang = pl["o"]
        n += 1
        e = rock_entry.get(species) or entry[species]
        vals.append(f"({9600000 + n}, {e}, {pl['map']}, {pl['x']}, {pl['y']}, {pl['z']}, {ang}, {respawn}, {respawn}, 0, 0)")
    assert 9600000 + n <= 9699999
    for i in range(0, len(vals), 500):
        w("INSERT INTO `creature` (`guid`,`id`,`map`,`position_x`,`position_y`,`position_z`,`orientation`,`spawntimesecsmin`,`spawntimesecsmax`,`spawndist`,`MovementType`) VALUES\n" + ",\n".join(vals[i:i + 500]) + ";")
    return n

GIVES = {}   # prefab -> objets reellement obtenus (butin de Valheim) : controle de rules.PLACEMENTS[...]["gives"]

def read_placements():
    """placements.json (tools/resources/place_resources.py) ; « kind » = cle de rules.PLACEMENT. Controle : palier autorise."""
    d = json.load(open(PLACEMENTS_JSON, encoding="utf-8"))
    out = []
    for it in d["items"]:
        pl = PLACEMENTS[it["kind"]]
        assert it["tier"] in pl["tiers"], ("type hors de ses paliers", it)
        src = zlib.crc32(("%d|%.2f|%.2f" % (it["map"], it["x"], it["y"])).encode())
        out.append(dict(key=it["kind"], map=int(it["map"]), zone=int(it["zone"]), tier=int(it["tier"]), src=src,
                        x=round(it["x"], 2), y=round(it["y"], 2), z=round(it["z"], 2), o=float(it["o"])))
    return out

def pick_prefab(pl, src):
    """Prefab pondere (rules.PLACEMENTS[...]["prefabs"]), tire de facon deterministe d'apres la position."""
    tot = sum(wt for _p, wt in pl["prefabs"])
    r = zlib.crc32(("wlv%d" % src).encode()) % tot
    for pf, wt in pl["prefabs"]:
        if r < wt: return pf
        r -= wt
    return pl["prefabs"][-1][0]

def build_pickables(w):
    """Ramassables de Valheim (composant Pickable) : GameObject coffre (type 3) sans verrou, sans outil (absent de wowlheim_node),
    un clic -> butin = Pickable.m_itemPrefab x m_amount, disparait (data3 = 1) et revient apres m_respawnTimeMinutes."""
    w("DELETE FROM `gameobject` WHERE `id` BETWEEN %d AND %d;" % (PICK_GO_BASE, PICK_GO_BASE + 98))
    w("DELETE FROM `gameobject_loot_template` WHERE `entry` BETWEEN %d AND %d;" % (PICK_GO_BASE, PICK_GO_BASE + 98))
    w("DELETE FROM `gameobject_template` WHERE `entry` BETWEEN %d AND %d;" % (PICK_GO_BASE, PICK_GO_BASE + 98))
    # anciens noeuds GameObject aux modeles WoW : plus aucun controle d'outil a faire sur eux
    w("DELETE FROM `wowlheim_node` WHERE `gameobject_entry` BETWEEN 9101001 AND 9101999;")
    go_entry, respawn = {}, {}
    for pf in PICKABLE_PREFABS:
        pk = mono(pf, "Pickable")
        item = pk["m_itemPrefab"]["name"]
        assert item in ITEM, ("ramassable sans objet serveur", pf, item)
        e = PICK_IDS[pf]
        go_entry[pf] = e
        name = fr(pk.get("m_overrideName") or "") or fr(_shared(item)["m_name"])
        # Valheim : m_respawnTimeMinutes (0 = ne repousse jamais dans un monde a un joueur) ; serveur partage : 0 -> 240 min [ADAPTATION]
        mins = float(pk.get("m_respawnTimeMinutes") or 0) or 240.0
        respawn[pf] = int(mins * 60)
        GIVES[pf] = {ITEM[item]}
        w(f"INSERT INTO `gameobject_template` (`entry`,`type`,`displayId`,`name`,`faction`,`flags`,`size`,`data0`,`data1`,`data2`,`data3`,`data4`,`data5`)"
          f" VALUES ({e}, 3, {IDS['go'][pf]}, {q(name)}, 0, 0, 1, 0, {e}, 0, 1, 0, 0);")
        amt = int(pk.get("m_amount") or 1)
        w(f"INSERT INTO `gameobject_loot_template` (`entry`,`item`,`ChanceOrQuestChance`,`groupid`,`mincountOrRef`,`maxcount`,`condition_id`,`comments`)"
          f" VALUES ({e}, {ITEM[item]}, 100, 0, {amt}, {amt}, 0, {q('Valheim ' + pf)});")
    rows = []
    guid = PICK_GUID_MIN
    for pl in read_placements():
        P_ = PLACEMENTS[pl["key"]]
        if P_["kind"] != "pickable": continue
        pf = pick_prefab(P_, pl["src"])
        o = pl["o"]
        rows.append(f"({guid}, {go_entry[pf]}, {pl['map']}, 1, {pl['x']}, {pl['y']}, {pl['z']}, {round(o, 6)}, 0, 0, {round(math.sin(o / 2), 8)}, {round(math.cos(o / 2), 8)}, {respawn[pf]}, {respawn[pf]})")
        guid += 1
    assert guid - 1 <= PICK_GUID_MAX, guid
    w("DELETE FROM `gameobject` WHERE `id` BETWEEN %d AND %d;" % (PICK_GO_BASE, PICK_GO_BASE + 98))   # anciens ramassables, quelle que soit leur plage
    for i in range(0, len(rows), 500):
        w("INSERT INTO `gameobject` (`guid`,`id`,`map`,`spawnMask`,`position_x`,`position_y`,`position_z`,`orientation`,`rotation0`,`rotation1`,`rotation2`,`rotation3`,`spawntimesecsmin`,`spawntimesecsmax`) VALUES\n" + ",\n".join(rows[i:i + 500]) + ";")
    # controle : les materiaux annonces par rules.PLACEMENTS sont bien ceux du butin de Valheim
    for pl in RES_RULES.PLACEMENTS:
        real = set().union(*(GIVES[pf] for pf, _w in pl["prefabs"]))
        assert set(pl["gives"]) <= real, ("rules.PLACEMENTS gives faux", pl["key"], sorted(set(pl["gives"]) - real), sorted(real))
        if real - set(pl["gives"]):
            print("  (info) %s donne aussi %s" % (pl["key"], sorted(real - set(pl["gives"]))))
    return len(rows)

def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'

def write_lua(pieces):
    cats = ["$hud_misc", "$hud_crafting", "$hud_building", "$hud_building2", "$hud_furniture"]
    L = ["-- GENERE par tools/valheim/gen_server_sql.py (donnees de Valheim) : NE PAS EDITER A LA MAIN.",
         "WowlheimData = {}",
         "WowlheimData.categories = {" + ", ".join(lua_str(fr(c)) for c in cats) + "}",
         "WowlheimData.items = {"]
    # objets produits par les recettes (panneau de fabrication) : outils et marteau, en plus des materiaux ;
    # 9201041/9201042 (outils d'argent) n'existent pas dans Valheim et ne sont produits par aucune recette
    client_items = dict(ITEM)
    client_items["Hammer"] = 9201100
    for it, (pf, kind, tier) in TOOLS.items():
        if it not in (9201041, 9201042): client_items[pf] = it
    for pf, it in sorted(client_items.items(), key=lambda x: x[1]):
        sh = (mono(pf, "ItemDrop") or {}).get("m_itemData", {}).get("m_shared", {})
        L.append(f"  [{it}] = {{ name = {lua_str(fr(sh.get('m_name', pf)))}, icon = {lua_str(ICONS.get(pf, ''))},"
                 f" desc = {lua_str(fr(sh.get('m_description', '')))} }},")
    L.append("}")
    L.append("WowlheimData.stations = { workbench = " + lua_str(fr("piece_workbench")) + ", forge = " + lua_str(fr("piece_forge")) +
             ", stonecutter = " + lua_str(fr("piece_stonecutter")) + ", artisan = " + lua_str(fr("piece_artisanstation")) +
             ", charcoal_kiln = " + lua_str(fr(mono("charcoal_kiln", "Smelter")["m_name"])) +
             ", smelter = " + lua_str(fr(mono("smelter", "Smelter")["m_name"])) + " }")
    # recettes (memes noms que wowlheim_recipe / lignes C|) : KR| ne donne que des identifiants, l'annonce « Nouvelle
    # recette : Marteau » a besoin du nom meme si le panneau de fabrication n'a jamais ete ouvert
    L.append("WowlheimData.recipes = {")
    for rid, nm, out_item, amount, st in sorted(RECIPES_LUA):
        L.append(f"  [{rid}] = {{ name = {lua_str(nm)}, out = {out_item}, count = {amount}, station = {lua_str(st)} }},")
    L.append("}")
    # fonderie / four a charbon (composant Smelter, meme source que build_smelters) : combustible et conversions
    L.append("WowlheimData.smelters = {")
    for kind, pf in sorted((smelter_kind(pf), pf) for pf in SMOKE):
        sm = mono(pf, "Smelter")
        fuel = (sm.get("m_fuelItem") or {}).get("name")
        conv = []
        for c in sm["m_conversion"]:
            a, b = (c.get("m_from") or {}).get("name"), (c.get("m_to") or {}).get("name")
            if a in ITEM and b in ITEM: conv.append(f"{{{ITEM[a]}, {ITEM[b]}}}")
        L.append(f"  {kind} = {{ name = {lua_str(fr(sm['m_name']))}, fuel = {ITEM.get(fuel, 0) if fuel else 0}, maxOre = {sm['m_maxOre']},"
                 f" maxFuel = {sm['m_maxFuel']}, conversion = {{ {', '.join(conv)} }} }},")
    L.append("}")
    L.append("WowlheimData.pieces = {")
    for p in sorted(pieces, key=lambda p: (p["category"], p["id"])):
        costs = ", ".join(f"{{{a}, {b}}}" for a, b in p["costs"])
        L.append(f"  {{ id = {p['id']}, cat = {p['category'] + 1}, name = {lua_str(p['name'])}, desc = {lua_str(p['desc'])}, icon = {lua_str(p['icon'])},"
                 f" station = {lua_str(p['station'])}, hp = {p['health']}, costs = {{ {costs} }} }},")
    L.append("}")
    open(os.path.join(REPO, "tools", "client", "addon", "Wowlheim", "WowlheimData.lua"), "w", encoding="utf-8").write("\n".join(L) + "\n")

if __name__ == "__main__":
    main()
