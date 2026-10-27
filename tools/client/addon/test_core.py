"""Teste l'addon Wowlheim hors du jeu avec lupa (Lua 5.4 : on fournit les fonctions 5.0 manquantes).
  1. WowlheimCore.lua (logique pure : protocole, inventaire, categories, pose continue) ;
  2. WowlheimData.lua (genere) : forme des donnees ;
  3. Wowlheim.lua charge dans une API WoW SIMULEE (CreateFrame, sacs, marteau...) : clics, molette, messages serveur ;
     controles du mode construction (liaisons temporaires, clic droit = menu, clic milieu = removeguid, molette = rotation).
     La simulation ne prouve rien sur le comportement du vrai client 1.12 (jamais charge en jeu) ; elle attrape les erreurs
     d'execution evidentes (nil, fautes de frappe) et verifie les commandes envoyees au serveur.
Lancer avec le venv de tools/client : tools/client/.venv/Scripts/python.exe tools/client/addon/test_core.py"""
import os, sys, re
from lupa import LuaRuntime

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.join(HERE, "Wowlheim")


def read(name):
    return open(os.path.join(ADDON, name), encoding="utf-8").read()


def new_lua():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute("table.getn = function(t) return #t end; math.mod = math.fmod")
    return lua


lua = new_lua()
lua.execute(read("WowlheimData.lua"))
lua.execute(read("WowlheimCore.lua"))
core = lua.eval("WowlheimCore")
data = lua.eval("WowlheimData")
ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(("[OK]   " if cond else "[ÉCHEC]"), name, detail)


# --- protocole -------------------------------------------------------------------------------------
m = core.ParseLine("[WL]P|1|Plancher|floor|200|1|0|9200001:2")
check("ligne P", m["type"] == "P" and m["id"] == 1 and m["name"] == "Plancher" and m["supports"] and not m["bench"] and m["cost"][1]["item"] == 9200001 and m["cost"][1]["count"] == 2)
m = core.ParseLine("[WL]P|7|Forge|forge|400|0|1|9200002:20,9200013:5")
check("ligne P avec deux coûts + établi requis", m["bench"] and m["cost"].n == 2 and m["cost"][2]["item"] == 9200013)
m = core.ParseLine("[WL]I|9200001:22,9200002:128")
check("inventaire", m["type"] == "I" and m["items"].n == 2 and m["items"][2]["count"] == 128)
m = core.ParseLine("[WL]I|")
check("inventaire vide", m["type"] == "I" and m["items"].n == 0)
m = core.ParseLine("[WL]M|Pièce Plancher posée (id 9500137)")
check("message M", m["type"] == "M" and "posée" in m["text"])
m = core.ParseLine("[WL]D|place|1")
check("fin de réponse", m["type"] == "D" and m["command"] == "place" and m["ok"])
m = core.ParseLine("[WL]S|9500143|1|100")
check("station", m["usable"] and m["cover"] == 100)
m = core.ParseLine("[WL]C|101|Hache en silex|workbench|9201011:1|9200001:4,9200003:3,9200004:1")
check("recette", m["name"] == "Hache en silex" and m["outItem"] == 9201011 and m["ingredients"].n == 3)
check("ligne hors protocole ignorée", core.ParseLine("Welcome to the server") is None)
check("commande de pose (ancienne)", core.PlaceCommand(1, 3, 0, 0, 90) == ".build api place 1 3 0 0 90", core.PlaceCommand(1, 3, 0, 0, 90))
check("commande select", core.SelectCommand(12, 3) == ".build api select 12 3")
check("commande mode", core.ModeCommand("repair") == ".build api mode repair")
cost = core.ParseItems("9200001:2")
inv = core.ParseItems("9200001:1")
afford, missing = core.CanAfford(cost, inv)
check("CanAfford : manque 1 Bois", (not afford) and missing[1]["have"] == 1 and missing[1]["need"] == 2)
afford, missing = core.CanAfford(cost, core.ParseItems("9200001:5"))
check("CanAfford : suffisant", afford)

# --- inventaire des sacs ---------------------------------------------------------------------------
check("id depuis un lien", core.ItemIdFromLink("|cffffffff|Hitem:9200001:0:0:0|h[Bois]|h|r") == 9200001)
check("lien nil", core.ItemIdFromLink(None) is None)
bags = lua.eval("""{
  [0] = { [1] = {"|Hitem:9200001:0:0:0|h[Bois]|h", 20}, [3] = {"|Hitem:9200002:0:0:0|h[Pierre]|h", 5} },
  [1] = { [2] = {"|Hitem:9200001:0:0:0|h[Bois]|h", 7}, [4] = {"|Hitem:6948:0:0:0|h[Pierre de foyer]|h", 1} },
}""")
api = lua.eval("""function(bags) return {
  numSlots = function(b) if bags[b] then return 16 end return 0 end,
  link = function(b, s) local x = bags[b] and bags[b][s]; return x and x[1] end,
  count = function(b, s) local x = bags[b] and bags[b][s]; return x and x[2] end } end""")(bags)
counts = core.CountBags(api)
check("comptage des sacs (Bois sur 2 sacs)", counts[9200001] == 27 and counts[9200002] == 5 and counts[6948] == 1, str(dict(counts)))
allok, rows = core.Affordability(lua.eval("{ {9200001, 10}, {9200002, 6} }"), counts)
check("Affordability : pierre insuffisante", (not allok) and rows.n == 2 and rows[1]["ok"] and rows[1]["have"] == 27 and (not rows[2]["ok"]) and rows[2]["have"] == 5)
allok, rows = core.Affordability(lua.eval("{ {9200001, 27} }"), counts)
check("Affordability : juste assez", allok)

# --- donnees et categories -------------------------------------------------------------------------
cats = data.categories
check("5 catégories, Construction en 3", cats[5] == "Meuble" and cats[3] == "Construction")
pieces = data.pieces
n_pieces = lua.eval("function(t) return #t end")(pieces)
good_shape = True
for i in range(1, n_pieces + 1):
    p = pieces[i]
    if not (p["id"] and 1 <= p["cat"] <= 5 and p["name"] and p["icon"] is not None and p["costs"] is not None):
        good_shape = False
    st = p["station"]
    if st and not data.stations[st]:   # toute station citée doit avoir un nom (Table de fabrication, Forge, Tailleur de pierre, Table d artisan…)
        good_shape = False
    c = p["costs"]
    j = 1
    while c[j] is not None:
        if not data["items"][c[j][1]]:
            good_shape = False
        j += 1
    if j - 1 > 6:
        good_shape = False  # l encadre affiche 6 ressources au plus
check("WowlheimData : %d pièces bien formées (station connue, objets connus, <= 6 coûts)" % n_pieces, good_shape)
div = core.CategoryEntries(pieces, 1)
check("Divers commence par Réparer puis Démolir", div[1]["special"] == "repair" and div[2]["special"] == "remove" and div[3]["cat"] == 1)
cons = core.CategoryEntries(pieces, 3)
check("Construction : uniquement cat 3, sans outils", cons.n > 0 and all(cons[i]["cat"] == 3 for i in range(1, cons.n + 1)))
total = sum(core.CategoryEntries(pieces, c).n for c in range(1, 6))
check("toutes les pièces sont réparties (+2 outils)", total == n_pieces + 2, "%d vs %d" % (total, n_pieces + 2))
check("MaxScroll", core.MaxScroll(34, 10, 4) == 0 and core.MaxScroll(41, 10, 4) == 1 and core.MaxScroll(0, 10, 4) == 0)

# --- etat du marteau -------------------------------------------------------------------------------
check("rotation modulo 16", core.RotStep(15, 1) == 0 and core.RotStep(0, -1) == 15 and core.RotStep(3, 1) == 4)
check("rotation en degrés", core.RotDegrees(3) == 67.5)
st = core.NewState()
cmds = core.Rotate(st, 1)
check("rotation sans pièce : rien à envoyer", cmds.n == 0 and st.rot == 1)
cmds, use = core.ChoosePiece(st, 12)
check("choisir une pièce : select avec la rotation courante + ciblage", cmds.n == 1 and cmds[1] == ".build api select 12 1" and use and st.continuous and st.pending)
cmds = core.Rotate(st, -2)
check("rotation avec pièce : renvoie select", cmds.n == 1 and cmds[1] == ".build api select 12 15")
check("succès D|place|1 => relance", core.OnServerMessage(st, core.ParseLine("[WL]D|place|1")) == "relaunch" and not st.pending)
check("doublon M posée sans ciblage en cours => pas de 2e relance", core.OnServerMessage(st, core.ParseLine("[WL]M|Pièce Mur posée")) is None)
st.pending = 1
check("succès M « posée » => relance", core.OnServerMessage(st, core.ParseLine("[WL]M|Pièce Mur posée (id 5)")) == "relaunch")
st.pending = 1
check("message neutre => pas de relance", core.OnServerMessage(st, core.ParseLine("[WL]M|Pièce choisie : Mur")) is None and st.pending)
check("refus D|place|0 => la pièce reste choisie, ciblage relancé (Valheim)", core.OnServerMessage(st, core.ParseLine("[WL]D|place|0")) == "relaunch"
      and st.continuous and not st.pending)
st.pending = 1
check("refus E| (trop fatigué) pendant une pose => relance aussi", core.OnServerMessage(st, core.ParseLine("[WL]E|Vous êtes trop fatigué.")) == "relaunch")
cmds = core.ChooseMode(st, "remove")
check("Démolir : mode remove", cmds.n == 1 and cmds[1] == ".build api mode remove" and st.mode == "remove" and not st.continuous)
cmds = core.Rotate(st, 1)
check("rotation en mode démolir : rien", cmds.n == 0)
cmds, use = core.ChoosePiece(st, 7)
check("choisir une pièce depuis Démolir : mode build puis select", cmds.n == 2 and cmds[1] == ".build api mode build" and cmds[2] == ".build api select 7 0")
core.ChooseMode(st, "repair")
cmds = core.Cancel(st)
check("annuler (Échap) en mode réparer : le mode reste « repair », rien à envoyer", cmds.n == 0 and st.mode == "repair" and not st.continuous)
check("rappel du mode : « Mode : Réparer » marteau équipé, rien marteau rangé", core.ModeBanner(st, 1) == "Mode : Réparer" and core.ModeBanner(st, None) is None)
core.ChooseMode(st, "remove")
check("rappel du mode : « Mode : Démolir »", core.ModeBanner(st, 1) == "Mode : Démolir")
cmds, use = core.ChoosePiece(st, 3)
check("seul le choix d'une pièce repasse en build ; plus de rappel", cmds[1] == ".build api mode build" and st.mode == "build" and core.ModeBanner(st, 1) is None)
check("fantôme natif : 9110000 + pièce", core.PlaceObjectId(st) == 9110003 and core.PlaceObjectId(core.NewState()) is None)
cmds = core.Cancel(st)
check("annuler en mode build : rien à envoyer", cmds.n == 0)
# --- menu masqué pendant la pose (Valheim) : rappel de la pièce, clic droit = menu ---------------------
check("rotation lisible", core.RotText(0) == "0" and core.RotText(1) == "22,5" and core.RotText(4) == "90" and core.RotText(3) == "67,5")
pb = core.NewState()
check("rappel de pose : rien sans pièce", core.PlaceBanner(pb, 1, False, "Mur") is None)
core.ChoosePiece(pb, 12)
core.Rotate(pb, 1)
check("rappel de pose : nom + rotation, menu masqué", core.PlaceBanner(pb, 1, False, "Mur") == "Mur  -  Rotation : 22,5°", str(core.PlaceBanner(pb, 1, False, "Mur")))
check("rappel de pose : nom inconnu => « Pièce <id> »", core.PlaceBanner(pb, 1, False, None).startswith("Pièce 12"))
check("rappel de pose : rien menu ouvert / marteau rangé", core.PlaceBanner(pb, 1, True, "Mur") is None and core.PlaceBanner(pb, None, False, "Mur") is None)
core.Cancel(pb)
check("rappel de pose : rien après annulation", core.PlaceBanner(pb, 1, False, "Mur") is None)
core.ChoosePiece(pb, 12)
core.ChooseMode(pb, "remove")
check("rappel de pose : rien en Démolir (rappel du mode à la place)", core.PlaceBanner(pb, 1, False, "Mur") is None and core.ModeBanner(pb, 1) == "Mode : Démolir")
rc = core.NewState()
check("clic droit court, construction, menu masqué, sans ciblage => menu", core.RightClickAction(rc, 1, None, None, False, 0.1) == "menu")
check("clic droit long (caméra) => rien", core.RightClickAction(rc, 1, None, None, False, 0.8) is None)
check("clic droit menu déjà ouvert => rien", core.RightClickAction(rc, 1, None, None, True, 0.1) is None)
check("clic droit marteau rangé => rien", core.RightClickAction(rc, None, None, None, False, 0.1) is None)
check("clic droit qui annule le ciblage => fin de pose (pas de menu)", core.RightClickAction(rc, 1, 1, None, False, 0.1) == "cancel")
check("clic droit, ciblage toujours actif => rien", core.RightClickAction(rc, 1, 1, 1, False, 0.1) is None)
core.ChooseMode(rc, "repair")
check("clic droit en Réparer / Démolir (vise une pièce) => rien", core.RightClickAction(rc, 1, None, None, False, 0.1) is None)
# --- un seul message par refus (notification + M| + D|place|0) ---------------------------------------
ns = core.NewNotify()
st.pending = 1
refus = core.ParseLine("[WL]M|Pose refusée : il faut Table de fabrication à moins de 10 m.")
check("refus de pose : ligne de pose", core.IsPlaceLine(st, refus) and core.IsPlaceLine(st, core.ParseLine("[WL]D|place|0"))
      and not core.IsPlaceLine(st, core.ParseLine("[WL]M|Recettes d'établi :")))
n = core.NotifyLine(ns, st, refus, None, 10)
check("refus de pose : texte du serveur, en erreur, affiché par l'addon (le serveur ne notifie plus)", n and n["text"] == refus["text"] and n["error"] and not n["notified"])
check("refus de pose : même texte reçu à nouveau => ignoré", core.NotifyLine(ns, st, core.ParseLine("[WL]E|Pose refusée : il faut Table de fabrication à moins de 10 m."), None, 10.5) is None)
check("D|place|0 : rien à afficher", core.NotifyLine(ns, st, core.ParseLine("[WL]D|place|0"), None, 10.6) is None)
check("même refus plus tard (nouvel essai) : affiché", core.NotifyLine(ns, st, refus, None, 20) is not None)
n = core.NotifyLine(ns, st, core.ParseLine("[WL]E|Cette pièce ne vous appartient pas."), None, 21)
check("E| de démolition (non sollicité) : affiché par l'addon", n["error"] and not n["notified"])
n = core.NotifyLine(ns, st, core.ParseLine("[WL]E|commande inconnue"), lua.eval("{ cmd = 'mode' }"), 22)
check("E| réponse à une commande : non notifié", n["error"] and not n["notified"])
n = core.NotifyLine(ns, st, core.ParseLine("[WL]M|Pièce Mur posée (id 5)"), None, 23)
check("pose réussie : message normal", n and not n["error"] and not n["notified"])
st.pending = None
check("fonderie : libellé « Cuivre x4 »", core.OutputLabel("Cuivre", 4) == "Cuivre x4")
check("relance après la recharge du marteau", core.RelaunchTime(100, 99.5, 1.5) == 101.05 and core.RelaunchTime(100, 0, 0) == 100.25)

# --- protocole : fabrication et fonderie -----------------------------------------------------------
m = core.ParseLine("[WL]C|99|Marteau||9201100:1|9200001:3,9200002:2|1")
check("recette à la main (station vide)", m["type"] == "C" and m["station"] == "" and m["outItem"] == 9201100 and m["outCount"] == 1 and m["minLevel"] == 1 and m["ingredients"].n == 2)
m = core.ParseLine("[WL]C|106|Pioche en fer|forge|9201032:1|9200001:3,9200021:20|2")
check("recette de forge niveau 2", m["station"] == "forge" and m["minLevel"] == 2)
m = core.ParseLine("[WL]S|9500143|0|40|2")
check("station : exposée, niveau 2", (not m["usable"]) and m["cover"] == 40 and m["level"] == 2)
m = core.ParseLine("[WL]SM|9500200|smelter|Fonderie|3|10|12.50|20|9200051|12.3|30|1|ok|9200060:2,9200064:1|9200013:4")
check("ligne SM (fonderie)", m["type"] == "SM" and m["guid"] == 9500200 and m["kind"] == "smelter" and m["name"] == "Fonderie" and m["queue"] == 3
      and m["maxOre"] == 10 and m["fuel"] == 12.5 and m["maxFuel"] == 20 and m["fuelItem"] == 9200051 and abs(m["bake"] - 12.3) < 1e-9
      and m["secPerProduct"] == 30 and m["active"] and m["why"] == "ok" and m["queueItems"].n == 2 and m["queueItems"][2]["item"] == 9200064
      and m["output"].n == 1 and m["output"][1]["count"] == 4)
sm_kiln = core.ParseLine("[WL]SM|9500201|charcoal_kiln|Four à charbon|0|25|0.00|0|0|0.0|15|0|noore||")
check("ligne SM (four à charbon vide, listes vides)", sm_kiln["kind"] == "charcoal_kiln" and sm_kiln["maxFuel"] == 0 and not sm_kiln["active"]
      and sm_kiln["why"] == "noore" and sm_kiln["queueItems"].n == 0 and sm_kiln["output"].n == 0)
check("ligne A (unités ajoutées)", core.ParseLine("[WL]A|5")["added"] == 5)
check("commandes de fabrication", core.RecipesCommand() == ".build api recipes" and core.StationCommand() == ".build api station" and core.CraftCommand(101) == ".build api craft 101")
check("commandes de fonderie", core.SmelterStatusCommand(None) == ".build api smelter status" and core.SmelterStatusCommand(12) == ".build api smelter status 12"
      and core.SmelterAddCommand("ore", 1, 12) == ".build api smelter add ore 1 12" and core.SmelterAddCommand("fuel", 3, None) == ".build api smelter add fuel 3"
      and core.SmelterTakeCommand(12) == ".build api smelter take 12")

# --- canal : quelle commande une ligne concerne-t-elle ? ---------------------------------------------
check("nom de commande", core.CommandName(".build api smelter status 12") == "smelter" and core.CommandName("bonjour") is None)
ch = core.NewChannel()
core.ChannelPush(ch, ".build api station", True, 10)
core.ChannelPush(ch, ".build api recipes", True, 10)
core.ChannelPush(ch, ".build api craft 99", False, 10)
e = core.ChannelRoute(ch, core.ParseLine("[WL]M|Établi 5 : niveau 1"), 10.1)
check("canal : M| rattaché à la 1re commande en attente (station, silencieuse)", e["cmd"] == "station" and e["silent"])
e = core.ChannelRoute(ch, core.ParseLine("[WL]D|station|1"), 10.1)
check("canal : D|station retire station", e["cmd"] == "station" and ch.n == 2 and core.ChannelHas(ch, "recipes") and not core.ChannelHas(ch, "station"))
core.ChannelRoute(ch, core.ParseLine("[WL]D|recipes|1"), 10.2)
e = core.ChannelRoute(ch, core.ParseLine("[WL]M|Fabriqué : 1 x Marteau."), 10.3)
check("canal : M| de craft non silencieux", e["cmd"] == "craft" and not e["silent"])
core.ChannelRoute(ch, core.ParseLine("[WL]D|craft|1"), 10.3)
check("canal vide après les D|", ch.n == 0 and core.ChannelRoute(ch, core.ParseLine("[WL]M|x"), 11) is None)
core.ChannelPush(ch, ".build api smelter status 5", True, 20)
check("canal : commande sans réponse oubliée après le délai", core.ChannelRoute(ch, core.ParseLine("[WL]M|x"), 30) is None and ch.n == 0)
core.ChannelPush(ch, ".build api station", True, 40)
check("canal : D| inconnu sans effet", core.ChannelRoute(ch, core.ParseLine("[WL]D|place|1"), 40) is None and ch.n == 1)

# --- fabrication : possédé / requis, station, niveau, bouton ----------------------------------------
cnt = lua.eval("{ [9200001] = 30, [9200002] = 2, [9200021] = 25 }")
r_hammer = core.ParseLine("[WL]C|99|Marteau||9201100:1|9200001:3,9200002:2|1")
r_axe = core.ParseLine("[WL]C|100|Hache en pierre||9201010:1|9200001:5,9200002:4|1")
r_flint = core.ParseLine("[WL]C|101|Hache en silex|workbench|9201011:1|9200001:4,9200002:1|1")
r_lvl2 = core.ParseLine("[WL]C|150|Objet niveau 2|workbench|9201011:1|9200001:1|2")
r_forge = core.ParseLine("[WL]C|106|Pioche en fer|forge|9201032:1|9200001:3,9200021:20|2")
bench1 = core.ParseLine("[WL]S|9500143|1|100|1"); bench1["kind"] = "workbench"
bench2 = core.ParseLine("[WL]S|9500143|1|100|2"); bench2["kind"] = "workbench"
exposed = core.ParseLine("[WL]S|9500143|0|40|2"); exposed["kind"] = "workbench"
c = core.CraftCheck(r_hammer, cnt, None)
check("à la main : réalisable sans station", c["ok"] and c["hand"] and c["rows"][1]["have"] == 30 and c["rows"][1]["need"] == 3 and c["rows"][2]["ok"])
c = core.CraftCheck(r_axe, cnt, None)
check("à la main : pierre 2/4 insuffisante", (not c["ok"]) and c["reason"] == "resources" and c["rows"][2]["have"] == 2 and c["rows"][2]["need"] == 4 and not c["rows"][2]["ok"])
c = core.CraftCheck(r_flint, cnt, None)
check("établi requis absent", (not c["ok"]) and c["reason"] == "nostation")
c = core.CraftCheck(r_flint, cnt, bench1)
check("établi à portée niveau 1 : réalisable", c["ok"] and c["curLevel"] == 1)
c = core.CraftCheck(r_lvl2, cnt, bench1)
check("niveau de station insuffisant (1 < 2)", (not c["ok"]) and c["reason"] == "level")
check("niveau suffisant (2)", core.CraftCheck(r_lvl2, cnt, bench2)["ok"])
c = core.CraftCheck(r_flint, cnt, exposed)
check("établi exposé : refusé", (not c["ok"]) and c["reason"] == "exposed")
c = core.CraftCheck(r_forge, cnt, None)
check("forge absente (aucune ligne S|forge) : refusée", (not c["ok"]) and c["reason"] == "nostation")
forge2 = core.ParseLine("[WL]S|9500150|1|100|2|forge")
c = core.CraftCheck(r_forge, cnt, forge2)
check("forge à portée (S|...|forge niveau 2) : réalisable", c["ok"] and c["curLevel"] == 2, str(c["reason"]))
check("bouton Fabriquer : actif / inactif / occupé", core.CraftButtonEnabled(core.CraftCheck(r_hammer, cnt, None), None)
      and not core.CraftButtonEnabled(core.CraftCheck(r_axe, cnt, None), None)
      and not core.CraftButtonEnabled(core.CraftCheck(r_hammer, cnt, None), 1))
names = data.stations
t, okst = core.StationText(core.CraftCheck(r_lvl2, cnt, bench1), names)
check("texte station : niveau requis vs actuel", (not okst) and "niveau 2 requis (actuel : 1)" in t and "Table de fabrication" in t, t)
t, okst = core.StationText(core.CraftCheck(r_hammer, cnt, None), names)
check("texte station : à la main", okst and "main" in t, t)
t, okst = core.StationText(core.CraftCheck(r_flint, cnt, None), names)
check("texte station : établi à portée requis", (not okst) and "Table de fabrication" in t, t)
recs = lua.eval("function(...) local t = {...}; t.n = select('#', ...); return t end")(r_axe, r_hammer, r_flint, r_lvl2, r_forge)
lst = core.RecipeList(recs, cnt, None, None)
check("liste sans station : recettes à la main seulement, réalisables d'abord", lst.n == 2 and lst[1]["r"]["id"] == 99 and lst[2]["r"]["id"] == 100)
lst = core.RecipeList(recs, cnt, bench1, None)
ids = [lst[i]["r"]["id"] for i in range(1, lst.n + 1)]
check("liste à l'établi : main + établi (pas la forge)", ids == [99, 101, 100, 150], str(ids))
lst = core.RecipeList(recs, cnt, None, True)
check("liste « toutes les stations »", lst.n == 5)
cs = core.NewCraft()
core.CraftRequestRecipes(cs)
for ln in ("[WL]M|Recettes d'établi :", "[WL]C|99|Marteau||9201100:1|9200001:3|1", "[WL]C|101|Hache en silex|workbench|9201011:1|9200001:4|1"):
    core.CraftOnMessage(cs, core.ParseLine(ln))
check("recettes remplacées à D|recipes", cs.recipes.n == 0 and core.CraftOnMessage(cs, core.ParseLine("[WL]D|recipes|1")) == "recipes" and cs.recipes.n == 2 and cs.loaded)
core.CraftRequestStation(cs)
core.CraftOnMessage(cs, core.ParseLine("[WL]S|9500143|1|100|2"))
core.CraftOnMessage(cs, core.ParseLine("[WL]D|station|1"))
check("station reçue (S| puis D|station)", cs.station and cs.station["kind"] == "workbench" and cs.station["level"] == 2)
core.CraftRequestStation(cs)
core.CraftOnMessage(cs, core.ParseLine("[WL]M|Aucun établi à moins de 10 m."))
core.CraftOnMessage(cs, core.ParseLine("[WL]D|station|1"))
check("plus d'établi : D|station sans S| => station nil", cs.station is None)
cs.busy = 1
check("D|craft|0 : fin de fabrication (échec)", core.CraftOnMessage(cs, core.ParseLine("[WL]D|craft|0")) == "craftfail" and not cs.busy)

