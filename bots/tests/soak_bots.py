#!/usr/bin/env python3
"""Test d'endurance des bots (jalon 6) : 45 bots + 2 joueurs connectes pendant N minutes.

Joueur 1 (WLTEST) : a Comte-de-l'Or, dit une phrase en /dire toutes les 5 min.
Joueur 2 (WLTEST2) : chuchote a un bot de sa faction toutes les 5 min.
Toutes les 15 min : instantane des bots (bot_activity), tick (mangosd.out), CPU/RAM, plantages.
Resume final : joueurs restes connectes, reponses recues, journal du pont, activite debut/fin.

  python -I bots/tests/soak_bots.py [--minutes 60]
"""
import argparse
import json
import os
import random
import re
import socket
import struct
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bot_activity  # noqa: E402
import chat_probe as cp  # noqa: E402  (redirige aussi les ports vers le serveur de test)

MAIN = os.environ.get("WL_TARGET") == "main"   # serveur principal fusionne (3724/8085, bases principales)
RUN = r"C:\Wowlheim\run" if MAIN else r"C:\Wowlheim\bots\run"
EXE = "mangosd" if MAIN else "mangosd_bots"
STATE = r"C:\Wowlheim\bots\state"
SAYS = ["quelqu'un pour les Mortemines ce soir ?", "vous savez ou on trouve des murlocs ici ?",
        "ca farm bien le coin ?", "qui veut grouper pour les quetes du lac ?",
        "c'est calme ce soir", "il vend quoi le forgeron de Comte-de-l'Or ?"]
WHISPERS = ["salut, tu fais quoi en ce moment ?", "tu joues souvent le soir ?", "t'es level combien maintenant ?",
            "tu connais un bon spot pour xp ?", "tu veux grouper plus tard ?", "ta classe c'est sympa a jouer ?"]
lock = threading.Lock()
report = {"joueurs": {}, "releves": []}


