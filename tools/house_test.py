"""CRITÈRE PHASE 4 : construire une maison complète UNIQUEMENT avec du butin de mobs, impossible en ville.
Aucun .additem : les matériaux viennent de la mort de kobolds (GM : .npc add / .die pour les faire apparaître et mourir ; le butin
est tiré et attribué par le serveur). python house_test.py <compte> <mdp>"""
import collections, socket, struct, subprocess, sys, time, re
from wlclient import Session
MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "--default-character-set=utf8mb4", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()
s = Session(sys.argv[1], sys.argv[2])
chars = {nm: gg for gg, nm in s.chars()}
if 'Wlhouse' not in chars:
    print('création du personnage Wlhouse (sac vide) ->', hex(s.create('Wlhouse')))
    chars = {nm: gg for gg, nm in s.chars()}
g = chars['Wlhouse']; s.login(g)
ok = True
def say(c, t=0.6): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
def check(name, cond, detail=''):
    global ok; ok &= bool(cond); print(('[OK]   ' if cond else '[ÉCHEC]'), name, detail)
def wood():
    m = re.search(r'(\d+) Bois', ' '.join(say('.build inv', 0.8))); return int(m[1]) if m else 0
def kill_and_loot(entry):
    say('.revive'); say(f'.npc add {entry}', 0.6)
    low = int(sql(f"select max(guid) from classicmangos.creature where id={entry}")[0]); guid = (0xF130 << 48) | (entry << 24) | low
    time.sleep(0.4); s.send(0x13D, struct.pack("<Q", guid)); say('.die', 0.5); s.send(0x15D, struct.pack("<Q", guid))
    end = time.time() + 1.0; s.s.settimeout(0.4); items = []
    while time.time() < end:
        try: op, d = s.read()
        except socket.timeout: continue
        if op == 0x160 and len(d) > 14:
            for k in range(d[13]):
                j = 14 + 22 * k; iid = struct.unpack('<I', d[j+1:j+5])[0]
                if 9200000 <= iid < 9300000: items.append(d[j])     # on ne ramasse que les matériaux Wowlheim (le reste encombre le sac)
    for slot in items: s.autostore_loot(slot); time.sleep(0.12)
    s.send(0x15F, struct.pack("<Q", guid)); say('.npc delete', 0.4)

# état propre : plus d'objets Wowlheim, pas de coût neutralisé, grace par défaut
say('.revive'); say('.build nocost off'); say('.build grace 0')
s.teleport_cmd('.go xyz -6180 745 400 0'); time.sleep(3); say('.revive')
for it in range(9200001, 9200007): say(f'.additem {it} -999', 0.2)
time.sleep(0.5)
print('inventaire de départ :', say('.build inv')[0])
NEED = 2 + 4 * 2 + 2 + 10          # plancher + 4 murs + toit + établi = 22 Bois
kills = 0
while wood() < NEED and kills < 150:
    for _ in range(10): kill_and_loot(257); kills += 1
    print(f'  {kills} mobs tués, Bois = {wood()}', flush=True)
check(f'butin suffisant ({NEED} Bois) obtenu en {kills} morts de kobolds', wood() >= NEED, str(wood()))
print('inventaire :', say('.build inv')[0])
# construction : maison complète hors ville
before = int(re.search(r'(\d+) au total', ' '.join(say('.build count'))).group(1))
results = []
def place(args):
    r = ' '.join(say('.build place ' + args, 0.7)); results.append(r); return 'posée' in r
# Valheim : plancher, murs et toit exigent une table de fabrication à portée -> l'établi d'abord ; murs étendus le long de l'axe local Y
okp = all([place('Établi 5 0 0.2 0'), place('Plancher 5 0 0 0'), place('Mur 6 0 0 0'), place('Mur 4 0 0 0'), place('Mur 5 -1 0 90'), place('Mur 5 1 0 90'), place('Toit 5 0 2.0 0')])
check('maison complète posée (plancher, 4 murs, toit, établi) avec des ressources lootées', okp, ' | '.join(results))
time.sleep(5)
after = int(re.search(r'(\d+) au total', ' '.join(say('.build count'))).group(1)); check('la maison tient debout (+7 pièces, aucune effondrée après 5 s)', after - before == 7, f'{before} -> {after}')
st = ' '.join(say('.build station')); check('établi à l\'abri : utilisable', 'utilisable (à l' in st, st)
# en ville : impossible même avec des ressources
for obj in (9200001,): say(f'.additem {obj} 20', 0.4)
s.teleport('Stormwind'); time.sleep(2.5); say('.revive')
r = ' '.join(say('.build place Plancher 3 0 0 0')); check('Stormwind : construction impossible (ressources en poche)', 'refusée' in r and 'ville' in r or 'village' in r, r)
s.teleport('Orgrimmar'); time.sleep(2.5); say('.revive')
r = ' '.join(say('.build place Plancher 3 0 0 0')); check('Orgrimmar : construction impossible', 'refusée' in r, r)
s.close()
print('RÉSULTAT :', 'OK' if ok else 'ÉCHEC')
