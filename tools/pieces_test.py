"""Coffres, portes, lits façon Valheim (Container, Door, Bed ; server/Wowlheim/Pieces.cpp), refus en combat, usure du marteau
(client de protocole, sans interface) :
- coffre (Coffre, 5 x 2 cases) : clic -> OPEN|chest ; dépôt / reprise / déplacement ; contenu persistant (déconnexion puis
  reconnexion) ; démolition au marteau -> contenu rendu dans le sac ; coffre personnel non vide : démolition refusée
  (« Ne peut être retiré pour l'instant », Container.CanBeRemoved) ;
- porte en bois : clic -> ouverte du côté opposé au joueur (s_state 1 / -1), refermée au clic suivant ; état et pose du GameObject
  enregistrés (wowlheim_piece_state, gameobject) ;
- lit : à découvert « Le lit requiert un toit » ; dans une maison (couverture >= 0,8) « Point de réapparition créé », foyer du
  personnage (character_homebind) sur le lit ;
- en combat : pose, démolition et réparation refusées (« Impossible en combat. ») ;
- marteau : durabilité de Valheim (m_maxDurability 100), usé à chaque pose (Player.GetPlaceDurability), réparé à l'établi.
python pieces_test.py <compte> <mdp>   (compte MJ, serveur lancé, SQL 012 + characters/005 appliqués)"""
import math, struct, subprocess, sys, time
from wlclient import Session, login_char, goto_test_spot

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()

WOOD, STONE, RESIN, HAMMER = 9200001, 9200002, 9200004, 9201100
# identifiants STABLES des pièces (tools/valheim/gen_server_sql.py PIECE_IDS)
FLOOR, WALL, ROOF, WORKBENCH, BED, CHEST, CHEST_PRIVATE, DOOR = 1, 2, 3, 6, 13, 28, 127, 56
CHAR = "Wlpiece"

ok = True
def check(name, cond, detail=""):
    global ok; ok &= bool(cond); print(("[OK]   " if cond else "[ÉCHEC]"), name, detail, flush=True)

s = Session(sys.argv[1], sys.argv[2]); cguid = login_char(s, CHAR) & 0xFFFFFFFF
def say(c, t=0.8): return [l for l in s.say(c, t) if "Welcome to" not in l and "Tickets" not in l]
def api(c, t=1.2): return [l for l in say(".build api " + c, t) if l.startswith("[WL]")]
def inv():
    for l in api("inv"):
        if l.startswith("[WL]I|"):
            return {int(a): int(b) for a, b in (x.split(":") for x in l[6:].split(",") if x)}
    return {}
def pos():
    s.send(0x13D, struct.pack("<Q", 0))
    for l in say(".gps", 1.0):
        if l.startswith("X:"):
            f = l.replace(":", " ").split()
            return float(f[1]), float(f[3]), float(f[5])
def face(o):
    x, y, z = pos()
    s.send(0x0DA, struct.pack("<II4fI", 0, int(time.time() * 1000) & 0xFFFFFFFF, x, y, z, o, 0)); time.sleep(0.6)
def pieces():
    return {int(r.split("\t")[0]): [float(v) for v in r.split("\t")[1:]] for r in sql("select guid, piece_id, x, y, z, o from classiccharacters.wowlheim_piece")}
def goto(x, y, z, o=0.0):
    s.teleport_cmd(f".go xyz {x:.2f} {y:.2f} {z + 0.5:.2f} 0"); time.sleep(0.8); face(o)
def hexguid(p):
    return "%016X" % ((0xF110 << 48) | ((9110000 + int(p[1])) << 24) | p[0])
def place(args):
    """.build place <args> -> [guid, piece_id, x, y, z, o] de la pièce posée (ou None)"""
    before = pieces()
    r = say(".build place " + args, 1.2)
    new = {g: v for g, v in pieces().items() if g not in before}
    return ([next(iter(new))] + new[next(iter(new))]) if len(new) == 1 else None
def chest(lines):
    """CH|guid|nom|l|h|privacy|n puis CI|guid|case|objet|nombre|dur|max -> {"w","h","slots":{case:(objet,nombre)}}"""
    out = None
    for l in lines:
        if l.startswith("[WL]CH|"):
            f = l[7:].split("|")
            out = {"guid": int(f[0]), "name": f[1], "w": int(f[2]), "h": int(f[3]), "privacy": int(f[4]), "slots": {}}
        elif l.startswith("[WL]CI|") and out:
            f = l[7:].split("|")
            out["slots"][int(f[1])] = (int(f[2]), int(f[3]))
    return out
