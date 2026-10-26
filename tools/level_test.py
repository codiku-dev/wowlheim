"""Niveaux de station : le niveau d'une forge = 1 + extensions à moins de 5 m ; une recette exige un niveau minimum.
(docs/VALHEIM_RULES.md 8 ; niveaux de recettes = proposition de conception, docs 8.9.) python level_test.py <compte> <mdp>"""
import sys, time, re
from wlclient import Session, login_char, goto_test_spot

s = Session(sys.argv[1], sys.argv[2])
login_char(s, 'Wllevel')
goto_test_spot(s)
ok = True


def say(c, t=0.8):
    return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]


def check(name, cond, detail=''):
    global ok
    ok &= bool(cond)
    print(('[OK]   ' if cond else '[ÉCHEC]'), name, detail)


say('.build nocost on')
say('.build place Plancher 5 0 0 0')
for a in ('6 0 0 0', '4 0 0 0', '5 -1 0 90', '5 1 0 90')   # murs de Valheim : étendus le long de l'axe local Y:
    say('.build place Mur ' + a)
say('.build place Toit 5 0 2.0 0')
say('.build place Établi 5 -0.5 0.2 0')
r = ' '.join(say('.build place Forge 5 0.5 0.2 0'))
check('forge posée dans la cabane (avec établi à portée)', 'posée' in r, r)
time.sleep(2)
say('.build nocost off')
# ingrédients de la hache de fer (Recipe_AxeIron de Valheim : 4 Bois, 20 Fer, 2 Bouts de cuir ; forge niveau 2)
# + un soufflet de forge (forge_ext1 : 5 Bois, 5 Peau de cerf, 4 Chaîne)
for it, n in ((9200001, 9), (9200021, 20), (9200006, 2), (9200005, 5), (9200052, 4)):
    say(f'.additem {it} {n}', 0.5)
time.sleep(1)
r = ' '.join(say('.build recipes', 1.5))
check('les recettes affichent leur niveau minimum', 'niveau 2' in r and 'niveau 4' in r, r[:200])
r = ' '.join(say('.build craft 105'))
check('forge niveau 1 : la hache de fer (niveau 2) est refusée', 'insuffisant (1, il faut 2)' in r, r)
r = ' '.join(say('.build place Soufflet 20 0 0 0'))
check('extension loin de toute forge : refusée', 'station' in r and 'refusée' in r, r)
r = ' '.join(say('.build place Soufflet 5 0.5 0.2 0'))
check('soufflet de forge posé contre la forge (5 Bois, 5 Peau de cerf, 4 Chaîne)', 'posée' in r, r)
time.sleep(0.5)
r = ' '.join(say('.build craft 105'))
check('forge niveau 2 : la hache de fer est fabriquée', 'Fabriqué' in r, r)
# second soufflet + enclumes (forge_ext2 : 5 Bois, 2 Bronze) + hache d'argent (recette Wowlheim 107, niveau 3)
for it, n in ((9200001, 10), (9200005, 5), (9200052, 4), (9200015, 2), (9200012, 4), (9200031, 6), (9200033, 2), (9200034, 2)):
    say(f'.additem {it} {n}', 0.5)
time.sleep(1)
r = ' '.join(say('.build place Soufflet 5 0 0.2 0'))
check('un second soufflet (même type) se pose', 'posée' in r, r)
r = ' '.join(say('.build craft 107'))
check('deux soufflets = une seule extension comptée : niveau 2, la hache en argent (niveau 3) reste refusée', 'insuffisant (2, il faut 3)' in r, r)
r = ' '.join(say('.build place Enclume 5 1 0.2 0'))
check('une enclume (autre type extension) se pose', 'posée' in r, r)
r = ' '.join(say('.build craft 107'))
check('forge niveau 3 : la hache en argent est fabriquée', 'Fabriqué' in r, r)
s.close()
print('RÉSULTAT :', 'OK' if ok else 'ÉCHEC')
