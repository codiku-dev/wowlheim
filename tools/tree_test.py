"""Abattage façon Valheim (client de protocole, sans interface) : un hêtre (créature au modèle Valheim) ne prend que les coups
d'une hache ; à la hache en pierre il tombe (80 PV), laisse un tronc (60 PV) qui se fend en deux bûches (60 PV) donnant 10 Bois
chacune (TreeLog.m_dropWhenDestroyed de Valheim) ; un bouleau exige une hache de bronze (m_minToolTier 2 : « Trop dur »).
python tree_test.py <compte> <mdp>   (compte GM, serveur lancé)"""
import math, re, socket, struct, subprocess, sys, time
from wlclient import Session, login_char

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()

s = Session(sys.argv[1], sys.argv[2]); login_char(s, "Wlharvest")
ok = True
def check(name, cond, detail=""):
    global ok; ok &= bool(cond); print(("[OK]   " if cond else "[ÉCHEC]"), name, detail, flush=True)
def say(c, t=0.8): return [l for l in s.say(c, t) if "Welcome to" not in l and "Tickets" not in l]
def cguid(entry, low): return (0xF130 << 48) | (entry << 24) | low
def trees(r=30):
    out = []
    for l in say(f".build api trees {r}", 1.2):
        if l.startswith("[WL]T|"):
            f = l[6:].split("|")
            out.append({"low": int(f[0]), "entry": int(f[1]), "kind": f[2], "x": float(f[3]), "y": float(f[4]), "z": float(f[5]),
                        "alive": f[6] == "1", "hp": int(f[7])})
    return out
MAP = 0
def equip(item_id):
    say(f".additem {item_id} 1", 1.2); time.sleep(0.7); s.equip_item(item_id); time.sleep(1.0)
def stand_near(t, dist=1.6, side=0.0):
    a = side
    x, y = t["x"] + dist * math.cos(a), t["y"] + dist * math.sin(a)
    face = math.atan2(t["y"] - y, t["x"] - x) % (2 * math.pi)
    s.teleport_cmd(f".go xyz {x:.2f} {y:.2f} {t['z'] + 0.5:.2f} {MAP}"); time.sleep(1.0)
    # MSG_MOVE_SET_FACING : le client se tourne vers l'arbre (mouvement : drapeaux, temps, x, y, z, o, temps de chute)
    s.send(0x0DA, struct.pack("<II4fI", 0, int(time.time() * 1000) & 0xFFFFFFFF, x, y, t["z"] + 0.5, face, 0)); time.sleep(0.6)
def unpack_guid(d, i):
    mask = d[i]; i += 1; g = 0
    for b in range(8):
        if mask & (1 << b): g |= d[i] << (8 * b); i += 1
    return g, i
def chop(t, seconds):
    """Attaque automatique sur la créature ; renvoie (dégâts par coup, notifications)."""
    g = cguid(t["entry"], t["low"])
    s.send(0x13D, struct.pack("<Q", g))          # CMSG_SET_SELECTION
    s.send(0x141, struct.pack("<Q", g))          # CMSG_ATTACKSWING
    hits, notes, end = [], [], time.time() + seconds
    s.s.settimeout(0.5)
    while time.time() < end:
        try:
            op, d = s.read()
        except socket.timeout:
            continue
        if op == 0x14A:                          # SMSG_ATTACKERSTATEUPDATE
            _, i = unpack_guid(d, 4); tg, i = unpack_guid(d, i)
            if tg == g:
                hits.append(struct.unpack("<I", d[i:i + 4])[0])
        elif op == 0x1CB:
            notes.append(d.split(b"\0")[0].decode("utf-8", "replace"))
        elif op == 0x144 and hits and sum(hits) >= t["hp"]:   # SMSG_ATTACKSTOP après la mort
            break
    s.send(0x142)                                # CMSG_ATTACKSTOP
    return hits, notes
def loot(t):
    g = cguid(t["entry"], t["low"])
    s.send(0x15D, struct.pack("<Q", g))          # CMSG_LOOT
    items, end = [], time.time() + 2
    s.s.settimeout(0.5)
    while time.time() < end:
        try:
            op, d = s.read()
        except socket.timeout:
            continue
        if op == 0x160:
            n = d[8 + 1 + 4]; i = 8 + 1 + 4 + 1
            for _ in range(n):
                items.append((d[i], struct.unpack("<I", d[i + 1:i + 5])[0], struct.unpack("<I", d[i + 5:i + 9])[0])); i += 22
    for slot, it, c in items:
        s.autostore_loot(slot); time.sleep(0.3)
    s.send(0x15F, struct.pack("<Q", g))          # CMSG_LOOT_RELEASE
    return items

