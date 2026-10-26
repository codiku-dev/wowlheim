"""Récolte : un nœud exige l'outil équipé du bon type et du bon palier (hache pour le bois, pic pour la pierre).
python harvest_test.py <compte> <mdp>   (GM : .additem pour donner les outils ; pas de redémarrage du serveur nécessaire)"""
import subprocess, sys, time, re
from wlclient import Session, login_char
MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()
def node(entry, skip=0):
    rows = [r.split("\t") for r in sql(f"select guid, round(position_x,2), round(position_y,2), round(position_z,2) from classicmangos.gameobject where id={entry} and map=0 order by guid limit {skip+1}")]
    g, x, y, z = rows[skip]; return int(g), float(x), float(y), float(z)
s = Session(sys.argv[1], sys.argv[2]); login_char(s, 'Wlharvest')
ok = True
def say(c, t=0.8): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
def check(name, cond, detail=''):
    global ok; ok &= bool(cond); print(('[OK]   ' if cond else '[ÉCHEC]'), name, detail)
def inv(): return ' '.join(say('.build inv'))
def goto(nd):
    g_, x, y, z = nd
    s.teleport_cmd(f'.go xyz {x} {y} {z + 1} 0'); time.sleep(2.5); say('.revive'); time.sleep(1.0)
def equip(item_id):
    say(f'.additem {item_id} 1', 1.2); time.sleep(0.7); s.equip_item(item_id); time.sleep(1.0)
say('.revive'); say('.build nocost off')
for it in (9201011, 9201012, 9200001, 9200002): say(f'.additem {it} -99')
time.sleep(0.5)
rock1 = node(9101041, 0)
print('nœud', rock1)

goto(rock1)
notes, items = s.use_gameobject(9101041, rock1[0])
check('sans outil : nœud (ossements) refusé avec message', notes and 'pic' in notes[0].lower(), str(notes) + str(items))
equip(9201011)                                     # hache en silex en main droite
notes, items = s.use_gameobject(9101041, rock1[0])
check('hache équipée sur un nœud (ossements) : refusé (il faut un pic)', notes and 'pic' in notes[0].lower() and not items, str(notes) + str(items))
equip(9201012)                                     # pic en andouiller en main droite
notes, items = s.use_gameobject(9101041, rock1[0])
print('nœud (ossements) avec pic :', notes, items)
check('pic équipé sur un nœud (ossements) : butin ouvert', items and not notes, str(items))
for slot, item, cnt in items:
    s.autostore_loot(slot); time.sleep(0.3)
time.sleep(0.8)
r = inv(); print(r)
check('butin du nœud dans le sac après récolte', any(it for _, it, _c in items), r)
# le bois se récolte désormais en abattant les arbres de Valheim (créatures) : voir tree_test.py
s.close()
print('RÉSULTAT :', 'OK' if ok else 'ÉCHEC')