def log(msg):
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    with lock:
        print(line, flush=True)
        with open(os.path.join(STATE, "soak.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")


def login(cred_file):
    kv = {}
    with open(cred_file, encoding="utf-8") as f:
        for line in f:
            if ": " in line:
                k, v = line.split(": ", 1)
                kv[k.strip()] = v.strip()
    s = cp.wlclient.Session(kv["account"], kv["password"])
    guid, name = s.chars()[0]
    s.login(guid)
    s.name = name
    return s


def pump(s, seconds, stats):
    """Lit les paquets (garde la connexion vivante) et compte les reponses de bots."""
    end = time.time() + seconds
    s.s.settimeout(0.5)
    while time.time() < end:
        try:
            op, d = s.read()
        except socket.timeout:
            continue
        if op == cp.OP_SMSG_MESSAGECHAT:
            c = cp.parse_chat(d)
            if c and c[0] in (0, 1, 6, 14) and c[1] != (s.guid & 0xFFFFFFFF):
                stats["recus"] += 1
                stats["derniers"] = (stats.get("derniers", []) + [c[2]])[-5:]


def player(role, cred_file, minutes, stop):
    st = {"recus": 0, "envoyes": 0, "erreur": None}
    report["joueurs"][role] = st
    try:
        s = login(cred_file)
        st["perso"] = s.name
        s.say(".revive", collect=1.0)          # un fantome n est pas entendu en /dire
        if role == "dire":
            s.teleport_cmd(".tele goldshire")
        log("%s connecte (%s)" % (role, s.name))
        end = time.time() + minutes * 60
        while time.time() < end and not stop.is_set():
            if role == "dire":
                txt = random.choice(SAYS)
                s.send(cp.OP_MESSAGECHAT, struct.pack("<II", 0, 0) + txt.encode() + b"\0")
            else:
                bots = cp.sql("SELECT c.name FROM characters c JOIN classicrealmd" + cp.DB_SUFFIX + ".account a ON a.id=c.account "
                              "WHERE a.username LIKE 'RNDBOT%' AND c.online=1 AND c.race IN (1,3,4,7) ORDER BY RAND() LIMIT 1")
                txt = random.choice(WHISPERS)
                s.send(cp.OP_MESSAGECHAT, struct.pack("<II", cp.CHAT_WHISPER, 0) + bots[0][0].encode() + b"\0"
                       + txt.encode() + b"\0")
            st["envoyes"] += 1
            pump(s, min(300, max(0, end - time.time())), st)
        s.close()
        log("%s termine : %d envoyes, %d reponses recues" % (role, st["envoyes"], st["recus"]))
    except Exception as e:
        st["erreur"] = "%s: %s" % (type(e).__name__, e)
        log("%s ERREUR %s" % (role, st["erreur"]))


def server_alive():
    return EXE + ".exe" in subprocess.run(["tasklist"], capture_output=True, text=True, errors="replace").stdout


DIFF_START = [0]   # position dans mangosd.out au debut du test : on ignore les ticks des sessions precedentes


def diffs():
    try:
        with open(os.path.join(RUN, "mangosd.out"), encoding="utf-8", errors="replace") as f:
            f.seek(DIFF_START[0])
            txt = f.read()
    except OSError:
        return []
    return [int(x) for x in re.findall(r"Avg Diff: (\d+)", txt)]


def releve(tag):
    snap = bot_activity.snapshot()
    path = os.path.join(STATE, "soak_%s.json" % tag)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    ps = subprocess.run(["powershell", "-NoProfile", "-Command",
                         "$p=Get-Process " + EXE + " -ErrorAction SilentlyContinue; if($p){'{0} {1}' -f [int]$p.CPU,[int]($p.WorkingSet64/1MB)}"],
                        capture_output=True, text=True).stdout.split()
    d = diffs()
    v = cp.sql("SELECT COUNT(*) FROM character_inventory ci JOIN item_instance ii ON ii.guid=ci.item JOIN characters c "
               "ON c.guid=ci.guid JOIN classicrealmd" + cp.DB_SUFFIX + ".account a ON a.id=c.account "
               "WHERE a.username LIKE 'RNDBOT%' AND ii.itemEntry >= 9000000")
    r = {"t": snap["t"], "bots": len(snap["bots"]), "fichier": path, "cpu_s": ps[0] if ps else None,
         "ram_mo": ps[1] if ps else None, "diff_dernier": d[-1] if d else None, "diff_max": max(d) if d else None,
         "valheim_chez_bots": int(v[0][0]) if v else None}
    report["releves"].append(r)
    log("releve %s : %d bots, objets Valheim chez les bots %s, CPU %s s, RAM %s Mo, diff %s ms (max %s)" % (
        tag, r["bots"], r["valheim_chez_bots"], r["cpu_s"], r["ram_mo"], r["diff_dernier"], r["diff_max"]))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=60)
    a = ap.parse_args()
    t0 = time.time()
    try:
        DIFF_START[0] = os.path.getsize(os.path.join(RUN, "mangosd.out"))
    except OSError:
        pass
    crashes0 = set(os.listdir(os.path.join(RUN, "Crashes"))) if os.path.isdir(os.path.join(RUN, "Crashes")) else set()
    log("debut du test d'endurance : %.0f min" % a.minutes)
    first = releve("debut")
    stop = threading.Event()
    th = [threading.Thread(target=player, args=("dire", r"C:\Wowlheim\run\test_account.txt", a.minutes, stop)),
          threading.Thread(target=player, args=("chuchote", r"C:\Wowlheim\run\test_account2.txt", a.minutes, stop))]
    for t in th:
        t.start()
    end = t0 + a.minutes * 60
    n = 1
    while time.time() < end:
        time.sleep(min(15 * 60, max(1, end - time.time())))
        if not server_alive():
            log("SERVEUR ARRETE")
            stop.set()
            break
        releve("%02d" % (n * 15))
        n += 1
    for t in th:
        t.join(timeout=60)
    last = report["releves"][-1]["fichier"]
    crashes = sorted(set(os.listdir(os.path.join(RUN, "Crashes"))) - crashes0) if os.path.isdir(os.path.join(RUN, "Crashes")) else []
    with open(first, encoding="utf-8") as f:
        A = json.load(f)
    with open(last, encoding="utf-8") as f:
        B = json.load(f)
    print()
    changed = bot_activity.diff(A, B)
    rows = []
    with open(os.path.join(STATE, "bridge_log.jsonl"), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["t"] >= t0:
                rows.append(r)
    why = {}
    for r in rows:
        why[r["why"]] = why.get(r["why"], 0) + 1
    d = diffs()
    summary = {"duree_min": round((time.time() - t0) / 60, 1), "serveur_vivant": server_alive(),
               "nouveaux_plantages": crashes, "bots_ayant_change": changed, "bots_fin": len(B["bots"]),
               "joueurs": report["joueurs"], "pont": why, "releves": report["releves"],
               "diff_moyen_global": round(sum(d) / len(d), 1) if d else None, "diff_max_global": max(d) if d else None}
    with open(os.path.join(STATE, "soak_resume.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    log("RESUME " + json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
