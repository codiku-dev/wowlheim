-- Wowlheim.lua : menu de construction du marteau, facon Valheim (client 1.12.1, Lua 5.0).
-- JAMAIS CHARGE EN JEU a ce jour : syntaxe et logique pure verifiees hors du jeu seulement (tools/client/addon/test_core.py).
-- Donnees : WowlheimData.lua (genere). Logique pure / protocole : WowlheimCore.lua.
--
-- Fonctionnement :
--   * equiper le Marteau (objet 9201100, main droite) ouvre le panneau ; le desequiper le ferme ; touche de bascule (Bindings.xml).
--   * clic gauche sur une piece = ".build api select <id> <rot>" puis UseInventoryItem(16) (ciblage au sol) ; apres une pose
--     reussie le ciblage est relance automatiquement (pose continue) jusqu'a annulation (clic droit sur le panneau, Echap).
--   * molette sur le panneau (ou touches liees) = rotation par pas de 22,5 degres ; Maj + molette = defilement de la grille.
--   * Divers commence par Reparer / Demolir (".build api mode repair|remove", puis clic droit sur la piece posee en jeu).

Wowlheim = {};
local WL = Wowlheim;
local Core = WowlheimCore;
local Data = WowlheimData;

WL.COLS = 10;
WL.ROWS = 4;
WL.ICON = 40;
WL.CELL = 44;
WL.MARGIN = 14;
WL.COST_SLOTS = 6;
WL.DEFAULT_CAT = 3;            -- "Construction"
WL.REPAIR_ICON = "Interface\\Icons\\WL_repair";
WL.REPAIR_ICON_FALLBACK = "Interface\\Icons\\INV_Hammer_20";
WL.REMOVE_ICON = "Interface\\Icons\\Ability_Warrior_Sunder";
WL.MISSING_ICON = "Interface\\Icons\\INV_Misc_QuestionMark";

WL.state = Core.NewState();
WL.cat = WL.DEFAULT_CAT;
WL.scroll = 0;
WL.entries = { n = 0 };
WL.counts = {};
WL.hover = nil;
WL.selected = nil;             -- entree choisie (piece ou outil special)
WL.debug = nil;

-- Couleurs « bois » de Valheim
local ORANGE = { 1.0, 0.68, 0.22 };
local BROWN_BG = { 0.16, 0.11, 0.07, 0.94 };
local BROWN_EDGE = { 0.55, 0.40, 0.22, 1 };

-- ------------------------------------------------------------------------------------------------
-- Utilitaires
-- ------------------------------------------------------------------------------------------------
function WL.Send(command)
	SendChatMessage(command, "SAY");
end

function WL.SendAll(cmds)
	local i = 1;
	while i <= cmds.n do
		WL.Send(cmds[i]);
		i = i + 1;
	end
end

function WL.ItemName(id)
	if ( Data.items[id] ) then return Data.items[id].name; end
	local name = GetItemInfo(id);
	if ( name ) then return name; end
	return "objet " .. id;
end

function WL.ItemIcon(id)
	if ( Data.items[id] and Data.items[id].icon ) then return "Interface\\Icons\\" .. Data.items[id].icon; end
	return WL.MISSING_ICON;
end

-- SetTexture renvoie nil si le fichier n'existe pas (comportement 1.12 SUPPOSE, non verifie : utilise seulement pour l'icone
-- WL_repair, absente du patch a ce jour ; au pire c'est l'icone de secours qui s'affiche).
local function SetTextureOr(tex, path, fallback)
	local ok = tex:SetTexture(path);
	if ( not ok and fallback ) then
		tex:SetTexture(fallback);
	end
end

