"""Controles automatiques des ressources Wowlheim.

usage : python check.py [--db BASE] [--baseline BASE_DE_REFERENCE] [--min-spawns N]
  --db        base ou les scripts 002..006 ont ete appliques (defaut classicmangos ; utiliser wl_scratch pour la validation)
  --baseline  base de reference SANS les scripts : verifie qu'aucune ligne existante n'a ete modifiee (compte + somme de controle)
Sorties : (1) validations de forme (miroir de LootStore::IsValidItemTemplate du serveur), (2) sources par ressource,
(3) zones par continent / faction, (4) couverture par palier, (5) liste explicite de ce qui NE PEUT PAS etre satisfait.
Code retour 1 si une validation de forme echoue ; les manques de couverture sont des constats, pas des erreurs de forme.
Rien n'est ecrit dans la base."""
import os, sys, argparse, collections
sys.stdout.reconfigure(encoding="utf8")
sys.path.insert(0, os.path.dirname(__file__))
from common import sql
import rules, classify

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="classicmangos")
ap.add_argument("--baseline", default=None)
ap.add_argument("--min-spawns", type=int, default=10, help="apparitions minimum pour qu'une zone compte comme source d'une ressource")
args = ap.parse_args()
DB = args.db
MIN_SP = args.min_spawns
errors = []
notes = []   # (gravite, texte) : constats de couverture


def err(msg):
    errors.append(msg)


def sect(t):
    print("\n" + "=" * 100 + "\n" + t + "\n" + "=" * 100)


R0, R1 = rules.REF_BASE, rules.REF_BASE + 99999

# ------------------------------------------------------------------ 1. validations de forme
sect("1. VALIDATIONS DE FORME (base : %s)" % DB)
items = {int(r[0]): r for r in sql("select entry,class,subclass,name,description,RequiredSkill,RequiredSkillRank,displayid,Quality,stackable,InventoryType,dmg_min1,dmg_max1,requiredspell,lockid from item_template where entry between 9200001 and 9299999", DB)}
exp_items = {m["id"] for m in rules.MATERIALS} | {t["id"] for t in rules.TOOLS}
if set(items) != exp_items:
    err("objets presents %s != attendus %s" % (sorted(set(items) ^ exp_items), ""))
for e, r in items.items():
    if r[4] != "Wowlheim":
        err("objet %d : description != Wowlheim" % e)
    if int(r[5]) or int(r[6]) or int(r[13]) or int(r[14]):
        err("objet %d : lie a une competence/sort/serrure (RequiredSkill/RequiredSkillRank/requiredspell/lockid)" % e)
print("objets 9200001-9299999 : %d (materiaux %d, outils %d), tous description=Wowlheim, aucune competence requise : %s"
      % (len(items), len(rules.MATERIALS), len(rules.TOOLS), "OK" if not errors else "ECHEC"))
for t in rules.TOOLS:
    r = items.get(t["id"])
    if r and not (int(r[1]) == 2 and float(r[12]) <= 16):
        err("outil %d : doit etre une arme (classe 2) a faibles degats" % t["id"])
for m in rules.MATERIALS:
    if m["id"] in items and rules.MAT[m["id"]]["name"] != items[m["id"]][3]:
        err("nom de l'objet %d different de rules.py" % m["id"])
# plages imposees par le cahier
for must, nm in ((9200001, "Bois"), (9200002, "Pierre"), (9200003, "Silex"), (9200004, "Résine"), (9200005, "Peau de cerf"), (9200006, "Chutes de cuir"),
                 (9200011, "Bois fin"), (9200012, "Bois de cœur"), (9200013, "Cuivre"), (9200014, "Étain"), (9200015, "Bronze"), (9200016, "Peau de troll"),
                 (9200021, "Fer"), (9200022, "Écorce ancienne"), (9200023, "Fragments d'os"), (9200024, "Entrailles"), (9200031, "Argent"),
                 (9200032, "Obsidienne"), (9200033, "Fourrure de loup"), (9200034, "Cristal"), (9200041, "Métal noir"), (9200042, "Lin"),
                 (9200043, "Fil de lin"), (9200044, "Peau de lox")):
    if must not in items or items[must][3] != nm:
        err("identifiant impose %d (%s) absent ou mal nomme" % (must, nm))

