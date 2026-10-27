-- WowlheimSkills.lua : endurance « outils » et competences facon Valheim (client 1.12.1, Lua 5.0).
-- JAMAIS CHARGE EN JEU a ce jour : syntaxe et logique verifiees hors du jeu seulement (tools/client/addon/test_core.py).
-- Logique pure (lignes EN| SK| SKU| SKL|, regeneration, visibilite) : WowlheimCore.lua. Regles : docs/VALHEIM_SKILLS.md.
--
-- Barre d'endurance (Hud de Valheim) : barre jaune fine en haut au centre, juste au-dessus du bandeau de pose ; affichee
--   seulement avec un marteau, une hache ou une pioche Valheim en main, ou pendant la regeneration ; clignote quand le
--   serveur refuse un coup faute d'endurance (EN|...|1). L'endurance de WoW (course) n'est pas concernee.
-- Panneau Competences (Maj+K, /wl skills) : Haches, Pioches, Bucheronnage, Fabrication ; niveau et progression.
-- Message de montee de niveau au centre de l'ecran : « Competence amelioree » / « Bucheronnage niveau 2 ».

local WL = Wowlheim;
local Core = WowlheimCore;

WL.Skills = {};
local SK = WL.Skills;

SK.stamina = Core.NewStamina();
SK.state = Core.NewSkills();
SK.ROW_H = 34;
SK.MSG_TIME = 3;          -- s : duree d'affichage du message de montee de niveau (fondu sur la derniere seconde)

-- ------------------------------------------------------------------------------------------------
-- Barre d'endurance
-- ------------------------------------------------------------------------------------------------
function SK.ToolEquipped()
	local link = GetInventoryItemLink("player", Core.HAMMER_SLOT);
	return link and Core.IsToolId(Core.ItemIdFromLink(link));
end

function SK.BuildBar()
	if ( SK.bar ) then return; end
	local d = Core.STAMINA_BAR;
	local bar = CreateFrame("StatusBar", "WowlheimStaminaBar", UIParent);
	bar:SetWidth(d.w); bar:SetHeight(d.h);
	bar:SetPoint("TOP", UIParent, "TOP", 0, -d.top);
	bar:SetFrameStrata("HIGH");
	bar:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar");
	bar:SetStatusBarColor(1.0, 0.82, 0.10);         -- jaune (endurance de Valheim)
	bar:SetMinMaxValues(0, 1);
	bar:SetValue(1);
	local bg = bar:CreateTexture("WowlheimStaminaBarBg", "BACKGROUND");
	bg:SetTexture(0, 0, 0, 0.55);
	bg:SetAllPoints(bar);
	bar:Hide();
	SK.bar = bar;
end

function SK.UpdateBar(now)
	SK.BuildBar();
	local sa = SK.stamina;
	if ( not Core.StaminaBarVisible(sa, now, SK.ToolEquipped()) ) then
		SK.bar:Hide();
		SK.barShown = nil;
		return;
	end
	local frac = 0;
	if ( sa.max > 0 ) then frac = Core.StaminaNow(sa, now) / sa.max; end
	SK.bar:SetValue(frac);
	SK.barValue = frac;
	local a = Core.StaminaFlashAlpha(sa, now);
	SK.bar:SetAlpha(a);
	if ( a < 1 ) then SK.bar:SetStatusBarColor(1.0, 0.25, 0.10); else SK.bar:SetStatusBarColor(1.0, 0.82, 0.10); end
	SK.bar:Show();
	SK.barShown = 1;
end

-- ------------------------------------------------------------------------------------------------
-- Message de montee de niveau (Valheim : MessageHud, $msg_skillup)
-- ------------------------------------------------------------------------------------------------
function SK.ShowMessage(title, text)
	if ( not SK.msg ) then
		local f = CreateFrame("Frame", "WowlheimSkillMsg", UIParent);
		f:SetWidth(420); f:SetHeight(50);
		f:SetPoint("CENTER", UIParent, "CENTER", 0, 170);
		f:SetFrameStrata("HIGH");
		local t1 = WL.Label(f, "WowlheimSkillMsgTitle", "GameFontNormal", 420, 16, "CENTER", "MIDDLE");
		t1:SetPoint("TOP", f, "TOP", 0, 0);
		t1:SetTextColor(WL.ORANGE[1], WL.ORANGE[2], WL.ORANGE[3]);
		local t2 = WL.Label(f, "WowlheimSkillMsgText", "GameFontHighlightLarge", 420, 24, "CENTER", "MIDDLE");
		t2:SetPoint("TOP", t1, "BOTTOM", 0, -4);
		f.title = t1;
		f.text = t2;
		SK.msg = f;
	end
	SK.msg.title:SetText(title);
	SK.msg.text:SetText(text);
	SK.msg:SetAlpha(1);
	SK.msg:Show();
	SK.msgAt = GetTime();
	SK.lastMessage = text;
end

function SK.UpdateMessage(now)
	if ( not SK.msg or not SK.msgAt ) then return; end
	local t = now - SK.msgAt;
	if ( t >= SK.MSG_TIME ) then
		SK.msg:Hide();
		SK.msgAt = nil;
	elseif ( t > SK.MSG_TIME - 1 ) then
		SK.msg:SetAlpha(SK.MSG_TIME - t);
	end
end

