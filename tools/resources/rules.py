"""Wowlheim - definitions de ressources (SOURCE UNIQUE de verite pour les generateurs et check.py).

Rien de ce qui est ecrit en SQL n'est saisi a la main : 002_items.sql ... 006_vendors.sql sont generes depuis ce fichier
et depuis des lectures de la base du jeu (classicmangos, lecture seule)."""

# ------------------------------------------------------------------ paliers
# (numero, nom, niveau min inclus, niveau max exclu) ; le niveau d'une creature = (MinLevel+MaxLevel)/2.
# Le cahier donne 1-15 / 15-28 / 28-40 / 40-52 / 52-60 : choix retenu = borne basse incluse, borne haute exclue.
TIERS = [
    (1, "Prairie", 0, 15),
    (2, "Foret noire", 15, 28),
    (3, "Marais", 28, 40),
    (4, "Montagne", 40, 52),
    (5, "Plaines", 52, 999),
]


def tier_of_level(lv):
    for t, _n, lo, hi in TIERS:
        if lo <= lv < hi:
            return t
    return 5


# ------------------------------------------------------------------ objets (materiaux)
# kind : base = materiau de base (taux 30-60 % exige) ; passage = materiau de passage (92000x9) ; crafted = fabrique, sans butin
# display = displayid d'un objet EXISTANT de item_template (donc valide cote client) ; buy/sell en cuivre.
def _mat(id_, name, tier, kind, display, quality=1):
    return dict(id=id_, name=name, tier=tier, kind=kind, display=display, quality=quality)


MATERIALS = [
    _mat(9200001, "Bois", 1, "base", 7375),
    _mat(9200002, "Pierre", 1, "base", 4714),
    _mat(9200003, "Silex", 1, "base", 18107),
    _mat(9200004, "Résine", 1, "base", 8283),
    _mat(9200005, "Peau de cerf", 1, "base", 6687),
    _mat(9200006, "Chutes de cuir", 1, "base", 7400),
    _mat(9200009, "Andouiller", 1, "passage", 7999, 2),
    _mat(9200011, "Bois fin", 2, "base", 7290),
    _mat(9200012, "Bois de cœur", 2, "base", 13458),
    _mat(9200013, "Cuivre", 2, "base", 4681),
    _mat(9200014, "Étain", 2, "base", 4690),
    _mat(9200015, "Bronze", 2, "crafted", 7390),
    _mat(9200016, "Peau de troll", 2, "base", 6684),
    _mat(9200019, "Œil de gréling", 2, "passage", 7394, 2),
    _mat(9200021, "Fer", 3, "base", 4689),
    _mat(9200022, "Écorce ancienne", 3, "base", 7149),
    _mat(9200023, "Fragments d'os", 3, "base", 7350),
    _mat(9200024, "Entrailles", 3, "base", 1116),
    _mat(9200029, "Noyau de Surtling", 3, "passage", 8560, 2),
    _mat(9200031, "Argent", 4, "base", 7355),
    _mat(9200032, "Obsidienne", 4, "base", 20769),
    _mat(9200033, "Fourrure de loup", 4, "base", 7294),
    _mat(9200034, "Cristal", 4, "base", 6546),
    _mat(9200039, "Glande de gel", 4, "passage", 4045, 2),
    _mat(9200041, "Métal noir", 5, "base", 20658),
    _mat(9200042, "Lin", 5, "base", 7383),
    _mat(9200043, "Fil de lin", 5, "base", 4752),
    _mat(9200044, "Peau de lox", 5, "base", 6698),
    _mat(9200049, "Noyau noir", 5, "passage", 17922, 2),
]
MAT = {m["id"]: m for m in MATERIALS}
STACK = 100          # taille de pile des materiaux
SELL_BASE = 4        # cuivre : prix de revente d'un materiau de base de palier 1 (x3 par palier)
BUY_FACTOR = 10      # prix chez le vendeur = revente x 10 (« prix eleve » : voir docs)


def sell_price(m):
    p = SELL_BASE * 3 ** (m["tier"] - 1)
    return {"base": p, "passage": p * 5, "crafted": p * 2}[m["kind"]]


def buy_price(m):
    """0 = non vendu par les PNJ (passage, fabrique)."""
    return sell_price(m) * BUY_FACTOR if m["kind"] == "base" else 0


