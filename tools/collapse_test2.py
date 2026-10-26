import sys, time
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
def say(c, t=0.6, show=True):
    r = [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
    if show:
        for l in r: print(c, '->', l)
    return r
for k in range(10):
    say(f'.build place Poteau 3 0 {k*2}', 0.4, False)
say('.build dump 12', 1.0)
time.sleep(3)
say('.build dump 12', 1.0)
say('.build count')
s.close()
