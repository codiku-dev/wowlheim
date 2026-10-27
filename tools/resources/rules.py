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
    # noms = noms francais EXACTS de Valheim (localization.txt, colonne French) ; 012 les reecrit de toute facon depuis les prefabs.
    # kind « smelted » : metal de Valheim, obtenu UNIQUEMENT par la fonderie / le haut fourneau (minerai des filons) : jamais en butin.
    _mat(9200001, "Bois", 1, "base", 7375),
    _mat(9200002, "Pierre", 1, "base", 4714),
    _mat(9200003, "Silex", 1, "base", 18107),
    _mat(9200004, "Résine", 1, "base", 8283),
    _mat(9200005, "Peau de cerf", 1, "base", 6687),
    _mat(9200006, "Bouts de cuir", 1, "base", 7400),
    _mat(9200009, "Bois dur", 1, "passage", 7999, 2),
    _mat(9200011, "Bois précieux", 2, "base", 7290),
    _mat(9200012, "Bois robuste", 2, "base", 13458),
    _mat(9200013, "Cuivre", 2, "smelted", 4681),
    _mat(9200014, "Étain", 2, "smelted", 4690),
    _mat(9200015, "Bronze", 2, "crafted", 7390),
    _mat(9200016, "Peau de troll", 2, "base", 6684),
    _mat(9200019, "Œil de naingris", 2, "passage", 7394, 2),
    _mat(9200021, "Fer", 3, "smelted", 4689),
    _mat(9200022, "Écorce ancienne", 3, "base", 7149),
    _mat(9200023, "Fragments d'os", 3, "base", 7350),
    _mat(9200024, "Entrailles", 3, "base", 1116),
    _mat(9200029, "Cœur de surtling", 3, "passage", 8560, 2),
    _mat(9200031, "Argent", 4, "smelted", 7355),
    _mat(9200032, "Obsidienne", 4, "base", 20769),
    _mat(9200033, "Peau de loup", 4, "base", 7294),
    _mat(9200034, "Cristal", 4, "base", 6546),
    _mat(9200039, "Glande gelée", 4, "passage", 4045, 2),
    _mat(9200041, "Sombracier", 5, "smelted", 20658),
    _mat(9200042, "Lin", 5, "base", 7383),
    _mat(9200043, "Toile de lin", 5, "crafted", 4752),       # Valheim : rouet (40 Lin -> Toile de lin), jamais en butin
    _mat(9200044, "Peau de Lox", 5, "base", 6698),
    _mat(9200049, "Noyau noir", 5, "passage", 17922, 2),
    # materiaux de Valheim ajoutes pour les pieces du marteau (tools/valheim/gen_server_sql.py, 012 : noms et icones de Valheim ;
    # display ci-dessous = repli WoW si 012 n'est pas applique). Fabriques = recettes de Valheim dans 012.
    _mat(9200051, "Charbon", 2, "base", 7340),            # aussi : four a charbon
    _mat(9200052, "Chaîne", 3, "base", 13692),            # Valheim : butin des spectres et cryptes du marais (pas de recette)
    _mat(9200053, "Clous en bronze", 2, "crafted", 7390),
    _mat(9200054, "Clous en fer", 3, "crafted", 7376),
    _mat(9200055, "Plumes", 1, "base", 28877),
    _mat(9200056, "Roue à aiguiser", 3, "crafted", 24673),
    _mat(9200057, "Goudron", 5, "base", 17957),
    _mat(9200070, "Framboises", 1, "base", 6410),
    _mat(9200071, "Pissenlit", 1, "base", 7396),
    _mat(9200072, "Myrtilles", 2, "base", 7341),
    _mat(9200073, "Chardon", 2, "base", 7241),
    _mat(9200074, "Carotte", 2, "base", 6402),
    _mat(9200075, "Viscosité", 3, "base", 2637),
    _mat(9200076, "Poche de sang", 3, "base", 7045),
    _mat(9200077, "Griffes de Fenris", 4, "base", 2460),
    _mat(9200078, "Larme de dragon", 4, "passage", 20977, 2),
    _mat(9200079, "Plaquebières", 5, "base", 18087),
    _mat(9200080, "Orge", 5, "base", 6661),
    _mat(9200081, "Morceau de sombracier", 5, "base", 20658),   # Valheim BlackMetalScrap : a fondre au haut fourneau
    _mat(9200082, "Champignon", 1, "pickable", 7341),     # Valheim : Pickable_Mushroom (ramassable seulement)
]
MAT = {m["id"]: m for m in MATERIALS}
STACK = 100          # taille de pile des materiaux
SELL_BASE = 4        # cuivre : prix de revente d'un materiau de base de palier 1 (x3 par palier)
BUY_FACTOR = 10      # prix chez le vendeur = revente x 10 (« prix eleve » : voir docs)


