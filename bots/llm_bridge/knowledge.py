"""Wowlheim : petite base de connaissances WoW vanilla (1.12, VF) pour les bots LLM.

Le modele local connait mal les details de vanilla (ou est son entraineur, ou acheter sa monture,
niveau des donjons...). Ce module choisit, par mots-cles, 0 a `limit` faits courts de
knowledge_vanilla.json a injecter dans le prompt systeme UNIQUEMENT quand le message du joueur
porte sur le sujet. La plupart des messages ("salut ca va") ne recoivent rien.

Usage :
    from knowledge import relevant_facts, prompt_block
    facts = relevant_facts("ou j'apprends la forme d'ours ?", {"race": "night elf", "classe": "druid", "niveau": 10})
    sysmsg += prompt_block(facts)      # "" si aucun fait

Stdlib uniquement, ~0,1 ms par appel (index charge une fois au premier appel).
"""

import json
import os
import re
import unicodedata

KB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge_vanilla.json")

PROMPT_PREFIX = ("Ce que ton personnage sait du jeu sur ce sujet (utilise-le seulement si ça aide à répondre, "
                 "avec tes propres mots, sans tout réciter) : ")

# --------------------------------------------------------------------------- normalisation

def norm(text):
    """minuscules, sans accents, ponctuation -> espace, entoure d'espaces (pour chercher ' mot ')."""
    s = unicodedata.normalize("NFKD", str(text or "").lower().replace("œ", "oe").replace("æ", "ae"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return " " + s + " " if s else " "


def _alias_map(table):
    return {norm(alias).strip(): key for key, aliases in table.items() for alias in aliases}


# Mots designant une classe / race / faction dans un message (cible la question sur autre chose que le bot).
CLASS_WORDS = _alias_map({
    "warrior": ["guerrier", "guerriers", "guerriere", "warrior", "war"],
    "paladin": ["paladin", "paladins", "pala", "palas"],
    "hunter": ["chasseur", "chasseurs", "chasseresse", "chasso", "hunt", "hunter", "huntard"],
    "rogue": ["voleur", "voleurs", "voleuse", "fufu", "rogue", "rogues"],
    "priest": ["pretre", "pretres", "pretresse", "priest", "prete"],
    "shaman": ["chaman", "chamans", "chamane", "cham", "shaman", "shamy"],
    "mage": ["mage", "mages"],
    "warlock": ["demoniste", "demonistes", "demo", "lock", "warlock"],
    "druid": ["druide", "druides", "druidesse", "dudu", "druid"],
})
RACE_WORDS = _alias_map({
    "human": ["humain", "humains", "humaine", "human"],
    "dwarf": ["nain", "nains", "naine", "dwarf"],
    "gnome": ["gnome", "gnomes"],
    "night elf": ["elfe", "elfes", "elfe de la nuit", "elfes de la nuit", "night elf", "nightelf", "kaldorei"],
    "orc": ["orc", "orcs", "orque"],
    "undead": ["mort vivant", "morts vivants", "mort vivante", "undead", "reprouve", "reprouves"],
    "tauren": ["tauren", "taurens", "taurene"],
    "troll": ["troll", "trolls", "trollesse"],
})
FACTION_WORDS = {"alliance": "A", "alliances": "A", "ally": "A", "horde": "H", "hordeux": "H"}
RACE_FACTION = {"human": "A", "dwarf": "A", "gnome": "A", "night elf": "A",
                "orc": "H", "undead": "H", "tauren": "H", "troll": "H"}
RACE_BY_ID = {1: "human", 2: "orc", 3: "dwarf", 4: "night elf", 5: "undead", 6: "tauren", 7: "gnome", 8: "troll"}
CLASS_BY_ID = {1: "warrior", 2: "paladin", 3: "hunter", 4: "rogue", 5: "priest", 7: "shaman", 8: "mage",
               9: "warlock", 11: "druid"}

# Questions generiques ("ou xp a mon niveau ?", "quel donjon ?") : declenchent une categorie entiere,
# mais seuls les faits dont la tranche de niveau convient sont gardes.
GROUP_TRIGGERS = {
    "zone": ["ou xp", "ou xper", "ou pex", "ou pexer", "ou leveler", "ou level", "ou up", "ou monter",
             "ou quete", "ou queter", "ou quester", "quelle zone", "quelles zones", "zone pour", "zone de mon niveau",
             "zones de mon niveau", "ou aller", "je vais ou", "on va ou", "j vais ou", "spot xp", "spot pour xp",
             "ou farm xp", "ou monter de niveau", "ou faire mes quetes", "ou continuer"],
    "donjon": ["quel donjon", "quels donjons", "quelle instance", "quelles instances", "quel dj", "quel donj",
               "un donjon", "une instance", "un dj", "des donjons", "donjon pour", "instance pour",
               "donjon de mon niveau", "donjons de mon niveau", "faire un donjon", "faire une instance"],
}
# Categories (noms de zones, mots courants de mecanique/metier) qui ne declenchent que sur une question.
NEEDS_QUESTION = {"zone", "mecanique", "metier"}
QUESTION_RE = re.compile(r"\?|^ (ou|quel|quelle|quels|quelles|comment|combien|c est ou|cest ou|c est quoi|"
                         r"c koi|kel|kelle|ya|y a|tu sais|vous savez|qui|pourquoi|est ce) |"
                         r" (niveau|niv|lvl|lv|level|ou|quel|quelle|combien|comment) ")
LEVEL_RE = re.compile(r" (?:niveau|niv|nv|lvl|lv|level|lvl\.) ?(\d{1,2}) | au (\d{1,2}) | (\d{1,2}) ?(?:lvl|lv) ")

# --------------------------------------------------------------------------- index

_FACTS = None


def _load(path=KB_PATH):
    global _FACTS
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    facts = []
    for raw in data["facts"]:
        kws = sorted({norm(k) for k in raw.get("kw", []) if norm(k).strip()}, key=len, reverse=True)
        ctx = sorted({norm(k) for k in raw.get("ctx", []) if norm(k).strip()})
        facts.append({
            "id": raw["id"], "cat": raw["cat"], "text": raw["text"], "kw": kws, "ctx": ctx,
            "faction": raw.get("faction"), "classes": set(raw.get("classes", [])),
            "races": set(raw.get("races", [])), "levels": raw.get("levels"),
        })
    _FACTS = facts
    return facts


def facts():
    return _FACTS if _FACTS is not None else _load()


# --------------------------------------------------------------------------- contexte

def _key(value, by_id, words):
    v = norm(value).strip()
    if not v:
        return ""
    if v.isdigit():
        return by_id.get(int(v), "")
    return words.get(v, v.replace("nightelf", "night elf"))


def _mentions(text, table):
    """Cles de `table` citees dans text (deja normalise)."""
    return {key for alias, key in table.items() if " " + alias + " " in text}


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _context(msg, bot_ctx):
    bot_ctx = bot_ctx or {}
    race = _key(bot_ctx.get("race") or bot_ctx.get("bot_race"), RACE_BY_ID, RACE_WORDS)
    cls = _key(bot_ctx.get("classe") or bot_ctx.get("class") or bot_ctx.get("bot_class"), CLASS_BY_ID, CLASS_WORDS)
    fac = str(bot_ctx.get("faction") or "").strip().lower()
    fac = {"a": "A", "alliance": "A", "h": "H", "horde": "H"}.get(fac) or RACE_FACTION.get(race, "")
    level = _int(bot_ctx.get("niveau") or bot_ctx.get("level") or bot_ctx.get("bot_level"))

    m_cls, m_race = _mentions(msg, CLASS_WORDS), _mentions(msg, RACE_WORDS)
    m_fac = {v for k, v in FACTION_WORDS.items() if " " + k + " " in msg}
    lv = LEVEL_RE.search(msg)
    if lv:
        asked = next(int(g) for g in lv.groups() if g)
        if 1 <= asked <= 60:
            level = asked
    if len(m_fac) != 1 and m_race:
        m_fac = {RACE_FACTION[r] for r in m_race}
    return {
        "classes": m_cls or ({cls} if cls else set()),
        "races": m_race or ({race} if race else set()),
        "faction": next(iter(m_fac)) if len(m_fac) == 1 else fac,
        "level": level,
        "zone": norm(bot_ctx.get("zone") or ""),
    }


# --------------------------------------------------------------------------- selection

def _score(f, msg, ctx, groups, is_question):
    matched = [k for k in f["kw"] if k in msg]
    group_only = False
    if matched:
        best = max(matched, key=len)
        s = 2.0 + 0.25 * (best.count(" ") - 2) + 0.5 * min(len(matched) - 1, 2)
    elif f["cat"] in groups:
        s, group_only = 1.0, True
    else:
        return None
    if f["cat"] in NEEDS_QUESTION and not (is_question or group_only):
        return None
    s += 0.5 * min(sum(1 for k in f["ctx"] if k in msg), 3)

    if f["classes"] and ctx["classes"]:
        s += 2.0 if f["classes"] & ctx["classes"] else -2.5
    if f["races"] and ctx["races"]:
        s += 1.5 if f["races"] & ctx["races"] else -1.0
    if f["faction"] and ctx["faction"]:
        s += 1.0 if f["faction"] == ctx["faction"] else -2.0
    lv, rng = ctx["level"], f["levels"]
    if rng and lv:
        lo, hi = rng
        if lo - 2 <= lv <= hi + 1:
            s += 1.5 if group_only else 0.5
            s -= 0.02 * abs(lv - (lo + hi) / 2.0)  # departage : tranche la plus centree
        elif group_only:
            return None
        else:
            s -= 0.5
    elif group_only and not lv:
        return None  # "quel donjon ?" sans niveau connu : on ne devine pas
    if ctx["zone"].strip() and any(k in ctx["zone"] for k in f["kw"]):
        s += 0.5
    return s


def relevant_facts(message, bot_ctx=None, limit=3):
    """Faits (textes) a injecter pour ce message, du plus pertinent au moins pertinent ; [] le plus souvent.

    bot_ctx : dict avec race, classe (ou class), niveau (ou level), zone, faction ("A"/"H"/"Alliance"/"Horde")
    -- valeurs anglaises (serveur), francaises ou identifiants numeriques acceptes.
    """
    msg = norm(message)
    if len(msg) < 4 or limit <= 0:
        return []
    ctx = _context(msg, bot_ctx)
    groups = {cat for cat, phrases in GROUP_TRIGGERS.items() if any(" " + p + " " in msg for p in phrases)}
    is_question = bool(QUESTION_RE.search(str(message or "")) or QUESTION_RE.search(msg))
    scored = []
    for f in facts():
        s = _score(f, msg, ctx, groups, is_question)
        if s is not None and s > 0.25:
            scored.append((s, f["text"]))
    if not scored:
        return []
    scored.sort(key=lambda x: -x[0])
    cutoff = 0.6 * scored[0][0]
    return [t for s, t in scored if s >= cutoff][:limit]


def prompt_block(fact_texts):
    """Phrase a ajouter au prompt systeme ("" si aucun fait)."""
    if not fact_texts:
        return ""
    return " " + PROMPT_PREFIX + " ".join(fact_texts)
