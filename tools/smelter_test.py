"""Fonderie, four à charbon, haut fourneau et rouet façon Valheim (composant Smelter ; client de protocole, sans interface) :
- four à charbon : 25 Bois au plus en file (m_maxOre), pas de combustible, 1 Charbon toutes les 15 s ;
- fonderie : Charbon jusqu'à 20 (m_maxFuel), minerai jusqu'à 10, 1 lingot toutes les 30 s pour 2 Charbon (m_fuelPerProduct) ;
- haut fourneau : Charbon jusqu'à 20, Morceau de sombracier jusqu'à 10, 1 Sombracier toutes les 30 s pour 2 Charbon ;
- rouet : 40 Lin au plus, pas de combustible, toit exigé (m_requiresRoof), 1 Toile de lin toutes les 30 s ;
- objet refusé (« Cela ne marchera pas »), station pleine (« C'est plein »), clic sur la station sans marteau = récupérer + ajouter,
  sortie de fumée bouchée par une pièce = arrêt, démolition = contenu rendu, état persisté (classiccharacters.wowlheim_smelter_state).
python smelter_test.py <compte> <mdp>   (compte GM, serveur lancé, SQL 012 + characters/002 appliqués)"""
import struct, subprocess, sys, time
from wlclient import Session, login_char, goto_test_spot

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
def sql(q):
    return subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()

WOOD, STONE, COAL, COPPER, COPPER_ORE, TIN_ORE, HAMMER = 9200001, 9200002, 9200051, 9200013, 9200060, 9200061, 9201100
FLAX, LINEN, BM_SCRAP, BLACKMETAL, IRON_ORE = 9200042, 9200043, 9200081, 9200041, 9200064

s = Session(sys.argv[1], sys.argv[2]); login_char(s, "Wlcost")
ok = True
def check(name, cond, detail=""):
    global ok; ok &= bool(cond); print(("[OK]   " if cond else "[ÉCHEC]"), name, detail, flush=True)
def say(c, t=0.8): return [l for l in s.say(c, t) if "Welcome to" not in l and "Tickets" not in l]
def api(c, t=1.2): return [l for l in say(".build api " + c, t) if l.startswith("[WL]")]
def sm(lines):
    """Dernière ligne [WL]SM|... -> dict"""
    for l in reversed(lines):
        if l.startswith("[WL]SM|"):
            f = l[7:].split("|")
            parse = lambda t: {int(a): int(b) for a, b in (x.split(":") for x in t.split(",") if x)}
            return {"guid": int(f[0]), "kind": f[1], "queue": int(f[3]), "maxOre": int(f[4]), "fuel": float(f[5]), "maxFuel": int(f[6]),
                    "bake": float(f[8]), "sec": float(f[9]), "active": f[10] == "1", "why": f[11],
                    "items": parse(f[12]), "out": parse(f[13])}
    return None
def added(lines):
    for l in lines:
        if l.startswith("[WL]A|"):
            return int(l[6:])
    return -1
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
def pieces():
    return {int(r.split("\t")[0]): [float(v) for v in r.split("\t")[1:]] for r in sql("select guid, piece_id, x, y, z from classiccharacters.wowlheim_piece")}
def face(o):
    x, y, z = pos()
    s.send(0x0DA, struct.pack("<II4fI", 0, int(time.time() * 1000) & 0xFFFFFFFF, x, y, z, o, 0)); time.sleep(0.6)
def near(p, dx=2.5):
    s.teleport_cmd(f".go xyz {p[2] + dx:.2f} {p[3]:.2f} {p[4] + 0.5:.2f} 0"); time.sleep(0.8)
    face(3.14159)                                     # tourné vers la station (-x)

say(".revive")
for it in (WOOD, STONE, COAL, COPPER, COPPER_ORE, TIN_ORE, 9200062, 9200064, 9200014, 9200021, 9200029, HAMMER, FLAX, LINEN, BM_SCRAP, BLACKMETAL):
    say(f".additem {it} -999", 0.4)
ids = {}
for l in api("list", 2.5):
    if l.startswith("[WL]P|"):
        f = l[6:].split("|")
        ids.setdefault(f[2], int(f[0]))
