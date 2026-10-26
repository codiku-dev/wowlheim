"""Butin de mobs : fait apparaître N créatures (GM .npc add, nettoyées ensuite), les tue, les pille, compte les matériaux Wowlheim.
python loot_test.py <compte> <mdp> <entrée_créature> <N>"""
import subprocess, sys, time, struct, collections
from wlclient import Session
MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "--default-character-set=utf8mb4", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()
entry, N = int(sys.argv[3]), int(sys.argv[4])
s = Session(sys.argv[1], sys.argv[2]); g, n = s.chars()[0]; s.login(g)
def say(c, t=0.5): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
say('.revive')
name = sql(f"select name, minlevel, maxlevel, CreatureType, Family from classicmangos.creature_template where entry={entry}")[0]
print('créature', entry, name)
tally = collections.Counter(); kills = 0
for i in range(N):
    say('.revive'); say(f'.npc add {entry}', 0.6)
    low = int(sql(f"select max(guid) from classicmangos.creature where id={entry}")[0])
    guid = (0xF130 << 48) | (entry << 24) | low
    time.sleep(0.5)
    s.send(0x13D, struct.pack("<Q", guid))              # CMSG_SET_SELECTION
    say('.die', 0.6)
    s.send(0x15D, struct.pack("<Q", guid))              # CMSG_LOOT
    end = time.time() + 1.2; s.s.settimeout(0.4); items = []
    import socket
    while time.time() < end:
        try: op, d = s.read()
        except socket.timeout: continue
        if op == 0x160 and len(d) > 14:
            c = d[13]; j = 14
            for _ in range(c):
                items.append((d[j], struct.unpack("<I", d[j+1:j+5])[0], struct.unpack("<I", d[j+5:j+9])[0])); j += 22
    for slot, item, cnt in items:
        if 9200000 <= item < 9300000: tally[item] += cnt
        s.autostore_loot(slot); time.sleep(0.15)
    s.send(0x15F, struct.pack("<Q", guid))              # CMSG_LOOT_RELEASE
    say('.npc delete', 0.4)
    kills += 1
names = {r.split("\t")[0]: r.split("\t")[1] for r in sql("select entry, name from classicmangos.item_template where entry between 9200000 and 9299999")}
print(f'{kills} morts ; matériaux Wowlheim reçus :')
for item, c in sorted(tally.items()): print(f'  {names.get(str(item), item)} : {c}')
print('inventaire serveur :', say('.build inv')[:1])
s.close()
sql(f"delete from classicmangos.creature where id={entry} and guid>=5000000 and 1=0")