def sell_price(m):
    p = SELL_BASE * 3 ** (m["tier"] - 1)
    return {"base": p, "passage": p * 5, "crafted": p * 2, "smelted": p * 2, "pickable": p}[m["kind"]]


def buy_price(m):
    """Prix d'achat theorique (item_template.BuyPrice). AUCUN PNJ ne vend de materiau Wowlheim (006 vide : Valheim n'en vend pas)."""
    return sell_price(m) * BUY_FACTOR if m["kind"] == "base" else 0


# ------------------------------------------------------------------ outils : UNIQUEMENT ceux de Valheim
# (classe 2 sous-classe 14 « Divers » comme le Pic de mineur : aucune maitrise d'arme requise). Id 9201000 + palier*10 + (1 hache | 2 pic).
# Noms, palier d'outil (m_toolTier), degats de coupe/minage et durabilite (m_maxDurability) : prefabs de Valheim ; 012 (gen_server_sql.py)
# reecrit nom, durabilite et table wowlheim_tool depuis valheim_data.json. Hache en pierre (9201010, Valheim AxeStone) : creee par 012.
# Pas d'outil d'argent (n'existe pas dans Valheim) ; pas de pioche en sombracier (recette de Valheim en bois d'Yggdrasil, biome absent).
# Aucun niveau requis (Valheim n'en a pas : la progression passe par les materiaux).
TOOLS = [
    dict(id=9201011, kind="hache", tier=1, name="Hache en silex", display=7429, dmg=(1, 3), req=0, prefab="AxeFlint", durability=100),
    dict(id=9201012, kind="pic", tier=1, name="Pioche de bois de cerf", display=7493, dmg=(1, 3), req=0, prefab="PickaxeAntler", durability=100),
    dict(id=9201021, kind="hache", tier=2, name="Hache en bronze", display=7428, dmg=(2, 5), req=0, prefab="AxeBronze", durability=125),
    dict(id=9201022, kind="pic", tier=2, name="Pioche en bronze", display=6568, dmg=(2, 5), req=0, prefab="PickaxeBronze", durability=120),
    dict(id=9201031, kind="hache", tier=3, name="Hache en fer", display=7428, dmg=(4, 8), req=0, prefab="AxeIron", durability=175),
    dict(id=9201032, kind="pic", tier=3, name="Pioche en fer", display=6568, dmg=(4, 8), req=0, prefab="PickaxeIron", durability=150),
    dict(id=9201051, kind="hache", tier=5, name="Hache en sombracier", display=7427, dmg=(8, 16), req=0, prefab="AxeBlackMetal", durability=175),
]
# Recettes : UNIQUEMENT les Recipe_* de Valheim, generees par tools/valheim/gen_server_sql.py (012). Les recettes et conversions
# « proposees » de la premiere version (hache/pic d'argent, bois precieux/robuste, silex, bouts de cuir, fil de lin a l'etabli) sont supprimees.
CONVERSIONS = []