ref_rows = [(int(a), int(b), float(c), int(d), int(e), int(f)) for a, b, c, d, e, f in
            sql("select entry,item,ChanceOrQuestChance,groupid,mincountOrRef,maxcount from reference_loot_template where entry between %d and %d" % (R0, R1), DB)]
cr_rows = [(int(a), int(b), float(c), int(d), int(e), int(f)) for a, b, c, d, e, f in
           sql("select entry,item,ChanceOrQuestChance,groupid,mincountOrRef,maxcount from creature_loot_template where item between %d and %d and mincountOrRef<0" % (R0, R1), DB)]
refs = collections.defaultdict(list)
for e, i, ch, g, mn, mx in ref_rows:
    refs[e].append((i, ch, mn, mx))
    # miroir de IsValidItemTemplate
    if mn == 0 or i not in items or (ch == 0 and g == 0) or (ch != 0 and ch < 0.000001) or mx < mn or ch > 100 or ch < 0:
        err("reference %d item %d : ligne invalide (chance %s min %s max %s)" % (e, i, ch, mn, mx))
    t = (e - R0) // 1000
    cat = rules.ALL_CATS[((e - R0) % 1000) // 10]
    m = rules.MAT.get(i)
    if m is None:
        err("reference %d : objet %d n'est pas un materiau" % (e, i)); continue
    if not (m["tier"] == t or (m["tier"] == t - 1 and m["kind"] == "base")):
        err("reference %d (palier %d) contient %s (palier %d, %s) : hors palier / retour en arriere non autorise" % (e, t, m["name"], m["tier"], m["kind"]))
    if m["kind"] == "crafted":
        err("reference %d contient le bronze (fabrique, jamais en butin)" % e)
for e, i, ch, g, mn, mx in cr_rows:
    if -mn not in refs or ch <= 0 or ch > 100 or i != -mn or mx not in (1, rules.ELITE_REPEAT):
        err("creature_loot_template entry %d : ligne de reference invalide" % e)
print("references : %d entrees, %d lignes ; lignes creature_loot_template ajoutees : %d ; erreurs de forme jusqu'ici : %d" % (len(refs), len(ref_rows), len(cr_rows), len(errors)))

# taux : materiaux de base 30-60 % (au moins une categorie principale), quantites variables
for m in rules.MATERIALS:
    if m["kind"] != "base":
        continue
    rs = rules.DROP_RULES.get(m["id"], [])
    if not rs:
        if m["kind"] == "base":
            err("%s : aucune regle de butin" % m["name"])
        continue
    top = max(r[1] for r in rs)
    if not (30 <= top <= 60):
        err("%s : taux principal %s hors 30-60 %%" % (m["name"], top))
    if not any(r[3] > r[2] for r in rs if r[1] >= 30):
        err("%s : quantites non variables sur le taux principal" % m["name"])

# creatures : verification INDEPENDANTE de la selection (SQL direct, pas le code de generate.py)
bad = sql("select count(*) from creature_loot_template l join creature_template c on c.LootId=l.entry where l.item between %d and %d and l.mincountOrRef<0 "
          "and (c.`Rank` not in (0,1) or c.NpcFlags & ~3 or c.CreatureType in (0,8,11) or c.Civilian<>0 or c.ExtraFlags & 66560)" % (R0, R1), DB)[0][0]
inst = sql("select count(distinct l.entry) from creature_loot_template l join creature_template c on c.LootId=l.entry join creature s on (s.id=c.Entry or "
           "(s.id=0 and s.guid in (select guid from creature_spawn_entry e where e.entry=c.Entry))) where l.item between %d and %d and l.mincountOrRef<0 and s.map not in (0,1)" % (R0, R1), DB)[0][0]
shared = sql("select count(*) from (select c.LootId from creature_template c join creature_loot_template l on l.entry=c.LootId where l.item between %d and %d "
             "and l.mincountOrRef<0 group by c.LootId having count(*)>1) x" % (R0, R1), DB)[0][0]
if int(bad):
    err("%s lignes ajoutees sur des creatures rares/boss/PNJ/critters/totems" % bad)
if int(inst):
    err("%s LootId modifies appartiennent a des creatures presentes hors cartes 0/1 (instances/BG)" % inst)
print("verification SQL independante : lignes sur rang hors 0/1, PNJ, critters, totems : %s ; LootId ayant une creature hors continents : %s" % (bad, inst))
lid_users = sql("select c.LootId, count(*) n from creature_template c where c.LootId in (select entry from creature_loot_template where item between %d and %d and mincountOrRef<0) group by c.LootId having n>1" % (R0, R1), DB)
if lid_users:
    err("LootId partages entre plusieurs modeles : %s" % lid_users[:5])
print("LootId modifies partages entre plusieurs modeles : %d" % len(lid_users))

if args.baseline:
    for tbl, cond in (("creature_loot_template", "not (item between %d and %d and mincountOrRef<0)" % (R0, R1)),
                      ("reference_loot_template", "entry not between %d and %d" % (R0, R1)),
                      ("item_template", "entry not between 9200001 and 9299999"),
                      ("gameobject_template", "entry not between 9101001 and 9101999"),
                      ("gameobject_loot_template", "entry not between 9101001 and 9101999"),
                      ("npc_vendor", "item not between 9200001 and 9299999"),
                      ("gameobject", "guid not between %d and %d" % (rules.NODE_GUID_BASE, rules.NODE_GUID_MAX))):
        a = sql("select count(*) from %s where %s" % (tbl, cond), DB)[0][0]
        b = sql("select count(*) from %s where %s" % (tbl, cond), args.baseline)[0][0]
        pk = {"creature_loot_template": "entry,item", "reference_loot_template": "entry,item", "item_template": "entry", "gameobject_template": "entry",
              "gameobject_loot_template": "entry,item", "npc_vendor": "entry,item", "gameobject": "guid"}[tbl]
        ca = sql("select sum(crc32(concat_ws('|',%s))) from %s where %s" % (pk, tbl, cond), DB)[0][0]
        cb = sql("select sum(crc32(concat_ws('|',%s))) from %s where %s" % (pk, tbl, cond), args.baseline)[0][0]
        ok = (a == b and ca == cb)
        print("lignes hors plage Wowlheim identiques a %s : %-26s %s lignes (%s)" % (args.baseline, tbl, a, "OK" if ok else "DIFFERENT %s/%s" % (a, b)))
        if not ok:
            err("%s : lignes existantes modifiees par rapport a %s" % (tbl, args.baseline))

# ------------------------------------------------------------------ 2. approvisionnement par ressource
info = classify.load(DB)
ct = info["ct"]
sp = info["spawns"]
lid_ref = {e: -mn for e, i, ch, g, mn, mx in cr_rows}        # lootid -> reference
res_sources = {m["id"]: dict(templates=set(), spawns=0, families=set(), zones=collections.defaultdict(int), zones_all=collections.defaultdict(int),
                             cats=collections.defaultdict(int)) for m in rules.MATERIALS}
for lid, ref in lid_ref.items():
    t_ref = (ref - R0) // 1000
    for it, ch, mn, mx in refs.get(ref, []):
        rs = res_sources[it]
        primary = rules.MAT[it]["tier"] == t_ref
        for tpl in info["groups"].get(lid, []):
            rs["templates"].add(tpl["entry"])
            rs["families"].add((tpl["type"], tpl["family"]) if tpl["type"] in (1,) else (tpl["type"], 0))
            rs["cats"][tpl["cat"]] += 1
            for (m, x, y, zid, zn, aid, an, g) in sp.get(tpl["entry"], []):
                rs["zones_all"][(m, zid, zn)] += 1
                if primary:
                    rs["zones"][(m, zid, zn)] += 1
                    rs["spawns"] += 1

node_t = {int(r[0]): r for r in sql("select entry,name,type,data0,data1,data3 from gameobject_template where entry between 9101001 and 9101999", DB)}
node_loot = collections.defaultdict(set)
for e, it in sql("select entry,item from gameobject_loot_template where entry between 9101001 and 9101999", DB):
    node_loot[int(it)].add(int(e))
for e, r in node_t.items():
    if int(r[2]) != 3:
        err("noeud %d : type %s != 3 (CHEST)" % (e, r[2]))
    if int(r[3]) != 0:
        err("noeud %d : lockId %s != 0 (aucun verrou de metier autorise)" % (e, r[3]))
    if int(r[4]) != e:
        err("noeud %d : table de butin %s != entry" % (e, r[4]))
import json
dn = json.load(open(os.path.join(os.path.dirname(__file__), "cache", "gobj_display.json")))
for e, r in node_t.items():
    d = sql("select displayId from gameobject_template where entry=%d" % e, DB)[0][0]
    if d not in dn:
        err("noeud %d : displayId %s absent de GameObjectDisplayInfo.dbc" % (e, d))
print("noeuds : %d modeles (type 3, data0=0 sans verrou, displayId present dans GameObjectDisplayInfo.dbc : verifie)" % len(node_t))
node_sp = collections.defaultdict(list)
for g, e, m, x, y in sql("select guid,id,map,position_x,position_y from gameobject where guid between %d and %d" % (rules.NODE_GUID_BASE, rules.NODE_GUID_MAX), DB):
    node_sp[int(e)].append((int(m), float(x), float(y)))
from common import zone_of
# apparitions de noeuds hors plage de guid ou dans une plage non prevue
for e, v in node_sp.items():
    if e not in node_t:
        err("apparition de noeud d'entree inconnue %d" % e)
node_zone = collections.defaultdict(lambda: collections.defaultdict(int))     # item -> (map,zone) -> n
for e, v in node_sp.items():
    for (m, x, y) in v:
        z = zone_of(m, x, y)
        for it in [i for i, es in node_loot.items() if e in es]:
            node_zone[it][(m, z[0], z[1])] += 1
vend = collections.defaultdict(list)
for e, it in sql("select entry,item from npc_vendor where item between 9200001 and 9299999", DB):
    vend[int(it)].append(int(e))
vend_zone = collections.defaultdict(lambda: collections.defaultdict(int))
for it, es in vend.items():
    for e in set(es):
        s = sp.get(e, [])
        if s:
            (m, zid, zn), _n = collections.Counter((a[0], a[3], a[4]) for a in s).most_common(1)[0]
            vend_zone[it][(m, zid, zn)] += 1
for it in vend:
    if rules.MAT[it]["kind"] != "base":
        err("le materiau %d (%s) est vendu alors qu'il n'est pas de base" % (it, rules.MAT[it]["name"]))
conv_for = collections.defaultdict(list)
for st, ing, out, why in rules.CONVERSIONS:
    conv_for[out[0]].append((st, ing, why))
CONT = {0: "Royaumes de l'Est", 1: "Kalimdor"}


def zsets(zd, thr=1):
    """-> {map: {zone_id: (name, n)}} pour n >= thr"""
    out = {0: {}, 1: {}}
    for (m, zid, zn), n in zd.items():
        if n >= thr and m in out and zid != 0:
            out[m][zid] = (zn, n)
    return out


def fac_count(zs):
    a = sum(1 for z in zs if rules.zone_faction(z) in ("A", "C"))
    h = sum(1 for z in zs if rules.zone_faction(z) in ("H", "C"))
    return a, h


sect("2. SOURCES PAR RESSOURCE (donnees reelles de la base %s ; zone = fichiers .map ; seuil %d apparitions)" % (DB, MIN_SP))
print("Legende : « types de sources » = parmi B/N/V combien existent ; « sources independantes » = familles de creatures distinctes + noeud + vendeur. B=butin de famille (categories/modeles/familles distinctes) N=noeud (modeles; apparitions en base) V=vendeur (lignes) C=conversion (PROPOSEE, non implementee : n'est PAS comptee)")
print("%-18s %-3s %-26s %-18s %-9s %-9s %s" % ("ressource", "pal", "B cat/modeles/familles", "N modeles/spawns", "V lignes", "C prop.", "types de sources / sources independantes"))
summary = {}
for m in rules.MATERIALS:
    rs = res_sources[m["id"]]
    b = len(rs["templates"]) > 0
    nmod = len(node_loot.get(m["id"], []))
    nsp = sum(len(node_sp.get(e, [])) for e in node_loot.get(m["id"], []))
    n_ok = nmod > 0
    v = len(vend.get(m["id"], []))
    c = len(conv_for.get(m["id"], []))
    kinds = int(b) + int(n_ok) + int(v > 0)
    indep = len(rs["families"]) + int(n_ok) + int(v > 0)
    summary[m["id"]] = dict(b=b, n=n_ok, nsp=nsp, v=v, c=c, kinds=kinds, fam=len(rs["families"]), cats=len(rs["cats"]), indep=indep)
    print("%-18s T%-2d %2d cat / %4d mod / %2d fam   %2d mod / %3d    %3d       %d        types %d/3, independantes %d %s" % (
        m["name"], m["tier"], len(rs["cats"]), len(rs["templates"]), len(rs["families"]), nmod, nsp, v, c, kinds, indep,
        ("(+%d conv. proposee)" % c) if c else ""))

sect("3. ZONES PAR CONTINENT ET PAR FACTION (butin de mobs de PALIER NATIF uniquement ; retour en arriere exclu)")
print("zones = zones comptant >= %d apparitions de creatures dont le butin contient la ressource. A/H = zones accessibles a l'Alliance/Horde (zones contestees comptees pour les deux ; classification manuelle rules.ZONE_FACTION)." % MIN_SP)
print("%-18s %-3s | %-26s | %-26s | %s" % ("ressource", "pal", "Royaumes de l'Est (zones, A, H)", "Kalimdor (zones, A, H)", "constat"))
zone_fail = []
for m in rules.MATERIALS:
    rs = res_sources[m["id"]]
    if not rs["templates"]:
        continue
    zs = zsets(rs["zones"], MIN_SP)
    cols, flag = [], []
    for mp in (0, 1):
        n = len(zs[mp])
        a, h = fac_count(zs[mp])
        cols.append("%2d zones (A %2d, H %2d)" % (n, a, h))
        if n < 3:
            flag.append("%s < 3 zones" % CONT[mp][:3])
            zone_fail.append((m, mp, n, zs[mp]))
    print("%-18s T%-2d | %-26s | %-26s | %s" % (m["name"], m["tier"], cols[0], cols[1], "; ".join(flag) or "ok"))

sect("4. COUVERTURE PAR PALIER (toutes ressources du palier confondues, butin de mobs natif)")
tier_zones = {}
for t in range(1, 6):
    zd = collections.defaultdict(int)
    for m in rules.MATERIALS:
        if m["tier"] == t and m["kind"] == "base":
            for k, n in res_sources[m["id"]]["zones"].items():
                zd[k] = max(zd[k], n)
    zs = zsets(zd, MIN_SP)
    tier_zones[t] = zs
    print("palier %d (%s) : EK %d zones %s | Kalimdor %d zones %s" % (t, rules.TIERS[t - 1][1], len(zs[0]), sorted(v[0] for v in zs[0].values()),
                                                                   len(zs[1]), sorted(v[0] for v in zs[1].values())))
    for mp in (0, 1):
        if len(zs[mp]) < 3:
            notes.append(("MANQUE", "Palier %d : seulement %d zone(s) sur %s avec >= %d apparitions de creatures lachant une ressource de base du palier." % (t, len(zs[mp]), CONT[mp], MIN_SP)))

sect("5. CE QUI NE PEUT PAS ETRE SATISFAIT AVEC LES DONNEES DU JEU (ou n'est pas verifie)")
for m in rules.MATERIALS:
    s = summary[m["id"]]
    rs = res_sources[m["id"]]
    name = m["name"]
    if m["kind"] == "crafted":
        notes.append(("LIMITE", "%s : materiau fabrique, aucune source de butin/noeud/vendeur par conception ; sa source = conversion cuivre+etain (proposee, a coder). Compte %d source(s) verifiee(s)." % (name, s["kinds"])))
        continue
    if m["kind"] == "passage":
        if s["kinds"] < 2:
            notes.append(("MANQUE", "%s (passage) : %d source(s) verifiee(s) < 2 exigees." % (name, s["kinds"])))
        if s["nsp"] == 0:
            notes.append(("LIMITE", "%s (passage) : le noeud existe mais n'a aucune apparition de production (seulement des echantillons de validation en Elwynn/Durotar)." % name))
        continue
    if s["kinds"] < 3:
        missing = []
        if not s["n"]:
            missing.append("noeud")
        if not s["v"]:
            missing.append("vendeur")
        if not s["b"]:
            missing.append("butin de famille")
        notes.append(("LIMITE", "%s (T%d) : %d/3 sources verifiees en base (manque : %s)%s ; %d familles distinctes de creatures ; %s" % (
            name, m["tier"], s["kinds"], ", ".join(missing),
            (" ; conversion proposee x%d (non implementee)" % s["c"]) if s["c"] else "", s["fam"],
            "proposition : noeud de carcasse/depouille (gameobject) ou conversion serveur" if not s["n"] else "")))
    if s["fam"] < 3:
        notes.append(("MANQUE", "%s : seulement %d famille(s)/type(s) de creatures distincts en butin (cahier : pas de goulot unique)" % (name, s["fam"])))
    if s["n"] and s["nsp"] == 0:
        notes.append(("LIMITE", "%s : noeuds definis mais aucune apparition en base." % name))
for m, mp, n, zs in zone_fail:
    notes.append(("MANQUE", "%s (T%d) : %d zone(s) sur %s (< 3)%s ; zones : %s. Proposition : elargir la regle a d'autres categories ou ajouter des noeuds de production." % (
        m["name"], m["tier"], n, CONT[mp], "", ", ".join(v[0] for v in zs.values()) or "aucune")))
# vendeurs : zones par palier et continent
for t in range(1, 6):
    for mp in (0, 1):
        vz = set()
        for m in rules.MATERIALS:
            if m["tier"] == t and m["kind"] == "base":
                vz |= {k for k in vend_zone[m["id"]] if k[0] == mp}
        if len(vz) < 3:
            notes.append(("LIMITE", "Vendeur de secours palier %d sur %s : %d zone(s) seulement (%s) : il manque des vendeurs « General/Trade » dans des zones de ce palier." % (t, CONT[mp], len(vz), ", ".join(sorted(k[2] for k in vz)) or "aucune")))
notes.append(("NON VERIFIE", "Accessibilite reelle des zones (mmaps absentes), faction des zones (classification manuelle), aucun test en jeu : loot jamais tire par le serveur reel."))
notes.append(("NON VERIFIE", "Verrouillage des noeuds : data0=0 -> sans code serveur un noeud est recoltable a la main (decision du cahier : controle de l'outil dans le code serveur)."))
notes.append(("NON VERIFIE", "Apparitions de noeuds : seule la validation (Elwynn/Durotar/Dun Morogh) est generee ; les zones de production des paliers 2-5 n'ont pas de noeuds."))
notes.append(("NON VERIFIE", "Sol sous les noeuds : z lu sur des creatures terrestres, jamais verifie contre le terrain."))
for sev in ("MANQUE", "LIMITE", "NON VERIFIE"):
    for s, t in notes:
        if s == sev:
            print("[%s] %s" % (s, t))

sect("RESULTAT")
if errors:
    print("ECHEC : %d erreur(s) de forme :" % len(errors))
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("Validations de forme : TOUTES OK (%d constats de couverture listes ci-dessus ; ce ne sont pas des erreurs de forme)." % len(notes))
