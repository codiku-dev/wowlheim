"""Classification des creatures pour le butin Wowlheim (lecture seule de la base du jeu).

Critere d'eligibilite d'un modele de creature (creature_template) :
  - Rank 0 (normal) ou 1 (elite) ; exclus : 2 (rare elite), 3 (boss), 4 (rare)
  - CreatureType hors 0 (inconnu), 8 (bete inoffensive/critter), 11 (totem)
  - LootId > 0 (on n'ajoute jamais de ligne de butin a une creature qui n'en a pas : ce serait modifier son comportement)
  - NpcFlags sans autre bit que gossip/questgiver (1, 2) : exclut vendeurs, entraineurs, etc.
  - ni Civilian, ni ExtraFlags GUARD/CIVILIAN
  - toutes ses apparitions sont sur les cartes 0 ou 1 (aucune dans une instance/champ de bataille) et au moins une existe
Critere d'eligibilite d'un LootId : TOUS les modeles qui le partagent sont eligibles, de meme palier ; sinon exclu
(un butin partage avec un boss d'instance ou entre paliers differents serait « dangereux »)."""
import os, re, sys, collections
sys.path.insert(0, os.path.dirname(__file__))
from common import sql, GAME_DB
import rules

HERE = os.path.dirname(__file__)

RE_MINER = re.compile(r"\b(Miner|Trogg|Kobold|Digger|Prospector|Excavator|Geomancer|Dark Iron|Thaurissan|Rockjaw|Pickaxe|Quarry|Mason|Smelter|Forgemaster|Overseer|Taskmaster)\b", re.I)
RE_LOGGER = re.compile(r"\b(Logger|Lumberjack|Woodcutter|Lumber|Sawmill)\b", re.I)
RE_BRUTE = re.compile(r"\b(Troll|Ogre|Gnoll|Ettin|Brute|Mosh'Ogg|Gor'dok|Bloodscalp|Mauler)\b", re.I)
RE_MAMMAL_NAME = re.compile(r"\b(Wolf|Worg|Bear|Boar|Cat|Lion|Lioness|Tiger|Panther|Cougar|Kodo|Yeti|Hyena|Gorilla|Ape|Mammoth|Elk|Stag|Ram|Goat|Cub|Saber|Frostsaber|Leopard|Jaguar|Basilisk)\b", re.I)
RE_BASILISK = re.compile(r"Basilisk", re.I)
RE_ROCK = re.compile(r"(Rock|Stone|Golem|Earth|Magma|Lava|Obsidian|Granite|Gravel|Boulder|Basalt|Rubble|Slag|Ember|Geode|Gem|Mineral|Crystal)", re.I)
RE_PLANT = re.compile(r"(Timber|Oakenscowl|Treant|Creeper|Lasher|Moss|Thorn|Vine|Bramble|Strangler|\bFen\b|\bEnt\b|Ancient Protector|Bark|Tree|Root|Sapling|Leafbeard|Venomlash|Spore|Petal|Bloom|Blossom|Trapper)", re.I)

MAMMAL_FAMILIES = {1, 2, 4, 5, 9, 25}   # loup, felin, ours, sanglier, gorille, hyene (CreatureFamily.dbc de 1.12)
SPIDER_FAMILIES = {3}                   # araignee


def category(ctype, family, name):
    if ctype == 7:
        if RE_LOGGER.search(name):
            return "LOGGER"
        if RE_MINER.search(name):
            return "MINER"
        if RE_BRUTE.search(name):
            return "BRUTE"
        return "HUMANOID"
    if ctype == 1:
        if family in SPIDER_FAMILIES:
            return "BEAST_SPIDER"
        if RE_BASILISK.search(name):
            return "BEAST_BASILISK"
        if family in MAMMAL_FAMILIES or (family == 0 and RE_MAMMAL_NAME.search(name)):
            return "BEAST_MAMMAL"
        return "BEAST_OTHER"
    if ctype == 6:
        return "UNDEAD"
    if ctype == 4:
        if RE_PLANT.search(name):
            return "ELEM_PLANT"
        if RE_ROCK.search(name):
            return "ELEM_ROCK"
        return "ELEM_OTHER"
    return {5: "GIANT", 9: "MECH", 2: "DRAGONKIN", 3: "DEMON", 10: "OTHER"}.get(ctype)


def ancestors(cat):
    out = [cat]
    while cat in rules.CAT_PARENT:
        cat = rules.CAT_PARENT[cat]
        out.append(cat)
    return out


