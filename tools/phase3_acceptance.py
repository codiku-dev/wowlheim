"""Critère phase 3 : (1) une structure sans support s'effondre ; (2) une pièce sans toit se dégrade sous la pluie, une pièce couverte non.
Prérequis : serveur lancé, compte de test. python phase3_acceptance.py <compte> <mdp>"""
import sys, time, re
from wlclient import Session, login_char, goto_test_spot
s = Session(sys.argv[1], sys.argv[2]); login_char(s, 'Wlphase'); goto_test_spot(s)
ok = True
def say(c, t=0.8):
    return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
def count():
    return int(re.search(r'(\d+) au total', say('.build count')[0]).group(1))
def check(name, cond, detail=''):
    global ok; ok &= bool(cond); print(('[OK]   ' if cond else '[ÉCHEC]'), name, detail)
def dump():
    out = {}
    for l in say('.build dump 50', 1.2):
        m = re.match(r'(\d+) modèle (\d+) z=([\d.-]+) support=([\d.]+) ancrée=(\w+) PV=(\d+)', l)
        if m: out[int(m[1])] = dict(model=int(m[2]), z=float(m[3]), support=float(m[4]), grounded=m[5] == 'oui', hp=int(m[6]))
    return out
say('.build nocost on'); say('.build grace 0'); say('.build rain 2')
base = count(); check('départ sans pièce', base == 0, f'({base})')
# 1a. colonne de 10 poteaux : Valheim bois => support 100*0,7375^k, seuil min 10 => 8 survivants attendus
for k in range(10): say(f'.build place Poteau 3 0 {k*2}', 0.3)
time.sleep(5)
d = dump(); check('colonne de 10 poteaux : 8 survivants (support ≥ 10)', len(d) == 8, f'({len(d)})')
if d:
    sup = sorted((v['support'] for v in d.values()), reverse=True)
    check('supports décroissants ~100, 73.8, 54.4…', abs(sup[0]-100) < 0.5 and abs(sup[1]-73.75) < 0.5 and sup[-1] >= 10, str([round(x,1) for x in sup]))
# 1b. pièce flottante
say('.build place Plancher 3 6 9'); time.sleep(4)
check('pièce flottante effondrée', count() == 8, f'({count()})')
# 1c. cascade : démolir la base
say('.build remove'); time.sleep(3)
check('démolition de la base : toute la colonne tombe', count() == 0, f'({count()})')
# 2. pluie
say('.wchange 1 1')
say('.build place Plancher 3 0 0'); say('.build place Poteau 3 5 0'); say('.build place Plancher 3 5 2.1')
time.sleep(14)
d = dump(); byz = sorted(d.values(), key=lambda v: (v['model'], v['z']))
exposed = [v for v in d.values() if v['model'] == 1]; pillar = [v for v in d.values() if v['model'] == 4]
check('planchers exposés usés sous la pluie, plafonnés à 50 % de PV max (sol en bois de Valheim : 400 PV -> 200)', exposed and all(v['hp'] <= 300 and v['hp'] >= 200 for v in exposed), str([v['hp'] for v in exposed]))
check('pilier couvert beaucoup moins usé que les exposés (max 1 coup avant évaluation du toit)', pillar and pillar[0]['hp'] >= 380, str([v['hp'] for v in pillar]))
print('RÉSULTAT :', 'TOUT OK' if ok else 'ÉCHECS')
s.close()
