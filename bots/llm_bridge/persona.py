"""Personnalites des bots Wowlheim.

Une personnalite decrit le JOUEUR derriere le bot (sa facon d'ecrire, son caractere,
sa vie, ses horaires, ses objectifs en jeu), pas seulement le personnage. Elle est stable :
meme nom de bot -> meme personnalite (graine = nom), et elle reste coherente avec la race,
la classe et le niveau que playerbots a choisis pour le bot.

Le style d'ecriture est compose de deux briques independantes et compatibles :
  - une FORME (casse, ponctuation, orthographe, abreviations) ;
  - un REGISTRE (vocabulaire, attitude, expressions) ;
plus une longueur de reponse, des expressions fetiches (tics), une regle sur les smileys
(« jamais » pour la grande majorite) et un ton hors-roleplay ou roleplay leger.
Le champ « style » (seul lu par bridge.build_messages pour l'ecriture) resume tout cela
en une consigne directement imitable ; les champs detailles restent dans la fiche.

Ordre de recherche : bots/personas/<Nom>.json (ecrites a la main, versionnees),
puis <state>/personas/<Nom>.json (generees automatiquement, hors depot), sinon
generation deterministe puis enregistrement dans <state>. Une fiche generee par une
version plus ancienne de ce module est regeneree (son champ « histoire » est garde).
"""
import hashlib
import json
import os
import random
import re

REPO_PERSONAS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "personas")
PERSONA_VERSION = 2

CLASS_FR = {
    "warrior": "guerrier", "paladin": "paladin", "hunter": "chasseur", "rogue": "voleur",
    "priest": "pretre", "shaman": "chaman", "mage": "mage", "warlock": "demoniste", "druid": "druide",
}
RACE_FR = {
    "human": "humain", "orc": "orc", "dwarf": "nain", "night elf": "elfe de la nuit",
    "nightelf": "elfe de la nuit", "undead": "mort-vivant", "tauren": "tauren", "gnome": "gnome",
    "troll": "troll",
}
# Identifiants 1.12 (tables characters.race / characters.class).
RACE_BY_ID = {1: "human", 2: "orc", 3: "dwarf", 4: "night elf", 5: "undead", 6: "tauren", 7: "gnome", 8: "troll"}
CLASS_BY_ID = {1: "warrior", 2: "paladin", 3: "hunter", 4: "rogue", 5: "priest", 7: "shaman", 8: "mage",
               9: "warlock", 11: "druid"}
FACTION = {"human": "A", "dwarf": "A", "night elf": "A", "nightelf": "A", "gnome": "A",
           "orc": "H", "undead": "H", "tauren": "H", "troll": "H"}

# Noms propres reserves a une faction (capitales, zones de depart, donjons de faction) :
# utilises par les tests pour verifier qu'un bot ne cite pas les lieux de l'autre camp.
FACTION_PLACES = {
    "A": ["Hurlevent", "Forgefer", "Darnassus", "Comté-du-Nord", "Comté-de-l'Or", "Elwynn", "Dun Morogh",
          "Kharanos", "Teldrassil", "Dolanaar", "Sombrevallon", "Auberdine", "Loch Modan", "Thelsamar",
          "Marche de l'Ouest", "Mortemines", "Prison de Hurlevent", "Menethil", "Gnomeregan",
          "Bois de la Pénombre", "Lumière", "Elune", "ancêtres"],
    "H": ["Orgrimmar", "Fossoyeuse", "Pitons-du-Tonnerre", "Durotar", "Vallée des Épreuves", "Sen'jin",
          "îles de l'Écho", "Tirisfal", "Le Glas", "Brill", "Mulgore", "Narache", "Sabot-de-Sang",
          "Croisée", "Ragefeu", "Lamentations", "Ombrecroc", "Pins-Argentés", "Lok'tar", "Terre-mère",
          "Reine banshee", "Loa"],
}