function WL.EntryIcon(tex, e)
	if ( e.special == "repair" ) then
		SetTextureOr(tex, WL.REPAIR_ICON, WL.REPAIR_ICON_FALLBACK);
	elseif ( e.special == "remove" ) then
		tex:SetTexture(WL.REMOVE_ICON);
	elseif ( e.icon and e.icon ~= "" ) then
		tex:SetTexture("Interface\\Icons\\" .. e.icon);
	else
		tex:SetTexture(WL.MISSING_ICON);
	end
end

local function SetGrey(tex, grey)
	if ( tex.SetDesaturated ) then
		if ( grey ) then tex:SetDesaturated(1); else tex:SetDesaturated(nil); end
	end
	if ( grey ) then
		tex:SetVertexColor(0.9, 0.45, 0.45);
	else
		tex:SetVertexColor(1, 1, 1);
	end
end

function WL.HammerEquipped()
	local link = GetInventoryItemLink("player", Core.HAMMER_SLOT);
	if ( link and Core.ItemIdFromLink(link) == Core.HAMMER_ID ) then
		return 1;
	end
	return nil;
end

-- ------------------------------------------------------------------------------------------------
-- Inventaire (sacs)
-- ------------------------------------------------------------------------------------------------
WL.bagApi = {
	numSlots = function(bag) return GetContainerNumSlots(bag); end,
	link = function(bag, slot) return GetContainerItemLink(bag, slot); end,
	count = function(bag, slot)
		local _, n = GetContainerItemInfo(bag, slot);
		return n;
	end,
};

function WL.RecountBags()
	WL.counts = Core.CountBags(WL.bagApi);
	WL.bagsDirty = nil;
end

function WL.EntryAffordable(e)
	if ( e.special ) then return true; end
	local ok = Core.Affordability(e.costs, WL.counts);
	return ok;
end

-- ------------------------------------------------------------------------------------------------
-- Messages
-- ------------------------------------------------------------------------------------------------
function WL.ShowMessage(text, isError)
	if ( WL.frame and WL.frame:IsVisible() ) then
		if ( isError ) then
			WL.msgText:SetText("|cffff4040" .. text .. "|r");
		else
			WL.msgText:SetText(text);
		end
	end
	if ( isError ) then
		UIErrorsFrame:AddMessage(text, 1.0, 0.1, 0.1, 1.0);
	elseif ( not (WL.frame and WL.frame:IsVisible()) ) then
		UIErrorsFrame:AddMessage(text, 1.0, 0.82, 0.0, 1.0);
	end
end

function WL.OnSystem(line)
	local m = Core.ParseLine(line);
	if ( not m ) then return; end
	if ( m.type == "M" ) then
		WL.ShowMessage(m.text);
	elseif ( m.type == "E" ) then
		WL.ShowMessage(m.text, 1);
	elseif ( m.type == "S" ) then
		WL.station = m;
	elseif ( m.type == "D" and m.command == "place" and not m.ok ) then
		WL.ShowMessage("La pièce n'a pas pu être posée.", 1);
	end
	if ( Core.OnServerMessage(WL.state, m) == "relaunch" ) then
		local start, duration = GetInventoryItemCooldown("player", Core.HAMMER_SLOT);
		WL.relaunchAt = Core.RelaunchTime(GetTime(), start, duration);
	end
	WL.UpdateInfo();
end

-- Les lignes [WL] ne doivent pas apparaitre dans le chat : on enveloppe ChatFrame_OnEvent (appele une fois PAR fenetre de
-- chat, donc le traitement se fait ailleurs : cadre WowlheimEvents ci-dessous). Voir docs/CLIENT_FEASIBILITY.md.
WL.origChatOnEvent = ChatFrame_OnEvent;
ChatFrame_OnEvent = function(event)
	if ( event == "CHAT_MSG_SYSTEM" and arg1 and string.sub(arg1, 1, 4) == Core.PREFIX and not WL.debug ) then
		return;
	end
	WL.origChatOnEvent(event);
end

