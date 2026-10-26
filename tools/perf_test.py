import sys, time
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
def say(c): 
    for l in s.say(c, 2): print(c, '->', l)
time.sleep(35); say('.build perf')
for k in range(int(sys.argv[3])):
    say('.build bulk Plancher 1000')
    time.sleep(35); say('.build perf'); say('.build near 100')
s.close()
