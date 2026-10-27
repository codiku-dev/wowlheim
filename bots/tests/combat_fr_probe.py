#!/usr/bin/env python3
"""Sonde « silence en combat » + « textes predefinis en francais » sur le serveur de TEST des bots
(realmd 3725, monde 8086). Compte WLTEST3 (identifiants lus dans C:\\Wowlheim\\bots\\state\\test_account_wltest3.txt,
jamais affiches).

A. Silence en combat
   1. personnage Alliance (humain guerrier), .levelup au niveau du bot, .appear pres du bot, invitation en groupe ;
   2. choisit une creature attaquable proche (SQL creature/creature_template), la cible (CMSG_SET_SELECTION) et
      chuchote « attack » au bot ; attend un paquet de combat qui le concerne (SMSG_ATTACKSTART /
      SMSG_ATTACKERSTATEUPDATE / SMSG_SPELLNONMELEEDAMAGELOG) ;
   3. PENDANT le combat : /groupe puis chuchotement ; releve les paquets de combat du bot avant/apres chaque message ;
   4. hors combat (plus aucun paquet de combat du bot depuis 15 s) : memes messages -> reponse attendue (controle) ;
   5. lignes de bridge_log.jsonl du bot pour chaque fenetre.
B. Textes predefinis
   phrases du bot a l'invitation, puis ecoute (/dire, canaux General/DefenseLocale/RechercheGroupe d'Elwynn a
   Comte-de-l'Or, puis Hurlevent : Commerce/General) ; classe chaque ligne de bot : LLM (bridge_log), table FR,
   table EN (sauvegarde anglaise), inconnue (probablement C++ code en dur), avec heuristique de langue.

  python -I bots/tests/combat_fr_probe.py [--bot Nom] [--player Nom] [--listen 180] [--skip-a] [--skip-b]
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
import chat_probe  # noqa: E402  (redirige 3724/8085 -> 3725/8086 et importe wlclient)
import group_probe  # noqa: E402
from chat_probe import sql, CHAT_NAMES, OP_MESSAGECHAT, OP_SMSG_MESSAGECHAT  # noqa: E402
from group_probe import parse_group_list, bridge_lines, crash_check, wait_server  # noqa: E402

wlclient = chat_probe.wlclient
MYSQL = chat_probe.MYSQL
ACCOUNT_FILE = r"C:\Wowlheim\bots\state\test_account_wltest3.txt"
BACKUP_TEXTS = r"C:\Wowlheim\bots\backup_ai_playerbot_texts.sql"
BRIDGE_LOG = group_probe.BRIDGE_LOG

CHAT_SAY, CHAT_PARTY, CHAT_WHISPER, CHAT_CHANNEL = 0, 1, 6, 14
OP_GROUP_INVITE, OP_GROUP_DISBAND, OP_SMSG_GROUP_LIST = 0x06E, 0x07B, 0x07D
OP_SET_SELECTION, OP_JOIN_CHANNEL, OP_SMSG_CHANNEL_NOTIFY = 0x13D, 0x097, 0x099
OP_ATTACKSTART, OP_ATTACKSTOP, OP_ATTACKERSTATEUPDATE, OP_SPELLDMG = 0x143, 0x144, 0x14A, 0x250
OP_LOGOUT_REQUEST, OP_SMSG_LOGOUT_COMPLETE, OP_PING = 0x04B, 0x04D, 0x1DC
HOSTILE_FACTIONS = (7, 14, 16, 17, 18, 20, 21, 22, 24, 26, 32, 34, 38, 44, 48, 54, 73, 189)
UNIT_HIGH = 0xF130


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def credentials():
    kv = {}
    with open(ACCOUNT_FILE, encoding="utf-8") as f:
        for line in f:
            if ":" in line:
                k, v = line.split(":", 1)
                kv[k.strip()] = v.strip()
    return kv["account"], kv["password"]


def player_session(name):
    user, pw = credentials()
    s = wlclient.Session(user, pw)
    chars = s.chars()
    pick = next(((g, n) for g, n in chars if n.lower() == name.lower()), None)
    if pick is None:
        code = s.create(name, race=1, cls=1)            # humain guerrier (Alliance)
        if code != 0x2E:
            raise RuntimeError("creation de %s refusee : 0x%02X" % (name, code))
        pick = next((g, n) for g, n in s.chars() if n.lower() == name.lower())
        log("personnage %s cree (humain guerrier)" % pick[1])
    s.login(pick[0])
    s.name = pick[1]
    return s


def packed_guid(d, i):
    mask = d[i]
    i += 1
    g = 0
    for b in range(8):
        if mask & (1 << b):
            g |= d[i] << (8 * b)
            i += 1
    return g, i


def parse_chat_full(d):
    """(type, guid_bas, texte, canal) ; None pour les types ignores (PNJ...)."""
    t = d[0]
    chan = ""
    if t in (0, 1, 5):
        guid, off = struct.unpack("<Q", d[5:13])[0], 21
    elif t in (6, 7, 8, 10):
        guid, off = struct.unpack("<Q", d[5:13])[0], 13
    elif t == CHAT_CHANNEL:
        j = d.index(b"\0", 5)
        chan = d[5:j].decode("utf-8", "replace")
        j += 1 + 4
        guid, off = struct.unpack("<Q", d[j:j + 8])[0], j + 8
    else:
        return None
    ln = struct.unpack("<I", d[off:off + 4])[0]
    return t, guid & 0xFFFFFFFF, d[off + 4:off + 4 + ln - 1].decode("utf-8", "replace"), chan


class Pump:
    """Lit tous les paquets ; garde le chat, les paquets de combat, de groupe et de canal."""

    def __init__(self, s):
        self.s = s
        self.names = {}
        self.chat = []          # (t_abs, type, guid_bas, nom, texte, canal)
        self.combat = []        # (t_abs, op, attaquant_bas, victime_bas, guid_attaquant, guid_victime)
        self.events = []        # (t_abs, op, data) pour groupe / canaux
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
            now = time.time()
            if op == OP_SMSG_MESSAGECHAT:
                c = parse_chat_full(d)
                if not c or c[0] == 7 or c[1] == (self.s.guid & 0xFFFFFFFF):
                    continue
                who = self.name(c[1]) if c[1] else "serveur"
                self.chat.append((now, c[0], c[1], who, c[2], c[3]))
                if c[0] != 10:
                    log("chat (%s%s) %s : %s" % (CHAT_NAMES.get(c[0], c[0]), " " + c[3] if c[3] else "", who, c[2]))
            elif op == OP_ATTACKSTART and len(d) >= 16:
                a, v = struct.unpack("<QQ", d[:16])
                self.combat.append((now, "ATTACKSTART", a & 0xFFFFFFFF, v & 0xFFFFFFFF, a, v))
            elif op == OP_ATTACKSTOP:
                a, i = packed_guid(d, 0)
                v, i = packed_guid(d, i)
                self.combat.append((now, "ATTACKSTOP", a & 0xFFFFFFFF, v & 0xFFFFFFFF, a, v))
            elif op == OP_ATTACKERSTATEUPDATE:
                a, i = packed_guid(d, 4)
                v, i = packed_guid(d, i)
                self.combat.append((now, "ATTACKERSTATEUPDATE", a & 0xFFFFFFFF, v & 0xFFFFFFFF, a, v))
            elif op == OP_SPELLDMG:
                v, i = packed_guid(d, 0)
                a, i = packed_guid(d, i)
                self.combat.append((now, "SPELLNONMELEEDAMAGELOG", a & 0xFFFFFFFF, v & 0xFFFFFFFF, a, v))
            elif op in (0x0C7, 0x03E):
                if op == 0x0C7:
                    i = 1 + bin(d[0]).count("1")
                    counter = struct.unpack("<I", d[i:i + 4])[0]
                    self.s.send(0x0C7, struct.pack("<QII", self.s.guid, counter, int(now * 1000) & 0xFFFFFFFF))
                else:
                    self.s.send(0x0DC)
            elif op in (OP_SMSG_GROUP_LIST, OP_SMSG_CHANNEL_NOTIFY, 0x07F, 0x074, 0x06F):
                self.events.append((now, op, d))
            if until and until(op, d):
                return True
        return False

    def system(self, command, collect=1.5):
        n0 = len(self.chat)
        self.s.send(OP_MESSAGECHAT, struct.pack("<II", 0, 0) + command.encode() + b"\0")
        self.run(collect)
        return [c[4] for c in self.chat[n0:] if c[1] == 10]

    def bot_combat(self, low, since=0.0, until=None):
        """Paquets de combat ou le bot est attaquant (joueur, guid haut = 0)."""
        return [c for c in self.combat if c[0] >= since and (until is None or c[0] <= until)
                and ((c[2] == low and c[4] >> 48 == 0) or (c[3] == low and c[5] >> 48 == 0))]


def fmt_combat(pump, c, t0):
    def nm(g, full):
        return pump.name(g) if full >> 48 == 0 else "creature entry=%d low=%d" % ((full >> 24) & 0xFFFFFF, full & 0xFFFFFF)
    return "%+.1fs %s %s -> %s" % (c[0] - t0, c[1], nm(c[2], c[4]), nm(c[3], c[5]))


def my_gps(pump):
    pump.s.send(OP_SET_SELECTION, struct.pack("<Q", pump.s.guid))
    pump.run(0.3)
    lines = " | ".join(pump.system(".gps", 1.5))
    m = re.search(r"Map: (\d+).*?X: ([-\d.]+) Y: ([-\d.]+) Z: ([-\d.]+)", lines)
    return (int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))) if m else None


def say_to(pump, ctype, text, target=None):
    if ctype == CHAT_WHISPER:
        pump.s.send(OP_MESSAGECHAT, struct.pack("<II", CHAT_WHISPER, 0) + target.encode() + b"\0" + text.encode() + b"\0")
    else:
        pump.s.send(OP_MESSAGECHAT, struct.pack("<II", ctype, 0) + text.encode() + b"\0")


def all_bridge(since, until=None):
    out = []
    try:
        with open(BRIDGE_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("t", 0) >= since and (until is None or e["t"] <= until):
                    out.append(e)
    except OSError:
        pass
    return out


# ---------------------------------------------------------------- classification des lignes (B)
def sql_literals(blob):
    """Decoupe les tuples d'un INSERT mysqldump -> listes de valeurs (chaines ou nombres en texte)."""
    rows, row, i, n = [], None, 0, len(blob)
    while i < n:
        ch = blob[i]
        if ch == "(" and row is None:
            row, cur = [], None
            i += 1
            continue
        if row is None:
            i += 1
            continue
        if ch == "'":
            j, buf = i + 1, []
            while j < n:
                if blob[j] == "\\":
                    nxt = blob[j + 1]
                    buf.append({"n": "\n", "r": "\r", "t": "\t", "0": "\0"}.get(nxt, nxt))
                    j += 2
                    continue
                if blob[j] == "'":
                    break
                buf.append(blob[j])
                j += 1
            row.append("".join(buf))
            i = j + 1
            continue
        if ch == ")":
            rows.append(row)
            row = None
            i += 1
            continue
        if ch == ",":
            i += 1
            continue
        j = i
        while j < n and blob[j] not in ",)":
            j += 1
        row.append(blob[i:j].strip())
        i = j
    return rows