-- ------------------------------------------------------------------------------------------------
-- Actions du marteau
-- ------------------------------------------------------------------------------------------------
function WL.StartTargeting()
	if ( not WL.HammerEquipped() ) then
		WL.ShowMessage("Équipez le marteau (main droite) pour construire.", 1);
		WL.state.continuous = nil;
		WL.state.pending = nil;
		return;
	end
	if ( SpellIsTargeting() ) then
		SpellStopTargeting();
	end
	WL.state.pending = 1;
	-- fantome natif du client (DLL Wowlheim, docs/GHOST_PREVIEW.md) : le sort de pose invoque le GameObject
	-- de la piece choisie (9110000 + id) ; le client l'affiche sous le curseur pendant le ciblage au sol
	if ( WowlheimSetPlaceObject and WL.selected and WL.selected.id ) then
		WowlheimSetPlaceObject(9110000 + WL.selected.id);
	end
	UseInventoryItem(Core.HAMMER_SLOT);
end

function WL.ChooseEntry(e)
	WL.selected = e;
	WL.relaunchAt = nil;
	if ( e.special ) then
		if ( SpellIsTargeting() ) then SpellStopTargeting(); end
		WL.SendAll(Core.ChooseMode(WL.state, e.special));
		if ( e.special == "repair" ) then
			WL.ShowMessage("Réparer : clic droit sur une construction.");
		else
			WL.ShowMessage("Démolir : clic droit sur une construction.");
		end
	else
		if ( not WL.EntryAffordable(e) ) then
			WL.ShowMessage("Ressources insuffisantes.", 1);
		end
		local cmds = Core.ChoosePiece(WL.state, e.id);
		WL.SendAll(cmds);
		WL.StartTargeting();
	end
	WL.Update();
end

function WL.Cancel()
	WL.relaunchAt = nil;
	if ( SpellIsTargeting() ) then SpellStopTargeting(); end
	WL.SendAll(Core.Cancel(WL.state));
	WL.selected = nil;
	if ( WL.frame ) then WL.Update(); end
end

function WL.Rotate(delta)
	WL.SendAll(Core.Rotate(WL.state, delta));
	WL.UpdateInfo();
end

function WL.Relaunch()
	WL.relaunchAt = nil;
	local st = WL.state;
	if ( not (st.continuous and st.mode == "build" and st.piece) ) then return; end
	if ( WL.selected and not WL.selected.special and not WL.EntryAffordable(WL.selected) ) then
		st.continuous = nil;
		WL.ShowMessage("Ressources insuffisantes pour reposer " .. WL.selected.name .. ".", 1);
		return;
	end
	WL.StartTargeting();
end

-- ------------------------------------------------------------------------------------------------
-- Construction du panneau
-- ------------------------------------------------------------------------------------------------
local function WoodBackdrop(f, edge)
	f:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
		tile = true, tileSize = 16, edgeSize = edge or 16, insets = { left = 4, right = 4, top = 4, bottom = 4 } });
	f:SetBackdropColor(BROWN_BG[1], BROWN_BG[2], BROWN_BG[3], BROWN_BG[4]);
	f:SetBackdropBorderColor(BROWN_EDGE[1], BROWN_EDGE[2], BROWN_EDGE[3], BROWN_EDGE[4]);
end

