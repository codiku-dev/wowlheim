"""Orchestrateur : pour chaque test d'acceptation, remet les tables de pièces à zéro, redémarre mangosd (stdin tenu ouvert),
lance le test et collecte le résultat. Prérequis : realmd et MySQL en marche ; compte de test dans C:\Wowlheim\run\test_account.txt.
python tools/run_all.py [test1 test2 ...]   (défaut : tous les tests structurels)"""
import os, subprocess, sys, time
RUN = r"C:\Wowlheim\run"
MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
TOOLS = os.path.dirname(os.path.abspath(__file__))
TESTS = sys.argv[1:] or ["phase3_acceptance", "station_test", "zone_test", "cost_test", "harvest_test", "craft_test", "api_test", "level_test", "prod_node_test", "tree_test", "hammer_test", "smelter_test", "known_test", "use_range_test", "pieces_test", "blocked_test"]
PY_LUPA = os.path.join(TOOLS, "client", ".venv", "Scripts", "python.exe")
pw = [l.split(": ", 1)[1].strip() for l in open(os.path.join(RUN, "test_account.txt"), encoding="utf-8") if l.startswith("password:")][0]

def sql(q):
    subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-e", q], check=True)

def stop_server(proc):
    if proc and proc.poll() is None:
        try:
            proc.stdin.write(b"server shutdown 1\n"); proc.stdin.flush()
            proc.wait(timeout=30)
        except Exception:
            proc.kill()
    subprocess.run(["taskkill", "/F", "/IM", "mangosd.exe"], capture_output=True)

def start_server():
    sql("delete from classicmangos.gameobject where id between 9100001 and 9100099 or id between 9110000 and 9119999; delete from classiccharacters.wowlheim_piece; "
        "delete from classicmangos.creature where guid>=9000000 and id in (257,299);")
    out = open(os.path.join(RUN, "mangosd.out"), "wb"); err = open(os.path.join(RUN, "mangosd.err"), "wb")
    proc = subprocess.Popen([os.path.join(RUN, "mangosd.exe"), "-c", "mangosd.conf"], cwd=RUN, stdin=subprocess.PIPE, stdout=out, stderr=err)
    for _ in range(90):
        time.sleep(1)
        if b"World initialized" in open(os.path.join(RUN, "mangosd.out"), "rb").read():
            return proc
    raise SystemExit("mangosd n'a pas démarré")

results = {}
proc = None
for t in TESTS:
    stop_server(proc)
    proc = start_server()
    py = PY_LUPA if t == "api_test" else sys.executable
    r = subprocess.run([py, os.path.join(TOOLS, t + ".py"), "WLTEST", pw], cwd=TOOLS, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=1800)
    lines = [l for l in r.stdout.splitlines() if not l.startswith("[realmd]")]
    bad = [l for l in lines if l.startswith("[ÉCHEC]")]
    results[t] = (r.returncode == 0 and not bad and any("OK" in l and "RÉSULTAT" in l for l in lines), bad, r.stderr.strip().splitlines()[-1:] )
    print(("[OK]   " if results[t][0] else "[ÉCHEC]"), t, flush=True)
    for l in bad: print("        ", l[:200])
    if r.stderr.strip() and not results[t][0]: print("         stderr:", r.stderr.strip().splitlines()[-1][:200])
stop_server(proc)
print("RÉSULTAT GLOBAL :", "OK" if all(v[0] for v in results.values()) else "ÉCHECS")
