#!/usr/bin/env python3
"""Les bots ignorent-ils le contenu Valheim ? Sonde en jeu sur l'essai de fusion (3725/8086, bases *_m par defaut).

Client de protocole (compte WLTEST, MJ : playerbots obeit aux ordres d'un MJ). On se place au milieu d'arbres (creatures
9300000-9300999) et de ramassables (GameObjects 9130000-9139999) de Valheim, on y fait venir des bots (.summon), puis :
  1. « los » chuchote a chaque bot : la liste des GameObjects qu'il percoit ne contient aucun objet Valheim
     (alors que le MJ en voit autour : .gobject near) ;
  2. arbre cible + « attack » chuchote : refus (« j'ai pas de cible »), aucun coup porte ; temoin : une creature WoW
     ordinaire ciblee + « attack » est bien attaquee ;
  3. observation N s : aucun coup de bot sur un arbre (SMSG_ATTACKERSTATEUPDATE), aucun objet Valheim equipe par un bot,
     ramassables proches toujours la (.gobject near avant/apres).

  set WL_DB_SUFFIX=_m && python -I bots/tests/valheim_isolation_probe.py [--bots 4] [--observe 240]
"""
import argparse
import os
import re
import socket
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("WL_DB_SUFFIX", "_m")
import chat_probe as cp  # noqa: E402
import wlclient  # noqa: E402

SFX = cp.DB_SUFFIX
SPOT = (-9016.0, -161.0, 81.0)        # Comte-de-l'Or, pres de Comte-du-Nord : 21 ramassables et 2 hetres a moins de 60 m
VALHEIM_GO_NAMES = None
ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(("[OK]    " if cond else "[ECHEC] ") + name, detail, flush=True)


def sql(db, q):
    out = subprocess.run([cp.MYSQL, "-uroot", "-h127.0.0.1", "-N", "-B", "--default-character-set=utf8mb4", db + SFX, "-e", q],
                         capture_output=True, text=True, encoding="utf-8")
    return [line.split("\t") for line in out.stdout.splitlines() if line]


def unpack_guid(d, i):
    mask = d[i]; i += 1; g = 0
    for b in range(8):
        if mask & (1 << b):
            g |= d[i] << (8 * b); i += 1
    return g, i


def pump(s, seconds, attacks, whispers, bots_low):
    """Lit les paquets : coups (attaquant, cible, degats) et chuchotements recus des bots."""
    end = time.time() + seconds
    s.s.settimeout(0.3)
    while time.time() < end:
        try:
            op, d = s.read()
        except socket.timeout:
            continue
        if op == 0x14A and len(d) > 8:            # SMSG_ATTACKERSTATEUPDATE
            att, i = unpack_guid(d, 4)
            tg, i = unpack_guid(d, i)
            attacks.append((att, tg, struct.unpack("<I", d[i:i + 4])[0]))
        elif op == cp.OP_SMSG_MESSAGECHAT:
            c = cp.parse_chat(d)
            if c and c[0] == cp.CHAT_WHISPER and c[1] in bots_low:
                whispers.append((bots_low[c[1]], c[2]))


