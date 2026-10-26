import sys, time
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
for c in sys.argv[3:]:
    for l in s.say(c, 1.5):
        if 'Welcome to' in l or 'Tickets' in l: continue
        print(c, '->', l)
s.close()