# --------------------------------------------------------------------------- style d'ecriture
# FORMES : mecanique d'ecriture. niveau : soigne / neutre / relache ; abr : abrege beaucoup.
FORMES = [
    {"id": "min_sans_ponct", "niveau": "relache", "abr": False, "age": (12, 45),
     "txt": "tout en minuscules, aucune ponctuation, pas de majuscule même aux noms"},
    {"id": "min_virgules", "niveau": "relache", "abr": False, "age": (12, 55),
     "txt": "minuscules, quelques virgules, jamais de point final"},
    {"id": "soignee", "niveau": "soigne", "abr": False, "age": (14, 80),
     "txt": "orthographe soignée avec accents, majuscule au début, point à la fin"},
    {"id": "sans_accents", "niveau": "neutre", "abr": False, "age": (12, 80),
     "txt": "aucun accent (clavier qwerty), mais majuscule en début de phrase et ponctuation normale"},
    {"id": "fautes_frappe", "niveau": "relache", "abr": False, "age": (12, 70),
     "txt": "tape vite et laisse des fautes de frappe (lettres inversées, accents oubliés) sans corriger"},
    {"id": "sms", "niveau": "relache", "abr": True, "age": (12, 38),
     "txt": "abrège presque tout : jsp, tkt, stp, pk, dac, g, c, jvais, bcp, mm, pr"},
    {"id": "phonetique", "niveau": "relache", "abr": True, "age": (12, 40),
     "txt": "écrit comme il parle : chuis, ya, tfaçon, jsais pas, chai pas, kestu fais"},
    {"id": "telegraphique", "niveau": "neutre", "abr": True, "age": (16, 70),
     "txt": "style télégraphique sans articles ni sujet (« farm loups, dispo après »)"},
    {"id": "suspension", "niveau": "neutre", "abr": False, "age": (12, 80),
     "txt": "phrases qui finissent souvent par des points de suspension..."},
    {"id": "exclamation", "niveau": "neutre", "abr": False, "age": (12, 60),
     "txt": "majuscule au début, finit souvent par un point d'exclamation (un seul, jamais plusieurs)"},
    {"id": "espace_ponct", "niveau": "soigne", "abr": False, "age": (25, 80),
     "txt": "phrases complètes, met une espace avant ? et ! comme à l'école"},
    {"id": "majuscule_insiste", "niveau": "neutre", "abr": False, "age": (12, 55),
     "txt": "écrit normalement ; de temps en temps un mot important en majuscules pour insister, jamais un mot au hasard"},
    {"id": "virgules_enchainees", "niveau": "neutre", "abr": False, "age": (14, 70),
     "txt": "enchaîne deux ou trois idées avec des virgules, sans point final"},
    {"id": "point_sec", "niveau": "neutre", "abr": False, "age": (16, 80),
     "txt": "phrases très courtes, toujours un point final, même après « Ok. »"},
    {"id": "sans_majuscule_ponct", "niveau": "neutre", "abr": False, "age": (12, 70),
     "txt": "pas de majuscule au début mais une ponctuation correcte (virgules, points d'interrogation)"},
]

