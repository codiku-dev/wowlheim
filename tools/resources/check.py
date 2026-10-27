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
# identifiants imposes par le cahier, sous leur nom francais EXACT de Valheim (localization.txt ; 012 les reecrit depuis les prefabs)
for must, nm in ((9200001, "Bois"), (9200002, "Pierre"), (9200003, "Silex"), (9200004, "Résine"), (9200005, "Peau de cerf"), (9200006, "Bouts de cuir"),
                 (9200011, "Bois précieux"), (9200012, "Bois robuste"), (9200013, "Cuivre"), (9200014, "Étain"), (9200015, "Bronze"), (9200016, "Peau de troll"),
                 (9200021, "Fer"), (9200022, "Écorce ancienne"), (9200023, "Fragments d'os"), (9200024, "Entrailles"), (9200031, "Argent"),
                 (9200032, "Obsidienne"), (9200033, "Peau de loup"), (9200034, "Cristal"), (9200041, "Sombracier"), (9200042, "Lin"),
                 (9200043, "Toile de lin"), (9200044, "Peau de Lox")):
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
    if m["kind"] in ("crafted", "smelted", "pickable"):
        err("reference %d contient %s (%s : jamais en butin dans Valheim)" % (e, m["name"], m["kind"]))
for e, i, ch, g, mn, mx in cr_rows:
    if -mn not in refs or ch <= 0 or ch > 100 or i != -mn or mx not in (1, rules.ELITE_REPEAT):
        err("creature_loot_template entry %d : ligne de reference invalide" % e)
print("references : %d entrees, %d lignes ; lignes creature_loot_template ajoutees : %d ; erreurs de forme jusqu'ici : %d" % (len(refs), len(ref_rows), len(cr_rows), len(errors)))

# taux : materiaux de base 30-60 % (au moins une categorie principale), quantites variables
for m in rules.MATERIALS:
    if m["kind"] != "base":
        continue
    rs = rules.DROP_RULES.get(m["id"], [])
    if m["id"] in rules.NODE_ONLY:
        # Bois, Pierre : arbres / rochers / ramassables uniquement (iso Valheim) : AUCUNE ligne de butin ni regle autorisee
        if rs:
            err("%s : materiau « arbres/rochers uniquement » (rules.NODE_ONLY) avec une regle de butin" % m["name"])
        if any(i == m["id"] for e, i, ch, g, mn, mx in ref_rows):
            err("%s : materiau « arbres/rochers uniquement » present dans une reference de butin" % m["name"])
        continue
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
# seule exception aux critters (type 8) : le gibier cerf/biche (modele classify.CRITTER_GAME_MODELS) a qui 004 donne LootId = Entry
game_critters = sorted(e for e, f in classify.model_folders(DB).items() if f in classify.CRITTER_GAME_MODELS) or [0]
print("gibier critter autorise (modeles %s) : %d modeles" % (sorted(classify.CRITTER_GAME_MODELS), len(game_critters)))
bad = sql("select count(*) from creature_loot_template l join creature_template c on c.LootId=l.entry where l.item between %d and %d and l.mincountOrRef<0 "
          "and (c.`Rank` not in (0,1) or c.NpcFlags & ~3 or (c.CreatureType in (0,8,11) and not (c.CreatureType=8 and c.LootId=c.Entry and c.Entry in (%s))) or c.Civilian<>0 or c.ExtraFlags & 66560)"
          % (R0, R1, ",".join(map(str, game_critters))), DB)[0][0]
