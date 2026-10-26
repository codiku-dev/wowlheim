r"""Contenu serveur et addon tires des donnees reelles de Valheim (prefabs lus par vh_dump_all.py) :
- server/sql/world/012_valheim_content.sql : catalogue des pieces du marteau (noms francais de Valheim, categories, couts,
  PV, materiau, station requise, extensions, points d'accroche), modeles Valheim des pieces et des objets, arbres/buches
  a abattre (creatures), recettes d'outils de Valheim, nouveaux materiaux necessaires aux pieces.
- tools/client/addon/Wowlheim/WowlheimData.lua : le meme catalogue pour le menu du marteau (icones, categories).
Entrees : C:\Wowlheim\valheim_extract\{valheim_data.json, localization.txt}, C:\Wowlheim\wl_assets\{manifest,icons,wl_ids}.json
et les GameObjects des noeuds de bois existants (MySQL local) pour placer les arbres.
usage : python gen_server_sql.py   (MySQL local lance)"""
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
}
NEW_ITEMS = ["Coal", "Chain", "BronzeNails", "IronNails", "Feathers", "SharpeningStone", "Tar"]
TOOLS = {  # objet -> (prefab Valheim, genre, palier serveur, degats Valheim chop/pickaxe)
    9201010: ("AxeStone", "axe", 0), 9201011: ("AxeFlint", "axe", 1), 9201021: ("AxeBronze", "axe", 2),
    9201031: ("AxeIron", "axe", 3), 9201041: ("AxeIron", "axe", 4), 9201051: ("AxeBlackMetal", "axe", 5),
    9201012: ("PickaxeAntler", "pick", 1), 9201022: ("PickaxeBronze", "pick", 2), 9201032: ("PickaxeIron", "pick", 3),
    9201042: ("PickaxeIron", "pick", 4), 9201052: ("PickaxeBlackMetal", "pick", 5),
}
STATION = {None: "", "piece_workbench": "workbench", "forge": "forge", "piece_stonecutter": "stonecutter",
           "piece_artisanstation": "artisan", "blackforge": "blackforge"}

def tool_damage(prefab, kind):
    sh = mono(prefab, "ItemDrop")["m_itemData"]["m_shared"]
    return float(sh["m_damages"]["m_chop" if kind == "axe" else "m_pickaxe"])

# --------------------------------------------------------------------------------------------- pieces
KEEP_IDS = {"wood_floor": 1, "woodwall": 2, "wood_roof": 3, "wood_pole2": 4, "fire_pit": 5, "piece_workbench": 6,
            "forge": 7, "piece_workbench_ext1": 8, "piece_workbench_ext2": 9, "forge_ext1": 10, "forge_ext2": 11,
            "forge_ext3": 12}

def piece_kind(name, piece):
    n = name.lower()
    if mono(name, "StationExtension"): return "extension"
    if name in ("charcoal_kiln", "smelter"): return name
    if mono(name, "CraftingStation"):
        return {"piece_workbench": "workbench", "forge": "forge", "piece_stonecutter": "stonecutter"}.get(name, name)
    if mono(name, "Fireplace") or "fire" in n or "torch" in n or "hearth" in n: return "fire"
    if "roof" in n: return "roof"
    if "floor" in n or "stair" in n or "ladder" in n: return "floor"
    if any(k in n for k in ("pole", "beam", "pillar", "log_")): return "pillar"
    if any(k in n for k in ("wall", "door", "gate", "window", "fence", "stake", "arch")): return "wall"
    return "furniture" if piece["m_category"] == 4 else "misc"

