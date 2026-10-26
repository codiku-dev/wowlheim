import sys, time, re
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
def say(c, t=0.15): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
say('.build nocost on'); say('.build grace 1')
fails = 0
for i in range(int(sys.argv[3])):
    r = say('.build place Plancher 3 %d 0' % (-20 + (i % 10) * 2))
    r2 = say('.build place Plancher 3 %d 9' % (-20 + (i % 10) * 2))     # flottante : doit s'effondrer
    if i % 3 == 0: say('.build remove')
    if i % 25 == 0: print(i, say('.build count', 0.3)[:1])
time.sleep(4); print('fin', say('.build count', 0.5))
s.close()