KINDS = ("smelter", "charcoal_kiln", "blastfurnace", "spinningwheel", "workbench")
check("catalogue : fonderie, four à charbon, haut fourneau et rouet posables", all(k in ids for k in KINDS), str({k: ids.get(k) for k in KINDS}))
goto_test_spot(s)
face(0.0)
say(".build nocost on")
before = pieces()
say(f".build place {ids['workbench']} 8 0", 1.2)
say(f".build place {ids['charcoal_kiln']} 8 -6", 1.2)
say(f".build place {ids['smelter']} 8 5", 1.2)
say(f".build place {ids['blastfurnace']} 15 5", 1.2)
say(f".build place {ids['spinningwheel']} 15 -6", 1.2)
new = {g: v for g, v in pieces().items() if g not in before}
def placed(kind):
    return next(([g] + v for g, v in new.items() if int(v[0]) == ids[kind]), None)
kiln, smel, blast, wheel = placed("charcoal_kiln"), placed("smelter"), placed("blastfurnace"), placed("spinningwheel")
check("établi, four à charbon, fonderie, haut fourneau et rouet posés", kiln and smel and blast and wheel and len(new) == 5, str(new))
if not (kiln and smel and blast and wheel):
    s.close(); print("RÉSULTAT : ÉCHEC"); sys.exit(1)
K, S, B, W = kiln[0], smel[0], blast[0], wheel[0]

# ---------------- four à charbon : m_maxOre 25, pas de combustible
near(kiln)
say(f".additem {WOOD} 30", 1.2)
r = api(f"smelter add {WOOD} 30 {K}", 2.5)
st = sm(r)
check("four : 25 Bois acceptés puis « C'est plein » (m_maxOre 25)", added(r) == 25 and st and st["queue"] == 25 and any("plein" in l for l in r), str(r[-3:]))
check("four : actif sans combustible (m_maxFuel 0), 15 s par produit", st and st["active"] and st["sec"] == 15.0 and st["maxFuel"] == 0, str(st))
check("four : 5 Bois restent dans le sac", inv().get(WOOD) == 5, str(inv()))
r = api(f"smelter add fuel 1 {K}")
check("four : pas d'ajout de combustible (« Objet inadéquat »)", added(r) == 0 and any("inadéquat" in l for l in r), str(r))
t_kiln = time.time()

# ---------------- rouet (piece_spinningwheel) : m_maxOre 40, pas de combustible, m_requiresRoof 1, Lin -> Toile de lin en 30 s
near(wheel)
say(f".additem {FLAX} 45", 1.2)
r = api(f"smelter add {FLAX} 45 {W}", 3.0)
st = sm(r)
check("rouet : 40 Lin acceptés puis « C'est plein » (m_maxOre 40)", added(r) == 40 and st and st["queue"] == 40 and any("plein" in l for l in r), str(r[-3:]))
check("rouet : sans combustible (m_maxFuel 0), 30 s par produit", st and st["maxFuel"] == 0 and st["sec"] == 30.0, str(st))
check("rouet : 5 Lin restent dans le sac", inv().get(FLAX) == 5, str(inv()))
r = api(f"smelter add fuel 1 {W}")
check("rouet : pas d'ajout de combustible (« Objet inadéquat »)", added(r) == 0 and any("inadéquat" in l for l in r), str(r))
time.sleep(2.0)
st = sm(api(f"smelter status {W}"))
check("rouet sans toit : à l'arrêt (m_requiresRoof), minuterie figée", st and not st["active"] and st["why"] == "roof" and st["bake"] == 0.0, str(st))
say(".build grace 600")                                   # le plancher-toit n'est porté par rien : pas d'effondrement pendant le test
face(3.14159)
say(".build place 1 2.5 0 2.6", 1.2)                      # Plancher au-dessus du rouet (hauteur 2,16 m) : toit (rayon vertical)
st = sm(api(f"smelter status {W}"))
check("rouet sous un toit : en marche", st and st["active"] and st["why"] == "ok", str(st))
t_wheel = time.time()

