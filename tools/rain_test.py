import sys, time
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
def say(c, t=0.8, show=True):
    r = [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
    if show:
        for l in r: print(c, '->', l)
    return r
say('.build rain 2')
say('.wchange 1 1')
say('.build place Plancher 3 0 0')        # A : exposé
say('.build place Poteau 3 5 0')          # B : pilier couvert
say('.build place Plancher 3 5 2.1')      # C : toit au-dessus de B (exposé lui-même)
for i in range(4):
    time.sleep(5)
    say('.build dump 10', 1.0)
    print('---')
s.close()