# ------------------------------------------------------------------ categories de creatures
# Categorie principale determinee par (CreatureType, Family, nom) dans classify.py ; heritage pour les regles ci-dessous.
CAT_PARENT = {
    "MINER": "HUMANOID", "LOGGER": "HUMANOID", "BRUTE": "HUMANOID",
    "BEAST_MAMMAL": "BEAST", "BEAST_OTHER": "BEAST", "BEAST_SPIDER": "BEAST", "BEAST_BASILISK": "BEAST_OTHER",
    "ELEM_ROCK": "ELEMENTAL", "ELEM_PLANT": "ELEMENTAL", "ELEM_OTHER": "ELEMENTAL",
    "BEAST_BIRD": "BEAST_OTHER",
    # materiaux animaux de Valheim (2026-10-26) : sous-categories par MODELE (classify.py) ; rattachees a BEAST (pas a BEAST_MAMMAL) pour
    # ne pas heriter des Bouts de cuir : dans Valheim, cerf, loup et lox ne lachent pas de chutes de cuir (seuls sanglier et chauve-souris)
    "BEAST_DEER": "BEAST", "BEAST_WOLF": "BEAST", "BEAST_BOAR": "BEAST", "BEAST_LOX": "BEAST",
    "TROLL": "BRUTE", "OGRE": "BRUTE", "HARPY": "HUMANOID",
}
ALL_CATS = ["HUMANOID", "MINER", "LOGGER", "BRUTE", "BEAST", "BEAST_MAMMAL", "BEAST_OTHER", "BEAST_SPIDER", "BEAST_BASILISK",
            "UNDEAD", "ELEMENTAL", "ELEM_ROCK", "ELEM_PLANT", "ELEM_OTHER", "GIANT", "MECH", "DRAGONKIN", "DEMON", "OTHER", "BEAST_BIRD",
            "BEAST_DEER", "BEAST_WOLF", "BEAST_BOAR", "BEAST_LOX", "TROLL", "OGRE", "HARPY"]   # ajout en fin : les id de reference existants ne bougent pas
# categories attribuables a une creature (feuilles ; HUMANOID/BEAST/ELEMENTAL generiques sont aussi des categories finales)
ASSIGNABLE = ["HUMANOID", "MINER", "LOGGER", "BRUTE", "BEAST_MAMMAL", "BEAST_OTHER", "BEAST_SPIDER", "BEAST_BASILISK",
              "UNDEAD", "ELEM_ROCK", "ELEM_PLANT", "ELEM_OTHER", "GIANT", "MECH", "DRAGONKIN", "DEMON", "OTHER", "BEAST_BIRD",
              "BEAST_DEER", "BEAST_WOLF", "BEAST_BOAR", "BEAST_LOX", "TROLL", "OGRE", "HARPY"]