# REGISTRES : vocabulaire et attitude. reg : soutenu / neutre / familier.
# sm = probabilite d'utiliser des smileys (0 = jamais), rp = compatible roleplay leger,
# w = poids relatif (registres regionaux plus rares),
# excl = interdit les points d'exclamation (incompatible avec la forme « exclamation »).
REGISTRES = [
    {"id": "ado", "reg": "familier", "age": (13, 19), "sm": 0.35, "rp": False,
     "txt": "parle comme un ado", "tics": ["wsh", "frr", "de ouf", "chelou", "c'est mort"]},
    {"id": "jeune_cool", "reg": "familier", "age": (17, 35), "sm": 0.25, "rp": False,
     "txt": "décontracté", "tics": ["genre", "en vrai", "grave", "tranquille", "carrément"]},
    {"id": "poli_vouvoie", "reg": "soutenu", "age": (25, 80), "sm": 0.0, "rp": True,
     "txt": "très poli : dit bonjour et merci, dit « vous » aux inconnus", "tics": ["volontiers", "avec plaisir", "bonne soirée"]},
    {"id": "jargon_vieux_joueur", "reg": "neutre", "age": (26, 50), "sm": 0.0, "rp": False,
     "txt": "jargon de vieux joueur de MMO", "tics": ["LFG", "pull", "aggro", "wipe", "add", "ninja loot"]},
    {"id": "anglicismes", "reg": "familier", "age": (16, 40), "sm": 0.15, "rp": False,
     "txt": "glisse des mots anglais", "tics": ["np", "ty", "gg", "brb", "nice", "go"]},
    {"id": "pince_sans_rire", "reg": "neutre", "age": (20, 70), "sm": 0.0, "rp": True, "excl": True,
     "txt": "humour pince-sans-rire : réponses sèches et ironiques, jamais d'exclamation", "tics": ["évidemment", "quelle surprise", "fascinant"]},
    {"id": "raleur", "reg": "familier", "age": (18, 70), "sm": 0.0, "rp": False,
     "txt": "râle un peu sur tout mais reste correct", "tics": ["pff", "franchement", "c'est abusé", "bref"]},
    {"id": "timide", "reg": "neutre", "age": (13, 60), "sm": 0.15, "rp": True, "excl": True,
     "txt": "timide, s'excuse souvent, n'ose pas trop", "tics": ["désolé", "euh", "si ça dérange pas"]},
    {"id": "enthousiaste", "reg": "familier", "age": (13, 50), "sm": 0.3, "rp": False,
     "txt": "enthousiaste et positif", "tics": ["trop bien", "yes", "génial", "allez"]},
    {"id": "conseiller", "reg": "neutre", "age": (22, 70), "sm": 0.0, "rp": True,
     "txt": "aime donner un conseil de jeu concret, ton de grand frère", "tics": ["astuce", "fais gaffe", "crois-moi"]},
    {"id": "quebecois", "w": 0.35, "reg": "familier", "age": (16, 70), "sm": 0.12, "rp": False,
     "txt": "joueur québécois (avec modération)", "tics": ["tantôt", "pantoute", "c'est correct", "icitte", "pis"]},
    {"id": "belge", "w": 0.35, "reg": "neutre", "age": (16, 70), "sm": 0.12, "rp": False,
     "txt": "joueur belge (avec modération)", "tics": ["septante", "nonante", "une fois", "savoir (pour pouvoir)", "allez"]},
    {"id": "sudiste", "w": 0.35, "reg": "familier", "age": (18, 70), "sm": 0.12, "rp": False,
     "txt": "joueur du sud de la France (avec modération)", "tics": ["peuchère", "fada", "té", "dégun", "boudu"]},
    {"id": "tryhard", "reg": "neutre", "age": (16, 45), "sm": 0.0, "rp": False,
     "txt": "optimise tout, parle chiffres et efficacité", "tics": ["xp/h", "stuff", "talents", "rentable", "opti"]},
    {"id": "vieillot", "reg": "soutenu", "age": (38, 80), "sm": 0.0, "rp": True,
     "txt": "tournures un peu vieillottes", "tics": ["ma foi", "fort bien", "diantre", "point du tout"]},
    {"id": "blagueur", "reg": "familier", "age": (14, 60), "sm": 0.2, "rp": False,
     "txt": "place des petites vannes ou jeux de mots sur sa classe", "tics": ["blague à part", "je dis ça je dis rien"]},
    {"id": "laconique", "reg": "neutre", "age": (14, 80), "sm": 0.0, "rp": True, "excl": True, "court": True,
     "txt": "laconique, aucune formule de politesse", "tics": ["ouais", "nan", "ok", "ça marche"]},
    {"id": "curieux", "reg": "neutre", "age": (13, 70), "sm": 0.12, "rp": True,
     "txt": "répond puis renvoie souvent une question à l'autre", "tics": ["et toi ?", "tu joues quoi ?", "c'est où ?"]},
    {"id": "rieur", "reg": "familier", "age": (13, 40), "sm": 0.35, "rp": False,
     "txt": "rit beaucoup à l'écrit (le rire remplace les smileys)", "tics": ["mdr", "ptdr", "jpp", "hahaha"]},
    {"id": "calme_adulte", "reg": "neutre", "age": (24, 80), "sm": 0.1, "rp": True,
     "txt": "calme et posé, tutoie, pas d'argot", "tics": ["pas de souci", "on verra", "d'accord"]},
    {"id": "occupe", "reg": "neutre", "age": (16, 60), "sm": 0.0, "rp": False,
     "txt": "toujours en train de faire un truc en jeu et le dit", "tics": ["attends", "2 sec", "je finis ma quête", "jsuis en combat"]},
    {"id": "nouveau_naif", "reg": "neutre", "age": (12, 60), "sm": 0.18, "rp": False,
     "txt": "découvre le jeu, pose des questions naïves, se trompe parfois de mot", "tics": ["c'est quoi", "comment on fait", "ah d'accord"]},
    {"id": "solennel_rp", "reg": "soutenu", "age": (16, 70), "sm": 0.0, "rp": True, "rp_only": True,
     "txt": "un peu solennel, aime l'ambiance d'Azeroth", "tics": ["l'ami", "que ta route soit sûre", "bien le bonjour"]},
]

LONGUEURS = [("très courtes (2 à 6 mots)", 3), ("courtes (5 à 12 mots)", 5), ("moyennes (jusqu'à 20 mots)", 2)]

TICS_PERSO = [  # (expression, familier ?)
    ("commence souvent par « bon, »", False), ("dit « ouais » au lieu de oui", True),
    ("finit parfois par « quoi »", True), ("dit « bah » pour hésiter", True), ("dit « nickel » quand ça va", False),
    ("dit « bref » pour changer de sujet", False), ("ajoute « hein » en fin de phrase", True),
    ("dit « mouais » quand il doute", True), ("dit « clairement »", False), ("dit « pas faux »", False),
    ("dit « oklm »", True), ("dit « à l'aise »", True),
]

SMILEYS = [(":)", 3), (":p", 2), ("xD", 2), (":D", 2), (";)", 1), ("^^", 1), (":/", 1)]

RP_FLAVOR = {
    "human": "« par la Lumière », « l'ami »", "dwarf": "« par la barbe de mes ancêtres », « une bonne bière »",
    "gnome": "« c'est ingénieux », « par mes engrenages »", "night elf": "« qu'Elune te guide », « jeune pousse »",
    "orc": "« Lok'tar », « pour la Horde »", "troll": "« mon », « les Loa te regardent »",
    "undead": "« pour la Reine banshee », « les vivants... »", "tauren": "« que la Terre-mère veille sur toi », « jeune veau »",
}

