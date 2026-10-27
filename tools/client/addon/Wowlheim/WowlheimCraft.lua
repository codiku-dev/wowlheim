-- WowlheimCraft.lua : panneaux de FABRICATION et de FONDERIE / FOUR A CHARBON, facon Valheim (client 1.12.1, Lua 5.0).
-- JAMAIS CHARGE EN JEU a ce jour : syntaxe et logique verifiees hors du jeu seulement (tools/client/addon/test_core.py).
-- Logique pure (analyse des lignes C| S| SM|, possede/requis, etat des boutons) : WowlheimCore.lua.
--
-- Fabrication (Valheim : onglet Fabrication de l'inventaire) : liste des recettes a gauche (sans station + station a portee),
--   detail a droite (objet produit, ingredients possede/requis, station requise / actuelle, bouton Fabriquer).
--   Serveur : ".build api recipes" (C|), ".build api station" (S|, etabli seulement), ".build api craft <id>".
-- Fonderie / four a charbon (Valheim : interrupteurs « ajouter minerai / combustible » de la station) :
--   ".build api smelter status|add|take [guid]" (SM|), rafraichi toutes les 2 s tant que le panneau est ouvert ;
--   s'ouvre aussi tout seul quand une ligne SM| non sollicitee arrive (clic sur la station en jeu).
-- Fabrication : s'ouvre aussi sur OPEN|craft|guid|kind (clic sur une table de fabrication / forge / tailleur / table
--   d'artisan) ; champ de recherche au-dessus de la liste ; recettes inconnues cachees (".build api known") ; bouton
--   Reparer (".build api repairable" -> RI|, ".build api repairitems" -> R|).

local WL = Wowlheim;
local Core = WowlheimCore;
local Data = WowlheimData;

WL.Craft = {};
WL.Smelt = {};
local CR = WL.Craft;
local SL = WL.Smelt;

CR.ROWS = 12;             -- 13 avant le champ de recherche (meme hauteur de liste au total)
CR.ROW_H = 24;
CR.LIST_W = 232;
CR.ING_SLOTS = 6;
CR.STATION_POLL = 5;      -- s : rafraichissement de la station a portee
SL.POLL = 2;              -- s : rafraichissement de la fonderie
CR.REPAIR_ICON = "Interface\\Icons\\INV_Hammer_20";

CR.state = Core.NewCraft();
CR.scroll = 0;
CR.showAll = nil;
CR.selectedId = nil;
CR.list = { n = 0 };
CR.query = "";            -- recherche (nom / description ; toutes les stations pendant une recherche)
CR.repair = Core.NewRepair();
SL.state = Core.NewSmelt();

local function ORANGE() return WL.ORANGE[1], WL.ORANGE[2], WL.ORANGE[3]; end

-- ------------------------------------------------------------------------------------------------
-- Elements communs (bois sombre, comme le menu du marteau)
-- ------------------------------------------------------------------------------------------------
local function WoodButton(name, parent, w, h, label, onClick)
	local b = CreateFrame("Button", name, parent);
	b:SetWidth(w); b:SetHeight(h);
	WL.WoodBackdrop(b, 12);
	b:SetBackdropColor(0.30, 0.19, 0.09, 0.95);
	-- libelle borne au bouton (5 px de marge de chaque cote, une ligne) : il ne peut pas deborder
	local fs = WL.Label(b, name .. "Text", "GameFontNormal", w - 10, 14, "CENTER", "MIDDLE");
	fs:SetPoint("CENTER", b, "CENTER", 0, 0);
	fs:SetText(label);
	b.label = fs;
	WL.AddHighlight(b, "Interface\\Buttons\\UI-Listbox-Highlight2");
	b:SetScript("OnClick", onClick);
	return b;
end

-- Active / desactive un bouton bois (texte grise ; Disable empeche OnClick dans le client)
local function SetButtonEnabled(b, on)
	b.on = on;
	if ( on ) then
		b:Enable();
		b.label:SetTextColor(ORANGE());
		b:SetBackdropBorderColor(WL.ORANGE[1], WL.ORANGE[2], WL.ORANGE[3], 1);
	else
		b:Disable();
		b.label:SetTextColor(0.45, 0.40, 0.33);
		b:SetBackdropBorderColor(WL.BROWN_EDGE[1], WL.BROWN_EDGE[2], WL.BROWN_EDGE[3], WL.BROWN_EDGE[4]);
	end
end

local function CloseButton(name, parent, frame)
	-- meme bouton et meme place que celui du menu du marteau (24 x 24, marges 16 / 12)
	local b = WoodButton(name, parent, 24, 24, "x", function() frame:Hide(); end);
	b:SetPoint("TOPRIGHT", parent, "TOPRIGHT", -16, -12);
	return b;
end

-- key : "craft" / "smelt" (WowlheimCore.PANELS) : position par defaut hors du centre de l'ecran, memorisee apres un glisser.
local function NewPanel(name, w, h, key)
	local f = CreateFrame("Frame", name, UIParent);
	f:SetWidth(w); f:SetHeight(h);
	WL.PlacePanel(f, key);
	f:SetFrameStrata("MEDIUM");
	if ( f.SetToplevel ) then f:SetToplevel(1); end
	WL.WoodBackdrop(f, 16);
	f:EnableMouse(1);
	f:SetMovable(1);
	f:RegisterForDrag("LeftButton");
	f:SetScript("OnDragStart", function() this:StartMoving(); end);
	f:SetScript("OnDragStop", function() this:StopMovingOrSizing(); WL.SavePanel(this, key); end);
	f:Hide();
	table.insert(UISpecialFrames, name);
	return f;
end

local function Bar(name, parent, w, h, r, g, b)
	local bar = CreateFrame("StatusBar", name, parent);
	bar:SetWidth(w); bar:SetHeight(h);
	bar:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar");
	bar:SetStatusBarColor(r, g, b);
	bar:SetMinMaxValues(0, 1);
	bar:SetValue(0);
	local bg = bar:CreateTexture(name .. "Bg", "BACKGROUND");
	bg:SetTexture(0, 0, 0, 0.6);
	bg:SetAllPoints(bar);
	local txt = WL.Label(bar, name .. "Text", "GameFontHighlightSmall", w - 4, h, "CENTER", "MIDDLE");
	txt:SetPoint("CENTER", bar, "CENTER", 0, 0);
	bar.text = txt;
	return bar;
end

local function SetBar(bar, frac, text)
	bar:SetValue(frac);
	bar.frac = frac;
	bar.text:SetText(text);
end

-- partages avec WowlheimSkills.lua (panneau des competences)
WL.NewPanel = NewPanel;
WL.Bar = Bar;
WL.SetBar = SetBar;
WL.CloseButton = CloseButton;

local function StationIcon(kind)
	local ic = Core.STATION_ICON[kind];
	if ( ic ) then return "Interface\\Icons\\" .. ic; end
	return "Interface\\Icons\\INV_Hammer_20";
end

-- ================================================================================================
-- PANNEAU DE FABRICATION
-- ================================================================================================
-- Mise en page (600 x 412, marges 16, pas de 8) :
--   12 haut | en-tete 28 : onglet « Fabrication », station (icone, nom, niveau), bascule des stations, fermeture
--   8 | recherche 20 (au-dessus de la liste) | 8 | liste 232 x 296          fiche 328 x 324 (de la recherche au bas de la liste)
--   8 | message (2 lignes, 24) a gauche, bouton Reparer a droite | 8 bas
CR.M = 16;
CR.HEAD_Y = 12;
CR.HEAD_H = 28;
CR.SEARCH_Y = CR.HEAD_Y + CR.HEAD_H + 8;                      -- 48
CR.LIST_Y = CR.SEARCH_Y + 20 + 8;                             -- 76
CR.LIST_H = CR.ROWS * CR.ROW_H + 8;                           -- 296
CR.BOTTOM_Y = CR.LIST_Y + CR.LIST_H + 8;                      -- 380
CR.DETAIL_X = CR.M + CR.LIST_W + 8;                           -- 256
CR.ROW_TEXT_W = CR.LIST_W - 8 - 2 - 20 - 6 - 24;              -- 172 : ligne 224 - icone 20 et marges - marteau 14 (+ 4 + 6)

function CR.Build()
	if ( CR.frame ) then return; end
	local W, H = Core.PANELS.craft.w, Core.PANELS.craft.h;
	local M = CR.M;
	local f = NewPanel("WowlheimCraftFrame", W, H, "craft");
	f:SetScript("OnShow", function() CR.OnShow(); end);
	f:SetScript("OnHide", function() CR.elapsed = 0; WL.HideTooltip(); if ( CR.searchBox ) then CR.searchBox:ClearFocus(); end end);
	CR.frame = f;
	CloseButton("WowlheimCraftClose", f, f);

	-- En-tete : onglet « Fabrication » + station a portee (icone, nom, niveau) + bascule « toutes les stations »
	local tab = CreateFrame("Frame", "WowlheimCraftTab", f);
	tab:SetWidth(128); tab:SetHeight(CR.HEAD_H);
	tab:SetPoint("TOPLEFT", f, "TOPLEFT", M, -CR.HEAD_Y);
	WL.WoodBackdrop(tab, 12);
	tab:SetBackdropColor(0.32, 0.20, 0.09, 0.95);
	tab:SetBackdropBorderColor(WL.ORANGE[1], WL.ORANGE[2], WL.ORANGE[3], 1);
	local tabText = WL.Label(tab, "WowlheimCraftTabText", "GameFontNormal", 118, 14, "CENTER", "MIDDLE");
	tabText:SetPoint("CENTER", tab, "CENTER", 0, 0);
	tabText:SetText("Fabrication");
	tabText:SetTextColor(ORANGE());

	-- bascule a droite, avant la fermeture (16 + 24 + 8)
	local ALL_W = 136;
	local all = WoodButton("WowlheimCraftShowAll", f, ALL_W, 24, "", function() CR.SetShowAll(not CR.showAll); end);
	all.label:SetFontObject(GameFontNormalSmall);
	all:SetPoint("TOPRIGHT", f, "TOPRIGHT", -(M + 24 + 8), -(CR.HEAD_Y + 2));
	all:SetScript("OnEnter", function()
		WL.ShowTooltip(this, "Recettes affichées", { "Station à portée : recettes réalisables ici (et à la main).",
			"Toutes les stations : aussi les recettes de la forge, du tailleur de pierre, etc.", n = 2 });
	end);
	all:SetScript("OnLeave", WL.HideTooltip);
	CR.allButton = all;

	local sx = M + 128 + 8;                                     -- 152
	local sIcon = f:CreateTexture("WowlheimCraftStationIcon", "ARTWORK");
	sIcon:SetWidth(28); sIcon:SetHeight(28);
	sIcon:SetPoint("TOPLEFT", f, "TOPLEFT", sx, -CR.HEAD_Y);
	CR.stationIcon = sIcon;
	CR.STATION_TEXT_W = W - (M + 24 + 8 + ALL_W + 8) - (sx + 28 + 8);   -- 220
	local sName = WL.Label(f, "WowlheimCraftStationName", "GameFontNormal", CR.STATION_TEXT_W, 14, "LEFT", "MIDDLE");
	sName:SetPoint("TOPLEFT", f, "TOPLEFT", sx + 28 + 8, -CR.HEAD_Y);
	CR.stationName = sName;
	local sLevel = WL.Label(f, "WowlheimCraftStationLevel", "GameFontHighlightSmall", CR.STATION_TEXT_W, 12, "LEFT", "MIDDLE");
	sLevel:SetPoint("TOPLEFT", f, "TOPLEFT", sx + 28 + 8, -(CR.HEAD_Y + 16));
	CR.stationLevel = sLevel;

	-- Recherche (au-dessus de la liste) : filtre nom / description, toutes les stations pendant une recherche
	CR.searchBox = WL.SearchBox("WowlheimCraftSearch", f, CR.LIST_W, "Rechercher une recette...", function(t) CR.SetSearch(t); end, 20);
	CR.searchBox:SetPoint("TOPLEFT", f, "TOPLEFT", M, -CR.SEARCH_Y);

	-- Liste des recettes (gauche) : lignes de 24, icone 20, nom borne (« ... ») et complet en info-bulle
	local list = CreateFrame("Frame", "WowlheimCraftList", f);
	list:SetWidth(CR.LIST_W); list:SetHeight(CR.LIST_H);
	list:SetPoint("TOPLEFT", f, "TOPLEFT", M, -CR.LIST_Y);
	WL.WoodBackdrop(list, 12);
	list:SetBackdropColor(0.10, 0.07, 0.04, 0.9);
	if ( list.EnableMouseWheel ) then list:EnableMouseWheel(1); end
	list:SetScript("OnMouseWheel", function() CR.SetScroll(CR.scroll - arg1); end);
	CR.listFrame = list;
	CR.rows = {};
	local i = 1;
	while i <= CR.ROWS do
		local b = CreateFrame("Button", "WowlheimCraftRow" .. i, list);
		b:SetWidth(CR.LIST_W - 8); b:SetHeight(CR.ROW_H - 2);
		b:SetPoint("TOPLEFT", list, "TOPLEFT", 4, -(4 + (i - 1) * CR.ROW_H + 1));
		b:SetID(i);
		local sel = b:CreateTexture("WowlheimCraftRow" .. i .. "Sel", "BACKGROUND");
		sel:SetTexture(WL.ORANGE[1], WL.ORANGE[2], WL.ORANGE[3], 0.25);
		sel:SetAllPoints(b);
		sel:Hide();
		b.sel = sel;
		local ic = b:CreateTexture("WowlheimCraftRow" .. i .. "Icon", "ARTWORK");
		ic:SetWidth(20); ic:SetHeight(20);
		ic:SetPoint("LEFT", b, "LEFT", 2, 0);
		b.icon = ic;
		local txt = WL.Label(b, "WowlheimCraftRow" .. i .. "Text", "GameFontHighlightSmall", CR.ROW_TEXT_W, 14, "LEFT", "MIDDLE");
		txt:SetPoint("LEFT", ic, "RIGHT", 6, 0);
		b.text = txt;
		-- objet abime reparable a cette station (marteau a droite de la ligne)
		local rep = b:CreateTexture("WowlheimCraftRow" .. i .. "Repair", "OVERLAY");
		rep:SetWidth(14); rep:SetHeight(14);
		rep:SetPoint("RIGHT", b, "RIGHT", -4, 0);
		rep:SetTexture(CR.REPAIR_ICON);
		rep:Hide();
		b.repair = rep;
		WL.AddHighlight(b, "Interface\\Buttons\\UI-Listbox-Highlight2");
		b:SetScript("OnClick", function() if ( this.entry ) then CR.Select(this.entry.r.id); end end);
		b:SetScript("OnEnter", function() if ( this.entry ) then CR.EntryTooltip(this, this.entry); end end);
		b:SetScript("OnLeave", WL.HideTooltip);
		if ( b.EnableMouseWheel ) then b:EnableMouseWheel(1); end
		b:SetScript("OnMouseWheel", function() CR.SetScroll(CR.scroll - arg1); end);
		CR.rows[i] = b;
		i = i + 1;
	end
	local empty = WL.Label(list, "WowlheimCraftEmpty", "GameFontDisableSmall", CR.LIST_W - 32, 40, "CENTER", "MIDDLE");
	empty:SetPoint("CENTER", list, "CENTER", 0, 0);
	CR.emptyText = empty;

	-- Fiche (droite), 328 x 324, marge interieure 12 (Valheim : InventoryGui, fiche de la recette choisie) :
	--   12  icone 48 | nom (1 ligne), quantite, etat de reparation
	--   68  description 3 lignes (40)
	--   114 filet | 122 « Station : Forge » | 138 niveau requis / actuel (rouge si insuffisant) | 158 filet
	--   166 « Ressources requises » (+ « possédé / requis » a droite) | 184 2 colonnes x 3 lignes de 32 (icone 32, nom + nombre)
	--   bas : « Dans vos sacs : n » a gauche, Fabriquer a droite
	local DW = W - M - CR.DETAIL_X;                                 -- 328
	local DH = CR.LIST_Y + CR.LIST_H - CR.SEARCH_Y;                 -- 324
	local P = 12;
	local d = CreateFrame("Frame", "WowlheimCraftDetail", f);
	d:SetWidth(DW); d:SetHeight(DH);
	d:SetPoint("TOPLEFT", f, "TOPLEFT", CR.DETAIL_X, -CR.SEARCH_Y);
	WL.WoodBackdrop(d, 12);
	d:SetBackdropColor(0.10, 0.07, 0.04, 0.9);
	d:EnableMouse(1);
	d:SetScript("OnEnter", function() local e = CR.SelectedEntry(); if ( e ) then CR.EntryTooltip(this, e); end end);
	d:SetScript("OnLeave", WL.HideTooltip);
	CR.detail = d;

	local big = d:CreateTexture("WowlheimCraftIcon", "ARTWORK");
	big:SetWidth(48); big:SetHeight(48);
	big:SetPoint("TOPLEFT", d, "TOPLEFT", P, -P);
	CR.icon = big;
	local tx = P + 48 + 8;                                          -- 68
	CR.NAME_W = DW - tx - P;                                        -- 248
	local nm = WL.Label(d, "WowlheimCraftName", "GameFontNormalLarge", CR.NAME_W, 18, "LEFT", "MIDDLE");
	nm:SetPoint("TOPLEFT", d, "TOPLEFT", tx, -P);
	nm:SetTextColor(ORANGE());
	CR.name = nm;
	local cnt = WL.Label(d, "WowlheimCraftCount", "GameFontHighlight", CR.NAME_W, 14, "LEFT", "MIDDLE");
	cnt:SetPoint("TOPLEFT", d, "TOPLEFT", tx, -(P + 20));
	CR.count = cnt;
	local repTxt = WL.Label(d, "WowlheimCraftRepairInfo", "GameFontNormalSmall", CR.NAME_W, 12, "LEFT", "MIDDLE");
	repTxt:SetPoint("TOPLEFT", d, "TOPLEFT", tx, -(P + 36));
	repTxt:SetTextColor(1.0, 0.55, 0.25);
	CR.repairInfo = repTxt;
	local TW = DW - P * 2;                                          -- 304
	CR.TEXT_W = TW;
	local desc = WL.Label(d, "WowlheimCraftDesc", "GameFontHighlightSmall", TW, 40, "LEFT", "TOP");
	desc:SetPoint("TOPLEFT", d, "TOPLEFT", P, -68);
	CR.desc = desc;
	local function Rule(name, y)
		local t = d:CreateTexture(name, "ARTWORK");
		t:SetTexture(WL.BROWN_EDGE[1], WL.BROWN_EDGE[2], WL.BROWN_EDGE[3], 0.6);
		t:SetWidth(TW); t:SetHeight(1);
		t:SetPoint("TOPLEFT", d, "TOPLEFT", P, -y);
		return t;
	end
	CR.rule1 = Rule("WowlheimCraftRule1", 114);
	CR.rule2 = Rule("WowlheimCraftRule2", 158);
	local st = WL.Label(d, "WowlheimCraftReq", "GameFontNormalSmall", TW, 14, "LEFT", "MIDDLE");
	st:SetPoint("TOPLEFT", d, "TOPLEFT", P, -122);
	CR.req = st;
	local lv = WL.Label(d, "WowlheimCraftReqLevel", "GameFontHighlightSmall", TW, 14, "LEFT", "MIDDLE");
	lv:SetPoint("TOPLEFT", d, "TOPLEFT", P, -138);
	CR.reqLevel = lv;
	local ingH = WL.Label(d, "WowlheimCraftIngHeader", "GameFontNormalSmall", TW - 100, 12, "LEFT", "MIDDLE");
	ingH:SetPoint("TOPLEFT", d, "TOPLEFT", P, -166);
	ingH:SetText("Ressources requises");
	CR.ingHeader = ingH;
	local ingHint = WL.Label(d, "WowlheimCraftIngHint", "GameFontDisableSmall", 96, 12, "RIGHT", "MIDDLE");
	ingHint:SetPoint("TOPRIGHT", d, "TOPRIGHT", -P, -166);
	ingHint:SetText("possédé / requis");
	CR.ingHint = ingHint;
	CR.ings = {};
	local COL = (TW + 8) / 2;                                       -- 156
	local s = 1;
	while s <= CR.ING_SLOTS do
		local slot = CreateFrame("Frame", "WowlheimCraftIng" .. s, d);
		slot:SetWidth(COL - 8); slot:SetHeight(32);
		slot:SetPoint("TOPLEFT", d, "TOPLEFT", P + math.mod(s - 1, 2) * COL, -184 - math.floor((s - 1) / 2) * 32);
		slot:EnableMouse(1);
		slot:SetScript("OnEnter", function()
			if ( this.item ) then
				WL.ShowTooltip(this, WL.ItemName(this.item), { "Possédé : " .. this.have .. "  -  Requis : " .. this.need, n = 1 });
			end
		end);
		slot:SetScript("OnLeave", WL.HideTooltip);
		local ic = slot:CreateTexture("WowlheimCraftIng" .. s .. "Icon", "ARTWORK");
		ic:SetWidth(32); ic:SetHeight(32);
		ic:SetPoint("TOPLEFT", slot, "TOPLEFT", 0, 0);
		local inm = WL.Label(slot, "WowlheimCraftIng" .. s .. "Name", "GameFontHighlightSmall", COL - 8 - 38, 12, "LEFT", "MIDDLE");
		inm:SetPoint("TOPLEFT", slot, "TOPLEFT", 38, -2);
		local num = WL.Label(slot, "WowlheimCraftIng" .. s .. "Text", "NumberFontNormal", COL - 8 - 38, 16, "LEFT", "MIDDLE");
		num:SetPoint("BOTTOMLEFT", slot, "BOTTOMLEFT", 38, 0);
		slot.icon = ic; slot.name = inm; slot.text = num;
		CR.ings[s] = slot;
		s = s + 1;
	end
	CR.ING_NAME_W = COL - 8 - 38;                                   -- 110
	-- sous la 3e ligne de ressources (fin a -280) : bouton de 28 a 12 du bas (-284 .. -312) ; a sa gauche, nombre deja possede
	local craft = WoodButton("WowlheimCraftButton", d, 128, 28, "Fabriquer", function() CR.CraftSelected(); end);
	craft:SetPoint("BOTTOMRIGHT", d, "BOTTOMRIGHT", -P, P);
	CR.button = craft;
	local owned = WL.Label(d, "WowlheimCraftOwned", "GameFontHighlightSmall", TW - 128 - 8, 28, "LEFT", "MIDDLE");
	owned:SetPoint("BOTTOMLEFT", d, "BOTTOMLEFT", P, P);
	CR.owned = owned;

	-- Ligne du bas : message (2 lignes, borne) a gauche, Reparer a droite (Valheim : bouton marteau du panneau de fabrication,
	-- repare les objets abimes reparables a cette station).
	local RB_W = 128;
	local rb = WoodButton("WowlheimCraftRepair", f, RB_W, 24, "Réparer", function() CR.RepairAll(); end);
	rb.label:SetFontObject(GameFontNormalSmall);
	rb.label:ClearAllPoints();
	rb.label:SetPoint("LEFT", rb, "LEFT", 30, 0);
	rb.label:SetWidth(RB_W - 30 - 6); rb.label:SetHeight(12);
	rb.label:SetJustifyH("LEFT");
	local ri = rb:CreateTexture("WowlheimCraftRepairIcon", "ARTWORK");
	ri:SetWidth(18); ri:SetHeight(18);
	ri:SetPoint("LEFT", rb, "LEFT", 6, 0);
	ri:SetTexture(CR.REPAIR_ICON);
	rb.icon = ri;
	rb:SetPoint("TOPRIGHT", f, "TOPRIGHT", -M, -CR.BOTTOM_Y);
	rb:SetScript("OnEnter", function()
		WL.ShowTooltip(this, "Réparer", { "Répare les objets abîmés de vos sacs réparables à cette station.", n = 1 });
	end);
	rb:SetScript("OnLeave", WL.HideTooltip);
	CR.repairButton = rb;

	local msg = WL.Label(f, "WowlheimCraftMsg", "GameFontHighlightSmall", W - M * 2 - RB_W - 8, 24, "LEFT", "MIDDLE");
	msg:SetPoint("TOPLEFT", f, "TOPLEFT", M, -CR.BOTTOM_Y);
	CR.msg = msg;
end

-- Info-bulle d'une recette : nom complet, description de l'objet, station requise, etat de reparation
function CR.EntryTooltip(owner, e)
	local it = Data.items[e.r.outItem];
	local txt = Core.StationText(e.check, Data.stations);
	WL.ShowTooltip(owner, e.r.name, { (it and it.desc) or "", txt, Core.RepairText(CR.repair, e.r.outItem) or "", n = 3 });
end

function CR.Message(text, isError)
	if ( not CR.msg ) then return; end
	CR.loadingShown = nil;
	if ( isError ) then
		CR.msg:SetText("|cffff4040" .. text .. "|r");
	else
		CR.msg:SetText(text);
	end
end

function CR.IsShown()
	return CR.frame and CR.frame:IsVisible();
end

function CR.Request()
	WL.Send(Core.CraftRequestStation(CR.state), 1);
	WL.Send(Core.CraftRequestRecipes(CR.state), 1);
end

-- Objets abimes reparables a la station (silencieux ; ancien serveur : plus d'interrogation)
function CR.RequestRepairable()
	if ( CR.repair.unsupported or Core.ChannelHas(WL.channel, "repairable") ) then return; end
	local st = CR.state.station;
	WL.Send(Core.RepairableCommand(st and st.guid), 1);
end

function CR.RepairAll()
	local on = Core.RepairButton(CR.repair);
	if ( not on ) then return; end
	CR.repair.busy = 1;
	CR.Message("Réparation...");
	-- station annoncee par RS| (celle dont les RI| ont ete listes)
	local rs = CR.repair.station;
	WL.Send(Core.RepairItemsCommand(rs and rs.guid));
	CR.UpdateRepair();
end

function CR.UpdateRepair()
	if ( not CR.repairButton ) then return; end
	local on, label = Core.RepairButton(CR.repair);
	SetButtonEnabled(CR.repairButton, on);
	CR.repairButton.label:SetText(label);
	WL.SetGrey(CR.repairButton.icon, not on);
end

function CR.OnShow()
	CR.elapsed = 0;
	CR.countsVersion = nil;
	WL.RecountBags();
	if ( not CR.state.loaded ) then CR.Message("Chargement des recettes..."); CR.loadingShown = 1; else CR.Message(""); end
	WL.RequestKnown();
	CR.RequestRepairable();
	CR.Request();
	CR.Update();
end

-- Recherche (OnTextChanged du champ)
function CR.SetSearch(text)
	text = text or "";
	if ( text == CR.query ) then return; end
	CR.query = text;
	CR.scroll = 0;
	CR.Update();
end

function CR.Show() CR.Build(); CR.frame:Show(); end
function CR.Hide() if ( CR.frame ) then CR.frame:Hide(); end end
function CR.Toggle()
	CR.Build();
	if ( CR.frame:IsVisible() ) then CR.frame:Hide(); else CR.frame:Show(); end
end

function CR.SetShowAll(v)
	if ( v ) then CR.showAll = 1; else CR.showAll = nil; end
	CR.scroll = 0;
	CR.Update();
end

function CR.SetScroll(v)
	local max = CR.list.n - CR.ROWS;
	if ( max < 0 ) then max = 0; end
	CR.scroll = Core.Clamp(v, 0, max);
	CR.UpdateList();
end

function CR.Select(id)
	CR.selectedId = id;
	CR.UpdateList();
	CR.UpdateDetail();
end

function CR.SelectedEntry()
	local i = 1;
	while i <= CR.list.n do
		if ( CR.list[i].r.id == CR.selectedId ) then return CR.list[i]; end
		i = i + 1;
	end
	return nil;
end

function CR.CraftSelected()
	local e = CR.SelectedEntry();
	if ( not e or not Core.CraftButtonEnabled(e.check, CR.state.busy) ) then return; end
	CR.state.busy = 1;
	CR.Message("Fabrication : " .. e.r.name .. "...");
	WL.Send(Core.CraftCommand(e.r.id));
	CR.UpdateDetail();
end

function CR.UpdateHeader()
	local stn = CR.state.station;
	if ( stn ) then
		CR.stationIcon:SetTexture(StationIcon(stn.kind));
		CR.stationIcon:Show();
		WL.FitText(CR.stationName, Data.stations[stn.kind] or stn.kind, CR.STATION_TEXT_W);
		local lv = "Niveau " .. (stn.level or 1);
		if ( not stn.usable ) then lv = lv .. "  -  |cffff4040exposée : il faut un toit|r"; end
		CR.stationLevel:SetText(lv);
	else
		CR.stationIcon:SetTexture(StationIcon(""));
		CR.stationName:SetText("Sans station");
		CR.stationLevel:SetText("Fabrication à la main");
	end
	if ( CR.showAll ) then
		CR.allButton.label:SetText("Toutes les stations");
	else
		CR.allButton.label:SetText("Station à portée");
	end
end

function CR.UpdateList()
	if ( not CR.frame ) then return; end
	local max = CR.list.n - CR.ROWS;
	if ( max < 0 ) then max = 0; end
	CR.scroll = Core.Clamp(CR.scroll, 0, max);
	local i = 1;
	while CR.rows[i] do
		local b = CR.rows[i];
		local e = CR.list[CR.scroll + i];
		if ( e ) then
			b.entry = e;
			b.icon:SetTexture(WL.ItemIcon(e.r.outItem));
			WL.SetGrey(b.icon, not e.check.ok);
			local label = e.r.name;
			-- les noms de recettes multiples portent deja la quantite (« Bronze x5 ») : pas de doublon
			if ( e.r.outCount and e.r.outCount > 1 and not string.find(label, " x" .. e.r.outCount .. "$") ) then label = label .. " x" .. e.r.outCount; end
			-- nom borne a la ligne (« ... ») ; nom complet dans l'info-bulle de la ligne
			WL.FitText(b.text, label, CR.ROW_TEXT_W);
			if ( e.check.ok ) then
				b.text:SetTextColor(1, 1, 1);
			else
				b.text:SetTextColor(0.6, 0.45, 0.4);
			end
			if ( e.r.id == CR.selectedId ) then b.sel:Show(); else b.sel:Hide(); end
			if ( Core.RepairText(CR.repair, e.r.outItem) ) then b.repair:Show(); else b.repair:Hide(); end
			b:Show();
		else
			b.entry = nil;
			b:Hide();
		end
		i = i + 1;
	end
	if ( CR.list.n == 0 ) then
		if ( CR.query ~= "" ) then
			CR.emptyText:SetText("Aucune recette connue ne correspond à cette recherche.");
		elseif ( CR.state.loaded ) then
			CR.emptyText:SetText("Aucune recette disponible ici.");
		else
			CR.emptyText:SetText("Chargement...");
		end
		CR.emptyText:Show();
	else
		CR.emptyText:Hide();
	end
end

function CR.UpdateDetail()
	if ( not CR.frame ) then return; end
	local e = CR.SelectedEntry();
	local s;
	if ( not e ) then
		CR.icon:Hide();
		CR.name:SetText("");
		CR.count:SetText("");
		CR.repairInfo:SetText("");
		CR.desc:SetText("Choisissez une recette dans la liste.");
		CR.req:SetText("");
		CR.reqLevel:SetText("");
		CR.owned:SetText("");
		CR.rule1:Hide(); CR.rule2:Hide();
		CR.ingHeader:Hide();
		CR.ingHint:Hide();
		s = 1;
		while CR.ings[s] do
			CR.ings[s].icon:Hide(); CR.ings[s].name:SetText(""); CR.ings[s].text:SetText(""); CR.ings[s].item = nil;
			s = s + 1;
		end
		SetButtonEnabled(CR.button, false);
		return;
	end
	local r, c = e.r, e.check;
	CR.icon:SetTexture(WL.ItemIcon(r.outItem));
	CR.icon:Show();
	WL.SetTitle(CR.name, r.name, CR.NAME_W, ORANGE());
	CR.count:SetText("Quantité : " .. (r.outCount or 1));
	WL.FitText(CR.repairInfo, Core.RepairText(CR.repair, r.outItem) or "", CR.NAME_W);
	local it = Data.items[r.outItem];
	CR.desc:SetText((it and it.desc) or "");
	local l1, l2, ok = Core.StationLines(c, Data.stations);
	WL.FitText(CR.req, l1, CR.TEXT_W);
	WL.FitText(CR.reqLevel, l2, CR.TEXT_W);
	if ( ok ) then CR.reqLevel:SetTextColor(0.85, 0.85, 0.85); else CR.reqLevel:SetTextColor(1.0, 0.25, 0.2); end
	CR.rule1:Show(); CR.rule2:Show();
	CR.ingHeader:Show();
	CR.ingHint:Show();
	CR.owned:SetText("Dans vos sacs : " .. (WL.counts[r.outItem] or 0));
	s = 1;
	while CR.ings[s] do
		local slot = CR.ings[s];
		local row = c.rows[s];
		if ( row ) then
			slot.icon:SetTexture(WL.ItemIcon(row.item));
			slot.icon:Show();
			WL.SetGrey(slot.icon, not row.ok);
			WL.FitText(slot.name, WL.ItemName(row.item), CR.ING_NAME_W);
			local color = "|cffffffff";
			if ( not row.ok ) then color = "|cffff3030"; end
			slot.text:SetText(color .. row.have .. "/" .. row.need .. "|r");
			slot.item, slot.have, slot.need = row.item, row.have, row.need;
		else
			slot.item = nil;
			slot.icon:Hide();
			slot.name:SetText("");
			slot.text:SetText("");
		end
		s = s + 1;
	end
	SetButtonEnabled(CR.button, Core.CraftButtonEnabled(c, CR.state.busy));
	if ( CR.state.busy ) then CR.button.label:SetText("..."); else CR.button.label:SetText("Fabriquer"); end
end

function CR.Update()
	if ( not CR.frame ) then return; end
	CR.list = Core.RecipeList(CR.state.recipes, WL.counts, CR.state.station, CR.showAll,
		{ query = CR.query, items = Data.items, known = WL.known });
	if ( not CR.SelectedEntry() ) then
		if ( CR.list.n > 0 ) then CR.selectedId = CR.list[1].r.id; else CR.selectedId = nil; end
	end
	CR.countsVersion = WL.countsVersion;
	CR.UpdateHeader();
	CR.UpdateList();
	CR.UpdateDetail();
	CR.UpdateRepair();
end

-- Ligne serveur (appelee par WL.OnSystem) ; renvoie true si le message M|/E| a ete affiche ici.
function CR.OnMessage(m, entry)
	local ev = Core.CraftOnMessage(CR.state, m);
	if ( ev == "crafted" ) then
		WL.bagsDirty = 1;
	end
	-- clic sur une table de fabrication / forge / tailleur / table d'artisan en jeu : ouvrir le panneau (sans le basculer)
	if ( ev == "open" ) then
		CR.Build();
		if ( not CR.IsShown() ) then CR.frame:Show(); else CR.Update(); end
		return nil;
	end
	local rev = Core.RepairOnMessage(CR.repair, m);
	if ( rev == "repaired" ) then
		WL.bagsDirty = 1;
		if ( CR.IsShown() ) then CR.RequestRepairable(); end
	end
	if ( rev and CR.IsShown() ) then CR.Update(); end
	if ( entry and (entry.cmd == "repairitems" or entry.cmd == "repairable") and (m.type == "M" or m.type == "E") ) then
		if ( entry.silent ) then return true; end
		if ( CR.IsShown() ) then
			CR.Message(m.text, m.type == "E");
			return true;
		end
	end
	-- recettes recues (D|recipes) : retirer « Chargement des recettes... » (sans effacer un autre message)
	if ( ev == "recipes" and CR.loadingShown ) then CR.Message(""); end
	if ( ev and CR.IsShown() ) then CR.Update(); end
	local mine = entry and (entry.cmd == "craft" or entry.cmd == "recipes" or entry.cmd == "station");
	if ( mine and CR.IsShown() and (m.type == "M" or m.type == "E") ) then
		if ( entry.silent ) then return true; end
		CR.Message(m.text, m.type == "E" or (entry.cmd == "craft" and string.find(m.text, "Fabriqué", 1, true) == nil));
		if ( m.type == "E" ) then WL.ScreenMessage(m.text, 1); end
		return true;
	end
	return nil;
end

function CR.OnUpdate(elapsed)
	if ( not CR.IsShown() ) then return; end
	if ( CR.countsVersion ~= WL.countsVersion ) then CR.Update(); end
	-- reparation sans reponse (commande oubliee du canal apres CHANNEL_TIMEOUT) : bouton reactive
	if ( CR.repair.busy ) then
		Core.ChannelRoute(WL.channel, nil, GetTime());
		if ( not Core.ChannelHas(WL.channel, "repairitems") ) then CR.repair.busy = nil; CR.UpdateRepair(); end
	end
	CR.elapsed = (CR.elapsed or 0) + elapsed;
	if ( CR.elapsed >= CR.STATION_POLL ) then
		CR.elapsed = 0;
		if ( not Core.ChannelHas(WL.channel, "station") ) then
			WL.Send(Core.CraftRequestStation(CR.state), 1);
		end
		CR.RequestRepairable();
	end
end

-- ================================================================================================
-- PANNEAU DE FONDERIE / FOUR A CHARBON
-- ================================================================================================
-- Mise en page (328 x 236, marges 16, pas de 8) :
--   12 haut | en-tete 32 : icone, nom + etat, fermeture | 8 | 3 lignes de 24 tous les 28 (icone, libelle 72, barre 184)
--   8 | « Pret : » + produits 2 x 2 (icone 20, texte 100) | 8 | 3 boutons de 96 x 24 | 6 | message 1 ligne (12) | 8 bas
function SL.Build()
	if ( SL.frame ) then return; end
	local W, H = Core.PANELS.smelt.w, Core.PANELS.smelt.h;
	local M = 16;
	local f = NewPanel("WowlheimSmeltFrame", W, H, "smelt");
	f:SetScript("OnShow", function() SL.elapsed = 0; WL.RecountBags(); SL.Update(); end);
	f:SetScript("OnHide", function() WL.HideTooltip(); end);
	SL.frame = f;
	CloseButton("WowlheimSmeltClose", f, f);

	local ic = f:CreateTexture("WowlheimSmeltIcon", "ARTWORK");
	ic:SetWidth(32); ic:SetHeight(32);
	ic:SetPoint("TOPLEFT", f, "TOPLEFT", M, -12);
	SL.icon = ic;
	SL.NAME_W = W - (M + 32 + 8) - (M + 24 + 8);                -- 224 (fermeture a droite)
	local nm = WL.Label(f, "WowlheimSmeltName", "GameFontNormalLarge", SL.NAME_W, 18, "LEFT", "MIDDLE");
	nm:SetPoint("TOPLEFT", f, "TOPLEFT", M + 32 + 8, -11);
	nm:SetTextColor(ORANGE());
	SL.name = nm;
	local status = WL.Label(f, "WowlheimSmeltStatus", "GameFontHighlightSmall", SL.NAME_W, 12, "LEFT", "MIDDLE");
	status:SetPoint("TOPLEFT", f, "TOPLEFT", M + 32 + 8, -31);
	SL.status = status;

	-- lignes : icone 24 + libelle (72, une ligne) + barre (184) alignes sur la meme colonne
	local LABEL_W, BAR_X = 72, M + 24 + 8 + 72 + 8;             -- barre de 128 a 312
	local function Row(key, y, label, r, g, b)
		local ri = f:CreateTexture("WowlheimSmelt" .. key .. "Icon", "ARTWORK");
		ri:SetWidth(24); ri:SetHeight(24);
		ri:SetPoint("TOPLEFT", f, "TOPLEFT", M, y);
		local lb = WL.Label(f, "WowlheimSmelt" .. key .. "Label", "GameFontNormalSmall", LABEL_W, 12, "LEFT", "MIDDLE");
		lb:SetPoint("LEFT", ri, "RIGHT", 8, 0);
		lb:SetText(label);
		local bar = Bar("WowlheimSmelt" .. key .. "Bar", f, W - M - BAR_X, 14, r, g, b);
		bar:SetPoint("TOPLEFT", f, "TOPLEFT", BAR_X, y - 5);
		return { icon = ri, label = lb, bar = bar };
	end
	SL.LABEL_W = LABEL_W;
	SL.ore = Row("Ore", -52, "Minerai", 0.80, 0.55, 0.25);
	SL.fuel = Row("Fuel", -80, "Charbon", 0.95, 0.35, 0.10);
	SL.prog = Row("Prog", -108, "Progression", 1.0, 0.75, 0.25);
	SL.prog.icon:SetTexture("Interface\\Icons\\Spell_Fire_Fire");

	-- produits prets : « Pret : » puis 2 colonnes x 2 lignes ; « rien » a la place quand il n'y a rien
	local readyLabel = WL.Label(f, "WowlheimSmeltReadyLabel", "GameFontNormalSmall", 40, 20, "LEFT", "MIDDLE");
	readyLabel:SetPoint("TOPLEFT", f, "TOPLEFT", M, -140);
	readyLabel:SetText("Prêt :");
	SL.readyLabel = readyLabel;
	SL.outs = {};
	SL.OUT_W = 100;
	local i = 1;
	while i <= 4 do
		local oi = f:CreateTexture("WowlheimSmeltOut" .. i .. "Icon", "ARTWORK");
		oi:SetWidth(20); oi:SetHeight(20);
		oi:SetPoint("TOPLEFT", f, "TOPLEFT", M + 40 + math.mod(i - 1, 2) * 132, -140 - math.floor((i - 1) / 2) * 22);
		local ot = WL.Label(f, "WowlheimSmeltOut" .. i .. "Text", "GameFontHighlightSmall", SL.OUT_W, 12, "LEFT", "MIDDLE");
		ot:SetPoint("LEFT", oi, "RIGHT", 4, 0);
		SL.outs[i] = { icon = oi, text = ot };
		i = i + 1;
	end
	local none = WL.Label(f, "WowlheimSmeltNone", "GameFontDisableSmall", 104, 20, "LEFT", "MIDDLE");
	none:SetPoint("TOPLEFT", f, "TOPLEFT", M + 40, -140);
	none:SetText("rien");
	SL.none = none;

	-- 3 boutons de meme taille sur toute la largeur (96 + 4 + 96 + 4 + 96 = 296) ; Maj+clic = remplir (info-bulle)
	local BW = (W - M * 2 - 8) / 3;
	local function Tip(b, title, text)
		b:SetScript("OnEnter", function() WL.ShowTooltip(this, title, { text, n = 1 }); end);
		b:SetScript("OnLeave", WL.HideTooltip);
	end
	SL.addOre = WoodButton("WowlheimSmeltAddOre", f, BW, 24, "Ajouter minerai", function() SL.Add("ore"); end);
	SL.addOre.label:SetFontObject(GameFontNormalSmall);
	SL.addOre:SetPoint("TOPLEFT", f, "TOPLEFT", M, -186);
	Tip(SL.addOre, "Ajouter", "Clic : une unité. Maj+clic : remplir autant que possible.");
	SL.addFuel = WoodButton("WowlheimSmeltAddFuel", f, BW, 24, "Ajouter charbon", function() SL.Add("fuel"); end);
	SL.addFuel.label:SetFontObject(GameFontNormalSmall);
	SL.addFuel:SetPoint("LEFT", SL.addOre, "RIGHT", 4, 0);
	Tip(SL.addFuel, "Ajouter du combustible", "Clic : une unité. Maj+clic : remplir autant que possible.");
	SL.take = WoodButton("WowlheimSmeltTake", f, BW, 24, "Récupérer", function() SL.Take(); end);
	SL.take.label:SetFontObject(GameFontNormalSmall);
	SL.take:SetPoint("LEFT", SL.addFuel, "RIGHT", 4, 0);
	Tip(SL.take, "Récupérer", "Prend les produits prêts.");

	local msg = WL.Label(f, "WowlheimSmeltMsg", "GameFontHighlightSmall", W - M * 2, 12, "LEFT", "MIDDLE");
	msg:SetPoint("TOPLEFT", f, "TOPLEFT", M, -216);
	SL.msg = msg;
end

function SL.IsShown()
	return SL.frame and SL.frame:IsVisible();
end

function SL.Message(text, isError)
	if ( not SL.msg ) then return; end
	if ( isError ) then SL.msg:SetText("|cffff4040" .. text .. "|r"); else SL.msg:SetText(text); end
end

-- Ouverture manuelle (/wlsmelt, touche) : station la plus proche (5 m)
function SL.Open()
	SL.Build();
	SL.state = Core.NewSmelt();
	SL.frame:Show();
	SL.Message("Recherche d'une station à moins de 5 m...");
	WL.Send(Core.SmelterStatusCommand(nil));
end

function SL.Hide() if ( SL.frame ) then SL.frame:Hide(); end end
function SL.Toggle()
	if ( SL.IsShown() ) then SL.frame:Hide(); else SL.Open(); end
end

function SL.Add(what)
	if ( not SL.view ) then return; end
	local fill = IsShiftKeyDown();
	local n = Core.SmelterAddCount(SL.view, what, fill);
	WL.Send(Core.SmelterAddCommand(what, n, SL.state.guid));
end

function SL.Take()
	if ( not SL.view ) then return; end
	WL.Send(Core.SmelterTakeCommand(SL.state.guid));
end

function SL.Update()
	if ( not SL.frame ) then return; end
	local sm = SL.state.sm;
	if ( not sm ) then
		SL.view = nil;
		SL.icon:SetTexture(StationIcon("smelter"));
		SL.name:SetText("Fonderie");
		SL.status:SetText("");
		SetBar(SL.ore.bar, 0, ""); SetBar(SL.fuel.bar, 0, ""); SetBar(SL.prog.bar, 0, "");
		SetButtonEnabled(SL.addOre, false); SetButtonEnabled(SL.addFuel, false); SetButtonEnabled(SL.take, false);
		return;
	end
	local def = Data.smelters and Data.smelters[sm.kind];
	local v = Core.SmelterView(sm, WL.counts, def and def.conversion);
	SL.view = v;
	SL.icon:SetTexture(StationIcon(sm.kind));
	WL.SetTitle(SL.name, sm.name, SL.NAME_W, ORANGE());
	if ( v.active ) then
		SL.status:SetText("|cff40ff40" .. v.status .. "|r");
	else
		SL.status:SetText("|cffff6040" .. v.status .. "|r");
	end
	-- minerai (four a charbon : bois)
	local oreIcon = nil;
	if ( sm.queueItems and sm.queueItems[1] ) then oreIcon = sm.queueItems[1].item; end
	if ( not oreIcon ) then oreIcon = v.oreItem; end
	if ( not oreIcon and def and def.conversion[1] ) then oreIcon = def.conversion[1][1]; end
	if ( oreIcon ) then SL.ore.icon:SetTexture(WL.ItemIcon(oreIcon)); end
	if ( v.kiln ) then
		SL.ore.label:SetText("Bois");
		SL.addOre.label:SetText("Ajouter du bois");
	else
		SL.ore.label:SetText("Minerai");
		SL.addOre.label:SetText("Ajouter minerai");
	end
	SetBar(SL.ore.bar, v.oreFrac, v.oreText);
	-- combustible (absent du four a charbon)
	if ( v.hasFuel ) then
		local fname = WL.ItemName(sm.fuelItem);
		SL.fuel.icon:SetTexture(WL.ItemIcon(sm.fuelItem));
		WL.FitText(SL.fuel.label, fname, SL.LABEL_W);
		SL.addFuel.label:SetText("Ajouter " .. string.lower(fname));
		SetBar(SL.fuel.bar, v.fuelFrac, v.fuelText);
		SL.fuel.icon:Show(); SL.fuel.label:Show(); SL.fuel.bar:Show(); SL.addFuel:Show();
	else
		SL.fuel.icon:Hide(); SL.fuel.label:Hide(); SL.fuel.bar:Hide(); SL.addFuel:Hide();
	end
	SetBar(SL.prog.bar, v.progress, v.progressText);
	-- produits prets
	local i = 1;
	while SL.outs[i] do
		local o = sm.output[i];
		if ( o ) then
			SL.outs[i].icon:SetTexture(WL.ItemIcon(o.item));
			SL.outs[i].icon:Show();
			WL.FitText(SL.outs[i].text, Core.OutputLabel(WL.ItemName(o.item), o.count), SL.OUT_W);
		else
			SL.outs[i].icon:Hide();
			SL.outs[i].text:SetText("");
		end
		i = i + 1;
	end
	if ( v.ready > 0 ) then SL.none:Hide(); else SL.none:Show(); end
	SetButtonEnabled(SL.addOre, v.canAddOre);
	SetButtonEnabled(SL.addFuel, v.canAddFuel);
	SetButtonEnabled(SL.take, v.canTake);
end

-- Ligne serveur (appelee par WL.OnSystem) ; renvoie true si le message M|/E| a ete affiche ici.
function SL.OnMessage(m, entry)
	local ev = Core.SmeltOnMessage(SL.state, m, entry, SL.IsShown());
	if ( ev == "open" ) then
		SL.Build();
		SL.frame:Show();
		SL.Message("");
	elseif ( ev == "update" ) then
		SL.Update();
	elseif ( ev == "lost" ) then
		if ( SL.IsShown() ) then
			SL.frame:Hide();
			WL.ScreenMessage("Aucune fonderie ni four à charbon à moins de 5 m.", 1);
		end
		return true;
	end
	if ( entry and entry.cmd == "smelter" and (m.type == "M" or m.type == "E") ) then
		if ( entry.silent ) then return true; end
		if ( SL.IsShown() ) then
			SL.Message(m.text, m.type == "E");
			return true;
		end
	end
	return nil;
end

function SL.OnUpdate(elapsed)
	if ( not SL.IsShown() ) then return; end
	if ( SL.countsVersion ~= WL.countsVersion ) then
		SL.countsVersion = WL.countsVersion;
		SL.Update();
	end
	SL.elapsed = (SL.elapsed or 0) + elapsed;
	if ( SL.elapsed >= SL.POLL ) then
		SL.elapsed = 0;
		if ( SL.state.guid and not Core.ChannelHas(WL.channel, "smelter") ) then
			WL.Send(Core.SmelterStatusCommand(SL.state.guid), 1);
		end
	end
end

-- ------------------------------------------------------------------------------------------------
-- Commandes, raccourcis (Bindings.xml : WOWLHEIM_CRAFT, WOWLHEIM_SMELT), rafraichissements
-- ------------------------------------------------------------------------------------------------
SLASH_WOWLHEIMCRAFT1 = "/wlcraft";
SlashCmdList["WOWLHEIMCRAFT"] = function() CR.Toggle(); end;
SLASH_WOWLHEIMSMELT1 = "/wlsmelt";
SlashCmdList["WOWLHEIMSMELT"] = function() SL.Toggle(); end;

local uf = CreateFrame("Frame", "WowlheimCraftEvents", UIParent);
uf:SetScript("OnUpdate", function()
	local dt = arg1 or 0;
	CR.OnUpdate(dt);
	SL.OnUpdate(dt);
end);
