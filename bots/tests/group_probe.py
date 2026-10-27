#!/usr/bin/env python3
"""Sonde groupe + donjon sur le serveur de TEST des bots (realmd 3725, monde 8086).

Compte WLTEST2 (identifiants lus dans C:\\Wowlheim\\run\\test_account2.txt, jamais affiches).
  1. attend que le serveur de test soit pret (port 8086 + "World initialized" dans mangosd.out) ;
  2. choisit un bot Alliance en ligne de niveau proche, .appear pres de lui, l'invite (CMSG_GROUP_INVITE),
     verifie SMSG_GROUP_LIST et les tables groups / group_member ;
  3. parle en /groupe et attend une reponse en /groupe (preuve serveur : bridge_log.jsonl, ch = party) ;
  4. .tele vers l'entree des Mortemines (carte 0) puis dans l'instance (carte 36) ; verifie la position du bot
     (.gps sur le bot selectionne, .saveall + SQL), essaie le chuchotement "summon" s'il ne suit pas ;
  5. quitte le groupe (CMSG_GROUP_DISBAND) et se deconnecte (CMSG_LOGOUT_REQUEST).

  python -I bots/tests/group_probe.py [--bot Nom] [--player Nom] [--chat-wait 45] [--follow-wait 60]
"""
import argparse
import json
import os
import re
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chat_probe  # noqa: E402  (redirige les ports 3724/8085 -> 3725/8086 et importe wlclient)
from chat_probe import sql, parse_chat, CHAT_NAMES, OP_MESSAGECHAT, OP_SMSG_MESSAGECHAT  # noqa: E402

wlclient = chat_probe.wlclient

MANGOSD_OUT = r"C:\Wowlheim\bots\run\mangosd.out"
CRASH_DIR = r"C:\Wowlheim\bots\run\Crashes"
BRIDGE_LOG = r"C:\Wowlheim\bots\state\bridge_log.jsonl"
ACCOUNT_FILE = r"C:\Wowlheim\run\test_account2.txt"

CHAT_PARTY, CHAT_WHISPER = 1, 6
OP_GROUP_INVITE, OP_GROUP_DISBAND = 0x06E, 0x07B
OP_SMSG_GROUP_LIST, OP_SMSG_PARTY_COMMAND_RESULT, OP_SMSG_GROUP_DECLINE = 0x07D, 0x07F, 0x074
OP_SMSG_GROUP_DESTROYED, OP_SMSG_GROUP_UNINVITE = 0x07C, 0x077
OP_SET_SELECTION = 0x13D
OP_LOGOUT_REQUEST, OP_SMSG_LOGOUT_RESPONSE, OP_SMSG_LOGOUT_COMPLETE = 0x04B, 0x04C, 0x04D
OP_PING = 0x1DC
ALLIANCE = (1, 3, 4, 7)


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


# ---------------------------------------------------------------- 1. serveur pret
def server_ready():
    try:
        with chat_probe._orig_connect(("127.0.0.1", 8086), timeout=2):
            pass
    except OSError:
        return False, "port 8086 ferme"
    try:
        with open(MANGOSD_OUT, encoding="utf-8", errors="replace") as f:
            if "World initialized" not in f.read():
                return False, "mangosd.out sans 'World initialized'"
    except OSError:
        return False, "mangosd.out absent"
    return True, "pret"


def crash_check():
    """Process mangosd_bots.exe absent -> renvoie le dernier rapport de plantage (texte) ; sinon None."""
    import subprocess
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq mangosd_bots.exe"], capture_output=True, text=True,
                         errors="replace").stdout
    if "mangosd_bots.exe" in out:
        return None
    txts = sorted((os.path.join(CRASH_DIR, f) for f in os.listdir(CRASH_DIR) if f.endswith(".txt")),
                  key=os.path.getmtime) if os.path.isdir(CRASH_DIR) else []
    return txts[-1] if txts else "(aucun rapport)"


def wait_server(timeout):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        ok, why = server_ready()
        if ok:
            return True
        if why != last:
            log("serveur pas pret : " + why)
            last = why
        time.sleep(5)
    return False


# ---------------------------------------------------------------- session joueur
def credentials():
    kv = {}
    with open(ACCOUNT_FILE, encoding="utf-8") as f:
        for line in f:
            if ": " in line:
                k, v = line.split(": ", 1)
                kv[k.strip()] = v.strip()
    return kv["account"], kv["password"]


