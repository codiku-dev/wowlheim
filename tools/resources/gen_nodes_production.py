"""Ecrit server/sql/world/008_node_spawns_production.sql : SUPPRESSION des anciens noeuds de ressources GameObject aux modeles WoW.

Historique : ce script placait 4 664 noeuds GameObject (modeles WoW 9101001-9101045) sur les positions des creatures. Depuis le
2026-10-26 le monde est peuple d'objets de Valheim :
  - positions : tools/resources/place_resources.py -> C:\\Wowlheim\\data\\wl_terrain\\placements.json (d'apres le terrain du client,
    palier = palier de la zone ; docs/RESOURCES_PLACEMENT.md) ;
  - arbres, roches, filons (creatures) et ramassables (GameObjects 9130001+) : 012_valheim_content.sql (tools/valheim/gen_server_sql.py).
008 ne fait donc plus que retirer les anciens noeuds (toutes apparitions des entrees 9101001-9101999 ; 003 retire leurs modeles et leur
butin, 005 les noeuds de validation). Aucune base n'est lue ni ecrite.
usage : python gen_nodes_production.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO
import rules, generate

OUT = os.path.join(REPO, "server", "sql", "world", "008_node_spawns_production.sql")


def main():
    text = generate.HEADER + (
        "-- 008 : SUPPRESSION des anciens noeuds de ressources GameObject aux modeles WoW (entrees 9101001-9101999, toutes apparitions).\n"
        "-- Le monde est desormais peuple d'objets de Valheim (arbres, roches, filons = creatures ; ramassables = GameObjects 9130001+)\n"
        "-- ecrits dans 012_valheim_content.sql par tools/valheim/gen_server_sql.py, aux positions de C:\\Wowlheim\\data\\wl_terrain\\placements.json\n"
        "-- (tools/resources/place_resources.py, docs/RESOURCES_PLACEMENT.md).\n")
    text += "DELETE FROM `gameobject` WHERE `id` BETWEEN %d AND %d;\n" % (rules.OLD_NODE_ENTRY_MIN, rules.OLD_NODE_ENTRY_MAX)
    with open(OUT, "w", encoding="utf8", newline="\n") as f:
        f.write(text)
    print("ecrit", OUT, len(text), "octets")


if __name__ == "__main__":
    main()