def template_regex(t):
    parts = re.split(r"(%[a-zA-Z_]+)", t.strip())
    rx = "".join(".+?" if p.startswith("%") else re.escape(p) for p in parts if p)
    return re.compile("^" + rx + "$", re.I | re.S)


def load_templates():
    fr = []
    out = __import__("subprocess").run(
        [MYSQL, "-uroot", "-h127.0.0.1", "-N", "-B", "--default-character-set=utf8mb4", "classicmangos_bots",
         "-e", "SELECT id, name, REPLACE(text, '\\n', ' ') FROM ai_playerbot_texts"],
        capture_output=True, text=True, encoding="utf-8")
    for line in out.stdout.splitlines():
        p = line.split("\t")
        if len(p) == 3 and p[2].strip():
            fr.append((int(p[0]), p[1], p[2], template_regex(p[2])))
    en = []
    try:
        with open(BACKUP_TEXTS, encoding="utf-8", errors="replace") as f:
            blob = f.read()
        k = blob.find("VALUES")
        for r in sql_literals(blob[k + 6:]):
            if len(r) >= 3 and r[2].strip():
                en.append((int(r[0]), r[1], r[2], template_regex(r[2])))
    except OSError:
        pass
    return fr, en


EN_WORDS = set("the you your i'm im my is are with for to have here what this that it's lets let's going "
               "want need anyone looking selling buying sell buy anybody group please thanks thank hello hi "
               "and of on in at be can will got good bad nice who where why how dont don't yes no "
               "following attacking stay staying ok okay welcome bye goodbye see".split())
