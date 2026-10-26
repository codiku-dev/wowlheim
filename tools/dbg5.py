import sys, time, struct, socket
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
def say(c, t=1.0): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
say('.revive')
say('.additem 9201012 1', 1.2); print('pushes', s.pushes)
s.equip_item(9201012); time.sleep(1)
print(s.teleport_cmd('.go xyz -6081.62 -382.52 436.3 0')); time.sleep(1.5); say('.revive')
print(say('.gobject near 20'))
s.send(0x0B1, struct.pack("<Q", (0xF110 << 48) | (9101011 << 24) | 9500015))
end = time.time() + 3; s.s.settimeout(0.5)
while time.time() < end:
    try: op, d = s.read()
    except socket.timeout: continue
    print(hex(op), len(d), d[:30].hex())
s.close()
