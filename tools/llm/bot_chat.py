#!/usr/bin/env python3
"""Client LLM local (LM Studio) pour le chat des bots Wowlheim.

Stdlib uniquement. Ne parle qu'a 127.0.0.1 / localhost. Ne leve jamais
d'exception vers l'appelant : en cas de probleme, generate_reply() renvoie None.

Usage CLI :
  python -I bot_chat.py --persona persona.json --zone "Elwynn" --place "Auberge" \
      --player "Salut, tu fais quoi ?"
  python -I bot_chat.py --demo        # 3 scenarios + latence
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

DEFAULT_MODEL = "nvidia-nemotron-3.5-bolt-e4b-4gb"
DEFAULT_URL = "http://127.0.0.1:1234/v1"
DEFAULT_TIMEOUT = 8.0
MAX_CHARS = 200
ALLOWED_HOSTS = ("127.0.0.1", "localhost")

SYSTEM_TEMPLATE = (
    "Tu incarnes un joueur de World of Warcraft 1.12 (Vanilla) qui discute dans le chat. "
    "Reponds en francais, en UNE seule phrase courte (moins de 150 caracteres), "
    "sans markdown, sans emoji, sans guillemets, sans lien, sans ecrire ton nom. "
    "Reste dans ton personnage. Ne parle jamais de modele, d'IA ou de serveur.\n"
    "Personnage : {name}, archetype {archetype}. Objectifs : {goals}. "
    "Zones preferees : {zones}. Ton : {tone}."
)

_THINK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.S | re.I)
_THINK_OPEN_RE = re.compile(r"<think(?:ing)?>.*", re.S | re.I)  # balise jamais fermee
_THINK_CLOSE_RE = re.compile(r"^.*?</think(?:ing)?>", re.S | re.I)  # ouverture perdue
_LINK_RE = re.compile(r"(https?://|www\.|\b[\w-]+\.(?:com|net|org|fr|io|gg|tv|ru|cn)\b|\|H)", re.I)
_QUOTES = "\"'`«»“”„"
_MD_RE = re.compile(r"[*_#>~]+")


def validate_base_url(url):
    """Renvoie l'URL sans slash final, ou leve ValueError si l'hote n'est pas local."""
    p = urlparse(url)
    if p.scheme != "http" or (p.hostname or "").lower() not in ALLOWED_HOSTS:
        raise ValueError("URL refusee (hote local http uniquement) : %r" % (url,))
    if p.username or p.password:
        raise ValueError("URL refusee (identifiants interdits)")
    return url.rstrip("/")


def filter_reply(text, max_chars=MAX_CHARS):
    """Nettoie la sortie du LLM. Renvoie None si inutilisable (vide ou lien)."""
    if not isinstance(text, str):
        return None
    text = _THINK_RE.sub(" ", text)
    text = _THINK_OPEN_RE.sub(" ", text)
    if "</think" in text.lower():
        text = _THINK_CLOSE_RE.sub(" ", text)
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = "".join(c for c in text if c.isprintable())
    if _LINK_RE.search(text):
        return None
    text = _MD_RE.sub("", text)
    text = text.replace("`", "")
    text = text.replace("’", "'").replace("‘", "'")
    text = "".join(c for c in text if c not in _QUOTES or c == "'")  # garde l'apostrophe (l'auberge)
    text = re.sub(r"\s+", " ", text).strip().strip("'").strip()
    if not text:
        return None
    if len(text) > max_chars:
        cut = text[:max_chars]
        # coupe au dernier espace si possible pour ne pas tronquer un mot
        sp = cut.rfind(" ")
        if sp > max_chars * 0.6:
            cut = cut[:sp]
        text = cut.rstrip(" ,;:-")
    return text or None


def build_messages(persona, context):
    p = persona or {}
    c = context or {}
    zones = p.get("zones_preferees", p.get("zones", []))
    goals = p.get("objectifs", p.get("goals", []))
    sysmsg = SYSTEM_TEMPLATE.format(
        name=p.get("nom", p.get("name", "Inconnu")),
        archetype=p.get("archetype", "aventurier"),
        goals=", ".join(goals) if isinstance(goals, list) else goals,
        zones=", ".join(zones) if isinstance(zones, list) else zones,
        tone=p.get("ton", p.get("tone", "neutre")),
    )
    user = "Zone : %s. Lieu : %s. Le joueur dit : %s\nTa replique :" % (
        c.get("zone", "?"), c.get("lieu", c.get("place", "?")), c.get("joueur", c.get("player", "")))
    return [{"role": "system", "content": sysmsg}, {"role": "user", "content": user}]


def _post(url, payload, timeout):
    # Pas de proxy systeme : on parle uniquement a la boucle locale.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read(1_000_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        e.close()
        raise


def generate_reply(persona, context, model=DEFAULT_MODEL, base_url=DEFAULT_URL,
                   timeout=DEFAULT_TIMEOUT, max_chars=MAX_CHARS, max_tokens=600):
    """Renvoie une replique filtree (str) ou None. Ne leve jamais, sauf URL non locale
    (ValueError : erreur de configuration, volontairement bruyante)."""
    base = validate_base_url(base_url)
    payload = {
        "model": model,
        "messages": build_messages(persona, context),
        "temperature": 0.8,
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        data = _post(base + "/chat/completions", payload, timeout)
        content = data["choices"][0]["message"].get("content")
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError,
            TypeError, AttributeError):
        return None
    except Exception:  # repli total : le chat ne doit jamais faire planter le serveur
        return None
    return filter_reply(content, max_chars)


DEMO_PERSONA = {
    "nom": "Thorgrim", "archetype": "guerrier nain bourru",
    "objectifs": ["monter de niveau", "trouver une bonne hache"],
    "zones_preferees": ["Dun Morogh", "Loch Modan"], "ton": "laconique et un peu sarcastique",
}
DEMO_SCENARIOS = [
    {"zone": "Dun Morogh", "lieu": "pres du feu de camp", "joueur": "Salut ! Tu fais quoi ici ?"},
    {"zone": "Elwynn", "lieu": "devant l'auberge de Goldshire", "joueur": "Tu connais une bonne quete pour niveau 10 ?"},
    {"zone": "Loch Modan", "lieu": "au barrage", "joueur": "Tu veux grouper avec moi ?"},
]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--persona", help="fichier JSON de personnalite")
    ap.add_argument("--zone", default="?")
    ap.add_argument("--place", default="?")
    ap.add_argument("--player", default="")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        validate_base_url(a.url)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    if a.demo:
        jobs = [(DEMO_PERSONA, s) for s in DEMO_SCENARIOS]
    else:
        persona = DEMO_PERSONA
        if a.persona:
            with open(a.persona, encoding="utf-8") as f:
                persona = json.load(f)
        jobs = [(persona, {"zone": a.zone, "lieu": a.place, "joueur": a.player})]
    rc = 0
    for persona, ctx in jobs:
        t0 = time.perf_counter()
        r = generate_reply(persona, ctx, a.model, a.url, a.timeout)
        dt = time.perf_counter() - t0
        print("[%.2fs] joueur: %s\n         bot  : %s" % (dt, ctx["joueur"], r))
        if r is None:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
