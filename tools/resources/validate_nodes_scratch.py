"""Valide 008 sur une COPIE (wl_scratch2) sans toucher classicmangos : copie les tables necessaires, applique 003, 005, 010 puis 008 DEUX fois
(idempotence), lance check_nodes.py, enregistre la sortie dans check_nodes_result.txt, puis supprime wl_scratch2.
usage : python validate_nodes_scratch.py [--keep]"""
import os, sys, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from common import sql, sql_file, REPO

HERE = os.path.dirname(__file__)
TABLES = ["gameobject", "gameobject_template", "gameobject_loot_template", "creature", "creature_template", "creature_spawn_entry"]
W = os.path.join(REPO, "server", "sql", "world")
FILES = ["003_nodes.sql", "005_node_spawns.sql", "010_nobuild_points.sql"]
keep = "--keep" in sys.argv
sql("DROP DATABASE IF EXISTS wl_scratch2", "mysql", rows=False)
sql("CREATE DATABASE wl_scratch2 DEFAULT CHARACTER SET utf8mb3", "mysql", rows=False)
log = []
try:
    for t in TABLES:
        sql("CREATE TABLE wl_scratch2.%s LIKE classicmangos.%s" % (t, t), "mysql", rows=False)
        sql("INSERT INTO wl_scratch2.%s SELECT * FROM classicmangos.%s" % (t, t), "mysql", rows=False)
    for f in FILES:
        sql_file(os.path.join(W, f), "wl_scratch2")
    log.append("copie de %d tables + application de %s dans wl_scratch2 (classicmangos non modifiee)" % (len(TABLES), ", ".join(FILES)))
    for p in (1, 2):
        sql_file(os.path.join(W, "008_node_spawns_production.sql"), "wl_scratch2")
        n = sql("select count(*), min(guid), max(guid) from gameobject where guid >= 9510001", "wl_scratch2")[0]
        log.append("passe %d : 008 appliquee sans erreur ; lignes de production = %s (guid %s-%s)" % (p, n[0], n[1], n[2]))
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "check_nodes.py"), "--db", "wl_scratch2", "--baseline", "classicmangos"],
                       capture_output=True, cwd=HERE, env={**os.environ, "PYTHONPATH": HERE})
    out = r.stdout.decode("utf8", "replace") + r.stderr.decode("utf8", "replace")
    log.append("check_nodes.py code retour : %d (0 = tout OK, 1 = erreur de forme, 3 = constats de couverture)" % r.returncode)
    text = "\n".join(log) + "\n\n" + out
    open(os.path.join(HERE, "check_nodes_result.txt"), "w", encoding="utf8").write(text)
    print(text)
finally:
    if not keep:
        sql("DROP DATABASE IF EXISTS wl_scratch2", "mysql", rows=False)
        print("wl_scratch2 supprimee")
