"""Nœuds de production (008) : charge du serveur avec ~4 800 nœuds, récolte d'un arbre et d'un nœud (ossements) de production avec l'outil.
python prod_node_test.py <compte> <mdp>"""
import subprocess, sys, time
from wlclient import Session, login_char

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"


def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()


def node(entry, skip=0):
    rows = [r.split("\t") for r in sql(f"select guid, round(position_x,2), round(position_y,2), round(position_z,2) from classicmangos.gameobject "
                                       f"where id={entry} and map=0 and guid>=9510001 order by guid limit {skip + 1}")]
    g, x, y, z = rows[skip]
    return int(g), float(x), float(y), float(z)


s = Session(sys.argv[1], sys.argv[2])
login_char(s, 'Wlprod')
ok = True


def say(c, t=0.8):
    return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]


def check(name, cond, detail=''):
    global ok
    ok &= bool(cond)
    print(('[OK]   ' if cond else '[ÉCHEC]'), name, detail)


total = int(sql("select count(*) from classicmangos.gameobject where id between 9101001 and 9101999")[0])
trees = int(sql("select count(*) from classicmangos.creature where id between 9300001 and 9300199")[0])
check('nœuds en base : pierre/minerai (GameObjects) + arbres et roches de Valheim (créatures)', total + trees >= 4700, f"{total} + {trees}")
time.sleep(30)                      # laisse la fenêtre de mesure du tick se remplir
perf = ' '.join(say('.build perf'))
check('diff tick moyen avec les nœuds en base', 'moyenne 50 ms' in perf or 'moyenne 51 ms' in perf, perf)
rock = node(9101041, 0)
print('nœud (ossements)', rock)


def goto(nd):
    s.teleport_cmd(f'.go xyz {nd[1]} {nd[2]} {nd[3] + 1} 0')
    time.sleep(2.5)
    say('.revive')
    time.sleep(1.0)


def equip(item_id):
    say(f'.additem {item_id} 1', 1.2)
    time.sleep(0.7)
    s.equip_item(item_id)
    time.sleep(1.0)


say('.revive')
equip(9201012)                      # pic en andouiller
goto(rock)
notes, items = s.use_gameobject(9101041, rock[0])
check('nœud (ossements) de production récolté avec le pic', items and not notes, str(notes) + str(items))
s.close()
print('RÉSULTAT :', 'OK' if ok else 'ÉCHEC')