def player_session(name):
    user, pw = credentials()
    s = wlclient.Session(user, pw)
    chars = s.chars()
    pick = None
    if name:
        pick = next(((g, n) for g, n in chars if n.lower() == name.lower()), None)
        if pick is None:
            code = s.create(name, race=1, cls=1)        # humain guerrier (Alliance)
            if code == 0x2E:
                chars = s.chars()
                pick = next((g, n) for g, n in chars if n.lower() == name.lower())
            else:
                log("creation de %s refusee : 0x%02X" % (name, code))
    if pick is None:
        humans = [(g, n) for g, n in chars
                  if sql("SELECT race FROM characters WHERE guid=%d" % (g & 0xFFFFFFFF)) in ([["1"]], [["3"]], [["4"]], [["7"]])]
        if humans:
            pick = humans[0]
        else:
            code = s.create("Groupeur", race=1, cls=1)
            if code != 0x2E:
                raise RuntimeError("aucun personnage Alliance et creation refusee : 0x%02X" % code)
            pick = next((g, n) for g, n in s.chars() if n == "Groupeur")
    s.login(pick[0])
    s.name = pick[1]
    return s


class Pump:
    """Lit tous les paquets ; garde le chat, les paquets de groupe, les lignes systeme."""

    def __init__(self, s):
        self.s = s
        self.names = {}
        self.chat = []          # (t_rel, type, nom, texte)
        self.events = []        # (op, data)
        self.t0 = time.time()
        self.last_ping = 0

    def name(self, low):
        if low not in self.names:
            r = sql("SELECT name FROM characters WHERE guid=%d" % low)
            self.names[low] = r[0][0] if r else str(low)
        return self.names[low]

    def run(self, wait, until=None):
        end = time.time() + wait
        self.s.s.settimeout(0.5)
        while time.time() < end:
            if time.time() - self.last_ping > 20:
                self.s.send(OP_PING, struct.pack("<II", int(time.time()) & 0xFFFF, 0))
                self.last_ping = time.time()
            try:
                op, d = self.s.read()
            except socket.timeout:
                continue
            if op == OP_SMSG_MESSAGECHAT:
                c = parse_chat(d)
                if not c or c[0] == 7 or c[1] == (self.s.guid & 0xFFFFFFFF):
                    continue
                who = self.name(c[1]) if c[1] else "serveur"
                item = (time.time() - self.t0, c[0], who, c[2])
                self.chat.append(item)
                log("chat (%s) %s : %s" % (CHAT_NAMES.get(c[0], c[0]), who, c[2]))
            elif op in (0x0C7, 0x03E):                  # teleport inattendu : acquitter
                if op == 0x0C7:
                    mask, i = d[0], 1
                    i += bin(mask).count("1")
                    counter = struct.unpack("<I", d[i:i + 4])[0]
                    self.s.send(0x0C7, struct.pack("<QII", self.s.guid, counter, int(time.time() * 1000) & 0xFFFFFFFF))
                else:
                    self.s.send(0x0DC)
            else:
                self.events.append((op, d))
            if until and until(op, d):
                return True
        return False


def system_lines(pump, command, collect=1.5):
    n0 = len(pump.chat)
    pump.s.send(OP_MESSAGECHAT, struct.pack("<II", 0, 0) + command.encode() + b"\0")
    pump.run(collect)
    return [c[3] for c in pump.chat[n0:] if c[1] == 10]


def parse_group_list(d):
    """SMSG_GROUP_LIST 1.12 : type, sous-groupe/flags, nombre, [nom, guid, en ligne, flags]..., guid du chef."""
    if len(d) < 6:
        return [], None
    n = struct.unpack("<I", d[2:6])[0]
    i, members = 6, []
    for _ in range(n):
        j = d.index(b"\0", i)
        nm = d[i:j].decode("utf-8", "replace")
        guid = struct.unpack("<Q", d[j + 1:j + 9])[0]
        online = d[j + 9]
        members.append((nm, guid & 0xFFFFFFFF, online))
        i = j + 11
    leader = struct.unpack("<Q", d[i:i + 8])[0] & 0xFFFFFFFF if len(d) >= i + 8 else None
    return members, leader


def gps_of(pump, guid_low):
    """Selectionne le bot puis .gps : (map, x, y, z) si le bot est visible sur la meme carte, sinon None."""
    pump.s.send(OP_SET_SELECTION, struct.pack("<Q", guid_low))
    pump.run(0.3)
    lines = " | ".join(system_lines(pump, ".gps", 1.5))
    m = re.search(r"Map: (\d+).*?X: ([-\d.]+) Y: ([-\d.]+) Z: ([-\d.]+)", lines)
    return (int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)), lines) if m else (None, lines)