def whisper(s, bot, text):
    s.send(cp.OP_MESSAGECHAT, struct.pack("<II", cp.CHAT_WHISPER, 0) + bot.encode() + b"\0" + text.encode() + b"\0")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--bots", type=int, default=4)
    ap.add_argument("--observe", type=int, default=240)
    ap.add_argument("--char", default="Wlcost")
    a = ap.parse_args()
    names = {r[0] for r in sql("classicmangos", "SELECT name FROM gameobject_template WHERE entry >= 9000000")}
    trees = sql("classicmangos", "SELECT guid, id FROM creature WHERE map=0 AND id BETWEEN 9300000 AND 9300999 AND "
                "POW(position_x-(%f),2)+POW(position_y-(%f),2) < 3600" % SPOT[:2])
    tree_guids = {(0xF130 << 48) | (int(e) << 24) | int(g) for g, e in trees}
    bots = sql("classiccharacters", "SELECT c.guid, c.name FROM characters c JOIN classicrealmd%s.account a ON a.id=c.account "
               "WHERE a.username LIKE 'RNDBOT%%' AND c.online=1 AND c.race IN (1,3,4,7) AND c.level <= 12 ORDER BY c.level, c.guid LIMIT %d"
               % (SFX, a.bots))
    bots_low = {int(g): n for g, n in bots}
    print("bots :", ", ".join(bots_low.values()), "| arbres a < 60 m :", len(trees))

    user, pw = cp.credentials()
    s = wlclient.Session(user, pw)
    wlclient.login_char(s, a.char)
    time.sleep(2)

    def say(c, t=0.8):
        return [l for l in s.say(c, t) if "Welcome to" not in l and "Tickets" not in l]

    say(".revive")
    say(".gm off")
    s.send(0x13D, struct.pack("<Q", s.guid))
    say(".modify hp 50000", 0.4)
    s.teleport_cmd(".go xyz %.1f %.1f %.1f 0" % (SPOT[0], SPOT[1], SPOT[2] + 1))
    time.sleep(2)
    near_before = [l for l in say(".gobject near 40", 2.0) if any(n in l for n in names)]
    check("le MJ voit des GameObjects Valheim autour (.gobject near 40)", len(near_before) > 0, "%d lignes, ex. %s" % (
        len(near_before), near_before[0][:90] if near_before else ""))
    for n in bots_low.values():
        say(".summon " + n, 1.0)
    time.sleep(4)
    attacks, wh = [], []

    # 1. perception des GameObjects
    for n in bots_low.values():
        whisper(s, n, "los")
    pump(s, 6, attacks, wh, bots_low)
    los = [(b, t) for b, t in wh]
    shown_valheim = [(b, t) for b, t in los if any(n in t for n in names)]
    gobj_lines = [t for b, t in los if "Game objects" in t or "objets" in t.lower() or "|Hfound" in t]
    print("    reponses « los » :", len(los), "lignes ; ex.", [t[:80] for b, t in los[:4]])
    check("« los » : aucun GameObject Valheim dans ce que percoivent les bots", len(los) > 0 and not shown_valheim,
          str(shown_valheim[:3]))

    # 2. ordre d'attaquer un arbre, puis temoin sur une creature ordinaire
    del wh[:]
    tree_g = None
    for g in tree_guids:
        tree_g = g
        break
    if tree_g:
        s.send(0x13D, struct.pack("<Q", tree_g))
        time.sleep(0.5)
        for n in bots_low.values():
            whisper(s, n, "attack")
        pump(s, 12, attacks, wh, bots_low)
        on_tree = [x for x in attacks if x[1] in tree_guids and (x[0] & 0xFFFFFFFF) in bots_low]
        check("« attack » sur un arbre Valheim : refus des bots, aucun coup", not on_tree and any("cible" in t for b, t in wh),
              "%s | %s" % (wh[:4], on_tree[:3]))
    mob = sql("classicmangos", "SELECT c.guid, c.id FROM creature c JOIN creature_template t ON t.entry=c.id WHERE c.map=0 AND "
              "c.id < 9000000 AND t.NpcFlags=0 AND t.Rank=0 AND t.MinLevel <= 5 AND t.Faction IN (7, 14, 22, 32) AND "
              "POW(c.position_x-(%f),2)+POW(c.position_y-(%f),2) < 6400 ORDER BY POW(c.position_x-(%f),2)+POW(c.position_y-(%f),2) LIMIT 1"
              % (SPOT[0], SPOT[1], SPOT[0], SPOT[1]))
    if mob:
        mg = (0xF130 << 48) | (int(mob[0][1]) << 24) | int(mob[0][0])
        say(".go creature %s" % mob[0][0], 1.0)
        time.sleep(1.5)
        for n in bots_low.values():
            say(".summon " + n, 0.6)
        time.sleep(3)
        s.send(0x13D, struct.pack("<Q", mg))
        time.sleep(0.5)
        del wh[:]
        n0 = len(attacks)
        for n in bots_low.values():
            whisper(s, n, "attack")
        pump(s, 15, attacks, wh, bots_low)
        on_mob = [x for x in attacks[n0:] if x[1] == mg and (x[0] & 0xFFFFFFFF) in bots_low]
        check("temoin : « attack » sur une creature WoW ordinaire (%s) -> les bots frappent" % mob[0][1], len(on_mob) > 0,
              "%d coups | %s" % (len(on_mob), wh[:2]))
        s.send(0x13D, struct.pack("<Q", 0))
        s.teleport_cmd(".go xyz %.1f %.1f %.1f 0" % (SPOT[0], SPOT[1], SPOT[2] + 1))
        time.sleep(2)
        for n in bots_low.values():   # les bots reprennent ensuite leur vie (IA libre) au milieu des arbres et ramassables
            say(".summon " + n, 0.6)

    # 3. observation libre au milieu du contenu Valheim
    n0 = len(attacks)
    print("    observation %d s..." % a.observe, flush=True)
    pump(s, a.observe, attacks, wh, bots_low)
    bot_hits = [x for x in attacks[n0:] if (x[0] & 0xFFFFFFFF) in bots_low]
    on_tree = [x for x in bot_hits if x[1] in tree_guids or ((x[1] >> 24) & 0xFFFFFF) in range(9300000, 9301000)]
    check("observation : aucun coup de bot sur un arbre / rocher Valheim", not on_tree,
          "%d coups de bots au total, %d sur Valheim" % (len(bot_hits), len(on_tree)))
    near_after = [l for l in say(".gobject near 40", 2.0) if any(n in l for n in names)]
    print("    .gobject near 40 (Valheim) : %d avant, %d apres" % (len(near_before), len(near_after)))
    eq = sql("classiccharacters", "SELECT COUNT(*) FROM character_inventory ci JOIN item_instance ii ON ii.guid=ci.item JOIN characters c "
             "ON c.guid=ci.guid JOIN classicrealmd%s.account a ON a.id=c.account WHERE a.username LIKE 'RNDBOT%%' AND ci.bag=0 AND "
             "ci.slot < 19 AND ii.itemEntry >= 9000000" % SFX)
    check("aucun objet Valheim (>= 9 000 000) equipe par un bot (base)", eq and eq[0][0] == "0", str(eq))
    s.close()
    print("RESULTAT :", "OK" if ok else "ECHEC")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
