import sys, time
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
def say(c, t=1.0): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
print(say('.gps'))
print('tp', s.teleport_cmd('.go xyz -6121.88 546.37 406.5 0'))
print(say('.gps'))
s.close()