# Regles de butin : item -> [(categorie, chance %, min, max)].
# Valheim : les metaux (cuivre, etain, fer, argent, sombracier) et la toile de lin ne tombent JAMAIS des monstres : minerai des filons ->
# fonderie / haut fourneau, lin -> rouet. Leurs anciennes regles sont supprimees (2026-10-26). Palier de la creature = palier de l'objet (ou palier+1 : retour en arriere).
# 2026-10-26 (demande de Robin : construction iso Valheim, materiaux ANIMAUX credibles) :
#   - Bois (9200001) et Pierre (9200002) : AUCUNE regle de butin. Comme dans Valheim pour le joueur, ils ne viennent que des arbres, rochers et
#     ramassables (PLACEMENTS ci-dessous : abattage, minage, cueillette). Aucun vendeur non plus (006 vide). Voir NODE_ONLY.
#   - materiaux animaux selon la CREATURE (modele 3D / famille, classify.py), d'apres les CharacterDrop de Valheim :
#     Peau de cerf = cervides seulement ; Bouts de cuir = sangliers et betes generiques (ours, felins, hyenes, gorilles, chauves-souris) ;
#     Peau de loup + Griffes de Fenris = loups/worgs ; Peau de Lox = grands herbivores (kodos, lezards-tonnerre, dimetrodons, girafes) ;
#     (poules et cerfs « critters » sans butin dans WoW : classify.CRITTER_GAME_MODELS, LootId = Entry par 004)
#     Peau de troll = trolls, ogres (trolls du folklore nordique), geants ; Plumes = oiseaux, poules et harpies ; Fragments d'os = morts-vivants
#     (squelettes) et betes ; Entrailles = betes et morts-vivants (draugr).
#   - plus de baies / carottes / plaquebieres sur les betes, plus de peau / glande sur des betes « au hasard », plus de cuir ni d'os
#     sur les humanoides generiques.
NODE_ONLY = {9200001, 9200002}   # materiaux de base sans aucun butin de monstre (arbres / rochers / ramassables uniquement)
DROP_RULES = {
    9200003: [("MINER", 40, 1, 2), ("BRUTE", 30, 1, 2), ("ELEM_ROCK", 30, 1, 2), ("HUMANOID", 25, 1, 2)],
    9200004: [("ELEM_PLANT", 45, 1, 2), ("BEAST_SPIDER", 30, 1, 2), ("HUMANOID", 10, 1, 1)],
    9200005: [("BEAST_DEER", 55, 1, 2), ("BEAST_LOX", 35, 1, 2)],                          # Peau de cerf : Valheim Deer ; cervides etendus, jeunes kodos
    9200006: [("BEAST_BOAR", 50, 1, 3), ("BEAST_MAMMAL", 40, 1, 2), ("BEAST_LOX", 30, 1, 2)],  # Bouts de cuir : Valheim Boar (et Bat) ; jeunes kodos
    9200009: [("BEAST_DEER", 12, 1, 1), ("BEAST_LOX", 8, 1, 1)],                           # Bois dur (andouiller) : Eikthyr = cerf ; cornes de jeunes kodos
    9200011: [("LOGGER", 50, 1, 3), ("ELEM_PLANT", 50, 1, 3), ("GIANT", 25, 1, 2), ("HUMANOID", 20, 1, 2)],
    9200012: [("ELEM_PLANT", 35, 1, 2), ("LOGGER", 30, 1, 2), ("GIANT", 30, 1, 2), ("HUMANOID", 8, 1, 1)],
    9200016: [("TROLL", 50, 1, 2), ("GIANT", 50, 1, 2), ("OGRE", 45, 1, 2)],               # Peau de troll : Valheim Troll
    9200019: [("ELEM_PLANT", 10, 1, 1), ("BEAST_SPIDER", 6, 1, 1), ("BRUTE", 6, 1, 1), ("HUMANOID", 3, 1, 1)],
    9200022: [("ELEM_PLANT", 45, 1, 3), ("LOGGER", 35, 1, 2), ("GIANT", 30, 1, 2), ("OTHER", 15, 1, 2), ("HUMANOID", 10, 1, 1)],
    9200023: [("UNDEAD", 50, 1, 3), ("BEAST", 20, 1, 2)],                                   # Fragments d'os : Valheim Skeleton
    9200024: [("BEAST", 45, 1, 2), ("UNDEAD", 30, 1, 2)],                                   # Entrailles : Valheim Draugr ; betes videes
    9200029: [("ELEM_OTHER", 10, 1, 1), ("DEMON", 10, 1, 1), ("ELEM_ROCK", 8, 1, 1), ("UNDEAD", 4, 1, 1)],
    9200032: [("ELEM_ROCK", 40, 1, 2), ("DRAGONKIN", 35, 1, 2), ("GIANT", 30, 1, 2), ("MINER", 25, 1, 2), ("DEMON", 20, 1, 2)],
    9200033: [("BEAST_WOLF", 50, 1, 2)],                                                    # Peau de loup : Valheim Wolf
    9200034: [("BEAST_BASILISK", 40, 1, 2), ("ELEM_ROCK", 30, 1, 2), ("GIANT", 20, 1, 2), ("DRAGONKIN", 15, 1, 2), ("ELEM_OTHER", 15, 1, 2)],
    9200039: [("DRAGONKIN", 10, 1, 1), ("ELEM_OTHER", 8, 1, 1)],                            # Glande gelee : Valheim Drake (dragonnet)
    9200042: [("ELEM_PLANT", 40, 1, 3), ("HUMANOID", 25, 1, 3), ("UNDEAD", 15, 1, 2)],
    9200044: [("BEAST_LOX", 50, 1, 2)],                                                     # Peau de Lox : Valheim Lox
    9200049: [("DRAGONKIN", 10, 1, 1), ("DEMON", 10, 1, 1), ("ELEM_ROCK", 8, 1, 1), ("MECH", 8, 1, 1), ("UNDEAD", 5, 1, 1)],
    # materiaux de Valheim des pieces du marteau (sources : docs/VALHEIM_ASSETS.md, « Materiaux des pieces »)
    9200051: [("MINER", 35, 1, 3), ("ELEM_OTHER", 30, 1, 2), ("DEMON", 15, 1, 2)],          # Charbon : mineurs, elementaires de feu
    9200052: [("UNDEAD", 35, 1, 2), ("MECH", 25, 1, 2), ("BRUTE", 20, 1, 2)],                # Chaine : spectres (Valheim), golems, ogres
    9200055: [("BEAST_BIRD", 55, 1, 3), ("HARPY", 45, 1, 2)],                               # Plumes : oiseaux (Valheim Seagal/Crow), harpies
    9200057: [("OTHER", 45, 1, 3), ("ELEM_OTHER", 30, 1, 2), ("ELEM_PLANT", 30, 1, 2)],     # Goudron : limons, betes de goudron d'Un'Goro
    9200070: [("ELEM_PLANT", 45, 1, 3)],                                                    # Framboises : plantes (et buissons ramassables)
    9200071: [("ELEM_PLANT", 40, 1, 3), ("HUMANOID", 10, 1, 1)],                            # Pissenlit : cueilleurs
    9200072: [("ELEM_PLANT", 45, 1, 3)],                                                    # Myrtilles
    9200073: [("ELEM_PLANT", 40, 1, 3), ("HUMANOID", 12, 1, 2)],                            # Chardon : cueilleurs
    9200074: [("ELEM_PLANT", 30, 1, 2)],                                                    # Carotte
    9200075: [("OTHER", 50, 1, 3), ("ELEM_PLANT", 25, 1, 2)],                               # Viscosite : limons, vases (Valheim Blob)
    9200076: [("BEAST_OTHER", 35, 1, 2), ("UNDEAD", 15, 1, 1)],                             # Poche de sang : crocilisques, reptiles des marais (Valheim Leech)
    9200077: [("BEAST_WOLF", 35, 1, 2)],                                                    # Griffes de Fenris : loups, worgs (Valheim Fenring)
    9200078: [("DRAGONKIN", 10, 1, 1), ("ELEM_OTHER", 4, 1, 1)],                            # Larme de dragon (passage : table d'artisan)
    9200079: [("ELEM_PLANT", 40, 1, 3)],                                                    # Plaquebieres
    9200080: [("ELEM_PLANT", 35, 1, 3), ("HUMANOID", 15, 1, 2)],                            # Orge
    # Morceau de sombracier (ferraille de metal noir) : Valheim = butin des Fulings (gobelins des plaines, camps) -> humanoides (gobelins, ogres), golems, mineurs
    9200081: [("HUMANOID", 35, 1, 3), ("MECH", 30, 1, 2), ("BRUTE", 30, 1, 2), ("MINER", 30, 1, 2)],
}
# ------------------------------------------------------------------ gibier ajoute aux zones de depart qui n'en ont pas (004)
# Le Bois dur (pioche de bois de cerf -> cuivre) et la Peau de cerf doivent exister au palier 1 dans la zone de depart de CHAQUE race. Dun Morogh,
# Clairieres de Tirisfal et Durotar n'ont aucune bete a bois/cornes attaquable : on y ajoute des apparitions de gibier EXISTANT (critters de WoW,
# meme modele, meme niveau) aux positions de critters deja presents (lapins / rats : sol valide, hors villes et interieurs).
# Idem Plumes a Dun Morogh (aucun oiseau ; une seule poule) : poules (critter 620) dans les fermes et villages (Amberstill, Brewnall, Kharanos).
# (carte, zone, entree posee, entrees dont on reprend les positions, nombre max, aires imposees (regex) ou None = hors villes)
GAME_SPAWNS = [
    (0, 1, 2098, (721,), 30, None),       # Dun Morogh : Belier (Ram, critter de Loch Modan / Les Paluns)
    (0, 85, 883, (721, 4075), 30, None),  # Clairieres de Tirisfal : Cerf (Deer, critter d'Elwynn / Teldrassil)
    (1, 14, 4166, (5951,), 30, None),     # Durotar : Gazelle (critter des Tarides) aux positions des lievres (Hare)
    (0, 1, 620, (721,), 12, r"Amberstill|Brewnall|Kharanos"),   # Dun Morogh : Poules (Chicken) dans les fermes / villages
]
GAME_SPAWN_GUID = (9700001, 9700999)
GAME_SPAWN_EXCLUDE_AREAS = r"Brill|Kharanos|Gnomeregan|Ruins of Lordaeron|Undercity|Razor Hill|Orgrimmar|Sen'jin|Amberstill|Steelgrill|Brewnall|Thunder Ridge"
GAME_SPAWN_MIN_DIST = 30.0
# departs de race (carte, zone) : controle check.py §6 (chaque materiau de palier 1 trouvable dans la zone de depart)
START_ZONES = [(0, 12, "Elwynn (Comte du Nord)"), (0, 1, "Dun Morogh (Coldridge)"), (1, 14, "Durotar (Vallee des epreuves)"),
               (1, 215, "Mulgore (Camp Narache)"), (1, 141, "Teldrassil (Shadowglen)"), (0, 85, "Tirisfal (Deathknell)")]

