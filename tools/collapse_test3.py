import sys, time
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
def say(c, t=0.8, show=True):
    r = [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
    if show:
        for l in r: print(c, '->', l)
    return r
say('.build count')
print('--- C : pièce flottante (8 m de haut, 4 m à droite) ---')
say('.build place Plancher 3 4 8'); say('.build count'); time.sleep(3); say('.build count')
print('--- B : démolition de la base de la colonne ---')
say('.build remove')
time.sleep(1.2); say('.build count')
time.sleep(3); say('.build count'); say('.build stats')
s.close()
