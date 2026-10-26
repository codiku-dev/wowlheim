"""Fabrication à l'établi : l'établi doit être à portée et à l'abri. python craft_test.py <compte> <mdp>"""
import sys, time, re
from wlclient import Session, login_char
s = Session(sys.argv[1], sys.argv[2]); login_char(s, 'Wlcraft')
ok = True
def say(c, t=0.8): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
def check(name, cond, detail=''):
    global ok; ok &= bool(cond); print(('[OK]   ' if cond else '[ÉCHEC]'), name, detail)
def inv(): return ' '.join(say('.build inv'))
# recette 101 = Recipe_AxeFlint de Valheim : 4 Bois + 6 Silex à la table de fabrication
say('.revive'); s.teleport_cmd('.go xyz -6240 770 400 0'); time.sleep(3); say('.revive')   # vallée de Coldridge, hors village
say('.build nocost on'); say('.build grace 0')
r = ' '.join(say('.build place Plancher 5 0 0 0')); print(r)
# murs de Valheim : étendus le long de l'axe local Y
for a in ('6 0 0 0', '4 0 0 0', '5 -1 0 90', '5 1 0 90'): say('.build place Mur ' + a)
say('.build place Toit 5 0 2.0 0'); r = ' '.join(say('.build place Établi 5 0 0.2 0')); print(r)
time.sleep(3)
say('.build nocost off')
for it, n_ in ((9200001, 4), (9200003, 6)): say(f'.additem {it} -99'); 
for it, n_ in ((9200001, 4), (9200003, 6)): say(f'.additem {it} {n_}')
time.sleep(0.8); print(inv())
r = ' '.join(say('.build craft 101')); check('abrité + ingrédients : fabrication réussie', 'Fabriqué' in r, r)
r = inv(); check('Hache en silex dans le sac, ingrédients consommés', 'Hache en silex' in r and 'Bois' not in r, r)
r = ' '.join(say('.build craft 101')); check('sans ingrédients : refusé', 'manquantes' in r, r)
# toit retiré -> établi exposé -> fabrication refusée même avec les ingrédients
dump = say('.build dump 80', 1.5); roofs = [int(re.match(r'(\d+) modèle 3 ', l)[1]) for l in dump if re.match(r'(\d+) modèle 3 ', l)]
say(f'.build removeid {roofs[-1]}'); time.sleep(2)
for it, n_ in ((9200001, 4), (9200003, 6)): say(f'.additem {it} {n_}')
time.sleep(0.8)
r = ' '.join(say('.build craft 101')); check('établi exposé : fabrication refusée', 'exposé' in r, r)
s.close()
print('RÉSULTAT :', 'OK' if ok else 'ÉCHEC')
