#!/usr/bin/env python3
"""Sonde des phrases d'initiative en groupe (route /spontaneous du pont) sur le serveur de TEST des bots.

Compte WLTEST2 (identifiants lus dans C:\\Wowlheim\\run\\test_account2.txt, jamais affiches).
  1. invite deux bots Alliance en ligne (.appear pres du premier) ;
  2. level_up : .levelup 1 sur le second bot (MJ), attend sa phrase en /groupe ;
  3. silence : le joueur ne dit rien ; attend une phrase d'initiative en /groupe
     (serveur prepare avec « setup_run.py --silence 40 60 » pour un test rapide) ;
  4. preuves : lignes /groupe recues sans qu'on ait parle + lignes « why: ok_initiative » de bridge_log.jsonl ;
  5. dissout le groupe et se deconnecte.

  python -I bots/tests/spontaneous_probe.py [--bots A B] [--levelup-wait 90] [--silence-wait 330]
"""
import argparse
import json
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import group_probe as gp  # noqa: E402  (session WLTEST2, pompe de paquets, outils SQL)
from chat_probe import sql  # noqa: E402

log = gp.log


def initiative_lines(since, bots):
    out = []
    try:
        with open(gp.BRIDGE_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("t", 0) >= since and e.get("bot") in bots and e.get("why") == "ok_initiative":
                    out.append(e)
    except OSError:
        pass
    return out


def invite(pump, s, bot, guid):
    n0 = len(pump.events)
    s.send(gp.OP_GROUP_INVITE, bot.encode() + b"\0")
    pump.run(15, until=lambda op, d: op == gp.OP_SMSG_GROUP_LIST and any(m[1] == guid for m in gp.parse_group_list(d)[0]))
    lists = [d for op, d in pump.events[n0:] if op == gp.OP_SMSG_GROUP_LIST]
    ok = bool(lists and any(m[1] == guid for m in gp.parse_group_list(lists[-1])[0]))
    log(("OK" if ok else "ECHEC") + " invitation de %s" % bot)
    return ok


def wait_party(pump, guids, wait):
    """Attend une ligne /groupe d'un des bots ; renvoie la liste des lignes recues."""
    n0 = len(pump.chat)
    names = set(guids.values())
    pump.run(wait, until=lambda op, d: op == gp.OP_SMSG_MESSAGECHAT and d[0] == gp.CHAT_PARTY
             and (gp.parse_chat(d) or (0, 0))[1] in guids)
    pump.run(1)
    return [c for c in pump.chat[n0:] if c[1] == gp.CHAT_PARTY and c[2] in names]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bots", nargs=2)
    ap.add_argument("--player")
    ap.add_argument("--levelup-wait", type=float, default=90)
    ap.add_argument("--silence-wait", type=float, default=330)  # > recharge de 4 min par bot du pont
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if not gp.wait_server(600):
        log("ECHEC : serveur de test pas pret")
        return 2

    s = gp.player_session(a.player)
    pump = gp.Pump(s)
    log("joueur %s connecte" % s.name)
    pump.run(2)
    gp.revive(pump, s)
    gp.system_lines(pump, ".gm off", 0.6)
    gp.system_lines(pump, ".gm visible on", 0.6)

    bots = sql("SELECT c.guid, c.name, c.level, c.zone FROM characters c "
               "JOIN classicrealmd_bots.account a ON a.id = c.account "
               "WHERE c.online = 1 AND a.username LIKE 'RNDBOT%' AND c.race IN (1,3,4,7) AND c.level < 59")
    in_group = {r[0] for r in sql("SELECT memberGuid FROM group_member")}
    if a.bots:
        cands = [b for name in a.bots for b in bots if b[1].lower() == name.lower()]
    else:
        cands = [b for b in bots if b[0] not in in_group]
        cands.sort(key=lambda b: b[3])                      # deux bots d'une meme zone si possible
        by_zone = {}
        for b in cands:
            by_zone.setdefault(b[3], []).append(b)
        pair = next((v[:2] for v in by_zone.values() if len(v) >= 2), cands[:2])
        cands = pair
    if len(cands) < 2:
        log("ECHEC : moins de deux bots Alliance disponibles")
        s.close()
        return 1
    guids = {int(b[0]): b[1] for b in cands}
    (ga, bot_a), (gb, bot_b) = list(guids.items())
    log("bots : %s (niveau %s), %s (niveau %s)" % (bot_a, cands[0][2], bot_b, cands[1][2]))
    s.teleport_cmd(".appear " + bot_a)
    pump.run(3)

    t0 = time.time()
    res = {"groupe": invite(pump, s, bot_a, ga) and invite(pump, s, bot_b, gb)}
    if not res["groupe"]:
        s.close()
        return 1
    pump.run(8)                    # salutations d'arrivee eventuelles (pas des initiatives)

    # level_up sur le second bot (MJ : selection + .levelup 1)
    t_lvl = time.time()
    s.send(gp.OP_SET_SELECTION, struct.pack("<Q", gb))
    pump.run(0.5)
    out = gp.system_lines(pump, ".levelup 1", 1.5)
    log(".levelup 1 sur %s : %s" % (bot_b, " | ".join(out)[:160]))
    # La premiere ligne peut etre un message tout fait de playerbots (« Upgrading spec ... ») : on attend
    # la phrase dont le pont a journalise l'initiative.
    ini, said = [], False
    end = time.time() + a.levelup_wait
    while time.time() < end and not said:
        for c in wait_party(pump, guids, end - time.time()):
            log("/groupe %s apres %.1fs : %s" % (c[2], c[0] - (t_lvl - pump.t0), c[3]))
        ini = [e for e in initiative_lines(t_lvl - 1, [bot_b]) if e.get("msg") == "[level_up]"]
        said = any(c[2] == bot_b and c[3] == e.get("reply") for e in ini for c in pump.chat)
    for e in ini:
        log("bridge_log : %s" % json.dumps(e, ensure_ascii=False))
    res["level_up"] = said

    # silence : on ne dit rien
    t_sil = time.time()
    log("silence du joueur pendant %.0f s max" % a.silence_wait)
    got = []
    end = time.time() + a.silence_wait
    while time.time() < end and not got:
        lines = wait_party(pump, guids, end - time.time())
        for c in lines:
            log("/groupe %s apres %.1fs de silence : %s" % (c[2], c[0] - (t_sil - pump.t0), c[3]))
        got = [e for e in initiative_lines(t_sil - 1, list(guids.values())) if e.get("msg") == "[silence]"
               and any(c[2] == e.get("bot") and c[3] == e.get("reply") for c in pump.chat)]
    for e in got:
        log("bridge_log : %s" % json.dumps(e, ensure_ascii=False))
    res["silence"] = bool(got)

    s.send(gp.OP_GROUP_DISBAND)
    pump.run(3)
    s.send(gp.OP_LOGOUT_REQUEST)
    pump.run(30, until=lambda op, d: op == gp.OP_SMSG_LOGOUT_COMPLETE)
    s.close()
    party = [c for c in pump.chat if c[1] == gp.CHAT_PARTY and c[2] in guids.values()]
    log("toutes les lignes /groupe des bots (le joueur n'a jamais parle) :")
    for c in party:
        log("  +%.0fs %s : %s" % (c[0] - (t0 - pump.t0), c[2], c[3]))
    crash = gp.crash_check()
    if crash:
        log("PLANTAGE : mangosd_bots.exe absent, rapport %s" % crash)
    log("resume : %s" % " ".join("%s=%s" % (k, "OK" if v else "ECHEC") for k, v in res.items()))
    return 0 if all(res.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