# --------------------------------------------------------------------------- caractere
TRAITS = [
    "serviable", "blagueur", "compétitif", "timide", "un peu râleur", "curieux", "nostalgique des débuts de WoW",
    "patient", "impatient", "généreux", "radin avec son or", "fier de sa classe", "tête en l'air", "organisé",
    "chill", "bavard", "solitaire", "sociable", "perfectionniste", "têtu", "optimiste", "pessimiste", "taquin",
    "prudent", "tête brûlée", "collectionneur", "explorateur", "chasseur de loot", "évite le PvP", "fan de PvP",
    "maladroit", "modeste", "frimeur", "rêveur", "protecteur avec les débutants", "mauvais perdant", "flemmard",
    "acharné", "susceptible", "philosophe",
]
INCOMPATIBLE = [
    {"patient", "impatient"}, {"généreux", "radin avec son or"}, {"timide", "bavard"}, {"timide", "frimeur"},
    {"solitaire", "sociable"}, {"solitaire", "bavard"}, {"optimiste", "pessimiste"}, {"prudent", "tête brûlée"},
    {"évite le PvP", "fan de PvP"}, {"modeste", "frimeur"}, {"flemmard", "acharné"}, {"organisé", "tête en l'air"},
    {"chill", "compétitif"}, {"chill", "un peu râleur"}, {"philosophe", "mauvais perdant"},
    {"perfectionniste", "flemmard"}, {"susceptible", "chill"},
]

# --------------------------------------------------------------------------- vie du joueur
# (masculin, feminin, ages, heures de jeu, poids)
LIVES = [
    ("étudiant en fac", "étudiante en fac", (19, 24), "le soir après les cours, tard le week-end", 4),
    ("lycéen", "lycéenne", (15, 17), "après les devoirs, doit couper à 22 h en semaine", 3),
    ("infirmier en horaires décalés", "infirmière en horaires décalés", (25, 50), "à des heures bizarres, parfois le matin", 2),
    ("père de deux enfants", "mère de deux enfants", (30, 45), "quand les petits dorment, après 21 h", 3),
    ("retraité qui a découvert WoW grâce à son petit-fils", "retraitée qui a découvert WoW grâce à son petit-fils",
     (60, 70), "l'après-midi, jamais très tard", 1),
    ("ancien joueur de 2005 revenu par nostalgie", "ancienne joueuse de 2005 revenue par nostalgie",
     (30, 42), "le soir en semaine", 4),
    ("développeur en télétravail", "développeuse en télétravail", (25, 40), "à la pause de midi et le soir", 2),
    ("chauffeur routier", "chauffeuse routière", (30, 55), "le week-end, en rentrant de tournée", 1),
    ("boulanger", "boulangère", (24, 50), "en début d'après-midi, couché tôt", 1),
    ("entre deux boulots", "entre deux boulots", (22, 35), "beaucoup en journée", 2),
    ("serveur dans un restaurant", "serveuse dans un restaurant", (19, 30), "tard la nuit après le service", 2),
    ("étudiant en médecine", "étudiante en médecine", (20, 26), "peu, pour décompresser entre deux révisions", 1),
    ("agriculteur", "agricultrice", (30, 55), "le soir, surtout l'hiver", 1),
    ("prof de collège", "prof de collège", (27, 50), "le soir et pendant les vacances scolaires", 2),
    ("caissier en supermarché", "caissière en supermarché", (19, 45), "après le boulot, en soirée", 2),
    ("informaticien d'astreinte", "informaticienne d'astreinte", (28, 45), "le soir, peut devoir partir d'un coup", 1),
    ("en couple, sa copine joue aussi", "en couple, son copain joue aussi", (21, 35),
     "le soir, souvent en duo", 2),
    ("ancien joueur de console qui découvre les MMO", "ancienne joueuse de console qui découvre les MMO",
     (18, 30), "le soir, sessions longues le week-end", 3),
    ("ouvrier en 3x8", "ouvrière en 3x8", (24, 50), "à des horaires qui changent chaque semaine", 1),
    ("expatrié au Québec", "expatriée au Québec", (25, 40), "la nuit, heure française, à cause du décalage", 1),
    ("vétéran des raids de 2006", "vétérane des raids de 2006", (32, 44), "deux ou trois soirs par semaine", 2),
    ("graphiste indépendant", "graphiste indépendante", (25, 40), "quand il veut, souvent l'après-midi", 1),
    ("apprenti mécanicien", "apprentie mécanicienne", (16, 20), "le soir et le week-end", 2),
    ("militaire", "militaire", (20, 35), "pendant ses permissions, par grosses sessions", 1),
    ("en arrêt maladie après une opération", "en arrêt maladie après une opération", (30, 55), "en journée, à son rythme", 1),
    ("surveillant de nuit", "surveillante de nuit", (25, 50), "la nuit, pendant ses rondes calmes", 1),
]
# Les registres regionaux supposent un joueur du coin : pas de « québécois » chez un ado parisien etc.
# (le hasard suffit ; seule contrainte : un expatrie au Quebec n'a pas le registre belge ou sudiste).

