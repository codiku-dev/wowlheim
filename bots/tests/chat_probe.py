#!/usr/bin/env python3
"""Sonde de bout en bout sur le serveur de TEST des bots (realmd 3725, monde 8086).

Connecte un joueur de test (compte WLTEST, mot de passe lu dans C:\\Wowlheim\\run\\test_account.txt,
jamais affiche), liste les bots en ligne (base classiccharacters_bots), puis chuchote a un bot
et attend sa reponse. Reutilise tools/wlclient.py en redirigeant ses ports codes en dur.

  python -I bots/tests/chat_probe.py --online            # bots en ligne (jalon 1)
  python -I bots/tests/chat_probe.py --whisper "salut, tu fais quoi ?" [--bot Nom] [--wait 40]
  python -I bots/tests/chat_probe.py --say "salut tout le monde" --bot Nom   # /dire a cote du bot
"""
import argparse
import os
import socket
import struct
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "tools"))

_orig_connect = socket.create_connection
# WL_TARGET=main : serveur principal (ports 3724/8085, sans redirection)
PORTS = {} if os.environ.get("WL_TARGET") == "main" else {3724: 3725, 8085: 8086}


def _redirect(addr, *a, **kw):
    host, port = addr
    if host not in ("127.0.0.1", "localhost"):
        raise OSError("sonde locale uniquement")
    return _orig_connect((host, PORTS.get(port, port)), *a, **kw)


socket.create_connection = _redirect
import wlclient  # noqa: E402

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
# Suffixe des bases lues : _bots (serveur de test, defaut) ; WL_DB_SUFFIX=_m pour l'essai de fusion
DB_SUFFIX = os.environ.get("WL_DB_SUFFIX", "" if os.environ.get("WL_TARGET") == "main" else "_bots")
CHAT_WHISPER = 6
OP_MESSAGECHAT, OP_SMSG_MESSAGECHAT = 0x95, 0x96


def sql(query):
    out = subprocess.run([MYSQL, "-uroot", "-h127.0.0.1", "-N", "-B", "classiccharacters" + DB_SUFFIX, "-e", query],
                         capture_output=True, text=True, encoding="utf-8")
    return [line.split("\t") for line in out.stdout.splitlines() if line]


def online_bots():
    return sql("SELECT c.name, c.race, c.class, c.level, c.zone FROM characters c "
               "JOIN classicrealmd" + DB_SUFFIX + ".account a ON a.id = c.account "
               "WHERE c.online = 1 AND a.username LIKE 'RNDBOT%' ORDER BY c.name")


def credentials():
    kv = {}
    with open(r"C:\Wowlheim\run\test_account.txt", encoding="utf-8") as f:
        for line in f:
            if ": " in line:
                k, v = line.split(": ", 1)
                kv[k.strip()] = v.strip()
    return kv["account"], kv["password"]


def player_session(name):
    user, pw = credentials()
    s = wlclient.Session(user, pw)
    chars = s.chars()
    guid = next((g for g, n in chars if n.lower() == name.lower()), None)
    if guid is None:
        code = s.create(name, race=1, cls=8)       # humain mage
        if code == 0x2E:
            chars = s.chars()
            guid = next(g for g, n in chars if n.lower() == name.lower())
        elif chars:                                 # compte plein (0x34) : on prend un personnage existant
            guid, name = chars[0]
        else:
            raise RuntimeError("creation du personnage refusee : 0x%02X" % code)
    s.login(guid)
    s.name = name
    return s


CHAT_NAMES = {0: "dire", 1: "groupe", 5: "crier", 6: "chuchote", 7: "chuchote a", 8: "emote", 10: "systeme",
              14: "canal"}
CHAT_CHANNEL = 14
OP_JOIN_CHANNEL = 0x097