inst = sql("select count(distinct l.entry) from creature_loot_template l join creature_template c on c.LootId=l.entry join creature s on (s.id=c.Entry or "
           "(s.id=0 and s.guid in (select guid from creature_spawn_entry e where e.entry=c.Entry))) where l.item between %d and %d and l.mincountOrRef<0 and s.map not in (0,1) "
           "and c.Entry not in (%s)" % (R0, R1, ",".join(map(str, game_critters))), DB)[0][0]
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
# gibier ajoute par 004 (rules.GAME_SPAWNS, guid GAME_SPAWN_GUID) : absent du cache spawns.tsv (base du jeu d'origine) -> lu dans la base controlee
from common import zone_of as _zone_of
g_lo, g_hi = rules.GAME_SPAWN_GUID
game_rows = sql("select guid,id,map,position_x,position_y from creature where guid between %d and %d" % (g_lo, g_hi), DB)
for g, e, m, x, y in game_rows:
    z = _zone_of(int(m), float(x), float(y)) or (0, "?", 0, "?")
    sp[int(e)].append((int(m), float(x), float(y), z[0], z[1], z[2], z[3], int(g)))
    if int(e) not in ct or ct[int(e)]["why_not"]:
        err("gibier ajoute guid %s : entree %s non eligible au butin" % (g, e))
print("gibier ajoute aux zones de depart (guid %d-%d) : %d apparitions %s" % (g_lo, g_hi, len(game_rows),
      dict(collections.Counter((int(r[1]), (_zone_of(int(r[2]), float(r[3]), float(r[4])) or (0, "?"))[1]) for r in game_rows))))
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
            # famille de creature : (type, famille) ; famille 0 (kodos, cerfs, lezards...) -> dossier du modele 3D
            rs["families"].add((tpl["type"] if tpl["type"] != 8 else 1, tpl["family"] or tpl.get("model", "")) if tpl["type"] in (1, 8) else (tpl["type"], 0))
            rs["cats"][tpl["cat"]] += 1
            for (m, x, y, zid, zn, aid, an, g) in sp.get(tpl["entry"], []):
                rs["zones_all"][(m, zid, zn)] += 1
                if primary:
                    rs["zones"][(m, zid, zn)] += 1
                    rs["spawns"] += 1

# anciens noeuds GameObject aux modeles WoW : doivent avoir disparu (003/005/008)
old_t = int(sql("select count(*) from gameobject_template where entry between %d and %d" % (rules.OLD_NODE_ENTRY_MIN, rules.OLD_NODE_ENTRY_MAX), DB)[0][0])
old_s = int(sql("select count(*) from gameobject where id between %d and %d" % (rules.OLD_NODE_ENTRY_MIN, rules.OLD_NODE_ENTRY_MAX), DB)[0][0])
if old_t or old_s:
    err("anciens noeuds aux modeles WoW encore presents : %d modeles, %d apparitions" % (old_t, old_s))
print("anciens noeuds GameObject aux modeles WoW (9101001-9101999) : %d modeles, %d apparitions (attendu 0)" % (old_t, old_s))
# sources « N » = placements de Valheim (creatures-ressources et ramassables, C:\Wowlheim\data\wl_terrain\placements.json ; ecrits dans 012)
from nodes_common import read_placements
from common import zone_of
node_loot = collections.defaultdict(set)          # item -> types de placement
node_sp = collections.defaultdict(list)           # type -> [(map, zone)]
for pl in read_placements():
    node_sp[pl["key"]].append((pl["map"], pl["zone"]))
for pl in rules.PLACEMENTS:
    for it in pl["gives"]:
        node_loot[it].add(pl["key"])
