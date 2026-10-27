"""Classification des creatures pour le butin Wowlheim (lecture seule de la base du jeu).

Critere d'eligibilite d'un modele de creature (creature_template) :
  - Rank 0 (normal) ou 1 (elite) ; exclus : 2 (rare elite), 3 (boss), 4 (rare)
  - CreatureType hors 0 (inconnu), 8 (bete inoffensive/critter), 11 (totem)
  - LootId > 0 (on n'ajoute jamais de ligne de butin a une creature qui n'en a pas : ce serait modifier son comportement)
  - SEULE EXCEPTION aux deux regles precedentes (2026-10-26, materiaux animaux de Valheim) : les critters cerfs/biches/faons (modele
    CRITTER_GAME_MODELS) recoivent LootId = Entry (004) et la Peau de cerf : ce sont les seuls cervides de niveau < 15 du jeu ;
    idem gazelles et beliers (betes a cornes, categorie « cervide » etendue) et poules (Plumes). Type 1 : seulement les poules non amicales.
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

MAMMAL_FAMILIES = {1, 2, 4, 5, 9, 24, 25}   # loup, felin, ours, sanglier, gorille, chauve-souris, hyene (CreatureFamily.dbc de 1.12)
SPIDER_FAMILIES = {3}                   # araignee
BIRD_FAMILIES = {7, 12, 26}             # charognard, haut-trotteur, chouette (Plumes de Valheim)
WOLF_FAMILIES = {1}
BOAR_FAMILIES = {5}

# Materiaux ANIMAUX de Valheim (2026-10-26) : la categorie d'une bete / d'un humanoide se lit d'abord sur son MODELE 3D
# (creature_template.DisplayId1 -> CreatureDisplayInfo.dbc -> CreatureModelData.dbc : dossier « Creature\<Dossier>\... »), plus fiable
# que le nom ; famille et nom servent de repli. Equivalences Valheim (CharacterDrop des prefabs) :
#   Deer -> Peau de cerf (+ Bois dur : Eikthyr est un cerf) ; Boar -> Bouts de cuir ; Wolf -> Peau de loup (+ Griffes : Fenring) ;
#   Lox -> Peau de Lox ; Troll -> Peau de troll ; Seagal/Crow -> Plumes ; Skeleton -> Fragments d'os ; Draugr -> Entrailles.
# « cervide » ETENDU (2026-10-26, demande de la coordination : le Bois dur ouvre la pioche, donc le cuivre ; il doit etre obtenable au palier 1
# pres de chaque depart) : betes a bois ou a cornes equivalentes = cerfs, biches, faons, beliers (Ram), gazelles, zhevras (modele « Unicorn »)
MODEL_DEER = {"stag", "deer", "ram", "gazelle", "unicorn"}
MODEL_WOLF = {"wolf", "direwolf"}                                     # loups, worgs, coyotes
MODEL_BOAR = {"boar"}
MODEL_LOX = {"kodobeast", "thunderlizard", "diemetradon", "giraffe"}  # grands herbivores : kodos, lezards-tonnerre/stegodons, dimetrodons, girafes
MODEL_BIRD = {"hippogryph", "gryphon", "owl", "carrionbird", "tallstrider", "chicken"}
MODEL_TROLL = {"troll", "foresttroll", "icetroll", "trollmale", "trollfemale"}
MODEL_OGRE = {"ogre", "ogremage", "ogrewarlord", "twoheadedogre", "ettin"}
MODEL_HARPY = {"harpy"}
# « gibier » SANS butin dans WoW (critters type 8, ou betes LootId 0) auxquels on DONNE un butin (generate.py : LootId = Entry dans 004) :
#   cerfs/biches/faons (Valheim Deer, premier gibier ; les seuls cervides de niveau < 15 de WoW sont ces critters) -> Peau de cerf, Bois dur ;
#   poules (Valheim Hen/Chicken -> Plumes ; seuls oiseaux de palier 1 de Dun Morogh, Elwynn, Tirisfal).
CRITTER_GAME_MODELS = MODEL_DEER | {"chicken"}
TYPE1_GAME_MODELS = {"chicken"}      # betes type 1 sans butin dotees : poules seulement (beliers type 1 = montures d'ecurie amicales, exclus)
FRIENDLY_FACTIONS = {35}

_model_cache = None


def model_folders(db=GAME_DB):
    """{Entry: dossier du modele en minuscules} (DisplayId1)."""
    global _model_cache
    if _model_cache is None:
        from common import read_dbc
        r, s = read_dbc("CreatureModelData.dbc")
        mpath = {x[0]: s(x[2]) for x in r}
        r2, _s = read_dbc("CreatureDisplayInfo.dbc")
        dmodel = {x[0]: x[1] for x in r2}
        out = {}
        for e, d in sql("select Entry,DisplayId1 from creature_template", db):
            p = mpath.get(dmodel.get(int(d), 0), "")
            parts = p.replace("/", "\\").split("\\")
            out[int(e)] = parts[1].lower() if len(parts) > 2 else ""
        _model_cache = out
    return _model_cache


def category(ctype, family, name, model=""):
    if ctype == 7:
        if model in MODEL_TROLL:
            return "TROLL"
        if model in MODEL_OGRE:
            return "OGRE"
        if model in MODEL_HARPY:
            return "HARPY"
        if RE_LOGGER.search(name):
            return "LOGGER"
        if RE_MINER.search(name):
            return "MINER"
        if RE_BRUTE.search(name):
            return "BRUTE"
        return "HUMANOID"
    if ctype == 1 or (ctype == 8 and model in CRITTER_GAME_MODELS):
        if family in SPIDER_FAMILIES:
            return "BEAST_SPIDER"
        if RE_BASILISK.search(name):
            return "BEAST_BASILISK"
        if model in MODEL_DEER:
            return "BEAST_DEER"
        if family in WOLF_FAMILIES or model in MODEL_WOLF:
            return "BEAST_WOLF"
        if family in BOAR_FAMILIES or model in MODEL_BOAR:
            return "BEAST_BOAR"
        if model in MODEL_LOX:
            return "BEAST_LOX"
        if family in BIRD_FAMILIES or model in MODEL_BIRD:
            return "BEAST_BIRD"
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
    cols = "Entry,Name,MinLevel,MaxLevel,CreatureType,Family,`Rank`,LootId,NpcFlags,Civilian,ExtraFlags,Faction"
    ct = {}
    for r in sql(f"select {cols} from creature_template", db):
        ct[int(r[0])] = dict(entry=int(r[0]), name=r[1], minlvl=int(r[2]), maxlvl=int(r[3]), type=int(r[4]), family=int(r[5]),
                             rank=int(r[6]), lootid=int(r[7]), npcflags=int(r[8]), civ=int(r[9]), extra=int(r[10]), faction=int(r[11]))
    # apparitions hors continents (instances, champs de bataille) : lecture directe de la base du jeu
    other = set()
    for (e,) in sql("select distinct if(c.id=0, e.entry, c.id) from creature c left join creature_spawn_entry e on c.id=0 and e.guid=c.guid "
                    "where c.map not in (0,1)", db):
        if e:
            other.add(int(e))
    sp = load_spawns()
    models = model_folders(db)
    used_lootids = {t["lootid"] for t in ct.values() if t["lootid"]}
    reasons = collections.Counter()
    for e, t in ct.items():
        lv = (t["minlvl"] + t["maxlvl"]) / 2.0
        t["level"] = lv
        t["tier"] = rules.tier_of_level(lv)
        t["elite"] = t["rank"] == 1
        t["nspawn"] = len(sp.get(e, []))
        t["model"] = models.get(e, "")
        t["new_lootid"] = False
        t["game_critter"] = False
        if (t["model"] in CRITTER_GAME_MODELS and t["rank"] == 0 and t["faction"] not in FRIENDLY_FACTIONS
                and (t["type"] == 8 or (t["type"] == 1 and t["model"] in TYPE1_GAME_MODELS))):
            # gibier critter (cerf, biche) : butin cree par 004 (LootId = Entry ; la ligne de creature_template est mise a jour par 004).
            # Sur une base ou 004 est deja applique, LootId == Entry : meme traitement.
            if t["lootid"] == 0 and e not in used_lootids:
                t["lootid"] = e
                t["new_lootid"] = True
            # (bete type 1 deja dotee par 004 : LootId == Entry comme une bete ordinaire, aucune exception necessaire)
            t["game_critter"] = t["new_lootid"] or (t["type"] == 8 and t["lootid"] == e)
        why = None
        if t["lootid"] == 0:
            why = "LootId = 0 (aucun butin existant)"
        elif t["rank"] not in (0, 1):
            why = "rang %d (rare/rare elite/boss)" % t["rank"]
        elif t["type"] in (0, 8, 11) and not t["game_critter"]:
            why = "type de creature %d (inconnu/critter/totem)" % t["type"]
        elif t["npcflags"] & ~3:
            why = "drapeaux PNJ (vendeur, entraineur...)"
        elif t["civ"] or t["extra"] & (0x400 | 0x10000):
            why = "garde/civil"
        elif e in other and not t["game_critter"]:
            # (gibier critter : le cerf 883 a 2 apparitions decoratives dans Hache-tripes ; une Peau de cerf y est sans consequence)
            why = "apparait aussi en instance/champ de bataille"
        elif t["nspawn"] == 0:
            why = "aucune apparition sur les cartes 0/1"
        t["why_not"] = why
        t["cat"] = None if why else category(t["type"], t["family"], t["name"], t["model"])
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