-- Texture de survol (couche HIGHLIGHT : affichee automatiquement au survol d'un Button)
local function AddHighlight(b, path)
	local h = b:CreateTexture(nil, "HIGHLIGHT");
	h:SetTexture(path);
	h:SetBlendMode("ADD");
	h:SetAllPoints(b);
end

local function OnWheel()
	if ( IsShiftKeyDown() ) then
		WL.SetScroll(WL.scroll - arg1);
	else
		WL.Rotate(arg1);
	end
end

local function EnableWheel(f)
	if ( f.EnableMouseWheel ) then f:EnableMouseWheel(1); end
	f:SetScript("OnMouseWheel", OnWheel);
end

function WL.BuildFrame()
	if ( WL.frame ) then return; end
	local width = WL.MARGIN * 2 + WL.COLS * WL.CELL + 22;
	local gridH = WL.ROWS * WL.CELL;
	local infoH = 112;
	local height = 12 + 26 + 6 + gridH + 8 + infoH + 22;

	local f = CreateFrame("Frame", "WowlheimFrame", UIParent);
	f:SetWidth(width); f:SetHeight(height);
	f:SetPoint("BOTTOM", UIParent, "BOTTOM", 0, 120);
	f:SetFrameStrata("MEDIUM");
	if ( f.SetToplevel ) then f:SetToplevel(1); end
	WoodBackdrop(f, 16);
	f:EnableMouse(1);
	f:SetMovable(1);
	f:RegisterForDrag("LeftButton");
	f:SetScript("OnDragStart", function() if ( IsShiftKeyDown() ) then this:StartMoving(); end end);
	f:SetScript("OnDragStop", function() this:StopMovingOrSizing(); end);
	f:SetScript("OnMouseUp", function() if ( arg1 == "RightButton" ) then WL.Cancel(); end end);
	f:SetScript("OnHide", function() WL.Cancel(); end);
	f:SetScript("OnShow", function() WL.RecountBags(); WL.Update(); end);
	EnableWheel(f);
	f:Hide();
	WL.frame = f;
	table.insert(UISpecialFrames, "WowlheimFrame");

	-- Onglets de categories
	WL.tabs = {};
	local ncat = table.getn(Data.categories);
	local tabW = (width - WL.MARGIN * 2) / ncat;
	local c = 1;
	while c <= ncat do
		local t = CreateFrame("Button", "WowlheimTab" .. c, f);
		t:SetWidth(tabW - 4); t:SetHeight(24);
		t:SetPoint("TOPLEFT", f, "TOPLEFT", WL.MARGIN + (c - 1) * tabW + 2, -12);
		WoodBackdrop(t, 12);
		t:SetID(c);
		local fs = t:CreateFontString("WowlheimTab" .. c .. "Text", "OVERLAY", "GameFontNormalSmall");
		fs:SetPoint("CENTER", t, "CENTER", 0, 0);
		fs:SetText(Data.categories[c]);
		t.label = fs;
		AddHighlight(t, "Interface\\Buttons\\UI-Listbox-Highlight2");
		t:RegisterForClicks("LeftButtonUp", "RightButtonUp");
		t:SetScript("OnClick", function()
			if ( arg1 == "RightButton" ) then WL.Cancel(); return; end
			WL.SetCategory(this:GetID());
		end);
		EnableWheel(t);
		WL.tabs[c] = t;
		c = c + 1;
	end

	-- Grille d'icones
	local gridTop = -(12 + 26 + 6);
	local grid = CreateFrame("Frame", "WowlheimGrid", f);
	grid:SetWidth(WL.COLS * WL.CELL); grid:SetHeight(gridH);
	grid:SetPoint("TOPLEFT", f, "TOPLEFT", WL.MARGIN, gridTop);
	WL.grid = grid;
	WL.buttons = {};
	local i = 1;
	while i <= WL.COLS * WL.ROWS do
		local col = math.mod(i - 1, WL.COLS);
		local row = math.floor((i - 1) / WL.COLS);
		local b = CreateFrame("Button", "WowlheimIcon" .. i, grid);
		b:SetWidth(WL.ICON); b:SetHeight(WL.ICON);
		b:SetPoint("TOPLEFT", grid, "TOPLEFT", col * WL.CELL + 2, -(row * WL.CELL + 2));
		b:SetID(i);
		local bg = b:CreateTexture("WowlheimIcon" .. i .. "Bg", "BACKGROUND");
		bg:SetTexture(0, 0, 0, 0.55);
		bg:SetPoint("TOPLEFT", b, "TOPLEFT", -2, 2);
		bg:SetPoint("BOTTOMRIGHT", b, "BOTTOMRIGHT", 2, -2);
		local tex = b:CreateTexture("WowlheimIcon" .. i .. "Icon", "ARTWORK");
		tex:SetAllPoints(b);
		b.icon = tex;
		local sel = b:CreateTexture("WowlheimIcon" .. i .. "Sel", "OVERLAY");
		sel:SetTexture("Interface\\Buttons\\UI-ActionButton-Border");
		sel:SetBlendMode("ADD");
		sel:SetVertexColor(ORANGE[1], ORANGE[2], ORANGE[3]);
		sel:SetWidth(WL.ICON * 1.8); sel:SetHeight(WL.ICON * 1.8);
		sel:SetPoint("CENTER", b, "CENTER", 0, 0);
		sel:Hide();
		b.sel = sel;
		AddHighlight(b, "Interface\\Buttons\\ButtonHilight-Square");
		b:RegisterForClicks("LeftButtonUp", "RightButtonUp");
		b:SetScript("OnClick", function()
			if ( arg1 == "RightButton" ) then WL.Cancel(); return; end
			if ( this.entry ) then WL.ChooseEntry(this.entry); end
		end);
		b:SetScript("OnEnter", function() WL.hover = this.entry; WL.UpdateInfo(); end);
		b:SetScript("OnLeave", function() WL.hover = nil; WL.UpdateInfo(); end);
		EnableWheel(b);
		WL.buttons[i] = b;
		i = i + 1;
	end

	-- Defilement (fleches a droite de la grille ; Maj + molette)
	local up = CreateFrame("Button", "WowlheimScrollUp", f);
	up:SetWidth(20); up:SetHeight(20);
	up:SetPoint("TOPLEFT", grid, "TOPRIGHT", 2, 0);
	up:SetNormalTexture("Interface\\Buttons\\UI-ScrollBar-ScrollUpButton-Up");
	up:SetPushedTexture("Interface\\Buttons\\UI-ScrollBar-ScrollUpButton-Down");
	up:SetDisabledTexture("Interface\\Buttons\\UI-ScrollBar-ScrollUpButton-Disabled");
	up:SetScript("OnClick", function() WL.SetScroll(WL.scroll - 1); end);
	WL.upButton = up;
	local down = CreateFrame("Button", "WowlheimScrollDown", f);
	down:SetWidth(20); down:SetHeight(20);
	down:SetPoint("BOTTOMLEFT", grid, "BOTTOMRIGHT", 2, 0);
	down:SetNormalTexture("Interface\\Buttons\\UI-ScrollBar-ScrollDownButton-Up");
	down:SetPushedTexture("Interface\\Buttons\\UI-ScrollBar-ScrollDownButton-Down");
	down:SetDisabledTexture("Interface\\Buttons\\UI-ScrollBar-ScrollDownButton-Disabled");
	down:SetScript("OnClick", function() WL.SetScroll(WL.scroll + 1); end);
	WL.downButton = down;

	-- Encadre de la piece (sous la grille, comme dans Valheim)
	local info = CreateFrame("Frame", "WowlheimInfo", f);
	info:SetWidth(width - WL.MARGIN * 2); info:SetHeight(infoH);
	info:SetPoint("TOPLEFT", grid, "BOTTOMLEFT", 0, -8);
	WoodBackdrop(info, 12);
	info:SetBackdropColor(0.10, 0.07, 0.04, 0.9);
	EnableWheel(info);
	WL.info = info;

	local bigIcon = info:CreateTexture("WowlheimInfoIcon", "ARTWORK");
	bigIcon:SetWidth(44); bigIcon:SetHeight(44);
	bigIcon:SetPoint("TOPLEFT", info, "TOPLEFT", 10, -10);
	WL.infoIcon = bigIcon;

	local name = info:CreateFontString("WowlheimInfoName", "OVERLAY", "GameFontNormalLarge");
	name:SetPoint("TOPLEFT", bigIcon, "TOPRIGHT", 8, 0);
	name:SetTextColor(ORANGE[1], ORANGE[2], ORANGE[3]);
	name:SetJustifyH("LEFT");
	WL.infoName = name;

	local desc = info:CreateFontString("WowlheimInfoDesc", "OVERLAY", "GameFontHighlightSmall");
	desc:SetPoint("TOPLEFT", name, "BOTTOMLEFT", 0, -4);
	desc:SetWidth(228); desc:SetHeight(58);
	desc:SetJustifyH("LEFT"); desc:SetJustifyV("TOP");
	WL.infoDesc = desc;

	local station = info:CreateFontString("WowlheimInfoStation", "OVERLAY", "GameFontNormalSmall");
	station:SetPoint("BOTTOMLEFT", info, "BOTTOMLEFT", 10, 8);
	station:SetJustifyH("LEFT");
	WL.infoStation = station;

	local rot = f:CreateFontString("WowlheimInfoRot", "OVERLAY", "GameFontHighlightSmall");
	rot:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -WL.MARGIN - 190, 8);
	rot:SetJustifyH("RIGHT");
	WL.infoRot = rot;

	-- Ressources requises : 2 colonnes x 3 lignes (icone + possede/requis)
	WL.costSlots = {};
	local s = 1;
	while s <= WL.COST_SLOTS do
		local cx = 300 + math.mod(s - 1, 2) * 85;
		local cy = -8 - math.floor((s - 1) / 2) * 32;
		local ic = info:CreateTexture("WowlheimCost" .. s .. "Icon", "ARTWORK");
		ic:SetWidth(28); ic:SetHeight(28);
		ic:SetPoint("TOPLEFT", info, "TOPLEFT", cx, cy);
		local txt = info:CreateFontString("WowlheimCost" .. s .. "Text", "OVERLAY", "NumberFontNormal");
		txt:SetPoint("LEFT", ic, "RIGHT", 4, 0);
		txt:SetJustifyH("LEFT");
		WL.costSlots[s] = { icon = ic, text = txt };
		s = s + 1;
	end

	-- Zone de message
	local msg = f:CreateFontString("WowlheimMsg", "OVERLAY", "GameFontHighlightSmall");
	msg:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", WL.MARGIN, 8);
	msg:SetWidth(width - WL.MARGIN * 2 - 300);
	msg:SetJustifyH("LEFT");
	WL.msgText = msg;

	local mode = f:CreateFontString("WowlheimMode", "OVERLAY", "GameFontNormalSmall");
	mode:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -WL.MARGIN, 8);
	mode:SetJustifyH("RIGHT");
	WL.modeText = mode;
