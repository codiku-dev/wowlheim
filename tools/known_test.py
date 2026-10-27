"""Connaissances façon Valheim, ouverture de la station au clic et réparation à la station (client de protocole, sans interface).
 - objet ramassé -> apparaît dans `.build api known` (K|item:) ; pièce dont tous les matériaux sont connus -> KP| ;
   pièce exigeant une station inconnue -> absente de KP| tant que la station n'est pas connue (KS|) ;
 - clic (CMSG_GAMEOBJ_USE) sur une table de fabrication sans marteau -> lignes S| puis OPEN|craft|guid|workbench ;
   marteau en mode réparer -> pas d'OPEN ;
 - réparation : `.build api repairable` (RS|, RI|) et `.build api repairitems` (R|) à la table de fabrication abritée.
python known_test.py <compte> <mdp>   (compte GM, serveur lancé ; docs/VALHEIM_RULES.md §10–11)"""
import socket, struct, subprocess, sys, time
from wlclient import Session, login_char

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
CHAR = sys.argv[3] if len(sys.argv) > 3 else "Wlcost"
WOOD, HAMMER, AXE = 9200001, 9201100, 9201010           # Bois, Marteau, Hache en pierre (recette sans station -> réparée à l'établi)
def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()

ok = True
def check(name, cond, detail=""):
    global ok; ok &= bool(cond); print(("[OK]   " if cond else "[ÉCHEC]"), name, detail, flush=True)

row = sql(f"select guid from classiccharacters.characters where name='{CHAR}'")
cguid = int(row[0]) if row else 0
if cguid:                                                  # repartir d'un personnage qui ne connaît rien (avant la connexion : cache vide)
    sql(f"delete from classiccharacters.wowlheim_known_item where guid={cguid}; delete from classiccharacters.wowlheim_known_station where guid={cguid}")
    # objets Wowlheim laissés dans le sac par les tests précédents : ils seraient « connus » dès la connexion (balayage du sac)
    sql(f"use classiccharacters; delete ci, ii from classiccharacters.character_inventory ci join classiccharacters.item_instance ii on ii.guid=ci.item "
        f"where ci.guid={cguid} and ii.itemEntry between 9200000 and 9299999")

s = Session(sys.argv[1], sys.argv[2]); cguid = login_char(s, CHAR) & 0xFFFFFFFF
def say(c, t=0.8): return [l for l in s.say(c, t) if "Welcome to" not in l and "Tickets" not in l]
def api(c, t=1.5): return [l[4:] for l in say(".build api " + c, t) if l.startswith("[WL]")]
def known():
    r = api("known", 2.0)
    get = lambda p: set(x for l in r if l.startswith(p) for x in l[len(p):].split(",") if x)
    return get("K|item:"), get("KS|"), get("KP|"), get("KR|"), r
def use_collect(entry, low, t=2.0):
    """CMSG_GAMEOBJ_USE puis lignes de chat système reçues pendant t secondes."""
    s.send(0x0B1, struct.pack("<Q", (0xF110 << 48) | (entry << 24) | low))
    lines, end = [], time.time() + t
    s.s.settimeout(0.5)
    while time.time() < end:
        try:
            op, d = s.read()
        except socket.timeout:
            continue
        if op == 0x96 and d[0] == 10:
            ln = struct.unpack("<I", d[13:17])[0]
            lines.append(d[17:17 + ln - 1].decode("utf-8", "replace"))
    return [l[4:] for l in lines if l.startswith("[WL]")]

say(".revive"); s.teleport_cmd(".go xyz -6240 770 400 0"); time.sleep(3); say(".revive"); say(".gm on")
say(".build nocost off"); say(".build grace 0")
for it in (WOOD, HAMMER, AXE):
    say(f".additem {it} -999", 0.4)
time.sleep(1.5)

# 1. rien de connu
items, stations, pieces, recipes, raw = known()
check("au départ : Bois inconnu", str(WOOD) not in items, str(raw[:3]))
check("au départ : table de fabrication (pièce 6, 10 Bois) absente du menu", "6" not in pieces, f"{len(pieces)} pièces")
check("au départ : aucune station connue", not stations, str(stations))

# 2. objet ramassé -> connu (balayage du sac chaque seconde, comme Player.OnInventoryChanged -> AddKnownItem)
say(f".additem {WOOD} 10", 1.0); time.sleep(2.0)
items, stations, pieces, recipes, raw = known()
check("Bois en sac -> connu (K|item:)", str(WOOD) in items, str(sorted(items)))
check("table de fabrication connue (tous ses matériaux connus)", "6" in pieces, "")
check("sol en bois (exige la table) encore inconnu : station inconnue", "1" not in pieces, "")
say(f".additem {WOOD} -999", 0.6); time.sleep(1.5)
items, *_ = known()
check("connaissance définitive : Bois toujours connu après l'avoir perdu", str(WOOD) in items, "")
check("persistance en base (wowlheim_known_item)", sql(f"select count(*) from classiccharacters.wowlheim_known_item where guid={cguid} and item={WOOD}") == ["1"], "")