# --- fonderie : vue, boutons ---------------------------------------------------------------------------
conv = data.smelters.smelter.conversion
sm = core.ParseLine("[WL]SM|9500200|smelter|Fonderie|3|10|12.50|20|9200051|12.3|30|1|ok|9200060:3|9200013:4,9200021:1")
v = core.SmelterView(sm, lua.eval("{ [9200060] = 5, [9200051] = 2 }"), conv)
check("fonderie : textes et barres", v["oreText"] == "3/10" and abs(v["oreFrac"] - 0.3) < 1e-9 and v["fuelText"] == "13/20" and abs(v["fuelFrac"] - 0.625) < 1e-9
      and v["progressText"] == "12/30 s" and abs(v["progress"] - 0.41) < 1e-9 and v["ready"] == 5 and v["status"] == "En marche", str(dict(v)))
check("fonderie : boutons actifs (minerai, charbon, récupérer)", v["canAddOre"] and v["canAddFuel"] and v["canTake"] and v["oreItem"] == 9200060)
check("Maj+clic : remplir (min(place 7, possédé 5))", core.SmelterAddCount(v, "ore", True) == 5 and core.SmelterAddCount(v, "ore", None) == 1
      and core.SmelterAddCount(v, "fuel", True) == 2)
sm = core.ParseLine("[WL]SM|9500200|smelter|Fonderie|10|10|19.50|20|9200051|0.0|30|0|roof||")
v = core.SmelterView(sm, lua.eval("{ [9200060] = 5, [9200051] = 2 }"), conv)
check("fonderie pleine : ajout impossible, rien à récupérer", (not v["canAddOre"]) and (not v["canAddFuel"]) and (not v["canTake"]) and v["status"] == "Nécessite un toit")
v = core.SmelterView(core.ParseLine("[WL]SM|9500200|smelter|Fonderie|0|10|0.00|20|9200051|0.0|30|0|noore||"), lua.eval("{}"), conv)
check("sans minerai ni charbon dans les sacs : boutons inactifs", (not v["canAddOre"]) and not v["canAddFuel"])
v = core.SmelterView(sm_kiln, lua.eval("{ [9200001] = 40 }"), data.smelters.charcoal_kiln.conversion)
check("four à charbon : pas de combustible, bois accepté", v["kiln"] and not v["hasFuel"] and v["canAddOre"] and not v["canAddFuel"] and v["oreItem"] == 9200001 and v["status"] == "Vide")
ss = core.NewSmelt()
smline = core.ParseLine("[WL]SM|9500200|smelter|Fonderie|3|10|12.50|20|9200051|12.3|30|1|ok||")
check("SM non sollicité, panneau fermé => ouverture", core.SmeltOnMessage(ss, smline, None, False) == "open" and ss.guid == 9500200)
poll = lua.eval("{ cmd = 'smelter', silent = true }")
check("SM d'un rafraîchissement silencieux, panneau fermé => pas de réouverture", core.SmeltOnMessage(ss, smline, poll, False) == "update")
check("E|trop loin => station perdue", core.SmeltOnMessage(ss, core.ParseLine("[WL]E|trop loin"), poll, True) == "lost" and ss.guid is None)
check("E| d'ajout (plein) => pas perdue", core.SmeltOnMessage(ss, core.ParseLine("[WL]E|La fonderie est pleine"), poll, True) is None)

# --- données générées pour les panneaux -----------------------------------------------------------
check("objets produits par les recettes : nom + icône (outils, marteau)", all(data["items"][i] and data["items"][i]["icon"].startswith("WL_")
      for i in (9201100, 9201010, 9201011, 9201012, 9201021, 9201022, 9201031, 9201032, 9200053, 9200054, 9200052, 9200056, 9200015)))
check("description des objets (marteau)", len(data["items"][9201100]["desc"]) > 10)
check("stations : four à charbon et fonderie nommés", data.stations.charcoal_kiln and data.stations.smelter)
check("fonderie : charbon, 10 minerais, 20 combustibles, conversions", data.smelters.smelter.fuel == 9200051 and data.smelters.smelter.maxOre == 10
      and data.smelters.smelter.maxFuel == 20 and data.smelters.smelter.conversion[1][1] == 9200060)

# --- touches par défaut et disposition des panneaux ----------------------------------------------------
def bind_api(bound, saves):
    """bound : dict touche -> action (liaisons actuelles) ; saves : liste, +1 par SaveBindings."""
    return lua.table_from({
        "action": lambda key: bound.get(key, ""),
        "keyOf": lambda action: next((k for k, a in bound.items() if a == action), None),
        "set": lambda key, action: bound.__setitem__(key, action),
        "save": lambda: saves.append(1),
    })

defaults = [(d["key"], d["action"]) for d in core.DEFAULT_KEYS.values()]
check("touches par défaut : menu Y, fabrication I, fonderie J, rotation Alt+A/Alt+E et Ctrl+molette, compétences Maj+K",
      defaults == [("Y", "WOWLHEIM_TOGGLE"), ("I", "WOWLHEIM_CRAFT"), ("J", "WOWLHEIM_SMELT"), ("ALT-A", "WOWLHEIM_ROTATE_LEFT"),
                   ("ALT-E", "WOWLHEIM_ROTATE_RIGHT"), ("CTRL-MOUSEWHEELDOWN", "WOWLHEIM_ROTATE_LEFT"), ("CTRL-MOUSEWHEELUP", "WOWLHEIM_ROTATE_RIGHT"),
                   ("SHIFT-K", "WOWLHEIM_SKILLS")], str(defaults))
FORBIDDEN = set("W A S D Z Q E B C P N O L M U H V K X T G F R TAB ESCAPE ENTER SPACE UP DOWN LEFT RIGHT".split()) | {str(i) for i in range(10)} | {"-", "="}
check("touches par défaut : ni déplacement (ZQSD/WASD), ni flèches, ni barre d'action, ni Échap/Entrée/Tab",
      not any(k in FORBIDDEN for k, _ in defaults))
DEFWTF = os.path.join(HERE, "..", "extracted", "WTF", "DefaultBindings.wtf")
if os.path.isfile(DEFWTF):   # extrait local du client (patch.MPQ, WTF\DefaultBindings.wtf) : non distribué
    orig = {ln.split()[1] for ln in open(DEFWTF, encoding="latin-1") if ln.startswith("bind ")}
    check("touches par défaut libres dans WTF\\DefaultBindings.wtf du client 1.12.1", len(orig) > 100 and not any(k in orig for k, _ in defaults),
          str([k for k, _ in defaults if k in orig]))
else:
    print("[--]   DefaultBindings.wtf non extrait (mpq_layers.py extract) : vérification des touches d'origine sautée")
bound, saves = {"B": "TOGGLEBACKPACK"}, []
db = lua.table()
r = core.ApplyDefaultBindings(db, bind_api(bound, saves))
check("liaisons appliquées au premier chargement (8 touches, une sauvegarde)", r.n == 8 and bound["Y"] == "WOWLHEIM_TOGGLE"
      and bound["CTRL-MOUSEWHEELUP"] == "WOWLHEIM_ROTATE_RIGHT" and saves == [1] and db.bindingsDone == core.BINDINGS_VERSION, str(bound))
bound.pop("Y")
check("une seule fois : rien de reposé ensuite (touche retirée par le joueur)", core.ApplyDefaultBindings(db, bind_api(bound, saves)) is None
      and "Y" not in bound and saves == [1])
bound, saves = {"I": "TOGGLEPETBOOK", "F6": "WOWLHEIM_TOGGLE"}, []
r = core.ApplyDefaultBindings(lua.table(), bind_api(bound, saves))
check("touche déjà prise (I) : non écrasée ; action déjà liée par le joueur (F6) : pas de 2e touche",
      bound["I"] == "TOGGLEPETBOOK" and "Y" not in bound and bound["J"] == "WOWLHEIM_SMELT" and r.n == 6, str(bound))
# mise à jour de l'addon (liaisons version 1 déjà posées) : seule la nouvelle touche (Maj+K) est posée, une touche retirée
# par le joueur (Y) n'est pas reposée ; Maj+K prise par le joueur : rien n'est écrasé
bound, saves = {"I": "WOWLHEIM_CRAFT", "J": "WOWLHEIM_SMELT"}, []
db = lua.table_from({"bindingsDone": 1})
r = core.ApplyDefaultBindings(db, bind_api(bound, saves))
check("mise à jour (liaisons v1 faites) : seule Maj+K est posée, Y retirée par le joueur non reposée",
      r.n == 1 and bound.get("SHIFT-K") == "WOWLHEIM_SKILLS" and "Y" not in bound and saves == [1] and db.bindingsDone == 2, str(bound))
bound, saves = {"SHIFT-K": "MACRO_X"}, []
r = core.ApplyDefaultBindings(lua.table_from({"bindingsDone": 1}), bind_api(bound, saves))
check("mise à jour : Maj+K déjà prise par le joueur, non écrasée", r.n == 0 and bound["SHIFT-K"] == "MACRO_X" and saves == [])
bound, saves = {d: "X" for d, _ in defaults}, []
db = lua.table()
check("aucune touche libre : pas de SaveBindings, mais marqué fait", core.ApplyDefaultBindings(db, bind_api(bound, saves)).n == 0 and saves == [] and db.bindingsDone)

check("tailles des panneaux = tailles construites", core.PANELS.hammer.w == 16 * 2 + 10 * 44 + 24 and core.PANELS.hammer.h == 12 + 24 + 8 + 20 + 8 + 4 * 44 + 8 + 112 + 8 + 16 + 8)
for sw, sh in ((1024, 768), (1365, 768), (1835, 768)):
    rects = {k: core.PanelRect(k, *core.PanelDefaultPos(k, sw, sh)) for k in ("hammer", "craft", "smelt", "skills")}
    keys = list(rects)
    overl = [(a, b) for i, a in enumerate(keys) for b in keys[i + 1:] if core.RectsOverlap(rects[a], rects[b])]
    banner = core.BannerRect(sw, sh)
    inside = all(r.l >= 0 and r.b >= 0 and r.r <= sw and r.t <= sh for r in rects.values())
    check("%dx%d : panneaux sans superposition, dans l'écran, hors bandeau « Mode : … »" % (sw, sh),
          not overl and inside and not any(core.RectsOverlap(r, banner) for r in rects.values()), str(overl))
    bar = core.StaminaBarRect(sw, sh)
    check("%dx%d : barre d'endurance en haut au centre, au-dessus du bandeau de pose, hors des panneaux" % (sw, sh),
          bar.b > banner.t and bar.t <= sh and not any(core.RectsOverlap(r, bar) for r in rects.values()) and abs((bar.l + bar.r) / 2 - sw / 2) < 1)
    check("%dx%d : marteau en bas à droite, au-dessus des barres d'action" % (sw, sh),
          rects["hammer"].b >= 96 and rects["hammer"].r <= sw - 100 and rects["hammer"].l > sw / 2 - 20)
    if sw >= 1365:   # 4:3 : trop étroit pour laisser le centre libre
        center = lua.table_from({"l": sw / 2 - 100, "r": sw / 2 + 100, "b": 120, "t": 360})
        check("%dx%d : personnage (centre de l'écran) non couvert" % (sw, sh), not any(core.RectsOverlap(r, center) for r in rects.values()))
l, b = core.PanelPos("smelt", lua.table_from({1: 600, 2: 300}), 1835, 768)
check("position mémorisée reprise telle quelle", (l, b) == (600, 300))
l, b = core.PanelPos("hammer", lua.table_from({1: 5000, 2: -40}), 1024, 768)
w, h = core.PanelSize("hammer")
check("position mémorisée hors écran (résolution changée) : ramenée dans l'écran", l == 1024 - w and b == 0, str((l, b)))
check("sans position mémorisée : position par défaut", core.PanelPos("craft", None, 1024, 768) == core.PanelDefaultPos("craft", 1024, 768))

# --- Wowlheim.lua dans une API WoW simulee ---------------------------------------------------------
MOCK = r"""
SENT = {}; USED = 0; TARGETING = nil; NOW = 1000; EQUIPPED = "|Hitem:9201100:0:0:0|h[Marteau]|h"; ERRORS = {}
BAGS = { [0] = { [1] = {"|Hitem:9200001:0:0:0|h[Bois]|h", 30}, [2] = {"|Hitem:9200002:0:0:0|h[Pierre]|h", 2} } }
FRAMES = {}
local Obj = {}
Obj.__index = function(t, k)
  local v = rawget(Obj, k); if v then return v end
  if type(k) == "string" and string.find(k, "^%u") then return function() return nil end end   -- methode inconnue : sans effet
end
function Obj:SetScript(name, f) self.scripts[name] = f end
function Obj:GetScript(name) return self.scripts[name] end
function Obj:Show() local was = self.shown; self.shown = true; if not was and self.scripts.OnShow then RunScript(self, "OnShow") end end
function Obj:Hide() local was = self.shown; self.shown = false; if was and self.scripts.OnHide then RunScript(self, "OnHide") end end
function Obj:IsVisible() return self.shown end
function Obj:IsShown() return self.shown end
function Obj:SetID(i) self.id = i end
function Obj:GetID() return self.id end
function Obj:GetName() return self.name end
function Obj:SetText(t) self.text = t end
function Obj:GetText() return self.text end
function Obj:SetTexture(t) self.texture = t; return 1 end
function Obj:SetDesaturated(d) self.desat = d; return 1 end
function Obj:SetVertexColor(r, g, b) self.color = {r, g, b} end
function Obj:SetTextColor(r, g, b) self.color = {r, g, b} end
function Obj:Enable() self.enabled = true end
function Obj:SetScale(v) self.scale = v end
function Obj:GetScale() return self.scale end
function Obj:SetPoint(p, rel, rp, x, y) self.point = {p, rel, rp, x, y} end
function Obj:ClearAllPoints() self.point = nil end
function Obj:GetLeft() return self.point and self.point[4] end
function Obj:GetBottom() return self.point and self.point[5] end
function Obj:Disable() self.enabled = false end
local function New(kind, name, parent)
  local o = setmetatable({ kind = kind, name = name, parent = parent, scripts = {}, shown = true }, Obj)
  if name then _G[name] = o; FRAMES[name] = o end
  return o
end
function Obj:CreateTexture(name) return New("Texture", name, self) end
function Obj:CreateFontString(name) return New("FontString", name, self) end
function CreateFrame(kind, name, parent) return New(kind, name, parent) end
function RunScript(o, name, a1)
  local f = o.scripts[name]; if not f then return end
  local oldthis, oldarg = this, arg1
  this = o; arg1 = a1; f(); this = oldthis; arg1 = oldarg
end
UIParent = New("Frame", "UIParent")
UIErrorsFrame = New("Frame", "UIErrorsFrame")
function UIErrorsFrame:AddMessage(t) table.insert(ERRORS, t) end
ERR_USE_TOO_FAR = "You are too far away."
function UIErrorsFrame_OnEvent(event, message)      -- FrameXML/UIErrorsFrame.lua (appelée par le gestionnaire XML)
  if event == "UI_ERROR_MESSAGE" then this:AddMessage(message, 1.0, 0.1, 0.1, 1.0) end
end
function UIError(msg) local old = this; this = UIErrorsFrame; event = "UI_ERROR_MESSAGE"; arg1 = msg; UIErrorsFrame_OnEvent(event, arg1); event = nil; arg1 = nil; this = old end
DEFAULT_CHAT_FRAME = New("Frame", "DEFAULT_CHAT_FRAME")
function DEFAULT_CHAT_FRAME:AddMessage(t) end
UISpecialFrames = {}; SlashCmdList = {}
CHAT_SHOWN = {}
function ChatFrame_OnEvent(event) table.insert(CHAT_SHOWN, arg1) end
function SendChatMessage(msg, kind) table.insert(SENT, msg) end
function UseInventoryItem(slot) USED = USED + 1; TARGETING = 1; USED_SLOT = slot end
function SpellIsTargeting() return TARGETING end
function SpellStopTargeting() TARGETING = nil end
function GetInventoryItemLink(unit, slot) if slot == 16 then return EQUIPPED end end
function GetInventoryItemCooldown() return 0, 0, 1 end
function GetTime() return NOW end
function GetItemInfo() return nil end
function IsShiftKeyDown() return SHIFT end
function GetContainerNumSlots(b) if BAGS[b] then return 16 end return 0 end
function GetContainerItemLink(b, s) local x = BAGS[b] and BAGS[b][s]; return x and x[1] end
function GetContainerItemInfo(b, s) local x = BAGS[b] and BAGS[b][s]; if x then return "tex", x[2] end end
function Fire(ev, a1) event = ev; arg1 = a1; WowlheimEvents.scripts.OnEvent(); event = nil; arg1 = nil end
function Tick(dt)
  NOW = NOW + dt; this = WowlheimEvents; WowlheimEvents.scripts.OnUpdate(); this = nil
  if WowlheimCraftEvents then this = WowlheimCraftEvents; arg1 = dt; WowlheimCraftEvents.scripts.OnUpdate(); this = nil; arg1 = nil end
end
function ChatSystem(text) event = "CHAT_MSG_SYSTEM"; arg1 = text; ChatFrame_OnEvent("CHAT_MSG_SYSTEM"); Fire("CHAT_MSG_SYSTEM", text) end
"""

ui = new_lua()
ui.execute(MOCK)
for f in ("WowlheimData.lua", "WowlheimCore.lua", "Wowlheim.lua", "WowlheimCraft.lua", "WowlheimSkills.lua"):
    ui.execute(read(f))
G = ui.globals()
WL = G.Wowlheim
check("Wowlheim.lua se charge (API simulée)", WL is not None)
# onglet mémorisé (WowlheimDB.cat, choix du joueur d'une session précédente) : Construction
ui.execute('WowlheimDB = { cat = 3 }; Fire("VARIABLES_LOADED"); Fire("PLAYER_ENTERING_WORLD")')
frame = G.WowlheimFrame
check("marteau équipé à l'entrée en jeu => panneau ouvert", frame is not None and frame.shown)
check("panneau fermable par Échap (UISpecialFrames)", G.UISpecialFrames[1] == "WowlheimFrame")
check("ouverture sur « Construction » (onglet en orange)", WL.cat == 3 and G.WowlheimTab3.label.color[1] == 1.0 and G.WowlheimTab1.label.color[1] < 1)
ui.execute("Tick(0.1)")
check("inventaire compté depuis les sacs", WL.counts[9200001] == 30 and WL.counts[9200002] == 2)
first = G.WowlheimIcon1
check("grille remplie (icône 1 = 1re pièce de Construction)", first.entry is not None and first.entry.cat == 3 and first.icon.texture.startswith("Interface\\Icons\\WL_"), str(first.icon.texture))
# Survol : encadre
ui.execute("RunScript(WowlheimIcon1, 'OnEnter')")
check("survol : nom affiché dans l'encadré", G.WowlheimInfoName.text == first.entry.name)
check("survol : ressources « possédé/requis »", "/" in (G.WowlheimCost1Text.text or ""), str(G.WowlheimCost1Text.text))
ui.execute("RunScript(WowlheimIcon1, 'OnLeave')")
# Clic gauche => select + UseInventoryItem(16)
pid = first.entry.id
ui.execute("RunScript(WowlheimIcon1, 'OnClick', 'LeftButton')")
check("clic gauche : select envoyé", list(G.SENT.values())[-1] == ".build api select %d 0" % pid, str(list(G.SENT.values())))
check("clic gauche : ciblage au sol (UseInventoryItem(16))", G.USED == 1 and G.USED_SLOT == 16)
check("choix d'une pièce : menu masqué pendant la pose (Valheim), pose continue conservée", not frame.shown and WL.state.continuous and G.TARGETING == 1)
check("rappel en haut de l'écran : nom de la pièce + rotation", G.WowlheimPlaceBanner.shown
      and G.WowlheimPlaceBannerText.text.split(chr(10))[0] == first.entry.name + "  -  Rotation : 0°", str(G.WowlheimPlaceBannerText.text))
# Molette => rotation
ui.execute("RunScript(WowlheimFrame, 'OnMouseWheel', 1)")
check("molette : select avec rot 1", list(G.SENT.values())[-1] == ".build api select %d 1" % pid)
check("encadré : rotation affichée", "22.5" in G.WowlheimInfoRot.text, G.WowlheimInfoRot.text)
ui.execute("Wowlheim.Rotate(1); Wowlheim.Rotate(-1)")
check("touche de rotation menu masqué : rappel mis à jour", G.WowlheimPlaceBannerText.text.endswith("Rotation : 22,5°"), G.WowlheimPlaceBannerText.text)
# Pose reussie => relance automatique (une seule fois malgre D + M)
ui.execute('TARGETING = nil; ChatSystem("[WL]M|Pièce Mur posée (id 9500001)"); ChatSystem("[WL]D|place|1")')
check("lignes [WL] masquées du chat", len(G.CHAT_SHOWN) == 0)
ui.execute("Tick(0.1)")
check("pas de relance avant le délai", G.USED == 1)
ui.execute("Tick(0.3)")
check("pose continue : relance du ciblage", G.USED == 2 and G.TARGETING == 1)
ui.execute("Tick(1)")
check("une seule relance par pose", G.USED == 2)
check("pose continue : menu toujours masqué, rappel affiché", not frame.shown and G.WowlheimPlaceBanner.shown)
# Clic droit au sol PENDANT le ciblage : le jeu annule le ciblage => fin de la pose, menu toujours masqué
# Le clic droit du monde n'est plus intercepte (action protegee en 1.12) : Echap arrete la pose, la touche rouvre le menu
check("l'addon ne remplace pas TurnOrActionStart/Stop (actions protégées)", G.TurnOrActionStart is None or not WL.origTurnStart)
ui.execute("ToggleGameMenu()")
check("Échap pendant le ciblage : fin de la pose, menu non rouvert", not WL.state.continuous and not frame.shown and not G.WowlheimPlaceBanner.shown)
ui.execute("Wowlheim.Toggle()")
check("touche de bascule : menu rouvert", frame.shown)
# Touche de bascule : rouvre le menu sans arrêter la pose
ui.execute("RunScript(WowlheimIcon1, 'OnClick', 'LeftButton')")
check("nouveau choix : menu masqué", not frame.shown and WL.state.continuous)
ui.execute("Wowlheim.Toggle()")
check("touche de bascule : menu rouvert, pose conservée, rappel masqué (menu ouvert)", frame.shown and WL.state.continuous and not G.WowlheimPlaceBanner.shown)
ui.execute("Wowlheim.Hide(); RunScript(WowlheimIcon1, 'OnClick', 'LeftButton')")
check("fermeture du menu par le joueur puis nouveau choix : pose relancée", WL.state.continuous and G.TARGETING == 1 and not frame.shown)
# Échap pendant le ciblage (menu masqué) : fin de la pose, pas de menu du jeu
ui.execute("GAMEMENU = 0; function ToggleGameMenu_orig_mock() GAMEMENU = GAMEMENU + 1 end; Wowlheim.origToggleGameMenu = ToggleGameMenu_orig_mock; ToggleGameMenu()")
check("Échap pendant le ciblage : fin de la pose, menu du jeu non ouvert", not WL.state.continuous and G.TARGETING is None and G.GAMEMENU == 0)
ui.execute("ToggleGameMenu()")
check("Échap hors pose : menu du jeu", G.GAMEMENU == 1)
ui.execute("Wowlheim.Show(); RunScript(WowlheimIcon1, 'OnClick', 'LeftButton'); Wowlheim.Show()")
check("menu rouvert pendant la pose : ciblage conservé", frame.shown and WL.state.continuous and G.TARGETING == 1)
# Clic droit sur le panneau => annulation
ui.execute("RunScript(WowlheimFrame, 'OnMouseUp', 'RightButton')")
check("clic droit : ciblage annulé", G.TARGETING is None and not WL.state.continuous)
u_cancel = G.USED
ui.execute('ChatSystem("[WL]D|place|1"); Tick(1)')
check("après annulation : pas de relance", G.USED == u_cancel)
# Erreur serveur => UIErrorsFrame
n_err0 = len(G.ERRORS)
ui.execute('ChatSystem("[WL]E|Ressources insuffisantes")')
check("E| affiché une fois, dans le panneau ouvert (pas de copie dans UIErrorsFrame)", "Ressources insuffisantes" in G.WowlheimMsg.text and len(G.ERRORS) == n_err0)
# Refus de pose : notification (serveur) + M| + D|place|0 => un seul message
ui.execute("RunScript(WowlheimIcon1, 'OnClick', 'LeftButton'); Wowlheim.Show()")
ui.execute('Wowlheim.Send(".build api station", 1)')     # commande silencieuse en attente : ne doit pas avaler le refus
ui.execute('ChatSystem("[WL]M|Pose refusée : il faut Table de fabrication à moins de 10 m."); ChatSystem("[WL]D|place|0")')
check("refus de pose (panneau ouvert) : texte du serveur dans le panneau, rien dans UIErrorsFrame",
      "Pose refusée" in G.WowlheimMsg.text and len(G.ERRORS) == n_err0 and WL.state.continuous and WL.relaunchAt, str(list(G.ERRORS.values())[n_err0:]))
