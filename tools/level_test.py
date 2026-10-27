"""Niveaux de station : le niveau d'une forge = 1 + extensions à moins de 5 m ; une recette exige un niveau minimum.
(docs/VALHEIM_RULES.md 8 ; niveaux de recettes = Recipe.m_minStationLevel de Valheim, table wowlheim_recipe.)
Hache en fer (105, Recipe_AxeIron : forge niveau 2), Hache en sombracier (109, Recipe_AxeBlackMetal : forge niveau 4) ;
extensions de forge de Valheim : Soufflet de forge (forge_ext1), Enclumes (forge_ext2), Meule (forge_ext3).
python level_test.py <compte> <mdp>"""
import sys, time, re
from wlclient import Session, login_char, goto_test_spot

s = Session(sys.argv[1], sys.argv[2])
login_char(s, 'Wlcraft')
goto_test_spot(s)
ok = True


def say(c, t=0.8):
    return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]


def check(name, cond, detail=''):
    global ok
    ok &= bool(cond)
    print(('[OK]   ' if cond else '[ÉCHEC]'), name, detail)


# sac vidé des matériaux Wowlheim des tests précédents + sacs de voyage (beaucoup de matériaux différents ici)
for it in (9200001, 9200002, 9200003, 9200005, 9200006, 9200012, 9200013, 9200015, 9200021, 9200031, 9200033, 9200034, 9200052, 9200011, 9200014, 9200041, 9200043, 9200056, 9201011):
    say(f'.additem {it} -999', 0.3)
for _ in range(2):
    say('.additem 4500 1', 0.8); time.sleep(0.4); s.equip_item(4500); time.sleep(0.6)
say('.build nocost on')
say('.build place Plancher 5 0 0 0')
# murs de Valheim : étendus le long de l'axe local Y
for a in ('6 0 0 0', '4 0 0 0', '5 -1 0 90', '5 1 0 90'):
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
# second soufflet + enclumes (forge_ext2 : 5 Bois, 2 Bronze) + meule (forge_ext3 : 25 Bois, 1 Roue à aiguiser)
# + hache en sombracier (Recipe_AxeBlackMetal : 6 Bois précieux, 20 Sombracier, 5 Toile de lin ; forge niveau 4)
for it, n in ((9200001, 35), (9200005, 5), (9200052, 4), (9200015, 2), (9200056, 1), (9200011, 6), (9200041, 20), (9200043, 5)):
    say(f'.additem {it} {n}', 0.5)
time.sleep(1)
r = ' '.join(say('.build place Soufflet 5 0 0.2 0'))
check('un second soufflet (même type) se pose', 'posée' in r, r)
r = ' '.join(say('.build craft 109'))
check('deux soufflets = une seule extension comptée : niveau 2, la hache en sombracier (niveau 4) reste refusée', 'insuffisant (2, il faut 4)' in r, r)
r = ' '.join(say('.build place Enclumes 5 1 0.2 0'))
check("des enclumes (autre type d'extension) se posent", 'posée' in r, r)
r = ' '.join(say('.build craft 109'))
check('forge niveau 3 : la hache en sombracier reste refusée', 'insuffisant (3, il faut 4)' in r, r)
r = ' '.join(say('.build place Meule 4.5 0.5 0.2 0'))
check("une meule (troisième type d'extension) se pose", 'posée' in r, r)
time.sleep(0.5)
r = ' '.join(say('.build craft 109'))
check('forge niveau 4 : la hache en sombracier est fabriquée', 'Fabriqué' in r, r)
s.close()
print('RÉSULTAT :', 'OK' if ok else 'ÉCHEC')
