"""Abattage façon Valheim (client de protocole, sans interface) : un hêtre (créature au modèle Valheim) ne prend que les coups
d'une hache ; à la hache en pierre il tombe (80 PV), laisse un tronc (60 PV) qui se fend en deux bûches (60 PV) donnant 10 Bois
chacune (TreeLog.m_dropWhenDestroyed de Valheim) ; un bouleau exige une hache de bronze (m_minToolTier 2 : « Trop dur »).
Compétences et endurance façon Valheim (docs/VALHEIM_SKILLS.md) : chaque coup de hache utile monte Couper du bois (13) de 1
(Skill.Raise, palier 0,5·(niveau+1)^1,5 + 0,5), chaque coup de pioche monte Pioches (12) ; chaque coup coûte de l'endurance
(EN|) ; endurance vide => coup refusé (0 dégât, EN|...|1, « trop fatigué »).
python tree_test.py <compte> <mdp>   (compte GM, serveur lancé)"""
import math, re, socket, struct, subprocess, sys, time
from wlclient import Session, login_char

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()

s = Session(sys.argv[1], sys.argv[2]); login_char(s, sys.argv[3] if len(sys.argv) > 3 else "Wlharvest")
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
    # personnage de niveau 1 au milieu des loups : ressuscité et rendu robuste à chaque placement (sinon mort -> rien ne s'équipe)
    say(".revive", 0.4); s.send(0x13D, struct.pack("<Q", s.guid)); say(".modify hp 50000", 0.4)
    s.teleport_cmd(f".go xyz {x:.2f} {y:.2f} {t['z'] + 0.5:.2f} {MAP}"); time.sleep(1.0)
    # MSG_MOVE_SET_FACING : le client se tourne vers l'arbre (mouvement : drapeaux, temps, x, y, z, o, temps de chute)
    s.send(0x0DA, struct.pack("<II4fI", 0, int(time.time() * 1000) & 0xFFFFFFFF, x, y, t["z"] + 0.5, face, 0)); time.sleep(0.6)
def unpack_guid(d, i):
    mask = d[i]; i += 1; g = 0
    for b in range(8):
        if mask & (1 << b): g |= d[i] << (8 * b); i += 1
    return g, i
WL = []                                          # lignes [WL] reçues pendant les attaques (EN| SK| SKU|)
def chop(t, seconds, every=None):
    """Attaque automatique sur la créature ; renvoie (dégâts par coup, notifications). every = (période, commande) : commande
    envoyée régulièrement pendant l'attaque (ex. endurance remise à 0)."""
    g = cguid(t["entry"], t["low"])
    s.send(0x13D, struct.pack("<Q", g))          # CMSG_SET_SELECTION
    s.send(0x141, struct.pack("<Q", g))          # CMSG_ATTACKSWING
    hits, notes, end = [], [], time.time() + seconds
    s.s.settimeout(0.2 if every else 0.5)
    nxt = 0
    while time.time() < end:
        if every and time.time() >= nxt:
            s.send(0x095, struct.pack("<II", 0, 0) + every[1].encode() + b"\0")   # CMSG_MESSAGECHAT (dire)
            nxt = time.time() + every[0]
        try:
            op, d = s.read()
        except socket.timeout:
            continue
        if op == 0x096 and d[0] == 10:           # SMSG_MESSAGECHAT, système : lignes [WL] du canal de l'addon
            ln = struct.unpack("<I", d[13:17])[0]
            line = d[17:17 + ln - 1].decode("utf-8", "replace")
            if line.startswith("[WL]"):
                WL.append(line)
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

equip(9201010)                                   # hache en pierre (Valheim : chop 20, palier 0, m_attackStamina 6)
stand_near(tree)
for sk in (7, 12, 13):
    say(f".build api skills set {sk} 0", 0.4)    # compétences remises à 0 (MJ) : test reproductible
# endurance vide (remise à 0 toutes les 0,3 s) : Attack.Start refuse le coup (HaveStamina(coût + 0,1)), la barre clignote
del WL[:]
hits, notes = chop(tree, 5, (0.3, ".build api skills stamina 0"))
flash = [l for l in WL if l.startswith("[WL]EN|") and l.endswith("|1")]
check("endurance vide : coups refusés (0 dégât), « trop fatigué », barre qui clignote (EN|…|1)",
      hits and max(hits) == 0 and any("fatigué" in n for n in notes) and flash, f"{hits} {notes} {WL[-4:]}")
check("endurance vide : aucun gain de compétence (pas de coup)", all(l == "[WL]SK|13|0|0" for l in WL if l.startswith("[WL]SK|13|")), str(WL[-4:]))   # la commande stamina renvoie aussi SK|13|0|0
say(".build api skills stamina 50", 0.4)
time.sleep(0.5)
del WL[:]
hits, notes = chop(tree, 60)
print("coups sur le hêtre :", hits)
check("hache en pierre : dégâts de coupe Valheim (20 x [0,25 ; 0,55] => 5 à 11)", hits and all(5 <= h <= 11 for h in hits), str(hits))
# Valheim : +1 (m_raiseSkillAmount × m_increseStep) par coup utile ; un seul niveau par coup, l'excédent perdu
lvl, acc = 0, 0.0
for _ in hits:
    acc += 1.0
    if acc >= 0.5 * (lvl + 1) ** 1.5 + 0.5:
        lvl, acc = lvl + 1, 0.0
sk13 = [l for l in WL if l.startswith("[WL]SK|13|")]
last = sk13[-1].split("|") if sk13 else None
check("chaque coup utile monte Couper du bois (une ligne SK|13 par coup)", len(sk13) == len(hits), f"{len(sk13)} lignes, {len(hits)} coups")
check(f"niveau de Couper du bois après {len(hits)} coups = {lvl} (Skill.Raise, palier 0,5·(n+1)^1,5 + 0,5)",
      last and int(last[2]) == lvl and any(l == "[WL]SKU|13|1" for l in WL), str(sk13[-3:]))