end

-- ------------------------------------------------------------------------------------------------
-- Mise a jour
-- ------------------------------------------------------------------------------------------------
function WL.SetCategory(cat)
	WL.cat = cat;
	WL.scroll = 0;
	WL.hover = nil;
	if ( WowlheimDB ) then WowlheimDB.cat = cat; end
	WL.Update();
end

function WL.SetScroll(v)
	local max = Core.MaxScroll(WL.entries.n, WL.COLS, WL.ROWS);
	WL.scroll = Core.Clamp(v, 0, max);
	WL.UpdateGrid();
end

function WL.UpdateTabs()
	local c = 1;
	while WL.tabs[c] do
		local t = WL.tabs[c];
		if ( c == WL.cat ) then
			t.label:SetTextColor(ORANGE[1], ORANGE[2], ORANGE[3]);
			t:SetBackdropBorderColor(ORANGE[1], ORANGE[2], ORANGE[3], 1);
			t:SetBackdropColor(0.32, 0.20, 0.09, 0.95);
		else
			t.label:SetTextColor(0.75, 0.68, 0.55);
			t:SetBackdropBorderColor(BROWN_EDGE[1], BROWN_EDGE[2], BROWN_EDGE[3], BROWN_EDGE[4]);
			t:SetBackdropColor(BROWN_BG[1], BROWN_BG[2], BROWN_BG[3], BROWN_BG[4]);
		end
		c = c + 1;
	end