FR_WORDS = set("le la les je tu de des du un une est pas et avec pour ici quoi ce cette qui on il elle vous "
               "nous mon ma mes ton ta tes salut bonjour merci oui non bien vend vends achete cherche groupe "
               "moi toi suis es sont au aux en sur dans mais".split())


def lang_of(text):
    words = re.findall(r"[a-zA-Z\u00C0-\u00FF']+", text.lower())
    en = sum(w in EN_WORDS for w in words)
    fr = sum(w in FR_WORDS for w in words) + (2 if re.search(r"[\u00E0-\u00FF]", text) else 0)
    if en > fr:
        return "EN"
    if fr > en:
        return "FR"
    return "?"


def strip_links(text):
    return re.sub(r"\|c[0-9a-fA-F]{8}|\|H[^|]*\|h|\|h|\|r", "", text)


def classify(line, bridge, fr, en):
    ch_t, bot, text = line
    for e in bridge:
        if e.get("bot") == bot and e.get("reply") and e["reply"].strip() == text.strip():
            return "LLM", "bridge_log %s" % e.get("ch")
    plain = strip_links(text)
    # gabarits tries : texte exact d'abord, puis par longueur de texte fixe decroissante (« %zone_name » en dernier)
    def lit(t):
        return len(re.sub(r"%[a-zA-Z_]+", "", t).strip())
    fr = sorted(fr, key=lambda r: -lit(r[2]))
    en = sorted(en, key=lambda r: -lit(r[2]))
    for i, nm, t, rx in fr:
        if rx.match(plain):
            # meme texte en anglais dans la sauvegarde -> traduction absente pour ce gabarit
            same_en = any(j == i and rx2.match(plain) for j, _, _, rx2 in en)
            if same_en and lang_of(plain) == "EN":
                return "EN", "table id=%d (%s), texte FR identique a l'anglais" % (i, nm)
            return "FR" if lang_of(plain) != "EN" else "EN", "table id=%d (%s)" % (i, nm)
    for i, nm, t, rx in en:
        if rx.match(plain):
            return "EN", "texte anglais d'origine id=%d (%s) mais absent de la colonne text actuelle" % (i, nm)
    lg = lang_of(plain)
    return lg, "hors table (C++ code en dur probable)" if lg != "FR" else "hors table"


