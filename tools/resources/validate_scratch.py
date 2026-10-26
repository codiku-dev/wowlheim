"""Valide 002..006 sur une COPIE (wl_scratch) sans toucher classicmangos : copie les tables, applique les scripts DEUX fois
(idempotence), lance check.py --db wl_scratch --baseline classicmangos, puis supprime wl_scratch.
usage : python validate_scratch.py [--keep]"""
import os, sys, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from common import sql, sql_file, REPO

TABLES = ["item_template", "gameobject_template", "gameobject_loot_template", "reference_loot_template", "creature_loot_template",
          "gameobject", "npc_vendor", "creature_template", "creature", "creature_spawn_entry"]
FILES = ["002_items.sql", "003_nodes.sql", "004_loot.sql", "005_node_spawns.sql", "006_vendors.sql"]
keep = "--keep" in sys.argv
sql("DROP DATABASE IF EXISTS wl_scratch", "mysql", rows=False)
sql("CREATE DATABASE wl_scratch DEFAULT CHARACTER SET utf8mb3", "mysql", rows=False)
try:
    for t in TABLES:
        sql("CREATE TABLE wl_scratch.%s LIKE classicmangos.%s" % (t, t), "mysql", rows=False)
        sql("INSERT INTO wl_scratch.%s SELECT * FROM classicmangos.%s" % (t, t), "mysql", rows=False)
    for p in (1, 2):
        for f in FILES:
            sql_file(os.path.join(REPO, "server", "sql", "world", f), "wl_scratch")
        print("passe %d : %d scripts appliques sans erreur" % (p, len(FILES)))
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "check.py"), "--db", "wl_scratch", "--baseline", "classicmangos"])
    print("check.py code retour :", r.returncode)
finally:
    if not keep:
        sql("DROP DATABASE IF EXISTS wl_scratch", "mysql", rows=False)
        print("wl_scratch supprimee")
