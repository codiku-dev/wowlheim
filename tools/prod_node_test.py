"""Ressources de production : charge du serveur avec tout le monde peuplé d'objets de Valheim (arbres, rochers, filons =
créatures 9300001-9300199 ; ramassables = GameObjects 9130001+, 012_valheim_content.sql, aux positions de placements.json),
puis présence en jeu, sur l'autre continent (Kalimdor, carte 1), d'un sapin et d'un rocher de production vivants
(.build api trees ; l'abattage/minage lui-même est testé par tree_test.py, la cueillette par harvest_test.py).
python prod_node_test.py <compte> <mdp>"""
import json, os, re, subprocess, sys, time
from wlclient import Session, login_char
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources"))
import rules as RES_RULES

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"


def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()


s = Session(sys.argv[1], sys.argv[2])
login_char(s, 'Wlprod')
ok = True


def say(c, t=0.8):
    return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]


def check(name, cond, detail=''):
    global ok
    ok &= bool(cond)
    print(('[OK]   ' if cond else '[ÉCHEC]'), name, detail)


creatures = int(sql("select count(*) from classicmangos.creature where id between 9300001 and 9300199")[0])
picks = int(sql("select count(*) from classicmangos.gameobject where id between 9130001 and 9130099")[0])
maps = sql("select distinct map from classicmangos.creature where id between 9300001 and 9300199 order by map")
# attendu = placements.json (tools/resources/place_resources.py), seule source des positions de 012_valheim_content.sql :
# chaque placement de type « creature » (arbre, roche, filon) ou « pickable » de rules.PLACEMENTS est une ligne en base
_kinds = {pl["key"]: pl["kind"] for pl in RES_RULES.PLACEMENTS}
_items = json.load(open(RES_RULES.PLACEMENTS_JSON, encoding="utf-8"))["items"]
want_creatures = sum(1 for it in _items if _kinds[it["kind"]] == "creature")
want_picks = sum(1 for it in _items if _kinds[it["kind"]] == "pickable")
check('ressources en base = placements.json : arbres et rochers de Valheim (créatures) + ramassables (GameObjects)',
      creatures == want_creatures and picks == want_picks and maps == ['0', '1'],
      f"{creatures}/{want_creatures} créatures + {picks}/{want_picks} ramassables, cartes {maps}")
time.sleep(30)                      # laisse la fenêtre de mesure du tick se remplir
perf = ' '.join(say('.build perf'))
# le monde tourne à 50 ms par tick (moyenne 50/51 ms à vide) ; tolérance 60 ms : une autre charge de la machine (build en parallèle,
# 61 ms mesurés) n'est pas une régression du serveur ; au-delà, ou sans mesure, c'est un échec. Le max est affiché, pas jugé.
m = re.search(r'moyenne (\d+) ms', perf)
check('diff tick moyen avec toutes les ressources en base (<= 60 ms, nominal 50)', m and int(m.group(1)) <= 60, perf)

# un sapin et un rocher (MineRock_Stone) de production, vivants en jeu sur Kalimdor
say('.revive')
for entry, name in ((9300004, 'sapin'), (9300104, 'rocher')):
    g, x, y, z = sql(f"select guid, round(position_x,2), round(position_y,2), round(position_z,2) from classicmangos.creature where id={entry} and map=1 "
                     "and guid not in (select guid from classiccharacters.creature_respawn) order by guid limit 1")[0].split("\t")
    print(name, '(carte 1)', g, x, y, z)
    s.teleport_cmd(f'.go xyz {float(x) + 2.5} {y} {float(z) + 1} 1')
    time.sleep(3.0)
    near = [l for l in say('.build api trees 8', 1.5) if l.startswith('[WL]T|')]
    mine = [l for l in near if l.split('|')[1] == g]
    f = mine[0][6:].split('|') if mine else []
    check(f'{name} de production (Kalimdor) chargé en jeu, vivant', f and int(f[1]) == entry and f[6] == '1', str(near[:4]))
s.close()
print('RÉSULTAT :', 'OK' if ok else 'ÉCHEC')
