"""Cueillette façon Valheim : les ramassables (composant Pickable de Valheim : Pickable_Flint, Pickable_Branch, Pickable_Stone...)
sont des GameObjects coffre (type 3) ramassés à la main, sans outil (aucune entrée wowlheim_node) ; un clic met directement
Pickable.m_itemPrefab x m_amount dans le sac (Pickable.Interact : pas de fenêtre de butin), puis l'objet disparaît jusqu'à sa repousse (tools/valheim/gen_server_sql.py, build_pickables).
L'abattage et le minage (créatures arbres / rochers, outil requis) sont testés par tree_test.py.
python harvest_test.py <compte> <mdp>   (GM ; pas de redémarrage du serveur nécessaire)"""
import subprocess, sys, time, re
from wlclient import Session, login_char
MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()
def node(entry):
    """Premier ramassable de cette entrée sur la carte 0 qui n'est pas en attente de repousse."""
    rows = [r.split("\t") for r in sql(f"select guid, round(position_x,2), round(position_y,2), round(position_z,2) from classicmangos.gameobject "
                                       f"where id={entry} and map=0 and guid not in (select guid from classiccharacters.gameobject_respawn) order by guid limit 1")]
    g, x, y, z = rows[0]; return int(g), float(x), float(y), float(z)
s = Session(sys.argv[1], sys.argv[2]); login_char(s, sys.argv[3] if len(sys.argv) > 3 else 'Wlharvest')
ok = True
def say(c, t=0.8): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
def check(name, cond, detail=''):
    global ok; ok &= bool(cond); print(('[OK]   ' if cond else '[ÉCHEC]'), name, detail)
def count(name):
    m = re.search(r"(\d+) " + re.escape(name) + r"(,|$)", ' '.join(say('.build inv')).strip())
    return int(m.group(1)) if m else 0
def goto(nd):
    g_, x, y, z = nd
    s.teleport_cmd(f'.go xyz {x} {y} {z + 1} 0'); time.sleep(2.5); say('.revive'); time.sleep(1.0)
def equip(item_id):
    say(f'.additem {item_id} 1', 1.2); time.sleep(0.7); s.equip_item(item_id); time.sleep(1.0)

# données : aucun GameObject n'exige d'outil (les anciens nœuds WoW sont remplacés par les rochers/arbres créatures de Valheim)
check('aucun ramassable n\'exige d\'outil (wowlheim_node vide)', sql("select count(*) from classicmangos.wowlheim_node") == ['0'])
say('.revive'); say('.build nocost off')
for it in (9200001, 9200002, 9200003): say(f'.additem {it} -999', 0.4)
time.sleep(0.5)
equip(9201100)                                     # marteau en main : ni hache ni pioche, la cueillette se fait à la main

# entrée GameObject, objet donné, quantité (gameobject_loot_template issu de Pickable.m_itemPrefab / m_amount de Valheim)
for entry, prefab, item, name, amount in ((9130007, 'Pickable_Flint', 9200003, 'Silex', 1),
                                          (9130004, 'Pickable_Branch', 9200001, 'Bois', 1),
                                          (9130010, 'Pickable_Stone', 9200002, 'Pierre', 1)):
    nd = node(entry)
    print(prefab, nd)
    goto(nd)
    before = count(name)
    notes, items = s.use_gameobject(entry, nd[0]); time.sleep(1.0)
    after = count(name)
    check(f'{prefab} : ramassé à la main, {amount} {name} directement dans le sac ({before} -> {after}), sans fenêtre de butin',
          after == before + amount and not items and not notes, str(notes) + str(items))
    notes, items = s.use_gameobject(entry, nd[0]); time.sleep(1.0)
    check(f'{prefab} : une fois ramassé, il disparaît (plus rien avant repousse)', count(name) == after and not items, str(notes) + str(items))
s.close()
print('RÉSULTAT :', 'OK' if ok else 'ÉCHEC')