check("la hache sur un arbre ne monte pas Haches (m_specialHitSkill = Couper du bois)", not any(l.startswith("[WL]SK|7|") for l in WL))
ens = [int(l.split("|")[1]) for l in WL if l.startswith("[WL]EN|")]
check("chaque coup débite l'endurance (EN| sous le max, 6 par coup de hache en pierre au niveau 0 de Haches)",
      len(ens) >= len(hits) and ens and min(ens) < 500, str(ens[:6]))
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
    say(".additem 9200001 -999")
    for h in halves:
        h["hp"] = 60
        stand_near(h, 1.4, math.atan2(lg["y"] - tree["y"], lg["x"] - tree["x"]) + math.pi / 2)
        hits, notes = chop(h, 50)
        time.sleep(1.0)
    # Valheim : la bûche brisée lâche son bois (ramassé automatiquement) -> directement dans le sac
    inv = " ".join(say(".build inv")); m = re.search(r"(\d+) Bois", inv); wood = int(m.group(1)) if m else 0
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
# minage façon Valheim : le rocher (créature MineRock_Stone) = rock4_coast de Valheim, brisé en rock4_coast_frac (MineRock5 :
# 130 zones de 50 PV, palier 0, 4 à 8 Pierre par zone), dont 69 dépassent du sol (atteignables sans creuser) ; regroupé :
# 69 x 50 / 8 = 431 PV (8 zones par coup : multiHit + effondrement des zones soutenues, calage), 394 à 434 Pierre (même moyenne et même variance que ces 69 zones, docs/VALHEIM_RULES.md §13), pioche seulement
rock = sql("select guid, position_x, position_y, position_z from classicmangos.creature where id=9300104 and map=0 and guid not in (select guid from classiccharacters.creature_respawn) order by guid limit 1")
rstat = sql("select t.MinLevelHealth, w.min_tier, w.rolls_min, w.rolls_max from classicmangos.creature_template t join classicmangos.wowlheim_tree w on w.entry=t.Entry where t.Entry=9300104")
if rstat:
    r_hp, r_tier, r_lo, r_hi = map(int, rstat[0].split("\t"))
    check("rocher en base = rock4_coast_frac de Valheim (69 zones hors sol) : 431 PV, palier 1 (pioche en bois de cerf), 394 à 434 Pierre",
          (r_hp, r_tier, r_lo, r_hi) == (431, 1, 394, 434), str(rstat))
if rock and rstat:
    r_ = rock[0].split("\t")
    rt = {"low": int(r_[0]), "entry": 9300104, "x": float(r_[1]), "y": float(r_[2]), "z": float(r_[3]), "hp": r_hp}
    say(".additem 9200002 -999")
    def mailed_stone():                           # Pierre arrivée par courrier (sac plein : BuildingMgr::GiveItems)
        m = sql(f"select coalesce(sum(i.count), 0) from classiccharacters.mail_items mi join classiccharacters.item_instance i on i.guid=mi.item_guid "
                f"where mi.receiver={s.guid & 0xFFFFFFFF} and mi.item_template=9200002")
        return int(m[0]) if m else 0
    mail0 = mailed_stone()
    # le rocher est souvent dans un camp de monstres : PV relevés pour ne tester que le minage
    s.send(0x13D, struct.pack("<Q", s.guid)); say(".modify hp 50000")
    equip(9201010)
    stand_near(rt, 2.2)
    hits, notes = chop(rt, 5)
    check("rocher à la hache : aucun dégât, « Il faut une pioche »", hits and max(hits) == 0 and any("pioche" in n for n in notes), f"{hits} {notes}")
    equip(9201012)                                # pioche en bois de cerf (Valheim : m_pickaxe 18, palier 0)
    stand_near(rt, 2.2)
    del WL[:]
    hits, notes = chop(rt, 45)                    # ~60 coups pour 431 PV (7 dégâts en moyenne) : on vérifie les coups, puis on achève au MJ
    sk12 = [l for l in WL if l.startswith("[WL]SK|12|")]
    check("chaque coup de pioche sur la roche monte Pioches (SK|12)", hits and len(sk12) == len(hits) and any(l == "[WL]SKU|12|1" for l in WL),
          f"{len(sk12)} lignes, {len(hits)} coups")
    check("la pioche en bois de cerf entame le rocher (palier 0 de Valheim)", hits and max(hits) > 0, str(hits[:8]))
    print("coups sur le rocher :", len(hits), hits[:8])
    left = [t["hp"] for t in trees(8) if t["low"] == rt["low"] and t["alive"]]
    if left:
        s.send(0x13D, struct.pack("<Q", cguid(rt["entry"], rt["low"])))
        say(f".damage {left[0] + 10}", 1.5)        # dégât direct sans sort = autorisé (TreeMgr::AllowDamage) ; tué par le joueur
    time.sleep(4)                                 # remise du butin + écriture du courrier en base
    alive = [t for t in trees(8) if t["low"] == rt["low"] and t["alive"]]
    inv = " ".join(say(".build inv"))
    m = re.search(r"(\d+) Pierre", inv)
    got = (int(m.group(1)) if m else 0) + mailed_stone() - mail0
    check(f"rocher brisé : {r_lo} à {r_hi} Pierre (sac + courrier ; DropTable de rock4_coast_frac, 69 zones hors sol)",
          not alive and r_lo <= got <= r_hi, f"{got} Pierre ; {inv}")
s.close()
print("RÉSULTAT :", "OK" if ok else "ÉCHEC")