def moved(lines):
    for l in lines:
        if l.startswith("[WL]A|"):
            return int(l[6:])
    return -1
def costs(pid):
    for l in api("list", 2.5):
        if l.startswith(f"[WL]P|{pid}|"):
            f = l[6:].split("|")
            return {int(a): int(b) for a, b in (x.split(":") for x in f[6].split(",") if x)}
    return {}

say(".revive")
api("piece combat off")
for it in (WOOD, STONE, RESIN, HAMMER):
    say(f".additem {it} -999", 0.4)
goto_test_spot(s)
face(0.0)
say(".build nocost on")
say(".build grace 600")                                   # pièces de test non portées : pas d'effondrement pendant le test
P0 = pos()
# maison (Valheim : murs et toit exigent l'établi à portée ; l'établi sert aussi à démolir le coffre et à réparer le marteau)
house = [place(a) for a in (f"{WORKBENCH} 12 0 0.2 0", f"{FLOOR} 12 0 0 0", f"{WALL} 13 0 0 0", f"{WALL} 11 0 0 0", f"{WALL} 12 -1 0 90",
                            f"{WALL} 12 1 0 90", f"{ROOF} 12 0 2.0 0", f"{BED} 12 0 0.1 0")]
check("maison posée (établi, plancher, 4 murs, toit, lit)", all(house), str(house))
bed = house[-1]

# ---------------- coffre (piece_chest_wood) : Container 5 x 2, m_privacy 2
c1 = place(f"{CHEST} 3 0")
check("coffre posé", c1 is not None, str(c1))
if not c1:
    s.close(); print("RÉSULTAT : ÉCHEC"); sys.exit(1)
G = c1[0]
goto(c1[2] - 1.5, c1[3], c1[4])
say(f".additem {WOOD} 30", 0.8); say(f".additem {STONE} 7", 0.8)
r = api(f"use {hexguid(c1)}")
ch = chest(r)
check("clic sur le coffre : OPEN|chest et contenu (5 x 2 cases, m_width / m_height de Valheim)",
      any(l == f"[WL]OPEN|chest|{G}" for l in r) and ch and ch["w"] == 5 and ch["h"] == 2 and not ch["slots"], str(r))
r = api(f"chest putitem {G} {WOOD} 30")
r2 = api(f"chest putitem {G} {STONE} 7")
ch = chest(r2)
check("dépôt : 30 Bois en case 0, 7 Pierre en case 1, sac vidé", moved(r) == 30 and moved(r2) == 7 and ch and ch["slots"].get(0) == (WOOD, 30)
      and ch["slots"].get(1) == (STONE, 7) and WOOD not in inv() and STONE not in inv(), f"{r[-3:]} {ch}")
r = api(f"chest take {G} 1 3")
ch = chest(r)
check("reprise de 3 Pierre (case 1 : 4 restantes)", moved(r) == 3 and inv().get(STONE) == 3 and ch["slots"].get(1) == (STONE, 4), str(ch))
r = api(f"chest move {G} 0 7")
ch = chest(r)
check("déplacement de la case 0 vers la case 7", ch and ch["slots"].get(7) == (WOOD, 30) and 0 not in ch["slots"], str(ch))
api(f"chest close {G}")
time.sleep(1.0)
rows = sql(f"select slot, item_id, count from classiccharacters.wowlheim_container where guid={G} order by slot")
check("contenu enregistré (wowlheim_container)", rows == [f"1\t{STONE}\t4", f"7\t{WOOD}\t30"], str(rows))

# déconnexion / reconnexion : le contenu est retrouvé
s.close(); time.sleep(2.0)
s = Session(sys.argv[1], sys.argv[2]); login_char(s, CHAR)
time.sleep(1.0)
goto(c1[2] - 1.5, c1[3], c1[4])
ch = chest(api(f"chest open {G}"))
check("après reconnexion : contenu retrouvé (4 Pierre, 30 Bois)", ch and ch["slots"] == {1: (STONE, 4), 7: (WOOD, 30)}, str(ch))
api(f"chest close {G}")