end

function WL.UpdateGrid()
	if ( not WL.frame ) then return; end
	local max = Core.MaxScroll(WL.entries.n, WL.COLS, WL.ROWS);
	WL.scroll = Core.Clamp(WL.scroll, 0, max);
	local first = WL.scroll * WL.COLS;
	local i = 1;
	while WL.buttons[i] do
		local b = WL.buttons[i];
		local e = WL.entries[first + i];
		if ( e ) then
			b.entry = e;
			WL.EntryIcon(b.icon, e);
			SetGrey(b.icon, not WL.EntryAffordable(e));
			if ( e == WL.selected ) then b.sel:Show(); else b.sel:Hide(); end
			b:Show();
		else
			b.entry = nil;
			b:Hide();
		end
		i = i + 1;
	end
	if ( max > 0 ) then
		WL.upButton:Show(); WL.downButton:Show();
		if ( WL.scroll > 0 ) then WL.upButton:Enable(); else WL.upButton:Disable(); end
		if ( WL.scroll < max ) then WL.downButton:Enable(); else WL.downButton:Disable(); end
	else
		WL.upButton:Hide(); WL.downButton:Hide();
	end
end

function WL.UpdateInfo()
	if ( not WL.frame ) then return; end
	local e = WL.hover or WL.selected;
	local s;
	if ( not e ) then
		WL.infoIcon:Hide();
		WL.infoName:SetText("Marteau");
		WL.infoDesc:SetText("Choisissez une construction. Clic gauche : poser (cliquez au sol). Molette : tourner. Clic droit / Échap : annuler.");
		WL.infoStation:SetText("");
		s = 1;
		while WL.costSlots[s] do
			WL.costSlots[s].icon:Hide(); WL.costSlots[s].text:SetText("");
			s = s + 1;
		end
	else
		WL.infoIcon:Show();
		WL.EntryIcon(WL.infoIcon, e);
		SetGrey(WL.infoIcon, not WL.EntryAffordable(e));
		WL.infoName:SetText(e.name);
		WL.infoDesc:SetText(e.desc or "");
		if ( e.station and e.station ~= "" ) then
			local sname = Data.stations[e.station] or e.station;
			WL.infoStation:SetText("Requiert : " .. sname);
		else
			WL.infoStation:SetText("");
		end
		local ok, rows = Core.Affordability(e.costs, WL.counts);
		s = 1;
		while WL.costSlots[s] do
			local slot = WL.costSlots[s];
			local r = rows[s];
			if ( r ) then
				slot.icon:SetTexture(WL.ItemIcon(r.item));
				slot.icon:Show();
				local color = "|cffffffff";
				if ( not r.ok ) then color = "|cffff3030"; end
				slot.text:SetText(color .. r.have .. "/" .. r.need .. "|r");
			else
				slot.icon:Hide();
				slot.text:SetText("");
			end
			s = s + 1;
		end
	end
	WL.infoRot:SetText("Rotation : " .. Core.RotDegrees(WL.state.rot) .. "°");
	local mode = "Construction";
	if ( WL.state.mode == "repair" ) then mode = "|cff40ff40Réparer|r";
	elseif ( WL.state.mode == "remove" ) then mode = "|cffff4040Démolir|r"; end
	if ( WL.state.continuous ) then mode = mode .. " (pose continue)"; end
	WL.modeText:SetText(mode);