ui.execute('ChatSystem("[WL]D|station|1")')
ui.execute("Wowlheim.Hide(); RunScript(WowlheimIcon1, 'OnClick', 'LeftButton')")
ui.execute('NOW = NOW + 5; ChatSystem("[WL]M|Pose refusée : il faut Table de fabrication à moins de 10 m."); ChatSystem("[WL]D|place|0")')
check("refus de pose (panneau fermé) : affiché une seule fois dans UIErrorsFrame", len(G.ERRORS) == n_err0 + 1, str(list(G.ERRORS.values())[n_err0:]))
ui.execute("Wowlheim.Show()")
# Pose continue : fantome natif rappele AVANT chaque UseInventoryItem
ui.execute("GHOST = {}; function WowlheimSetPlaceObject(id) table.insert(GHOST, { id = id, used = USED }) end")
u0 = G.USED
ui.execute("RunScript(WowlheimIcon2, 'OnClick', 'LeftButton')")
pid2 = G.WowlheimIcon2.entry.id
ui.execute('TARGETING = nil; ChatSystem("[WL]M|Pièce Mur posée (id 9500003)"); ChatSystem("[WL]D|place|1"); Tick(0.5)')
ui.execute('TARGETING = nil; ChatSystem("[WL]D|place|1"); ChatSystem("[WL]M|Pièce Mur posée (id 9500004)"); Tick(0.5)')
ghost = [(g.id, g.used) for g in G.GHOST.values()]
check("pose continue : 2 relances après 2 poses réussies", G.USED == u0 + 3, str(G.USED - u0))
check("pose continue : WowlheimSetPlaceObject(9110000+id) avant chaque ciblage", ghost == [(9110000 + pid2, u0), (9110000 + pid2, u0 + 1), (9110000 + pid2, u0 + 2)], str(ghost))
ui.execute("WowlheimSetPlaceObject = nil; Wowlheim.Show(); RunScript(WowlheimFrame, 'OnMouseUp', 'RightButton')")
# Divers : Reparer / Demolir
ui.execute("RunScript(WowlheimTab1, 'OnClick', 'LeftButton')")
check("onglet Divers : 1re icône = Réparer", G.WowlheimIcon1.entry.special == "repair" and G.WowlheimIcon2.entry.special == "remove")
ui.execute("RunScript(WowlheimIcon2, 'OnClick', 'LeftButton')")
check("Démolir : mode remove envoyé", list(G.SENT.values())[-1] == ".build api mode remove")
check("Démolir : menu masqué, « Mode : Démolir » affiché", not frame.shown and WL.state.mode == "remove" and G.WowlheimModeBanner.shown and not G.WowlheimPlaceBanner.shown)
check("en Démolir : menu reste masqué", not frame.shown and WL.state.mode == "remove")
ui.execute("Wowlheim.Toggle()")
check("touche de bascule en Démolir : menu rouvert, mode conservé", frame.shown and WL.state.mode == "remove")
ui.execute("RunScript(WowlheimIcon3, 'OnClick', 'LeftButton')")
sent = list(G.SENT.values())
check("choisir une pièce après Démolir : mode build puis select", sent[-2] == ".build api mode build" and sent[-1].startswith(".build api select "), str(sent[-2:]))
# Echap / fermeture du menu en mode Demolir : le mode reste, rappel en haut de l'ecran
ui.execute("Wowlheim.Show(); RunScript(WowlheimIcon2, 'OnClick', 'LeftButton')")
check("Démolir : rappel « Mode : Démolir » affiché", G.WowlheimModeBanner.shown and G.WowlheimModeBannerText.text == "Mode : Démolir")
n_sent = len(list(G.SENT.values()))
ui.execute("Wowlheim.Hide()")
check("fermeture du menu (Échap) en mode Démolir : pas de retour en build", WL.state.mode == "remove" and len(list(G.SENT.values())) == n_sent
      and G.WowlheimModeBanner.shown)
ui.execute('EQUIPPED = nil; Fire("UNIT_INVENTORY_CHANGED", "player")')
check("marteau rangé : rappel masqué", not G.WowlheimModeBanner.shown)
ui.execute('EQUIPPED = "|Hitem:9201100:0:0:0|h[Marteau]|h"; Fire("UNIT_INVENTORY_CHANGED", "player")')
check("marteau rééquipé : menu rouvert, toujours en Démolir", G.WowlheimFrame.shown and WL.state.mode == "remove" and G.WowlheimModeBanner.shown)
ui.execute("RunScript(WowlheimFrame, 'OnMouseUp', 'RightButton')")
check("clic droit sur le menu en Démolir : mode conservé", WL.state.mode == "remove")
ui.execute("RunScript(WowlheimIcon3, 'OnClick', 'LeftButton')")
check("choix d'une pièce : retour en build, rappel masqué", WL.state.mode == "build" and not G.WowlheimModeBanner.shown)
# Icône rougeatre si ressources insuffisantes (Pierre : 2 seulement)
ui.execute("RunScript(WowlheimTab3, 'OnClick', 'LeftButton')")
grey_ok = True
for i in range(1, 41):
    b = G["WowlheimIcon%d" % i]
    if b.entry is None:
        continue
    affordable = G.WowlheimCore.Affordability(b.entry.costs, WL.counts)
    if isinstance(affordable, tuple):
        affordable = affordable[0]
    greyed = bool(b.icon.color) and b.icon.color[1] < 1 and not b.icon.desat
    if greyed == bool(affordable):
        grey_ok = False
check("icônes grisées exactement quand les ressources manquent", grey_ok)
# Rafraichissement sur BAG_UPDATE
ui.execute('BAGS[0][2][2] = 200; Fire("BAG_UPDATE", 0); Tick(0.1)')
check("BAG_UPDATE : recomptage", WL.counts[9200002] == 200)
# Desequiper le marteau => fermeture ; reequiper => ouverture
ui.execute('EQUIPPED = nil; Fire("UNIT_INVENTORY_CHANGED", "player")')
check("marteau déséquipé => panneau fermé", not frame.shown)
ui.execute('EQUIPPED = "|Hitem:9201100:0:0:0|h[Marteau]|h"; Fire("UNIT_INVENTORY_CHANGED", "player")')
check("marteau rééquipé => panneau ouvert", frame.shown)
ui.execute("Wowlheim.Toggle()")
check("touche de bascule : fermeture", not frame.shown)
ui.execute("Wowlheim.Rotate(1)")
check("touche de rotation hors panneau : sans erreur", True)

# --- panneau de fabrication (API simulee) ---------------------------------------------------------
def sent():
    return list(G.SENT.values())

def errors():
    return list(G.ERRORS.values())

ui.execute('BAGS = { [0] = { [1] = {"|Hitem:9200001:0:0:0|h[Bois]|h", 30}, [2] = {"|Hitem:9200002:0:0:0|h[Pierre]|h", 2} } }')
# panneaux de fabrication / fonderie : marteau range (sinon l'interrogation des cercles de portee s'ajoute aux commandes envoyees)
ui.execute('EQUIPPED = nil; Fire("UNIT_INVENTORY_CHANGED", "player")')
# les commandes du marteau envoyees plus haut n'ont jamais recu leur D| (serveur simule) : elles expirent du canal apres 6 s
ui.execute("Tick(7)")
check("canal : commandes sans réponse expirées", G.Wowlheim.channel.n > 0 and G.WowlheimCore.ChannelRoute(G.Wowlheim.channel, None, G.NOW) is None and G.Wowlheim.channel.n == 0)
n_err = len(errors())
ui.execute('SlashCmdList["WOWLHEIMCRAFT"]("")')
cf = G.WowlheimCraftFrame
check("/wlcraft : panneau de fabrication ouvert", cf is not None and cf.shown)
check("ouverture : demande station puis recettes", sent()[-2:] == [".build api station", ".build api recipes"], str(sent()[-2:]))
check("fermable par Échap", "WowlheimCraftFrame" in list(G.UISpecialFrames.values()))
check("ouverture : interrogations known et repairable (silencieuses) avant station / recettes",
      sent()[-4:-2] == [".build api known", ".build api repairable"], str(sent()[-4:]))
# ancien serveur : known / repairable inconnus => E|commande inconnue + D|...|0, rien d'affiché, tout reste visible
ui.execute('''ChatSystem("[WL]E|commande inconnue"); ChatSystem("[WL]D|known|0")
ChatSystem("[WL]E|commande inconnue"); ChatSystem("[WL]D|repairable|0")''')
check("ancien serveur : known / repairable refusés sans message, compatibilité (tout affiché)",
      len(errors()) == n_err and "inconnue" not in (G.WowlheimCraftMsg.text or "") and G.Wowlheim.known.unsupported
      and not G.Wowlheim.known.loaded and G.Wowlheim.Craft.repair.unsupported and not G.WowlheimCraftRepair.enabled, str(errors()[n_err:]))
ui.execute('''ChatSystem("[WL]M|Aucun établi à moins de 10 m."); ChatSystem("[WL]D|station|1")
ChatSystem("[WL]M|Recettes d'établi :")
ChatSystem("[WL]C|99|Marteau||9201100:1|9200001:3,9200002:2|1")
ChatSystem("[WL]C|100|Hache en pierre||9201010:1|9200001:5,9200002:4|1")
ChatSystem("[WL]C|101|Hache en silex|workbench|9201011:1|9200001:4,9200002:1|1")
ChatSystem("[WL]C|106|Pioche en fer|forge|9201032:1|9200001:3,9200021:20|2")
ChatSystem("[WL]D|recipes|1")''')
check("recettes reçues : « Chargement des recettes... » effacé", "Chargement" not in (G.WowlheimCraftMsg.text or ""), str(G.WowlheimCraftMsg.text))
check("réponses des requêtes automatiques non affichées", len(errors()) == n_err and len(G.CHAT_SHOWN) == 0, str(errors()[n_err:]))
check("sans station : recettes à la main seulement", G.WowlheimCraftRow1.entry.r.id == 99 and G.WowlheimCraftRow2.entry.r.id == 100 and not G.WowlheimCraftRow3.shown)
check("en-tête : sans station", G.WowlheimCraftStationName.text == "Sans station")
check("1re recette choisie : objet produit (icône, nom, description)", G.WowlheimCraftName.text == "Marteau" and G.WowlheimCraftIcon.texture == "Interface\\Icons\\WL_hammer"
      and len(G.WowlheimCraftDesc.text) > 10)
check("ingrédients : icône + possédé/requis", G.WowlheimCraftIng1Icon.texture == "Interface\\Icons\\WL_wood" and "30/3" in G.WowlheimCraftIng1Text.text
      and "2/2" in G.WowlheimCraftIng2Text.text and not G.WowlheimCraftIng3Icon.shown)
check("recette réalisable : bouton Fabriquer actif", G.WowlheimCraftButton.enabled)
ui.execute("RunScript(WowlheimCraftRow2, 'OnClick', 'LeftButton')")
check("recette non réalisable : quantité en rouge, bouton inactif", G.WowlheimCraftIng2Text.text.startswith("|cffff3030") and "2/4" in G.WowlheimCraftIng2Text.text
      and not G.WowlheimCraftButton.enabled)
check("ligne de liste grisée (ressources manquantes)", G.WowlheimCraftRow2.icon.color[1] < 1 and G.WowlheimCraftRow1.icon.color[1] == 1)
ui.execute("RunScript(WowlheimCraftRow1, 'OnClick', 'LeftButton'); RunScript(WowlheimCraftButton, 'OnClick', 'LeftButton')")
check("Fabriquer : craft envoyé", sent()[-1] == ".build api craft 99")
check("fabrication en cours : bouton inactif", not G.WowlheimCraftButton.enabled)
ui.execute('ChatSystem("[WL]M|Fabriqué : 1 x Marteau."); ChatSystem("[WL]D|craft|1")')
check("réponse affichée dans le panneau, bouton réactivé", "Fabriqué" in G.WowlheimCraftMsg.text and G.WowlheimCraftButton.enabled and len(errors()) == n_err)
ui.execute('ChatSystem("[WL]S|9500143|1|100|1")')
ids = [G["WowlheimCraftRow%d" % i].entry.r.id for i in range(1, 5) if G["WowlheimCraftRow%d" % i].shown]
check("établi à portée : ses recettes s'ajoutent (pas la forge)", ids == [99, 101, 100], str(ids))
check("en-tête : établi niveau 1", G.WowlheimCraftStationName.text == "Table de fabrication" and "Niveau 1" in G.WowlheimCraftStationLevel.text)
ui.execute("RunScript(WowlheimCraftShowAll, 'OnClick', 'LeftButton')")
check("« toutes les stations » : la forge apparaît", any(G["WowlheimCraftRow%d" % i].shown and G["WowlheimCraftRow%d" % i].entry.r.id == 106 for i in range(1, 6)))
row_forge = [i for i in range(1, 6) if G["WowlheimCraftRow%d" % i].shown and G["WowlheimCraftRow%d" % i].entry.r.id == 106][0]
ui.execute("RunScript(WowlheimCraftRow%d, 'OnClick', 'LeftButton')" % row_forge)
check("forge hors de portée : station requise affichée", "Forge" in G.WowlheimCraftReq.text, G.WowlheimCraftReq.text)
n_sent = len(sent())
ui.execute("Tick(5.1)")
check("rafraîchissement de la station (5 s)", sent()[n_sent:] == [".build api station"], str(sent()[n_sent:]))
ui.execute('ChatSystem("[WL]M|Aucun établi à moins de 10 m."); ChatSystem("[WL]D|station|1")')
check("établi perdu : en-tête « Sans station »", G.WowlheimCraftStationName.text == "Sans station" and len(errors()) == n_err)
ui.execute("Wowlheim.Craft.Toggle()")
check("touche de fabrication : fermeture", not cf.shown)

# --- panneau de fonderie (API simulee) --------------------------------------------------------------
ui.execute('BAGS[0][3] = {"|Hitem:9200060:0:0:0|h[Minerai de cuivre]|h", 6}; BAGS[0][4] = {"|Hitem:9200051:0:0:0|h[Charbon]|h", 3}; Fire("BAG_UPDATE", 0); Tick(0.1)')
ui.execute('SlashCmdList["WOWLHEIMSMELT"]("")')
sf = G.WowlheimSmeltFrame
check("/wlsmelt : panneau ouvert, status envoyé", sf.shown and sent()[-1] == ".build api smelter status")
ui.execute('ChatSystem("[WL]M|Fonderie : minerai 3/10 ..."); ChatSystem("[WL]SM|9500200|smelter|Fonderie|3|10|12.50|20|9200051|12.3|30|1|ok|9200060:3|9200013:4"); ChatSystem("[WL]D|smelter|1")')
check("fonderie : nom, état, barres", G.WowlheimSmeltName.text == "Fonderie" and "En marche" in G.WowlheimSmeltStatus.text
      and G.WowlheimSmeltOreBarText.text == "3/10" and G.WowlheimSmeltFuelBarText.text == "13/20" and G.WowlheimSmeltProgBarText.text == "12/30 s")
check("fonderie : produits prêts (icône cuivre x4)", G.WowlheimSmeltOut1Icon.texture == "Interface\\Icons\\WL_copper" and G.WowlheimSmeltOut1Text.text == "Cuivre x4", str(G.WowlheimSmeltOut1Text.text))
check("fonderie : boutons actifs", G.WowlheimSmeltAddOre.enabled and G.WowlheimSmeltAddFuel.enabled and G.WowlheimSmeltTake.enabled)
ui.execute("RunScript(WowlheimSmeltAddOre, 'OnClick', 'LeftButton')")
check("Ajouter minerai : 1 unité vers la station affichée", sent()[-1] == ".build api smelter add ore 1 9500200")
ui.execute("SHIFT = 1; RunScript(WowlheimSmeltAddFuel, 'OnClick', 'LeftButton'); SHIFT = nil")
check("Maj + Ajouter charbon : remplir (3 possédés)", sent()[-1] == ".build api smelter add fuel 3 9500200")
ui.execute("RunScript(WowlheimSmeltTake, 'OnClick', 'LeftButton')")
check("Récupérer : take", sent()[-1] == ".build api smelter take 9500200")
ui.execute('ChatSystem("[WL]M|Récupéré : 4 Cuivre"); ChatSystem("[WL]SM|9500200|smelter|Fonderie|4|10|15.00|20|9200051|13.0|30|1|ok|9200060:4|"); ChatSystem("[WL]D|smelter|1")')
check("message d'action dans le panneau ; plus rien à récupérer", "Récupéré" in G.WowlheimSmeltMsg.text and not G.WowlheimSmeltTake.enabled and not G.WowlheimSmeltOut1Icon.shown)
ui.execute('ChatSystem("[WL]D|smelter|1"); ChatSystem("[WL]D|smelter|1"); ChatSystem("[WL]D|smelter|1")')
n_sent = len(sent()); n_err = len(errors())
ui.execute("Tick(2.1)")
check("rafraîchissement toutes les 2 s (status <guid>)", sent()[n_sent:] == [".build api smelter status 9500200"], str(sent()[n_sent:]))
ui.execute("Tick(2.1)")
check("pas de 2e status tant que le 1er n'a pas répondu", len(sent()) == n_sent + 1)
ui.execute('ChatSystem("[WL]M|Fonderie : minerai 4/10 ..."); ChatSystem("[WL]SM|9500200|smelter|Fonderie|4|10|14.90|20|9200051|14.0|30|1|ok|9200060:4|"); ChatSystem("[WL]D|smelter|1")')
check("réponse du rafraîchissement : silencieuse, panneau à jour", len(errors()) == n_err and G.WowlheimSmeltProgBarText.text == "14/30 s")
ui.execute("Tick(2.1)")
ui.execute("RunScript(WowlheimSmeltClose, 'OnClick', 'LeftButton')")
check("bouton fermer", not sf.shown)
ui.execute('ChatSystem("[WL]M|..."); ChatSystem("[WL]SM|9500200|smelter|Fonderie|4|10|14.80|20|9200051|15.0|30|1|ok|9200060:4|"); ChatSystem("[WL]D|smelter|1")')
check("SM d'un rafraîchissement arrivé après fermeture : pas de réouverture", not sf.shown and len(errors()) == n_err)
ui.execute('ChatSystem("[WL]SM|9500201|charcoal_kiln|Four à charbon|2|25|0.00|0|0|3.0|15|1|ok|9200001:2|9200051:1")')
check("SM non sollicité (clic sur la station) : ouverture automatique", sf.shown and G.WowlheimSmeltName.text == "Four à charbon")
check("four à charbon : pas de combustible, « Ajouter du bois »", not G.WowlheimSmeltAddFuel.shown and G.WowlheimSmeltAddOre.label.text == "Ajouter du bois"
      and G.WowlheimSmeltOreLabel.text == "Bois")
ui.execute("Tick(2.1)")
check("rafraîchissement du four affiché", sent()[-1] == ".build api smelter status 9500201")
ui.execute('ChatSystem("[WL]M|Station trop loin (5 m au plus)."); ChatSystem("[WL]E|trop loin"); ChatSystem("[WL]D|smelter|0")')
check("station hors de portée : panneau fermé + avertissement", not sf.shown and "5 m" in errors()[-1])
ui.execute('ChatSystem("[WL]M|Pièce Mur posée (id 9500002)")')
check("messages du marteau toujours affichés hors requêtes", errors()[-1] == "Pièce Mur posée (id 9500002)")
# --- touches par défaut (API simulée) et positions des panneaux --------------------------------------------
ui.execute("""
BINDS = { B = "TOGGLEBACKPACK", I = "TOGGLEPETBOOK" }; BIND_SAVES = 0; BIND_SETS = 0
function GetBindingAction(k) return BINDS[k] or "" end
function GetBindingKey(a) for k, v in pairs(BINDS) do if v == a then return k end end end
function SetBinding(k, a) BINDS[k] = a; BIND_SETS = BIND_SETS + 1 end
function GetCurrentBindingSet() return 2 end
function SaveBindings(set) BIND_SAVES = BIND_SAVES + 1; SAVED_SET = set end
WowlheimDB.bindingsDone = nil
Fire("PLAYER_ENTERING_WORLD")
""")
check("entrée en jeu : touches libres liées et sauvegardées (jeu de liaisons courant)", G.BINDS["Y"] == "WOWLHEIM_TOGGLE" and G.BINDS["ALT-E"] == "WOWLHEIM_ROTATE_RIGHT"
      and G.BINDS["I"] == "TOGGLEPETBOOK" and G.BINDS["SHIFT-K"] == "WOWLHEIM_SKILLS" and G.BIND_SAVES == 1 and G.SAVED_SET == 2 and G.BIND_SETS == 7)
ui.execute('BINDS["Y"] = nil; Fire("PLAYER_ENTERING_WORLD")')
check("entrée en jeu suivante : rien n'est reposé", G.BINDS["Y"] is None and G.BIND_SAVES == 1 and G.BIND_SETS == 7)
ui.execute('BINDS["Y"] = "WOWLHEIM_TOGGLE"')
check("aide du panneau : touches réellement liées", WL.KeyText("WOWLHEIM_ROTATE_LEFT", "?") in ("Alt+A", "Ctrl+molette bas") and WL.KeyText("WOWLHEIM_CRAFT", "aucune") == "aucune")
hf = G.WowlheimFrame
dl, db_ = core.PanelDefaultPos("hammer", 1024, 768)
check("menu du marteau : échelle réduite, position par défaut en bas à droite", hf.scale == 0.85 and hf.point[1] == "BOTTOMLEFT"
      and abs(hf.point[4] * 0.85 - dl) < 1e-6 and abs(hf.point[5] * 0.85 - db_) < 1e-6, str(list(hf.point.values())))
ui.execute("WowlheimFrame:SetPoint('BOTTOMLEFT', UIParent, 'BOTTOMLEFT', 100, 200); RunScript(WowlheimFrame, 'OnDragStop')")
check("Maj+glisser : position mémorisée (unités UIParent)", abs(G.WowlheimDB.pos.hammer[1] - 85) < 1e-6 and abs(G.WowlheimDB.pos.hammer[2] - 170) < 1e-6)
ui.execute("Wowlheim.frame = nil; Wowlheim.BuildFrame()")
check("position mémorisée réappliquée à la construction du panneau", abs(G.WowlheimFrame.point[4] - 100) < 1e-6 and abs(G.WowlheimFrame.point[5] - 200) < 1e-6)
ui.execute("WowlheimFrame:Show(); RunScript(WowlheimClose, 'OnClick', 'LeftButton')")
check("bouton x : ferme le menu du marteau", not G.WowlheimFrame.shown)
cf = G.WowlheimCraftFrame
cl, cb = core.PanelDefaultPos("craft", 1024, 768)
check("fabrication : position par défaut en haut à gauche", cf is not None and cf.scale == 0.8 and abs(cf.point[4] * 0.8 - cl) < 1e-6 and abs(cf.point[5] * 0.8 - cb) < 1e-6)
ui.execute("WowlheimSmeltFrame:SetPoint('BOTTOMLEFT', UIParent, 'BOTTOMLEFT', 400, 300); RunScript(WowlheimSmeltFrame, 'OnDragStop')")
check("fonderie : glisser mémorise la position", abs(G.WowlheimDB.pos.smelt[1] - 340) < 1e-6)
ui.execute('SlashCmdList["WOWLHEIM"]("reset")')
sl, sb = core.PanelDefaultPos("smelt", 1024, 768)
check("/wl reset : positions par défaut", G.WowlheimDB.pos is None and abs(G.WowlheimSmeltFrame.point[4] * 0.85 - sl) < 1e-6
      and abs(G.WowlheimFrame.point[4] * 0.85 - dl) < 1e-6)

check("libellés des raccourcis", G.BINDING_NAME_WOWLHEIM_CRAFT == "Wowlheim : fabrication" and G.BINDING_NAME_WOWLHEIM_SMELT.startswith("Wowlheim : fonderie"))
bind = read("Bindings.xml")
check("Bindings.xml : fabrication et fonderie", "WOWLHEIM_CRAFT" in bind and "Wowlheim.Craft.Toggle()" in bind and "WOWLHEIM_SMELT" in bind and "Wowlheim.Smelt.Toggle()" in bind)
check("Wowlheim.toc charge WowlheimCraft.lua après Wowlheim.lua", read("Wowlheim.toc").split().index("WowlheimCraft.lua") > read("Wowlheim.toc").split().index("Wowlheim.lua"))

# --- cercle de portée des stations (Valheim : CraftingStation.m_areaMarker) ---------------------------------
st = core.ParseLine("[WL]ST|9500143|workbench|-8913.50|-120.25|94.10|10.0|1|8")
check("ligne ST", st["type"] == "ST" and st["guid"] == 9500143 and st["kind"] == "workbench" and st["inside"] and st["n"] == 8
      and abs(st["x"] + 8913.5) < 1e-9 and st["range"] == 10)
sg = core.ParseLine("[WL]SG|9500143|6|-8900.1,-120.3,94.15,1.57;-8901.0,-119.0,94.20,1.80")
check("ligne SG : points x,y,z,o", sg["type"] == "SG" and sg["first"] == 6 and sg["points"].n == 2 and sg["points"][2]["z"] == 94.2 and sg["points"][1]["o"] == 1.57)
check("SG : point incomplet ignoré", core.ParsePoints("1,2;3,4,5,6").n == 1)
rs = core.NewRings()
check("cercles : marteau en construction seulement", core.RingsWanted(lua.eval("{mode='build'}"), 1) and not core.RingsWanted(lua.eval("{mode='remove'}"), 1)
      and not core.RingsWanted(lua.eval("{mode='build'}"), None))
check("avertissement inconnu tant qu'aucune liste n'est reçue", core.StationRangeWarning(rs, "workbench", data.stations) is None)
pts = ";".join("%d,0,10,0" % k for k in range(6))
for ln in ("[WL]ST|1|workbench|0|0|10|10.0|0|8", "[WL]SG|1|0|" + pts, "[WL]SG|1|6|6,0,10,0;7,0,10,0",
           "[WL]ST|2|forge|50|0|10|10.0|1|3", "[WL]SG|2|0|50,1,10,0;50,2,10,0;50,3,10,0"):
    core.RingsOnMessage(rs, core.ParseLine(ln))
check("liste remplacée seulement à D|stations", rs.stations.n == 0 and core.RingsOnMessage(rs, core.ParseLine("[WL]D|stations|1")) == "update" and rs.stations.n == 2)
mk = core.RingMarkers(rs.stations, 256)
check("segments : 8 + 3, ids 0..10 contigus", mk.n == 11 and mk[1]["id"] == 0 and mk[11]["id"] == 10 and mk[8]["x"] == 7 and mk[9]["x"] == 50)
check("segments : rouge hors zone, vert dans la zone", mk[1]["path"] == core.RING_MODELS.outside and mk[9]["path"] == core.RING_MODELS.inside
      and core.RING_MODELS.inside == "World\\Wowlheim\\wl_station_ring_in.m2")
