"""Construit cache/spawns.tsv : toutes les apparitions de creatures des continents (cartes 0 et 1) avec leur zone,
calculee a partir des fichiers .map extraits du client (meme algorithme que le serveur). Lecture seule sur la base du jeu.
Sortie : cache/spawns.tsv  (guid, entry, map, x, y, zone_id, zone_name, area_id, area_name)"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import json
from common import sql, zone_of, read_dbc

HERE = os.path.dirname(__file__)
os.makedirs(os.path.join(HERE, "cache"), exist_ok=True)
rows = sql("""select c.guid, if(c.id=0, e.entry, c.id), c.map, c.position_x, c.position_y
              from creature c left join creature_spawn_entry e on c.id=0 and e.guid=c.guid
              where c.map in (0,1) and (c.id>0 or e.entry is not null)""")
out = open(os.path.join(HERE, "cache", "spawns.tsv"), "w", encoding="utf8")
miss = 0
for guid, entry, m, x, y in rows:
    z = zone_of(int(m), float(x), float(y))
    if z is None:
        miss += 1
        z = (0, "?", 0, "?")
    out.write("\t".join(map(str, [guid, entry, m, round(float(x), 2), round(float(y), 2), *z])) + "\n")
out.close()
print(len(rows), "apparitions,", miss, "sans zone")

# GameObjectDisplayInfo.dbc : id -> chemin de modele (pour verifier les displayId des noeuds)
recs, st = read_dbc("GameObjectDisplayInfo.dbc")
json.dump({r[0]: st(r[1]) for r in recs}, open(os.path.join(HERE, "cache", "gobj_display.json"), "w", encoding="utf8"))
print(len(recs), "modeles de GameObjectDisplayInfo.dbc")
