"""Portée d'utilisation des grandes pièces mesurée depuis leur BORD (Valheim : on interagit à ~2–3 m de la surface) ;
client de protocole, sans interface.
 - CMSG_GAMEOBJ_USE : le cœur mesure 5 m depuis le CENTRE de l'objet (HandleGameObjectUseOpcode) ; pour une pièce Wowlheim il
   accepte aussi le joueur à 3 m au plus du bord de la boîte (Wowlheim_PieceInUseRange -> BuildingMgr::InUseRange) ;
 - `.build api use <guidHex>` (repli de l'addon quand le client 1.12 refuse : « You are too far away. ») : même vérification puis
   même chemin que GameObject::Use (fonderie / four à charbon -> ligne SM|) ; D|use|1, ou E|Vous êtes trop loin. + D|use|0.
Cas : fonderie à ~4,5 m du centre et < 3 m du bord (coin) ; four à charbon (4,9 x 4,7 m) à ~6,2 m du centre et 2,8 m du bord
(au-delà des 5 m du cœur : seule l'accroche Wowlheim l'accepte) ; les deux à 8 m du bord -> refusés.
python use_range_test.py <compte> <mdp>   (compte GM, serveur lancé)"""
import math, socket, struct, subprocess, sys, time
from wlclient import Session, login_char, goto_test_spot

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()

HAMMER = 9201100
ok = True
def check(name, cond, detail=""):
    global ok; ok &= bool(cond); print(("[OK]   " if cond else "[ÉCHEC]"), name, detail, flush=True)

s = Session(sys.argv[1], sys.argv[2]); login_char(s, "Wlcost")
def say(c, t=0.8): return [l for l in s.say(c, t) if "Welcome to" not in l and "Tickets" not in l]
def api(c, t=1.5): return [l[4:] for l in say(".build api " + c, t) if l.startswith("[WL]")]
def use_collect(entry, low, t=2.0):
    """CMSG_GAMEOBJ_USE puis lignes [WL] reçues pendant t secondes."""
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
def pieces():
    return {int(r.split("\t")[0]): [float(v) for v in r.split("\t")[1:]]
            for r in sql("select guid, piece_id, x, y, z, o from classiccharacters.wowlheim_piece")}
def template(pid):
    r = sql(f"select gameobject_entry, sx, sy, sz from classicmangos.wowlheim_piece_template where id={pid}")[0].split("\t")
    return int(r[0]), float(r[1]), float(r[2]), float(r[3])
def corner_spot(p, sx, sy, edge):
    """Point au-delà du coin (+x, +y local) de la boîte, à `edge` m du bord (distance au coin) ; renvoie (x, y, centre)."""
    a = edge / math.sqrt(2.0)
    lx, ly = sx / 2 + a, sy / 2 + a
    c, sn = math.cos(p["o"]), math.sin(p["o"])
    return p["x"] + lx * c - ly * sn, p["y"] + lx * sn + ly * c, math.hypot(lx, ly)
def go(x, y, z):
    s.teleport_cmd(f".go xyz {x:.2f} {y:.2f} {z:.2f} 0"); time.sleep(0.8)

say(".revive")
say(f".additem {HAMMER} -999", 0.4)                   # sans marteau : le clic utilise la station (pas de démolition)
ids = {}
for l in api("list", 2.5):
    if l.startswith("P|"):
        f = l[2:].split("|")
        ids.setdefault(f[2], int(f[0]))
check("catalogue : fonderie et four à charbon", "smelter" in ids and "charcoal_kiln" in ids, str(ids.get("smelter")) + " " + str(ids.get("charcoal_kiln")))
goto_test_spot(s)
say(".build nocost on"); say(".build grace 600")
before = pieces()
say(f".build place {ids['smelter']} 8 -7", 1.2)
say(f".build place {ids['charcoal_kiln']} 8 8", 1.2)
new = {g: v for g, v in pieces().items() if g not in before}
def placed(kind):
    for g, v in new.items():
        if int(v[0]) == ids[kind]:
            return {"guid": g, "pid": int(v[0]), "x": v[1], "y": v[2], "z": v[3], "o": v[4]}
smel, kiln = placed("smelter"), placed("charcoal_kiln")
check("fonderie et four à charbon posés", smel and kiln, str(new))
if not (smel and kiln):
    s.close(); print("RÉSULTAT : ÉCHEC"); sys.exit(1)

for name, p, edge_in in (("fonderie", smel, 2.5), ("four à charbon", kiln, 2.8)):
    entry, sx, sy, sz = template(p["pid"])
    guid_hex = "%016X" % ((0xF110 << 48) | (entry << 24) | p["guid"])
    # près : < 3 m du bord, loin du centre
    x, y, dc = corner_spot(p, sx, sy, edge_in)
    go(x, y, p["z"] + 0.3)
    r = use_collect(entry, p["guid"])
    check(f"{name} : CMSG_GAMEOBJ_USE à {dc:.1f} m du centre, {edge_in} m du bord -> accepté (SM|)",
          any(l.startswith(f"SM|{p['guid']}|") for l in r), str(r[:3]))
    r = api(f"use {guid_hex}", 2.0)
    check(f"{name} : .build api use <guid> à {edge_in} m du bord -> SM| + D|use|1",
          any(l.startswith(f"SM|{p['guid']}|") for l in r) and "D|use|1" in r, str(r[-3:]))
    # loin : 8 m du bord
    x, y, dc = corner_spot(p, sx, sy, 8.0)
    go(x, y, p["z"] + 0.3)
    r = use_collect(entry, p["guid"])
    check(f"{name} : CMSG_GAMEOBJ_USE à 8 m du bord ({dc:.1f} m du centre) -> refusé (aucune ligne SM|)",
          not any(l.startswith("SM|") for l in r), str(r[:3]))
    r = api(f"use {guid_hex}", 2.0)
    check(f"{name} : .build api use à 8 m du bord -> E|Vous êtes trop loin. + D|use|0",
          "E|Vous êtes trop loin." in r and "D|use|0" in r and not any(l.startswith("SM|") for l in r), str(r))

r = api("use F110000C3500002A")
check(".build api use sur autre chose qu'une pièce -> E|Rien à utiliser. + D|use|0", "E|Rien à utiliser." in r and "D|use|0" in r, str(r))
r = api("use zz")
check(".build api use avec un GUID invalide -> E|GUID invalide. + D|use|0", "E|GUID invalide." in r and "D|use|0" in r, str(r))

say(".build nocost off"); say(".build grace 0")
s.close()
print("RÉSULTAT :", "OK" if ok else "ÉCHEC")
sys.exit(0 if ok else 1)