check("segments : plafond des marqueurs", core.RingMarkers(rs.stations, 5).n == 5)
check("hors de portée de l'établi", core.StationRangeWarning(rs, "workbench", data.stations) == "Hors de portée de la table de fabrication")
check("dans la zone de la forge : pas d'avertissement", core.StationRangeWarning(rs, "forge", data.stations) is None)
check("pièce sans station : pas d'avertissement", core.StationRangeWarning(rs, "", data.stations) is None)
check("station absente des environs : avertissement nommé", core.StationRangeWarning(rs, "stonecutter", data.stations) == "Hors de portée : Tailleur de pierre")
core.RingsOnMessage(rs, core.ParseLine("[WL]D|stations|1"))
check("D|stations sans ST : plus aucune station", rs.stations.n == 0 and core.StationRangeWarning(rs, "workbench", data.stations) is not None)
ch = core.NewChannel()
core.ChannelPush(ch, ".build api stations", 1, 0)
core.ChannelPush(ch, ".build api craft 101", None, 0)
check("canal : un M| reçu pendant l'interrogation des stations appartient à la commande suivante",
      core.ChannelRoute(ch, core.ParseLine("[WL]M|Fabriqué"), 0)["cmd"] == "craft" and core.ChannelRoute(ch, core.ParseLine("[WL]ST|1|workbench|0|0|0|10|1|0"), 0)["cmd"] == "stations")
ch = core.NewChannel()
core.ChannelPush(ch, ".build api stations", 1, 0)
check("canal : E| non sollicité pendant l'interrogation des stations => à personne", core.ChannelRoute(ch, core.ParseLine("[WL]E|Démolition impossible"), 0) is None
      and core.ChannelRoute(ch, core.ParseLine("[WL]D|stations|1"), 0)["cmd"] == "stations")

# cercles dans l'API WoW simulee (DLL simulee : WowlheimMarkerShow / WowlheimMarkerHide)
ui.execute("""MARKERS = {}; MARKER_CALLS = 0
function WowlheimMarkerShow(id, path, x, y, z, o) MARKERS[id] = { path = path, x = x, y = y, z = z, o = o }; MARKER_CALLS = MARKER_CALLS + 1; return 1 end
function WowlheimMarkerHide(id) if id then MARKERS[id] = nil else MARKERS = {} end end
function MarkerCount() local n = 0; for _ in pairs(MARKERS) do n = n + 1 end; return n end
for i, p in ipairs(WowlheimData.pieces) do if p.station == "workbench" then BENCH_PIECE = p; break end end""")
ui.execute('Wowlheim.HideRings(); EQUIPPED = "|Hitem:9201100:0:0:0|h[Marteau]|h"; Fire("UNIT_INVENTORY_CHANGED", "player"); Wowlheim.ChooseEntry(BENCH_PIECE); Tick(7)')
check("marteau en construction : interrogation des stations", ".build api stations" in sent())
n_chat = len(G.CHAT_SHOWN)
ring = ['[WL]ST|9500143|workbench|10.00|20.00|5.00|10.0|0|8', '[WL]SG|9500143|0|' + ";".join("%d,1,5.05,%.2f" % (k, k * 0.5) for k in range(6)),
        '[WL]SG|9500143|6|6,1,5.05,3.00;7,1,5.05,3.50', '[WL]D|stations|1']
def feed(lines):
    ui.execute(";".join('ChatSystem("%s")' % l for l in lines))
feed(ring)
check("8 segments posés (modèle rouge : hors zone), lignes masquées du chat", G.MarkerCount() == 8 and G.MARKERS[0].path == "World\\Wowlheim\\wl_station_ring_out.m2"
      and G.MARKERS[7].x == 7 and abs(G.MARKERS[7].o - 3.5) < 1e-9 and len(G.CHAT_SHOWN) == n_chat, str(G.MarkerCount()))
check("bandeau de pose : « Hors de portée de la table de fabrication »", "Hors de portée de la table de fabrication" in (G.WowlheimPlaceBannerText.text or ""),
      str(G.WowlheimPlaceBannerText.text))
n_sent = len(sent())
ui.execute("Tick(0.5)")
check("pas de 2e interrogation avant le délai", len(sent()) == n_sent)
ui.execute("Tick(1.6)")
check("interrogation périodique (1,5 s)", sent()[-1] == ".build api stations" and len(sent()) == n_sent + 1)
ui.execute("Tick(1.6)")
check("pas de 2e interrogation tant que la 1re n'a pas répondu", len(sent()) == n_sent + 1)
calls = G.MARKER_CALLS
ring[0] = ring[0].replace("|0|8", "|1|8")
feed(ring)
check("joueur entré dans la zone : segments verts, bandeau sans avertissement", G.MARKERS[0].path == "World\\Wowlheim\\wl_station_ring_in.m2"
      and "Hors de port" not in (G.WowlheimPlaceBannerText.text or "") and G.MARKER_CALLS == calls + 8)
ui.execute("Tick(1.6)")
feed(["[WL]ST|9500143|workbench|10|20|5|10.0|1|3", "[WL]SG|9500143|0|0,1,5,0;1,1,5,0;2,1,5,0", "[WL]D|stations|1"])
check("contour plus court : segments en trop masqués", G.MarkerCount() == 3 and G.MARKERS[3] is None)
n_err = len(errors())
ui.execute("Tick(1.6)")
ui.execute('Wowlheim.Hide(); ChatSystem("[WL]E|Démolition impossible : pièce protégée")')
check("E| reçu pendant l'interrogation silencieuse : affiché quand même", len(errors()) == n_err + 1 and "Démolition" in errors()[-1])
feed(["[WL]D|stations|1"])
check("réponse vide : plus de segments", G.MarkerCount() == 0)
ui.execute("Tick(1.6)")
feed(ring)
check("segments reposés", G.MarkerCount() == 8)
ui.execute("Wowlheim.ChooseEntry(WowlheimCore.SPECIALS[2]); Tick(0.1)")
check("mode Démolir : cercles masqués", G.MarkerCount() == 0 and WL.ringCount == 0)
ui.execute("Wowlheim.ChooseEntry(BENCH_PIECE); Tick(7)")
feed(ring)
check("retour en construction : cercles reposés", G.MarkerCount() == 8)
ui.execute('EQUIPPED = nil; Fire("UNIT_INVENTORY_CHANGED", "player"); Tick(0.1)')
n_sent = len(sent())
ui.execute("Tick(3)")
check("marteau rangé : cercles masqués, plus d'interrogation", G.MarkerCount() == 0 and len(sent()) == n_sent)
ui.execute("WowlheimMarkerShow = nil; WowlheimMarkerHide = nil")

# --- recherche, pièces connues (Valheim), clic sur une station, réparation : logique pure ------------------
check("repli : casse et accents", core.Fold("Œil de NAINGRIS") == "oeil de naingris" and core.Fold("Écorce ANCIENNE à Mûrir") == "ecorce ancienne a murir"
      and core.Fold(None) == "")
w = core.SearchWords("  Écorce   anc ")
check("mots de recherche (repliés, espaces ignorés)", w.n == 2 and w[1] == "ecorce" and w[2] == "anc" and core.SearchWords("").n == 0 and core.SearchWords(None).n == 0)
check("correspondance nom + description, tous les mots", core.EntryMatches(w, "Écorce ancienne", None) and core.EntryMatches(core.SearchWords("robuste"), "Écorce", "Un matériau ancien et robuste.")
      and not core.EntryMatches(core.SearchWords("ecorce fer"), "Écorce ancienne", "") and core.EntryMatches(core.SearchWords(""), "x", None))
m = core.ParseLine("[WL]K|9200001,9200002,,9200013")
check("ligne K (objets connus)", m["type"] == "K" and m["items"].n == 3 and m["items"][3] == 9200013)
m = core.ParseLine("[WL]KS|workbench,forge")
check("ligne KS (stations connues)", m["type"] == "KS" and m["stations"].n == 2 and m["stations"][2] == "forge")
check("ligne K vide", core.ParseLine("[WL]K|")["items"].n == 0)
m = core.ParseLine("[WL]OPEN|craft|9500143|workbench")
check("ligne OPEN", m["type"] == "OPEN" and m["what"] == "craft" and m["guid"] == 9500143 and m["kind"] == "workbench")
m = core.ParseLine("[WL]RI|9201011|40|100")
check("ligne RI", m["type"] == "RI" and m["item"] == 9201011 and m["dur"] == 40 and m["max"] == 100)
check("ligne R", core.ParseLine("[WL]R|9201011,9201010")["items"].n == 2)
ks = core.NewKnown()
costs_ws = lua.eval("{ {9200001, 2}, {9200002, 1} }")
check("known : sans réponse, tout est connu (compatibilité)", core.IsKnown(ks, costs_ws, "forge", lua.eval("{}"), None))
core.KnownOnMessage(ks, core.ParseLine("[WL]K|9200001"))
core.KnownOnMessage(ks, core.ParseLine("[WL]K|9200003"))
core.KnownOnMessage(ks, core.ParseLine("[WL]KS|workbench"))
check("known : liste remplacée seulement à D|known", not ks.loaded and core.KnownOnMessage(ks, core.ParseLine("[WL]D|known|1")) == "update" and ks.loaded and ks["items"][9200003])
check("known : matériau inconnu => caché", not core.IsKnown(ks, costs_ws, "", lua.eval("{}"), None))
check("known : matériau présent dans les sacs => connu (union locale)", core.IsKnown(ks, costs_ws, "", lua.eval("{ [9200002] = 1 }"), None))
check("known : station inconnue => caché ; station à portée => connue", not core.IsKnown(ks, lua.eval("{ {9200001, 1} }"), "forge", lua.eval("{}"), None)
      and core.IsKnown(ks, lua.eval("{ {9200001, 1} }"), "forge", lua.eval("{}"), lua.eval("{ forge = true }"))
      and core.IsKnown(ks, lua.eval("{ {9200001, 1} }"), "workbench", lua.eval("{}"), None))
ks_old = core.NewKnown()
core.KnownOnMessage(ks_old, core.ParseLine("[WL]D|known|0"))
check("known : ancien serveur (D|known|0) => tout affiché, plus d'interrogation sur BAG_UPDATE", ks_old.unsupported and core.IsKnown(ks_old, costs_ws, "forge", lua.eval("{}"), None))
core.KnownOnMessage(ks, core.ParseLine("[WL]D|known|0"))
check("known : échec ultérieur => liste précédente conservée", ks.loaded and ks["items"][9200001] and not ks.unsupported)
ch = core.NewChannel()
core.ChannelPush(ch, ".build api known", 1, 0)
check("canal : « E|commande inconnue » rattaché à known (silencieux), un autre E| non", core.ChannelRoute(ch, core.ParseLine("[WL]E|commande inconnue"), 0)["cmd"] == "known"
      and core.ChannelRoute(ch, core.ParseLine("[WL]E|Démolition impossible"), 0) is None and core.ChannelRoute(ch, core.ParseLine("[WL]K|1"), 0)["cmd"] == "known")
# menu du marteau : recherche dans toutes les catégories + pièces inconnues cachées
allp = core.MenuEntries(pieces, 3, "", None, lua.eval("{}"), None)
check("menu sans recherche ni known : identique à la catégorie", allp.n == core.CategoryEntries(pieces, 3).n and not allp.searching)
target = None
for i in range(1, n_pieces + 1):
    if pieces[i]["cat"] != 3 and any(ord(ch_) > 127 for ch_ in pieces[i]["name"]):
        target = pieces[i]; break
q = core.Fold(target["name"]).upper()
res = core.MenuEntries(pieces, 3, q, None, lua.eval("{}"), None)
check("recherche « %s » (sans accents, majuscules) : trouvée hors de la catégorie courante" % q, res.searching and any(res[i]["id"] == target["id"] for i in range(1, res.n + 1)))
res = core.MenuEntries(pieces, 3, "demol", None, lua.eval("{}"), None)
check("recherche « demol » : l'outil Démolir", res.n >= 1 and res[1]["special"] == "remove")
res = core.MenuEntries(pieces, 3, "zzzz introuvable", None, lua.eval("{}"), None)
check("recherche sans résultat", res.n == 0 and res.searching)
kw = core.NewKnown(); kw.loaded = 1; kw["items"] = lua.eval("{ [9200001] = true }"); kw.stations = lua.eval("{}")
res = core.MenuEntries(pieces, 1, "", kw, lua.eval("{}"), None)
okk = all(res[i]["special"] or (res[i]["station"] == "" and all(res[i]["costs"][j][1] == 9200001 for j in range(1, len(res[i]["costs"]) + 1))) for i in range(1, res.n + 1))
check("known : seulement les pièces au bois sans station (+ Réparer / Démolir)", okk and res[1]["special"] == "repair" and res.n < core.CategoryEntries(pieces, 1).n, str(res.n))
# recettes : recherche (toutes stations) et known
lst = core.RecipeList(recs, cnt, None, None, lua.table_from({"query": "pioche", "items": data["items"]}))
check("recettes : recherche « pioche » => la forge aussi (toutes les stations)", lst.n == 1 and lst[1]["r"]["id"] == 106)
lst = core.RecipeList(recs, cnt, None, None, lua.table_from({"query": "HACHE"}))
ids = sorted(lst[i]["r"]["id"] for i in range(1, lst.n + 1))
check("recettes : recherche insensible à la casse (main + établi)", ids == [100, 101], str(ids))
kr = core.NewKnown(); kr.loaded = 1; kr["items"] = lua.eval("{}"); kr.stations = lua.eval("{}")
lst = core.RecipeList(recs, lua.eval("{ [9200001] = 5 }"), None, True, lua.table_from({"known": kr}))
check("recettes : matériau jamais possédé (pierre) => cachées", lst.n == 0)
lst = core.RecipeList(recs, cnt, bench1, True, lua.table_from({"known": kr}))
ids = sorted(lst[i]["r"]["id"] for i in range(1, lst.n + 1))
check("recettes : sacs + établi à portée connus ; forge inconnue cachée", ids == [99, 100, 101, 150], str(ids))
# clic sur une station
cs = core.NewCraft()
core.CraftOnMessage(cs, core.ParseLine("[WL]S|9500143|1|100|1|workbench"))
core.CraftOnMessage(cs, core.ParseLine("[WL]D|station|1"))       # ancienne réponse : établi
core.CraftOnMessage(cs, core.ParseLine("[WL]S|9500150|1|100|2|forge"))
core.CraftOnMessage(cs, core.ParseLine("[WL]S|9500151|1|100|1|stonecutter"))
check("clic sur une station : S| d'abord, puis OPEN|craft (déclencheur) => stations du clic seulement",
      core.CraftOnMessage(cs, core.ParseLine("[WL]OPEN|craft|9500150|forge")) == "open" and cs.station["kind"] == "forge"
      and cs.station.all["stonecutter"] and not cs.station.all["workbench"] and cs.loose is None)
check("OPEN d'un autre type : ignoré", core.CraftOnMessage(cs, core.ParseLine("[WL]OPEN|smelt|1|smelter")) is None)
# réparation
rp = core.NewRepair()
check("commandes de réparation (station visée)", core.RepairableCommand(5) == ".build api repairable 5" and core.RepairItemsCommand(None) == ".build api repairitems")
check("réparer : rien => bouton inactif", core.RepairButton(rp) == (False, "Réparer"))
m = core.ParseLine("[WL]RS|9500143|workbench|2")
check("ligne RS", m["type"] == "RS" and m["guid"] == 9500143 and m["kind"] == "workbench" and m["level"] == 2)
core.RepairOnMessage(rp, m)
for ln in ("[WL]RI|9201011|40|100", "[WL]RI|9201011|10|100", "[WL]RI|9201010|90|200"):
    core.RepairOnMessage(rp, core.ParseLine(ln))
check("réparer : liste à D|repairable", rp.list.n == 0 and core.RepairOnMessage(rp, core.ParseLine("[WL]D|repairable|1")) == "repairable" and rp.list.n == 3)
check("réparer : bouton « Réparer (3) », station RS retenue", core.RepairButton(rp) == (True, "Réparer (3)") and rp.station["guid"] == 9500143)
check("réparer : texte du plus abîmé", core.RepairText(rp, 9201011) == "Abîmé (10 %) : réparable ici" and core.RepairText(rp, 9201100) is None)
rp.busy = 1
check("réparer : inactif pendant la réparation", core.RepairButton(rp)[0] is False)
core.RepairOnMessage(rp, core.ParseLine("[WL]R|9201011,9201010"))
check("réparer : fin à D|repairitems", core.RepairOnMessage(rp, core.ParseLine("[WL]D|repairitems|1")) == "repaired" and not rp.busy and rp.repaired.n == 2)
core.RepairOnMessage(rp, core.ParseLine("[WL]D|repairable|0"))
check("réparer : refus (pas de station) => liste vidée, toujours interrogé", rp.list.n == 0 and not rp.unsupported)
rp_old = core.NewRepair()
core.RepairOnMessage(rp_old, core.ParseLine("[WL]E|commande inconnue")); core.RepairOnMessage(rp_old, core.ParseLine("[WL]D|repairable|0"))
check("réparer : ancien serveur (commande inconnue) => plus d'interrogation", rp_old.unsupported)
# formats exacts du serveur : K|item:..., KS|kind:niveau, KP| / KR| (pièces / recettes connues), KN| (découverte)
m = core.ParseLine("[WL]K|item:9200001,9200002")
check("K|item:<id>,<id> : préfixe ignoré", m["items"].n == 2 and m["items"][1] == 9200001 and m["items"][2] == 9200002)
m = core.ParseLine("[WL]KS|workbench:2,forge:1")
check("KS|kind:niveau", m["stations"].n == 2 and m["stations"][1] == "workbench" and m["levels"]["workbench"] == 2 and m["levels"]["forge"] == 1)
check("KP / KR", core.ParseLine("[WL]KP|5,14")["ids"][2] == 14 and core.ParseLine("[WL]KR|99,101")["ids"].n == 2 and core.ParseLine("[WL]KP|")["ids"].n == 0)
m = core.ParseLine("[WL]KN|station|forge|2")
check("KN|station|kind|niveau et KN|item|id", m["what"] == "station" and m["kind"] == "forge" and m["level"] == 2 and core.ParseLine("[WL]KN|item|9200021")["item"] == 9200021)
kp = core.NewKnown()
for ln in ("[WL]K|item:9200001", "[WL]K|item:9200002", "[WL]KS|workbench:1", "[WL]KP|5", "[WL]KP|", "[WL]KR|99", "[WL]D|known|1"):
    core.KnownOnMessage(kp, core.ParseLine(ln))
check("lignes coupées concaténées (K, KP)", kp["items"][9200001] and kp["items"][9200002] and kp.pieces[5] and kp.recipes[99] and kp.newPieces.n == 0)
p14 = [pieces[i] for i in range(1, n_pieces + 1) if pieces[i]["id"] == 14][0]
check("KP fait foi : pièce listée => affichée ; non listée et matériaux inconnus => cachée",
      core.PieceKnown(kp, [pieces[i] for i in range(1, n_pieces + 1) if pieces[i]["id"] == 5][0], lua.eval("{}"), None)
      and not core.PieceKnown(kp, p14, lua.eval("{}"), None))
check("KR : recette listée affichée, recette de niveau 2 sur établi niveau 1 cachée",
      core.RecipeKnown(kp, r_hammer, lua.eval("{}"), None) and not core.RecipeKnown(kp, r_lvl2, lua.eval("{}"), None))
check("KN|item : connaissance ajoutée tout de suite, relance demandée", core.KnownOnMessage(kp, core.ParseLine("[WL]KN|item|9200029")) == "learned" and kp["items"][9200029])
for ln in ("[WL]K|item:9200001", "[WL]KS|workbench:2", "[WL]KP|5,14", "[WL]KR|99,150", "[WL]D|known|1"):
    core.KnownOnMessage(kp, core.ParseLine(ln))
check("nouvelles pièces / recettes depuis la réponse précédente", kp.newPieces.n == 1 and kp.newPieces[1] == 14 and kp.newRecipes.n == 1 and kp.newRecipes[1] == 150)

# --- recherche, known, OPEN, réparation dans l'API simulée ---------------------------------------------------
ui.execute('EQUIPPED = "|Hitem:9201100:0:0:0|h[Marteau]|h"; Fire("UNIT_INVENTORY_CHANGED", "player"); Wowlheim.Show(); Tick(7)')
hf = G.WowlheimFrame
sb = G.WowlheimSearch
check("menu du marteau : champ de recherche (EditBox sans focus automatique)", sb is not None and sb.kind == "EditBox" and hf.shown)
check("champ de recherche sous les onglets, au-dessus de la grille", sb.point[5] == -(12 + 24 + 8) and G.WowlheimGrid.point[5] == -(12 + 24 + 8 + 20 + 8))
ui.execute("Wowlheim.SetCategory(3)")
ui.execute('WowlheimSearch:SetText("%s"); RunScript(WowlheimSearch, "OnTextChanged")' % q)
found = [G["WowlheimIcon%d" % i].entry.id for i in range(1, 41) if G["WowlheimIcon%d" % i].shown and G["WowlheimIcon%d" % i].entry.id]
check("recherche dans le menu : pièce d'une autre catégorie affichée", target["id"] in found and WL.entries.searching, str(found[:5]))
check("recherche : onglets désélectionnés", all(G["WowlheimTab%d" % c].label.color[1] < 1 for c in range(1, 6)))
check("recherche : aide grisée masquée", not G.WowlheimSearchHint.shown)
ui.execute('WowlheimSearch:SetText("zzzz"); RunScript(WowlheimSearch, "OnTextChanged")')
check("recherche sans résultat : message dans la grille", G.WowlheimGridEmpty.shown and "recherche" in G.WowlheimGridEmpty.text and not G.WowlheimIcon1.shown)
ui.execute("RunScript(WowlheimTab4, 'OnClick', 'LeftButton')")
check("clic sur un onglet : recherche effacée, onglet sélectionné", WL.query == "" and G.WowlheimSearch.text == "" and WL.cat == 4
      and G.WowlheimTab4.label.color[1] == 1.0 and not G.WowlheimGridEmpty.shown)
ui.execute('RunScript(WowlheimSearch, "OnEditFocusGained"); RunScript(WowlheimSearch, "OnEscapePressed"); RunScript(WowlheimSearch, "OnEditFocusLost")')
check("Échap dans le champ : focus rendu, aide réaffichée", G.WowlheimSearchHint.shown)
ui.execute("Wowlheim.selected = nil; Wowlheim.hover = nil; Wowlheim.UpdateInfo()")
_help = G.WowlheimInfoDesc.text or ""
_help_lines = [re.sub(r"\|c[0-9a-fA-F]{8}|\|r", "", l) for l in _help.split("\n")]
check("aide du menu : 5 lignes au plus (dont une vide), aucune ne dépasse ~70 caractères (zone de 400 px)",
      len(_help_lines) <= 5 and all(len(l) <= 70 for l in _help_lines) and "Clic gauche" in _help and "Échap" in _help, str(_help_lines))
# objets connus : interrogation à l'ouverture et sur BAG_UPDATE, pièces inconnues cachées
ui.execute("Wowlheim.known = WowlheimCore.NewKnown()")
ui.execute("Wowlheim.Hide(); Tick(7); Wowlheim.Show()")
check("ouverture du menu : known interrogé (silencieux)", ".build api known" in sent()[-3:] and any(G.Wowlheim.channel[i].cmd == "known" and G.Wowlheim.channel[i].silent
      for i in range(1, G.Wowlheim.channel.n + 1)), str(sent()[-3:]))
ui.execute("Wowlheim.SetCategory(3)")
n_before = WL.entries.n
n_err = len(errors())
feed(["[WL]K|9200001", "[WL]KS|", "[WL]D|known|1"])
vis = [WL.entries[i] for i in range(1, WL.entries.n + 1)]
okk = all(e.station == "" and all(WL.counts[e.costs[j][1]] or e.costs[j][1] == 9200001 for j in range(1, len(e.costs) + 1)) for e in vis)
check("known reçu : pièces aux matériaux inconnus / station inconnue cachées (pas grisées)", WL.entries.n < n_before and okk and len(errors()) == n_err,
      "%d -> %d" % (n_before, WL.entries.n))
n_sent = len(sent())
ui.execute('Fire("BAG_UPDATE", 0); Tick(0.1)')
check("BAG_UPDATE moins d'1 s après la dernière interrogation : attente", sent()[n_sent:] == [])
ui.execute('Tick(1)')
check("BAG_UPDATE : nouvelle interrogation known", sent()[n_sent:] == [".build api known"], str(sent()[n_sent:]))
ui.execute('Fire("BAG_UPDATE", 0); Tick(0.1)')
check("BAG_UPDATE répété : pas de 2e interrogation tant que la 1re attend", sent()[n_sent:] == [".build api known"])
feed(["[WL]K|item:9200001,9200002,9200003,9200004,9200009,9200011", "[WL]K|item:9200012,9200013,9200014,9200015,9200021",
      "[WL]KS|workbench:2,forge:2,stonecutter:1,artisan:1", "[WL]KP|", "[WL]KR|", "[WL]D|known|1"])
