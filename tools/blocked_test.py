"""Pose bloquée par le décor de WoW (Valheim : Piece.IsOverlapping -> fantôme rouge, pose impossible) : la boîte de la pièce,
réduite de 10 %, ne doit pas couper la géométrie statique (VMaps : WMO, doodads M2 avec collision). Client de protocole, sans interface.
Cas : Plancher et Mur au milieu du chariot de marchand de l'abbaye du Comté du Nord (Stormwindgypsywagon01.m2, centre
-8895,77 ; -114,25 ; 81,83 d'après 000_32_48.vmtile) -> `.build api canplace` CP|0|…|Bloqué. et pose refusée (M|Bloqué., D|place|0) ;
Plancher en plein champ à 10 m de là -> CP|1 et pose acceptée. Affiche le coût mesuré (`.build perf`).
python blocked_test.py [<compte> <mdp>]   (compte GM, serveur lancé ; défaut : WLTEST5, mot de passe lu dans run\\test_account5.txt)"""
import os, re, struct, subprocess, sys, time
from wlclient import Session, login_char, goto_test_spot

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()

if len(sys.argv) >= 3:
    user, pw = sys.argv[1], sys.argv[2]
else:
    user = "WLTEST5"
    pw = [l.split(": ", 1)[1].strip() for l in open(r"C:\Wowlheim\run\test_account5.txt", encoding="utf-8") if l.startswith("password:")][0]

s = Session(user, pw); login_char(s, "Wlblock")
ok = True
def check(name, cond, detail=""):
    global ok; ok &= bool(cond); print(("[OK]   " if cond else "[ÉCHEC]"), name, detail, flush=True)
def say(c, t=0.8): return [l for l in s.say(c, t) if "Welcome to" not in l and "Tickets" not in l]
def ground(x, y):
    """GroundZ au point (x, y) : téléport du personnage puis .gps (même méthode que goto_test_spot)."""
    goto_test_spot(s, x, y, 90.0)
    m = re.search(r"GroundZ: ([-\d.]+)", " ".join(say(".gps", 1.0)))
    return float(m.group(1)) if m else None
def pieces():
    return {int(r.split("\t")[0]) for r in sql("select guid from classiccharacters.wowlheim_piece")}

WAGON = (-8895.77, -114.25, 81.83)        # chariot de marchand (doodad M2 avec collision)
FIELD = (-8887.0, -122.0)                 # herbe libre (aucun objet VMaps à moins de 3 m)
STAND = (-8891.0, -118.0)                 # personnage : à moins de 8 m des deux points (portée de pose)

say(".revive"); say(".build nocost on")    # sans coût : seul le chevauchement est testé (station et ressources ailleurs)
say(".additem 9201100 1", 1.2); time.sleep(0.5); s.equip_item(9201100); time.sleep(1.0)
fz = ground(*FIELD)
check("sol du champ trouvé (.gps GroundZ)", fz is not None and abs(fz - 81.9) < 3.0, str(fz))
fz = fz if fz is not None else 81.9
sz = ground(*STAND) or 81.9
s.teleport_cmd(f".go xyz {STAND[0]} {STAND[1]} {sz + 0.2:.2f} 0"); time.sleep(1.0)
say(".build perf", 1.0)

before = pieces()
for pid, name in ((1, "Plancher 2x2"), (2, "Mur en bois")):
    say(f".build api select {pid} 0")
    r = say(f".build api canplace {WAGON[0]} {WAGON[1]} {WAGON[2]}", 1.0)
    cp = [l for l in r if l.startswith("[WL]CP|")]
    check(f"canplace {name} au milieu du chariot -> fantôme rouge (CP|0|…|Bloqué.)", cp and cp[0].startswith("[WL]CP|0|") and cp[0].endswith("|Bloqué."), str(cp))
    r = say(f".build api placeat {WAGON[0]} {WAGON[1]} {WAGON[2]}", 1.5)
    time.sleep(0.5)
    check(f"pose {name} au milieu du chariot refusée (M|Bloqué. + D|place|0, rien en base)",
          any(l == "[WL]M|Bloqué." for l in r) and any("D|place|0" in l for l in r) and pieces() == before, str(r))

say(".build api select 1 0")
r = say(f".build api canplace {FIELD[0]} {FIELD[1]} {fz:.2f}", 1.0)
cp = [l for l in r if l.startswith("[WL]CP|")]
check("canplace Plancher en plein champ -> fantôme valide (CP|1)", cp and cp[0].startswith("[WL]CP|1|"), str(cp))
r = say(f".build api placeat {FIELD[0]} {FIELD[1]} {fz:.2f}", 1.5)
new = set()
for _ in range(15):
    new = pieces() - before
    if new: break
    time.sleep(0.2)
check("pose Plancher en plein champ acceptée (D|place|1, pièce en base)", any("D|place|1" in l for l in r) and len(new) == 1, str(r))

perf = [l for l in say(".build perf", 1.0) if "VMaps" in l]
check("coût mesuré (.build perf)", perf, str(perf))
print("       ", perf[0] if perf else "")

if new:                                        # nettoyage : démolition au marteau (sans coût), à portée d'utilisation
    s.teleport_cmd(f".go xyz {FIELD[0] + 2.5:.2f} {FIELD[1]:.2f} {fz + 0.2:.2f} 0"); time.sleep(1.0)
for g in new:
    say(".build api mode remove"); s.use_gameobject(9110001, g, 1.0); say(".build api mode build")
say(".build nocost off")
s.close()
print("RÉSULTAT :", "OK" if ok else "ÉCHEC")