# ------------------------------------------------------------------ outils (armes a faibles degats, classe 2 sous-classe 14 « Divers » comme le Pic de mineur : aucune maitrise d'arme requise)
# id = 9201000 + palier*10 + (1 hache | 2 pic)
TOOLS = []
_tool_names = {
    1: ("Hache en silex", "Pic en andouiller"),
    2: ("Hache de bronze", "Pic de bronze"),
    3: ("Hache de fer", "Pic de fer"),
    4: ("Hache d'argent", "Pic d'argent"),
    5: ("Hache de métal noir", "Pic de métal noir"),
}
_tool_dmg = {1: (1, 3), 2: (2, 5), 3: (4, 8), 4: (6, 12), 5: (8, 16)}
_tool_req = {1: 1, 2: 15, 3: 28, 4: 40, 5: 52}
# modeles : axe = « Monster - Axe, Stone Basic » / « Metal Basic » ; pic = « Mining Pick » / « Monster - Item, Pick »
_tool_disp = {
    ("hache", 1): 7429, ("hache", 2): 7428, ("hache", 3): 7428, ("hache", 4): 7426, ("hache", 5): 7427,
    ("pic", 1): 7493, ("pic", 2): 6568, ("pic", 3): 6568, ("pic", 4): 14039, ("pic", 5): 14039,
}
for _t in range(1, 6):
    for _i, _k in enumerate(("hache", "pic")):
        TOOLS.append(dict(id=9201000 + _t * 10 + 1 + _i, kind=_k, tier=_t, name=_tool_names[_t][_i],
                          display=_tool_disp[(_k, _t)], dmg=_tool_dmg[_t], req=_tool_req[_t]))

# Recettes PROPOSEES (non implementees : la table de recettes vivra dans le code serveur). (station, [(id, qte)])
TOOL_RECIPES = {
    9201011: ("Établi", [(9200001, 4), (9200003, 3), (9200004, 1)]),
    9201012: ("Établi", [(9200001, 4), (9200009, 2), (9200006, 2)]),
    9201021: ("Forge", [(9200011, 4), (9200015, 5), (9200012, 1), (9200004, 2)]),
    9201022: ("Forge", [(9200011, 3), (9200015, 6), (9200019, 2), (9200016, 2)]),
    9201031: ("Forge", [(9200012, 4), (9200021, 6), (9200022, 2), (9200006, 2)]),
    9201032: ("Forge", [(9200012, 3), (9200021, 8), (9200029, 2), (9200023, 2)]),
    9201041: ("Forge", [(9200012, 4), (9200031, 6), (9200033, 2), (9200034, 2)]),
    9201042: ("Forge", [(9200012, 3), (9200031, 8), (9200039, 2), (9200032, 2)]),
    9201051: ("Forge", [(9200012, 4), (9200041, 6), (9200043, 3), (9200044, 2)]),
    9201052: ("Forge", [(9200012, 3), (9200041, 8), (9200049, 2), (9200044, 2)]),
}
# Conversions PROPOSEES (source de secours, non implementees ; station -> code serveur)
CONVERSIONS = [
    ("Forge", [(9200013, 2), (9200014, 1)], (9200015, 2), "Bronze (seul moyen d'en obtenir : il n'y a pas de butin)"),
    ("Établi", [(9200042, 2)], (9200043, 1), "Fil de lin depuis le lin"),
    ("Établi", [(9200001, 5)], (9200011, 1), "Bois fin depuis le bois (secours palier 1 -> 2)"),
    ("Établi", [(9200011, 5)], (9200012, 1), "Bois de cœur depuis le bois fin"),
    ("Forge", [(9200002, 6)], (9200003, 2), "Silex depuis la pierre (secours)"),
    ("Établi", [(9200005, 3)], (9200006, 4), "Chutes de cuir depuis la peau de cerf"),
]

