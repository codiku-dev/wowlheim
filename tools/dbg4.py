import sys
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
for c in ('.revive', '.cheat god on', '.cheat god'):
    print(c, [l for l in s.say(c, 1.0) if 'Welcome to' not in l and 'Tickets' not in l])
s.close()
