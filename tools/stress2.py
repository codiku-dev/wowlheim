import sys, time
from wlclient import Session
mode = sys.argv[3]; n = int(sys.argv[4])
s = Session(sys.argv[1], sys.argv[2]); g, nm = s.chars()[0]; s.login(g)
def say(c, t=0.25): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
say('.build nocost on'); say('.build grace 0')
for i in range(n):
    x = -20 + (i % 10) * 2; yy = (i // 10) * 2
    if mode == 'ground':        # pose au sol + démolition, pas d'effondrement
        say('.build place Plancher %d %d 0' % (3 + yy, x)); say('.build remove')
    elif mode == 'float':       # pièce flottante qui s'effondre toute seule
        say('.build place Plancher %d %d 9' % (3 + yy, x))
    elif mode == 'place':       # seulement des poses au sol
        say('.build place Plancher %d %d 0' % (3 + yy, x))
    if i % 20 == 0: print(mode, i, flush=True)
time.sleep(3); print('fin', mode, say('.build count', 0.5)); s.close()
