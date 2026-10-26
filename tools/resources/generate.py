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
                      t["req"], 1, 2000, "Wowlheim", 1, 0, t["dmg"][0], t["dmg"][1], 0, 0, 0])
    text = HEADER + "-- 002 : materiaux (classe 7/11) et outils (classe 2/14, comme le Pic de mineur) de Wowlheim. Plage 9200001-9299999.\n"
    text += "DELETE FROM `item_template` WHERE `entry` BETWEEN 9200001 AND 9299999;\n"
    text += insert("item_template", cols, rows) + "\n" + insert("item_template", wcols, wrows) + "\n"
    write("002_items.sql", text)


# ------------------------------------------------------------------ 003 : noeuds
def gen_nodes():
    dn = json.load(open(os.path.join(os.path.dirname(__file__), "cache", "gobj_display.json")))
    for n in rules.NODES:
        assert str(n["display"]) in dn, ("displayId absent de GameObjectDisplayInfo.dbc", n)
    cols = ["entry", "type", "displayId", "name", "faction", "flags", "size", "data0", "data1", "data2", "data3", "data4", "data5"]
    rows = [[n["entry"], 3, n["display"], n["name"], 0, 0, n["size"], 0, n["entry"], 0, 1, 0, 0] for n in rules.NODES]
    lrows = []
    for n in rules.NODES:
        for item, ch, mn, mx in n["loot"]:
            lrows.append([n["entry"], item, ch, 0, mn, mx, 0, rules.MAT[item]["name"]])
    text = HEADER + ("-- 003 : noeuds de ressources (type 3 CHEST, data0=0 : AUCUN verrou, data1=table de butin, data3=1 : disparait une fois pille).\n"
                     "-- Le controle de l'outil requis n'est PAS ici : il doit etre fait par le code serveur (sinon recoltable a la main).\n"
                     "-- Modeles : GameObjectDisplayInfo.dbc (voir docs/RESOURCES.md).\n")
    text += "DELETE FROM `gameobject_template` WHERE `entry` BETWEEN 9101001 AND 9101999;\n"
    text += "DELETE FROM `gameobject_loot_template` WHERE `entry` BETWEEN 9101001 AND 9101999;\n"
    text += insert("gameobject_template", cols, rows) + "\n"
    text += insert("gameobject_loot_template", ["entry", "item", "ChanceOrQuestChance", "groupid", "mincountOrRef", "maxcount", "condition_id", "comments"], lrows) + "\n"
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
                     "-- (item = id de la reference, mincountOrRef = -id). Aucune ligne existante n'est modifiee.\n")
    text += "DELETE FROM `reference_loot_template` WHERE `entry` BETWEEN 8300000 AND 8399999;\n"
    text += "DELETE FROM `creature_loot_template` WHERE `item` BETWEEN 8300000 AND 8399999 AND `mincountOrRef` < 0;\n"
    cols = ["entry", "item", "ChanceOrQuestChance", "groupid", "mincountOrRef", "maxcount", "condition_id", "comments"]
    text += insert("reference_loot_template", cols, rrows) + "\n" + insert("creature_loot_template", cols, crows, 200) + "\n"
    write("004_loot.sql", text)
    print("references:", len(refs), "lignes ref:", len(rrows), "lignes creature:", len(crows), "lootid sans regle:", skipped)


# ------------------------------------------------------------------ 005 : apparitions de noeuds (VALIDATION uniquement)
MASS_ZONES = [(0, 12, "Elwynn Forest"), (1, 14, "Durotar"), (0, 1, "Dun Morogh")]
SPECIMEN_ZONES = [(0, 12, {9}), (1, 14, {363})]          # echantillon de chaque modele : Northshire Valley / Valley of Trials
N_WOOD, N_STONE = 14, 10
SPACING = 12.0


def _h(g):
    return zlib.crc32(("wl%d" % g).encode())