# ------------------------------------------------------------------ categories de creatures
# Categorie principale determinee par (CreatureType, Family, nom) dans classify.py ; heritage pour les regles ci-dessous.
CAT_PARENT = {
    "MINER": "HUMANOID", "LOGGER": "HUMANOID", "BRUTE": "HUMANOID",
    "BEAST_MAMMAL": "BEAST", "BEAST_OTHER": "BEAST", "BEAST_SPIDER": "BEAST", "BEAST_BASILISK": "BEAST_OTHER",
    "ELEM_ROCK": "ELEMENTAL", "ELEM_PLANT": "ELEMENTAL", "ELEM_OTHER": "ELEMENTAL",
}
ALL_CATS = ["HUMANOID", "MINER", "LOGGER", "BRUTE", "BEAST", "BEAST_MAMMAL", "BEAST_OTHER", "BEAST_SPIDER", "BEAST_BASILISK",
            "UNDEAD", "ELEMENTAL", "ELEM_ROCK", "ELEM_PLANT", "ELEM_OTHER", "GIANT", "MECH", "DRAGONKIN", "DEMON", "OTHER"]
# categories attribuables a une creature (feuilles ; HUMANOID/BEAST/ELEMENTAL generiques sont aussi des categories finales)
ASSIGNABLE = ["HUMANOID", "MINER", "LOGGER", "BRUTE", "BEAST_MAMMAL", "BEAST_OTHER", "BEAST_SPIDER", "BEAST_BASILISK",
              "UNDEAD", "ELEM_ROCK", "ELEM_PLANT", "ELEM_OTHER", "GIANT", "MECH", "DRAGONKIN", "DEMON", "OTHER"]

# Regles de butin : item -> [(categorie, chance %, min, max)]. Palier de la creature = palier de l'objet (ou palier+1 : retour en arriere).
DROP_RULES = {
    9200001: [("LOGGER", 50, 1, 3), ("ELEM_PLANT", 50, 1, 3), ("GIANT", 25, 1, 2), ("HUMANOID", 20, 1, 2)],
    9200002: [("MINER", 50, 1, 3), ("ELEM_ROCK", 50, 1, 3), ("GIANT", 40, 1, 3), ("MECH", 30, 1, 2), ("HUMANOID", 15, 1, 2)],
    9200003: [("MINER", 40, 1, 2), ("BRUTE", 30, 1, 2), ("ELEM_ROCK", 30, 1, 2), ("HUMANOID", 25, 1, 2)],
    9200004: [("ELEM_PLANT", 45, 1, 2), ("BEAST_SPIDER", 30, 1, 2), ("HUMANOID", 10, 1, 1)],
    9200005: [("BEAST_MAMMAL", 50, 1, 2), ("BEAST_OTHER", 20, 1, 1)],
    9200006: [("BRUTE", 45, 1, 3), ("HUMANOID", 45, 1, 3), ("BEAST_MAMMAL", 30, 1, 2), ("UNDEAD", 25, 1, 2)],
    9200009: [("BEAST_MAMMAL", 8, 1, 1), ("BEAST_OTHER", 3, 1, 1), ("HUMANOID", 3, 1, 1)],
    9200011: [("LOGGER", 50, 1, 3), ("ELEM_PLANT", 50, 1, 3), ("GIANT", 25, 1, 2), ("HUMANOID", 20, 1, 2)],
    9200012: [("ELEM_PLANT", 35, 1, 2), ("LOGGER", 30, 1, 2), ("GIANT", 30, 1, 2), ("HUMANOID", 8, 1, 1)],
    9200013: [("MINER", 45, 1, 3), ("ELEM_ROCK", 40, 1, 2), ("MECH", 30, 1, 2), ("HUMANOID", 15, 1, 2)],
    9200014: [("MINER", 40, 1, 2), ("ELEM_ROCK", 35, 1, 2), ("MECH", 25, 1, 2), ("HUMANOID", 12, 1, 1)],
    9200016: [("GIANT", 50, 1, 2), ("BRUTE", 45, 1, 2), ("BEAST_MAMMAL", 25, 1, 1)],
    9200019: [("ELEM_PLANT", 10, 1, 1), ("BEAST_SPIDER", 6, 1, 1), ("BRUTE", 6, 1, 1), ("HUMANOID", 3, 1, 1)],
    9200021: [("MINER", 45, 1, 3), ("ELEM_ROCK", 40, 1, 2), ("MECH", 35, 1, 2), ("GIANT", 20, 1, 2), ("HUMANOID", 12, 1, 2)],
    9200022: [("ELEM_PLANT", 45, 1, 3), ("LOGGER", 35, 1, 2), ("GIANT", 30, 1, 2), ("OTHER", 15, 1, 2), ("HUMANOID", 10, 1, 1)],
    9200023: [("UNDEAD", 50, 1, 3), ("BEAST", 20, 1, 2), ("HUMANOID", 12, 1, 2)],
    9200024: [("BEAST", 45, 1, 2), ("OTHER", 20, 1, 2)],
    9200029: [("ELEM_OTHER", 10, 1, 1), ("DEMON", 10, 1, 1), ("ELEM_ROCK", 8, 1, 1), ("UNDEAD", 4, 1, 1)],
    9200031: [("MINER", 40, 1, 2), ("ELEM_ROCK", 35, 1, 2), ("MECH", 30, 1, 2), ("DRAGONKIN", 20, 1, 2), ("HUMANOID", 10, 1, 1)],
    9200032: [("ELEM_ROCK", 40, 1, 2), ("DRAGONKIN", 35, 1, 2), ("GIANT", 30, 1, 2), ("MINER", 25, 1, 2), ("DEMON", 20, 1, 2)],
    9200033: [("BEAST_MAMMAL", 50, 1, 2)],
    9200034: [("BEAST_BASILISK", 40, 1, 2), ("ELEM_ROCK", 30, 1, 2), ("GIANT", 20, 1, 2), ("DRAGONKIN", 15, 1, 2), ("ELEM_OTHER", 15, 1, 2)],
    9200039: [("DRAGONKIN", 10, 1, 1), ("ELEM_OTHER", 8, 1, 1), ("BEAST_MAMMAL", 7, 1, 1)],
    9200041: [("MINER", 40, 1, 2), ("ELEM_ROCK", 35, 1, 2), ("MECH", 35, 1, 2), ("DEMON", 25, 1, 2), ("GIANT", 20, 1, 2), ("HUMANOID", 12, 1, 1)],
    9200042: [("ELEM_PLANT", 40, 1, 3), ("HUMANOID", 25, 1, 3), ("UNDEAD", 15, 1, 2)],
    9200043: [("HUMANOID", 35, 1, 3), ("ELEM_PLANT", 25, 1, 2), ("UNDEAD", 25, 1, 2)],
    9200044: [("BEAST_MAMMAL", 50, 1, 2), ("BEAST_OTHER", 25, 1, 2)],
    9200049: [("DRAGONKIN", 10, 1, 1), ("DEMON", 10, 1, 1), ("ELEM_ROCK", 8, 1, 1), ("MECH", 8, 1, 1), ("UNDEAD", 5, 1, 1)],
}
BACK_FACTOR = 0.35   # retour en arriere : un monstre de palier t lache aussi les materiaux de BASE du palier t-1 a 35 % du taux
BACK_MIN = 8         # (plancher en %)
ELITE_REPEAT = 2     # elites normales : la reference est tiree 2 fois