print("placements de Valheim (placements.json) : %d, %d types" % (sum(len(v) for v in node_sp.values()), len(node_sp)))
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
if vend:
    err("%d materiaux Wowlheim vendus par des PNJ (Valheim : aucun vendeur de materiaux ; 006 doit etre vide)" % len(vend))
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
print("Legende : « types de sources » = parmi B/N/V combien existent ; « sources independantes » = familles de creatures distinctes + placement + vendeur. B=butin de famille (categories/modeles/familles distinctes) N=placement de Valheim (arbre/roche/filon/ramassable : types ; apparitions dans placements.json) V=vendeur (lignes ; aucun par conception) ; fonderie/rouet/recettes de Valheim non comptes ici")
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
    if m["kind"] in ("crafted", "smelted"):
        notes.append(("INFO", "%s : %s ; aucune source de butin/vendeur par conception (Valheim)." % (name, "fondu a la fonderie / au haut fourneau depuis le minerai des filons" if m["kind"] == "smelted" else "recette de Valheim / rouet")))
        continue
    if m["kind"] == "pickable":
        if not s["nsp"]:
            notes.append(("MANQUE", "%s : ramassable sans aucun placement." % name))
        continue
    if m["id"] in rules.NODE_ONLY:
        kinds_n = sorted(node_loot.get(m["id"], []))
        notes.append(("INFO" if len(kinds_n) >= 3 and s["nsp"] else "MANQUE",
                      "%s : arbres/rochers/ramassables UNIQUEMENT (aucun butin, aucun vendeur, iso Valheim) ; %d types de placement %s, %d placements ; "
                      "couverture zones x continent x faction : check_nodes.py" % (name, len(kinds_n), kinds_n, s["nsp"])))
        continue
    if m["kind"] == "passage":
        if s["kinds"] < 2:
            notes.append(("MANQUE", "%s (passage) : %d source(s) verifiee(s) < 2 exigees." % (name, s["kinds"])))
        continue
    if s["kinds"] < 3:
        missing = []
        if not s["n"]:
            missing.append("noeud")
        if not s["v"]:
            missing.append("vendeur (aucun par conception)")
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
notes.append(("NON VERIFIE", "Accessibilite reelle des zones (mmaps absentes), faction des zones (classification manuelle), aucun test en jeu : loot jamais tire par le serveur reel."))
notes.append(("NON VERIFIE", "Placements de Valheim (012) : non appliques a cette base de controle (002-006 seulement) ; leur forme est controlee par check_nodes.py."))
for sev in ("MANQUE", "LIMITE", "INFO", "NON VERIFIE"):
    for s, t in notes:
        if s == sev:
            print("[%s] %s" % (s, t))

sect("6. DEPARTS DE RACE : chaque materiau de palier 1 trouvable DANS la zone de depart (butin de creatures de la zone + placements de Valheim)")
T1_MATS = [m for m in rules.MATERIALS if m["tier"] == 1 and m["kind"] in ("base", "passage", "pickable")]
pl_zone = collections.Counter()
for k, v in node_sp.items():
    for (m, z) in v:
        pl_zone[(m, z, k)] += 1
loot_zone = collections.Counter()      # (map, zone, item) -> apparitions de creatures dont le butin contient l'objet
for lid, ref in lid_ref.items():
    items_r = {it for it, ch, mn, mx in refs.get(ref, [])}
    for tpl in info["groups"].get(lid, []):
        for (m, x, y, zid, zn, aid, an, g) in sp.get(tpl["entry"], []):
            for it in items_r:
                loot_zone[(m, zid, it)] += 1
START_MIN_B, START_MIN_N = 5, 3   # minimum dans la zone de depart : apparitions de creatures porteuses, ou placements (ramassables / arbres / roches)
print("cellule = B<apparitions de creatures dont le butin contient l'objet>/N<placements de Valheim qui le donnent> dans la zone ; « -- » = introuvable (butin < %d et placements < %d)" % (START_MIN_B, START_MIN_N))
print("%-30s " % "depart" + " ".join("%-13s" % m["name"][:13] for m in T1_MATS))
for mp, zid, label in rules.START_ZONES:
    cells = []
    for m in T1_MATS:
        b_ = loot_zone[(mp, zid, m["id"])]
        n_ = sum(pl_zone[(mp, zid, k)] for k in node_loot.get(m["id"], []))
        ok_ = b_ >= START_MIN_B or n_ >= START_MIN_N
        cells.append("%-13s" % (("B%d/N%d" % (b_, n_)) if ok_ else "-- B%d/N%d" % (b_, n_)))
        if not ok_:
            err("depart %s : %s (palier 1) introuvable dans la zone (butin %d, placements %d)" % (label, m["name"], b_, n_))
    print("%-30s " % label + " ".join(cells))

sect("RESULTAT")
if errors:
    print("ECHEC : %d erreur(s) de forme :" % len(errors))
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("Validations de forme : TOUTES OK (%d constats de couverture listes ci-dessus ; ce ne sont pas des erreurs de forme)." % len(notes))