def gen_spawns():
    info = classify.load()
    ct = info["ct"]
    indoor = re.compile(rules.INDOOR_AREA_RE, re.I)
    cands = collections.defaultdict(list)       # (map, zone) -> [(guid, x, y, area_id)]
    for e, sps in info["spawns"].items():
        t = ct.get(e)
        if not t or t["why_not"] or t["level"] > 12 or t["rank"] != 0:
            continue
        for (m, x, y, zid, zn, aid, an, g) in sps:
            if not indoor.search(an):
                cands[(m, zid)].append((g, x, y, aid))
    # z / orientation lus dans la table creature
    need = {g for v in cands.values() for (g, _x, _y, _a) in v}
    pos = {}
    ids = sorted(need)
    for i in range(0, len(ids), 2000):
        for g, z, o in sql("select guid, position_z, orientation from creature where guid in (%s)" % ",".join(map(str, ids[i:i + 2000]))):
            pos[int(g)] = (float(z), float(o))
    chosen = []   # (map, node_entry, x, y, z, o, zone, note)
    used = collections.defaultdict(list)

    def free(m, x, y):
        return all((x - ux) ** 2 + (y - uy) ** 2 >= SPACING ** 2 for ux, uy in used[m])

    def take(m, zid, entry, cand_sorted, note):
        for (g, x, y, aid) in cand_sorted:
            if free(m, x, y):
                z, o = pos[g]
                used[m].append((x, y))
                chosen.append((m, entry, x, y, z, o, zid, note, g))
                return True
        return False

    t1_wood = [n["entry"] for n in rules.NODES if n["tier"] == 1 and n["kind"] == "bois"][0]
    t1_stone = [n["entry"] for n in rules.NODES if n["tier"] == 1 and n["kind"] == "pierre"][0]
    # 1) echantillons : un de chaque modele, au plus pres du centre de la zone de depart
    for m, zid, areas in SPECIMEN_ZONES:
        pool = cands[(m, zid)]
        start = [(x, y) for (g, x, y, a) in pool if a in areas]
        cx = statistics.mean(p[0] for p in start)
        cy = statistics.mean(p[1] for p in start)
        pool_s = sorted(pool, key=lambda c: (c[1] - cx) ** 2 + (c[2] - cy) ** 2)
        for n in rules.NODES:
            if not take(m, zid, n["entry"], pool_s, "echantillon"):
                print("AVERTISSEMENT : pas de place pour l'echantillon", n["name"], "zone", zid)
    # 2) masse de palier 1 : bois et pierre, positions tirees de facon deterministe parmi toute la zone
    for m, zid, zn in MASS_ZONES:
        pool = sorted(cands[(m, zid)], key=lambda c: _h(c[0]))
        for entry, count in ((t1_wood, N_WOOD), (t1_stone, N_STONE)):
            got = 0
            for c in pool:
                if got >= count:
                    break
                if take(m, zid, entry, [c], "masse"):
                    got += 1
            if got < count:
                print("AVERTISSEMENT : seulement", got, "/", count, "noeuds", entry, "dans", zn)
    rows = []
    guid = rules.NODE_GUID_BASE
    for (m, entry, x, y, z, o, zid, note, cg) in sorted(chosen, key=lambda c: (c[0], c[6], c[1], c[8])):
        n = rules.NODE[entry]
        rows.append([guid, entry, m, 1, round(x, 4), round(y, 4), round(z, 4), round(o, 6), 0, 0,
                     round(math.sin(o / 2), 8), round(math.cos(o / 2), 8), n["respawn"][0], n["respawn"][1]])
        guid += 1
    assert guid - 1 <= rules.NODE_GUID_MAX
    text = HEADER + ("-- 005 : apparitions de noeuds, ZONES DE VALIDATION UNIQUEMENT (Elwynn Forest, Durotar, Dun Morogh).\n"
                     "-- Positions = positions de creatures de la table `creature` (jamais inventees) ; guid 9500001-9599999.\n"
                     "-- Echantillon de chaque modele pres de Northshire / Valley of Trials, + noeuds de palier 1 dans les 3 zones.\n")
    text += "DELETE FROM `gameobject` WHERE `guid` BETWEEN %d AND %d;\n" % (rules.NODE_GUID_BASE, rules.NODE_GUID_MAX)
    text += insert("gameobject", ["guid", "id", "map", "spawnMask", "position_x", "position_y", "position_z", "orientation",
                                  "rotation0", "rotation1", "rotation2", "rotation3", "spawntimesecsmin", "spawntimesecsmax"], rows) + "\n"
    write("005_node_spawns.sql", text)
    print("noeuds:", len(rows), collections.Counter((r[2], r[1]) for r in rows).most_common(8))


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
    info = classify.load()
    zt = zone_tiers(info)
    rows = sql("select Entry,Name,coalesce(SubName,'') from creature_template where NpcFlags & 4 and (SubName regexp '^(General|Trade)' or SubName regexp 'Innkeeper|Mining|Blacksmith')")
    names = {int(r[0]): (r[1], r[2]) for r in rows}
    by_ct = collections.defaultdict(dict)   # (map, tier) -> {zone: (priorite, entry)}  priorite 0 = General/Trade, 1 = repli (aubergistes, fournisseurs...)
    for e in sorted(names):
        nm, sub = names[e]
        prio = 0 if VENDOR_SUBNAME.search(sub) else 1
        sps = info["spawns"].get(e, [])
        if not sps:
            continue
        zc = collections.Counter((s[0], s[3]) for s in sps)
        (m, zid), _n = zc.most_common(1)[0]
        if zid in CITY_ZONES or (m, zid) not in zt:
            continue
        cur = by_ct[(m, zt[(m, zid)][0])].get(zid)
        if cur is None or (prio, e) < cur:
            by_ct[(m, zt[(m, zid)][0])][zid] = (prio, e)
    chosen = []
    for (m, tier), zd in sorted(by_ct.items()):
        for zid, (prio, e) in sorted(zd.items(), key=lambda kv: (kv[1][0], kv[0]))[:VENDORS_PER_TIER_CONTINENT]:
            chosen.append((m, tier, zid, e))
    rows = []
    for (m, tier, zid, e) in chosen:
        items = [mm for mm in rules.MATERIALS if mm["tier"] == tier and mm["kind"] == "base"]
        for i, mm in enumerate(items):
            rows.append([e, mm["id"], 20, 1800, 200 + i, 0, "Wowlheim T%d secours (%s)" % (tier, names[e][0])])
    text = HEADER + ("-- 006 : source de secours des materiaux de BASE : stock LIMITE (20, reapprovisionne toutes les 30 min) chez des vendeurs\n"
                     "-- existants : en priorite « General.../Trade... », a defaut aubergistes/fournisseurs (zones sans marchand general) ; zones dont\n"
                     "-- le niveau median des creatures correspond au palier. Hors capitales.\n"
                     "-- Prix = prix de revente x10 (champ BuyPrice de l'objet). Les materiaux de passage et le bronze ne sont jamais vendus.\n")
    text += "DELETE FROM `npc_vendor` WHERE `item` BETWEEN 9200001 AND 9299999;\n"
    text += insert("npc_vendor", ["entry", "item", "maxcount", "incrtime", "slot", "condition_id", "comments"], rows) + "\n"
    write("006_vendors.sql", text)
    print("vendeurs:", [(m, t, zid, e, names[e][0], names[e][1]) for (m, t, zid, e) in chosen])


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in (("items", gen_items), ("nodes", gen_nodes), ("loot", gen_loot), ("spawns", gen_spawns), ("vendors", gen_vendors)):
        if what in ("all", name):
            fn()
