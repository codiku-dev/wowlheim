#!/usr/bin/env python3
"""Sonde « le bot s'arrete pour parler » sur le serveur de TEST des bots (realmd 3725, monde 8086).

Compte WLTEST3 (identifiants lus dans C:\\Wowlheim\\bots\\state\\test_account_wltest3.txt, jamais affiches),
personnage Sondefer (jamais le compte ADMIN de Robin).
  1. choisit un bot Alliance hors combat qui se deplace (.appear pres de lui, deux .gps a 4 s d'intervalle),
     loin de Comté-du-Nord / Elwynn (zone 12) pour ne pas deranger Robin ;
  2. .appear a cote, dit « salut » en /dire puis deux autres messages espaces de 8 s ;
  3. releve la position et l'orientation du bot (.gps sur le bot selectionne) toutes les ~2 s pendant l'echange
     puis pendant --after secondes (reprise attendue ~25 s apres le dernier echange) ;
  4. mesure le delai message -> reponse affichee (reception du SMSG_MESSAGECHAT du bot) pour chaque replique.

  python -I bots/tests/converse_probe.py [--bot Nom] [--after 50] [--json sortie.json]
"""
import argparse
import json
import math
import os
import re
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chat_probe  # noqa: E402  (redirige 3724/8085 -> 3725/8086 et importe wlclient)
import group_probe  # noqa: E402
from chat_probe import sql, OP_MESSAGECHAT  # noqa: E402

group_probe.ACCOUNT_FILE = r"C:\Wowlheim\bots\state\test_account_wltest3.txt"
log = group_probe.log
OP_SET_SELECTION = 0x13D
CHAT_SAY = 0
MESSAGES = ["salut", "tu fais quoi dans le coin ?", "ah ok, et t'es de quel niveau ?"]


def gps(pump, guid_low):
    """(map, x, y, z, o) du bot selectionne, ou None."""
    pump.s.send(OP_SET_SELECTION, struct.pack("<Q", guid_low))
    pump.run(0.2)
    lines = " | ".join(group_probe.system_lines(pump, ".gps", 1.0))
    m = re.search(r"Map: (\d+).*?X: ([-\d.]+) Y: ([-\d.]+) Z: ([-\d.]+)(?: Orientation: ([-\d.]+))?", lines)
    if not m:
        return None
    return (int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)),
            float(m.group(5)) if m.group(5) else None)


def d2(a, b):
    return math.hypot(a[1] - b[1], a[2] - b[2])


def facing_error(bot, me):
    """Ecart (degres) entre l'orientation du bot et la direction du joueur."""
    if bot[4] is None:
        return None
    want = math.atan2(me[2] - bot[2], me[1] - bot[1])
    diff = (bot[4] - want + math.pi) % (2 * math.pi) - math.pi
    return abs(math.degrees(diff))


def candidates(exclude_zone=12):
    rows = sql("SELECT c.guid, c.name, c.zone, c.level FROM characters c "
               "JOIN classicrealmd_bots.account a ON a.id = c.account "
               "LEFT JOIN group_member gm ON gm.memberGuid = c.guid "
               "WHERE c.online = 1 AND a.username LIKE 'RNDBOT%%' AND c.race IN (1,3,4,7) "
               "AND c.zone <> %d AND gm.memberGuid IS NULL ORDER BY RAND()" % exclude_zone)
    return [(int(g), n, z, lv) for g, n, z, lv in rows]


WHISPERS = ["salut", "tu fais quoi ?", "t'es de quel niveau ?", "tu farmes quoi la ?", "c'est dur ici ?",
            "tu joues depuis longtemps ?", "t'as une monture ?", "tu connais un bon coin pour xp ?",
            "t'es dans une guilde ?", "allez bon jeu"]
CHAT_WHISPER = 6