BACK_FACTOR = 0.35   # retour en arriere : un monstre de palier t lache aussi les materiaux de BASE du palier t-1 a 35 % du taux
BACK_MIN = 8         # (plancher en %)
ELITE_REPEAT = 2     # elites normales : la reference est tiree 2 fois

# ------------------------------------------------------------------ placement du monde, iso Valheim (2026-10-26)
# Plus AUCUN GameObject-noeud aux modeles WoW (anciens 9101001-9101045 : supprimes par 003/005/008). Le monde est peuple d'objets de
# Valheim : « creature » = arbre / roche / filon frappe a la hache ou a la pioche (TreeMgr) ; « pickable » = ramassable de Valheim
# (composant Pickable) = GameObject coffre sans verrou, un clic sans outil.
# POSITIONS : tools/resources/place_resources.py -> C:\Wowlheim\data\wl_terrain\placements.json (d'apres le terrain du client :
# arbres Valheim pres des arbres WoW, rochers pres des rochers/falaises, silex/chardon/etain sur les berges, cuivre en amas, rien sur
# routes/villes/eau ; palier = palier de la ZONE ; docs/RESOURCES_PLACEMENT.md). Les « kinds » de ce fichier sont les cles ci-dessous.
# tiers = paliers ou le type est autorise (controle : jamais de type d'un palier superieur dans une zone de palier inferieur) ;
# prefabs = [(prefab Valheim, poids)] ; gives = materiaux obtenus (controle par gen_server_sql.py contre les DropTable de Valheim).
def _pl(key, tiers, kind, prefabs, gives):
    return dict(key=key, tiers=tiers, tier=min(tiers), kind=kind, prefabs=prefabs, gives=gives)


