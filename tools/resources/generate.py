"""Generateur des scripts SQL de ressources Wowlheim (server/sql/world/002..006). Lecture seule de classicmangos.

usage : python generate.py [items|nodes|loot|spawns|vendors|all]   (defaut : all ; prerequis : python build_cache.py)
Les fichiers produits sont idempotents (DELETE de leurs propres plages, puis INSERT), UTF-8, applicables par
  mysql ... classicmangos < 00x_*.sql   (l'integrateur les applique ; ce script n'ecrit jamais dans une base)."""
import os, sys, re, json, math, zlib, collections, statistics
sys.path.insert(0, os.path.dirname(__file__))
from common import sql, REPO
import rules, classify

OUT = os.path.join(REPO, "server", "sql", "world")
HEADER = "-- GENERE par tools/resources/generate.py : NE PAS EDITER A LA MAIN. Rejouable (idempotent).\nSET NAMES utf8mb4;\n"


def q(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v) if isinstance(v, float) else str(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def insert(table, cols, rows, chunk=100):
    out = []
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        out.append("INSERT INTO `%s` (%s) VALUES\n%s;" % (table, ",".join("`%s`" % c for c in cols),
                   ",\n".join("(" + ",".join(q(v) for v in r) + ")" for r in part)))
    return "\n".join(out)


def write(name, text):
    p = os.path.join(OUT, name)
    with open(p, "w", encoding="utf8", newline="\n") as f:
        f.write(text)
    print("ecrit", p, len(text), "octets")


# ------------------------------------------------------------------ 002 : objets
# champ Material (sons de manipulation) : 1 metal, 2 bois, 8 cuir, 0 indefini
MATERIAL_SOUND = {**{i: 2 for i in (9200001, 9200011, 9200012, 9200022)}, **{i: 1 for i in (9200013, 9200014, 9200015, 9200021, 9200031, 9200041)},
                  **{i: 8 for i in (9200005, 9200006, 9200016, 9200033, 9200044)}}
def gen_items():
    # validation : displayid reels d'item_template
    known = {int(r[0]) for r in sql("select distinct displayid from item_template")}
    for m in rules.MATERIALS:
        assert m["display"] in known, ("displayid inconnu", m)
    for t in rules.TOOLS:
        assert t["display"] in known, ("displayid inconnu", t)
    cols = ["entry", "class", "subclass", "name", "displayid", "Quality", "BuyCount", "BuyPrice", "SellPrice", "InventoryType",
            "ItemLevel", "RequiredLevel", "stackable", "delay", "description", "Material", "bonding"]
    rows = []
    lo = {t: l for t, _n, l, _h in rules.TIERS}
    for m in rules.MATERIALS:
        rows.append([m["id"], 7, 11, m["name"], m["display"], m["quality"], 1, rules.buy_price(m), rules.sell_price(m), 0,
                     max(lo[m["tier"]], 1), 0, rules.STACK, 0, "Wowlheim", MATERIAL_SOUND.get(m["id"], 0), 0])
    wcols = cols + ["dmg_min1", "dmg_max1", "dmg_type1", "sheath", "MaxDurability"]
    wrows = []
    for t in rules.TOOLS:
        wrows.append([t["id"], 2, 14, t["name"], t["display"], 1, 1, 0, 10 * 3 ** (t["tier"] - 1), 21, max(lo[t["tier"]], 1),
                      t["req"], 1, 2000, "Wowlheim", 1, 0, t["dmg"][0], t["dmg"][1], 0, 0, t["durability"]])
    text = HEADER + ("-- 002 : materiaux (classe 7/11) et outils (classe 2/14, comme le Pic de mineur) de Wowlheim. Plage 9200001-9299999.\n"
                     "-- Noms francais de Valheim ; outils : uniquement ceux de Valheim (durabilite m_maxDurability, aucun niveau requis).\n")
    text += "DELETE FROM `item_template` WHERE `entry` BETWEEN 9200001 AND 9299999;\n"
    text += insert("item_template", cols, rows) + "\n" + insert("item_template", wcols, wrows) + "\n"
    write("002_items.sql", text)


# ------------------------------------------------------------------ 003 : anciens noeuds (supprimes)
def gen_nodes():
    text = HEADER + ("-- 003 : SUPPRESSION des anciens modeles de noeuds GameObject aux modeles WoW (9101001-9101999) et de leur butin.\n"
                     "-- Remplaces par les arbres, roches, filons (creatures) et ramassables (GameObjects 9130001+) de Valheim, ecrits dans\n"
                     "-- 012_valheim_content.sql (tools/valheim/gen_server_sql.py, positions : C:\\Wowlheim\\data\\wl_terrain\\placements.json).\n")
    text += "DELETE FROM `gameobject_template` WHERE `entry` BETWEEN %d AND %d;\n" % (rules.OLD_NODE_ENTRY_MIN, rules.OLD_NODE_ENTRY_MAX)
    text += "DELETE FROM `gameobject_loot_template` WHERE `entry` BETWEEN %d AND %d;\n" % (rules.OLD_NODE_ENTRY_MIN, rules.OLD_NODE_ENTRY_MAX)
    write("003_nodes.sql", text)


# ------------------------------------------------------------------ 004 : butin de mobs
def ref_id(tier, cat):
    return rules.REF_BASE + tier * 1000 + rules.ALL_CATS.index(cat) * 10


def ref_contents(tier, cat):
    """[(item, chance, min, max)] pour un monstre de palier `tier` et de categorie `cat` (regles heritees des categories parentes)."""
    anc = classify.ancestors(cat)
    out = []
    for m in rules.MATERIALS:
        if m["id"] not in rules.DROP_RULES:
            continue
        if m["tier"] == tier:
            back = False
        elif m["tier"] == tier - 1 and m["kind"] == "base":
            back = True
        else:
            continue
        best = None
        for c, ch, mn, mx in rules.DROP_RULES[m["id"]]:
            if c in anc and (best is None or ch > best[0]):
                best = (ch, mn, mx)
        if best is None:
            continue
        ch, mn, mx = best
        if back:
            ch = max(rules.BACK_MIN, int(round(ch * rules.BACK_FACTOR)))
            mx = min(mx, 2)
        out.append((m["id"], ch, mn, mx))
    return out


def game_spawns(info):
    """Lignes `creature` du gibier ajoute (rules.GAME_SPAWNS) : positions reprises de critters existants de la zone (lapins, rats), hors villes
    et interieurs, espacees d'au moins GAME_SPAWN_MIN_DIST ; ordre deterministe (guid source croissant)."""
    rows = []
    guid = rules.GAME_SPAWN_GUID[0]
    excl = re.compile(rules.GAME_SPAWN_EXCLUDE_AREAS + "|" + rules.INDOOR_AREA_RE, re.I)
    for mp, zid, entry, src, nmax, only in rules.GAME_SPAWNS:
        keep = (lambda an: re.search(only, an, re.I)) if only else (lambda an: not excl.search(an))
        cand = sorted((a[7], a[1], a[2]) for e in src for a in info["spawns"].get(e, [])
                      if a[0] == mp and a[3] == zid and keep(a[6] or ""))
        picked = []
        for g, x, y in cand:
            if len(picked) >= nmax:
                break
            if all(math.hypot(x - px, y - py) >= rules.GAME_SPAWN_MIN_DIST for _g, px, py in picked):
                picked.append((g, x, y))
        if not picked:
            continue
        pos = {int(r[0]): r for r in sql("select guid,position_x,position_y,position_z,orientation from creature where guid in (%s)"
                                         % ",".join(str(g) for g, _x, _y in picked))}
        for g, _x, _y in picked:
            r = pos[g]
            rows.append([guid, entry, mp, 1, float(r[1]), float(r[2]), float(r[3]), float(r[4]), 300, 300, 8.0, 1])
            guid += 1
    assert guid - 1 <= rules.GAME_SPAWN_GUID[1]
    return rows


def gen_loot():
    info = classify.load()
    elig = classify.eligible_lootids(info)
    refs = {}
    rrows = []
    for t in range(1, 6):
        for cat in rules.ASSIGNABLE:
            items = ref_contents(t, cat)
            if not items:
                continue
            rid = ref_id(t, cat)
            refs[(t, cat)] = rid
            for item, ch, mn, mx in items:
                rrows.append([rid, item, ch, 0, mn, mx, 0, "T%d %s : %s" % (t, cat, rules.MAT[item]["name"])])
    crows = []
    skipped = 0
    for lid, (t, cat, elite) in sorted(elig.items()):
        rid = refs.get((t, cat))
        if rid is None:
            skipped += 1
            continue
        crows.append([lid, rid, 100, 0, -rid, rules.ELITE_REPEAT if elite else 1, 0, "Wowlheim T%d %s" % (t, cat)])
    text = HEADER + ("-- 004 : butin Wowlheim par categorie de creature x palier (voir docs/RESOURCES.md).\n"
                     "-- reference_loot_template : entrees 8300000+ (9300000+ impossible : mincountOrRef est un MEDIUMINT signe) ; creature_loot_template : UNE ligne de reference ajoutee par LootId eligible\n"
                     "-- (item = id de la reference, mincountOrRef = -id). Aucune ligne de butin existante n'est modifiee ; seule modification d'une ligne existante : LootId des critters cerfs/biches (ci-dessous).\n")
    # gibier critter (cerfs, biches : classify.CRITTER_GAME_MODELS) : seuls modeles SANS butin dans WoW auxquels Wowlheim en donne un
    # (LootId = Entry ; aucune ligne creature_loot_template n'existait sous ces entrees). Annulation : UPDATE ... SET LootId=0 sur ces entrees.
    game = sorted(e for e, t in info["ct"].items() if t.get("game_critter") and t["lootid"] in elig)
    if game:
        text += ("-- gibier critter (cerfs, biches, faons ; Valheim : le cerf est le premier gibier) : LootId = Entry (aucun butin dans WoW).\n"
                 "UPDATE `creature_template` SET `LootId` = `Entry` WHERE `Entry` IN (%s) AND `LootId` IN (0, `Entry`);\n"
                 % ",".join(str(e) for e in game))
    gs = game_spawns(info)
    lo, hi = rules.GAME_SPAWN_GUID
    text += ("-- gibier ajoute aux zones de depart sans bete a bois/cornes (rules.GAME_SPAWNS) : critters existants, positions de critters existants.\n"
             "DELETE FROM `creature` WHERE `guid` BETWEEN %d AND %d;\n" % (lo, hi))
    if gs:
        text += insert("creature", ["guid", "id", "map", "spawnMask", "position_x", "position_y", "position_z", "orientation",
                                    "spawntimesecsmin", "spawntimesecsmax", "spawndist", "MovementType"], gs) + "\n"
    text += "DELETE FROM `reference_loot_template` WHERE `entry` BETWEEN 8300000 AND 8399999;\n"
    text += "DELETE FROM `creature_loot_template` WHERE `item` BETWEEN 8300000 AND 8399999 AND `mincountOrRef` < 0;\n"
    cols = ["entry", "item", "ChanceOrQuestChance", "groupid", "mincountOrRef", "maxcount", "condition_id", "comments"]
    text += insert("reference_loot_template", cols, rrows) + "\n" + insert("creature_loot_template", cols, crows, 200) + "\n"
    write("004_loot.sql", text)
    print("references:", len(refs), "lignes ref:", len(rrows), "lignes creature:", len(crows), "lootid sans regle:", skipped)


# ------------------------------------------------------------------ 005 : anciens noeuds de validation (supprimes)
def gen_spawns():
    text = HEADER + ("-- 005 : SUPPRESSION des anciens noeuds de validation (Elwynn, Durotar, Dun Morogh ; guid 9500001-9599999) aux modeles WoW.\n"
                     "-- Le DELETE est limite aux entrees de noeuds (9101001-9101999) : les pieces de construction posees dans cette plage\n"
                     "-- de guid (le serveur attribue max(guid)+1) ne sont pas touchees.\n")
    text += "DELETE FROM `gameobject` WHERE `guid` BETWEEN %d AND %d AND `id` BETWEEN %d AND %d;\n" % (
        rules.NODE_GUID_BASE, rules.NODE_GUID_MAX, rules.OLD_NODE_ENTRY_MIN, rules.OLD_NODE_ENTRY_MAX)
    write("005_node_spawns.sql", text)


# ------------------------------------------------------------------ 006 : vendeurs de secours
CITY_ZONES = {1519, 1537, 1497, 1637, 1638, 1657, 3487}
VENDOR_SUBNAME = re.compile(r"^(General|Trade)", re.I)
VENDORS_PER_TIER_CONTINENT = 6


def zone_tiers(info):
    lv = collections.defaultdict(list)
    for e, sps in info["spawns"].items():
        t = info["ct"].get(e)
        if not t or t["why_not"]:
            continue
        for (m, x, y, zid, zn, aid, an, g) in sps:
            lv[(m, zid)].append(t["level"])
    return {k: (rules.tier_of_level(statistics.median(v)), statistics.median(v), len(v)) for k, v in lv.items() if len(v) >= 30}


VENDOR_FALLBACK = re.compile(r"Innkeeper|Mining|Blacksmith", re.I)


def gen_vendors():
    """Valheim n'a aucun vendeur de materiaux (Haldor ne vend ni bois, ni pierre, ni minerai, ni metal) : 006 retire toute vente
    de materiau ou d'outil Wowlheim (plage 9200001-9299999) et n'en ajoute aucune."""
    text = HEADER + ("-- 006 : AUCUN vendeur de materiaux Wowlheim (Valheim : le marchand Haldor ne vend aucun materiau de construction).\n"
                     "-- Supprime les lignes npc_vendor de la plage Wowlheim (9200001-9299999) ajoutees par l'ancienne version de ce script.\n")
    text += "DELETE FROM `npc_vendor` WHERE `item` BETWEEN 9200001 AND 9299999;\n"
    write("006_vendors.sql", text)

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in (("items", gen_items), ("nodes", gen_nodes), ("loot", gen_loot), ("spawns", gen_spawns), ("vendors", gen_vendors)):
        if what in ("all", name):
            fn()
