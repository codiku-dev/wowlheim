#!/usr/bin/env python3
"""Sonde Valheim sur un serveur de bots (essai de fusion : realmd 3725, monde 8086, bases *_m par defaut).

Client de protocole (tools/wlclient.py, ports rediriges par chat_probe), compte WLTEST (mot de passe lu dans
C:\\Wowlheim\\run\\test_account.txt, jamais affiche). Verifie, sans toucher aux scripts de tools/ :
  1. « .build api list » : une ligne P| par modele de piece de la base (wowlheim_piece_template) ;
  2. « .build count » / « .build perf » (commandes sans effet) ;
  3. une piece posee au marteau (table de fabrication, « .build api placeat ») -> ligne dans wowlheim_piece, puis demolie ;
  4. un hetre de Valheim (creature 9300001) abattu a la hache en pierre (degats de coupe, arbre mort, tronc qui apparait).

  set WL_DB_SUFFIX=_m && python -I bots/tests/valheim_probe.py [--char Wlcost]
"""
import argparse
import math
import os
import socket
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("WL_DB_SUFFIX", "_m")
import chat_probe as cp  # noqa: E402  (redirige 3724/8085 -> 3725/8086 puis importe wlclient)
import wlclient  # noqa: E402

SFX = cp.DB_SUFFIX
ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(("[OK]    " if cond else "[ECHEC] ") + name, detail, flush=True)


def sql(db, q):
    out = subprocess.run([cp.MYSQL, "-uroot", "-h127.0.0.1", "-N", "-B", db + SFX, "-e", q],
                         capture_output=True, text=True, encoding="utf-8")
    return [line.split("\t") for line in out.stdout.splitlines() if line]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--char", default="Wlcost")   # compte WLTEST plein (10 personnages) : on reprend celui de hammer_test
    a = ap.parse_args()
    user, pw = cp.credentials()
    s = wlclient.Session(user, pw)
    wlclient.login_char(s, a.char)
    time.sleep(2)

    def say(c, t=0.8):
        return [l for l in s.say(c, t) if "Welcome to" not in l and "Tickets" not in l]

    say(".revive")
    # 1. catalogue
    n_tpl = int(sql("classicmangos", "SELECT COUNT(*) FROM wowlheim_piece_template")[0][0])
    lst = [l for l in say(".build api list", 2.5) if l.startswith("[WL]P|")]
    check(".build api list : une ligne P| par piece de la base", len(lst) == n_tpl and n_tpl > 0, "%d lignes / %d modeles" % (len(lst), n_tpl))
    print("   ", lst[0][:100] if lst else "")
    r = say(".build count") + say(".build perf")
    check(".build count / .build perf repondent", any("Pi" in l and "total" in l for l in r) and any("Diff tick" in l for l in r), " | ".join(r))

    # 2. piece posee au marteau
    wlclient.goto_test_spot(s)
    say(".build nocost on")
    say(".additem 9201100 1", 1.2)
    time.sleep(0.5)
    s.equip_item(9201100)
    time.sleep(1.0)
    s.send(0x13D, struct.pack("<Q", 0))
    gps = [l for l in say(".gps", 1.0) if l.startswith("X:")]
    f = gps[0].replace(":", " ").split()
    x, y, z = float(f[1]), float(f[3]), float(f[5])
    guid_lo = s.guid & 0xFFFFFFFF
    before = {r_[0] for r_ in sql("classiccharacters", "SELECT guid FROM wowlheim_piece")}
    say(".build api select 6 0")
    r = say(".build api placeat %.2f %.2f %.2f" % (x + 5, y + 3, z), 1.5)
    new = []
    for _ in range(15):
        new = [r_ for r_ in sql("classiccharacters", "SELECT guid, piece_id, owner_guid, x, y, z FROM wowlheim_piece") if r_[0] not in before]
        if new:
            break
        time.sleep(0.2)
    check("piece posee au marteau (table de fabrication) : D|place|1 + ligne wowlheim_piece", any("D|place|1" in l for l in r) and len(new) == 1,
          "%s %s" % ([l for l in r if "D|" in l], new))
    if new:
        g = int(new[0][0])
        r = say(".build api removeguid %016X" % ((0xF110 << 48) | ((9110000 + 6) << 24) | g), 1.5)
        time.sleep(0.5)
        gone = not sql("classiccharacters", "SELECT guid FROM wowlheim_piece WHERE guid=%d" % g)
        check("piece demolie (.build api removeguid)", gone and any("D|removeguid|1" in l for l in r), str([l for l in r if "D|" in l]))
    say(".build nocost off")

    # 3. hetre abattu a la hache en pierre
    row = sql("classicmangos", "SELECT guid, position_x, position_y, position_z FROM creature WHERE id=9300001 AND map=0 AND guid NOT IN "
              "(SELECT guid FROM classiccharacters%s.creature_respawn) ORDER BY guid LIMIT 1" % SFX)
    check("un hetre de Valheim (creature 9300001) disponible", bool(row), str(row))
    if row:
        low, tx, ty, tz = int(row[0][0]), float(row[0][1]), float(row[0][2]), float(row[0][3])
        say(".gm off")
        say(".additem 9201010 1", 1.2)
        time.sleep(0.7)
        s.equip_item(9201010)
        time.sleep(1.0)
        px, py = tx + 1.6, ty
        s.send(0x13D, struct.pack("<Q", s.guid))
        say(".modify hp 50000", 0.4)
        s.teleport_cmd(".go xyz %.2f %.2f %.2f 0" % (px, py, tz + 0.5))
        time.sleep(1.0)
        face = math.atan2(ty - py, tx - px) % (2 * math.pi)
        s.send(0x0DA, struct.pack("<II4fI", 0, int(time.time() * 1000) & 0xFFFFFFFF, px, py, tz + 0.5, face, 0))
        time.sleep(0.6)
        say(".build api skills stamina 50", 0.4)
        g = (0xF130 << 48) | (9300001 << 24) | low
        s.send(0x13D, struct.pack("<Q", g))
        s.send(0x141, struct.pack("<Q", g))      # CMSG_ATTACKSWING
        hits, end = [], time.time() + 60
        s.s.settimeout(0.5)
        while time.time() < end and sum(hits) < 80:
            try:
                op, d = s.read()
            except socket.timeout:
                continue
            if op == 0x14A:                       # SMSG_ATTACKERSTATEUPDATE
                i = 4
                mask = d[i]; i += 1
                for b in range(8):
                    if mask & (1 << b):
                        i += 1
                mask = d[i]; i += 1; tg = 0
                for b in range(8):
                    if mask & (1 << b):
                        tg |= d[i] << (8 * b); i += 1
                if tg == g:
                    hits.append(struct.unpack("<I", d[i:i + 4])[0])
        s.send(0x142)
        time.sleep(2.5)
        trees = [l for l in say(".build api trees 25", 1.2) if l.startswith("[WL]T|")]
        mine = [l for l in trees if l[6:].split("|")[0] == str(low)]
        logs = [l for l in trees if l[6:].split("|")[2] == "log" and l[6:].split("|")[6] == "1"]
        print("    coups :", hits)
        check("hetre abattu a la hache en pierre (>= 80 degats de coupe, arbre mort, tronc apparu)",
              sum(hits) >= 80 and (not mine or mine[0][6:].split("|")[6] == "0") and logs, "%s | %s" % (mine, logs[:1]))
    s.close()
    print("RESULTAT :", "OK" if ok else "ECHEC")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