# 3. abri + table de fabrication (sans coût, posée par ce joueur -> station connue)
say(".build nocost on")
say(".build place Plancher 5 0 0 0")
for a in ("6 0 0 0", "4 0 0 0", "5 -1 0 90", "5 1 0 90"):
    say(".build place Mur " + a)
say(".build place Toit 5 0 2.0 0"); r = " ".join(say(".build place Établi 5 0 0.2 0", 1.2))
check("table de fabrication posée", "posée" in r, r)
say(".build nocost off"); time.sleep(2.0)
items, stations, pieces, recipes, raw = known()
check("station connue après la pose (KS|workbench:1)", any(x.startswith("workbench:") for x in stations), str(stations))
check("sol en bois désormais connu (station + Bois connus)", "1" in pieces, "")
check("persistance (wowlheim_known_station)", sql(f"select count(*) from classiccharacters.wowlheim_known_station where guid={cguid} and kind='workbench'") == ["1"], "")
wb = sql("select p.guid from classiccharacters.wowlheim_piece p where p.piece_id=6 order by p.guid desc limit 1")
wb = int(wb[0]) if wb else 0
check("table de fabrication trouvée en base", wb > 0, str(wb))

# 4. clic droit (Use) sur la table sans marteau -> panneau de fabrication (portée d'utilisation WoW : 5 m -> on s'approche à 3,5 m)
pos = sql(f"select position_x, position_y, position_z from classicmangos.gameobject where guid={wb}")
if pos:                                                  # à 1,5 m de la table elle-même (le personnage peut encore tomber après .go)
    x, y, z = map(float, pos[0].split("	"))
    s.teleport_cmd(f".go xyz {x - 1.5:.2f} {y:.2f} {z + 0.8:.2f} 0"); time.sleep(2.0)
r = use_collect(9110006, wb)
opens = [l for l in r if l.startswith("OPEN|")]
check("clic sur la table : OPEN|craft|guid|workbench", opens == [f"OPEN|craft|{wb}|workbench"], str(r))
check("lignes S| envoyées avant OPEN", any(l.startswith("S|") and l.endswith("|workbench") for l in r) and r.index(opens[0]) > 0 if opens else False, str(r))
# marteau en mode réparer -> pas d'ouverture ; mode construction -> ouverture
say(f".additem {HAMMER} 1", 1.0); time.sleep(0.5); s.equip_item(HAMMER); time.sleep(1.0)
say(".build api mode repair")
r = use_collect(9110006, wb)
check("marteau en mode réparer : pas d'OPEN", not any(l.startswith("OPEN|") for l in r), str(r))
say(".build api mode build")
r = use_collect(9110006, wb)
check("marteau en mode construction : OPEN", any(l.startswith("OPEN|craft|") for l in r), str(r))
say(f".additem {HAMMER} -999", 0.6)

# 5. réparation à la table abritée
say(f".additem {AXE} 1", 1.0); time.sleep(1.0)
maxd = sql(f"select MaxDurability from classicmangos.item_template where entry={AXE}")
maxd = int(maxd[0]) if maxd else 0
r = api(f"repairable {wb}")
check("repairable : RS|guid|workbench|niveau", any(l.startswith(f"RS|{wb}|workbench|") for l in r), str(r))
if maxd <= 0:
    print("[INFO] Hache en pierre sans MaxDurability en base : partie usure/réparation sautée (item_template à régénérer).")
    r = api(f"repairitems {wb}")
    check("repairitems sans objet usé : R| vide, D|repairitems|1", "R|" in r and "D|repairitems|1" in r, str(r))
else:
    api(f"wear {AXE} 1")                                 # usure en jeu (commande MJ)
    r = api(f"repairable {wb}")
    check("hache usée listée : RI|9201010|1|max", f"RI|{AXE}|1|{maxd}" in r, str(r))
    r = api(f"repairitems {wb}")
    check("repairitems : R| contient la hache", any(l.startswith("R|") and str(AXE) in l.split("|")[1].split(",") for l in r), str(r))
    r = api(f"repairable {wb}")
    check("après réparation : plus rien à réparer", not any(l.startswith("RI|") for l in r), str(r))
    say(".build nocost on"); r = api("repairitems 999999999"); say(".build nocost off")
r = api("repairitems 999999999")
check("station inexistante : E| et D|repairitems|0", any(l.startswith("E|") for l in r) and "D|repairitems|0" in r, str(r))
say(f".additem {AXE} -999", 0.4)
s.close()
print("RÉSULTAT :", "OK" if ok else "ÉCHEC")
