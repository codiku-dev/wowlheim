import sys, time
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
def say(c, t=1.5):
    r = s.say(c, t)
    for l in r[2:] if len(r) > 2 else r: print(c, '->', l)
    return r
say('.build count')
# Test A : colonne de 10 poteaux empilés (pas de 2 m). Valheim bois : 100 * 0.7375^k < 10 pour k >= 8
for k in range(10):
    say(f'.build place Poteau 3 0 {k*2}', 0.6)
say('.build count')
time.sleep(4)
say('.build count')
say('.build stats')
s.close()
