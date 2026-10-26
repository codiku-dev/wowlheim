import sys, time
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
def say(c, t=1.0): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
print(say('.revive')); print(say('.gps')[:2])
print('add257', say('.npc add 257', 1.5))
print('add299', say('.npc add 299', 1.5))
s.close()