def my_gps(pump):
    pump.s.send(OP_SET_SELECTION, struct.pack("<Q", pump.s.guid))
    pump.run(0.3)
    lines = " | ".join(system_lines(pump, ".gps", 1.5))
    m = re.search(r"Map: (\d+).*?X: ([-\d.]+) Y: ([-\d.]+) Z: ([-\d.]+)", lines)
    return (int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))) if m else None


def db_pos(guid_low):
    r = sql("SELECT map, ROUND(position_x,1), ROUND(position_y,1), ROUND(position_z,1), online FROM characters WHERE guid=%d" % guid_low)
    return r[0] if r else None


def bridge_lines(since, bot):
    out = []
    try:
        with open(BRIDGE_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("t", 0) >= since and e.get("bot") == bot:
                    out.append(e)
    except OSError:
        pass
    return out


def player_state(s):
    """(sante, drapeaux) en base apres .saveall ; drapeau 0x10 = fantome."""
    r = sql("SELECT health, playerFlags FROM characters WHERE guid=%d" % (s.guid & 0xFFFFFFFF))
    return r[0] if r else None


def revive(pump, s):
    """Ressuscite le joueur s'il est mort / fantome (un maitre mort n'attire pas ses bots)."""
    system_lines(pump, ".saveall", 1.0)
    st = player_state(s)
    if st and (int(st[1]) & 0x10 or st[0] == "0"):
        log("joueur mort (sante=%s, drapeaux=%s) : .revive" % tuple(st))
        system_lines(pump, ".revive", 1.0)


def dist(a, b):
    return ((a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2 + (a[3] - b[3]) ** 2) ** 0.5


def follow_check(pump, bot, guid, me, wait, label):
    """Attend jusqu'a `wait` s que le bot soit sur la meme carte a < 30 m ; renvoie (ok, derniere position)."""
    end, last = time.time() + wait, None
    while time.time() < end:
        g = gps_of(pump, guid)
        if g[0] is not None:
            last = g
            d = dist(g, me) if g[0] == me[0] else None
            log("%s : %s carte %d (%.0f, %.0f, %.0f), distance %s" % (label, bot, g[0], g[1], g[2], g[3],
                                                                  "%.1f m" % d if d is not None else "-"))
            if d is not None and d < 30:
                return True, g
        else:
            log("%s : %s pas visible sur ma carte (.gps -> %s)" % (label, bot, g[1][:120]))
        pump.run(5)
    return False, last


# ---------------------------------------------------------------- deroule
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot")
    ap.add_argument("--player", help="personnage du compte WLTEST2 (defaut : le premier personnage Alliance)")
    ap.add_argument("--ready-timeout", type=float, default=900)
    ap.add_argument("--chat-wait", type=float, default=45)
    ap.add_argument("--follow-wait", type=float, default=60)
    ap.add_argument("--min-level", type=int, default=10, help="niveau minimal du bot choisi automatiquement "
                    "(les Mortemines exigent le niveau 10)")
    ap.add_argument("--message", default="salut, merci pour l'invit, tu viens aux Mortemines ?")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    res = {}

    # 1. serveur pret
    if not wait_server(a.ready_timeout):
        log("ECHEC 1 : serveur de test pas pret apres %.0fs" % a.ready_timeout)
        return 2
    log("OK 1 : serveur pret (port 8086 ouvert, 'World initialized')")
    res[1] = True

    s = player_session(a.player)
    pump = Pump(s)
    mylvl = int(sql("SELECT level FROM characters WHERE guid=%d" % (s.guid & 0xFFFFFFFF))[0][0])
    log("joueur %s (niveau %d) connecte" % (s.name, mylvl))
    pump.run(2)
    revive(pump, s)
    system_lines(pump, ".gm off", 0.6)
    system_lines(pump, ".gm visible on", 0.6)

    # 2. choix du bot + invitation
    bots = sql("SELECT c.guid, c.name, c.race, c.class, c.level, c.map, c.zone, "
               "ROUND(SQRT(POW(c.position_x + 11208.7, 2) + POW(c.position_y - 1673.5, 2))) FROM characters c "
               "JOIN classicrealmd_bots.account a ON a.id = c.account "
               "WHERE c.online = 1 AND a.username LIKE 'RNDBOT%' AND c.race IN (1,3,4,7)")
    in_group = {r[0] for r in sql("SELECT memberGuid FROM group_member")}
    # niveau >= 10 (Mortemines) et a plus de 1000 m de l'entree, pour que "master far away" (> 500 m) ait un sens
    cands = [b for b in bots if b[0] not in in_group and int(b[4]) >= a.min_level
             and (b[5] != "0" or float(b[7]) > 1000)]
    if a.bot:
        cands = [b for b in bots if b[1].lower() == a.bot.lower()]
    else:
        cands.sort(key=lambda b: (b[5] != "0", abs(int(b[4]) - mylvl)))   # carte 0 d'abord, puis niveau proche
    if not cands:
        log("ECHEC 2 : aucun bot Alliance en ligne disponible")
        s.close()
        return 1
    guid, bot = int(cands[0][0]), cands[0][1]
    log("bot choisi : %s guid=%d race=%s classe=%s niveau=%s carte=%s zone=%s (a %s m de l'entree des Mortemines)"
        % tuple([bot, guid] + cands[0][2:8]))
    s.teleport_cmd(".appear " + bot)
    pump.run(3)
    me = my_gps(pump)
    g = gps_of(pump, guid)
    log("moi : %s ; bot : %s" % (me, g[:4] if g[0] is not None else g[1][:120]))

    n0 = len(pump.events)
    t_inv = time.time()
    s.send(OP_GROUP_INVITE, bot.encode() + b"\0")
    log("invitation envoyee a %s" % bot)
    got_list = pump.run(20, until=lambda op, d: op in (OP_SMSG_GROUP_LIST, OP_SMSG_GROUP_DECLINE)
                        or (op == OP_SMSG_GROUP_LIST))
    for op, d in pump.events[n0:]:
        if op == OP_SMSG_PARTY_COMMAND_RESULT:
            j = d.index(b"\0", 4)
            log("SMSG_PARTY_COMMAND_RESULT op=%d nom=%s resultat=%d" % (
                struct.unpack("<I", d[:4])[0], d[4:j].decode("utf-8", "replace"), struct.unpack("<I", d[j + 1:j + 5])[0]))
        elif op == OP_SMSG_GROUP_DECLINE:
            log("SMSG_GROUP_DECLINE : %s" % d.split(b"\0")[0].decode("utf-8", "replace"))
        elif op == OP_SMSG_GROUP_LIST:
            members, leader = parse_group_list(d)
            log("SMSG_GROUP_LIST (%.1fs) membres=%s chef=%s" % (time.time() - t_inv, members, leader))
    pump.run(3)
    lists = [d for op, d in pump.events[n0:] if op == OP_SMSG_GROUP_LIST]
    if lists:
        log("dernier SMSG_GROUP_LIST : membres (hors moi)=%s chef=%s" % parse_group_list(lists[-1]))
    grp = sql("SELECT g.groupId, g.leaderGuid, m.memberGuid FROM `groups` g JOIN group_member m ON m.groupId = g.groupId "
              "WHERE g.leaderGuid = %d" % (s.guid & 0xFFFFFFFF))
    log("SQL groups/group_member : %s" % grp)
    lists = [d for op, d in pump.events[n0:] if op == OP_SMSG_GROUP_LIST]
    res[2] = bool(lists and any(m[1] == guid for m in parse_group_list(lists[-1])[0]))
    log(("OK" if res[2] else "ECHEC") + " 2 : %s %s dans le groupe" % (bot, "est" if res[2] else "n'est pas"))
    if not res[2]:
        s.close()
        return 1

    # 3. /groupe
    pump.run(5)                     # laisse passer le "hello" et les reglages du bot
    t_chat = time.time()
    n0 = len(pump.chat)
    log("%s (groupe) : %s" % (s.name, a.message))
    s.send(OP_MESSAGECHAT, struct.pack("<II", CHAT_PARTY, 0) + a.message.encode() + b"\0")
    pump.run(a.chat_wait, until=lambda op, d: op == OP_SMSG_MESSAGECHAT and d[0] == CHAT_PARTY
             and (parse_chat(d) or (0, 0))[1] == guid)
    party = [c for c in pump.chat[n0:] if c[1] == CHAT_PARTY and c[2] == bot]
    for c in party:
        log("reponse en /groupe apres %.1fs : %s" % (c[0] - (t_chat - pump.t0), c[3]))
    pump.run(2)
    bl = bridge_lines(t_chat - 2, bot)
    for e in bl:
        log("bridge_log : %s" % json.dumps(e, ensure_ascii=False))
    res[3] = bool(party)
    log(("OK" if res[3] else "ECHEC") + " 3 : reponse du bot en /groupe" + ("" if party else " absente en %.0fs" % a.chat_wait))

    # 4. donjon : entree (carte 0) puis instance (carte 36)
    # Un maitre mort (fantome) ne declenche jamais "master far away" : on s'assure d'etre vivant.
    # Le joueur (niveau bas) se fait tuer par les Defias de l'entree : mode GM (les monstres l'ignorent)
    # pendant l'attente ; le declencheur ne regarde pas le mode GM du maitre.
    revive(pump, s)
    system_lines(pump, ".gm on", 0.6)
    system_lines(pump, ".gm visible on", 0.6)
    s.teleport_cmd(".tele TheDeadmines")
    pump.run(3)
    me = my_gps(pump)
    log("moi a l'entree des Mortemines : %s" % (me,))
    ok, last = follow_check(pump, bot, guid, me, a.follow_wait, "entree")
    alone = ok
    if not ok:
        log("joueur vivant ? %s" % player_state(s))
        log("le bot ne suit pas seul : chuchotement 'summon'")
        s.send(OP_MESSAGECHAT, struct.pack("<II", CHAT_WHISPER, 0) + bot.encode() + b"\0summon\0")
        pump.run(5)
        ok, last = follow_check(pump, bot, guid, me, 20, "entree apres summon")
    res["4a"] = ok
    log(("OK" if ok else "ECHEC") + " 4a : bot a l'entree des Mortemines" + (" (seul, sans 'summon')" if alone else
                                                                          " (apres 'summon')" if ok else ""))

    # l'instance exige le niveau 10 (SMSG_AREA_TRIGGER_MESSAGE) : le mode GM leve cette condition pour le joueur
    revive(pump, s)
    system_lines(pump, ".gm on", 0.6)
    system_lines(pump, ".gm visible on", 0.6)
    n0 = len(pump.events)
    s.teleport_cmd(".tele deadmines")
    pump.run(3)
    for op, d in pump.events[n0:]:
        if op == 0x2B8:
            log("SMSG_AREA_TRIGGER_MESSAGE : %s" % d[4:].split(b"\0")[0].decode("utf-8", "replace"))
    system_lines(pump, ".gm off", 0.6)
    me = my_gps(pump)
    log("moi dans l'instance : %s" % (me,))
    ok, last = follow_check(pump, bot, guid, me, a.follow_wait, "instance") if me else (False, None)
    alone = ok
    if not ok and me:
        log("joueur vivant ? %s" % player_state(s))
        log("le bot n'est pas dans l'instance : chuchotement 'summon'")
        s.send(OP_MESSAGECHAT, struct.pack("<II", CHAT_WHISPER, 0) + bot.encode() + b"\0summon\0")
        pump.run(5)
        ok, last = follow_check(pump, bot, guid, me, 20, "instance apres summon")
    system_lines(pump, ".saveall", 2)
    pump.run(2)
    log("SQL position du bot apres .saveall (map, x, y, z, online) : %s" % db_pos(guid))
    res["4b"] = bool(ok and me and me[0] == 36)
    log(("OK" if res["4b"] else "ECHEC") + " 4b : bot dans l'instance (carte 36)" + (
        " (seul, sans 'summon')" if res["4b"] and alone else " (apres 'summon')" if res["4b"] else ""))

    # 5. quitter le groupe + deconnexion
    s.send(OP_GROUP_DISBAND)
    pump.run(3)
    grp = sql("SELECT g.groupId FROM `groups` g JOIN group_member m ON m.groupId = g.groupId "
              "WHERE m.memberGuid IN (%d, %d)" % (s.guid & 0xFFFFFFFF, guid))
    log("SQL groupe apres CMSG_GROUP_DISBAND : %s" % (grp or "aucun"))
    s.send(OP_LOGOUT_REQUEST)
    out = pump.run(30, until=lambda op, d: op == OP_SMSG_LOGOUT_COMPLETE)
    s.close()
    res[5] = bool(out and not grp)
    log(("OK" if res[5] else "ECHEC") + " 5 : groupe quitte%s, deconnexion %s" % (
        "" if not grp else " (groupe encore en base)", "complete" if out else "sans SMSG_LOGOUT_COMPLETE"))
    crash = crash_check()
    if crash:
        log("PLANTAGE : mangosd_bots.exe absent, rapport %s" % crash)
    log("resume : %s" % " ".join("%s=%s" % (k, "OK" if v else "ECHEC") for k, v in res.items()))
    return 0 if all(res.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