# démolition au marteau (coût payé : le remboursement et le contenu vont au sac du démolisseur)
say(".build nocost off")
say(f".additem {HAMMER} 1", 1.2); time.sleep(0.5); s.equip_item(HAMMER); time.sleep(1.0)
cost = costs(CHEST)
iv0 = inv()
r = api(f"removeguid {hexguid(c1)}", 1.5)
time.sleep(0.6)
iv1 = inv()
check("démolition du coffre : pièce retirée", G not in pieces() and any("démoli" in l for l in r), str(r))
check("démolition : contenu rendu dans le sac (30 Bois + coût, 4 Pierre)",
      iv1.get(WOOD, 0) - iv0.get(WOOD, 0) == 30 + cost.get(WOOD, 0) and iv1.get(STONE, 0) - iv0.get(STONE, 0) == 4 + cost.get(STONE, 0),
      f"{iv0} -> {iv1} (coût {cost})")
check("démolition : contenu effacé de la base", not sql(f"select guid from classiccharacters.wowlheim_container where guid={G}"), "")
say(".build nocost on")

# coffre personnel (piece_chest_private, m_privacy 0) : non vide -> démolition refusée
c2 = place(f"{CHEST_PRIVATE} 3 -3")
check("coffre personnel posé", c2 is not None, str(c2))
if c2:
    goto(c2[2] - 1.5, c2[3], c2[4])
    ch = chest(api(f"chest open {c2[0]}"))
    check("coffre personnel : 3 x 2 cases", ch and ch["w"] == 3 and ch["h"] == 2 and ch["privacy"] == 0, str(ch))
    say(f".additem {RESIN} 1", 0.6)
    api(f"chest putitem {c2[0]} {RESIN} 1")
    r = api(f"removeguid {hexguid(c2)}", 1.5)
    check("coffre personnel non vide : « Ne peut être retiré pour l'instant »", any("Ne peut être retiré pour l'instant" in l for l in r) and c2[0] in pieces(), str(r))
    api(f"chest takeall {c2[0]}")
    api(f"chest close {c2[0]}")
    r = api(f"removeguid {hexguid(c2)}", 1.5)
    check("coffre personnel vidé (Prendre tout) : démolition acceptée", c2[0] not in pieces() and inv().get(RESIN) == 1, str(r))

# ---------------- porte en bois (wood_door) : bascule ouverte / fermée, état persistant
goto(*P0); face(0.0)
d = place(f"{DOOR} 3 4")
check("porte posée", d is not None, str(d))
if d:
    D, o0 = d[0], d[5]
    def go_row():
        rr = sql(f"select position_x, position_y, orientation from classicmangos.gameobject where guid={D}")
        return [float(v) for v in rr[0].split("\t")] if rr else None
    def state():
        for l in api(f"piece state {D}"):
            if l.startswith("[WL]PS|"):
                return int(l[7:].split("|")[2])
    def angle(a, b):
        return abs((a - b + math.pi) % (2 * math.pi) - math.pi)
    fx, fy = math.cos(o0), math.sin(o0)
    goto(d[2] - 1.2 * fx, d[3] - 1.2 * fy, d[4])           # derrière la porte (côté −forward)
    r = api(f"use {hexguid(d)}")
    time.sleep(1.0)
    row = go_row()
    check("clic derrière la porte : ouverte vers l'avant (s_state 1)", any(l == f"[WL]DR|{D}|1" for l in r) and state() == 1, str(r))
    check("porte ouverte : GameObject tourné de 90° et enregistré (gameobject)", row and angle(row[2], o0 - math.pi / 2) < 0.02, f"{row} o0={o0:.3f}")
    check("état enregistré (wowlheim_piece_state)", sql(f"select door_state from classiccharacters.wowlheim_piece_state where guid={D}") == ["1"], "")
    r = api(f"use {hexguid(d)}")
    time.sleep(1.0)
    row = go_row()
    check("second clic : refermée, pose d'origine", any(l == f"[WL]DR|{D}|0" for l in r) and state() == 0 and row
          and angle(row[2], o0) < 0.02 and abs(row[0] - d[2]) < 0.05 and abs(row[1] - d[3]) < 0.05, f"{r} {row}")
    goto(d[2] + 1.2 * fx, d[3] + 1.2 * fy, d[4])           # devant la porte
    r = api(f"use {hexguid(d)}")
    time.sleep(1.0)
    row = go_row()
    check("clic devant la porte : ouverte de l'autre côté (s_state -1)", any(l == f"[WL]DR|{D}|-1" for l in r) and row and angle(row[2], o0 + math.pi / 2) < 0.02, f"{r} {row}")

