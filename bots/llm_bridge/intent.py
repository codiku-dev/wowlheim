#!/usr/bin/env python3
"""Intention d'un message de joueur a un bot -> commande playerbots (route POST /intent du pont).

playerbots ne comprend que des ordres anglais exacts (« follow », « stay »...) et WowlheimFrenchCommands.h
traduit seulement des phrases francaises courtes et exactes. Pour une phrase libre (« tu viens on va aux
mortemines ? », « attends moi devant la porte »), mangosd appelle ce module en asynchrone ; on demande a
TypeSafe Jev (API en ligne autorisee par Robin, reponse typee « choice » en ~0,2 s) quelle action le joueur
demande, puis on la traduit en une commande playerbots qui EXISTE (ChatTriggerContext.h / ChatActionContext.h).

Le texte de reponse du bot reste genere par le LLM local (route /api/v1/generate) ; ici on ne renvoie
qu'une commande, ou "" (rien a faire). Toute erreur, tout doute (confiance < seuil) -> "".

Garde-fous : chuchotement et groupe seulement, message <= 255 caracteres, delai Jev court (2 s), cache
court (un meme message de groupe recu par 4 bots = 1 seul appel Jev), interrupteur (--no-intent du pont,
ou fichier <state>/intent_off present = coupe a chaud), journal <state>/intent_log.jsonl.
La cle n'est jamais journalisee ni renvoyee.
"""
import json
import os
import re
import threading
import time
import unicodedata
import urllib.request

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
KEY_FILE = r"C:\Wowlheim\bots\state\typesafe_api_key.txt"
MAX_MESSAGE_CHARS = 255
MIN_CONFIDENCE = 0.8
JEV_TIMEOUT = 2.0
CACHE_TTL = 60.0

# Canaux acceptes (noms courts du pont ou textes de playerbots) -> nom court.
CHANNELS = {"whisper": "whisper", "in private message": "whisper",
            "party": "party", "in party chat": "party", "raid": "party", "in raid chat": "party"}

# Etiquettes proposees a Jev. Les descriptions disent quand choisir chaque etiquette ; « discussion » est
# le choix par defaut (une question, un avis, un projet sans demande d'action immediate).
INTENTS = {
    "suivre": "Le joueur demande au personnage de le suivre, de venir avec lui, de l'accompagner ou de se "
              "remettre en route maintenant (ex. « viens avec moi », « allez on y va », « suis moi jusqu'a la ville »).",
    "rester": "Le joueur demande au personnage de s'arreter, de ne plus bouger, de l'attendre ou de rester a un "
              "endroit (ex. « attends moi devant la porte », « reste ici je reviens », « bouge pas deux minutes »).",
    "attaquer": "Le joueur demande au personnage d'attaquer, de taper ou de tuer un ennemi maintenant, en general "
                "sa cible (ex. « tape celui-la », « aide moi a tuer le kobold », « on le defonce »).",
    "rejoindre": "Le joueur demande au personnage de le rejoindre la ou il est alors qu'ils sont loin l'un de "
                 "l'autre, de venir le retrouver ou de se teleporter pres de lui (ex. « rejoins moi a Hurlevent », "
                 "« t'es ou ? viens me retrouver »).",
    "aller_donjon": "Le joueur propose ou demande d'aller ensemble dans un donjon ou une instance maintenant "
                    "(ex. « tu viens on va aux mortemines ? », « on fait la Lame ? », « go donjon »).",
    "quete_ensemble": "Le joueur propose de faire une quete ensemble, maintenant (ex. « on fait la quete des "
                      "kobolds ensemble ? », « tu m'aides pour ma quete ? »).",
    "grouper": "Le joueur demande au personnage de l'inviter dans un groupe ou propose de grouper, sans parler "
               "d'une quete ou d'un donjon precis (ex. « tu veux grouper ? », « tu peux m'inviter ? »).",
    "quitter": "Le joueur demande au personnage de quitter le groupe (ex. « tu peux quitter le groupe », "
               "« sors du groupe merci »).",
    "echanger": "Le joueur demande au personnage d'ouvrir un echange avec lui (fenetre d'echange) pour lui "
                "donner ou recevoir un objet ou de l'or (ex. « ouvre l'echange », « tu peux me trade ? »).",
    "ramasser": "Le joueur demande au personnage de ramasser le butin ou de fouiller les corps (ex. « ramasse "
                "le loot », « pense a looter »).",
    "donner_chef": "Le joueur demande au personnage de lui passer la direction du groupe (ex. « passe moi le "
                   "lead », « donne moi le chef »).",
    "discussion": "Aucune action precise demandee maintenant : salutation, question, avis, plaisanterie, "
                  "recit, projet pour plus tard, remerciement, ou demande impossible a executer (ex. « ca va ? », "
                  "« t'es quel niveau ? », « demain on ira aux mortemines », « merci pour le coup de main »).",
}