# ---------------- haut fourneau (blastfurnace) : Charbon (20 max, 2 par produit), Morceau de sombracier (10 max) -> Sombracier, 30 s
near(blast)
say(f".additem {COAL} 25", 1.0); say(f".additem {BM_SCRAP} 12", 1.0); say(f".additem {IRON_ORE} 1", 1.0)
r = api(f"smelter add {IRON_ORE} 1 {B}")
check("haut fourneau : le minerai de fer est refusé (« Cela ne marchera pas »)", added(r) == 0 and any("marchera pas" in l for l in r), str(r))
say(f".additem {IRON_ORE} -1", 0.6)
r = api(f"smelter add fuel 25 {B}", 2.5)
st = sm(r)
check("haut fourneau : 20 Charbon au plus (m_maxFuel 20) puis « C'est plein »", added(r) == 20 and st and abs(st["fuel"] - 20) < 0.01 and any("plein" in l for l in r), str(r[-3:]))
r = api(f"smelter add ore 12 {B}", 2.5)
st = sm(r)
check("haut fourneau : 10 Morceaux de sombracier au plus (m_maxOre 10), en marche", added(r) == 10 and st and st["queue"] == 10 and st["active"] and st["sec"] == 30.0, str(st))
t_blast = time.time()

# ---------------- fonderie : Charbon (20 max, 2 par produit), minerai (10 max), 30 s par produit
near(smel)
say(f".additem {STONE} 1", 0.8); say(f".additem {COAL} 25", 1.0); say(f".additem {COPPER_ORE} 2", 1.0)
r = api(f"smelter add {STONE} 1 {S}")
check("fonderie : la pierre est refusée (« Cela ne marchera pas »)", added(r) == 0 and any("marchera pas" in l for l in r), str(r))
r = api(f"smelter add fuel 25 {S}", 2.5)
st = sm(r)
check("fonderie : 20 Charbon au plus (m_maxFuel 20) puis « C'est plein »", added(r) == 20 and st and abs(st["fuel"] - 20) < 0.01 and any("plein" in l for l in r), str(r[-3:]))
check("fonderie : à l'arrêt sans minerai, combustible non consommé", st and not st["active"] and st["why"] == "noore", str(st))
r = api(f"smelter add ore 2 {S}", 1.5)
st = sm(r)
check("fonderie : 2 Minerai de cuivre en file, en marche", added(r) == 2 and st and st["queue"] == 2 and st["active"], str(st))
time.sleep(1.0)                                        # écriture asynchrone (PExecute)
check("état persisté (wowlheim_smelter_state)", any(r_.startswith(str(S)) for r_ in sql(f"select guid, queue from classiccharacters.wowlheim_smelter_state where guid={S}")), "")
t_smel = time.time()
time.sleep(32)
st = sm(api(f"smelter status {S}"))
el = time.time() - t_smel
check("fonderie : 1 Cuivre après 30 s (m_secPerProduct)", st and st["out"].get(COPPER) == 1 and st["queue"] == 1, str(st))
exp = 20 - el / 15.0                                   # 2 Charbon par 30 s = 1 par 15 s, consommé seconde par seconde
check("fonderie : Charbon consommé en continu (1 par 15 s)", st and abs(st["fuel"] - exp) < 0.35, f"{st and st['fuel']:.2f} attendu ~{exp:.2f}")

# clic sur la fonderie sans marteau : récupère le cuivre et ouvre le panneau, sans rien prendre dans le sac ;
# le minerai s'ajoute ensuite depuis le panneau, une unité par clic (interrupteur add_ore de Valheim)
say(f".additem {TIN_ORE} 1", 1.0)
notes, _ = s.use_gameobject(9110000 + ids["smelter"], S, 2.0)
st = sm(api(f"smelter status {S}"))
iv = inv()
check("clic sans marteau : produits récupérés (1 Cuivre dans le sac)", iv.get(COPPER) == 1 and st and not st["out"], str(iv))
check("clic sans marteau : le sac n'est pas vidé (Minerai d'étain toujours dans le sac)", iv.get(TIN_ORE) == 1 and st and not st["items"].get(TIN_ORE), f"{st} {notes}")
api(f"smelter add ore 1 {S}")
st = sm(api(f"smelter status {S}"))
check("panneau : Ajouter (1) met le minerai d'étain en file", st and st["items"].get(TIN_ORE) == 1 and TIN_ORE not in inv(), str(st))