-- ------------------------------------------------------------------------------------------------
-- Panneau des competences
-- ------------------------------------------------------------------------------------------------
function SK.Build()
	if ( SK.frame ) then return; end
	local p = Core.PANELS.skills;
	-- 260 x 192, marges 16 partout : titre (ligne de 24, a cote de la fermeture) puis 4 lignes de 30 tous les 34 a partir de 44
	-- (derniere ligne finie a 176, 16 du bas) ; colonnes : icone 28 | nom + barre a 36 | niveau aligne a droite sous la fermeture
	local M = 16;
	local RW = p.w - M * 2;                                     -- 228
	local f = WL.NewPanel("WowlheimSkillsFrame", p.w, p.h, "skills");
	local title = WL.Label(f, "WowlheimSkillsTitle", "GameFontNormalLarge", RW - 24 - 8, 24, "LEFT", "MIDDLE");
	title:SetPoint("TOPLEFT", f, "TOPLEFT", M, -12);
	title:SetText("Compétences");
	title:SetTextColor(WL.ORANGE[1], WL.ORANGE[2], WL.ORANGE[3]);
	WL.CloseButton("WowlheimSkillsClose", f, f);
	SK.rows = {};
	local i = 1;
	while i <= Core.SKILLS.n do
		local d = Core.SKILLS[i];
		local row = CreateFrame("Frame", "WowlheimSkillRow" .. i, f);
		row:SetWidth(RW); row:SetHeight(SK.ROW_H - 4);
		row:SetPoint("TOPLEFT", f, "TOPLEFT", M, -44 - (i - 1) * SK.ROW_H);
		row:EnableMouse(1);
		local icon = row:CreateTexture("WowlheimSkillRow" .. i .. "Icon", "ARTWORK");
		icon:SetWidth(28); icon:SetHeight(28);
		icon:SetPoint("LEFT", row, "LEFT", 0, 0);
		if ( not icon:SetTexture("Interface\\Icons\\" .. d.icon) ) then icon:SetTexture("Interface\\Icons\\INV_Misc_QuestionMark"); end
		-- nom a gauche (zone bornee), niveau a droite (zone de 32 alignee a droite), barre de progression dessous
		local name = WL.Label(row, "WowlheimSkillRow" .. i .. "Name", "GameFontNormal", RW - 36 - 32 - 8, 14, "LEFT", "MIDDLE");
		name:SetPoint("TOPLEFT", row, "TOPLEFT", 36, -2);
		name:SetText(d.name);
		local lvl = WL.Label(row, "WowlheimSkillRow" .. i .. "Level", "GameFontHighlight", 32, 14, "RIGHT", "MIDDLE");
		lvl:SetPoint("TOPRIGHT", row, "TOPRIGHT", 0, -2);
		local bar = WL.Bar("WowlheimSkillRow" .. i .. "Bar", row, RW - 36, 8, 1.0, 0.68, 0.22);
		bar:SetPoint("BOTTOMLEFT", row, "BOTTOMLEFT", 36, 2);
		row.desc = d.desc;
		row.skillName = d.name;
		row:SetScript("OnEnter", function()
			if ( GameTooltip ) then
				GameTooltip:SetOwner(this, "ANCHOR_RIGHT");
				GameTooltip:SetText(this.skillName);
				GameTooltip:AddLine(this.desc, 1, 1, 1, 1);
				GameTooltip:Show();
			end
		end);
		row:SetScript("OnLeave", function() if ( GameTooltip ) then GameTooltip:Hide(); end end);
		row.level = lvl;
		row.bar = bar;
		SK.rows[i] = row;
		i = i + 1;
	end
	f:SetScript("OnShow", function() SK.Request(); SK.Update(); end);
	SK.frame = f;
end

function SK.Update()
	if ( not SK.frame ) then return; end
	local i = 1;
	while i <= Core.SKILLS.n do
		local r = Core.SkillRow(SK.state, i);
		SK.rows[i].level:SetText(tostring(r.level));
		WL.SetBar(SK.rows[i].bar, r.pct, "");
		i = i + 1;
	end
end

function SK.Request()
	if ( not Core.ChannelHas(WL.channel, "skills") ) then
		WL.Send(Core.SkillsCommand(), 1);
	end
end

function SK.Show() SK.Build(); SK.frame:Show(); end
function SK.Hide() if ( SK.frame ) then SK.frame:Hide(); end end
function SK.Toggle()
	SK.Build();
	if ( SK.frame:IsVisible() ) then SK.frame:Hide(); else SK.frame:Show(); end
end

-- ------------------------------------------------------------------------------------------------
-- Branchements (appeles par Wowlheim.lua : OnSystem, entree en jeu, OnUpdate)
-- ------------------------------------------------------------------------------------------------
function SK.OnMessage(m)
	local now = GetTime();
	if ( Core.StaminaOnMessage(SK.stamina, m, now) ) then
		SK.UpdateBar(now);
		return;
	end
	local ev, text = Core.SkillsOnMessage(SK.state, m);
	if ( ev == "levelup" ) then
		SK.ShowMessage(Core.SKILL_UP_TITLE, text);
	elseif ( ev == "lowered" ) then
		SK.ShowMessage(text, "");
	end
	if ( ev ) then SK.Update(); end
end

function SK.OnEnterWorld()
	SK.Request();
end

function SK.OnUpdate(now)
	SK.UpdateBar(now);
	SK.UpdateMessage(now);
end