def main():
    pieces = []
    next_id = 13
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
        lo, hi = m["bbox"]
        cs = pc.get("m_craftingStation")
        pieces.append({
            "id": pid, "prefab": name, "name": fr(pc["m_name"]), "desc": fr(pc["m_description"]),
            "category": pc["m_category"], "kind": piece_kind(name, pc), "station": STATION.get(cs["name"] if cs else None, cs and cs["name"]),
            "health": int(w.get("m_health", 100)), "material": int(w.get("m_materialType", 0)),
            "supports": 1 if w.get("m_supports", 1) else 0,
            "sx": round(hi[0] - lo[0], 3), "sy": round(hi[1] - lo[1], 3), "sz": round(hi[2] - lo[2], 3),
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
    w("DELETE FROM `item_template` WHERE `entry` BETWEEN 9200051 AND 9200059 OR `entry` = 9201010;")
    for pf in NEW_ITEMS:
        sh = mono(pf, "ItemDrop")["m_itemData"]["m_shared"]
        w(f"INSERT INTO `item_template` (`entry`,`class`,`subclass`,`name`,`displayid`,`Quality`,`BuyCount`,`BuyPrice`,`SellPrice`,`InventoryType`,`ItemLevel`,`RequiredLevel`,`stackable`,`delay`,`description`,`Material`,`bonding`)"
          f" VALUES ({ITEM[pf]},7,11,{q(fr(sh['m_name']))},7375,1,1,120,12,0,15,0,{min(200, max(1, int(sh.get('m_maxStackSize', 50))))},0,'Wowlheim',0,0);")
    w("CREATE TEMPORARY TABLE `tmp_axe` SELECT * FROM `item_template` WHERE `entry` = 9201011;")
    w(f"UPDATE `tmp_axe` SET `entry` = 9201010, `name` = {q(fr('item_axe_stone'))};")
    w("INSERT INTO `item_template` SELECT * FROM `tmp_axe`; DROP TEMPORARY TABLE `tmp_axe`;")
    for k, v in IDS["idi"].items():
        w(f"UPDATE `item_template` SET `displayid` = {v} WHERE `entry` = {int(k)};")
    w(f"UPDATE `item_template` SET `name` = {q(fr('item_hammer'))}, `sheath` = 3 WHERE `entry` = 9201100;")
    w("UPDATE `item_template` SET `sheath` = 3 WHERE `entry` BETWEEN 9201010 AND 9201099;")
    # sort de pose (meme definition que dans le Spell.dbc du patch client, gen_client_patch.py) : CMaNGOS lit spell_template
    w("DELETE FROM `spell_template` WHERE `Id` = 40001;")
    w("CREATE TEMPORARY TABLE `tmp_sp` SELECT * FROM `spell_template` WHERE `Id` = 1543;")
    w("UPDATE `tmp_sp` SET `Id` = 40001, `School` = 0, `Category` = 0, `Attributes` = 0, `AttributesEx` = 0, `AttributesEx2` = 0, `Targets` = 64,"
      " `CastingTimeIndex` = 1, `RecoveryTime` = 0, `CategoryRecoveryTime` = 0, `MaxLevel` = 0, `BaseLevel` = 0, `SpellLevel` = 0, `DurationIndex` = 0,"
      " `ManaCost` = 0, `RangeIndex` = 3, `Effect1` = 76, `Effect2` = 0, `EffectImplicitTargetA1` = 28, `EffectImplicitTargetA2` = 0, `EffectRadiusIndex1` = 7,"
      " `EffectRadiusIndex2` = 0, `EffectApplyAuraName1` = 0, `EffectApplyAuraName2` = 0, `EffectMiscValue1` = 9110001, `EffectMiscValue2` = 0, `SpellVisual` = 0,"
      " `SpellIconID` = 3000, `SpellName` = 'Construire', `StartRecoveryCategory` = 0, `StartRecoveryTime` = 0, `SpellFamilyName` = 0;")
    w("INSERT INTO `spell_template` SELECT * FROM `tmp_sp`; DROP TEMPORARY TABLE `tmp_sp`;")
    # marteau : utilisation = sort de pose a cible au sol (40001, patch client) -> cercle de ciblage, pose au point clique
    w("UPDATE `item_template` SET `spellid_1` = 40001, `spelltrigger_1` = 5, `spellcharges_1` = 0, `spellcooldown_1` = 0, `spellcategory_1` = 0, `spellcategorycooldown_1` = 0 WHERE `entry` = 9201100;")
    # noms francais de Valheim pour les materiaux
    for pf, it in ITEM.items():
        sh = (mono(pf, "ItemDrop") or {}).get("m_itemData", {}).get("m_shared", {})
        if sh.get("m_name"):
            w(f"UPDATE `item_template` SET `name` = {q(fr(sh['m_name']))} WHERE `entry` = {it};")
    w("DROP TABLE IF EXISTS `wowlheim_tool`;")
    w("CREATE TABLE `wowlheim_tool` (`item_id` INT UNSIGNED NOT NULL PRIMARY KEY, `kind` VARCHAR(8) NOT NULL COMMENT 'axe | pick', `tier` TINYINT UNSIGNED NOT NULL DEFAULT 1,"
      " `damage` FLOAT NOT NULL DEFAULT 0 COMMENT 'Valheim m_damages.m_chop (hache) / m_pickaxe (pic)') ENGINE=InnoDB DEFAULT CHARSET=utf8;")
    for it, (pf, kind, tier) in sorted(TOOLS.items()):
        w(f"INSERT INTO `wowlheim_tool` (`item_id`,`kind`,`tier`,`damage`) VALUES ({it}, {q(kind)}, {tier}, {tool_damage(pf, kind)});")

    # ---------------- recettes de Valheim (Recipe_*) pour les objets qui existent ici
    w("ALTER TABLE `wowlheim_recipe` MODIFY `station` VARCHAR(16) NOT NULL DEFAULT '' COMMENT 'vide = sans station (Valheim : fabrication a la main)';")
    rec_out = {"AxeStone": (100, 9201010), "AxeFlint": (101, 9201011), "PickaxeAntler": (102, 9201012), "AxeBronze": (103, 9201021),
               "PickaxeBronze": (104, 9201022), "AxeIron": (105, 9201031), "PickaxeIron": (106, 9201032), "Bronze": (201, 9200015),
               "Hammer": (99, 9201100), "BronzeNails": (210, 9200053), "IronNails": (211, 9200054), "Chain": (212, 9200052),
               "SharpeningStone": (213, 9200056)}
    done = set()
    for r in D["recipes"]:
        it = r.get("m_item") or {}
        pf = it.get("name")
        if pf not in rec_out or pf in done: continue
        ings = [(x["m_resItem"]["name"], x["m_amount"]) for x in r["m_resources"] if x["m_resItem"] and x["m_amount"] > 0
                and not x["m_resItem"]["name"].startswith("Upgrader")]
        if any(i[0] not in ITEM for i in ings): continue
        if pf == "Bronze" and r.get("m_amount", 1) != 1: continue
        done.add(pf)
        rid, out_item = rec_out[pf]
        st = STATION.get((r.get("m_craftingStation") or {}).get("name"), "")
        nm = fr(mono(pf, "ItemDrop")["m_itemData"]["m_shared"]["m_name"])
        w(f"DELETE FROM `wowlheim_recipe_ingredient` WHERE `recipe_id` = {rid}; DELETE FROM `wowlheim_recipe` WHERE `id` = {rid};")
        w(f"INSERT INTO `wowlheim_recipe` (`id`,`name`,`station`,`output_item`,`output_count`,`min_station_level`) VALUES ({rid}, {q(nm)}, {q(st)}, {out_item}, {r.get('m_amount', 1)}, {max(1, r.get('m_minStationLevel', 1))});")
        for i, n in ings:
            w(f"INSERT INTO `wowlheim_recipe_ingredient` VALUES ({rid}, {ITEM[i]}, {n});")
    # charbon : Valheim le produit au four a charbon (bois -> charbon) ; ici recette au four pose (piece charcoal_kiln)
    w("DELETE FROM `wowlheim_recipe_ingredient` WHERE `recipe_id` = 214; DELETE FROM `wowlheim_recipe` WHERE `id` = 214;")
    w(f"INSERT INTO `wowlheim_recipe` VALUES (214, {q(fr('item_coal'))}, 'charcoal_kiln', 9200051, 1, 1);")
    w("INSERT INTO `wowlheim_recipe_ingredient` VALUES (214, 9200001, 1);")

    # ---------------- arbres et buches : creatures a abattre a la hache
    trees = build_trees(w)
    open(os.path.join(REPO, "server", "sql", "world", "012_valheim_content.sql"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    write_lua(pieces)
    print("pieces :", len(pieces), "; arbres :", trees)

TREE_SPECIES = {  # prefab arbre -> (buche, demi-buche, souche, butin direct (objet, chance, min, max))
    "Beech1": ("beech_log", "beech_log_half", "Beech_Stub", ("Resin", 0.31, 1, 2)),
    "FirTree": ("FirTree_log", "FirTree_log_half", "FirTree_Stub", ("Resin", 0.2, 1, 1)),
    "Pinetree_01": ("PineTree_log", "PineTree_log_half", "Pinetree_01_Stub", ("Resin", 0.4, 1, 2)),
    "Birch1": ("Birch_log", "Birch_log_half", "BirchStub", ("Resin", 0.2, 1, 1)),
    "Oak1": ("Oak_log", "Oak_log_half", "OakStub", ("Resin", 0.3, 1, 2)),
}
# noeud de bois existant (palier de zone) -> essences de Valheim du biome correspondant
NODE_SPECIES = {9101001: ["Beech1", "Beech1", "FirTree"], 9101002: ["Pinetree_01", "FirTree"], 9101003: ["Oak1"],
                9101004: ["FirTree", "Pinetree_01"], 9101005: ["Birch1"]}

# noeud de pierre/minerai existant -> roches et filons de Valheim
NODE_ROCKS = {9101011: ["MineRock_Stone", "Rock_4", "Rock_4"], 9101012: ["MineRock_Stone", "Rock_4"], 9101013: ["MineRock_Stone"],
              9101014: ["MineRock_Stone"], 9101015: ["MineRock_Stone"], 9101021: ["MineRock_Copper"], 9101022: ["MineRock_Tin"],
              9101023: ["MineRock_Iron"], 9101026: ["MineRock_Obsidian"]}
# Valheim : minerai a fondre a la fonderie ; tant que la fonderie n'est pas geree, le minerai donne directement le metal du serveur
ORE = {"CopperOre": "Copper", "TinOre": "Tin", "IronOre": "Iron", "SilverOre": "Silver", "IronScrap": "Iron"}

def build_rocks(w, respawn):
    """Roches et filons de Valheim (MineRock / Destructible + DropOnDestroyed) : creatures frappees a la pioche."""
    rock_entry = {}
    rocks = sorted({r for v in NODE_ROCKS.values() for r in v})
    w("DELETE FROM `creature_template` WHERE `Entry` BETWEEN 9300101 AND 9300199;")
    for i, n in enumerate(rocks):
        e = 9300101 + i
        rock_entry[n] = e
        mr = mono(n, "MineRock") or mono(n, "Destructible")
        dd = (mono(n, "MineRock") or mono(n, "DropOnDestroyed") or {})
        dw = dd.get("m_dropItems") or dd.get("m_dropWhenDestroyed") or {"m_dropMin": 0, "m_dropMax": 0, "m_drops": []}
        hp, tier = mr["m_health"], mr["m_minToolTier"] + 1          # paliers de pioche du serveur = Valheim + 1
        # MineRock : chaque zone (enfant « stone », maillage de 190 sommets) a m_health PV et donne son propre butin ;
        # la creature regroupe les zones : PV et tirages multiplies par le nombre de zones
        areas = max(1, MAN[n]["verts"] // 190) if mono(n, "MineRock") else 1
        # la pioche de Valheim frappe plusieurs zones par coup (Attack.m_multiHit, arc de 120 deg) : HYPOTHESE 3 zones par coup
        # [INFERE, non mesure] -> PV effectifs = PV d'une zone x zones / 3 ; le butin reste celui de toutes les zones
        hp_total = hp * areas / (3 if areas > 1 else 1)
        disp = IDS["cdi"][n]
        nm = fr(mr.get("m_name") or "") if mr.get("m_name") and not mr["m_name"].startswith("$") is False else None
        nm = {"MineRock_Stone": "Rocher", "Rock_4": "Pierre", "MineRock_Copper": "Gisement de cuivre", "MineRock_Tin": "Gisement d'étain",
              "MineRock_Iron": "Tas de ferraille", "MineRock_Obsidian": "Obsidienne"}.get(n, n)
        w("INSERT INTO `creature_template` (`Entry`,`Name`,`SubName`,`MinLevel`,`MaxLevel`,`DisplayId1`,`DisplayIdProbability1`,`Faction`,`Scale`,`CreatureType`,"
          "`InhabitType`,`RegenerateStats`,`UnitFlags`,`ExtraFlags`,`SpeedWalk`,`SpeedRun`,`HealthMultiplier`,`DamageMultiplier`,`ArmorMultiplier`,`ExperienceMultiplier`,"
          "`MinLevelHealth`,`MaxLevelHealth`,`MinMeleeDmg`,`MaxMeleeDmg`,`Armor`,`MeleeBaseAttackTime`,`UnitClass`,`LootId`,`SchoolImmuneMask`,`MechanicImmuneMask`,`MovementType`,`AIName`)"
          f" VALUES ({e}, {q(nm)}, 'Wowlheim', 1, 1, {disp}, 100, 7, 1, 10, 1, 0, 0, {2 | 4 | 16 | 131072}, 0.01, 0.01, {round((hp_total + 0.2) / 42.0, 5)}, 0, 0, 0,"
          f" {int(hp_total)}, {int(hp_total)}, 0, 0, 0, 2000, 1, 0, 126, 2147483647, 0, 'NullAI');")
        lo, hi = MAN[n]["bbox"]
        w(f"INSERT INTO `creature_model_info` (`modelid`,`bounding_radius`,`combat_reach`,`gender`,`modelid_other_gender`,`modelid_alternative`) VALUES ({disp}, 0.8, {round(max(hi[0] - lo[0], hi[1] - lo[1]) / 2 + 1.0, 2)}, 2, 0, 0);")
        w(f"INSERT INTO `wowlheim_tree` VALUES ({e}, 'rock', {tier}, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'pick', {dw['m_dropMin'] * areas}, {dw['m_dropMax'] * areas});")
        agg = {}
        for x in dw["m_drops"]:
            if not x["m_item"]: continue
            it = ORE.get(x["m_item"]["name"], x["m_item"]["name"])
            if it not in ITEM: continue
            a = agg.setdefault(ITEM[it], [0.0, x["m_stackMin"], x["m_stackMax"]])
            a[0] += x["m_weight"]
        for it, (wgt, smin, smax) in agg.items():
            w(f"INSERT INTO `wowlheim_tree_drop` VALUES ({e}, {it}, {wgt}, {smin}, {smax});")
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
        names += [t, log, half]
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
        tb = mono(t, "TreeBase"); tl = mono(log, "TreeLog"); th = mono(half, "TreeLog")
        stub_go = 9120001 + i
        w(f"INSERT INTO `gameobject_template` (`entry`,`type`,`displayId`,`name`,`size`) VALUES ({stub_go}, 5, {IDS['go'][stub]}, {q(fr('prop_stub') if 'prop_stub' in LOC else 'Souche')}, 1);")
        loglen = MAN[log]["bbox"][1][0] - MAN[log]["bbox"][0][0]
        halflen = MAN[half]["bbox"][1][0] - MAN[half]["bbox"][0][0]
        tname = fr("prop_" + t.lower().rstrip("1").rstrip("_01").replace("pinetree", "pine").replace("firtree", "fir"))
        for n, kind, hp, tier in ((t, "tree", tb["m_health"], tb["m_minToolTier"]), (log, "log", tl["m_health"], tl["m_minToolTier"]),
                                  (half, "half", th["m_health"], th["m_minToolTier"])):
            disp = IDS["cdi"][n]
            nm = {"tree": tname, "log": "Tronc", "half": "Bûche"}[kind] + ("" if kind == "tree" else " (" + tname.lower() + ")")
            loot = entry[n] if kind == "half" else 0
            w("INSERT INTO `creature_template` (`Entry`,`Name`,`SubName`,`MinLevel`,`MaxLevel`,`DisplayId1`,`DisplayIdProbability1`,`Faction`,`Scale`,`CreatureType`,"
              "`InhabitType`,`RegenerateStats`,`UnitFlags`,`ExtraFlags`,`SpeedWalk`,`SpeedRun`,`HealthMultiplier`,`DamageMultiplier`,`ArmorMultiplier`,`ExperienceMultiplier`,"
              "`MinLevelHealth`,`MaxLevelHealth`,`MinMeleeDmg`,`MaxMeleeDmg`,`Armor`,`MeleeBaseAttackTime`,`UnitClass`,`LootId`,`SchoolImmuneMask`,`MechanicImmuneMask`,`MovementType`,`AIName`)"
              f" VALUES ({entry[n]}, {q(nm)}, 'Wowlheim', 1, 1, {disp}, 100, 7, 1, 10, 1, 0, 0, {2 | 4 | 16 | 131072}, 0.01, 0.01, {round((hp + 0.2) / 42.0, 5)}, 0, 0, 0,"
              f" {int(hp)}, {int(hp)}, 0, 0, 0, 2000, 1, {loot}, 126, 2147483647, 0, 'NullAI');")
            lo, hi = MAN[n]["bbox"]
            # Valheim : le coup touche n'importe quel point du collider ; ici portee de melee = demi-longueur pour une buche couchee
            reach = 3.0 if kind == "tree" else round((hi[0] - lo[0]) / 2 + 1.0, 2)
            reach_r = 1.0 if kind == "tree" else 0.8
            w(f"INSERT INTO `creature_model_info` (`modelid`,`bounding_radius`,`combat_reach`,`gender`,`modelid_other_gender`,`modelid_alternative`) VALUES ({disp}, {reach_r}, {reach}, 2, 0, 0);")
            if kind == "tree":
                di = ITEM.get(drop[0], 0)
                w(f"INSERT INTO `wowlheim_tree` VALUES ({entry[n]}, 'tree', {tier}, {entry[log]}, 1, 0, {round(loglen / 2 + 1.0, 2)}, {stub_go}, {respawn}, {di}, {drop[2]}, {drop[3]}, {drop[1]}, 'axe', 0, 0);")
            elif kind == "log":
                w(f"INSERT INTO `wowlheim_tree` VALUES ({entry[n]}, 'log', {tier}, {entry[half]}, 2, {round(halflen + 0.3, 2)}, 0, 0, 0, 0, 0, 0, 0, 'axe', 0, 0);")
            else:
                w(f"INSERT INTO `wowlheim_tree` VALUES ({entry[n]}, 'half', {tier}, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'axe', 0, 0);")
                # TreeLog.m_dropWhenDestroyed : m_dropMin..m_dropMax tirages, chacun choisit un objet selon son poids
                dmin, dmax, items = droptable(half)
                tw = sum(x[1] for x in items)
                for it, wgt, smin, smax in items:
                    if it not in ITEM: continue
                    share = wgt / tw
                    lo_n = max(1, int(round(dmin * share * smin))); hi_n = max(lo_n, int(round(dmax * share * smax)))
                    w(f"INSERT INTO `creature_loot_template` (`entry`,`item`,`ChanceOrQuestChance`,`groupid`,`mincountOrRef`,`maxcount`,`comments`) VALUES ({entry[n]}, {ITEM[it]}, 100, 0, {lo_n}, {hi_n}, {q(half)});")
    rock_entry = build_rocks(w, respawn)
    # placement : les noeuds de bois GameObject deviennent des arbres de Valheim (memes positions, essences par biome)
    # positions lues dans les scripts des noeuds (005, 008), rejoues avant 012 par apply_sql.py
    import re, glob
    rows = []
    for fn in sorted(glob.glob(os.path.join(REPO, "server", "sql", "world", "00[58]_*.sql"))):
        for m in re.finditer(r"^\((\d+),(910100[1-5]|91010(?:1[1-5]|2[1236])),(\d+),\d+,([-\d.]+),([-\d.]+),([-\d.]+),", open(fn, encoding="utf-8").read(), re.M):
            rows.append("	".join(m.groups()))
    w("DELETE FROM `creature` WHERE `guid` BETWEEN 9600001 AND 9699999;")
    w("DELETE FROM `gameobject` WHERE `id` BETWEEN 9101001 AND 9101005;")
    w("DELETE FROM `gameobject` WHERE `id` IN (" + ",".join(str(k) for k in NODE_ROCKS) + ");")
    n = 0
    vals = []
    for line in rows:
        if not line.strip(): continue
        guid, gid, mp, x, y, z = line.split("\t")
        sp = NODE_SPECIES.get(int(gid)) or NODE_ROCKS[int(gid)]
        h = zlib.crc32(guid.encode())
        species = sp[h % len(sp)]
        ang = (h >> 8) % 628 / 100.0
        n += 1
        e = rock_entry.get(species) or entry[species]
        vals.append(f"({9600000 + n}, {e}, {mp}, {x}, {y}, {z}, {ang}, {respawn}, {respawn}, 0, 0)")
    for i in range(0, len(vals), 500):
        w("INSERT INTO `creature` (`guid`,`id`,`map`,`position_x`,`position_y`,`position_z`,`orientation`,`spawntimesecsmin`,`spawntimesecsmax`,`spawndist`,`MovementType`) VALUES\n" + ",\n".join(vals[i:i + 500]) + ";")
    # 005/008 sont rejoues avant 012 : ils recreent les noeuds de bois que l'on vient de convertir
    return n

def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'

def write_lua(pieces):
    cats = ["$hud_misc", "$hud_crafting", "$hud_building", "$hud_building2", "$hud_furniture"]
    L = ["-- GENERE par tools/valheim/gen_server_sql.py (donnees de Valheim) : NE PAS EDITER A LA MAIN.",
         "WowlheimData = {}",
         "WowlheimData.categories = {" + ", ".join(lua_str(fr(c)) for c in cats) + "}",
         "WowlheimData.items = {"]
    for pf, it in sorted(ITEM.items(), key=lambda x: x[1]):
        sh = (mono(pf, "ItemDrop") or {}).get("m_itemData", {}).get("m_shared", {})
        L.append(f"  [{it}] = {{ name = {lua_str(fr(sh.get('m_name', pf)))}, icon = {lua_str(ICONS.get(pf, ''))} }},")
    L.append("}")
    L.append("WowlheimData.stations = { workbench = " + lua_str(fr("piece_workbench")) + ", forge = " + lua_str(fr("piece_forge")) +
             ", stonecutter = " + lua_str(fr("piece_stonecutter")) + " }")
    L.append("WowlheimData.pieces = {")
    for p in sorted(pieces, key=lambda p: (p["category"], p["id"])):
        costs = ", ".join(f"{{{a}, {b}}}" for a, b in p["costs"])
        L.append(f"  {{ id = {p['id']}, cat = {p['category'] + 1}, name = {lua_str(p['name'])}, desc = {lua_str(p['desc'])}, icon = {lua_str(p['icon'])},"
                 f" station = {lua_str(p['station'])}, hp = {p['health']}, costs = {{ {costs} }} }},")
    L.append("}")
    open(os.path.join(REPO, "tools", "client", "addon", "Wowlheim", "WowlheimData.lua"), "w", encoding="utf-8").write("\n".join(L) + "\n")

if __name__ == "__main__":
    main()