say(".revive"); say(".gm off"); say(".build nocost off")
for it in (9201010, 9201011, 9201021, 9201100, 9200001, 9200004): say(f".additem {it} -99")
beech = [r.split("\t") for r in sql("select guid, position_x, position_y, position_z from classicmangos.creature where id=9300001 and map=0 and guid not in (select guid from classiccharacters.creature_respawn) order by guid limit 1")][0]
tree = {"low": int(beech[0]), "entry": 9300001, "x": float(beech[1]), "y": float(beech[2]), "z": float(beech[3]), "hp": 80}
stand_near(tree)
near = [t for t in trees(6) if t["entry"] == 9300001 and t["alive"]]
check("un hêtre de Valheim est là (créature vivante, 80 PV)", near and near[0]["hp"] == 80, str(near))

equip(9201100)                                   # marteau : pas une hache
hits, notes = chop(tree, 6)
check("au marteau : aucun dégât, message « il faut une hache »", hits and max(hits) == 0 and any("hache" in n for n in notes), f"{hits} {notes}")

equip(9201010)                                   # hache en pierre (Valheim : chop 20, palier 0)
stand_near(tree)
hits, notes = chop(tree, 60)
print("coups sur le hêtre :", hits)
check("hache en pierre : dégâts de coupe Valheim (20 x [0,25 ; 0,55] => 5 à 11)", hits and all(5 <= h <= 11 for h in hits), str(hits))
time.sleep(3.5)
around = trees(25)
logs = [t for t in around if t["kind"] == "log" and t["alive"]]
check("le hêtre abattu laisse un tronc (beech_log, 60 PV)", logs and logs[0]["hp"] == 60, str(around))
if logs:
    lg = logs[0]; lg["hp"] = 60
    stand_near(lg, 1.4, math.atan2(lg["y"] - tree["y"], lg["x"] - tree["x"]) + math.pi / 2)
    hits, notes = chop(lg, 50)
    print("coups sur le tronc :", hits)
    time.sleep(1.5)
    halves = [t for t in trees(25) if t["kind"] == "half" and t["alive"]]
    check("le tronc se fend en deux bûches", len(halves) == 2, str(halves))
    wood = 0
    for h in halves:
        h["hp"] = 60
        stand_near(h, 1.4, math.atan2(lg["y"] - tree["y"], lg["x"] - tree["x"]) + math.pi / 2)
        hits, notes = chop(h, 50)
        time.sleep(1.0)
        items = loot(h)
        print("butin de la bûche :", items)
        wood += sum(c for _, it, c in items if it == 9200001)
    check("deux bûches => 20 Bois (10 chacune, comme dans Valheim)", wood == 20, str(wood))
    time.sleep(0.8)
    inv = " ".join(say(".build inv"))
    check("Bois dans le sac", "Bois" in inv, inv)

birch = sql("select guid, position_x, position_y, position_z from classicmangos.creature where id=9300010 and map=0 and guid not in (select guid from classiccharacters.creature_respawn) order by guid limit 1")
if birch:
    b = birch[0].split("\t")
    bt = {"low": int(b[0]), "entry": 9300010, "x": float(b[1]), "y": float(b[2]), "z": float(b[3]), "hp": 80}
    stand_near(bt)
    hits, notes = chop(bt, 6)
    check("bouleau à la hache en pierre : « Trop dur » (palier 2 requis)", hits and max(hits) == 0 and any("dur" in n.lower() for n in notes), f"{hits} {notes}")
# minage façon Valheim : MineRock_Stone (24 zones de 20 PV, 1-2 Pierre par zone), pioche seulement
rock = sql("select guid, position_x, position_y, position_z from classicmangos.creature where id=9300104 and map=0 and guid not in (select guid from classiccharacters.creature_respawn) order by guid limit 1")
if rock:
    r_ = rock[0].split("\t")
    rt = {"low": int(r_[0]), "entry": 9300104, "x": float(r_[1]), "y": float(r_[2]), "z": float(r_[3]), "hp": 160}
    say(".additem 9200002 -999")
    equip(9201010)
    stand_near(rt, 2.2)
    hits, notes = chop(rt, 5)
    check("rocher à la hache : aucun dégât, « Il faut une pioche »", hits and max(hits) == 0 and any("pioche" in n for n in notes), f"{hits} {notes}")
    equip(9201012)                                # pioche en bois de cerf (Valheim : m_pickaxe 18, palier 0)
    stand_near(rt, 2.2)
    hits, notes = chop(rt, 150)
    print("coups sur le rocher :", len(hits), hits[:8])
    time.sleep(2)
    inv = " ".join(say(".build inv"))
    m = re.search(r"(\d+) Pierre", inv)
    check("rocher brisé à la pioche : 24 à 48 Pierre (DropTable de Valheim, 24 zones)", m and 24 <= int(m.group(1)) <= 48, inv)
s.close()
print("RÉSULTAT :", "OK" if ok else "ÉCHEC")