end

function WL.Update()
	if ( not WL.frame ) then return; end
	WL.entries = Core.CategoryEntries(Data.pieces, WL.cat);
	WL.UpdateTabs();
	WL.UpdateGrid();
	WL.UpdateInfo();
end

function WL.Show()
	WL.BuildFrame();
	WL.frame:Show();
end

function WL.Hide()
	if ( WL.frame ) then WL.frame:Hide(); end
end

function WL.Toggle()
	WL.BuildFrame();
	if ( WL.frame:IsVisible() ) then
		WL.frame:Hide();
	else
		WL.frame:Show();
	end
end

-- ------------------------------------------------------------------------------------------------
-- Raccourcis (Bindings.xml) et commande /wl
-- ------------------------------------------------------------------------------------------------
BINDING_HEADER_WOWLHEIM = "Wowlheim";
BINDING_NAME_WOWLHEIM_TOGGLE = "Wowlheim : menu du marteau";
BINDING_NAME_WOWLHEIM_ROTATE_LEFT = "Wowlheim : tourner à gauche";
BINDING_NAME_WOWLHEIM_ROTATE_RIGHT = "Wowlheim : tourner à droite";

SLASH_WOWLHEIM1 = "/wl";
SLASH_WOWLHEIM2 = "/wowlheim";
SlashCmdList["WOWLHEIM"] = function(msg)
	if ( msg == "debug" ) then
		if ( WL.debug ) then WL.debug = nil; else WL.debug = 1; end
		local state = "OFF";
		if ( WL.debug ) then state = "ON"; end
		DEFAULT_CHAT_FRAME:AddMessage("Wowlheim debug " .. state .. " (les lignes [WL] du serveur restent visibles dans le chat)");
		return;
	end
	WL.Toggle();