PLACEMENTS = [
    # arbres (essence = biome de Valheim du palier de zone ; bouleau/chene : hache en bronze, « trop durs » au debut comme dans Valheim)
    _pl("beech", (1, 2), "creature", [("Beech1", 1)], [9200001, 9200004]),
    _pl("birch", (1, 5), "creature", [("Birch1", 1)], [9200001, 9200011]),
    _pl("oak", (1, 5), "creature", [("Oak1", 1)], [9200001, 9200011]),
    _pl("fir", (1, 2, 4), "creature", [("FirTree", 1)], [9200001]),
    _pl("pine", (2,), "creature", [("Pinetree_01", 1)], [9200001, 9200012]),
    _pl("swamp", (3,), "creature", [("SwampTree1", 1)], [9200001, 9200022]),
    # roches et filons (pioche ; palier de pioche de Valheim)
    _pl("rock", (1, 2, 3, 4, 5), "creature", [("MineRock_Stone", 1), ("Rock_4", 1)], [9200002]),
    _pl("copper", (2,), "creature", [("MineRock_Copper", 1)], [9200060]),
    _pl("tin", (2,), "creature", [("MineRock_Tin", 1)], [9200061]),
    _pl("iron", (3,), "creature", [("MineRock_Iron", 1)], [9200062]),   # tas de boue (mudpile) : Ferraille
    _pl("silver", (4,), "creature", [("silvervein", 1)], [9200063, 9200002]),
    _pl("obsidian", (4,), "creature", [("MineRock_Obsidian", 1)], [9200032]),
    # ramassables (un clic, sans outil)
    _pl("branch", (1, 2), "pickable", [("Pickable_Branch", 1)], [9200001]),
    _pl("stone", (1, 2), "pickable", [("Pickable_Stone", 1)], [9200002]),
    _pl("flint", (1, 2), "pickable", [("Pickable_Flint", 1)], [9200003]),
    _pl("raspberry", (1,), "pickable", [("RaspberryBush", 1)], [9200070]),
    _pl("mushroom", (1, 2), "pickable", [("Pickable_Mushroom", 1)], [9200082]),
    _pl("dandelion", (1,), "pickable", [("Pickable_Dandelion", 1)], [9200071]),
    _pl("blueberry", (2,), "pickable", [("BlueberryBush", 1)], [9200072]),
    # chardon : Foret noire et Marais (KINDS de place_resources.py) ; palier 1 = seulement sur la berge la plus proche de chaque
    # depart de race (place_resources.start_pass, controle start_check.py), demande de Robin du 2026-10-26
    _pl("thistle", (1, 2, 3), "pickable", [("Pickable_Thistle", 1)], [9200073]),
    _pl("crystal", (4,), "pickable", [("Pickable_MountainCaveCrystal", 1)], [9200034]),
    _pl("flax", (5,), "pickable", [("Pickable_Flax_Wild", 1)], [9200042]),
    _pl("barley", (5,), "pickable", [("Pickable_Barley_Wild", 1)], [9200080]),
    _pl("cloudberry", (5,), "pickable", [("CloudberryBush", 1)], [9200079]),
    _pl("tar", (5,), "pickable", [("Pickable_TarBig", 1)], [9200057]),
]
PLACEMENT = {p["key"]: p for p in PLACEMENTS}
PLACEMENTS_JSON = r"C:\Wowlheim\data\wl_terrain\placements.json"
# anciens noeuds GameObject aux modeles WoW : plage supprimee (templates, butin, apparitions) par 003/005/008
OLD_NODE_ENTRY_MIN, OLD_NODE_ENTRY_MAX = 9101001, 9101999
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
