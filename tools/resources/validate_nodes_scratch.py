"""Valide le monde Valheim (003, 005, 007, 008, 011, 012 et leurs dependances) sur une COPIE (wl_scratch2) sans toucher classicmangos :
copie les tables necessaires, applique 001, 002, 003, 005, 006, 007, 008, 010, 011, 012 DEUX fois (idempotence, ordre d'apply_sql.py), lance
check_nodes.py, enregistre la sortie dans check_nodes_result.txt, puis supprime wl_scratch2.
usage : python validate_nodes_scratch.py [--keep]"""
import os, sys, subprocess, time
sys.path.insert(0, os.path.dirname(__file__))
from common import sql, sql_file, REPO

HERE = os.path.dirname(__file__)
TABLES = ["gameobject", "gameobject_template", "gameobject_loot_template", "creature", "creature_template", "creature_spawn_entry",
          "creature_model_info", "creature_loot_template", "reference_loot_template", "item_template", "spell_template", "npc_vendor",
          "playercreateinfo", "playercreateinfo_item"]
W = os.path.join(REPO, "server", "sql", "world")
FILES = ["001_wowlheim_pieces.sql", "002_items.sql", "003_nodes.sql", "005_node_spawns.sql", "006_vendors.sql", "007_tools_recipes.sql",
         "008_node_spawns_production.sql", "010_nobuild_points.sql", "011_hammer_starter.sql", "012_valheim_content.sql"]
keep = "--keep" in sys.argv
sql("DROP DATABASE IF EXISTS wl_scratch2", "mysql", rows=False)
sql("CREATE DATABASE wl_scratch2 DEFAULT CHARACTER SET utf8mb3", "mysql", rows=False)
log = []
try:
    for t in TABLES:
        sql("CREATE TABLE wl_scratch2.%s LIKE classicmangos.%s" % (t, t), "mysql", rows=False)
        sql("INSERT INTO wl_scratch2.%s SELECT * FROM classicmangos.%s" % (t, t), "mysql", rows=False)
    log.append("copie de %d tables de classicmangos dans wl_scratch2 (classicmangos non modifiee)" % len(TABLES))
    for p in (1, 2):
        t0 = time.time()
        for f in FILES:
            sql_file(os.path.join(W, f), "wl_scratch2")
        n = sql("select (select count(*) from creature where guid between 9600001 and 9699999), "
                "(select count(*) from gameobject where id between 9130001 and 9130099), "
                "(select count(*) from gameobject where id between 9101001 and 9101999)", "wl_scratch2")[0]
        log.append("passe %d : %s appliques sans erreur (%.0f s) ; creatures-ressources %s, ramassables %s, anciens noeuds %s"
                   % (p, ", ".join(f[:3] for f in FILES), time.time() - t0, n[0], n[1], n[2]))
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
