"""Coûts, consommation, remboursement, établi requis. python cost_test.py <compte> <mdp>  (GM : .additem pour donner les ressources de départ)"""
import sys, time, re
from wlclient import Session, login_char, goto_test_spot
s = Session(sys.argv[1], sys.argv[2]); login_char(s, 'Wlcost'); goto_test_spot(s)
ok = True
def say(c, t=0.8): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
def check(name, cond, detail=''):
    global ok; ok &= bool(cond); print(('[OK]   ' if cond else '[ÉCHEC]'), name, detail)
def have(item_name_part):
    r = ' '.join(say('.build inv', 0.8))
    m = re.search(r'(\d+) ' + item_name_part, r); return (int(m[1]) if m else 0), r
say('.build nocost off'); say('.build grace 0'); say('.additem 9200001 -9999'); time.sleep(0.5)
r = say('.build list'); print('\n'.join(r[:9]))
r = ' '.join(say('.build place Établi 6 -4 0 0'))   # la table de fabrication n'exige aucune station
check('sans ressources : pose refusée avec le décompte', 'Ressources manquantes' in r and 'Bois' in r, r)
# Valheim : le plancher exige une table de fabrication à portée (Piece.m_craftingStation) -> l'établi d'abord (10 Bois)
say('.additem 9200001 14'); time.sleep(0.5)
a, r = have('Bois'); check('après .additem : 14 Bois', a == 14, r)
r = ' '.join(say('.build place Établi 6 -4 0 0')); check('établi posé (10 Bois, coût de Valheim)', 'posée' in r, r)
a, r = have('Bois'); check("après l'établi : 4 Bois", a == 4, r)
r1 = ' '.join(say('.build place Plancher 3 0 0 0')); r2 = ' '.join(say('.build place Plancher 3 2.5 0 0'))
check('deux planchers posés (2 Bois chacun, coût de Valheim)', 'posée' in r1 and 'posée' in r2, r1 + ' | ' + r2)
a, r = have('Bois'); check('consommation : 4 − 2×2 = 0 Bois', a == 0, r)
r = ' '.join(say('.build remove')); check('démolition : ressources rendues', 'Ressources rendues' in r, r)
a, r = have('Bois'); check('remboursement complet : 0 + 2 = 2 Bois', a == 2, r)
r = ' '.join(say('.build place Forge 3 4 0 0')); check('forge : il faut les matériaux (pierre + cuivre)', 'manquantes' in r or 'établi' in r, r)
print(' | '.join(say('.build recipes')[:4]))
s.close()
print('RÉSULTAT :', 'OK' if ok else 'ÉCHEC')
