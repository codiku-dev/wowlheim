import sys, time, struct, socket
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
def say(c, t=1.0): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
say('.additem 9201012 -9'); say('.additem 9201012 1', 1.5)
print('pushes', getattr(s, 'pushes', None))
bag, slot = s.pushes.get(9201012, (255, 23))
s.send(0x10A, bytes([bag, slot]))
end = time.time() + 2; s.s.settimeout(0.5)
while time.time() < end:
    try: op, d = s.read()
    except socket.timeout: continue
    print(hex(op), d[:24].hex())
s.close()
