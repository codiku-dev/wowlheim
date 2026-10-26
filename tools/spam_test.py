import sys
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
for i in range(int(sys.argv[3])):
    r = s.say(sys.argv[4], 0.05)
    if i % 50 == 0: print(i, len(r), flush=True)
s.close(); print('terminé sans crash')
