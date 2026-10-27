#!/usr/bin/env python3
"""Passage de tests unique des bots sur le serveur de TEST (a lancer apres un redemarrage).

Enchaine, avec le compte WLTEST : (1) /dire au milieu des bots de Comte-de-l'Or (un seul doit
repondre) ; (2) canal General de la foret d'Elwynn ; (3) chuchotement a un bot eloigne (activite) ;
puis resume le journal du pont depuis le debut du passage (reponses, refus par raison, latences).
L'activite des 45 bots se mesure a part : bot_activity.py snapshot / diff.

  python -I bots/tests/test_pass.py [--far-bot Nom]
"""
import argparse
import collections
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = r"C:\Wowlheim\bots\state\bridge_log.jsonl"
PROBE = [sys.executable, "-I", os.path.join(HERE, "chat_probe.py")]


def run(args, title):
    print("\n=== %s ===" % title, flush=True)
    out = subprocess.run(PROBE + args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    lines = [l for l in out.stdout.splitlines() if l.startswith(("[", "Wl", "pas de")) or "->" in l]
    print("\n".join(l for l in lines if "(systeme)" not in l and "realmd" not in l) or out.stderr[-800:])
    return out.returncode


def bridge_summary(since):
    rows = []
    try:
        with open(LOG, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r["t"] >= since:
                    rows.append(r)
    except OSError:
        pass
    why = collections.Counter(r["why"] for r in rows)
    ok = [r for r in rows if r["why"] == "ok"]
    print("\n=== journal du pont (%d requetes) ===" % len(rows))
    print("raisons :", dict(why))
    by_msg = collections.defaultdict(list)
    for r in ok:
        by_msg[(r["other"], r["ch"], r["msg"])].append(r["bot"])
    multi = {k: v for k, v in by_msg.items() if len(v) > 1 and k[1] != "whisper"}
    print("messages avec plusieurs repondeurs (doit etre vide) :", multi or "aucun")
    if ok:
        dts = sorted(r["dt"] for r in ok)
        print("latence pont : mediane %.1f s, max %.1f s" % (dts[len(dts) // 2], dts[-1]))
    for r in ok:
        print("  [%s] %s -> %s : %s  =>  %s" % (r["ch"], r["other"], r["bot"], r["msg"], r["reply"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--far-bot", help="bot loin du joueur pour le test de chuchotement")
    a = ap.parse_args()
    t0 = time.time()
    rc = {}
    rc["dire_foule"] = run(["--tele", "goldshire", "--say", "salut tout le monde, quelqu'un pour les Mortemines ?",
                            "--wait", "45"], "/dire au milieu des bots (Comte-de-l'Or)")
    rc["canal_general"] = run(["--tele", "goldshire", "--channel", "General - Elwynn Forest",
                               "--text", "des gens chauds pour farmer les murlocs du lac ?", "--wait", "45"],
                              "canal General")
    if a.far_bot:
        rc["chuchote_loin"] = run(["--tele", "goldshire", "--whisper", "hello, t'es dans quel coin ?",
                                   "--bot", a.far_bot, "--wait", "60"], "chuchotement a un bot eloigne")
    bridge_summary(t0)
    print("\ncodes retour sonde :", rc)


if __name__ == "__main__":
    main()