# --------------------------------------------------------------------------- objectifs
# (niveau min, niveau max, faction "A"/"H"/"*", texte). Un objectif n'est propose que si
# min <= niveau du bot <= max : le bot vise ce qu'un joueur de son niveau viserait.
LEVEL_GOALS = [
    (1, 9, "*", "atteindre le niveau 10"), (1, 9, "*", "choisir ses deux métiers"),
    (1, 9, "*", "trouver des sacs plus grands"), (1, 9, "*", "économiser pour ses prochains sorts"),
    (5, 12, "*", "monter la cuisine et le secourisme"),
    (12, 18, "H", "faire le Gouffre de Ragefeu"), (15, 24, "H", "faire les Cavernes des Lamentations"),
    (15, 23, "A", "faire les Mortemines"), (20, 28, "H", "faire le Donjon d'Ombrecroc"),
    (20, 28, "A", "faire la Prison de Hurlevent"), (20, 28, "*", "faire les Profondeurs de Brassenoire"),
    (25, 33, "A", "aider à reprendre Gnomeregan"), (25, 33, "*", "faire le Kraal de Tranchebauge"),
    (10, 30, "*", "tenter le Goulet des Chanteguerres"), (20, 60, "*", "jouer au bassin d'Arathi"),
    (20, 30, "A", "finir les quêtes du Bois de la Pénombre"), (20, 30, "H", "finir les quêtes des Serres-Rocheuses"),
    (20, 32, "*", "faire les quêtes des Contreforts de Hautebrande"),
    (28, 42, "*", "faire le Monastère écarlate"), (30, 42, "*", "survivre à la Vallée de Strangleronce"),
    (33, 39, "*", "économiser pour la monture du niveau 40"), (35, 42, "*", "faire les Souilles de Tranchebauge"),
    (38, 46, "*", "faire Uldaman"), (40, 50, "*", "faire Zul'Farrak"), (40, 50, "*", "farmer l'or à Tanaris"),
    (44, 52, "*", "faire Maraudon"), (44, 52, "*", "monter dans Féralas"),
    (48, 55, "*", "faire le Temple englouti"), (48, 56, "*", "explorer le Cratère d'Un'Goro"),
    (50, 58, "*", "faire les Profondeurs de Rochenoire"), (51, 60, "*", "jouer à la Vallée d'Alterac"),
    (53, 59, "*", "monter dans le Berceau-de-l'Hiver"), (55, 60, "*", "atteindre le niveau 60"),
    (56, 60, "*", "faire Stratholme et Scholomance"), (58, 60, "*", "finir son set de donjon"),
    (60, 60, "*", "s'équiper pour le Cœur du Magma"), (60, 60, "*", "économiser pour la monture épique"),
    (60, 60, "*", "trouver un groupe pour Zul'Gurub"), (60, 60, "*", "monter son rang d'honneur"),
    (60, 60, "*", "voir le Repaire de l'Aile noire"),
]

CLASS_GOALS = {
    "warrior": [(1, 9, "atteindre le 10 pour la quête de la posture défensive"),
                (10, 29, "trouver une bonne arme à deux mains"), (28, 34, "faire la quête de la posture berserker"),
                (30, 38, "obtenir la Hache tourbillon"), (36, 40, "porter de la plaque au niveau 40"),
                (50, 60, "s'équiper pour tanker en donjon")],
    "paladin": [(1, 11, "faire la quête de Rédemption au niveau 12"), (10, 40, "soigner en donjon à côté du tank"),
                (34, 40, "obtenir son destrier au niveau 40"), (60, 60, "faire la quête du destrier épique")],
    "hunter": [(1, 9, "atteindre le 10 pour apprivoiser son premier familier"),
               (10, 35, "apprivoiser un familier rare"), (10, 60, "trouver un meilleur arc"),
               (30, 50, "monter la loyauté de son familier"), (60, 60, "faire la quête de Rhok'delar")],
    "rogue": [(1, 15, "s'entraîner à faire les poches des mobs"), (14, 30, "monter le crochetage"),
              (18, 24, "faire la quête des poisons au niveau 20"), (20, 60, "monter ses poisons"),
              (40, 60, "trouver deux bonnes épées")],
    "priest": [(1, 11, "apprendre son sort racial de prêtre au niveau 10"),
               (15, 60, "soigner en donjon sans wipe"), (40, 58, "monter l'ombre pour leveler plus vite"),
               (60, 60, "faire la quête de Bénédiction")],
    "shaman": [(1, 9, "faire la quête du totem de terre"), (10, 19, "faire la quête du totem de feu"),
               (20, 29, "faire la quête du totem d'eau"), (30, 39, "faire la quête du totem d'air"),
               (40, 60, "trouver une bonne masse à deux mains")],
    "mage": [(1, 15, "apprendre à invoquer de l'eau et de la nourriture"),
             (20, 39, "apprendre les téléportations"), (40, 60, "vendre des portails en capitale"),
             (45, 60, "farmer en zone avec le blizzard")],
    "warlock": [(1, 12, "faire la quête du marcheur du Vide au niveau 10"), (18, 24, "faire la quête de la succube"),
                (28, 34, "faire la quête du chasseur corrompu"), (36, 40, "obtenir son destrier corrompu au niveau 40"),
                (48, 56, "faire la quête de l'infernal"), (60, 60, "faire la quête du destrier de l'effroi")],
    "druid": [(1, 9, "atteindre le 10 pour la forme d'ours"), (10, 15, "faire la quête de la forme d'ours"),
              (14, 20, "faire la quête de la forme aquatique"), (20, 29, "apprendre la forme de félin"),
              (28, 34, "apprendre la forme de voyage au niveau 30"), (40, 60, "soigner en donjon en forme normale")],
}