check("plus de matériaux et stations connus : plus de pièces", WL.entries.n > len(vis))
# KP fait foi : une pièce aux matériaux inconnus mais listée par le serveur apparaît ; annonce « Nouvelle pièce »
p14name = p14["name"]
ui.execute("Wowlheim.SetCategory(%d)" % p14["cat"])
check("pièce 14 cachée (matériaux inconnus, absente de KP)", not any(WL.entries[i].id == 14 for i in range(1, WL.entries.n + 1)))
n_sent = len(sent())
ui.execute('ChatSystem("[WL]KN|item|9200029"); Tick(1.1)')
check("KN| spontané : known relancé discrètement", sent()[n_sent:].count(".build api known") == 1 and len(errors()) == n_err, str(sent()[n_sent:]))
feed(["[WL]K|item:9200001,9200002,9200029", "[WL]KS|workbench:2", "[WL]KP|14", "[WL]KR|", "[WL]D|known|1"])
check("KP|14 : pièce affichée", any(WL.entries[i].id == 14 for i in range(1, WL.entries.n + 1)))
check("annonce Valheim « Nouvelle pièce de construction : %s »" % p14name, G.WowlheimMsg.text == "Nouvelle pièce de construction : " + p14name, str(G.WowlheimMsg.text))
ui.execute("Wowlheim.known = WowlheimCore.NewKnown(); Wowlheim.Update()")
ui.execute("Wowlheim.Hide()")
# clic sur une table de fabrication : OPEN|craft
ui.execute("Wowlheim.Craft.Hide(); Tick(7)")
feed(["[WL]S|9500143|1|100|2|workbench"])
check("S| spontanée seule : pas d'ouverture", not G.WowlheimCraftFrame.shown)
feed(["[WL]OPEN|craft|9500143|workbench"])
check("clic sur une table de fabrication : panneau de fabrication ouvert", G.WowlheimCraftFrame.shown)
check("OPEN : station de la table cliquée dans l'en-tête", G.WowlheimCraftStationName.text == "Table de fabrication" and "Niveau 2" in G.WowlheimCraftStationLevel.text,
      str(G.WowlheimCraftStationName.text))
feed(["[WL]S|9500143|1|100|2|workbench", "[WL]D|station|1", "[WL]S|9500143|1|100|2|workbench", "[WL]OPEN|craft|9500143|workbench"])
check("OPEN, panneau déjà ouvert : reste ouvert (pas de bascule)", G.WowlheimCraftFrame.shown)
check("OPEN : lignes masquées du chat", all("[WL]" not in str(x) for x in G.CHAT_SHOWN.values()))
# recherche dans le panneau de fabrication
ui.execute('WowlheimCraftSearch:SetText("pioche"); RunScript(WowlheimCraftSearch, "OnTextChanged")')
check("fabrication : recherche « pioche » => recette de forge (toutes stations)", G.WowlheimCraftRow1.shown and G.WowlheimCraftRow1.entry.r.id == 106 and not G.WowlheimCraftRow2.shown)
ui.execute('WowlheimCraftSearch:SetText("zzzz"); RunScript(WowlheimCraftSearch, "OnTextChanged")')
check("fabrication : recherche sans résultat", not G.WowlheimCraftRow1.shown and "recherche" in G.WowlheimCraftEmpty.text)
ui.execute('WowlheimCraftSearch:SetText(""); RunScript(WowlheimCraftSearch, "OnTextChanged")')
check("fabrication : recherche vidée => liste normale", G.WowlheimCraftRow1.shown and G.WowlheimCraftSearchHint.shown)
# réparation à la station
ui.execute("Wowlheim.Craft.repair = WowlheimCore.NewRepair()")
ui.execute("Wowlheim.Craft.Update()")
check("réparer : bouton présent, inactif sans objet abîmé", G.WowlheimCraftRepair is not None and not G.WowlheimCraftRepair.enabled)
n_sent = len(sent())
ui.execute("Tick(5.1)")
check("rafraîchissement : station + repairable <guid de la station>", ".build api repairable 9500143" in sent()[n_sent:], str(sent()[n_sent:]))
feed(["[WL]S|9500143|1|100|2|workbench", "[WL]D|station|1", "[WL]RS|9500143|workbench|2", "[WL]RI|9201011|40|100", "[WL]D|repairable|1"])
rows_rep = [i for i in range(1, 13) if G["WowlheimCraftRow%d" % i].shown and G["WowlheimCraftRow%d" % i].entry.r.id == 101]
check("objet abîmé : bouton « Réparer (1) » actif, marteau sur la ligne de la recette", G.WowlheimCraftRepair.enabled and G.WowlheimCraftRepairText.text == "Réparer (1)"
      and rows_rep and G["WowlheimCraftRow%dRepair" % rows_rep[0]].shown, str(G.WowlheimCraftRepairText.text))
ui.execute("RunScript(WowlheimCraftRow%d, 'OnClick', 'LeftButton')" % rows_rep[0])
check("fiche : « Abîmé (40 %) : réparable ici »", G.WowlheimCraftRepairInfo.text == "Abîmé (40 %) : réparable ici", str(G.WowlheimCraftRepairInfo.text))
ui.execute("RunScript(WowlheimCraftRepair, 'OnClick', 'LeftButton')")
check("Réparer : repairitems <guid RS> envoyé, bouton inactif", sent()[-1] == ".build api repairitems 9500143" and not G.WowlheimCraftRepair.enabled)
feed(["[WL]R|9201011", "[WL]M|Réparé : Hache en silex", "[WL]D|repairitems|1"])
check("réparation terminée : message dans le panneau, nouvelle liste demandée", "Réparé" in G.WowlheimCraftMsg.text and sent()[-1] == ".build api repairable 9500143",
      str(G.WowlheimCraftMsg.text))
feed(["[WL]D|repairable|1"])
check("plus rien à réparer : bouton inactif, plus d'indication", not G.WowlheimCraftRepair.enabled and G.WowlheimCraftRepairInfo.text == ""
      and not G["WowlheimCraftRow%dRepair" % rows_rep[0]].shown)

# --- compétences et endurance « outils » (WowlheimCore + WowlheimSkills.lua) ------------------------------------
m = core.ParseLine("[WL]EN|372|500|600|1")
check("EN| : endurance en dixièmes, délai en s, clignotement", m.type == "EN" and abs(m.cur - 37.2) < 1e-6 and m.max == 50 and abs(m.delay - 0.6) < 1e-6 and m.flash)
m = core.ParseLine("[WL]SK|13|12|45")
check("SK| : compétence, niveau, pourcentage", m.type == "SK" and m.id == 13 and m.level == 12 and m.pct == 45)
check("SKU| / SKL|", core.ParseLine("[WL]SKU|12|3").level == 3 and core.ParseLine("[WL]SKL|5").pct == 5)
sa = core.NewStamina()
core.StaminaOnMessage(sa, core.ParseLine("[WL]EN|0|500|1000|0"), 100)
check("régénération : rien pendant le délai d'1 s (m_staminaRegenDelay)", core.StaminaNow(sa, 100.9) == 0)
v = core.StaminaNow(sa, 101 + 2.3973)
check("régénération Valheim : de 0 à 25 en ln(4/3)/0,12 s après le délai (6/s + (1 - s/M)·6/s)", abs(v - 25) < 0.05, str(v))
check("régénération : pleine (50) après 6,8 s et bornée au max", core.StaminaNow(sa, 100 + 1 + 40) == 50)
check("barre : visible pendant la régénération sans outil, cachée pleine sans outil",
      core.StaminaBarVisible(sa, 102, False) and not core.StaminaBarVisible(sa, 200, False) and core.StaminaBarVisible(sa, 200, True))
check("outils Valheim reconnus (hache, pioche, marteau), pas le bois", core.IsToolId(9201010) and core.IsToolId(9201012) and core.IsToolId(9201100) and not core.IsToolId(9200001))
sk = core.NewSkills()
ev, text = core.SkillsOnMessage(sk, core.ParseLine("[WL]SKU|13|2"))
check("montée de niveau : « Couper du bois niveau 2 »", ev == "levelup" and text == "Couper du bois niveau 2", str(text))
check("ordre du panneau = Skills.SkillType (Haches, Pioches, Couper du bois, Fabrication)",
      [core.SKILLS[i].name for i in range(1, core.SKILLS.n + 1)] == ["Haches", "Pioches", "Couper du bois", "Fabrication"])
ui.execute("""
SENT = {}; EQUIPPED = "|Hitem:9201010:0:0:0|h[Hache en pierre]|h"
Fire("PLAYER_ENTERING_WORLD")
""")
check("entrée en jeu : compétences demandées (.build api skills)", ".build api skills" in list(G.SENT.values()), str(list(G.SENT.values())))
ui.execute('Tick(0.1)')
check("hache en main : barre d'endurance affichée (pleine)", G.WowlheimStaminaBar.shown and G.Wowlheim.Skills.barValue == 1)
ui.execute('ChatSystem("[WL]EN|20|500|1000|1"); Tick(0.05)')
check("refus faute d'endurance : la barre clignote (EN|...|1), ligne masquée du chat", G.Wowlheim.Skills.stamina.flashAt is not None
      and abs(G.Wowlheim.Skills.barValue - 0.04) < 0.01 and "[WL]EN|20|500|1000|1" not in list(G.CHAT_SHOWN.values()))
ui.execute('EQUIPPED = nil; Tick(3)')
check("sans outil en main : barre visible tant que l'endurance remonte", G.WowlheimStaminaBar.shown)
ui.execute('Tick(30)')
check("sans outil, endurance pleine : barre cachée", not G.WowlheimStaminaBar.shown)
ui.execute('ChatSystem("[WL]SK|13|1|91"); ChatSystem("[WL]SKU|13|2"); ChatSystem("[WL]SK|13|2|0")')
check("montée de niveau : message au centre « Compétence améliorée / Couper du bois niveau 2 »", G.WowlheimSkillMsg.shown
      and G.WowlheimSkillMsgTitle.text == "Compétence améliorée" and G.WowlheimSkillMsgText.text == "Couper du bois niveau 2")
ui.execute('Tick(3.5)')
check("message de montée de niveau effacé après 3 s", not G.WowlheimSkillMsg.shown)
ui.execute('SENT = {}; Wowlheim.Skills.Toggle()')
sf = G.WowlheimSkillsFrame
check("panneau Compétences : ouvert, fermable par Échap, compétences redemandées", sf.shown and "WowlheimSkillsFrame" in list(G.UISpecialFrames.values())
      and list(G.SENT.values()) in ([".build api skills"], []), str(list(G.SENT.values())))
check("panneau Compétences : Couper du bois niveau 2 (3e ligne)", G.WowlheimSkillRow3Name.text == "Couper du bois" and G.WowlheimSkillRow3Level.text == "2")
ui.execute('ChatSystem("[WL]SKL|5"); ChatSystem("[WL]SK|13|1|0")')
check("perte à la mort : message « Compétences abaissées (-5 %) », niveau mis à jour", G.WowlheimSkillMsgTitle.text == "Compétences abaissées (-5 %)"
      and G.WowlheimSkillRow3Level.text == "1")
ui.execute('SlashCmdList["WOWLHEIM"]("skills")')
check("/wl skills : bascule le panneau", not sf.shown)
check("Wowlheim.toc charge WowlheimSkills.lua après WowlheimCraft.lua", read("Wowlheim.toc").split().index("WowlheimSkills.lua") > read("Wowlheim.toc").split().index("WowlheimCraft.lua"))
check("Bindings.xml : WOWLHEIM_SKILLS", "WOWLHEIM_SKILLS" in read("Bindings.xml") and G.BINDING_NAME_WOWLHEIM_SKILLS)
# --- contrôles du mode construction (docs/BUILD_CONTROLS.md) -------------------------------------------
# logique pure : liaisons temporaires, clic milieu, détection du clic droit, modèles à précharger
binds = {"BUTTON3": "MOVEANDSTEER", "MOUSEWHEELUP": "CAMERAZOOMIN", "MOUSEWHEELDOWN": "CAMERAZOOMOUT", "Q": "STRAFELEFT", "E": "STRAFERIGHT"}
tapi = lua.table_from({"action": lambda k: binds.get(k, ""),
                       "set": lambda k, a: binds.__setitem__(k, a) if a else binds.pop(k, None)})
saved = lua.table()
check("liaisons temporaires : clic milieu = démolir, molette = rotation (3 touches)", core.TempBindApply(saved, tapi, core.BuildKeys(None)) == 3
      and binds["BUTTON3"] == "WOWLHEIM_REMOVE" and binds["MOUSEWHEELUP"] == "WOWLHEIM_ROTATE_RIGHT" and binds["MOUSEWHEELDOWN"] == "WOWLHEIM_ROTATE_LEFT"
      and binds["Q"] == "STRAFELEFT" and saved["BUTTON3"] == "MOVEANDSTEER", str(binds))
check("liaisons temporaires : pas reposées deux fois", core.TempBindApply(saved, tapi, core.BuildKeys(None)) == 0)
check("liaisons temporaires rétablies (valeurs d'origine, mémoire vidée)", core.TempBindRestore(saved, tapi) == 3 and binds["BUTTON3"] == "MOVEANDSTEER"
      and binds["MOUSEWHEELUP"] == "CAMERAZOOMIN" and binds["MOUSEWHEELDOWN"] == "CAMERAZOOMOUT" and len(list(saved.keys())) == 0, str(binds))
binds.pop("BUTTON3")
core.TempBindApply(saved, tapi, core.BuildKeys(1))
check("option Q / E : 5 touches ; touche libre mémorisée comme vide", binds["Q"] == "WOWLHEIM_ROTATE_LEFT" and binds["E"] == "WOWLHEIM_ROTATE_RIGHT"
      and saved["BUTTON3"] == "")
binds["MOUSEWHEELUP"] = "MACRO_ZOOM"
core.TempBindRestore(saved, tapi)
check("rétablissement : touche libre redéliée, touche reliée par le joueur entre-temps conservée", "BUTTON3" not in binds
      and binds["MOUSEWHEELUP"] == "MACRO_ZOOM" and binds["Q"] == "STRAFELEFT", str(binds))
binds.update({"BUTTON3": "WOWLHEIM_REMOVE", "MOUSEWHEELDOWN": "WOWLHEIM_ROTATE_LEFT"})
check("liaison temporaire enregistrée par erreur : remise à l'origine du client", core.TempBindRepair(tapi) == 2 and binds["BUTTON3"] == "MOVEANDSTEER"
      and binds["MOUSEWHEELDOWN"] == "CAMERAZOOMOUT")
check("construction seulement : marteau équipé, mode construction", core.BuildControlsWanted(lua.eval("{mode='build'}"), 1)
      and not core.BuildControlsWanted(lua.eval("{mode='remove'}"), 1) and not core.BuildControlsWanted(lua.eval("{mode='build'}"), None))
check("clic milieu sur une pièce : removeguid <guid>", core.RemoveCommand(True, "F1108B0172000123", 9110002) == ".build api removeguid F1108B0172000123")
r = core.RemoveCommand(True, "F110000C3500002A", 50000)
check("clic milieu sur un objet qui n'est pas une pièce : rien + « Rien à démolir. »", r[0] is None and r[1] == "Rien à démolir.")
check("clic milieu sans objet sous la souris : rien", core.RemoveCommand(True, None, None)[0] is None)
check("clic milieu sans DLL : repli .build api remove", core.RemoveCommand(False, None, None) == ".build api remove")
ur = core.NewUseRetry()
r = core.UseRetry(ur, "You are too far away.", "You are too far away.", "F1108B0172000123", 9110040, 10)
check("clic droit trop loin (client) sur une pièce : use <guid>, message masqué", r[0] == ".build api use F1108B0172000123" and r[1])
r = core.UseRetry(ur, "You are too far away.", "You are too far away.", "F1108B0172000123", 9110040, 10.1)
check("même pièce, même clic (< 0,25 s) : pas de 2e commande, toujours masqué", r[0] is None and r[1])
r = core.UseRetry(ur, "You are too far away.", "You are too far away.", "F1108B0172000123", 9110040, 10.5)
check("même pièce, nouveau clic : use renvoyé", r[0] == ".build api use F1108B0172000123")
r = core.UseRetry(ur, "You are too far away.", "You are too far away.", "F110000C3500002A", 50000, 20)
check("trop loin sur autre chose qu'une pièce (PNJ, coffre) : rien, message affiché", r[0] is None and not r[1])
r = core.UseRetry(ur, "Out of range.", "You are too far away.", "F1108B0172000123", 9110040, 30)
check("autre erreur sur une pièce : rien, message affiché", r[0] is None and not r[1])
r = core.UseRetry(ur, "You are too far away.", None, "F1108B0172000124", 9110040, 40)
check("constante ERR_USE_TOO_FAR absente : repli sur le texte anglais", r[0] == ".build api use F1108B0172000124")
check("objet sous la souris : contrôle du guid", core.IsPieceObject("F1108B0172000123", 9110002) and not core.IsPieceObject("F1108B01720001", 9110002)
      and not core.IsPieceObject("F1108B017200012G", 9110002) and not core.IsPieceObject(None, 9110002))
tw = core.NewTargetWatch()
core.TargetWatchStart(tw, 10)
check("surveillance : rien tant que le ciblage n'a pas commencé", core.TargetWatchUpdate(tw, None, 10.1) is None and tw.armedAt)
core.TargetWatchUpdate(tw, 1, 10.2)
check("ciblage fin sans pose : rien avant 0,3 s", tw.active and core.TargetWatchUpdate(tw, None, 10.3) is None
      and core.TargetWatchUpdate(tw, None, 10.5) is None)
check("ciblage fin sans pose : menu après 0,3 s (clic droit)", core.TargetWatchUpdate(tw, None, 10.61) == "menu" and core.TargetWatchUpdate(tw, None, 11) is None)
core.TargetWatchStart(tw, 20); core.TargetWatchUpdate(tw, 1, 20.1); core.TargetWatchUpdate(tw, None, 20.2); core.TargetWatchCast(tw, 20.3)
check("fin du ciblage suivie d'un sort (SPELLCAST / D|place) : pose, pas de menu", core.TargetWatchUpdate(tw, None, 20.35) is None
      and core.TargetWatchUpdate(tw, None, 21) is None)
core.TargetWatchStart(tw, 30); core.TargetWatchUpdate(tw, 1, 30.1); core.TargetWatchCast(tw, 30.15)
check("sort vu avant la fin du ciblage : pose", core.TargetWatchUpdate(tw, None, 30.2) is None and core.TargetWatchUpdate(tw, None, 31) is None)
core.TargetWatchStart(tw, 40); core.TargetWatchUpdate(tw, 1, 40.1); core.TargetWatchRemove(tw, 40.15)
check("clic milieu qui annule le ciblage : relance, pas de menu", core.TargetWatchUpdate(tw, None, 40.2) == "relaunch")
core.TargetWatchStart(tw, 50); core.TargetWatchUpdate(tw, 1, 50.1)
check("bouton droit enfoncé à la fin du ciblage : menu tout de suite", core.TargetWatchUpdate(tw, None, 50.2, True) == "menu")
core.TargetWatchStart(tw, 60)
# régression 2026-10-26 (p2/115-118) : un UseInventoryItem refusé laissait la pose sans ciblage, sans relance ni menu
check("UseInventoryItem sans ciblage : nouvelle tentative (pas d'abandon silencieux)", core.TargetWatchUpdate(tw, None, 60.2) is None
      and core.TargetWatchUpdate(tw, None, 60.6) == "relaunch" and not tw.armedAt and tw.fails == 1)
core.TargetWatchStart(tw, 61); core.TargetWatchUpdate(tw, 1, 61.05)
check("ciblage obtenu : compteur d'échecs remis à zéro", tw.active and tw.fails == 0)
core.TargetWatchStop(tw)
r = []
for k in range(core.ARM_RETRIES):
    core.TargetWatchStart(tw, 70 + k)
    r.append(core.TargetWatchUpdate(tw, None, 70 + k + 0.6))
check("%d échecs de suite : menu (pièce gardée), plus de tentative" % core.ARM_RETRIES, r == ["relaunch"] * (core.ARM_RETRIES - 1) + ["menu"]
      and core.TargetWatchUpdate(tw, None, 80) is None, str(r))
core.TargetWatchStart(tw, 90); core.TargetWatchUpdate(tw, 1, 90.1); core.TargetWatchCast(tw, 90.15)
core.TargetWatchUpdate(tw, None, 90.2)
check("pose vue sans réponse du serveur : relance après PLACE_WAIT", core.TargetWatchUpdate(tw, None, 91) is None
      and core.TargetWatchUpdate(tw, None, 90.2 + core.PLACE_WAIT) == "relaunch" and core.TargetWatchUpdate(tw, None, 99) is None)
core.TargetWatchStart(tw, 100); core.TargetWatchUpdate(tw, 1, 100.1); core.TargetWatchCast(tw, 100.15); core.TargetWatchUpdate(tw, None, 100.2)
core.TargetWatchStart(tw, 100.5)
check("relance par le serveur avant PLACE_WAIT : pas de relance en double", tw.waitAt is None and core.TargetWatchUpdate(tw, 1, 100.6) is None
      and core.TargetWatchUpdate(tw, 1, 103) is None)
check("souris sur le monde : WorldFrame ou nil ; sur un cadre d'interface : non", core.MouseOnWorld(None, "W") and core.MouseOnWorld("W", "W")
      and not core.MouseOnWorld("ContainerFrame1", "W"))
md = core.ParseLine("[WL]MD|1:wood_floor,2:woodwall,x:bad")
check("ligne MD (modèles des pièces)", md.type == "MD" and md.models.n == 2 and md.models[2].prefab == "woodwall")
ms = core.NewModels()
core.ModelsOnMessage(ms, md); core.ModelsOnMessage(ms, core.ParseLine("[WL]MD|6:piece_workbench"))
check("modèles : chemins World\\Wowlheim\\<prefab>.m2 à D|models", core.ModelsOnMessage(ms, core.ParseLine("[WL]D|models|1")) == "update"
      and ms.loaded and ms.paths[2] == "World\\Wowlheim\\woodwall.m2" and ms.paths[6] == "World\\Wowlheim\\piece_workbench.m2")
kn = core.NewKnown()
for ln in ("[WL]K|item:9200001", "[WL]KP|1", "[WL]D|known|1"):
    core.KnownOnMessage(kn, core.ParseLine(ln))
pl = core.PreloadList(data.pieces, ms, kn, lua.table(), lua.table(), lua.table())
check("préchargement : pièces connues seulement (KP / matériaux et station connus)", "World\\Wowlheim\\wood_floor.m2" in list(pl.values())
      and "World\\Wowlheim\\woodwall.m2" not in list(pl.values()), str(list(pl.values())))
plall = core.PreloadList(data.pieces, ms, core.NewKnown(), lua.table(), lua.table(), lua.table_from({"World\\Wowlheim\\wood_floor.m2": True}))
check("préchargement : tout tant que known n'a pas répondu, sans les modèles déjà faits", sorted(plall[i] for i in range(1, plall.n + 1)) == ["World\\Wowlheim\\piece_workbench.m2", "World\\Wowlheim\\woodwall.m2"],
      str([plall[i] for i in range(1, plall.n + 1)]))
ch = core.NewChannel()
core.ChannelPush(ch, ".build api models", 1, 0)
check("canal : MD| appartient à models (silencieux)", core.ChannelRoute(ch, md, 0)["cmd"] == "models" and core.ChannelRoute(ch, core.ParseLine("[WL]M|Mur posée"), 0) is None)

# API WoW simulée : liaisons, DLL (survol, fondu, préchargement), sorts
BC_MOCK = r"""
BINDS = { BUTTON1 = "CAMERAORSELECTORMOVE", BUTTON2 = "TURNORACTION", BUTTON3 = "MOVEANDSTEER", MOUSEWHEELUP = "CAMERAZOOMIN",
  MOUSEWHEELDOWN = "CAMERAZOOMOUT", Q = "STRAFELEFT", E = "STRAFERIGHT", ["SHIFT-MOUSEWHEELUP"] = "PREVIOUSACTIONPAGE" }
BIND_SAVES = 0; SAVED_BINDS = nil
function GetBindingAction(k) return BINDS[k] or "" end
function GetBindingKey(a) for k, v in pairs(BINDS) do if v == a then return k end end end
function SetBinding(k, a) BINDS[k] = a end
function GetCurrentBindingSet() return 2 end
function SaveBindings(set) BIND_SAVES = BIND_SAVES + 1; SAVED_BINDS = {}; for k, v in pairs(BINDS) do SAVED_BINDS[k] = v end end
function TurnOrActionStart() end; function TurnOrActionStop() end
ORIG_TURN_START = TurnOrActionStart; ORIG_TURN_STOP = TurnOrActionStop
GAMEMENU = 0; function ToggleGameMenu() GAMEMENU = GAMEMENU + 1 end
FADE = nil; function WowlheimSetInstantFade(a, b, c, d) FADE = { a, b, c, d } end
PRELOADED = {}; function WowlheimPreloadModel(p) table.insert(PRELOADED, p); return 1 end
MOUSEOVER = nil; function WowlheimGetMouseoverObject() if MOUSEOVER then return MOUSEOVER[1], MOUSEOVER[2] end end
function Spell(ev) event = ev; WowlheimEvents.scripts.OnEvent(); event = nil end
"""
import re
BIND_BODY = {m.group(1): m.group(2).strip() for m in re.finditer(r'<Binding name="(\w+)"[^>]*>\s*(.*?)\s*</Binding>', read("Bindings.xml"), re.S)}

def new_ui(extra=""):
    u = new_lua()
    u.execute(MOCK)
    u.execute(BC_MOCK)
    u.execute(extra)
    for f in ("WowlheimData.lua", "WowlheimCore.lua", "Wowlheim.lua", "WowlheimCraft.lua", "WowlheimSkills.lua"):
        u.execute(read(f))
    return u

bc = new_ui()
B = bc.globals()
BW = B.Wowlheim

def press(key):
    """Touche / bouton de la souris : exécute le corps de la liaison (Bindings.xml) de l'action liée."""
    action = B.BINDS[key]
    if action in BIND_BODY:
        bc.execute(BIND_BODY[action])
    return action

def bsent():
    return list(B.SENT.values())

