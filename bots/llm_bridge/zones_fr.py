"""Wowlheim : noms de zones de WoW classic (1.12) en version francaise officielle.

Le serveur (DBC enUS) donne les noms anglais ; un vrai joueur FR dit « Hurlevent », pas « Stormwind ».
Usage : from zones_fr import fr ; fr("Elwynn Forest") -> "Forêt d'Elwynn" (nom inconnu : renvoye tel quel).
"""

ZONES_FR = {
    # --- Royaumes de l'Est : zones ---
    "Elwynn Forest": "Forêt d'Elwynn",
    "Westfall": "Marche de l'Ouest",
    "Redridge Mountains": "Les Carmines",
    "Duskwood": "Bois de la Pénombre",
    "Stranglethorn Vale": "Vallée de Strangleronce",
    "Dun Morogh": "Dun Morogh",
    "Loch Modan": "Loch Modan",
    "Wetlands": "Les Paluns",
    "Arathi Highlands": "Hautes-terres d'Arathi",
    "Hillsbrad Foothills": "Contreforts de Hautebrande",
    "Alterac Mountains": "Montagnes d'Alterac",
    "Silverpine Forest": "Forêt des Pins-Argentés",
    "Tirisfal Glades": "Clairières de Tirisfal",
    "Western Plaguelands": "Maleterres de l'Ouest",
    "Eastern Plaguelands": "Maleterres de l'Est",
    "The Hinterlands": "Les Hinterlands",
    "Badlands": "Terres ingrates",
    "Searing Gorge": "Gorge des Vents brûlants",
    "Burning Steppes": "Steppes ardentes",
    "Swamp of Sorrows": "Marais des Chagrins",
    "Blasted Lands": "Terres foudroyées",
    "Deadwind Pass": "Défilé de Deuillevent",
    "Blackrock Mountain": "Mont Rochenoire",
    # --- Royaumes de l'Est : capitales ---
    "Stormwind City": "Hurlevent",
    "Stormwind": "Hurlevent",
    "Ironforge": "Forgefer",
    "Undercity": "Fossoyeuse",
    # --- Royaumes de l'Est : sous-zones frequentes ---
    "Northshire Valley": "Vallée de Northshire",
    "Northshire Abbey": "Abbaye de Northshire",
    "Goldshire": "Comté-de-l'Or",
    "Sentinel Hill": "Colline des Sentinelles",
    "Moonbrook": "Ruisselune",
    "Lakeshire": "Comté-du-Lac",
    "Darkshire": "Sombre-Comté",
    "Booty Bay": "Baie-du-Butin",
    "Coldridge Valley": "Vallée de Frigrêve",
    "Anvilmar": "Anvilmar",
    "Kharanos": "Kharanos",
    "Thelsamar": "Thelsamar",
    "Menethil Harbor": "Port de Menethil",
    "Southshore": "Austrivage",
    "Tarren Mill": "Moulin-de-Tarren",
    "The Sepulcher": "Le Sépulcre",
    "Deathknell": "Le Glas",
    "Brill": "Brill",
    # --- Royaumes de l'Est : donjons ---
    "The Deadmines": "Les Mortemines",
    "The Stockade": "La Prison",
    "Shadowfang Keep": "Donjon d'Ombrecroc",
    "Gnomeregan": "Gnomeregan",
    "Scarlet Monastery": "Monastère Écarlate",
    "Uldaman": "Uldaman",
    "Blackrock Depths": "Profondeurs de Rochenoire",
    "Stratholme": "Stratholme",
    "Scholomance": "Scholomance",
    "Zul'Gurub": "Zul'Gurub",
    "Molten Core": "Cœur du Magma",
    "Blackwing Lair": "Repaire de l'Aile noire",
    # --- Kalimdor : zones ---
    "Durotar": "Durotar",
    "Mulgore": "Mulgore",
    "The Barrens": "Les Tarides",
    "Teldrassil": "Teldrassil",
    "Darkshore": "Sombrivage",
    "Ashenvale": "Orneval",
    "Stonetalon Mountains": "Les Serres-Rocheuses",
    "Thousand Needles": "Mille pointes",
    "Desolace": "Désolace",
    "Dustwallow Marsh": "Marécage d'Âprefange",
    "Tanaris": "Tanaris",
    "Feralas": "Féralas",
    "Azshara": "Azshara",
    "Felwood": "Gangrebois",
    "Un'Goro Crater": "Cratère d'Un'Goro",
    "Winterspring": "Berceau-de-l'Hiver",
    "Silithus": "Silithus",
    "Moonglade": "Reflet-de-Lune",
    # --- Kalimdor : capitales ---
    "Orgrimmar": "Orgrimmar",
    "Thunder Bluff": "Les Pitons-du-Tonnerre",
    "Darnassus": "Darnassus",
    # --- Kalimdor : sous-zones frequentes ---
    "Valley of Trials": "Vallée des Épreuves",
    "Razor Hill": "Tranchecolline",
    "Sen'jin Village": "Village de Sen'jin",
    "Camp Narache": "Camp Narache",
    "Bloodhoof Village": "Sabot-de-Sang",
    "The Crossroads": "La Croisée",
    "Ratchet": "Cabestan",
    "Shadowglen": "Sombrevallon",
    "Dolanaar": "Dolanaar",
    "Auberdine": "Auberdine",
    "Astranaar": "Astranaar",
    "Theramore Isle": "Île de Theramore",
    "Gadgetzan": "Gadgetzan",
    # --- Kalimdor : donjons ---
    "Ragefire Chasm": "Gouffre de Ragefeu",
    "Wailing Caverns": "Cavernes des Lamentations",
    "Blackfathom Deeps": "Profondeurs de Brassenoire",
    "Razorfen Kraul": "Kraal de Tranchebauge",
    "Razorfen Downs": "Souilles de Tranchebauge",
    "Maraudon": "Maraudon",
    "Zul'Farrak": "Zul'Farrak",
    "Dire Maul": "Hache-Tripes",
    "Onyxia's Lair": "Repaire d'Onyxia",
}

_LOWER = {k.lower(): v for k, v in ZONES_FR.items()}


def fr(name):
    """Nom francais officiel de la zone `name` (anglais), sinon `name` inchange."""
    if not name:
        return name
    key = name.strip()
    return ZONES_FR.get(key) or _LOWER.get(key.lower()) or name
