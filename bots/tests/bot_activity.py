#!/usr/bin/env python3
"""Preuve que les bots jouent seuls (jalon 1) : instantane des personnages RNDBOT en ligne
(niveau, XP, argent, position, zone, quetes), puis comparaison apres quelques minutes.

  python -I bots/tests/bot_activity.py snapshot            # ecrit C:\\Wowlheim\\bots\\state\\activity_<heure>.json
  python -I bots/tests/bot_activity.py diff A.json B.json  # ce qui a change entre deux instantanes
"""
import json
import math
import os
import subprocess
import sys
import time

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
SUFFIX = os.environ.get("WL_DB_SUFFIX", "" if os.environ.get("WL_TARGET") == "main" else "_bots")
STATE = r"C:\Wowlheim\bots\state"
COLS = ["name", "race", "class", "level", "xp", "money", "map", "zone", "x", "y", "z", "online", "quests_done", "quests_active"]


def snapshot():
    q = ("SELECT c.name, c.race, c.class, c.level, c.xp, c.money, c.map, c.zone, "
         "ROUND(c.position_x,1), ROUND(c.position_y,1), ROUND(c.position_z,1), c.online, "
         "(SELECT COUNT(*) FROM character_queststatus q WHERE q.guid=c.guid AND q.rewarded=1), "
         "(SELECT COUNT(*) FROM character_queststatus q WHERE q.guid=c.guid AND q.rewarded=0) "
         "FROM characters c JOIN classicrealmd{SUFFIX}.account a ON a.id=c.account "
         "WHERE a.username LIKE 'RNDBOT%' AND c.online=1 ORDER BY c.name").replace("{SUFFIX}", SUFFIX)
    out = subprocess.run([MYSQL, "-uroot", "-h127.0.0.1", "-N", "-B", "classiccharacters" + SUFFIX, "-e", q],
                         capture_output=True, text=True, encoding="utf-8").stdout
    rows = [dict(zip(COLS, line.split("\t"))) for line in out.splitlines() if line]
    return {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "bots": rows}


def diff(a, b):
    old = {r["name"]: r for r in a["bots"]}
    changed = 0
    print("%s -> %s : %d bots en ligne avant, %d apres" % (a["t"], b["t"], len(a["bots"]), len(b["bots"])))
    for r in b["bots"]:
        o = old.get(r["name"])
        if not o:
            print("  %-12s nouveau (niveau %s, zone %s)" % (r["name"], r["level"], r["zone"]))
            continue
        d = []
        for k in ("level", "xp", "money", "zone", "quests_done", "quests_active"):
            if o[k] != r[k]:
                d.append("%s %s->%s" % (k, o[k], r[k]))
        dist = math.dist([float(o[k]) for k in "xyz"], [float(r[k]) for k in "xyz"]) if o["map"] == r["map"] else -1
        if dist != 0:
            d.append("deplacement %s" % ("changement de carte" if dist < 0 else "%.0f m" % dist))
        if d:
            changed += 1
        print("  %-12s %s" % (r["name"], ", ".join(d) or "aucun changement"))
    print("bots ayant change : %d / %d" % (changed, len(b["bots"])))
    return changed


def main(argv):
    if argv[:1] == ["snapshot"]:
        s = snapshot()
        os.makedirs(STATE, exist_ok=True)
        path = os.path.join(STATE, "activity_%s.json" % time.strftime("%H%M%S"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)
        print(path, "-", len(s["bots"]), "bots en ligne")
        for r in s["bots"]:
            print("  %(name)-12s niv %(level)-2s race %(race)s classe %(class)s zone %(zone)s xp %(xp)s" % r)
        return 0
    if argv[:1] == ["diff"] and len(argv) == 3:
        with open(argv[1], encoding="utf-8") as f:
            a = json.load(f)
        with open(argv[2], encoding="utf-8") as f:
            b = json.load(f)
        return 0 if diff(a, b) else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