def load_spawns():
    """cache/spawns.tsv (cf. build_cache.py) -> {entry: [(map, x, y, zone_id, zone_name, area_id, area_name)]}"""
    p = os.path.join(HERE, "cache", "spawns.tsv")
    if not os.path.exists(p):
        raise SystemExit("cache/spawns.tsv absent : lancer build_cache.py")
    sp = collections.defaultdict(list)
    for l in open(p, encoding="utf8"):
        g, e, m, x, y, zid, zn, aid, an = l.rstrip("\n").split("\t")
        sp[int(e)].append((int(m), float(x), float(y), int(zid), zn, int(aid), an, int(g)))
    return sp


def load(db=GAME_DB):
    """Retourne un dict avec modeles, eligibilite par modele, par LootId, et compteurs d'exclusion."""
    cols = "Entry,Name,MinLevel,MaxLevel,CreatureType,Family,`Rank`,LootId,NpcFlags,Civilian,ExtraFlags"
    ct = {}
    for r in sql(f"select {cols} from creature_template", db):
        ct[int(r[0])] = dict(entry=int(r[0]), name=r[1], minlvl=int(r[2]), maxlvl=int(r[3]), type=int(r[4]), family=int(r[5]),
                             rank=int(r[6]), lootid=int(r[7]), npcflags=int(r[8]), civ=int(r[9]), extra=int(r[10]))
    # apparitions hors continents (instances, champs de bataille) : lecture directe de la base du jeu
    other = set()
    for (e,) in sql("select distinct if(c.id=0, e.entry, c.id) from creature c left join creature_spawn_entry e on c.id=0 and e.guid=c.guid "
                    "where c.map not in (0,1)", db):
        if e:
            other.add(int(e))
    sp = load_spawns()
    reasons = collections.Counter()
    for e, t in ct.items():
        lv = (t["minlvl"] + t["maxlvl"]) / 2.0
        t["level"] = lv
        t["tier"] = rules.tier_of_level(lv)
        t["elite"] = t["rank"] == 1
        t["nspawn"] = len(sp.get(e, []))
        why = None
        if t["lootid"] == 0:
            why = "LootId = 0 (aucun butin existant)"
        elif t["rank"] not in (0, 1):
            why = "rang %d (rare/rare elite/boss)" % t["rank"]
        elif t["type"] in (0, 8, 11):
            why = "type de creature %d (inconnu/critter/totem)" % t["type"]
        elif t["npcflags"] & ~3:
            why = "drapeaux PNJ (vendeur, entraineur...)"
        elif t["civ"] or t["extra"] & (0x400 | 0x10000):
            why = "garde/civil"
        elif e in other:
            why = "apparait aussi en instance/champ de bataille"
        elif t["nspawn"] == 0:
            why = "aucune apparition sur les cartes 0/1"
        t["why_not"] = why
        t["cat"] = None if why else category(t["type"], t["family"], t["name"])
        if not why and t["cat"] is None:
            t["why_not"] = "categorie non attribuable (type %d)" % t["type"]
        if t["why_not"]:
            reasons[t["why_not"].split(" (")[0]] += 1
    # LootId partages
    groups = collections.defaultdict(list)
    for t in ct.values():
        if t["lootid"]:
            groups[t["lootid"]].append(t)
    loot_ok, loot_bad = {}, {}
    for lid, ms in groups.items():
        bad = None
        if any(m["why_not"] for m in ms):
            # un modele de ce groupe est inelligible (boss, instance, etc.) : on n'y touche pas
            bad = "partage avec un modele inelligible (%s)" % next(m["why_not"] for m in ms if m["why_not"]).split(" (")[0]
        elif len({m["tier"] for m in ms}) > 1:
            bad = "partage entre paliers differents"
        elif len({m["cat"] for m in ms}) > 1:
            bad = "partage entre categories differentes"
        if bad:
            loot_bad[lid] = (bad, ms)
        else:
            loot_ok[lid] = ms
    return dict(ct=ct, spawns=sp, reasons=reasons, loot_ok=loot_ok, loot_bad=loot_bad, groups=groups)


def eligible_lootids(info):
    """{lootid: (tier, cat, elite_all)} : elite si TOUS les modeles du groupe sont elites (sinon 1 tirage)."""
    out = {}
    for lid, ms in info["loot_ok"].items():
        out[lid] = (ms[0]["tier"], ms[0]["cat"], all(m["elite"] for m in ms))
    return out