def parse_chat(d):
    """(type, guid_bas, texte) d'un SMSG_MESSAGECHAT 1.12, ou None pour les types ignores."""
    t = d[0]
    if t in (0, 1, 5):                     # dire / groupe / crier : guid, guid, longueur, texte
        guid, off = struct.unpack("<Q", d[5:13])[0], 21
    elif t in (6, 7, 8, 10):               # chuchotement, emote, systeme : guid, longueur, texte
        guid, off = struct.unpack("<Q", d[5:13])[0], 13
    elif t == CHAT_CHANNEL:                # canal : nom\0, rang (u32), guid, longueur, texte
        j = d.index(b"\0", 5) + 1 + 4
        guid, off = struct.unpack("<Q", d[j:j + 8])[0], j + 8
    else:
        return None
    ln = struct.unpack("<I", d[off:off + 4])[0]
    return t, guid & 0xFFFFFFFF, d[off + 4:off + 4 + ln - 1].decode("utf-8", "replace")


def listen(s, wait, stop_on_whisper=False):
    end = time.time() + wait
    s.s.settimeout(0.5)
    got = []
    names = {}
    while time.time() < end:
        try:
            op, d = s.read()
        except socket.timeout:
            continue
        if op != OP_SMSG_MESSAGECHAT:
            continue
        c = parse_chat(d)
        if not c or c[0] == 7 or c[1] == (s.guid & 0xFFFFFFFF):
            continue
        if c[1] not in names:
            r = sql("SELECT name FROM characters WHERE guid=%d" % c[1])
            names[c[1]] = r[0][0] if r else str(c[1])
        got.append((c[0], names[c[1]], c[2]))
        print("[%5.1fs] (%s) %s : %s" % (wait - (end - time.time()), CHAT_NAMES[c[0]], names[c[1]], c[2]), flush=True)
        if stop_on_whisper and c[0] == CHAT_WHISPER:
            break
    return got


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--online", action="store_true")
    ap.add_argument("--whisper", help="chuchote ce texte au bot")
    ap.add_argument("--say", help="se teleporte pres du bot (.appear, compte GM) et dit ce texte")
    ap.add_argument("--channel", help="rejoint ce canal (ex. « General - Elwynn Forest ») et y ecrit --text")
    ap.add_argument("--text")
    ap.add_argument("--tele", help="lieu .tele (au lieu de .appear sur le bot), ex. goldshire")
    ap.add_argument("--bot")
    ap.add_argument("--player", default="Sondeur")
    ap.add_argument("--wait", type=float, default=40)
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    bots = online_bots()
    print("bots en ligne : %d" % len(bots))
    for b in bots:
        print("  %s race=%s classe=%s niveau=%s zone=%s" % tuple(b))
    if not (a.whisper or a.say or a.channel):
        return 0 if bots else 1
    target = a.bot or (bots[0][0] if bots else None)
    if not target and not a.tele:
        print("aucun bot a qui parler")
        return 1
    s = player_session(a.player)
    time.sleep(2)
    if a.tele:
        s.teleport_cmd(".tele " + a.tele)
        time.sleep(3)
    if a.channel:
        s.send(OP_JOIN_CHANNEL, a.channel.encode() + b"\0" + b"\0")
        time.sleep(1)
        print("%s (canal %s) : %s" % (s.name, a.channel, a.text))
        s.send(OP_MESSAGECHAT, struct.pack("<II", CHAT_CHANNEL, 0) + a.channel.encode() + b"\0" + a.text.encode() + b"\0")
        got = listen(s, a.wait)
    elif a.say:
        if not a.tele:
            s.teleport_cmd(".appear " + target)
            time.sleep(3)
        print("%s (dire, pres de %s) : %s" % (s.name, a.tele or target, a.say))
        s.send(OP_MESSAGECHAT, struct.pack("<II", 0, 0) + a.say.encode() + b"\0")
        got = listen(s, a.wait)
    else:
        print("%s -> %s : %s" % (s.name, target, a.whisper))
        s.send(OP_MESSAGECHAT, struct.pack("<II", CHAT_WHISPER, 0) + target.encode() + b"\0" + a.whisper.encode() + b"\0")
        got = [g for g in listen(s, a.wait, stop_on_whisper=True) if g[0] == CHAT_WHISPER]
    if not got:
        print("pas de reponse en %.0fs" % a.wait)
    s.close()
    return 0 if got else 1


if __name__ == "__main__":
    sys.exit(main())
