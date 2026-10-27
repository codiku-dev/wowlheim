#!/usr/bin/env python3
"""Verification rapide en jeu apres chaque deploiement (~2-3 min) : trois sondes EN PARALLELE,
chacune sur son compte, puis un resume du journal du pont et des intentions.

  A (WLTEST)  : test_pass.py  -> /dire en foule, canal General, chuchotement a un bot eloigne
  B (WLTEST2) : group_probe.py -> invitation, /groupe, Mortemines sans « summon » (suivi auto)
  C (WLTEST3) : combat_fr_probe.py -> silence en combat + ordres en francais libre (intentions)

  python -I bots/tests/quick_check.py [--far-bot Nom] [--orders "tu viens on va aux mortemines ?,attends moi ici"]
"""
import argparse
import collections
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = r"C:\Wowlheim\bots\state"
OUT = os.path.join(STATE, "quick_check")


def jsonl_since(path, t0):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("t", 0) >= t0:
                    rows.append(r)
    except OSError:
        pass
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--far-bot", default="Kedries")
    ap.add_argument("--orders", default="tu viens on va aux mortemines ?,attends moi ici,bon suis moi")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    py = [sys.executable, "-I"]
    jobs = {
        "A_chat": py + [os.path.join(HERE, "test_pass.py"), "--far-bot", a.far_bot],
        "B_groupe_donjon": py + [os.path.join(HERE, "group_probe.py"), "--chat-wait", "40", "--follow-wait", "40"],
        "C_combat_ordres": py + [os.path.join(HERE, "combat_fr_probe.py"), "--skip-b", "--commands", a.orders],
    }
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    procs = {}
    for name, cmd in jobs.items():
        f = open(os.path.join(OUT, name + ".txt"), "w", encoding="utf-8")
        procs[name] = (subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env), f)
        time.sleep(3)                       # etale les connexions realmd
    for name, (p, f) in procs.items():
        try:
            p.wait(timeout=600)
        except subprocess.TimeoutExpired:
            p.kill()
        f.close()
        with open(os.path.join(OUT, name + ".txt"), encoding="utf-8", errors="replace") as fh:
            lines = [l.rstrip() for l in fh if l.strip() and "(systeme)" not in l and "realmd" not in l]
        print("\n===== %s (code %s, %.0f s) =====" % (name, p.returncode, time.time() - t0))
        print("\n".join(lines[-25:]))
    br = jsonl_since(os.path.join(STATE, "bridge_log.jsonl"), t0)
    it = jsonl_since(os.path.join(STATE, "intent_log.jsonl"), t0)
    print("\n===== pont : %d requetes %s" % (len(br), dict(collections.Counter(r["why"] for r in br))))
    for r in br:
        if r["why"] == "ok":
            print("  [%s] %s -> %s : %s  =>  %s (%.1fs)" % (r["ch"], r["other"], r["bot"], r["msg"], r["reply"], r["dt"]))
    print("===== intentions : %d" % len(it))
    for r in it:
        print("  " + json.dumps(r, ensure_ascii=False)[:220])
    print("\nduree totale %.0f s ; sorties completes dans %s" % (time.time() - t0, OUT))


if __name__ == "__main__":
    main()