# ------------------------------------------------------------------ noeuds de ressources (gameobject_template, type 3 CHEST)
# displays : GameObjectDisplayInfo.dbc (verifie par generation : l'id doit exister dans le DBC extrait) ; size copie des filons vanilla (0.5)
def _node(entry, name, tier, kind, display, size, loot, respawn):
    return dict(entry=entry, name=name, tier=tier, kind=kind, display=display, size=size, loot=loot, respawn=respawn)


WOOD_RESPAWN = (120, 180)
STONE_RESPAWN = (150, 210)
ORE_RESPAWN = (300, 420)
CACHE_RESPAWN = (900, 1200)

NODES = [
    _node(9101001, "Arbre de la prairie", 1, "bois", 5975, 1.0, [(9200001, 100, 2, 4), (9200004, 25, 1, 2)], WOOD_RESPAWN),
    _node(9101002, "Arbre de la forêt noire", 2, "bois", 927, 1.0, [(9200011, 100, 2, 4), (9200012, 30, 1, 2), (9200004, 20, 1, 2)], WOOD_RESPAWN),
    _node(9101003, "Vieille souche du marais", 3, "bois", 2474, 1.0, [(9200022, 100, 1, 3), (9200012, 50, 1, 2)], WOOD_RESPAWN),
    _node(9101004, "Pin de montagne", 4, "bois", 6158, 1.0, [(9200012, 100, 2, 4), (9200004, 20, 1, 2)], WOOD_RESPAWN),
    _node(9101005, "Arbre des plaines", 5, "bois", 967, 1.0, [(9200012, 100, 2, 4), (9200004, 20, 1, 2)], WOOD_RESPAWN),
    _node(9101011, "Rocher de la prairie", 1, "pierre", 4315, 1.0, [(9200002, 100, 2, 4), (9200003, 40, 1, 2)], STONE_RESPAWN),
    _node(9101012, "Rocher moussu", 2, "pierre", 248, 1.0, [(9200002, 100, 2, 4), (9200003, 30, 1, 2)], STONE_RESPAWN),
    _node(9101013, "Rocher du marais", 3, "pierre", 3992, 1.0, [(9200002, 100, 2, 4)], STONE_RESPAWN),
    _node(9101014, "Rocher de montagne", 4, "pierre", 5737, 1.0, [(9200002, 100, 2, 4)], STONE_RESPAWN),
    _node(9101015, "Rocher des plaines", 5, "pierre", 4320, 1.0, [(9200002, 100, 2, 4)], STONE_RESPAWN),
    _node(9101021, "Filon de cuivre", 2, "minerai", 310, 0.5, [(9200013, 100, 2, 4)], ORE_RESPAWN),
    _node(9101022, "Filon d'étain", 2, "minerai", 315, 0.5, [(9200014, 100, 2, 4)], ORE_RESPAWN),
    _node(9101023, "Gisement de fer", 3, "minerai", 312, 0.5, [(9200021, 100, 2, 4)], ORE_RESPAWN),
    _node(9101024, "Filon d'argent", 4, "minerai", 314, 0.5, [(9200031, 100, 2, 4)], ORE_RESPAWN),
    _node(9101025, "Filon de métal noir", 5, "minerai", 3951, 0.5, [(9200041, 100, 2, 4)], ORE_RESPAWN),
    _node(9101026, "Gisement d'obsidienne", 4, "minerai", 6650, 0.5, [(9200032, 100, 2, 3)], ORE_RESPAWN),
    _node(9101027, "Formation de cristal", 4, "minerai", 2971, 1.0, [(9200034, 100, 2, 3)], ORE_RESPAWN),
    _node(9101031, "Plant de lin", 5, "plante", 2315, 0.6, [(9200042, 100, 2, 4)], WOOD_RESPAWN),
    _node(9101041, "Ossements de cerf", 1, "passage", 6328, 1.0, [(9200009, 100, 1, 2)], CACHE_RESPAWN),
    _node(9101042, "Racines de gréling", 2, "passage", 148, 1.0, [(9200019, 100, 1, 2)], CACHE_RESPAWN),
    _node(9101043, "Roche de Surtling", 3, "passage", 3711, 1.0, [(9200029, 100, 1, 2)], CACHE_RESPAWN),
    _node(9101044, "Cristal de givre", 4, "passage", 2975, 1.0, [(9200039, 100, 1, 2)], CACHE_RESPAWN),
    _node(9101045, "Amas de noyaux noirs", 5, "passage", 2571, 1.0, [(9200049, 100, 1, 2)], CACHE_RESPAWN),
]
NODE = {n["entry"]: n for n in NODES}
NODE_GUID_BASE = 9500001
NODE_GUID_MAX = 9599999