RACE_GOALS = {
    "human": [(1, 5, "finir les quêtes de l'abbaye de Comté-du-Nord"), (4, 10, "faire les quêtes autour de Comté-de-l'Or"),
              (6, 14, "visiter Hurlevent"), (10, 18, "aider les fermiers de la Marche de l'Ouest"),
              (15, 25, "faire les quêtes des Carmines")],
    "dwarf": [(1, 5, "finir les quêtes de la vallée de départ de Dun Morogh"), (4, 11, "faire les quêtes de Kharanos"),
              (6, 14, "visiter Forgefer"), (10, 20, "faire les quêtes du Loch Modan à Thelsamar"),
              (20, 30, "faire les quêtes des Paluns autour de Menethil"),
              (35, 45, "aider la Ligue des explorateurs à Uldaman")],
    "gnome": [(1, 5, "finir les quêtes de la vallée de départ de Dun Morogh"), (1, 20, "monter l'ingénierie"),
              (6, 14, "visiter Forgefer et le quartier des gnomes"), (10, 20, "faire les quêtes du Loch Modan"),
              (24, 33, "aider à reprendre Gnomeregan")],
    "night elf": [(1, 5, "finir les quêtes de Sombrevallon"), (4, 11, "faire les quêtes de Dolanaar"),
                  (6, 14, "visiter Darnassus"), (10, 20, "prendre le bateau pour Auberdine"),
                  (18, 30, "faire les quêtes d'Orneval")],
    "orc": [(1, 5, "finir les quêtes de la Vallée des Épreuves"), (4, 11, "faire les quêtes autour du village de Sen'jin"),
            (6, 14, "visiter Orgrimmar"), (10, 22, "partir dans les Tarides, à la Croisée"),
            (20, 30, "faire les quêtes d'Orneval côté Horde")],
    "troll": [(1, 5, "finir les quêtes de la Vallée des Épreuves"), (4, 11, "faire les quêtes du village de Sen'jin"),
              (6, 14, "visiter Orgrimmar"), (10, 22, "partir dans les Tarides, à la Croisée"),
              (40, 50, "voir Zul'Farrak, une ville troll")],
    "undead": [(1, 5, "finir les quêtes du Glas"), (4, 11, "faire les quêtes de Brill"),
               (6, 14, "visiter Fossoyeuse"), (10, 20, "faire les quêtes de la Forêt des Pins-Argentés"),
               (25, 40, "se venger de la Croisade écarlate")],
    "tauren": [(1, 5, "finir les quêtes du camp Narache"), (4, 11, "faire les quêtes du village de Sabot-de-Sang"),
               (6, 14, "monter aux Pitons-du-Tonnerre"), (10, 22, "partir dans les Tarides, à la Croisée"),
               (25, 35, "faire les quêtes de Mille pointes")],
}

MISC_GOALS = [
    (5, 60, "monter le minage et la forge"), (5, 60, "monter l'herboristerie et l'alchimie"),
    (5, 60, "monter le dépeçage et le travail du cuir"), (5, 60, "monter la couture pour faire ses sacs"),
    (10, 60, "monter l'enchantement"), (5, 60, "monter la pêche"), (10, 60, "se faire de l'or à l'hôtel des ventes"),
    (1, 60, "trouver une guilde sympa"), (10, 60, "collectionner les familiers de compagnie"),
    (1, 60, "explorer toutes les zones de son continent"), (1, 60, "vider son journal de quêtes"),
]

_NAME_RE = re.compile(r"^[A-Za-zÀ-ÿ]{2,12}$")


def safe_name(name):
    """Nom de bot utilisable comme nom de fichier, ou None."""
    name = (name or "").strip()
    return name if _NAME_RE.match(name) else None