def whisper_mode(a, s, pump):
    """Chuchote N messages a un bot (pas forcement proche), mesure taux de reponse et delais."""
    pool = [c for c in candidates(exclude_zone=-1) if not a.bot or c[1].lower() == a.bot.lower()]
    if not pool:
        log("aucun bot")
        return 1
    guid, name = pool[0][0], pool[0][1]
    log("chuchotements a %s" % name)
    results = []
    for i in range(a.whispers):
        msg = WHISPERS[i % len(WHISPERS)]
        n0 = len(pump.chat)
        t_sent = time.time()
        s.send(OP_MESSAGECHAT, struct.pack("<II", CHAT_WHISPER, 0) + name.encode() + b"\0" + msg.encode() + b"\0")
        got = None
        end = t_sent + a.whisper_wait
        while time.time() < end and got is None:
            pump.run(0.25)
            for c in pump.chat[n0:]:
                if c[1] == CHAT_WHISPER and c[2] == name:
                    got = (c[0] + pump.t0 - t_sent, c[3])
                    break
        results.append({"msg": msg, "delai": round(got[0], 2) if got else None, "reponse": got[1] if got else None})
        log("%-32s -> %s" % (msg, ("%.2fs : %s" % got) if got else "PAS DE REPONSE en %.0fs" % a.whisper_wait))
        pump.run(2.0)
    delays = sorted(r["delai"] for r in results if r["delai"] is not None)
    if delays:
        log("reponses %d/%d ; delai median %.2fs, min %.2fs, max %.2fs" % (len(delays), len(results), delays[len(delays) // 2], delays[0], delays[-1]))
    else:
        log("aucune reponse sur %d" % len(results))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"bot": name, "chuchotements": results}, f, ensure_ascii=False, indent=1)
    s.close()
    return 0 if delays else 1


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot")
    ap.add_argument("--player", default="Sondefer")
    ap.add_argument("--gap", type=float, default=8.0)
    ap.add_argument("--after", type=float, default=50.0)
    ap.add_argument("--json")
    ap.add_argument("--whispers", type=int, default=0, help="mode chuchotements : N messages a un bot (de preference en train de farmer)")
    ap.add_argument("--whisper-wait", type=float, default=30.0)
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if not group_probe.wait_server(60):
        log("serveur de test pas pret")
        return 2
    s = group_probe.player_session(a.player)
    pump = group_probe.Pump(s)
    pump.run(2)
    group_probe.revive(pump, s)

    if a.whispers:
        return whisper_mode(a, s, pump)

    # 1. bot qui se deplace
    pick = None
    pool = [c for c in candidates() if not a.bot or c[1].lower() == a.bot.lower()]
    for guid, name, zone, lvl in pool[:12]:
        s.teleport_cmd(".appear " + name)
        pump.run(1)
        p1 = gps(pump, guid)
        pump.run(4)
        p2 = gps(pump, guid)
        if not p1 or not p2:
            continue
        moved = d2(p1, p2)
        log("candidat %s (zone %s, niv. %s) : %.1f m en 4 s" % (name, zone, lvl, moved))
        if 3 < moved < 30 or a.bot:   # marche ou court (pas en vol de taxi)
            pick = (guid, name)
            break
    if not pick:
        log("aucun bot en mouvement trouve")
        s.close()
        return 1
    guid, name = pick
    s.teleport_cmd(".appear " + name)
    pump.run(0.2)

    # 2-3. echange + releves (le premier message part tout de suite apres .appear : le bot n'a pas le temps de filer)
    samples, raw, sent = [], [], []
    t0 = time.time()

    def pump_until(t_end):
        while time.time() < t_end:
            b = gps(pump, guid)
            if b:
                raw.append((round(time.time() - t0, 1), b))
            pump.run(max(0.0, min(0.3, t_end - time.time())))

    for msg in MESSAGES:
        log("%s (dire) : %s" % (s.name, msg))
        s.send(OP_MESSAGECHAT, struct.pack("<II", 0, 0) + msg.encode() + b"\0")
        sent.append({"t": round(time.time() - t0, 2), "texte": msg})
        pump_until(time.time() + a.gap)
    pump_until(time.time() + a.after)

    me = group_probe.my_gps(pump)
    me = (me[0], me[1], me[2], me[3], None) if me else None
    for t, b in raw:
        samples.append({"t": t, "x": b[1], "y": b[2], "z": b[3], "o": b[4],
                        "dist_joueur": round(d2(b, me), 1) if me else None,
                        "ecart_face": facing_error(b, me) if me else None})

    # 4. bilan
    replies = [{"t": round(c[0] + pump.t0 - t0, 2), "texte": c[3]} for c in pump.chat
               if c[1] == CHAT_SAY and c[2] == name and c[0] + pump.t0 >= t0]
    others = [(round(c[0] + pump.t0 - t0, 1), c[2], c[3]) for c in pump.chat
              if c[1] == CHAT_SAY and c[2] != name and c[0] + pump.t0 >= t0]
    for o in others:
        log("autre locuteur a +%.1fs : %s : %s" % o)
    for r in replies:
        prev = [m for m in sent if m["t"] <= r["t"]]
        r["delai"] = round(r["t"] - prev[-1]["t"], 2) if prev else None
        log("reponse de %s a +%.1fs (delai %.1fs) : %s" % (name, r["t"], r["delai"] or -1, r["texte"]))
    t_talk0 = sent[0]["t"]
    t_last = max([sent[-1]["t"]] + [r["t"] for r in replies])

    def moved(t1, t2):
        pts = [p for p in samples if t1 <= p["t"] <= t2]
        if len(pts) < 2:
            return None
        return round(sum(math.hypot(q["x"] - p["x"], q["y"] - p["y"]) for p, q in zip(pts, pts[1:])), 1)

    phases = {
        "avant (0 -> 1er message)": moved(0, t_talk0),
        "conversation (1er message +1 s -> derniere replique)": moved(t_talk0 + 1.0, t_last),
        "fin attendue (derniere replique -> +25 s)": moved(t_last, t_last + 25),
        "apres (+25 s -> fin)": moved(t_last + 25, 1e9),
    }
    for k, v in phases.items():
        log("deplacement %s : %s m" % (k, v))
    faces = [p["ecart_face"] for p in samples if t_talk0 + 2 <= p["t"] <= t_last and p["ecart_face"] is not None]
    if faces:
        log("ecart d'orientation vers le joueur pendant l'echange : median %.0f deg, max %.0f deg"
            % (sorted(faces)[len(faces) // 2], max(faces)))
    dists = [p["dist_joueur"] for p in samples if t_talk0 <= p["t"] <= t_last]
    if dists:
        log("distance bot-joueur pendant l'echange : %.1f -> %.1f m (max %.1f)" % (dists[0], dists[-1], max(dists)))
    out = {"bot": name, "joueur": me, "autres": others, "envoyes": sent, "reponses": replies, "phases_m": phases, "releves": samples}
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    s.close()
    return 0 if replies else 1


if __name__ == "__main__":
    sys.exit(main())
