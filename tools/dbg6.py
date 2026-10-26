import sys, time, struct, socket
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
def say(c, t=1.0): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
say('.revive')
print(say('.npc add 299', 1.5))
print(say('.npc info', 1.0))
s.close()