# ---------------- sortie de fumée bouchée (SmokeSpawner.IsBlocked) : un plancher sur la cheminée arrête la fonderie
face(3.14159)
say(".build place 1 2.5 0 4.0", 1.2)                     # Plancher (wood_floor) posé sur le haut de la fonderie (4,24 m), cheminée à 4,58 m
time.sleep(2.5)
st1 = sm(api(f"smelter status {S}"))
time.sleep(3.0)
st2 = sm(api(f"smelter status {S}"))
check("fumée bouchée : fonderie à l'arrêt, combustible figé", st1 and st1["why"] == "smoke" and st2 and abs(st2["fuel"] - st1["fuel"]) < 0.01 and st2["bake"] == st1["bake"], f"{st1} / {st2}")

# ---------------- rouet et haut fourneau : produits après 30 s et récupération
near(wheel)
st = sm(api(f"smelter status {W}"))
n_exp = int((time.time() - t_wheel) // 30)
n_got = st["out"].get(LINEN, 0) if st else 0
check("rouet : Toile de lin produite (1 toutes les 30 s)", st and n_got >= 1 and n_got in (n_exp - 1, n_exp, n_exp + 1) and st["queue"] == 40 - n_got, f"{st} attendu ~{n_exp}")
before_l = inv().get(LINEN, 0)
r = api(f"smelter take {W}")
check("rouet : récupération de la Toile de lin dans le sac", inv().get(LINEN, 0) - before_l >= 1 and sm(r) and not sm(r)["out"], str(r[-2:]))
near(blast)
st = sm(api(f"smelter status {B}"))
el = time.time() - t_blast
n_exp = int(el // 30)
n_got = st["out"].get(BLACKMETAL, 0) if st else 0
check("haut fourneau : Sombracier produit (1 toutes les 30 s)", st and n_got >= 1 and n_got in (n_exp - 1, n_exp, n_exp + 1) and st["queue"] == 10 - n_got, f"{st} attendu ~{n_exp}")
exp = 20 - el / 15.0
check("haut fourneau : Charbon consommé en continu (1 par 15 s)", st and abs(st["fuel"] - exp) < 0.35, f"{st and st['fuel']:.2f} attendu ~{exp:.2f}")
before_b = inv().get(BLACKMETAL, 0)
r = api(f"smelter take {B}")
check("haut fourneau : récupération du Sombracier dans le sac", inv().get(BLACKMETAL, 0) - before_b >= 1 and sm(r) and not sm(r)["out"], str(r[-2:]))

# ---------------- four : produits (1 Charbon / 15 s) et récupération
near(kiln)
st = sm(api(f"smelter status {K}"))
n_exp = int((time.time() - t_kiln) // 15)
check("four : Charbon produit (1 toutes les 15 s)", st and st["out"].get(COAL, 0) in (n_exp - 1, n_exp, n_exp + 1) and st["queue"] == 25 - st["out"].get(COAL, 0), f"{st} attendu ~{n_exp}")
coal_before = inv().get(COAL, 0)
r = api(f"smelter take {K}")
st = sm(r)
got = inv().get(COAL, 0) - coal_before
check("four : récupération du Charbon dans le sac", got >= 2 and st and not st["out"], f"+{got} {r[-2:]}")

# ---------------- démolition au marteau : le contenu est rendu (Smelter.DropAllItems)
st = sm(api(f"smelter status {K}"))
wood_before = inv().get(WOOD, 0)
say(".build nocost off")
say(f".additem {HAMMER} 1", 1.2); time.sleep(0.5); s.equip_item(HAMMER); time.sleep(1.0)
api("mode remove")
s.use_gameobject(9110000 + ids["charcoal_kiln"], K, 2.0)
time.sleep(0.5)
iv = inv()
check("démolition du four : Bois en file rendu", K not in pieces() and iv.get(WOOD, 0) - wood_before >= st["queue"] - 1, f"+{iv.get(WOOD, 0) - wood_before} (file {st['queue']})")
check("démolition : état supprimé", not sql(f"select guid from classiccharacters.wowlheim_smelter_state where guid={K}"), "")
api("mode build")
say(".build nocost on")
say(".build grace 0")                                     # valeur de Valheim (pièces posées par un joueur)
s.close()
print("RÉSULTAT :", "OK" if ok else "ÉCHEC")
