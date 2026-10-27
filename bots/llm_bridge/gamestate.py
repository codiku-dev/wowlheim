"""Etat de jeu reel d'un bot, lu en base, pour qu'il parle de ce qu'il fait vraiment.

Le pont ne recoit de playerbots que race/classe/niveau/zone. Ici on ajoute, depuis la base
personnages du serveur de test : or, quetes en cours, groupe avec l'interlocuteur, heure reelle.
Lecture seule, resultat en cache quelques secondes ; en cas d'erreur : etat vide (le bot parle
quand meme). Les noms sont deja valides par persona.safe_name avant d'arriver ici.
"""
import subprocess
import threading
import time

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
CHAR_DB = "classiccharacters_bots"
WORLD_DB = "classicmangos_bots"


class GameState:
    def __init__(self, char_db=CHAR_DB, world_db=WORLD_DB, ttl=10.0, query=None):
        self.char_db = char_db
        self.world_db = world_db
        self.ttl = ttl
        self.cache = {}
        self.lock = threading.Lock()
        self._query = query or self._mysql

    def _mysql(self, sql):
        out = subprocess.run([MYSQL, "-uroot", "-h127.0.0.1", "-N", "-B", "--default-character-set=utf8mb4",
                              self.char_db, "-e", sql], capture_output=True, text=True, encoding="utf-8",
                             timeout=3)
        return [line.split("\t") for line in out.stdout.splitlines() if line]

    def get(self, bot, other):
        key = (bot.lower(), other.lower())
        now = time.time()
        with self.lock:
            hit = self.cache.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        try:
            state = self._read(bot, other)
        except Exception:
            state = {}
        with self.lock:
            self.cache[key] = (now, state)
        return state

    def _read(self, bot, other):
        rows = self._query(
            "SELECT c.guid, c.money, "
            "(SELECT COUNT(*) FROM group_member a JOIN group_member b ON a.groupId=b.groupId "
            " JOIN characters o ON o.guid=b.memberGuid WHERE a.memberGuid=c.guid AND o.name='%s') "
            "FROM characters c WHERE c.name='%s'" % (other.replace("'", ""), bot.replace("'", "")))
        if not rows:
            return {}
        guid, money, grouped = (rows[0] + ["", "", ""])[:3]
        state = {"or": int(money) // 10000 if money.isdigit() else None,
                 "quetes": self._quests(guid) if guid.isdigit() else [],
                 "groupe_avec_lui": grouped not in ("", "0", "NULL")}
        return state

    def _quests(self, guid):
        """Quetes en cours avec progression reelle (mobs tues / objets ramasses), 3 au plus."""
        w = self.world_db
        slots = ", ".join(
            "s.mobcount%d, q.ReqCreatureOrGOCount%d, COALESCE(ct%d.Name, gt%d.name, ''), "
            "s.itemcount%d, q.ReqItemCount%d, COALESCE(it%d.name, '')" % ((n,) * 7) for n in range(1, 5))
        joins = " ".join(
            "LEFT JOIN %s.creature_template ct%d ON q.ReqCreatureOrGOId%d > 0 AND ct%d.Entry = q.ReqCreatureOrGOId%d "
            "LEFT JOIN %s.gameobject_template gt%d ON q.ReqCreatureOrGOId%d < 0 AND gt%d.entry = -q.ReqCreatureOrGOId%d "
            "LEFT JOIN %s.item_template it%d ON it%d.entry = q.ReqItemId%d" % (w, n, n, n, n, w, n, n, n, n, w, n, n, n)
            for n in range(1, 5))
        rows = self._query("SELECT q.entry, q.QuestLevel, q.Title, s.status, %s FROM character_queststatus s "
                           "JOIN %s.quest_template q ON q.entry = s.quest %s "
                           "WHERE s.guid = %s AND s.rewarded = 0 AND s.status IN (1, 3) LIMIT 3" % (slots, w, joins, guid))
        out = []
        for r in rows:
            entry, level, title, status = r[:4]
            prog = []
            for n in range(4):
                done, req, name, idone, ireq, iname = r[4 + 6 * n: 10 + 6 * n]
                if req not in ("", "0", "NULL") and name:
                    prog.append("%s/%s %s" % (done, req, name))
                if ireq not in ("", "0", "NULL") and iname:
                    prog.append("%s/%s %s" % (idone, ireq, iname))
            out.append({"id": int(entry), "niveau": int(level) if level.lstrip("-").isdigit() else 0, "titre": title,
                        "finie": status == "1", "progres": prog})
        return out


def quest_link(q):
    """Lien de quete du chat 1.12 (titre exact de la base, sinon le serveur rejette le lien)."""
    return "|cffffff00|Hquest:%d:%d|h[%s]|h|r" % (q["id"], max(q["niveau"], 1), q["titre"])


def describe(state, hour=None):
    """Phrase d'etat pour le prompt systeme (francais, courte)."""
    hour = time.localtime().tm_hour if hour is None else hour
    parts = ["Il est %dh chez toi." % hour]
    if state.get("or") is not None:
        parts.append("Tu as environ %d pieces d'or sur toi." % state["or"])
    if state.get("quetes"):
        qs = []
        for q in state["quetes"]:
            d = "[[q:%d]] « %s »" % (q["id"], q["titre"])
            if q["finie"]:
                d += " (objectifs finis, a rendre)"
            elif q["progres"]:
                d += " (" + ", ".join(q["progres"]) + ")"
            qs.append(d)
        parts.append("Ce que tu fais vraiment en ce moment, tes quetes en cours (titres anglais du journal) : %s. "
                     "Si on te demande ce que tu fais ou quelle quete, reponds avec ca, ta progression comprise. "
                     "Pour montrer une quete dans le chat, ecris exactement son code [[q:numero]] : il devient un lien "
                     "cliquable ; ne le fais que si on te demande ta quete ou si c'est utile." % " ; ".join(qs))
    elif state:
        parts.append("Tu n'as AUCUNE quete en cours en ce moment : tu tues des monstres pour l'xp, tu te balades ou "
                     "tu vas en chercher. N'invente jamais de quete ni de lien.")
    if state.get("groupe_avec_lui"):
        parts.append("Tu es en groupe avec lui en ce moment.")
    return " ".join(parts)