bc.execute('WowlheimDB = { cat = 3 }; Fire("VARIABLES_LOADED"); Fire("PLAYER_ENTERING_WORLD"); Tick(0.1)')
check("Bindings.xml : WOWLHEIM_REMOVE -> Wowlheim.RemoveUnderMouse()", BIND_BODY.get("WOWLHEIM_REMOVE") == "Wowlheim.RemoveUnderMouse();"
      and B.BINDING_NAME_WOWLHEIM_REMOVE)
check("marteau en main (construction) : clic milieu et molette liés temporairement", B.BINDS["BUTTON3"] == "WOWLHEIM_REMOVE"
      and B.BINDS["MOUSEWHEELUP"] == "WOWLHEIM_ROTATE_RIGHT" and B.BINDS["MOUSEWHEELDOWN"] == "WOWLHEIM_ROTATE_LEFT"
      and B.BINDS["Q"] == "STRAFELEFT" and B.BINDS["BUTTON1"] == "CAMERAORSELECTORMOVE" and B.BINDS["BUTTON2"] == "TURNORACTION", str(dict(B.BINDS)))
check("liaisons temporaires jamais enregistrées (SaveBindings seulement pour les touches par défaut, avant)", B.BIND_SAVES == 1
      and B.SAVED_BINDS["BUTTON3"] == "MOVEANDSTEER" and B.SAVED_BINDS["MOUSEWHEELUP"] == "CAMERAZOOMIN")
check("anciennes liaisons mémorisées dans WowlheimDB (/reload, plantage)", B.WowlheimDB.tempBinds["BUTTON3"] == "MOVEANDSTEER"
      and B.WowlheimDB.tempBinds["MOUSEWHEELDOWN"] == "CAMERAZOOMOUT")
check("aucune fonction protégée remplacée (TurnOrActionStart / Stop)", bc.eval("TurnOrActionStart == ORIG_TURN_START and TurnOrActionStop == ORIG_TURN_STOP"))
check("DLL : apparition instantanée activée (pièces 9110000-9119999, arbres / roches 9300000-9300099)",
      B.FADE is not None and list(B.FADE.values()) == [9110000, 9119999, 9300000, 9300099])
check("équipement du marteau : chemins des modèles demandés (.build api models, silencieux)", ".build api models" in bsent()
      and BW.channel.n > 0)
prefabs = ",".join("%d:p%d" % (p.id, p.id) for p in list(B.WowlheimData.pieces.values())[:23])
bc.execute('ChatSystem("[WL]MD|%s"); ChatSystem("[WL]D|models|1"); Tick(0.02)' % prefabs)
check("préchargement : 10 modèles par image", len(list(B.PRELOADED.values())) == 10 and list(B.PRELOADED.values())[0].startswith("World\\Wowlheim\\p"),
      str(list(B.PRELOADED.values())[:2]))
bc.execute("Tick(0.02); Tick(0.02); Tick(0.02)")
check("préchargement : tous les modèles du catalogue reçu (23), une seule fois", len(list(B.PRELOADED.values())) == 23
      and len(set(B.PRELOADED.values())) == 23)
bc.execute('EQUIPPED = nil; Fire("UNIT_INVENTORY_CHANGED", "player"); Tick(0.02); EQUIPPED = "|Hitem:9201100:0:0:0|h[Marteau]|h"; Fire("UNIT_INVENTORY_CHANGED", "player"); Tick(0.02)')
check("rééquipement : modèles déjà préchargés non repris", len(list(B.PRELOADED.values())) == 23)

# molette = rotation (liaison temporaire)
bc.execute("Wowlheim.ChooseEntry(WowlheimIcon1.entry); Tick(0.02)")
pidb = B.WowlheimIcon1.entry.id
used0 = B.USED
press("MOUSEWHEELUP")
check("molette haut (liaison temporaire) : rotation à droite, select envoyé", bsent()[-1] == ".build api select %d 1" % pidb and BW.state.rot == 1)
press("MOUSEWHEELDOWN"); press("MOUSEWHEELDOWN")
check("molette bas : rotation à gauche", bsent()[-1] == ".build api select %d 15" % pidb and BW.state.rot == 15)
check("rotation pendant la pose : ciblage conservé, menu masqué", B.TARGETING == 1 and not B.WowlheimFrame.shown and B.USED == used0)

# clic droit pendant le ciblage : le client annule le ciblage => menu (pièce conservée, pas de relance)
bc.execute("TARGETING = nil; Tick(0.1)")
check("fin du ciblage vue (clic droit possible)", BW.tw.endedAt is not None)
check("fin du ciblage : pas de menu avant 0,3 s", not B.WowlheimFrame.shown)
bc.execute("Tick(0.35)")
check("ciblage terminé sans pose (clic droit) : menu de construction ouvert après 0,3 s", B.WowlheimFrame.shown)
check("clic droit : la pièce reste choisie, ciblage non relancé", BW.state.piece == pidb and BW.state.continuous and B.USED == used0 and not B.TARGETING)
bc.execute("Tick(2)")
check("clic droit : pas de relance plus tard", B.USED == used0 and B.WowlheimFrame.shown)
bc.execute("RunScript(WowlheimIcon1, 'OnClick', 'LeftButton'); Tick(0.02)")
check("choix d'une pièce dans le menu : ciblage relancé, menu masqué", B.USED == used0 + 1 and B.TARGETING == 1 and not B.WowlheimFrame.shown)

# clic gauche au sol : pose puis enchaînement (pas de menu)
bc.execute('TARGETING = nil; Spell("SPELLCAST_STOP"); Tick(0.05); Tick(0.4)')
check("pose (SPELLCAST_STOP) : pas de menu", not B.WowlheimFrame.shown)
bc.execute('ChatSystem("[WL]M|Pièce Mur posée (id 9500001)"); ChatSystem("[WL]D|place|1"); Tick(0.3); Tick(0.02)')
check("pose réussie : ciblage relancé, même pièce (pose continue)", B.USED == used0 + 2 and B.TARGETING == 1 and BW.state.piece == pidb
      and not B.WowlheimFrame.shown)
bc.execute('TARGETING = nil; Tick(0.05); ChatSystem("[WL]D|place|1"); Tick(0.4); Tick(0.02)')
check("pose sans SPELLCAST mais D|place dans les 0,3 s : pas de menu, relance", not B.WowlheimFrame.shown and B.USED == used0 + 3 and B.TARGETING == 1)
bc.execute('TARGETING = nil; Spell("SPELLCAST_FAILED"); Tick(0.05); Tick(0.4); Tick(0.02)')
check("pose ratée côté client (SPELLCAST_FAILED) : pas de menu, ciblage relancé", not B.WowlheimFrame.shown and B.USED == used0 + 4 and B.TARGETING == 1)
bc.execute('TARGETING = nil; Tick(0.05); ChatSystem("[WL]M|Pose refusée : il faut Table de fabrication à moins de 10 m."); ChatSystem("[WL]D|place|0"); Tick(0.4); Tick(0.02)')
check("refus du serveur : la pièce reste choisie, ciblage relancé, pas de menu", not B.WowlheimFrame.shown and B.USED == used0 + 5
      and BW.state.continuous and B.TARGETING == 1)

# clic milieu : démolir la pièce sous la souris (DLL), le ciblage reste actif
bc.execute('SENT = {}; MOUSEOVER = { "F1108B0172000123", 9110002 }')
press("BUTTON3")
check("clic milieu sur une pièce : .build api removeguid <guid>", bsent() == [".build api removeguid F1108B0172000123"], str(bsent()))
bc.execute('Tick(0.5)')
check("clic milieu : ciblage et pose continue conservés, pas de menu", B.TARGETING == 1 and BW.state.continuous and not B.WowlheimFrame.shown)
n_e = len(list(B.ERRORS.values()))
bc.execute('ChatSystem("[WL]M|Démoli : Mur en bois."); ChatSystem("[WL]D|removeguid|1")')
check("réponse removeguid : « démolie » affiché, lignes masquées du chat, pose continue intacte", list(B.ERRORS.values())[-1] == "Démoli : Mur en bois."
      and BW.state.continuous and all(BW.channel[i].cmd == "pieceinfo" for i in range(1, BW.channel.n + 1))
      and not any("[WL]" in (t or "") for t in B.CHAT_SHOWN.values()))
bc.execute('MOUSEOVER = { "F1108B0172000124", 9110002 }; Wowlheim.state.pending = 1')
press("BUTTON3")
bc.execute('ChatSystem("[WL]E|Trop loin."); ChatSystem("[WL]D|removeguid|0")')
check("refus removeguid (E|) pendant une pose : affiché en erreur, pas pris pour un refus de pose", list(B.ERRORS.values())[-1] == "Trop loin."
      and BW.state.continuous and BW.state.pending == 1 and not BW.relaunchAt)
bc.execute("Wowlheim.state.pending = nil")
bc.execute('SENT = {}; MOUSEOVER = { "F110000C3500002A", 50000 }')
press("BUTTON3")
check("clic milieu sur autre chose qu'une pièce : rien envoyé, « Rien à démolir. »", bsent() == [] and list(B.ERRORS.values())[-1] == "Rien à démolir.")
bc.execute('MOUSEOVER = nil')
press("BUTTON3")
check("clic milieu dans le vide : rien envoyé", bsent() == [])
u1 = B.USED
bc.execute('MOUSEOVER = { "F1108B0172000123", 9110002 }')
press("BUTTON3")
bc.execute('TARGETING = nil; Tick(0.05); Tick(0.02)')
check("clic milieu qui annulerait le ciblage : relancé, pas de menu", B.USED == u1 + 1 and B.TARGETING == 1 and not B.WowlheimFrame.shown)
bc.execute('SENT = {}; WowlheimGetMouseoverObject = nil')
press("BUTTON3")
check("clic milieu sans DLL : repli .build api remove", bsent() == [".build api remove"])
bc.execute('function WowlheimGetMouseoverObject() if MOUSEOVER then return MOUSEOVER[1], MOUSEOVER[2] end end')

# clic droit sur une grande pièce refusé par le client (« You are too far away. ») : .build api use <guid>, message masqué
def usent():
    return [c for c in bsent() if c.startswith(".build api use")]
check("UIErrorsFrame_OnEvent enveloppée (FrameXML), aucune fonction protégée touchée",
      bc.eval("UIErrorsFrame_OnEvent ~= nil and Wowlheim.origErrorsOnEvent ~= nil and TurnOrActionStart == ORIG_TURN_START"))
bc.execute('SENT = {}; MOUSEOVER = { "F1108B0172000125", 9110040 }; Tick(1)')
n_e = len(list(B.ERRORS.values()))
bc.execute('UIError("You are too far away.")')
check("trop loin sur une fonderie : use <guid> envoyé, message rouge masqué", usent() == [".build api use F1108B0172000125"]
      and len(list(B.ERRORS.values())) == n_e, str(usent()))
bc.execute('ChatSystem("[WL]SM|9500125|Fonderie|0|0|0|0"); ChatSystem("[WL]D|use|1")')
check("réponse use : canal vidé, lignes [WL] masquées du chat", BW.channel.n == 0 and not any("[WL]" in (t or "") for t in B.CHAT_SHOWN.values()))
bc.execute('SENT = {}; MOUSEOVER = { "F110000C3500002A", 50000 }; Tick(1); UIError("You are too far away.")')
check("trop loin sur autre chose (PNJ, coffre...) : rien envoyé, message affiché", usent() == []
      and list(B.ERRORS.values())[-1] == "You are too far away.")
bc.execute('MOUSEOVER = { "F1108B0172000125", 9110040 }; UIError("Out of range.")')
check("autre erreur : affichée telle quelle", usent() == [] and list(B.ERRORS.values())[-1] == "Out of range.")
bc.execute('SENT = {}; Tick(1); UIError("You are too far away.")')
# réponses dans l'ordre d'envoi : rafraîchissement silencieux du panneau de la fonderie (ouvert par SM|) puis use
bc.execute('ChatSystem("[WL]SM|9500125|Fonderie|0|0|0|0"); ChatSystem("[WL]D|smelter|1"); ChatSystem("[WL]E|Vous êtes trop loin."); ChatSystem("[WL]D|use|0")')
check("pièce vraiment trop loin : refus du serveur affiché (« Vous êtes trop loin. »)", usent() == [".build api use F1108B0172000125"]
      and list(B.ERRORS.values())[-1] == "Vous êtes trop loin.", str(list(B.ERRORS.values())[-2:]))
bc.execute('SENT = {}; WowlheimGetMouseoverObject = nil; Tick(1); UIError("You are too far away.")')
check("sans DLL : rien envoyé, message du client affiché", usent() == [] and list(B.ERRORS.values())[-1] == "You are too far away.")
bc.execute('function WowlheimGetMouseoverObject() if MOUSEOVER then return MOUSEOVER[1], MOUSEOVER[2] end end; MOUSEOVER = nil')

# Échap : fin de la pose (pas de menu ni du menu du jeu), y compris si le client a déjà arrêté le ciblage
bc.execute("ToggleGameMenu(); Tick(0.5)")
check("Échap pendant le ciblage : fin de la pose, ni menu de construction ni menu du jeu", not BW.state.continuous and not B.WowlheimFrame.shown
      and B.GAMEMENU == 0 and not B.TARGETING)
bc.execute("Wowlheim.Show(); RunScript(WowlheimIcon1, 'OnClick', 'LeftButton'); Tick(0.02); TARGETING = nil; Tick(0.05); ToggleGameMenu(); Tick(0.5)")
check("Échap après l'annulation du ciblage par le client : fin de la pose, pas de menu", not BW.state.continuous and not B.WowlheimFrame.shown
      and B.GAMEMENU == 0)
check("hors pose, toujours en construction : liaisons temporaires gardées", B.BINDS["BUTTON3"] == "WOWLHEIM_REMOVE")

# Démolir / Réparer : liaisons d'origine (le clic droit vise la construction) ; retour en construction : reposées
bc.execute("Wowlheim.Show(); RunScript(WowlheimTab1, 'OnClick', 'LeftButton'); RunScript(WowlheimIcon2, 'OnClick', 'LeftButton'); Tick(0.02)")
check("mode Démolir : liaisons d'origine rétablies", BW.state.mode == "remove" and B.BINDS["BUTTON3"] == "MOVEANDSTEER"
      and B.BINDS["MOUSEWHEELUP"] == "CAMERAZOOMIN" and len(list(B.WowlheimDB.tempBinds.keys())) == 0)
bc.execute("Wowlheim.Show(); RunScript(WowlheimTab3, 'OnClick', 'LeftButton'); RunScript(WowlheimIcon1, 'OnClick', 'LeftButton'); Tick(0.02)")
check("retour en construction : liaisons temporaires reposées", B.BINDS["BUTTON3"] == "WOWLHEIM_REMOVE" and B.BINDS["MOUSEWHEELDOWN"] == "WOWLHEIM_ROTATE_LEFT")

# rangement du marteau, sortie du monde, /wl reset, option Q / E
bc.execute('EQUIPPED = nil; Fire("UNIT_INVENTORY_CHANGED", "player")')
check("marteau rangé : liaisons d'origine rétablies", B.BINDS["BUTTON3"] == "MOVEANDSTEER" and B.BINDS["MOUSEWHEELUP"] == "CAMERAZOOMIN"
      and B.BINDS["MOUSEWHEELDOWN"] == "CAMERAZOOMOUT")
bc.execute('Tick(0.5)')
check("marteau rangé : la molette zoome de nouveau (rien de reposé)", B.BINDS["MOUSEWHEELUP"] == "CAMERAZOOMIN")
bc.execute('EQUIPPED = "|Hitem:9201100:0:0:0|h[Marteau]|h"; Fire("UNIT_INVENTORY_CHANGED", "player")')
check("marteau rééquipé : liaisons temporaires reposées", B.BINDS["BUTTON3"] == "WOWLHEIM_REMOVE")
bc.execute('BINDS["MOUSEWHEELUP"] = "MACRO_ZOOM"; EQUIPPED = nil; Fire("UNIT_INVENTORY_CHANGED", "player")')
check("touche reliée par le joueur pendant la construction : non écrasée au rangement", B.BINDS["MOUSEWHEELUP"] == "MACRO_ZOOM"
      and B.BINDS["BUTTON3"] == "MOVEANDSTEER")
bc.execute('BINDS["MOUSEWHEELUP"] = "CAMERAZOOMIN"; EQUIPPED = "|Hitem:9201100:0:0:0|h[Marteau]|h"; Fire("UNIT_INVENTORY_CHANGED", "player")')
bc.execute('Fire("PLAYER_LEAVING_WORLD"); Tick(0.5)')
check("sortie du monde (déconnexion, /reload) : liaisons d'origine, rien de reposé avant le retour", B.BINDS["BUTTON3"] == "MOVEANDSTEER"
      and B.BINDS["MOUSEWHEELDOWN"] == "CAMERAZOOMOUT" and len(list(B.WowlheimDB.tempBinds.keys())) == 0)
bc.execute('PRELOADED = {}; Fire("PLAYER_ENTERING_WORLD"); Tick(0.02)')
check("retour dans le monde marteau en main : liaisons temporaires reposées", B.BINDS["BUTTON3"] == "WOWLHEIM_REMOVE")
bc.execute('Tick(0.02); Tick(0.02); Tick(0.02)')
check("retour dans le monde : modèles préchargés de nouveau (la DLL les libère au changement de carte)", len(list(B.PRELOADED.values())) == 23)
bc.execute('SlashCmdList["WOWLHEIM"]("qe on"); Tick(0.02)')
check("/wl qe on : Q / E tournent la pièce", B.BINDS["Q"] == "WOWLHEIM_ROTATE_LEFT" and B.BINDS["E"] == "WOWLHEIM_ROTATE_RIGHT" and B.WowlheimDB.qe == 1)
rot0 = BW.state.rot
press("E")
check("touche E (option) : rotation à droite", BW.state.rot == (rot0 + 1) % 16, str((rot0, BW.state.rot)))
bc.execute('SlashCmdList["WOWLHEIM"]("qe off"); Tick(0.02)')
check("/wl qe off : pas latéraux rétablis", B.BINDS["Q"] == "STRAFELEFT" and B.BINDS["E"] == "STRAFERIGHT" and B.BINDS["BUTTON3"] == "WOWLHEIM_REMOVE")
check("aucun SaveBindings pendant toute la construction", B.BIND_SAVES == 1)

# /reload ou plantage : liaisons temporaires encore actives au chargement => rétablies d'après WowlheimDB.tempBinds
bc2 = new_ui('''BINDS.BUTTON3 = "WOWLHEIM_REMOVE"; BINDS.MOUSEWHEELUP = "WOWLHEIM_ROTATE_RIGHT"; BINDS.MOUSEWHEELDOWN = "WOWLHEIM_ROTATE_LEFT"
EQUIPPED = nil''')
B2 = bc2.globals()
bc2.execute('WowlheimDB = { bindingsDone = 2, tempBinds = { BUTTON3 = "MACRO_X", MOUSEWHEELUP = "CAMERAZOOMIN" } }; Fire("VARIABLES_LOADED"); Fire("PLAYER_ENTERING_WORLD"); Tick(0.1)')
check("/reload : liaisons mémorisées rétablies, liaison temporaire orpheline remise à l'origine", B2.BINDS["BUTTON3"] == "MACRO_X"
      and B2.BINDS["MOUSEWHEELUP"] == "CAMERAZOOMIN" and B2.BINDS["MOUSEWHEELDOWN"] == "CAMERAZOOMOUT" and len(list(B2.WowlheimDB.tempBinds.keys())) == 0
      and B2.BIND_SAVES == 0, str(dict(B2.BINDS)))
bc2.execute('EQUIPPED = "|Hitem:9201100:0:0:0|h[Marteau]|h"; Fire("UNIT_INVENTORY_CHANGED", "player")')
check("/reload puis marteau : ancienne liaison (macro du joueur) mémorisée", B2.WowlheimDB.tempBinds["BUTTON3"] == "MACRO_X"
      and B2.BINDS["BUTTON3"] == "WOWLHEIM_REMOVE")
# --- piece visee : surbrillance (WearNTear.Highlight) et info-bulle (docs/BUILD_CONTROLS.md section 9) -----------------
def near(a, b):
    return all(abs(x - y) < 1e-6 for x, y in zip(a, b))
check("couleur de surbrillance, support inconnu : bleu clair Valheim", near(core.HighlightColor(None), (0.6, 0.8, 1.0)))
check("couleur de surbrillance, support complet (-1) : bleu clair", near(core.HighlightColor(-1), (0.6, 0.8, 1.0)))
check("couleur de surbrillance, support 1 : vert HSV(1/3, 0.5, 0.9)", near(core.HighlightColor(1), (0.45, 0.9, 0.45)), str(core.HighlightColor(1)))
check("couleur de surbrillance, support 0 : rouge HSV(0, 1, 1.2)", near(core.HighlightColor(0), (1.2, 0, 0)), str(core.HighlightColor(0)))
check("couleur de surbrillance, support 0.5 : jaune HSV(1/6, 0.75, 1.05)", near(core.HighlightColor(0.5), (1.05, 1.05, 0.2625)), str(core.HighlightColor(0.5)))
name2 = core.PieceName(data.pieces, 2)
check("info-bulle : nom et action en mode Démolir", core.HoverTip(lua.eval('{ mode = "remove" }'), 9110002, data.pieces) == (name2, "Clic droit : démolir"))
check("info-bulle : action en mode Réparer", core.HoverTip(lua.eval('{ mode = "repair" }'), 9110002, data.pieces)[1] == "Clic droit : réparer")
check("info-bulle : rien hors pièce Wowlheim", core.HoverTip(lua.eval('{ mode = "remove" }'), 50000, data.pieces) is None)
hv = new_ui('HL = {}; function WowlheimHighlightObject(g, r, gg, b, glow) table.insert(HL, { g or "clear", r, gg, b, glow }); if g then return 1 end end; '
            'function GetCursorPosition() return 400, 300 end')
H = hv.globals()
HW = H.Wowlheim
hv.execute('WowlheimDB = {}; Fire("VARIABLES_LOADED"); Fire("PLAYER_ENTERING_WORLD"); Wowlheim.state.mode = "remove"; '
           'MOUSEOVER = { "F1108B0172000123", 9110002 }; HL = {}; Tick(0.02)')
last = list(H.HL.values())[-1] if len(H.HL) else None
check("Démolir : pièce sous la souris en surbrillance (bleu clair, lueur 0.4)", last is not None and last[1] == "F1108B0172000123"
      and near((last[2], last[3], last[4], last[5]), (0.6, 0.8, 1.0, 0.4)), str(last and list(last.values())))
tip = H.WowlheimHoverTip
check("Démolir : info-bulle près du curseur (nom de la pièce, clic droit : démolir)", tip is not None and tip.shown
      and H.WowlheimHoverTipName.text == name2 and H.WowlheimHoverTipAction.text == "Clic droit : démolir"
      and tip.point[3] == "BOTTOMLEFT" and tip.point[4] == 400 + 18 and tip.point[5] == 300 - 18, str(tip and tip.point and list(tip.point.values())))
hv.execute('Tick(0.02)')
check("surbrillance réappliquée à chaque image", len(H.HL) == 2 and H.HL[2][1] == "F1108B0172000123")
hv.execute('MOUSEOVER = { "F1108B0172000124", 9110002 }; HL = {}; Tick(0.02)')
check("autre pièce : l'ancienne surbrillance est retirée avant la nouvelle", len(H.HL) == 2 and H.HL[1][1] == "clear" and H.HL[2][1] == "F1108B0172000124")
hv.execute('MOUSEOVER = { "F110000C3500002A", 50000 }; HL = {}; Tick(0.02)')
check("objet non Wowlheim : surbrillance retirée, info-bulle masquée", len(H.HL) == 1 and H.HL[1][1] == "clear" and not tip.shown)
hv.execute('HL = {}; Tick(0.02)')
check("rien sous la souris : aucun appel inutile à la DLL", len(H.HL) == 0)
hv.execute('Wowlheim.state.mode = "repair"; MOUSEOVER = { "F1108B0172000123", 9110002 }; Tick(0.02)')
check("Réparer : info-bulle « clic droit : réparer »", tip.shown and H.WowlheimHoverTipAction.text == "Clic droit : réparer")
hv.execute('Wowlheim.state.mode = "build"; HL = {}; Tick(0.02)')
check("Construction : surbrillance + info-bulle (nom) sans ligne d'action", len(H.HL) == 1 and H.HL[1][1] == "F1108B0172000123"
      and tip.shown and not H.WowlheimHoverTipAction.text)
pis = [s for s in H.SENT.values() if s.startswith(".build api pieceinfo")]
check("pièce visée : pieceinfo silencieux envoyé (au plus un toutes les 2 s par pièce)", pis and pis[-1] == ".build api pieceinfo F1108B0172000123"
      and len([s for s in pis if s.endswith("F1108B0172000123")]) <= 3, str(pis))
hv.execute('ChatSystem("[WL]PI|F1108B0172000123|100|400|0.000|Mur en bois"); ChatSystem("[WL]D|pieceinfo|1"); HL = {}; Tick(0.02)')
check("PI| reçu : surbrillance rouge (support 0, WearNTear.Highlight)", len(H.HL) == 1 and near((H.HL[1][2], H.HL[1][3], H.HL[1][4]), (1.2, 0, 0)),
      str(H.HL[1] and list(H.HL[1].values())))
check("PI| reçu : info-bulle « Santé : 25 % » et « Support : critique »", H.WowlheimHoverTipHealth.text == "Santé : 25 %"
      and H.WowlheimHoverTipSupport.text == "Support : critique" and tip.shown, str((H.WowlheimHoverTipHealth.text, H.WowlheimHoverTipSupport.text)))