# ---------------------------------------------------------------- A. combat
def find_mobs(me, lvl, radius=70):
    q = ("SELECT c.guid, c.id, ct.Name, ct.MinLevel, ct.MaxLevel, ROUND(SQRT(POW(c.position_x-%f,2)+POW(c.position_y-%f,2))) d "
         "FROM creature c JOIN creature_template ct ON ct.Entry = c.id WHERE c.map=%d AND ct.NpcFlags=0 "
         "AND ct.`Rank`=0 AND ct.Faction IN (%s) AND ct.MaxLevel BETWEEN %d AND %d "
         "AND ABS(c.position_x-%f)<%d AND ABS(c.position_y-%f)<%d ORDER BY d LIMIT 12"
         % (me[1], me[2], me[0], ",".join(map(str, HOSTILE_FACTIONS)), max(1, lvl - 4), lvl + 1,
            me[1], radius, me[2], radius))
    out = __import__("subprocess").run([MYSQL, "-uroot", "-h127.0.0.1", "-N", "-B", "classicmangos_bots", "-e", q],
                                       capture_output=True, text=True, encoding="utf-8")
    return [l.split("\t") for l in out.stdout.splitlines() if l]


def part_a(pump, bot, guid, args):
    res = {}
    me = my_gps(pump)
    log("A : ma position %s" % (me,))
    lvl = int(sql("SELECT level FROM characters WHERE guid=%d" % guid)[0][0])
    mobs = find_mobs(me, lvl) if me else []
    if not mobs:                    # pas de creature autour (ville) : on va pres d'une creature du bon niveau
        far = find_mobs((0, -10600.0, 1300.0, 0), lvl, radius=900)       # Marche de l'Ouest
        if not far:
            log("ECHEC A : aucune creature de niveau %d trouvee" % lvl)
            return {"A_combat": False}
        log("A : aucune creature proche ; .go creature %s (%s) puis .summon %s" % (far[0][0], far[0][2], bot))
        pump.s.teleport_cmd(".go creature %s" % far[0][0])
        pump.run(3)
        log("A : .summon -> %s" % pump.system(".summon " + bot, 2))
        pump.run(5)
        me = my_gps(pump)
        log("A : ma position %s" % (me,))
        mobs = find_mobs(me, lvl) if me else []
    log("A : creatures candidates : %s" % [(m[2], m[3] + "-" + m[4], m[5] + " m") for m in mobs])
    started = None
    for m in mobs:
        dbg, entry = int(m[0]), int(m[1])
        cg = (UNIT_HIGH << 48) | (entry << 24) | dbg
        pump.s.send(OP_SET_SELECTION, struct.pack("<Q", cg))
        info = " | ".join(pump.system(".npc info", 1.5))
        hm = re.search(r"[Cc]urrent\)?:?\s*(\d+)", info) or re.search(r"[Hh]ealth[^0-9]*(\d+)", info)
        if not info or "No creature" in info or "No selection" in info:
            log("A : %s (guid %d) non visible/selectionnable : %s" % (m[2], dbg, info[:100]))
            continue
        log("A : cible %s (guid %d, entry %d) : %s" % (m[2], dbg, entry, info[:160]))
        t_cmd = time.time()
        say_to(pump, CHAT_WHISPER, "attack", bot)
        log("A : chuchote 'attack' a %s (cible selectionnee)" % bot)
        if pump.run(20, until=lambda op, d: bool(pump.bot_combat(guid, t_cmd))):
            started = pump.bot_combat(guid, t_cmd)[0][0]
            break
        log("A : pas de combat du bot sur %s en 20 s, creature suivante" % m[2])
    if not started:
        log("ECHEC A : impossible de mettre le bot en combat")
        return {"A_combat": False}
    log("A : combat du bot detecte : %s" % fmt_combat(pump, pump.bot_combat(guid, started)[0], started))
    pump.run(1.0)

    # messages pendant le combat
    t_party = time.time()
    log("A : (groupe, EN COMBAT) %s" % args.party_msg)
    say_to(pump, CHAT_PARTY, args.party_msg)
    pump.run(2.0)
    t_wh = time.time()
    log("A : (chuchote a %s, EN COMBAT) %s" % (bot, args.whisper_msg))
    say_to(pump, CHAT_WHISPER, args.whisper_msg, bot)
    pump.run(args.combat_wait)
    t_end = time.time()
    for label, t in (("/groupe", t_party), ("chuchotement", t_wh)):
        before = pump.bot_combat(guid, t - 5, t)
        after = pump.bot_combat(guid, t, t + 5)
        log("A : autour du %s : %d paquets de combat du bot dans les 5 s avant, %d dans les 5 s apres"
            % (label, len(before), len(after)))
        for c in (before[-2:] + after[:2]):
            log("      %s" % fmt_combat(pump, c, t))
    in_combat_proof = all(pump.bot_combat(guid, t - 5, t) and pump.bot_combat(guid, t, t + 5) for t in (t_party, t_wh))
    replies = [c for c in pump.chat if c[0] >= t_party and c[2] == guid and c[1] in (CHAT_PARTY, CHAT_WHISPER, CHAT_SAY)]
    bl = [e for e in bridge_lines(t_party - 1, bot)]
    log("A : reponses du bot (groupe/chuchote/dire) pendant/apres le combat jusqu'a +%.0fs : %s"
        % (t_end - t_party, [(round(c[0] - t_party, 1), CHAT_NAMES[c[1]], c[4]) for c in replies]))
    log("A : bridge_log du bot depuis le message en combat : %s" % [json.dumps(e, ensure_ascii=False) for e in bl])
    res["A_combat"] = in_combat_proof
    res["A_silence"] = not replies and not [e for e in bl if e.get("msg") in (args.party_msg, args.whisper_msg)]
    last = pump.bot_combat(guid)
    log("A : dernier paquet de combat du bot : %s" % (fmt_combat(pump, last[-1], t_party) if last else "-"))

    # controle hors combat : attendre 15 s sans paquet de combat du bot
    end = time.time() + 120
    while time.time() < end:
        pump.run(3)
        lc = pump.bot_combat(guid)
        if not lc or time.time() - lc[-1][0] > 15:
            break
    lc = pump.bot_combat(guid)
    calm = time.time() - lc[-1][0] if lc else 999
    log("A : controle : %.0f s sans paquet de combat du bot" % calm)
    pump.run(5)
    t_c1 = time.time()
    log("A : (groupe, HORS COMBAT) %s" % args.party_msg)
    say_to(pump, CHAT_PARTY, args.party_msg)
    pump.run(args.chat_wait, until=lambda op, d: op == OP_SMSG_MESSAGECHAT and d[0] == CHAT_PARTY
             and (parse_chat_full(d) or (0, 0))[1] == guid)
    pump.run(8)                     # recharge 6 s du pont
    t_c2 = time.time()
    log("A : (chuchote a %s, HORS COMBAT) %s" % (bot, args.whisper_msg))
    say_to(pump, CHAT_WHISPER, args.whisper_msg, bot)
    pump.run(args.chat_wait, until=lambda op, d: op == OP_SMSG_MESSAGECHAT and d[0] == CHAT_WHISPER
             and (parse_chat_full(d) or (0, 0))[1] == guid)
    pump.run(2)
    ctrl = [c for c in pump.chat if c[0] >= t_c1 and c[2] == guid and c[1] in (CHAT_PARTY, CHAT_WHISPER)]
    for c in ctrl:
        log("A : controle : reponse (%s) apres %.1fs : %s" % (CHAT_NAMES[c[1]], c[0] - (t_c1 if c[1] == CHAT_PARTY else t_c2), c[4]))
    for e in bridge_lines(t_c1 - 1, bot):
        log("A : controle bridge_log : %s" % json.dumps(e, ensure_ascii=False))
    combat_during_ctrl = pump.bot_combat(guid, t_c1 - 5)
    log("A : paquets de combat du bot pendant le controle : %d" % len(combat_during_ctrl))
    res["A_controle_groupe"] = any(c[1] == CHAT_PARTY for c in ctrl)
    res["A_controle_chuchote"] = any(c[1] == CHAT_WHISPER for c in ctrl)
    return res