INSTRUCTIONS = (
    "Dans World of Warcraft, un joueur ecrit au personnage nomme dans l'etat. Quelle action demande-t-il a CE "
    "personnage de faire tout de suite ? Choisis « discussion » s'il ne demande rien de concret maintenant, "
    "s'il parle au passe ou d'un projet lointain, ou s'il s'adresse a quelqu'un d'autre."
)

# Commande playerbots selon l'intention, quand l'expediteur est dans le groupe du bot.
# aller_donjon / quete_ensemble -> follow : le bot colle au joueur, le declencheur Wowlheim « master far
# away » le fait venir a pied (jamais de teleportation) ; une quete partagee par le joueur (bouton
# Partager) est acceptee seule par la strategie « quest » (declencheur « quest share »).
COMMANDS_IN_GROUP = {
    "suivre": "follow", "rester": "stay", "attaquer": "attack", "rejoindre": "follow",
    "aller_donjon": "follow", "quete_ensemble": "follow", "grouper": "", "quitter": "leave",
    "echanger": "", "ramasser": "loot", "donner_chef": "give leader", "discussion": "",
}
# Expediteur hors du groupe : il faut d'abord grouper (le bot invite le joueur, commande « invite »).
# Un maitre hors groupe garde les ordres simples ; un inconnu n'obtient qu'une invitation (meme regle que
# les ordres francais exacts dans PlayerbotAI::HandleCommand).
GROUPING_INTENTS = ("grouper", "aller_donjon", "quete_ensemble")
# Retour Robin : jamais de teleportation d'un bot vers le joueur (il vient a pied), pas d'echange impose.
MASTER_ONLY = {"suivre": "follow", "rester": "stay", "attaquer": "attack", "rejoindre": "follow"}
# Toutes les commandes que ce module peut renvoyer (mangosd verifie la meme liste).
ALLOWED_COMMANDS = {"follow", "stay", "attack", "invite", "leave", "loot", "give leader"}

_NAME_RE = re.compile(r"^[A-Za-z\u00C0-\u00FF]{2,12}$")
_LINK = re.compile(r"\|c[0-9a-fA-F]{8}\|H[^|]*\|h(\[[^\]]*\])\|h\|r")
_COLOR = re.compile(r"\|c[0-9a-fA-F]{8}|\|r|\|H[^|]*\|h|\|h")


def normalize(text):
    """minuscules, sans accents, espaces fusionnes : cle du cache."""
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.findall(r"[a-z0-9]+", t))


def command_for(intent, relation):
    """Commande playerbots pour une intention et la relation de l'expediteur avec le bot."""
    if relation == "groupe":
        return COMMANDS_IN_GROUP.get(intent, "")
    if intent in GROUPING_INTENTS:
        return "invite"
    if relation == "maitre":
        return MASTER_ONLY.get(intent, "")
    return ""