end

-- ------------------------------------------------------------------------------------------------
-- Evenements : marteau equipe, sacs, messages serveur, relance de la pose continue
-- ------------------------------------------------------------------------------------------------
function WL.CheckHammer()
	local eq = WL.HammerEquipped();
	if ( eq and not WL.hammerWasEquipped ) then
		WL.Show();
	elseif ( not eq and WL.hammerWasEquipped ) then
		WL.Hide();
	end
	WL.hammerWasEquipped = eq;
end

local ef = CreateFrame("Frame", "WowlheimEvents", UIParent);
ef:RegisterEvent("VARIABLES_LOADED");
ef:RegisterEvent("PLAYER_ENTERING_WORLD");
ef:RegisterEvent("UNIT_INVENTORY_CHANGED");
ef:RegisterEvent("BAG_UPDATE");
ef:RegisterEvent("CHAT_MSG_SYSTEM");
ef:SetScript("OnEvent", function()
	if ( event == "CHAT_MSG_SYSTEM" ) then
		if ( arg1 and string.sub(arg1, 1, 4) == Core.PREFIX ) then
			WL.OnSystem(arg1);
		end
	elseif ( event == "BAG_UPDATE" ) then
		WL.bagsDirty = 1;
	elseif ( event == "VARIABLES_LOADED" ) then
		if ( not WowlheimDB ) then WowlheimDB = {}; end
		if ( WowlheimDB.cat and Data.categories[WowlheimDB.cat] ) then WL.cat = WowlheimDB.cat; end
	elseif ( event == "PLAYER_ENTERING_WORLD" ) then
		WL.bagsDirty = 1;
		WL.CheckHammer();
	elseif ( event == "UNIT_INVENTORY_CHANGED" and arg1 == "player" ) then
		WL.CheckHammer();
	end
end);
ef:SetScript("OnUpdate", function()
	if ( WL.bagsDirty ) then
		WL.RecountBags();
		if ( WL.frame and WL.frame:IsVisible() ) then
			WL.UpdateGrid();
			WL.UpdateInfo();
		end
	end
	if ( WL.relaunchAt and GetTime() >= WL.relaunchAt ) then
		local start, duration = GetInventoryItemCooldown("player", Core.HAMMER_SLOT);
		local t = Core.RelaunchTime(GetTime(), start, duration, 0);
		if ( t > GetTime() ) then
			WL.relaunchAt = t;
		else
			WL.Relaunch();
		end
	end
end);
