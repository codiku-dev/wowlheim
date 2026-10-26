"""Test de stabilité (critère phase 1 sans bots : 2 joueurs, N minutes sans crash). Deux bots de protocole :
 A (compte 1) : relève toutes les 20 s .build perf/.build count, se téléporte régulièrement entre 3 lieux (charge des grilles) ;
 B (compte 2) : tue/pille des kobolds, pose et démolit des pièces en boucle (nocost).
python soak_test.py <compte1> <mdp1> <compte2> <mdp2> <minutes>   → journal sur stdout"""
import socket, struct, subprocess, sys, threading, time, re
from wlclient import Session
MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip().splitlines()
minutes = float(sys.argv[5]); end = time.time() + minutes * 60
log_lock = threading.Lock()
def log(*a):
    with log_lock: print(time.strftime("%H:%M:%S"), *a, flush=True)
def login(user, pw, name):
    s = Session(user, pw)
    chars = {nm: g for g, nm in s.chars()}
    if name not in chars:
        s.create(name); chars = {nm: g for g, nm in s.chars()}
    s.login(chars[name]); return s
def say(s, c, t=0.6): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
status = {"A": "?", "B": "?"}
def botA():
    try:
        s = login(sys.argv[1], sys.argv[2], 'Wlhouse'); n = 0
        places = ['Westfall', 'Barrens', 'WesternPlaguelands']
        while time.time() < end:
            for _ in range(10):
                if time.time() >= end: break
                r = say(s, '.build perf', 1.0); r2 = say(s, '.build count', 0.6)
                log('A', ' | '.join(r + r2)); time.sleep(20)
            if time.time() < end:
                p = places[n % 3]; n += 1; ok = s.teleport(p); say(s, '.revive'); log('A téléport', p, ok)
        s.close(); status["A"] = "ok"
    except Exception as e:
        status["A"] = f"ERREUR {type(e).__name__}: {e}"; log('A', status["A"])
def botB():
    try:
        s = login(sys.argv[3], sys.argv[4], 'Wlsoak'); say(s, '.build nocost on'); say(s, '.revive')
        s.teleport_cmd('.go xyz -6205 745 400 0'); time.sleep(3); say(s, '.revive')
        i = 0
        errors = 0
        while time.time() < end:
            try:
                entry = 257
                say(s, '.revive'); say(s, f'.npc add {entry}', 0.5)
                rows = sql(f"select max(guid) from classicmangos.creature where id={entry} and guid>=9000000")
                if rows and rows[0].isdigit():
                    guid = (0xF130 << 48) | (entry << 24) | int(rows[0])
                    time.sleep(0.3); s.send(0x13D, struct.pack("<Q", guid)); say(s, '.die', 0.4)
                    s.send(0x15D, struct.pack("<Q", guid)); time.sleep(0.6)
                    s.send(0x15F, struct.pack("<Q", guid)); say(s, '.npc delete', 0.3)
                x = 3 + (i % 12) * 2
                say(s, f'.build place Plancher {x} {(i // 12 % 6) * 2 - 6} 0 0', 0.4)
                if i % 3 == 2: say(s, '.build remove', 0.4)
                i += 1
                if i % 30 == 0: log('B cycles', i, ' | '.join(say(s, '.build count', 0.5)))
            except (socket.error, EOFError, ConnectionError) as e:
                raise                                   # la connexion est perdue : le serveur est probablement tombé
            except Exception as e:
                errors += 1; log('B erreur de cycle', type(e).__name__, e)
                if errors > 20: raise
            time.sleep(3)
        s.close(); status["B"] = "ok"
    except Exception as e:
        status["B"] = f"ERREUR {type(e).__name__}: {e}"; log('B', status["B"])
ta, tb = threading.Thread(target=botA), threading.Thread(target=botB)
ta.start(); time.sleep(5); tb.start(); ta.join(); tb.join()
log('FIN', status)
