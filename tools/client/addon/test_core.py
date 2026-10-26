"""Teste l'addon Wowlheim hors du jeu avec lupa (Lua 5.4 : on fournit les fonctions 5.0 manquantes).
  1. WowlheimCore.lua (logique pure : protocole, inventaire, categories, pose continue) ;
  2. WowlheimData.lua (genere) : forme des donnees ;
  3. Wowlheim.lua charge dans une API WoW SIMULEE (CreateFrame, sacs, marteau...) : clics, molette, messages serveur.
     La simulation ne prouve rien sur le comportement du vrai client 1.12 (jamais charge en jeu) ; elle attrape les erreurs
     d'execution evidentes (nil, fautes de frappe) et verifie les commandes envoyees au serveur.
Lancer avec le venv de tools/client : tools/client/.venv/Scripts/python.exe tools/client/addon/test_core.py"""
import os, sys
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
    if st not in ("", "workbench", "forge", "stonecutter") or (st and not data.stations[st]):
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
check("échec D|place|0 => arrêt de la pose continue", core.OnServerMessage(st, core.ParseLine("[WL]D|place|0")) is None and not st.continuous)
cmds = core.ChooseMode(st, "remove")
check("Démolir : mode remove", cmds.n == 1 and cmds[1] == ".build api mode remove" and st.mode == "remove" and not st.continuous)
cmds = core.Rotate(st, 1)
check("rotation en mode démolir : rien", cmds.n == 0)
cmds, use = core.ChoosePiece(st, 7)
check("choisir une pièce depuis Démolir : mode build puis select", cmds.n == 2 and cmds[1] == ".build api mode build" and cmds[2] == ".build api select 7 0")
core.ChooseMode(st, "repair")
cmds = core.Cancel(st)
check("annuler en mode réparer : retour au mode build", cmds.n == 1 and cmds[1] == ".build api mode build" and st.mode == "build")
cmds = core.Cancel(st)
check("annuler en mode build : rien à envoyer", cmds.n == 0)
check("relance après la recharge du marteau", core.RelaunchTime(100, 99.5, 1.5) == 101.05 and core.RelaunchTime(100, 0, 0) == 100.25)

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
function Tick(dt) NOW = NOW + dt; this = WowlheimEvents; WowlheimEvents.scripts.OnUpdate(); this = nil end
function ChatSystem(text) event = "CHAT_MSG_SYSTEM"; arg1 = text; ChatFrame_OnEvent("CHAT_MSG_SYSTEM"); Fire("CHAT_MSG_SYSTEM", text) end
"""

ui = new_lua()
ui.execute(MOCK)
for f in ("WowlheimData.lua", "WowlheimCore.lua", "Wowlheim.lua"):
    ui.execute(read(f))
G = ui.globals()
WL = G.Wowlheim
check("Wowlheim.lua se charge (API simulée)", WL is not None)
ui.execute('Fire("VARIABLES_LOADED"); Fire("PLAYER_ENTERING_WORLD")')
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
# Molette => rotation
ui.execute("RunScript(WowlheimFrame, 'OnMouseWheel', 1)")
check("molette : select avec rot 1", list(G.SENT.values())[-1] == ".build api select %d 1" % pid)
check("encadré : rotation affichée", "22.5" in G.WowlheimInfoRot.text, G.WowlheimInfoRot.text)
# Pose reussie => relance automatique (une seule fois malgre D + M)
ui.execute('TARGETING = nil; ChatSystem("[WL]M|Pièce Mur posée (id 9500001)"); ChatSystem("[WL]D|place|1")')
check("lignes [WL] masquées du chat", len(G.CHAT_SHOWN) == 0)
ui.execute("Tick(0.1)")
check("pas de relance avant le délai", G.USED == 1)
ui.execute("Tick(0.3)")
check("pose continue : relance du ciblage", G.USED == 2 and G.TARGETING == 1)
ui.execute("Tick(1)")
check("une seule relance par pose", G.USED == 2)
# Clic droit sur le panneau => annulation
ui.execute("RunScript(WowlheimFrame, 'OnMouseUp', 'RightButton')")
check("clic droit : ciblage annulé", G.TARGETING is None and not WL.state.continuous)
ui.execute('ChatSystem("[WL]D|place|1"); Tick(1)')
check("après annulation : pas de relance", G.USED == 2)
# Erreur serveur => UIErrorsFrame
ui.execute('ChatSystem("[WL]E|Ressources insuffisantes")')
check("E| affiché dans UIErrorsFrame", list(G.ERRORS.values())[-1] == "Ressources insuffisantes")
# Divers : Reparer / Demolir
ui.execute("RunScript(WowlheimTab1, 'OnClick', 'LeftButton')")
check("onglet Divers : 1re icône = Réparer", G.WowlheimIcon1.entry.special == "repair" and G.WowlheimIcon2.entry.special == "remove")
ui.execute("RunScript(WowlheimIcon2, 'OnClick', 'LeftButton')")
check("Démolir : mode remove envoyé", list(G.SENT.values())[-1] == ".build api mode remove")
ui.execute("RunScript(WowlheimIcon3, 'OnClick', 'LeftButton')")
sent = list(G.SENT.values())
check("choisir une pièce après Démolir : mode build puis select", sent[-2] == ".build api mode build" and sent[-1].startswith(".build api select "), str(sent[-2:]))
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
    if bool(b.icon.desat) == bool(affordable):
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

print("RÉSULTAT :", "OK" if ok else "ÉCHEC")
sys.exit(0 if ok else 1)
