"""Marteau façon Valheim (client de protocole, sans interface) : catalogue des pièces de Valheim, pièce choisie (select),
pose au point visé avec accroche sur les points d'accroche de Valheim (même chemin que le sort de pose du marteau),
démolition par clic droit sur la pièce en mode « démolir », avec remboursement.
python hammer_test.py <compte> <mdp>   (compte GM, serveur lancé)"""
import math, struct, subprocess, sys, time
from wlclient import Session, login_char, goto_test_spot

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()

s = Session(sys.argv[1], sys.argv[2]); login_char(s, "Wlcost")
ok = True
def check(name, cond, detail=""):
    global ok; ok &= bool(cond); print(("[OK]   " if cond else "[ÉCHEC]"), name, detail, flush=True)
def say(c, t=0.8): return [l for l in s.say(c, t) if "Welcome to" not in l and "Tickets" not in l]
def pos():
    s.send(0x13D, struct.pack("<Q", 0))
    for l in say(".gps", 1.0):
        if l.startswith("X:"):
            f = l.replace(":", " ").split()
            return float(f[1]), float(f[3]), float(f[5])
def pieces():
    return {int(r.split("\t")[0]): [float(v) for v in r.split("\t")[1:]] for r in sql("select guid, piece_id, x, y, z, o from classiccharacters.wowlheim_piece")}

say(".revive"); say(".build nocost off")
for it in (9200001, 9201100): say(f".additem {it} -999")
lst = [l for l in say(".build api list", 2.5) if l.startswith("[WL]P|")]
check("catalogue du marteau : pièces de Valheim (83)", len(lst) == 83, str(len(lst)))
goto_test_spot(s)
x, y, z = pos()
s.send(0x0DA, struct.pack("<II4fI", 0, int(time.time() * 1000) & 0xFFFFFFFF, x, y, z, 0.0, 0)); time.sleep(0.6)   # face au nord (o = 0)
say(".additem 9200001 4", 1.2); say(".additem 9201100 1", 1.2); time.sleep(0.5); s.equip_item(9201100); time.sleep(1.0)
before = pieces()

say(".build api select 1 0")                                  # Sol en bois (wood_floor, 2 Bois)
r = say(f".build api placeat {x + 4:.2f} {y:.2f} {z:.2f}", 1.5)
new = {g: v for g, v in pieces().items() if g not in before}
check("sol posé au point visé (2 Bois consommés)", len(new) == 1 and any("D|place|1" in l for l in r), str(r))
fg, (fpid, fx, fy, fz, fo) = list(new.items())[0] if new else (0, (0, 0, 0, 0, 0))

say(".build api select 2 0")                                  # Mur en bois : clic au bord du sol, un peu à côté
r = say(f".build api placeat {fx + 1.15:.2f} {fy + 0.2:.2f} {fz:.2f}", 1.5)
new2 = {g: v for g, v in pieces().items() if g not in before and g != fg}
check("mur posé", len(new2) == 1, str(r))
if new2:
    wg, (wpid, wx, wy, wz, wo) = list(new2.items())[0]
    # points d'accroche Valheim : mur (0,064 ; ±1 ; 0) sur les coins du sol (±0,992 ; ±1 ; 0,14) -> le mur se cale au bord du sol
    check("mur accroché au sol (x au bord, y centré, base au niveau d'accroche du sol)",
          abs(wx - (fx + 1.008 - 0.064)) < 0.06 and abs(wy - fy) < 0.06 and abs(wz - (fz + 0.14)) < 0.06,
          f"sol ({fx:.2f},{fy:.2f},{fz:.2f}) mur ({wx:.2f},{wy:.2f},{wz:.2f})")
    inv = " ".join(say(".build inv"))
    check("coûts de Valheim : 2 + 2 Bois consommés", "Bois" not in inv, inv)
    say(".build api mode remove")
    s.use_gameobject(9110000 + 2, wg, 1.5)                    # clic droit sur le mur (GameObject cliquable)
    time.sleep(0.5)
    check("démolition au marteau (clic droit en mode démolir)", wg not in pieces(), "")
    inv = " ".join(say(".build inv"))
    check("remboursement complet (2 Bois rendus)", "2 Bois" in inv, inv)
    say(".build api mode build")
    s.use_gameobject(9110000 + 1, fg, 1.5)                    # mode construction : clic sans effet
    time.sleep(0.5)
    check("en mode construction, un clic ne démolit pas", fg in pieces(), "")
    say(".build nocost on"); say(".build api mode remove"); s.use_gameobject(9110001, fg, 1.0); say(".build api mode build"); say(".build nocost off")
s.close()
print("RÉSULTAT :", "OK" if ok else "ÉCHEC")