# ---------------- lit (bed) : à découvert, puis dans une maison
goto(*P0); face(0.0)
b1 = place(f"{BED} 3 9")
check("lit à découvert posé", b1 is not None, str(b1))
if b1:
    goto(b1[2] - 2.5, b1[3], b1[4])
    r = api(f"use {hexguid(b1)}")
    check("lit à découvert : « Le lit requiert un toit » (Bed.CheckExposure)", any("Le lit requiert un toit" in l for l in r), str(r))
if bed:
    goto(bed[2] + 2.6, bed[3], bed[4], math.pi)
    r = api(f"use {hexguid(bed)}")
    time.sleep(1.0)
    hb = sql(f"select position_x, position_y, position_z from classiccharacters.character_homebind where guid={cguid}")
    hx, hy, hz = [float(v) for v in hb[0].split("\t")] if hb else (0, 0, 0)
    check("lit abrité : « Point de réapparition créé »", any("Point de réapparition créé" in l for l in r), str(r))
    check("foyer du personnage (character_homebind) sur le lit", hb and abs(hx - bed[2]) < 0.1 and abs(hy - bed[3]) < 0.1 and abs(hz - bed[4] - 0.5) < 0.2, f"{hb} lit {bed[2:5]}")
    check("propriétaire du lit enregistré", sql(f"select bed_owner from classiccharacters.wowlheim_piece_state where guid={bed[0]}") == [str(cguid)], "")

# ---------------- refus en combat (adaptation WoW) : pose, démolition, réparation
goto(*P0); face(0.0)
api("piece combat on")
r = say(f".build place {FLOOR} 3 -7", 1.0)
check("en combat : pose refusée (.build place)", any("Impossible en combat" in l for l in r), str(r))
x, y, z = pos()
api(f"select {FLOOR} 0")
api("piece combat on")
r = api(f"placeat {x + 3:.2f} {y - 7:.2f} {z:.2f}", 1.5)
check("en combat : pose au marteau refusée (sort de pose)", any("Impossible en combat" in l for l in r) and any("D|place|0" in l for l in r), str(r))
if b1:
    goto(b1[2] - 2.5, b1[3], b1[4])
    api("piece combat on")
    r = api(f"removeguid {hexguid(b1)}", 1.5)
    check("en combat : démolition refusée", any("Impossible en combat" in l for l in r) and b1[0] in pieces(), str(r))
    api("mode repair")
    api("piece combat on")
    r = api(f"use {hexguid(b1)}", 1.5)
    check("en combat : réparation refusée", any("Impossible en combat" in l for l in r), str(r))
    api("mode build")
    api("piece combat off")
    r = api(f"removeguid {hexguid(b1)}", 1.5)
    check("hors combat : démolition acceptée", b1[0] not in pieces(), str(r))

# ---------------- marteau : durabilité de Valheim, usure à la pose, réparation à l'établi
goto(*P0); face(0.0)
r = api(f"wear {HAMMER} 50")
check("marteau à durabilité (MaxDurability > 0)", any("1 objet(s)" in l for l in r), str(r))
def hammer_dur():
    for l in api("repairable"):
        if l.startswith(f"[WL]RI|{HAMMER}|"):
            f = l[4:].split("|")
            return int(f[2]), int(f[3])
    return None
dm = hammer_dur()
check("durabilité max du marteau = m_maxDurability de Valheim (100)", dm == (50, 100), str(dm))
x, y, z = pos()
api(f"select {FLOOR} 0")
for k in range(3):
    time.sleep(2.0)                                       # endurance
    api(f"placeat {x + 3:.2f} {y - 4 - 2.5 * k:.2f} {z:.2f}", 1.2)
dm = hammer_dur()
check("3 poses au marteau : durabilité usée (Player.GetPlaceDurability, 1 − 0,5 × facteur Fabrication par pose)",
      dm and 46 <= dm[0] <= 48, str(dm))
if bed:
    say(".build nocost off")
    goto(bed[2] + 2.6, bed[3], bed[4], math.pi)
    r = api("repairitems", 1.5)
    check("réparation à l'établi abrité : marteau réparé", any(l.startswith("[WL]R|") and str(HAMMER) in l for l in r), str(r))
    say(".build nocost on")
    check("marteau à 100 après réparation (n'apparaît plus parmi les objets usés)", hammer_dur() is None, "")

api("piece combat off")
api("mode build")
say(".build nocost on")
say(".build grace 0")                                     # valeur de Valheim (pièces posées par un joueur)
s.close()
print("RÉSULTAT :", "OK" if ok else "ÉCHEC")
