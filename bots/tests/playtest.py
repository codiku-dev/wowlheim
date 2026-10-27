#!/usr/bin/env python3
"""Session de jeu « comme Robin » : aller voir un bot, lui parler en /dire puis en chuchotement, mesurer.

Compte WLTEST (identifiants dans C:\\Wowlheim\\run\\test_account.txt, jamais affiches).
Pour chaque message : delai message -> premiere reponse du bot, texte recu, lien de quete present.
A la fin : taux de reponse, delais (mediane/max), et note Jev du dialogue (« ecrit par un humain ? »).

  python -I bots/tests/playtest.py [--bot Nom] [--near Gogo]
"""
import argparse
import json
import os
import socket
import statistics
import struct
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chat_probe as cp  # noqa: E402

SAY = ["salut", "tu fais quoi ?", "c'est quelle quete ?", "tu peux me la link ?", "t'en es ou ?", "ok merci, bon jeu"]
WHISPER = ["re, t'es level combien ?", "tu joues souvent le soir ?", "bon a+"]


def pick_bot(near):
    me = cp.sql("SELECT map, position_x, position_y FROM characters WHERE name='%s'" % near)
    rows = cp.sql("SELECT c.name, c.map, c.position_x, c.position_y, c.level FROM characters c JOIN classicrealmd" + cp.DB_SUFFIX + ".account a "
                  "ON a.id=c.account WHERE a.username LIKE 'RNDBOT%' AND c.online=1 AND c.race IN (1,3,4,7)")
    if me:
        m, x, y = me[0]
        rows.sort(key=lambda r: (r[1] != m, (float(r[2]) - float(x)) ** 2 + (float(r[3]) - float(y)) ** 2))
    return rows[0][0] if rows else None


def exchange(s, kind, target, text, wait=20.0):   # un joueur en plein combat repond apres le mob
    if kind == "say":
        s.send(cp.OP_MESSAGECHAT, struct.pack("<II", 0, 0) + text.encode() + b"\0")
    else:
        s.send(cp.OP_MESSAGECHAT, struct.pack("<II", cp.CHAT_WHISPER, 0) + target.encode() + b"\0" + text.encode() + b"\0")
    t0 = time.time()
    s.s.settimeout(0.3)
    while time.time() - t0 < wait:
        try:
            op, d = s.read()
        except socket.timeout:
            continue
        if op != cp.OP_SMSG_MESSAGECHAT:
            continue
        c = cp.parse_chat(d)
        if not c or c[1] == (s.guid & 0xFFFFFFFF) or c[0] not in (0, 6):
            continue
        who = cp.sql("SELECT name FROM characters WHERE guid=%d" % c[1])
        if who and who[0][0] == target:
            return time.time() - t0, c[2]
    return None, None


def jev(lines):
    try:
        key = open(r"C:\Wowlheim\bots\state\typesafe_api_key.txt", encoding="utf-8").read().strip()
        body = {"model": "jev-latest", "state": "\n".join(lines), "questions": {
            "humain": {"type": "noul", "instructions": "Les repliques de BOT pourraient-elles venir d'un vrai joueur humain francais "
                       "dans le chat de WoW, sans qu'on soupconne une IA ?"},
            "reactif": {"type": "score", "instructions": "BOT reagit-il vraiment a ce que dit JOUEUR (pertinence, pas a cote) ?",
                        "criteria": ["0 nul", "1 faible", "2 moyen", "3 bon", "4 excellent"]}}}
        req = urllib.request.Request("https://api.typesafe.ai/v1/systemone", data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        socket.create_connection = cp._orig_connect      # la sonde n'autorise que 127.0.0.1 ; Jev est en ligne
        try:
            a = json.loads(urllib.request.urlopen(req, timeout=30).read())["answers"]
        finally:
            socket.create_connection = cp._redirect
        return {"humain": a["humain"]["noul"], "reactif": a["reactif"]["score"]}
    except Exception as e:
        return {"erreur": type(e).__name__}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot")
    ap.add_argument("--near", default="Gogo")
    a = ap.parse_args()
    bot = a.bot or pick_bot(a.near)
    s = cp.player_session("Sondeur")
    time.sleep(2)
    s.say(".revive", collect=1.0)          # un fantome n'est pas entendu en /dire par les vivants
    s.say(".modify hp 5000", collect=0.5)
    s.teleport_cmd(".appear " + bot)
    time.sleep(3)
    g = cp.sql("SELECT guid FROM characters WHERE name='%s'" % bot)
    if g:
        s.send(0x13D, struct.pack("<Q", int(g[0][0])))   # CMSG_SET_SELECTION : on cible celui a qui on parle
    print("joueur %s, bot %s" % (s.name, bot))
    delays, lines, links, answered, sent = [], [], 0, 0, 0
    for kind, msgs in (("say", SAY), ("whisper", WHISPER)):
        for m in msgs:
            sent += 1
            dt, txt = exchange(s, kind, bot, m)
            lines.append("JOUEUR : " + m)
            if txt is None:
                print("  [%s] %s  ->  (pas de reponse en 20 s)" % (kind, m))
                lines.append("BOT : (silence)")
            else:
                answered += 1
                delays.append(dt)
                links += "|Hquest:" in txt
                shown = txt.replace("|cffffff00", "").replace("|h|r", "").split("|h")[-1] if "|Hquest:" in txt else txt
                print("  [%s] %s  ->  %.1f s : %s%s" % (kind, m, dt, txt if "|H" not in txt else shown,
                                                       "   (LIEN DE QUETE)" if "|Hquest:" in txt else ""))
                lines.append("BOT : " + shown)
            time.sleep(3)
    s.close()
    print("\nreponses : %d/%d ; delai median %.1f s, max %.1f s ; liens de quete : %d" % (
        answered, sent, statistics.median(delays) if delays else -1, max(delays) if delays else -1, links))
    print("Jev :", jev(lines))


if __name__ == "__main__":
    main()
