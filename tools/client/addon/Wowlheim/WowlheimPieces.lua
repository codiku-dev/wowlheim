-- WowlheimPieces.lua : coffres facon Valheim (composant Container ; serveur : server/Wowlheim/Pieces.cpp) — client 1.12.1, Lua 5.0.
-- JAMAIS CHARGE EN JEU a ce jour : syntaxe et logique verifiees hors du jeu seulement (tools/client/addon/test_core.py).
--
-- Clic droit sur un coffre pose (sans marteau, ou marteau en mode construction) : le serveur envoie le contenu puis
-- OPEN|chest|guid ; le panneau « coffre » s'ouvre : grille m_width x m_height de Valheim (Coffre 5 x 2, Coffre renforce 6 x 4,
-- Coffre personnel 3 x 2, Coffre en sombracier 8 x 4).
--   * clic sur une case du coffre = la reprendre dans les sacs (.build api chest take <guid> <case>) ;
--   * clic droit sur un objet des sacs pendant que le coffre est ouvert = le deposer (.build api chest put <guid> <sac> <case>),
--     comme a la banque de WoW (ContainerFrameItemButton_OnClick enveloppee, fonction FrameXML non protegee en 1.12) ;
--   * « Prendre tout » (Container.TakeAll) et « Objets similaires » (Container.StackAll : depose ce que le coffre contient deja).
-- Fermeture (croix, Echap, eloignement signale par CX|) : .build api chest close <guid> (Container.SetInUse(false)).
-- Lignes du serveur :
--   CH|guid|nom|largeur|hauteur|privacy|cases occupees    debut du contenu
--   CI|guid|case|objet|nombre|durabilite|durabilite max   une case occupee (cases numerotees depuis 0)
--   CE|guid                                              fin du contenu
--   OPEN|chest|guid                                      ouvrir le panneau (clic sur le coffre)
--   CX|guid                                              trop loin : fermer le panneau

local WL = Wowlheim;
local Core = WowlheimCore;

WL.Chest = {};
local CH = WL.Chest;

CH.COLS_MAX = 8;          -- coffre en sombracier : 8 x 4 ; grille construite pour 8 x 5 (piece_chest_grausten)
CH.ROWS_MAX = 5;
CH.SLOT = 40;             -- pas de la grille (case 36 + 4)
CH.M = 16;
CH.HEAD_H = 28;
CH.BOTTOM_H = 24;
CH.W = CH.M * 2 + CH.COLS_MAX * CH.SLOT;                                        -- 352
CH.H = 12 + CH.HEAD_H + 8 + CH.ROWS_MAX * CH.SLOT + 8 + CH.BOTTOM_H + 12;       -- 292
Core.PANELS.chest = { w = CH.W, h = CH.H, scale = 0.85 };

-- ------------------------------------------------------------------------------------------------
-- Logique (sans interface) : etat du coffre ouvert d'apres les lignes [WL]
-- ------------------------------------------------------------------------------------------------
function CH.NewState()
	return { guid = nil, name = "", w = 0, h = 0, privacy = 2, slots = {}, pending = nil, complete = nil };
end
CH.state = CH.NewState();

