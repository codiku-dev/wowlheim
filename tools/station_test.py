"""Critère phase 3/4 : un établi n'est utilisable qu'à l'abri (toit + couverture >= 70 %). python station_test.py <compte> <mdp>"""
import sys, time, re
from wlclient import Session, login_char, goto_test_spot
s = Session(sys.argv[1], sys.argv[2]); login_char(s, 'Wlstation'); goto_test_spot(s)
ok = True
def say(c, t=0.7): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
def check(name, cond, detail=''):
    global ok; ok &= bool(cond); print(('[OK]   ' if cond else '[ÉCHEC]'), name, detail)
say('.build nocost on'); say('.build grace 0')
# cabane : plancher, 4 murs, toit, établi à l'intérieur
say('.build place Plancher 5 0 0 0')
# murs de Valheim : étendus le long de l'axe local Y
for args in ('6 0 0 0', '4 0 0 0', '5 -1 0 90', '5 1 0 90'): say('.build place Mur ' + args)
say('.build place Toit 5 0 2.0 0')
say('.build place Établi 5 0 0.2 0')
time.sleep(3)
r = say('.build station')
print(r)
m = re.search(r'couverture (\d+) %', ' '.join(r))
check('établi dans une cabane fermée : utilisable', any('utilisable (à l' in l for l in r), ' '.join(r))
def pieces():
    out = []
    for l in say('.build dump 60', 1.2):
        m = re.match(r'(\d+) modèle (\d+) ', l)
        if m: out.append((int(m[1]), int(m[2])))
    return out
def cover():
    r = say('.build station'); m = re.search(r'couverture (\d+) %', ' '.join(r)); return (int(m[1]) if m else None), ' '.join(r)
walls = [g for g, mo in pieces() if mo == 2]; roof = [g for g, mo in pieces() if mo == 3]
say(f'.build removeid {walls[0]}'); time.sleep(2)
pct, txt = cover(); print('un mur retiré :', txt)
check('un mur en moins : couverture réduite mais toit présent', pct is not None and pct < 100, txt)
say(f'.build removeid {roof[0]}'); time.sleep(2)
pct, txt = cover(); print('toit retiré :', txt)
check('sans toit : établi inutilisable', 'inutilisable' in txt, txt)
s.close()
print('RÉSULTAT :', 'OK' if ok else 'ÉCHEC')