def read_key(path=KEY_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def jev_post(state, key, timeout=JEV_TIMEOUT):
    """Un appel Jev « choice ». Renvoie (etiquette, confiance). Leve en cas d'erreur."""
    body = json.dumps({"model": JEV_MODEL, "state": state, "questions": {"intention": {
        "type": "choice", "instructions": INSTRUCTIONS, "criteria": INTENTS}}}).encode("utf-8")
    req = urllib.request.Request(JEV_URL, data=body, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read(200_000).decode("utf-8"))
    ans = data["answers"]["intention"]
    choice = ans.get("choice")
    conf = ans.get("confidence")
    if conf is None and isinstance(ans.get("probabilities"), dict):
        conf = ans["probabilities"].get(choice)
    return str(choice or ""), float(conf or 0.0)


class IntentClassifier:
    def __init__(self, state_dir, enabled=True, classify=None, key_path=KEY_FILE, known_bots=None,
                 min_confidence=MIN_CONFIDENCE, cache_ttl=CACHE_TTL, timeout=JEV_TIMEOUT, clock=time.time):
        self.state_dir = state_dir
        self.enabled = enabled
        self.key_path = key_path
        self._key = None
        self._classify = classify or self._call_jev
        self.known_bots = known_bots or (lambda: set())
        self.min_confidence = min_confidence
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self.clock = clock
        self.lock = threading.Lock()
        self.cache = {}          # cle -> (etiquette, confiance, t)
        self.inflight = {}       # cle -> threading.Event (meme message recu par plusieurs bots en meme temps)
        self.log_path = os.path.join(state_dir, "intent_log.jsonl")
        self.stats = {}

    def _call_jev(self, state):
        if self._key is None:
            self._key = read_key(self.key_path) or ""
        if not self._key:
            raise RuntimeError("cle absente")
        return jev_post(state, self._key, self.timeout)

    def is_on(self):
        return self.enabled and not os.path.exists(os.path.join(self.state_dir, "intent_off"))

    @staticmethod
    def build_state(bot, other, channel, message):
        canal = "en message prive (chuchotement)" if channel == "whisper" else "dans le chat de son groupe"
        return ("Jeu : World of Warcraft 1.12, joueurs francais. Personnage qui recoit le message : %s. "
                "Le joueur %s lui ecrit %s : %s" % (bot, other, canal, message))

    def _log(self, entry):
        try:
            if os.path.exists(self.log_path) and os.path.getsize(self.log_path) > 5_000_000:
                os.replace(self.log_path, self.log_path + ".1")
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _classify_cached(self, key, state):
        """(etiquette, confiance, depuis_cache). Un seul appel Jev par message identique a la fois."""
        while True:
            with self.lock:
                now = self.clock()
                for k in [k for k, v in self.cache.items() if now - v[2] > self.cache_ttl]:
                    del self.cache[k]
                hit = self.cache.get(key)
                if hit:
                    return hit[0], hit[1], True
                ev = self.inflight.get(key)
                if ev is None:
                    ev = self.inflight[key] = threading.Event()
                    owner = True
                else:
                    owner = False
            if not owner:
                ev.wait(self.timeout + 1.0)
                with self.lock:
                    hit = self.cache.get(key)
                if hit:
                    return hit[0], hit[1], True
                raise RuntimeError("appel concurrent en echec")
            try:
                label, conf = self._classify(state)
                with self.lock:
                    self.cache[key] = (label, conf, self.clock())
                return label, conf, False
            finally:
                with self.lock:
                    self.inflight.pop(key, None)
                ev.set()

    def handle(self, raw):
        """Renvoie {"command", "intent", "confidence"}. Ne leve jamais ; tout echec -> commande vide."""
        t0 = time.time()
        raw = raw if isinstance(raw, dict) else {}
        bot = str(raw.get("bot", "") or "").strip()[:32]
        other = str(raw.get("other", "") or "").strip()[:32]
        channel = CHANNELS.get(str(raw.get("channel", "") or "").strip().lower(), "")
        relation = str(raw.get("relation", "groupe") or "").strip().lower()
        if relation not in ("groupe", "maitre", "inconnu"):
            relation = "inconnu"
        msg = str(raw.get("message", "") or "")
        res = {"command": "", "intent": "", "confidence": 0.0}
        entry = {"t": round(t0, 1), "bot": bot, "other": other, "ch": channel, "rel": relation, "msg": msg[:300]}
        why = None
        try:
            why = self._handle(bot, other, channel, relation, msg, res, entry)
        except Exception as e:  # jamais d'exception vers mangosd
            why = "exception:%s" % type(e).__name__
            res.update(command="")
        entry.update(intent=res["intent"], conf=res["confidence"], cmd=res["command"], why=why or "ok",
                     dt=round(time.time() - t0, 3))
        self.stats[why or "ok"] = self.stats.get(why or "ok", 0) + 1
        self._log(entry)
        return res

    def _handle(self, bot, other, channel, relation, msg, res, entry):
        if not self.is_on():
            return "coupe"
        if not _NAME_RE.match(bot) or not _NAME_RE.match(other):
            return "requete_invalide"
        if not channel:
            return "canal"
        if channel != "whisper" and relation == "inconnu":
            return "canal"
        if not msg.strip() or len(msg) > MAX_MESSAGE_CHARS:
            return "longueur"
        msg = _COLOR.sub("", _LINK.sub(r"\1", msg))
        msg = "".join(c for c in msg if c.isprintable()).strip()
        if not msg or msg.startswith((".", "!", "#", "@")):
            return "commande"
        words = set(normalize(msg).split())
        if channel == "party" and bot.lower() not in words:
            # Un ordre de groupe qui nomme un autre bot ne concerne pas celui-ci.
            others = {n.lower() for n in self.known_bots()} - {bot.lower()}
            if words & {normalize(n) for n in others}:
                return "adresse_a_un_autre"
        # Le nom du bot change la cible, pas l'intention : cle de cache sans lui (groupe = meme message).
        key = (channel, normalize(msg))
        label, conf, cached = self._classify_cached(key, self.build_state(bot, other, channel, msg))
        entry["cache"] = cached
        if label not in INTENTS:
            return "etiquette_inconnue"
        res["intent"], res["confidence"] = label, round(conf, 3)
        if conf < self.min_confidence:
            return "confiance_basse"
        cmd = command_for(label, relation)
        if cmd and cmd not in ALLOWED_COMMANDS:
            return "commande_refusee"
        res["command"] = cmd
        return None if cmd else "sans_commande"