-- Une ligne [WL]... : renvoie "open", "update", "close" ou nil (ligne d'un autre module)
function CH.OnLine(st, line)
	if ( not line or string.sub(line, 1, 4) ~= Core.PREFIX ) then return nil; end
	local f = Core.Split(string.sub(line, 5), "|");
	local t = f[1];
	if ( t == "CH" ) then
		-- debut d'un contenu : remplace l'etat a la fin (CE|), pour ne jamais afficher un coffre a moitie recu
		st.pending = { guid = tonumber(f[2]), name = f[3] or "", w = tonumber(f[4]) or 0, h = tonumber(f[5]) or 0,
			privacy = tonumber(f[6]) or 2, slots = {} };
		return nil;
	elseif ( t == "CI" ) then
		local p = st.pending;
		if ( p and p.guid == tonumber(f[2]) ) then
			p.slots[tonumber(f[3])] = { item = tonumber(f[4]), count = tonumber(f[5]) or 1, dur = tonumber(f[6]) or 0, maxDur = tonumber(f[7]) or 0 };
		end
		return nil;
	elseif ( t == "CE" ) then
		local p = st.pending;
		if ( not p or p.guid ~= tonumber(f[2]) ) then return nil; end
		st.pending = nil;
		local same = (st.guid == p.guid);
		st.guid = p.guid; st.name = p.name; st.w = p.w; st.h = p.h; st.privacy = p.privacy; st.slots = p.slots;
		st.complete = 1;
		if ( same ) then return "update"; end
		return "content";
	elseif ( t == "OPEN" and f[2] == "chest" ) then
		if ( st.guid == tonumber(f[3]) ) then return "open"; end
		return nil;
	elseif ( t == "CX" ) then
		if ( st.guid and st.guid == tonumber(f[2]) ) then return "close"; end
	end
	return nil;
end

-- Commandes envoyees au serveur (texte exact)
function CH.TakeCommand(st, slot) return ".build api chest take " .. st.guid .. " " .. slot; end
function CH.PutCommand(st, bag, slot) return ".build api chest put " .. st.guid .. " " .. bag .. " " .. slot; end
function CH.CloseCommand(st) return ".build api chest close " .. st.guid; end

-- Case (0..w*h-1) de la grille affichee (ligne, colonne depuis 1) ; nil hors du coffre
function CH.SlotIndex(st, row, col)
	if ( row < 1 or col < 1 or row > st.h or col > st.w ) then return nil; end
	return (row - 1) * st.w + (col - 1);
end

-- ------------------------------------------------------------------------------------------------
-- Interface
-- ------------------------------------------------------------------------------------------------
local function WoodBtn(name, parent, w, h, label, onClick)
	local b = CreateFrame("Button", name, parent);
	b:SetWidth(w); b:SetHeight(h);
	WL.WoodBackdrop(b, 12);
	b:SetBackdropColor(0.30, 0.19, 0.09, 0.95);
	local fs = WL.Label(b, name .. "Text", "GameFontNormal", w - 10, 14, "CENTER", "MIDDLE");
	fs:SetPoint("CENTER", b, "CENTER", 0, 0);
	fs:SetText(label);
	b.label = fs;
	WL.AddHighlight(b, "Interface\\Buttons\\UI-Listbox-Highlight2");
	b:SetScript("OnClick", onClick);
	return b;
end

function CH.Build()
	if ( CH.frame ) then return; end
	local f = CreateFrame("Frame", "WowlheimChestFrame", UIParent);
	f:SetWidth(CH.W); f:SetHeight(CH.H);
	WL.PlacePanel(f, "chest");
	f:SetFrameStrata("MEDIUM");
	if ( f.SetToplevel ) then f:SetToplevel(1); end
	WL.WoodBackdrop(f, 16);
	f:EnableMouse(1);
	f:SetMovable(1);
	f:RegisterForDrag("LeftButton");
	f:SetScript("OnDragStart", function() this:StartMoving(); end);
	f:SetScript("OnDragStop", function() this:StopMovingOrSizing(); WL.SavePanel(this, "chest"); end);
	f:Hide();                 -- avant OnHide : un cadre neuf est visible, le cacher ici ne doit pas fermer le coffre cote serveur
	f:SetScript("OnHide", function() CH.OnHide(); end);
	table.insert(UISpecialFrames, "WowlheimChestFrame");
	CH.frame = f;

	local title = WL.Label(f, "WowlheimChestTitle", "GameFontNormalLarge", CH.W - 2 * CH.M - 32, CH.HEAD_H, "LEFT", "MIDDLE");
	title:SetPoint("TOPLEFT", f, "TOPLEFT", CH.M, -12);
	title:SetTextColor(WL.ORANGE[1], WL.ORANGE[2], WL.ORANGE[3]);
	CH.title = title;
	local close = WoodBtn("WowlheimChestClose", f, 24, 24, "x", function() CH.frame:Hide(); end);
	close:SetPoint("TOPRIGHT", f, "TOPRIGHT", -CH.M, -12);

	CH.buttons = {};
	local row = 1;
	while row <= CH.ROWS_MAX do
		local col = 1;
		while col <= CH.COLS_MAX do
			local i = (row - 1) * CH.COLS_MAX + col;
			local b = CreateFrame("Button", "WowlheimChestSlot" .. i, f);
			b:SetWidth(CH.SLOT - 4); b:SetHeight(CH.SLOT - 4);
			b:SetPoint("TOPLEFT", f, "TOPLEFT", CH.M + (col - 1) * CH.SLOT, -(12 + CH.HEAD_H + 8 + (row - 1) * CH.SLOT));
			WL.WoodBackdrop(b, 8);
			b:SetBackdropColor(0.06, 0.04, 0.02, 0.95);
			local ic = b:CreateTexture("WowlheimChestSlot" .. i .. "Icon", "ARTWORK");
			ic:SetWidth(CH.SLOT - 10); ic:SetHeight(CH.SLOT - 10);
			ic:SetPoint("CENTER", b, "CENTER", 0, 0);
			b.icon = ic;
			local n = WL.Label(b, "WowlheimChestSlot" .. i .. "Count", "NumberFontNormal", CH.SLOT - 8, 12, "RIGHT", "BOTTOM");
			n:SetPoint("BOTTOMRIGHT", b, "BOTTOMRIGHT", -3, 3);
			b.count = n;
			b.row = row; b.col = col;
			WL.AddHighlight(b, "Interface\\Buttons\\ButtonHilight-Square");
			if ( b.RegisterForClicks ) then b:RegisterForClicks("LeftButtonUp", "RightButtonUp"); end
			b:SetScript("OnClick", function() CH.OnSlotClick(this); end);
			b:SetScript("OnEnter", function() CH.OnSlotEnter(this); end);
			b:SetScript("OnLeave", function() WL.HideTooltip(); end);
			CH.buttons[i] = b;
			col = col + 1;
		end
		row = row + 1;
	end

	local by = -(12 + CH.HEAD_H + 8 + CH.ROWS_MAX * CH.SLOT + 8);
	local takeAll = WoodBtn("WowlheimChestTakeAll", f, 140, CH.BOTTOM_H, "Prendre tout", function()     -- $inventory_takeall
		if ( CH.state.guid ) then WL.Send(".build api chest takeall " .. CH.state.guid); end
	end);
	takeAll:SetPoint("TOPLEFT", f, "TOPLEFT", CH.M, by);
	local stack = WoodBtn("WowlheimChestStackAll", f, 160, CH.BOTTOM_H, "Objets similaires", function()   -- $inventory_stackall
		if ( CH.state.guid ) then WL.Send(".build api chest stackall " .. CH.state.guid); end
	end);
	stack:SetPoint("TOPRIGHT", f, "TOPRIGHT", -CH.M, by);
end

function CH.Update()
	if ( not CH.frame ) then return; end
	local st = CH.state;
	CH.title:SetText(st.name or "");
	local i = 1;
	while i <= CH.COLS_MAX * CH.ROWS_MAX do
		local b = CH.buttons[i];
		local idx = CH.SlotIndex(st, b.row, b.col);
		if ( idx ) then
			local s = st.slots[idx];
			b.slot = idx;
			if ( s ) then
				b.icon:SetTexture(WL.ItemIcon(s.item));
				b.icon:Show();
				if ( s.count > 1 ) then b.count:SetText(s.count); else b.count:SetText(""); end
			else
				b.icon:Hide();
				b.count:SetText("");
			end
			b:Show();
		else
			b.slot = nil;
			b:Hide();
		end
		i = i + 1;
	end
end

function CH.OnSlotClick(b)
	local st = CH.state;
	if ( not st.guid or not b.slot or not st.slots[b.slot] ) then return; end
	WL.Send(CH.TakeCommand(st, b.slot));
end

function CH.OnSlotEnter(b)
	local s = b.slot and CH.state.slots[b.slot];
	if ( not s ) then return; end
	local lines = { n = 1 };
	if ( s.maxDur and s.maxDur > 0 ) then lines[1] = "Durabilite " .. s.dur .. " / " .. s.maxDur; end
	WL.ShowTooltip(b, WL.ItemName(s.item), lines);
end

function CH.OnHide()
	WL.HideTooltip();
	if ( CH.state.guid and not CH.closing ) then WL.Send(CH.CloseCommand(CH.state), 1); end
	CH.state.guid = nil;
end

function CH.Show()
	CH.Build();
	CH.Update();
	CH.frame:Show();
end

-- Reponses du serveur : cadre a part (Wowlheim.lua n'est pas modifie ; WL.OnSystem affiche deja les M| / E|)
function CH.OnSystem(line)
	local ev = CH.OnLine(CH.state, line);
	if ( ev == "open" ) then
		CH.Show();
	elseif ( ev == "update" or ev == "content" ) then
		if ( CH.frame and CH.frame:IsVisible() ) then CH.Update(); end
	elseif ( ev == "close" ) then
		if ( CH.frame and CH.frame:IsVisible() ) then
			CH.closing = 1;
			CH.frame:Hide();
			CH.closing = nil;
		end
	end
end

local ev = CreateFrame("Frame", "WowlheimChestEvents", UIParent);
ev:RegisterEvent("CHAT_MSG_SYSTEM");
ev:SetScript("OnEvent", function()
	if ( event == "CHAT_MSG_SYSTEM" and arg1 and string.sub(arg1, 1, 4) == Core.PREFIX ) then
		CH.OnSystem(arg1);
	end
end);

-- Clic droit sur un objet des sacs, coffre ouvert : depot (comme la banque). Sinon comportement normal.
CH.origBagClick = ContainerFrameItemButton_OnClick;
ContainerFrameItemButton_OnClick = function(button, ignoreShift)
	if ( button == "RightButton" and CH.frame and CH.frame:IsVisible() and CH.state.guid and this and this.GetParent
			and not (IsShiftKeyDown and IsShiftKeyDown()) and not (IsControlKeyDown and IsControlKeyDown()) ) then
		local bag = this:GetParent():GetID();
		local slot = this:GetID();
		WL.Send(CH.PutCommand(CH.state, bag, slot));
		return;
	end
	if ( CH.origBagClick ) then CH.origBagClick(button, ignoreShift); end
end