# ------------------------------------------------------------------ butin de reference
REF_BASE = 8300000   # reference = REF_BASE + palier*1000 + index de categorie (ALL_CATS) * 10. NB : 9300000+ est IMPOSSIBLE : creature_loot_template.mincountOrRef est un MEDIUMINT SIGNE (min -8388608) et une reference y est stockee en negatif

# ------------------------------------------------------------------ zones : faction d'acces (classification MANUELLE, non verifiee par les donnees)
ZONE_FACTION = {
    # Royaumes de l'Est (carte 0)
    12: "A", 1: "A", 40: "A", 38: "A", 44: "A", 10: "A", 1519: "A", 11: "A",
    85: "H", 130: "H", 1497: "H",
    # Kalimdor (carte 1)
    141: "A", 148: "A", 1657: "A",
    14: "H", 215: "H", 17: "H", 1637: "H", 1638: "H",
}   # toute autre zone : contestee (« C »), accessible aux deux factions


def zone_faction(zid):
    return ZONE_FACTION.get(zid, "C")


# Zones exclues des spawns de validation / vendeurs : sous-zones souterraines ou interieures (filtre sur le nom d'aire)
INDOOR_AREA_RE = r"Mine|Cave|Cavern|Den\b|Burrow|Lair|Abbey|Stockade|Crypt|Catacomb|Dungeon|Tunnel|Hollow"