# ---------------------------------------------------------------- B. ecoute
def join(pump, chan):
    n0 = len(pump.events)
    pump.s.send(OP_JOIN_CHANNEL, chan.encode() + b"\0" + b"\0")
    pump.run(1.0)
    notes = [(d[0], d[1:].split(b"\0")[0].decode("utf-8", "replace")) for t, op, d in pump.events[n0:]
             if op == OP_SMSG_CHANNEL_NOTIFY]
    log("B : rejoindre '%s' -> SMSG_CHANNEL_NOTIFY %s" % (chan, notes))


def part_b(pump, args, t_start):
    s = pump.s
    bot_guids = {int(r[0]) for r in sql("SELECT c.guid FROM characters c JOIN classicrealmd_bots.account a "
                                        "ON a.id = c.account WHERE a.username LIKE 'RNDBOT%'")}
    s.teleport_cmd(".tele goldshire")
    pump.run(3)
    for ch in ("General - Elwynn Forest", "LocalDefense - Elwynn Forest", "LookingForGroup", "Trade - City"):
        join(pump, ch)
    t_l = time.time()
    log("B : ecoute a Comte-de-l'Or %.0f s" % (args.listen * 0.6))
    pump.run(args.listen * 0.6)
    s.teleport_cmd(".tele stormwind")
    pump.run(3)
    for ch in ("General - Stormwind City", "Trade - City", "LookingForGroup"):
        join(pump, ch)
    log("B : ecoute a Hurlevent %.0f s" % (args.listen * 0.4))
    pump.run(args.listen * 0.4)
    for b in [x for x in args.appear.split(",") if x]:        # /dire autour d'autres bots
        s.teleport_cmd(".appear " + b)
        log("B : ecoute pres de %s %.0f s" % (b, args.appear_wait))
        pump.run(args.appear_wait)
    fr, en = load_templates()
    log("B : %d gabarits FR (colonne text), %d gabarits EN (sauvegarde)" % (len(fr), len(en)))
    bridge = all_bridge(t_start - 2)
    lines = [c for c in pump.chat if c[0] >= t_start and c[2] in bot_guids and c[1] != 10]
    counts = {}
    log("B : %d lignes de bots depuis le debut (invitation incluse) :" % len(lines))
    for c in lines:
        kind, src = classify((c[1], c[3], c[4]), bridge, fr, en)
        counts[kind] = counts.get(kind, 0) + 1
        log("  [%s] (%s%s) %s : %s   <- %s" % (kind, CHAT_NAMES.get(c[1], c[1]), " " + c[5] if c[5] else "", c[3], c[4], src))
    others = [c for c in pump.chat if c[0] >= t_l and c[2] not in bot_guids and c[1] != 10]
    log("B : %d lignes d'autres joueurs (non bots) ignorees" % len(others))
    log("B : bilan %s" % counts)
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", default="Charo")
    ap.add_argument("--player", default="Sondefer")
    ap.add_argument("--listen", type=float, default=180)
    ap.add_argument("--chat-wait", type=float, default=40)
    ap.add_argument("--combat-wait", type=float, default=25)
    ap.add_argument("--party-msg", default="ca va toi ? tu fais quoi ce soir")
    ap.add_argument("--whisper-msg", default="t'as deja fait les mortemines ?")
    ap.add_argument("--commands", default="", help="ordres chuchotes au bot groupe, separes par des virgules")
    ap.add_argument("--appear", default="", help="bots a rejoindre (.appear) pour ecouter le /dire, separes par des virgules")
    ap.add_argument("--appear-wait", type=float, default=30)
    ap.add_argument("--skip-a", action="store_true")
    ap.add_argument("--skip-b", action="store_true")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if not wait_server(30):
        log("serveur de test pas pret")
        return 2
    t_start = time.time()
    s = player_session(a.player)
    pump = Pump(s)
    pump.run(2)
    b = sql("SELECT guid, level, race FROM characters WHERE name='%s' AND online=1" % a.bot)
    if not b:
        log("bot %s hors ligne" % a.bot)
        s.close()
        return 1
    guid, blvl = int(b[0][0]), int(b[0][1])
    mylvl = int(sql("SELECT level FROM characters WHERE guid=%d" % (s.guid & 0xFFFFFFFF))[0][0])
    log("joueur %s niveau %d ; bot %s guid=%d niveau %d" % (s.name, mylvl, a.bot, guid, blvl))
    if mylvl < blvl:
        log(".levelup %d -> %s" % (blvl - mylvl, pump.system(".levelup %d" % (blvl - mylvl), 1.5)))
    pump.system(".gm off", 0.6)
    pump.system(".gm visible on", 0.6)
    s.teleport_cmd(".appear " + a.bot)
    pump.run(3)

    # invitation (B : phrase d'accueil du bot)
    n0 = len(pump.events)
    t_inv = time.time()
    s.send(OP_GROUP_INVITE, a.bot.encode() + b"\0")
    pump.run(20, until=lambda op, d: op in (OP_SMSG_GROUP_LIST, 0x06F))
    if any(op == 0x06F for t, op, d in pump.events[n0:]):     # le bot nous a invite d'abord : accepter
        log("SMSG_GROUP_INVITE recu du bot : CMSG_GROUP_ACCEPT")
        s.send(0x072)
        pump.run(10, until=lambda op, d: op == OP_SMSG_GROUP_LIST)
    pump.run(6)
    for t, op, d in pump.events[n0:]:
        if op == 0x07F:
            j = d.index(b"\0", 4)
            log("SMSG_PARTY_COMMAND_RESULT op=%d nom=%s resultat=%d" % (
                struct.unpack("<I", d[:4])[0], d[4:j].decode("utf-8", "replace"), struct.unpack("<I", d[j + 1:j + 5])[0]))
        elif op == 0x074:
            log("SMSG_GROUP_DECLINE %s" % d.split(b"\0")[0].decode("utf-8", "replace"))
    lists = [d for t, op, d in pump.events[n0:] if op == OP_SMSG_GROUP_LIST]
    grouped = bool(lists and any(m[1] == guid for m in parse_group_list(lists[-1])[0]))
    log("groupe : %s (SMSG_GROUP_LIST %s)" % ("OK" if grouped else "ECHEC", parse_group_list(lists[-1]) if lists else "-"))
    hello = [c for c in pump.chat if c[0] >= t_inv and c[2] == guid]
    log("phrases du bot a l'invitation : %s" % [(CHAT_NAMES.get(c[1]), c[4]) for c in hello])
    res = {"groupe": grouped}
    if grouped and not a.skip_a:
        res.update(part_a(pump, a.bot, guid, a))
    if grouped and a.commands:      # B : reponses toutes faites aux ordres chuchotes (souvent codees en dur)
        for cmd in a.commands.split(","):
            log("B : (chuchote a %s) %s" % (a.bot, cmd))
            say_to(pump, CHAT_WHISPER, cmd, a.bot)
            pump.run(4)
    s.send(OP_GROUP_DISBAND)
    pump.run(2)
    if not a.skip_b:
        part_b(pump, a, t_start)
    s.send(OP_LOGOUT_REQUEST)
    pump.run(25, until=lambda op, d: op == OP_SMSG_LOGOUT_COMPLETE)
    s.close()
    crash = crash_check()
    if crash:
        log("PLANTAGE : mangosd_bots.exe absent, rapport %s" % crash)
    log("resume : %s" % " ".join("%s=%s" % (k, "OK" if v else "ECHEC") for k, v in res.items()))
    return 0 if all(res.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
