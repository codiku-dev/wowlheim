#!/usr/bin/env python3
"""Combien de bots autour d'un joueur (positions en base, sauvegardees periodiquement par le serveur).

  python -I bots/tests/near_player.py [Gogo]
"""
import math
import subprocess
import sys

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
RACES = {1: "humain", 2: "orc", 3: "nain", 4: "elfe nuit", 5: "mort-vivant", 6: "tauren", 7: "gnome", 8: "troll"}


def sql(q):
    out = subprocess.run([MYSQL, "-uroot", "-h127.0.0.1", "-N", "-B", "classiccharacters_bots", "-e", q],
                         capture_output=True, text=True, encoding="utf-8").stdout
    return [l.split("\t") for l in out.splitlines() if l]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    name = sys.argv[1] if len(sys.argv) > 1 else "Gogo"
    me = sql("SELECT map, position_x, position_y, zone, level, online FROM characters WHERE name='%s'" % name.replace("'", ""))
    if not me:
        print("personnage introuvable :", name)
        return 1
    m, x, y, zone, lvl, online = me[0]
    bots = sql("SELECT c.name, c.race, c.level, c.map, c.position_x, c.position_y, c.zone FROM characters c "
               "JOIN classicrealmd_bots.account a ON a.id=c.account WHERE a.username LIKE 'RNDBOT%' AND c.online=1")
    near = []
    same_zone = 0
    for n, r, l, bm, bx, by, bz in bots:
        if bm != m:
            continue
        d = math.hypot(float(bx) - float(x), float(by) - float(y))
        same_zone += bz == zone
        near.append((d, n, int(r), int(l), bz))
    near.sort()
    print("%s : carte %s zone %s niveau %s (en ligne=%s) ; %d bots en ligne au total" % (name, m, zone, lvl, online, len(bots)))
    for r in (100, 300, 1000, 3000):
        print("  bots a moins de %4d m : %d" % (r, sum(1 for d, *_ in near if d <= r)))
    print("  bots dans la meme zone : %d" % same_zone)
    lv = sorted(int(b[2]) for b in bots)
    if lv:
        print("  niveaux des bots : min %d, mediane %d, max %d ; <= %d+8 : %d" % (lv[0], lv[len(lv) // 2], lv[-1], int(lvl),
                                                                             sum(1 for v in lv if v <= int(lvl) + 8)))
    for d, n, r, l, bz in near[:12]:
        print("    %-12s %-11s niv %2d zone %-5s a %6.0f m" % (n, RACES.get(r, r), l, bz, d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