check("PI| : lignes [WL] masquées du chat, rien au centre", not any("[WL]" in (t or "") for t in H.CHAT_SHOWN.values()))
hv.execute('EQUIPPED = nil; HL = {}; Tick(0.02); Tick(0.02)')
check("marteau rangé : surbrillance retirée une seule fois", len(H.HL) == 1 and H.HL[1][1] == "clear")
hv.execute('EQUIPPED = "|Hitem:9201100:0:0:0|h[Marteau]|h"; WowlheimHighlightObject = nil; Wowlheim.state.mode = "remove"; Tick(0.02)')
check("sans WowlheimHighlightObject (ancienne DLL) : info-bulle seule, sans erreur", tip.shown)

bc3 = new_ui('WowlheimPreloadModel = nil; WowlheimSetInstantFade = nil; WowlheimGetMouseoverObject = nil')
bc3.execute('Fire("VARIABLES_LOADED"); Fire("PLAYER_ENTERING_WORLD"); Tick(0.1)')
check("sans DLL : pas de demande de modèles, liaisons temporaires quand même", ".build api models" not in list(bc3.globals().SENT.values())
      and bc3.globals().BINDS["BUTTON3"] == "WOWLHEIM_REMOVE")

# --- défauts constatés en jeu (personnage neuf, tools/client/gui/shots/p2) ----------------------------------------
# 1. noms des découvertes (KR| ne donne que des identifiants ; panneau de fabrication jamais ouvert)
check("WowlheimData.recipes : noms des recettes (99 = Marteau, 100 = Hache en pierre, sans station)",
      data.recipes[99].name == "Marteau" and data.recipes[99].out == 9201100 and data.recipes[99].station == ""
      and data.recipes[100].name == "Hache en pierre" and data.recipes[202].name == "Bronze x5")
ka = core.NewKnown()
ka.newRecipes = lua.eval("{ 99, n = 1 }")
ka.newPieces = lua.eval("{ 6, n = 1 }")
a = core.KnownAnnouncements(ka, pieces, data.recipes, None, data["items"])
check("annonce : « Nouvelle recette : Marteau » (sans le panneau de fabrication)", a.recipe == "Nouvelle recette : Marteau", str(a.recipe))
check("annonce : « Nouvelle pièce de construction : Table de fabrication »", a.piece == "Nouvelle pièce de construction : Table de fabrication", str(a.piece))
ka.newRecipes = lua.eval("{ 99, 100, n = 2 }")
check("annonce groupée : premier nom (+1)", core.KnownAnnouncements(ka, pieces, data.recipes, None, data["items"]).recipe == "Nouvelle recette : Marteau (+1)")
ka.newRecipes = lua.eval("{ 777, n = 1 }")
check("recette absente des données : nom des lignes C| reçues", core.KnownAnnouncements(ka, pieces, lua.eval("{}"),
      lua.eval("{ { id = 777, name = 'Truc' } }"), data["items"]).recipe == "Nouvelle recette : Truc")
check("KN|item matériau : « Nouveau matériau : Bois »", core.LearnedText(core.ParseLine("[WL]KN|item|9200001"), data["items"], data.stations) == "Nouveau matériau : Bois")
check("KN|item outil : « Nouvel objet : Marteau »", core.LearnedText(core.ParseLine("[WL]KN|item|9201100"), data["items"], data.stations) == "Nouvel objet : Marteau")
check("KN|station : « Nouvel établi : Table de fabrication » / « Établi mis à niveau : ... niveau 2 »",
      core.LearnedText(core.ParseLine("[WL]KN|station|workbench|1"), data["items"], data.stations) == "Nouvel établi : Table de fabrication"
      and core.LearnedText(core.ParseLine("[WL]KN|station|forge|2"), data["items"], data.stations) == "Établi mis à niveau : Forge niveau 2")
# 2. onglet à l'ouverture
kc = core.NewKnown()
for ln in ("[WL]K|", "[WL]KS|", "[WL]KP|6", "[WL]KR|99", "[WL]D|known|1"):
    core.KnownOnMessage(kc, core.ParseLine(ln))
empty_counts = lua.eval("{}")
check("onglet mémorisé vide (Construction) => premier onglet avec une pièce connue (Fabrication : établi)",
      core.PickCategory(pieces, 3, True, 5, kc, empty_counts, None) == 2)
check("premier usage => premier onglet avec une pièce connue (Divers n'a que Réparer / Démolir)",
      core.PickCategory(pieces, 3, None, 5, kc, empty_counts, None) == 2)
check("onglet mémorisé non vide : conservé", core.PickCategory(pieces, 3, True, 5, None, empty_counts, None) == 3)
check("premier usage, tout connu : premier onglet (Divers)", core.PickCategory(pieces, 3, None, 5, None, empty_counts, None) == 1)
# 4. dédoublonnage et attribution des lignes
dd = core.NewDedup()
check("même erreur à moins d'1 s : une seule fois, même avec un autre texte entre les deux",
      core.DedupPass(dd, "A", 10) and core.DedupPass(dd, "B", 10.1) and not core.DedupPass(dd, "A", 10.5) and core.DedupPass(dd, "A", 11.2))
chx = core.NewChannel()
core.ChannelPush(chx, ".build api repairable 5", True, 0)
core.ChannelPush(chx, ".build api craft 99", None, 0)
e = core.ChannelRoute(chx, core.ParseLine("[WL]E|Station exposée (couverture 0 %, il faut un toit et au moins 70 %)."), 0)
check("E|Station exposée pendant repairable (silencieux) : rattachée à repairable, pas à la fabrication", e is not None and e.cmd == "repairable" and e.silent)
chs = core.NewChannel()
core.ChannelPush(chs, ".build api select 6 0", True, 0)
e1 = core.ChannelRoute(chs, core.ParseLine("[WL]M|Pièce choisie : Table de fabrication (rotation 0°)."), 0)
e2 = core.ChannelRoute(chs, core.ParseLine("[WL]M|Table de fabrication choisi (rotation 0°)."), 0)
e3 = core.ChannelRoute(chs, core.ParseLine("[WL]E|Vous êtes trop fatigué."), 0)
check("select silencieux : son accusé lui appartient (nouveau et ancien texte), pas les autres erreurs",
      e1 is not None and e1.cmd == "select" and e2 is not None and e2.cmd == "select" and e3 is None)
check("ressources manquantes : « Manque : Bois 3/10 »", core.MissingText(lua.eval("{ {9200001, 10} }"), lua.eval("{ [9200001] = 3 }"), lambda i: "Bois") == "Manque : Bois 3/10"
      and core.MissingText(lua.eval("{ {9200001, 10} }"), lua.eval("{ [9200001] = 10 }"), None) is None)

# scénario complet (personnage neuf) dans l'API simulée
nu = new_ui()
N = nu.globals()
NW = N.Wowlheim
def nsent():
    return list(N.SENT.values())
def nerr():
    return list(N.ERRORS.values())
def nfeed(lines):
    nu.execute(";".join('ChatSystem("%s")' % l for l in lines))
# onglet mémorisé « Construction », mais aucune station connue : Construction est vide pour ce personnage
nu.execute('BAGS = { [0] = { [1] = {"|Hitem:9200001:0:0:0|h[Bois]|h", 30} } }')
nu.execute('WowlheimDB = { cat = 3 }; Fire("VARIABLES_LOADED"); Fire("PLAYER_ENTERING_WORLD"); Tick(0.1)')
check("avant la réponse known (tout affiché) : onglet mémorisé conservé", NW.cat == 3)
nfeed(["[WL]K|item:9200001", "[WL]KS|", "[WL]KP|6", "[WL]KR|99", "[WL]D|known|1"])
near0 = NW.NearStations()
want = next(c for c in range(1, 6) if N.WowlheimCore.CategoryPieceCount(N.WowlheimData.pieces, c, NW.known, NW.counts, near0) > 0)
check("personnage neuf : onglet vide quitté pour le premier onglet avec une pièce connue (grille non vide)",
      N.WowlheimCore.CategoryPieceCount(N.WowlheimData.pieces, 3, NW.known, NW.counts, near0) == 0 and NW.cat == want and want != 3
      and N.WowlheimFrame.shown and not N.WowlheimGridEmpty.shown and N.WowlheimDB.cat == 3, "%s -> %s" % (want, NW.cat))
nu.execute("Wowlheim.SetCategory(2)")
check("clic sur l'onglet Fabrication : établi affiché, onglet mémorisé", N.WowlheimIcon1.entry.id == 6 and N.WowlheimDB.cat == 2)
nu.execute("Wowlheim.Hide(); Wowlheim.Show()")
check("réouverture : onglet mémorisé (non vide) conservé", NW.cat == 2)
nfeed(["[WL]K|item:9200001", "[WL]KS|", "[WL]KP|6", "[WL]KR|99,100", "[WL]D|known|1"])
check("KR| nouvelle recette, panneau de fabrication fermé : « Nouvelle recette : Hache en pierre » au centre",
      "Nouvelle recette : Hache en pierre" in nerr(), str(nerr()))
n_e = len(nerr())
nu.execute("RunScript(WowlheimIcon1, 'OnClick', 'LeftButton')")
check("choix d'une pièce : select silencieux", any(NW.channel[i].cmd == "select" and NW.channel[i].silent for i in range(1, NW.channel.n + 1)))
nfeed(["[WL]M|Pièce choisie : Table de fabrication (rotation 0°).", "[WL]D|select|1"])
check("accusé du serveur non affiché (le bandeau suffit)", len(nerr()) == n_e and N.WowlheimPlaceBanner.shown
      and N.WowlheimPlaceBannerText.text == "Table de fabrication  -  Rotation : 0°", str(nerr()[n_e:]) + str(N.WowlheimPlaceBannerText.text))
# 3. pose réussie, plus assez de bois pour une 2e : pose en chaîne, pas de menu, bandeau « Manque »
used0 = N.USED
nu.execute('BAGS[0][1][2] = 4; Fire("BAG_UPDATE", 0); TARGETING = nil')
nfeed(["[WL]M|Pièce Table de fabrication posée (id 9500001)", "[WL]D|place|1"])
nu.execute("Tick(0.5)")
check("après la pose, ressources insuffisantes : le menu ne se rouvre PAS, ciblage relancé (même pièce)",
      not N.WowlheimFrame.shown and N.USED == used0 + 1 and N.TARGETING == 1 and NW.state.continuous and NW.state.piece == 6)
check("bandeau : ce qui manque en rouge", "Manque : Bois 4/10" in (N.WowlheimPlaceBannerText.text or ""), str(N.WowlheimPlaceBannerText.text))
check("aucun message « Ressources insuffisantes pour reposer »", not any("reposer" in x for x in nerr()))
# refus du serveur (pose sans ressources) : une fois, la pose continue
n_e = len(nerr())
nu.execute('TARGETING = nil')
nfeed(["[WL]M|Ressources manquantes : 6 Bois.", "[WL]D|place|0"])
nfeed(["[WL]E|Ressources manquantes : 6 Bois."])
nu.execute("Tick(0.5)")
check("refus : affiché une seule fois (texte identique à moins d'1 s ignoré), ciblage relancé, menu fermé",
      nerr()[n_e:].count("Ressources manquantes : 6 Bois.") == 1 and N.TARGETING == 1 and not N.WowlheimFrame.shown, str(nerr()[n_e:]))
# 4 / 5. établi exposé : fabrication à la main (Marteau) ; le refus de réparation silencieux n'est ni affiché ni attribué
nu.execute('ToggleGameMenu(); BAGS[0][1][2] = 30; Fire("BAG_UPDATE", 0); Tick(7)')
nu.execute('SlashCmdList["WOWLHEIMCRAFT"]("")')
n_e = len(nerr())
nfeed(["[WL]E|Station exposée (couverture 0 %, il faut un toit et au moins 70 %).", "[WL]D|repairable|0"])
nfeed(["[WL]S|9500001|0|0|1|workbench", "[WL]D|station|1",
       "[WL]C|99|Marteau||9201100:1|9200001:3|1", "[WL]C|101|Hache en silex|workbench|9201011:1|9200001:5|1", "[WL]D|recipes|1"])
check("établi exposé à l'ouverture : aucun message au centre (l'en-tête l'indique)", len(nerr()) == n_e and "exposée" in (N.WowlheimCraftStationLevel.text or ""),
      str(nerr()[n_e:]))
nu.execute("Wowlheim.Craft.Select(99); Wowlheim.Craft.Update()")
check("Marteau (sans station) réalisable devant un établi exposé", N.WowlheimCraftButton.enabled)
nu.execute("Tick(5.1)")      # rafraîchissement : station + repairable en attente
check("rafraîchissement : repairable en attente pendant la fabrication", any(NW.channel[i].cmd == "repairable" for i in range(1, NW.channel.n + 1)))
nu.execute("RunScript(WowlheimCraftButton, 'OnClick', 'LeftButton')")
check("Fabriquer : craft 99 envoyé", nsent()[-1] == ".build api craft 99", str(nsent()[-3:]))
nfeed(["[WL]S|9500001|0|0|1|workbench", "[WL]D|station|1",
       "[WL]E|Station exposée (couverture 0 %, il faut un toit et au moins 70 %).", "[WL]D|repairable|0",
       "[WL]M|Fabriqué : 1 x Marteau.", "[WL]D|craft|1"])
check("refus de réparation reçu pendant la fabrication : pas attribué à la fabrication, rien au centre ; « Fabriqué » affiché",
      len(nerr()) == n_e and "Fabriqué" in (N.WowlheimCraftMsg.text or "") and "exposée" not in (N.WowlheimCraftMsg.text or ""),
      str(nerr()[n_e:]) + " / " + str(N.WowlheimCraftMsg.text))

# --- fantôme de pose : orientation (rotation à la molette) et couleur (canplace) --------------------
import math
m = core.ParseLine("[WL]CP|1")
check("ligne CP|1", m["type"] == "CP" and m["ok"] and m["why"] == "")
m = core.ParseLine("[WL]CP|0|Ressources manquantes : 2 Pierre.")
check("ligne CP|0|raison", m["type"] == "CP" and not m["ok"] and m["why"] == "Ressources manquantes : 2 Pierre.", m["why"])
check("commande canplace", core.CanPlaceCommand(-1234.5, 87.126, 12, 3) == ".build api canplace -1234.50 87.13 12.00 3",
      core.CanPlaceCommand(-1234.5, 87.126, 12, 3))
check("décalage d'orientation = rot × 22,5° (même formule que BuildingMgr::PlaceOrientation)",
      abs(core.PlaceFacingOffset(0)) < 1e-9 and abs(core.PlaceFacingOffset(3) - 3 * math.pi / 8) < 1e-9 and abs(core.PlaceFacingOffset(15) - 15 * math.pi / 8) < 1e-9)
gc = core.NewGhostCheck()
st = lua.table_from({"mode": "build", "piece": 4, "rot": 0, "continuous": 1})
P = lambda x, y, z: lua.table_from({"x": x, "y": y, "z": z})
c1 = core.GhostCheckCommand(gc, st, P(10, 20, 5), 100, False)
check("canplace : première interrogation", c1 == ".build api canplace 10.00 20.00 5.00 0", str(c1))
check("canplace : pas deux à moins de 0,25 s", core.GhostCheckCommand(gc, st, P(15, 20, 5), 100.2, False) is None)
check("canplace : une seule en attente", core.GhostCheckCommand(gc, st, P(15, 20, 5), 100.3, True) is None)
check("canplace : immobile, pas de nouvelle interrogation avant 1 s", core.GhostCheckCommand(gc, st, P(10.05, 20, 5), 100.5, False) is None)
check("canplace : immobile, rafraîchie après 1 s", core.GhostCheckCommand(gc, st, P(10, 20, 5), 101.0, False) is not None)
c2 = core.GhostCheckCommand(gc, st, P(12, 20, 5), 101.3, False)
check("canplace : point visé déplacé -> nouvelle interrogation", c2 == ".build api canplace 12.00 20.00 5.00 0", str(c2))
st.rot = 2
check("canplace : rotation changée -> nouvelle interrogation avec rot", core.GhostCheckCommand(gc, st, P(12, 20, 5), 101.6, False) == ".build api canplace 12.00 20.00 5.00 2")
check("canplace : hors mode construction, rien", core.GhostCheckCommand(gc, lua.table_from({"mode": "remove", "piece": 4, "rot": 0}), P(1, 1, 1), 200, False) is None)
entry = lua.table_from({"cmd": "canplace"})
check("CP| hors commande canplace ignoré", core.GhostCheckOnMessage(gc, core.ParseLine("[WL]CP|0|x"), None, 101.7) is None and gc.ok is None)
core.GhostCheckOnMessage(gc, core.ParseLine("[WL]CP|0|Trop loin."), entry, 101.7)
costs_ok = lua.table_from({1: lua.table_from({1: 9200001, 2: 2})})
costs_ko = lua.table_from({1: lua.table_from({1: 9200002, 2: 5})})
counts = lua.table_from({9200001: 30, 9200002: 2})
def gv(**kw):
    o = {"st": st, "costs": costs_ok, "counts": counts, "gc": gc, "now": 101.8, "range": 0}
    o.update(kw)
    return core.GhostValid(lua.table_from({k: v for k, v in o.items() if v is not None}))
v, why = gv()
check("verdict récent du serveur (refus) : fantôme rouge", v is False and why == "Trop loin.", str((v, why)))
core.GhostCheckOnMessage(gc, core.ParseLine("[WL]CP|1"), entry, 101.8)
check("verdict récent du serveur (accord) : fait foi même si les sacs manquent (sans coût, accroche)", gv(costs=costs_ko)[0] is True)
check("hors portée du sort (DLL) : rouge sans attendre le serveur", gv(range=1)[0] is False)
st.rot = 3
check("verdict pour une autre rotation : contrôles locaux (ressources manquantes -> rouge)", gv(costs=costs_ko)[0] is False)
check("verdict périmé (> 1,5 s) : contrôles locaux (ressources suffisantes -> normal)", gv(now=104)[0] is True)
rs = core.NewRings()
for ln in ["[WL]ST|9500001|workbench|0|0|0|20.0|0|0", "[WL]D|stations|1"]:
    core.RingsOnMessage(rs, core.ParseLine(ln))
v, why = gv(now=104, station="workbench", rings=rs)
check("hors de la zone de la table de fabrication : rouge", v is False and "table de fabrication" in why, str(why))
check("pièce sans station, stations inconnues : normal", gv(now=104, station="")[0] is True)
gc2 = core.NewGhostCheck()
core.GhostCheckOnMessage(gc2, core.ParseLine("[WL]E|commande inconnue"), entry, 1)
check("ancien serveur (commande inconnue) : plus d'interrogation", gc2.unsupported and core.GhostCheckCommand(gc2, st, P(1, 1, 1), 50, False) is None)

GHOST_MOCK = r"""
FACING = {}; COLORS = {}; GHOSTPOS = { -100, 200, 30 }; GHOSTRANGE = 0
function WowlheimSetPlaceObject(id) end
function WowlheimSetPlaceFacing(f, rel) table.insert(FACING, { f = f, rel = rel }) end
function WowlheimGhostGetPos() return GHOSTPOS[1], GHOSTPOS[2], GHOSTPOS[3], 0, 1, GHOSTRANGE, 0 end
function WowlheimGhostSetColor(r, g, b, a, glow, target) table.insert(COLORS, { r, g, b, a, glow, target }) end
"""
gu = new_ui(GHOST_MOCK)
GG = gu.globals()
GW = GG.Wowlheim
def gsent():
    return list(GG.SENT.values())
gu.execute('WowlheimDB = { cat = 3 }; Fire("VARIABLES_LOADED"); Fire("PLAYER_ENTERING_WORLD"); Tick(0.1)')
gu.execute("RunScript(WowlheimIcon1, 'OnClick', 'LeftButton')")
gpid = GG.WowlheimIcon1.entry.id
fac = [(f.f, f.rel) for f in GG.FACING.values()]
check("ciblage : fantôme natif orienté joueur + rot × 22,5° (WowlheimSetPlaceFacing(0, 1))", fac and fac[-1] == (0, 1), str(fac))
gu.execute("Wowlheim.Rotate(1)")
f = list(GG.FACING.values())[-1]
check("molette : le fantôme tourne de 22,5° tout de suite (décalage relatif)", abs(f.f - math.pi / 8) < 1e-9 and f.rel == 1, str((f.f, f.rel)))
gu.execute("Wowlheim.Rotate(-2)")
f = list(GG.FACING.values())[-1]
check("molette arrière depuis 22,5° : 337,5° (rot 15, comme le serveur)", abs(f.f - 15 * math.pi / 8) < 1e-9, str(f.f))
gu.execute("Tick(0.02)")
cp = [s for s in gsent() if s.startswith(".build api canplace")]
check("ciblage : canplace envoyé avec le point visé et la rotation", cp and cp[-1] == ".build api canplace -100.00 200.00 30.00 15", str(cp))
check("canplace silencieux, en attente dans le canal", any(GW.channel[i].cmd == "canplace" and GW.channel[i].silent for i in range(1, GW.channel.n + 1)))
gu.execute('ChatSystem("[WL]CP|0|Pose refusée : construction interdite en ville."); ChatSystem("[WL]D|canplace|1"); Tick(0.02)')
col = list(GG.COLORS.values())[-1]
check("refus du serveur : fantôme natif teinté en rouge (cible 1)", col[1] == 1 and col[2] < 0.5 and col[6] == 1, str(list(col.values())))
n_err = len(list(GG.ERRORS.values()))
check("refus de canplace : rien affiché (ni chat ni centre)", len(GG.CHAT_SHOWN) == 0 and not any("interdite" in e for e in GG.ERRORS.values()))
gu.execute("GHOSTPOS = { -95, 200, 30 }; Tick(0.1)")
check("au plus une interrogation toutes les 0,25 s", len([s for s in gsent() if s.startswith(".build api canplace")]) == 1)
gu.execute("Tick(0.2)")
cp = [s for s in gsent() if s.startswith(".build api canplace")]
check("point visé déplacé : nouvelle interrogation", len(cp) == 2 and cp[-1].startswith(".build api canplace -95.00"), str(cp))
gu.execute('ChatSystem("[WL]CP|1"); ChatSystem("[WL]D|canplace|1"); Tick(0.02)')
col = list(GG.COLORS.values())[-1]
check("accord du serveur : fantôme normal", list(col.values()) == [1, 1, 1, 1, 0, 1], str(list(col.values())))
nc = len(list(GG.COLORS.values()))
gu.execute("Tick(0.02); Tick(0.02)")
check("couleur inchangée : pas de nouvel appel à la DLL", len(list(GG.COLORS.values())) == nc)
gu.execute("GHOSTRANGE = 1; Tick(0.02)")
check("hors portée du sort : rouge immédiat", list(GG.COLORS.values())[-1][2] < 0.5)
gu.execute("GHOSTRANGE = 0; TARGETING = nil; Tick(0.02)")
col = list(GG.COLORS.values())[-1]
check("fin du ciblage : teinte du fantôme natif retirée (cible -1)", col[6] == -1, str(list(col.values())))
ncp = len([s for s in gsent() if s.startswith(".build api canplace")])
gu.execute("Tick(2)")
check("hors ciblage : plus de canplace", len([s for s in gsent() if s.startswith(".build api canplace")]) == ncp)

# --- fantôme accroché (canplace -> position après Snap), état de la pièce visée (pieceinfo), son de démolition ------------
m = core.ParseLine("[WL]CP|1|10.50|-3.25|42.00|1.571|1")
check("CP|1|x|y|z|o|1 : position accrochée", m["ok"] and m["snapped"] and m["x"] == 10.5 and m["y"] == -3.25 and m["z"] == 42 and abs(m["o"] - 1.571) < 1e-9 and m["why"] == "")
m = core.ParseLine("[WL]CP|0|1.00|2.00|3.00|0.000|0|Ressources manquantes : 2 Pierre.")
check("CP|0|x|y|z|o|0|raison : raison et position", not m["ok"] and not m["snapped"] and m["x"] == 1 and m["why"] == "Ressources manquantes : 2 Pierre.", m["why"])
m = core.ParseLine("[WL]CP|0|Ressources manquantes : 2 Pierre.")
check("ancien serveur CP|0|raison : sans position", not m["ok"] and m["x"] is None and m["why"] == "Ressources manquantes : 2 Pierre.")
gs = core.NewGhostCheck(); sts = lua.table_from({"mode": "build", "piece": 2, "rot": 0})
core.GhostCheckCommand(gs, sts, P(10, 20, 5), 200, False)
core.GhostCheckOnMessage(gs, core.ParseLine("[WL]CP|1|10.40|19.00|5.00|0.000|1"), entry, 200.1)
sp = core.GhostSnapPos(gs, sts, P(10.1, 20, 5), 200.2)
check("fantôme accroché : position du serveur tant que la souris reste près du point interrogé", sp is not None and sp.x == 10.4 and sp.y == 19)
check("souris éloignée de plus de 0,75 m : fantôme à la souris", core.GhostSnapPos(gs, sts, P(11, 20, 5), 200.2) is None)
check("verdict périmé : fantôme à la souris", core.GhostSnapPos(gs, sts, P(10, 20, 5), 210) is None)
core.GhostCheckCommand(gs, sts, P(30, 20, 5), 201, False)
core.GhostCheckOnMessage(gs, core.ParseLine("[WL]CP|1|30.00|20.00|5.00|0.000|0"), entry, 201.1)
check("pas d'accroche (a = 0) : fantôme à la souris", core.GhostSnapPos(gs, sts, P(30, 20, 5), 201.2) is None)
m = core.ParseLine("[WL]PI|f1108b0172000123|300|400|-1.000|Mur en bois")
check("PI| : guid (majuscules), pv, pv max, support, nom", m["guid"] == "F1108B0172000123" and m["hp"] == 300 and m["hpMax"] == 400
      and m["support"] == -1 and m["name"] == "Mur en bois")