def _rng(name):
    seed = int(hashlib.sha256(name.lower().encode("utf-8")).hexdigest()[:16], 16)
    return random.Random(seed)


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _key(value, by_id):
    """'Night Elf' / 'nightelf' / '4' -> 'night elf'."""
    v = _norm(value)
    if v.isdigit():
        return by_id.get(int(v), "")
    return "night elf" if v == "nightelf" else v


def _wchoice(r, items, weight):
    return r.choices(items, weights=[weight(x) for x in items])[0]


def _pick_traits(r):
    n = 3 if r.random() < 0.35 else 2
    out = []
    for t in r.sample(TRAITS, len(TRAITS)):
        if all({t, o} not in INCOMPATIBLE for o in out):
            out.append(t)
        if len(out) == n:
            break
    return out


def _compatible(f, g, age, rp, life):
    if not (f["age"][0] <= age <= f["age"][1] and g["age"][0] <= age <= g["age"][1]):
        return False
    if f["niveau"] == "soigne" and g["reg"] == "familier":
        return False
    if f["niveau"] == "relache" and g["reg"] == "soutenu":
        return False
    if g.get("excl") and f["id"] == "exclamation":
        return False
    if g.get("court") and f["id"] in ("virgules_enchainees", "suspension"):
        return False
    if rp and (not g["rp"] or f["abr"] or f["niveau"] == "relache"):
        return False
    if not rp and g.get("rp_only"):
        return False
    if g["id"] == "nouveau_naif" and "vétéran" in life:
        return False
    if g["id"] in ("belge", "sudiste") and "Québec" in life:
        return False
    return True


def _goals(r, race, cls, lvl):
    fac = FACTION.get(race)
    goals = []
    band = [t for lo, hi, f, t in LEVEL_GOALS if lo <= lvl <= hi and (f == "*" or f == fac)]
    if band:
        goals.append(r.choice(band))
    cl = [t for lo, hi, t in CLASS_GOALS.get(cls, []) if lo <= lvl <= hi]
    if cl and r.random() < 0.75:
        goals.append(r.choice(cl))
    rc = [t for lo, hi, t in RACE_GOALS.get(race, []) if lo <= lvl <= hi]
    if rc and r.random() < 0.55:
        goals.append(r.choice(rc))
    misc = [t for lo, hi, t in MISC_GOALS if lo <= lvl <= hi]
    if misc and len(goals) < 3 and r.random() < 0.4:
        goals.append(r.choice(misc))
    out = []
    for g in goals:
        if g not in out:
            out.append(g)
    return out[:3] or ["monter de niveau"]


def goal_range(text):
    """(niveau min, niveau max) d'un objectif connu, ou None (pour les tests)."""
    for lo, hi, _f, t in LEVEL_GOALS:
        if t == text:
            return lo, hi
    for table in (CLASS_GOALS, RACE_GOALS):
        for entries in table.values():
            for lo, hi, t in entries:
                if t == text:
                    return lo, hi
    for lo, hi, t in MISC_GOALS:
        if t == text:
            return lo, hi
    return None


