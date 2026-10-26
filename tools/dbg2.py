import sys, time, struct, socket
from wlclient import Session
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
def say(c, t=1.0): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
print('tp', s.teleport_cmd('.go xyz -6121.88 546.37 406.5 0')); time.sleep(2)
print(say('.gobject near 30'))
low = 9500001; entry = 9101001
s.send(0x1B1, struct.pack("<Q", (0xF110 << 48) | (entry << 24) | low))
end = time.time() + 3; s.s.settimeout(0.5)
while time.time() < end:
    try: op, d = s.read()
    except socket.timeout: continue
    print(hex(op), d[:40].hex())
s.close()