pinfo = core.NewPieceInfo()
check("pieceinfo : première interrogation", core.PieceInfoCommand(pinfo, "f1108b0172000123", 10, False) == ".build api pieceinfo F1108B0172000123")
check("pieceinfo : pas deux fois la même pièce avant 2 s", core.PieceInfoCommand(pinfo, "F1108B0172000123", 11, False) is None)
check("pieceinfo : une seule en attente", core.PieceInfoCommand(pinfo, "F1108B0172000124", 11, True) is None)
check("pieceinfo : autre pièce -> interrogation", core.PieceInfoCommand(pinfo, "F1108B0172000124", 11, False) is not None)
pie = lua.table_from({"cmd": "pieceinfo"})
core.PieceInfoOnMessage(pinfo, core.ParseLine("[WL]PI|F1108B0172000124|300|400|0.500|Mur"), pie, 11.2)
inf = core.PieceInfoFor(pinfo, "f1108b0172000124", 12)
h, sup = core.PieceInfoLines(inf)
check("info-bulle : « Santé : 75 % », « Support : moyen » dans la couleur de la surbrillance (bornée à 1)",
      h.text == "Santé : 75 %" and sup.text == "Support : moyen" and sup.r == 1 and sup.g == 1 and abs(sup.b - 0.2625) < 1e-6, str((h.text, sup.text)))
check("état d'une autre pièce : inconnu", core.PieceInfoFor(pinfo, "F1108B0172000123", 12) is None)
check("état trop ancien (> 10 s) : oublié", core.PieceInfoFor(pinfo, "F1108B0172000124", 30) is None)
check("support complet (-1) : « Support : complet », bleu clair", core.PieceInfoLines(lua.table_from({"hp": 400, "hpMax": 400, "support": -1}))[1].text == "Support : complet")
core.PieceInfoOnMessage(pinfo, core.ParseLine("[WL]E|commande inconnue"), pie, 13)
check("ancien serveur : plus d'interrogation pieceinfo", core.PieceInfoCommand(pinfo, "F1108B0172000999", 50, False) is None)
wall = [p for p in data.pieces.values() if p.name == "Mur en bois"]
stone_p = [p for p in data.pieces.values() if p.costs and p.costs[1] and p.costs[1][1] == 9200002 and (not p.costs[2] or p.costs[2][2] < p.costs[1][2])]
check("son de démolition : bois (Mur en bois)", core.DestroySound(core.ParseLine("[WL]M|Démoli : Mur en bois."), data.pieces) == "Sound\\Doodad\\DeadmineDoor01Destroy.wav")
check("son de démolition : pierre pour une pièce surtout en pierre", stone_p and core.DestroySound(core.ParseLine("[WL]M|Démoli : " + stone_p[0].name + "."), data.pieces)
      == "Sound\\Doodad\\G_CaveinClosed.wav", stone_p and stone_p[0].name)
check("son de démolition : rien pour une autre ligne", core.DestroySound(core.ParseLine("[WL]M|Pièce Mur posée (id 1)"), data.pieces) is None)
l1, l2, okl = core.StationLines(lua.table_from({"station": "forge", "minLevel": 2, "curLevel": 1, "levelOk": False}), data.stations)
check("fiche de recette : « Station : Forge » / « Niveau 2 requis (actuel : 1) » en rouge", l1 == "Station : Forge" and l2 == "Niveau 2 requis (actuel : 1)" and not okl, str((l1, l2)))
check("fiche de recette : fabrication à la main", core.StationLines(lua.table_from({"station": "", "hand": True}), data.stations)[1] == "Fabrication à la main")

# fantôme accroché en jeu simulé : fantôme natif invisible, fantôme DLL (même modèle) au point accroché, tourné comme le natif
SNAP_MOCK = GHOST_MOCK + r"""
DLLG = { shown = nil, place = nil, rot = nil, color = nil, hides = 0 }
function WowlheimGhostShow(p) DLLG.shown = p; return 1 end
function WowlheimGhostPlace(x, y, z) if x then DLLG.place = { x, y, z } else DLLG.place = nil end end
function WowlheimGhostRotate(o) DLLG.rot = o end
function WowlheimGhostHide() DLLG.shown = nil; DLLG.place = nil; DLLG.hides = DLLG.hides + 1 end
function WowlheimGhostGetPos() return GHOSTPOS[1], GHOSTPOS[2], GHOSTPOS[3], 0, 1, GHOSTRANGE, 0.75 end
SOUNDS = {}; function PlaySoundFile(p) table.insert(SOUNDS, p) end
"""
su = new_ui(SNAP_MOCK)
SG = su.globals()
su.execute('WowlheimDB = { cat = 3 }; Fire("VARIABLES_LOADED"); Fire("PLAYER_ENTERING_WORLD"); Tick(0.1)')
su.execute("RunScript(WowlheimIcon1, 'OnClick', 'LeftButton'); Tick(0.02)")
spid = SG.WowlheimIcon1.entry.id
ssent = [s for s in SG.SENT.values()]
check("fantôme accroché : modèles demandés si inconnus (.build api models)", ".build api models" in ssent, str(ssent))
su.execute('ChatSystem("[WL]MD|%d:wood_wall"); ChatSystem("[WL]D|models|1")' % spid)
su.execute('ChatSystem("[WL]CP|1|-99.00|201.00|31.00|2.000|1"); ChatSystem("[WL]D|canplace|1"); Tick(0.02)')
check("accroche reçue : fantôme DLL au point accroché, modèle de la pièce, orientation du fantôme natif",
      SG.DLLG.shown == "World\\Wowlheim\\wood_wall.m2" and SG.DLLG.place and list(SG.DLLG.place.values()) == [-99, 201, 31] and SG.DLLG.rot == 0.75,
      str((SG.DLLG.shown, SG.DLLG.place and list(SG.DLLG.place.values()), SG.DLLG.rot)))
ncol = list(SG.COLORS.values())
check("accroche : fantôme natif rendu invisible (alpha 0, cible 1)", any(c[4] == 0 and c[6] == 1 for c in ncol), str([list(c.values()) for c in ncol]))
su.execute("GHOSTPOS = { -90, 200, 30 }; Tick(0.02)")
check("souris éloignée : fantôme DLL masqué, fantôme natif de nouveau visible", SG.DLLG.shown is None and SG.DLLG.hides >= 1
      and list(SG.COLORS.values())[-1][4] == 1, str(list(list(SG.COLORS.values())[-1].values())))
su.execute("TARGETING = nil; Tick(0.02)")
check("fin du ciblage : fantôme DLL masqué", SG.DLLG.shown is None)
su.execute('ChatSystem("[WL]M|Démoli : Mur en bois.")')
check("démolition : son de bois brisé joué (PlaySoundFile)", list(SG.SOUNDS.values()) == ["Sound\\Doodad\\DeadmineDoor01Destroy.wav"], str(list(SG.SOUNDS.values())))

# --- non-régression 2026-10-26 (captures p2/112-118) : pose en chaîne avec fantôme / canplace / survol actifs -------------
# pose -> relance du ciblage (même pièce, fantôme natif rappelé, canplace de nouveau) -> seconde pose -> relance ; un
# UseInventoryItem refusé par le client est retenté au lieu de laisser « bandeau sans fantôme » ; Échap dans cet état quitte
# la pose sans menu du jeu ; survol d'une pièce ignoré quand la souris est sur un cadre d'interface.
CHAIN_MOCK = SNAP_MOCK + r"""
REFUSE = 0
function UseInventoryItem(slot) USED = USED + 1; USED_SLOT = slot; if REFUSE > 0 then REFUSE = REFUSE - 1 else TARGETING = 1 end end
PLACEOBJ = {}; function WowlheimSetPlaceObject(id) table.insert(PLACEOBJ, id) end
HL = {}; function WowlheimHighlightObject(g) table.insert(HL, g or "off"); if g then return 1 end end
WorldFrame = CreateFrame("Frame", "WorldFrame"); FOCUS = WorldFrame; function GetMouseFocus() return FOCUS end
"""
cu = new_ui(CHAIN_MOCK)
CG = cu.globals(); CW = CG.Wowlheim
def csent():
    return list(CG.SENT.values())
def canplaces():
    return [s for s in csent() if s.startswith(".build api canplace")]
def pose(n):
    # clic gauche au sol : le client termine le ciblage et lance le sort ; le serveur répond M| + D|place|1 ; la pièce posée
    # est alors sous la souris (surbrillance / info-bulle / pieceinfo)
    cu.execute('TARGETING = nil; Tick(0.02); Spell("SPELLCAST_STOP")')
    cu.execute('ChatSystem("[WL]M|Pièce Plancher 2x2 posée (id %d) [sans coût]"); ChatSystem("[WL]D|place|1")' % (9000300 + n))
    cu.execute('MOUSEOVER = { "F1108B01F18955%02d", 9110001 }' % n)
cu.execute('WowlheimDB = { cat = 3 }; Fire("VARIABLES_LOADED"); Fire("PLAYER_ENTERING_WORLD"); Tick(0.1)')
cu.execute("RunScript(WowlheimIcon1, 'OnClick', 'LeftButton'); Tick(0.05)")
cpid = CG.WowlheimIcon1.entry.id
cu.execute('ChatSystem("[WL]CP|1|-100.00|200.00|30.00|0.000|0"); ChatSystem("[WL]D|canplace|1"); Tick(0.05)')
u0, n_cp = CG.USED, len(canplaces())
check("chaîne : 1er ciblage, canplace envoyé", u0 == 1 and CG.TARGETING == 1 and n_cp == 1, str((u0, n_cp)))
pose(1)
for _ in range(15):
    cu.execute("Tick(0.05)")
check("chaîne : après la 1re pose, ciblage relancé avec la même pièce (fantôme natif rappelé)", CG.USED == 2 and CG.TARGETING == 1
      and list(CG.PLACEOBJ.values()) == [9110000 + cpid, 9110000 + cpid], str((CG.USED, list(CG.PLACEOBJ.values()))))
check("chaîne : bandeau affiché, menu masqué, pose continue", CG.WowlheimPlaceBanner.shown and not CG.WowlheimFrame.shown and CW.state.continuous)
check("chaîne : nouvelle interrogation canplace après la relance (verdict d'avant la pose oublié)", len(canplaces()) == n_cp + 1, str(canplaces()))
col = list(CG.COLORS.values())[-1]
check("chaîne : fantôme natif teinté visible (alpha > 0) pendant le 2e ciblage", col[6] == 1 and col[4] > 0, str(list(col.values())))
cu.execute('ChatSystem("[WL]CP|1|-100.00|202.00|30.00|0.000|1"); ChatSystem("[WL]D|canplace|1"); Tick(0.05)')
pose(2)
for _ in range(15):
    cu.execute("Tick(0.05)")
check("chaîne : seconde pose -> ciblage relancé à nouveau", CG.USED == 3 and CG.TARGETING == 1 and CW.tw.active, str(CG.USED))
# UseInventoryItem refusé une fois par le client (avant : surveillance abandonnée, bandeau sans fantôme)
cu.execute("REFUSE = 1")
pose(3)
for _ in range(10):
    cu.execute("Tick(0.05)")
check("relance refusée par le client : pas encore de ciblage", CG.USED == 4 and not CG.TARGETING)
for _ in range(10):
    cu.execute("Tick(0.05)")
check("relance refusée : nouvelle tentative -> ciblage, la pose en chaîne continue", CG.USED == 5 and CG.TARGETING == 1 and CW.state.continuous
      and CG.WowlheimPlaceBanner.shown, str(CG.USED))
# survol : souris sur un cadre d'interface (sac) -> ni surbrillance ni info-bulle
cu.execute("Tick(0.05)")
check("survol d'une pièce sur le monde : surbrillance + info-bulle", list(CG.HL.values())[-1] != "off" and CG.WowlheimHoverTip and CG.WowlheimHoverTip.shown)
cu.execute("FOCUS = ContainerFrame1 or CreateFrame('Frame', 'ContainerFrame1'); Tick(0.05)")
check("souris sur un cadre d'interface : surbrillance retirée, info-bulle masquée", list(CG.HL.values())[-1] == "off" and not CG.WowlheimHoverTip.shown)
cu.execute("FOCUS = WorldFrame; Tick(0.05)")
# pose sans réponse du serveur : relance quand même après PLACE_WAIT
cu.execute('TARGETING = nil; Tick(0.02); Spell("SPELLCAST_STOP")')
u1 = CG.USED
for _ in range(int(CG.WowlheimCore.PLACE_WAIT / 0.1) + 5):
    cu.execute("Tick(0.1)")
check("pose vue sans D|place : ciblage relancé après %g s" % CG.WowlheimCore.PLACE_WAIT, CG.USED == u1 + 1 and CG.TARGETING == 1, str(CG.USED - u1))
# client qui refuse toujours : après ARM_RETRIES essais, menu (pièce gardée), plus de boucle
cu.execute("REFUSE = 99")
pose(4)
for _ in range(80):
    cu.execute("Tick(0.05)")
check("relance toujours refusée : menu rouvert après %d essais, pièce gardée" % CG.WowlheimCore.ARM_RETRIES,
      CG.WowlheimFrame.shown and CW.state.piece == cpid and CG.USED == u1 + 1 + CG.WowlheimCore.ARM_RETRIES, str(CG.USED - u1))
# Échap en pose sans ciblage (relance en attente) : fin de la pose, bandeau masqué, pas de menu du jeu (p2/118)
cu.execute("REFUSE = 0; RunScript(WowlheimIcon1, 'OnClick', 'LeftButton'); Tick(0.05)")
pose(5)
cu.execute("Tick(0.05); GAMEMENU = 0; ToggleGameMenu()")
check("Échap entre deux poses : fin de la pose, bandeau masqué, menu du jeu NON ouvert", not CW.state.continuous
      and not CG.WowlheimPlaceBanner.shown and CG.GAMEMENU == 0 and not CG.TARGETING)
u2 = CG.USED
cu.execute("Tick(1)")
check("après Échap : pas de relance", CG.USED == u2)
cu.execute("ToggleGameMenu()")
check("Échap hors pose : menu du jeu", CG.GAMEMENU == 1)
cu.execute("Wowlheim.Show(); RunScript(WowlheimIcon1, 'OnClick', 'LeftButton'); Wowlheim.Show(); GAMEMENU = 0; ToggleGameMenu()")
check("Échap menu du marteau ouvert pendant la pose : menu fermé, pose finie, pas de menu du jeu",
      not CG.WowlheimFrame.shown and not CW.state.continuous and CG.GAMEMENU == 0)

# --- WowlheimPieces.lua : panneau des coffres (Container de Valheim, server/Wowlheim/Pieces.cpp) -------------------------
toc = [l.strip() for l in open(os.path.join(ADDON, "Wowlheim.toc"), encoding="utf-8") if l.strip() and not l.startswith("#")]
check("toc : WowlheimPieces.lua chargé après Wowlheim.lua et WowlheimCraft.lua", "WowlheimPieces.lua" in toc
      and toc.index("WowlheimPieces.lua") > toc.index("Wowlheim.lua") and toc.index("WowlheimPieces.lua") > toc.index("WowlheimCraft.lua"), str(toc))
pu = new_lua()
pu.execute(MOCK)
pu.execute("BAG_CLICKS = {}; function ContainerFrameItemButton_OnClick(button, ignoreShift) table.insert(BAG_CLICKS, button) end")
for f in ("WowlheimData.lua", "WowlheimCore.lua", "Wowlheim.lua", "WowlheimCraft.lua", "WowlheimSkills.lua", "WowlheimPieces.lua"):
    pu.execute(read(f))
P = pu.globals()
PC = P.Wowlheim.Chest
check("WowlheimPieces.lua se charge (API simulée)", PC is not None and P.WowlheimChestEvents is not None and P.WowlheimCore.PANELS.chest is not None)
pu.execute('WowlheimDB = {}; Fire("VARIABLES_LOADED"); Fire("PLAYER_ENTERING_WORLD"); Tick(0.1)')
def pfeed(lines):
    pu.execute(";".join('ChatSystem("%s"); event = "CHAT_MSG_SYSTEM"; arg1 = "%s"; WowlheimChestEvents.scripts.OnEvent(); event = nil; arg1 = nil' % (l, l) for l in lines))
def psent():
    return list(P.SENT.values())
# logique pure
st = PC.NewState()
check("CH/CI sans CE : contenu pas encore appliqué", PC.OnLine(st, "[WL]CH|77|Coffre|5|2|2|1") is None and PC.OnLine(st, "[WL]CI|77|3|9200001|30|0|0") is None and st.guid is None)
check("CE : contenu appliqué (case 3 : 30 Bois)", PC.OnLine(st, "[WL]CE|77") == "content" and st.guid == 77 and st.w == 5 and st.h == 2 and st.slots[3].item == 9200001 and st.slots[3].count == 30)
check("OPEN|chest du même coffre : ouverture", PC.OnLine(st, "[WL]OPEN|chest|77") == "open" and PC.OnLine(st, "[WL]OPEN|chest|78") is None and PC.OnLine(st, "[WL]OPEN|craft|77|workbench") is None)
check("case de la grille : ligne 2 colonne 1 = case 5 ; hors coffre = nil", PC.SlotIndex(st, 2, 1) == 5 and PC.SlotIndex(st, 3, 1) is None and PC.SlotIndex(st, 1, 6) is None)
check("lignes d'autres modules ignorées", PC.OnLine(st, "[WL]SM|1|smelter") is None and PC.OnLine(st, "pas une ligne") is None)
# clic sur un coffre en jeu : contenu puis OPEN -> panneau
n_chat = len(list(P.CHAT_SHOWN.values()))
pfeed(["[WL]CH|9500010|Coffre renforcé|6|4|2|2", "[WL]CI|9500010|0|9200001|30|0|0", "[WL]CI|9500010|7|9201011|1|80|100", "[WL]CE|9500010", "[WL]OPEN|chest|9500010"])
cf = P.WowlheimChestFrame
check("OPEN|chest : panneau du coffre ouvert, titre = nom de Valheim", cf is not None and cf.shown and P.WowlheimChestTitle.text == "Coffre renforcé")
check("lignes [WL] du coffre masquées du chat", len(list(P.CHAT_SHOWN.values())) == n_chat)
check("grille 6 x 4 : 24 cases visibles, les autres cachées", P.WowlheimChestSlot1.shown and P.WowlheimChestSlot6.shown and not P.WowlheimChestSlot7.shown
      and P.WowlheimChestSlot25.shown and P.WowlheimChestSlot30.shown and not P.WowlheimChestSlot33.shown, "")
check("case 0 : icône du Bois, quantité 30 ; case 7 (2e ligne, 2e colonne) : la hache, sans quantité",
      P.WowlheimChestSlot1.icon.shown and P.WowlheimChestSlot1.count.text == 30 and P.WowlheimChestSlot10.icon.shown and P.WowlheimChestSlot10.count.text == ""
      and not P.WowlheimChestSlot2.icon.shown, str((P.WowlheimChestSlot1.count.text, P.WowlheimChestSlot10.count.text)))
pu.execute("RunScript(WowlheimChestSlot10, 'OnClick', 'LeftButton')")
check("clic sur une case : chest take <guid> <case>", psent()[-1] == ".build api chest take 9500010 7", str(psent()[-2:]))
n = len(psent())
pu.execute("RunScript(WowlheimChestSlot2, 'OnClick', 'LeftButton')")
check("clic sur une case vide : rien envoyé", len(psent()) == n)
pu.execute("this = { GetParent = function() return { GetID = function() return 2 end } end, GetID = function() return 5 end }; ContainerFrameItemButton_OnClick('RightButton'); this = nil")
check("clic droit sur un objet des sacs, coffre ouvert : chest put <guid> <sac> <case> (pas d'utilisation de l'objet)",
      psent()[-1] == ".build api chest put 9500010 2 5" and len(list(P.BAG_CLICKS.values())) == 0, str(psent()[-1]))
pu.execute("this = { GetParent = function() return { GetID = function() return 0 end } end, GetID = function() return 1 end }; ContainerFrameItemButton_OnClick('LeftButton'); this = nil")
check("clic gauche dans les sacs : comportement normal de WoW", list(P.BAG_CLICKS.values()) == ["LeftButton"])
pu.execute("RunScript(WowlheimChestTakeAll, 'OnClick', 'LeftButton'); RunScript(WowlheimChestStackAll, 'OnClick', 'LeftButton')")
check("Prendre tout / Objets similaires : takeall / stackall", psent()[-2:] == [".build api chest takeall 9500010", ".build api chest stackall 9500010"], str(psent()[-2:]))
pfeed(["[WL]A|30", "[WL]CH|9500010|Coffre renforcé|6|4|2|1", "[WL]CI|9500010|7|9201011|1|80|100", "[WL]CE|9500010", "[WL]D|chest|1"])
check("contenu renvoyé après une reprise : case 0 vidée", not P.WowlheimChestSlot1.icon.shown and P.WowlheimChestSlot10.icon.shown and cf.shown)
pu.execute("RunScript(WowlheimChestClose, 'OnClick', 'LeftButton')")
check("fermeture : chest close <guid> (le coffre se libère)", not cf.shown and psent()[-1] == ".build api chest close 9500010" and PC.state.guid is None, str(psent()[-1]))
pu.execute("ContainerFrameItemButton_OnClick('RightButton')")
check("coffre fermé : clic droit dans les sacs = comportement normal", list(P.BAG_CLICKS.values())[-1] == "RightButton")
pfeed(["[WL]CH|9500011|Coffre|5|2|2|0", "[WL]CE|9500011", "[WL]OPEN|chest|9500011"])
check("autre coffre (5 x 2) : panneau rouvert, 10 cases", cf.shown and P.WowlheimChestSlot5.shown and not P.WowlheimChestSlot6.shown and P.WowlheimChestSlot13.shown and not P.WowlheimChestSlot17.shown)
n = len(psent())
pfeed(["[WL]E|Trop loin.", "[WL]CX|9500011", "[WL]D|chest|0"])
check("CX| (trop loin) : panneau fermé sans renvoyer close", not cf.shown and len(psent()) == n)

# --- WowlheimUseHammer (DLL, 2026-10-27) : en jeu, UseInventoryItem appelé par l'addon hors touche / clic (relance après la
# pose : OnUpdate, CHAT_MSG D|place) ne démarre pas le ciblage (CanPerformAction(2) 0x494a50) ; la DLL fournit
# WowlheimUseHammer(slot) qui fait le même appel avec le drapeau « touche en cours ». L'addon doit l'utiliser s'il existe.
calls = []
r = core.UseHammer(None, lambda s: calls.append(("item", s)), 16)
check("UseHammer sans DLL : UseInventoryItem(16), voie lua", r == "lua" and calls == [("item", 16)], str((r, calls)))
calls = []
r = core.UseHammer(lambda s: calls.append(("dll", s)) or 1, lambda s: calls.append(("item", s)))
check("UseHammer avec DLL : WowlheimUseHammer(16) seul (slot par défaut = HAMMER_SLOT), ciblage renvoyé",
      r == ("dll", 1) and calls == [("dll", 16)], str((r, calls)))
calls = []
r = core.UseHammer(lambda s: calls.append(("dll", s)), lambda s: calls.append(("item", s)), 16)
check("UseHammer avec DLL sans ciblage : pas de double utilisation (la surveillance relance)", r == ("dll", None) and calls == [("dll", 16)], str((r, calls)))

HW_MOCK = CHAIN_MOCK + r"""
HW = nil      -- vrai pendant un clic (RunScript OnClick) : seul cas où le vrai client accepte UseInventoryItem d'un addon
function UseInventoryItem(slot) USED = USED + 1; USED_SLOT = slot; if HW then TARGETING = 1 end end
HAMMER = 0; HAMMER_SLOT = nil
function WowlheimUseHammer(slot) HAMMER = HAMMER + 1; HAMMER_SLOT = slot; TARGETING = 1; return 1 end
"""
hu = new_ui(HW_MOCK)
HG = hu.globals(); HWL = HG.Wowlheim
hu.execute('WowlheimDB = { cat = 3 }; Fire("VARIABLES_LOADED"); Fire("PLAYER_ENTERING_WORLD"); Tick(0.1)')
hu.execute("RunScript(WowlheimIcon1, 'OnClick', 'LeftButton'); Tick(0.05)")
check("DLL présente : 1er ciblage par WowlheimUseHammer(16), pas UseInventoryItem", HG.HAMMER == 1 and HG.HAMMER_SLOT == 16 and HG.USED == 0
      and HG.TARGETING == 1 and HWL.lastUse == "dll", str((HG.HAMMER, HG.USED)))
for n in range(1, 4):
    hu.execute('TARGETING = nil; Tick(0.02); Spell("SPELLCAST_STOP")')
    hu.execute('ChatSystem("[WL]M|Pièce posée (id %d) [sans coût]"); ChatSystem("[WL]D|place|1")' % (9000400 + n))
    for _ in range(15):
        hu.execute("Tick(0.05)")
check("pose en chaîne (relance hors clic) : 3 relances par WowlheimUseHammer, ciblage actif, aucun UseInventoryItem",
      HG.HAMMER == 4 and HG.USED == 0 and HG.TARGETING == 1 and HWL.state.continuous and not HG.WowlheimFrame.shown,
      str((HG.HAMMER, HG.USED, HG.WowlheimFrame.shown)))
# sans DLL, la même relance hors clic échoue comme en jeu : ARM_RETRIES essais puis menu (comportement de repli conservé)
hu.execute("WowlheimUseHammer = nil; TARGETING = nil; Tick(0.02); Spell('SPELLCAST_STOP')")
hu.execute('ChatSystem("[WL]M|Pièce posée (id 9000499) [sans coût]"); ChatSystem("[WL]D|place|1")')
for _ in range(80):
    hu.execute("Tick(0.05)")
check("sans DLL : relance hors clic refusée -> %d essais UseInventoryItem puis menu" % CG.WowlheimCore.ARM_RETRIES,
      HG.USED == CG.WowlheimCore.ARM_RETRIES and HG.WowlheimFrame.shown and HWL.lastUse == "lua", str((HG.USED, HG.WowlheimFrame.shown)))

print("RÉSULTAT :", "OK" if ok else "ÉCHEC")
sys.exit(0 if ok else 1)