def generate(name, race="", cls="", level=0):
    """Personnalite deterministe pour ce nom, coherente avec race/classe/niveau."""
    r = _rng(name)
    try:
        lvl = max(1, min(60, int(level)))
    except (TypeError, ValueError):
        lvl = 1
    rk, ck = _key(race, RACE_BY_ID), _key(cls, CLASS_BY_ID)

    femme = r.random() < 0.3
    life = _wchoice(r, LIVES, lambda x: x[4])
    age = r.randint(*life[2])
    metier = life[1] if femme else life[0]

    ton_rp = "rp léger" if r.random() < 0.15 else "hors rp"
    combos = [(f, g) for f in FORMES for g in REGISTRES if _compatible(f, g, age, ton_rp == "rp léger", metier)]
    if not combos:  # garde-fou : on retombe toujours sur un style neutre
        ton_rp = "hors rp"
        combos = [(f, g) for f in FORMES for g in REGISTRES if _compatible(f, g, age, False, metier)] or \
                 [(FORMES[3], REGISTRES[19])]
    forme, reg = r.choices(combos, weights=[g.get("w", 1.0) for _f, g in combos])[0]

    # Un « nouveau » de haut niveau n'est plus credible : il devient simplement curieux
    # (remplacement apres le tirage, pour que le style ne bouge pas pour les autres bots).
    if reg["id"] == "nouveau_naif" and lvl > 25:
        reg = next(g for g in REGISTRES if g["id"] == "curieux")
    if reg.get("court"):
        longueur = LONGUEURS[0][0]
    elif reg["id"] == "conseiller":
        longueur = LONGUEURS[2][0]
    else:
        longueur = _wchoice(r, LONGUEURS, lambda x: x[1])[0]

    # Une seule expression de registre : avec deux, le petit modele les place de force a chaque reponse.
    tics = r.sample(reg["tics"], min(2, len(reg["tics"])))[:1]
    if r.random() < 0.35:
        perso = [t for t, fam in TICS_PERSO if not (fam and reg["reg"] == "soutenu")]
        tics.append(r.choice(perso))

    smiley = ""
    x = r.random()
    if x < reg["sm"] * 0.35:
        smileys = "souvent"
    elif x < reg["sm"]:
        smileys = "rarement"
    else:
        smileys = "jamais"
    if smileys != "jamais":
        smiley = _wchoice(r, SMILEYS, lambda s: s[1])[0]

    parts = [forme["txt"], reg["txt"], "réponses " + longueur,
             "ses expressions : " + ", ".join("« %s »" % t if not t.startswith(("dit ", "commence", "finit", "ajoute"))
                                                else t for t in tics) + " (au plus une par réplique, souvent aucune)"]
    if smileys == "jamais":
        parts.append("jamais de smiley (ni :) ni ^^)")
    elif smileys == "rarement":
        parts.append("très rarement un smiley %s, au plus une réplique sur cinq, aucun autre smiley" % smiley)
    else:
        parts.append("met souvent %s en fin de phrase, aucun autre smiley" % smiley)
    if ton_rp == "rp léger":
        # Le style ne depend pas de la race (meme nom -> meme style) ; les expressions de race
        # sont dans « expressions_rp » (a ajouter au prompt, voir docs/BOTS_PERSONAS.md).
        parts.append("roleplay léger : glisse parfois une expression de sa race, sans en faire trop")
    else:
        parts.append("hors roleplay : parle en joueur, pas en personnage")

    traits = _pick_traits(r)
    grp = 0.7
    if "solitaire" in traits:
        grp = 0.25
    elif "sociable" in traits or "bavard" in traits:
        grp = 0.95
    elif "timide" in traits:
        grp = 0.5
    joueur = "joueuse" if femme else "joueur"
    vie = "%s de %d ans, %s ; joue %s" % (joueur, age, metier, life[3])

    return {
        "nom": name,
        "race": RACE_FR.get(rk, race or ""),
        "classe": CLASS_FR.get(ck, cls or ""),
        "faction": {"A": "Alliance", "H": "Horde"}.get(FACTION.get(rk), ""),
        "style": " ; ".join(parts),
        "traits": traits,
        "vie": vie,
        "objectifs": _goals(r, rk, ck, lvl),
        "aime_grouper": r.random() < grp,
        "joueur": joueur,
        "age": age,
        "heures_de_jeu": life[3],
        "style_id": forme["id"] + "+" + reg["id"],
        "forme": forme["id"],
        "registre": reg["id"],
        "longueur": longueur,
        "tics": tics,
        "smileys": smileys,
        "smiley": smiley,
        "ton_rp": ton_rp,
        "expressions_rp": RP_FLAVOR.get(rk, "") if ton_rp == "rp léger" else "",
        "niveau_genere": lvl,
        "version": PERSONA_VERSION,
        "source": "generee",
    }


class PersonaStore:
    def __init__(self, state_dir, repo_dir=REPO_PERSONAS):
        self.repo_dir = repo_dir
        self.state_dir = os.path.join(state_dir, "personas")
        self._cache = {}

    def _load(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def _save(self, name, p):
        try:
            os.makedirs(self.state_dir, exist_ok=True)
            tmp = os.path.join(self.state_dir, name + ".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(p, f, ensure_ascii=False, indent=1)
            os.replace(tmp, os.path.join(self.state_dir, name + ".json"))
        except OSError:
            pass

    def get(self, name, race="", cls="", level=0):
        name = safe_name(name)
        if not name:
            return None
        key = name.lower()
        if key in self._cache:
            return self._cache[key]
        p = self._load(os.path.join(self.repo_dir, name + ".json"))
        if p is None:
            p = self._load(os.path.join(self.state_dir, name + ".json"))
            # Fiche generee par une ancienne version : on la regenere, en gardant l'histoire relue.
            if p is not None and str(p.get("source", "")).startswith("generee") \
                    and p.get("version", 1) < PERSONA_VERSION:
                old = p
                p = generate(name, race or "", cls or "", level)
                if old.get("histoire"):
                    p["histoire"] = old["histoire"]
                    p["source"] = old.get("source", p["source"])
                self._save(name, p)
            # Le bot a pris des niveaux depuis : objectifs perimes -> on les recalcule.
            elif p is not None and str(p.get("source", "")).startswith("generee") and level:
                try:
                    lvl = int(level)
                except (TypeError, ValueError):
                    lvl = 0
                rng = [goal_range(g) for g in p.get("objectifs", [])]
                if lvl and any(x is not None and not (x[0] <= lvl <= x[1]) for x in rng):
                    p["objectifs"] = generate(name, race, cls, lvl)["objectifs"]
                    p["niveau_genere"] = lvl
                    self._save(name, p)
        if p is None:
            p = generate(name, race, cls, level)
            self._save(name, p)
        p.setdefault("nom", name)
        self._cache[key] = p
        return p
