-- Wowlheim.lua : menu de construction du marteau, facon Valheim (client 1.12.1, Lua 5.0).
-- JAMAIS CHARGE EN JEU a ce jour : syntaxe et logique pure verifiees hors du jeu seulement (tools/client/addon/test_core.py).
-- Donnees : WowlheimData.lua (genere). Logique pure / protocole : WowlheimCore.lua.
--
-- Fonctionnement :
--   * equiper le Marteau (objet 9201100, main droite) ouvre le panneau ; le desequiper le ferme ; touche de bascule (Bindings.xml).
--   * clic gauche sur une piece = ".build api select <id> <rot>" puis UseInventoryItem(16) (ciblage au sol) ; apres chaque
--     pose (reussie ou refusee) le ciblage est relance automatiquement : la piece reste choisie (pose continue, Valheim).
--   * Valheim : choisir une piece (ou Reparer / Demolir) MASQUE le menu pendant la pose ; un rappel « Mur  -  Rotation : 0° »
--     s'affiche en haut de l'ecran.
--   * controles du mode construction (docs/BUILD_CONTROLS.md), marteau equipe en mode construction : clic gauche = poser ;
--     clic droit = menu (le client annule le ciblage au sol ; l'addon detecte « ciblage termine sans pose » et ouvre le menu,
--     sans toucher a TurnOrActionStart, action protegee) ; clic milieu = demolir la piece sous la souris
--     (WowlheimGetMouseoverObject -> ".build api removeguid <guid>") ; molette = tourner. Liaisons TEMPORAIRES BUTTON3 /
--     MOUSEWHEELUP / MOUSEWHEELDOWN (SetBinding sans SaveBindings), retablies au rangement du marteau, en Demolir / Reparer,
--     a la sortie du monde (deconnexion, /reload) ; memorisees dans WowlheimDB.tempBinds (retablies a l'entree si besoin).
--   * molette sur le panneau (ou touches liees) = rotation par pas de 22,5 degres ; Maj + molette = defilement de la grille.
--   * Divers commence par Reparer / Demolir (".build api mode repair|remove", puis clic droit sur la piece posee en jeu).
--   * champ de recherche sous les onglets (nom / description, sans accents ni casse) : resultats de toutes les categories.
--   * pieces connues (Valheim) : ".build api known" ; une piece dont un materiau ou la station est inconnu est cachee.

Wowlheim = {};
local WL = Wowlheim;
local Core = WowlheimCore;
local Data = WowlheimData;

WL.COLS = 10;
WL.ROWS = 4;
WL.ICON = 40;
WL.CELL = 44;
-- Mise en page du menu du marteau (pas de 8 px ; Core.PANELS.hammer = taille construite, verifiee par test_core.py) :
--   12 haut | onglets 24 | 8 | recherche + rotation / mode 20 | 8 | grille 4 x 44 | 8 | encadre 112 | 8 | message 16 | 8 bas
--   16 gauche | grille 10 x 44 | 4 | fleches 20 | 16 droite
WL.MARGIN = 16;
WL.GAP = 8;
WL.TOP = 12;
WL.TAB_H = 24;
WL.CLOSE = 24;
WL.SCROLL_W = 24;                -- 4 d'ecart + fleches de 20
WL.INFO_H = 112;
WL.MSG_H = 16;
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
WL.channel = Core.NewChannel();  -- commandes envoyees en attente de leur D| (WowlheimCore : ChannelRoute)
WL.countsVersion = 0;            -- incremente a chaque recomptage des sacs (panneaux de fabrication / fonderie)
WL.rings = Core.NewRings();      -- cercles de portee des stations (marteau en mode construction)
WL.ringCount = 0;                -- marqueurs de la DLL actuellement poses (ids 0 .. ringCount-1)
WL.ringPollAt = 0;
WL.SEARCH_H = 20;                -- ligne du champ de recherche (a gauche) et de la rotation / du mode (a droite)
WL.SEARCH_Y = WL.TOP + WL.TAB_H + WL.GAP;                 -- 44
WL.GRID_Y = WL.SEARCH_Y + WL.SEARCH_H + WL.GAP;           -- 72
WL.query = "";                   -- recherche du menu du marteau (toutes categories pendant une recherche)
WL.known = Core.NewKnown();      -- objets / stations connus (.build api known) : pieces inconnues cachees
WL.knownAt = 0;
WL.tw = Core.NewTargetWatch();   -- detection du clic droit (« ciblage termine sans pose ») : WowlheimCore.TargetWatch*
WL.tempBinds = {};               -- liaisons temporaires du mode construction : { touche = action precedente }
WL.buildKeysOn = nil;            -- liaisons temporaires posees
WL.models = Core.NewModels();    -- chemins des modeles des pieces (.build api models) pour WowlheimPreloadModel
WL.preloadDone = {};             -- chemins deja precharges (remis a zero a chaque entree dans le monde : la DLL libere tout)
WL.preloadQueue = nil;
WL.gc = Core.NewGhostCheck();    -- verdict du serveur pour la couleur du fantome (.build api canplace)
WL.ghostTint = nil;              -- couleur posee sur le fantome natif ("valid" / "invalid" / "hidden"), nil = aucune teinte
WL.snapGhost = nil;              -- fantome DLL au point accroche : { path, tint } (nil = masque ; docs/GHOST_PREVIEW.md)
WL.modelsAskAt = -100;
WL.pi = Core.NewPieceInfo();     -- etat de la piece visee (.build api pieceinfo) : couleur du support, sante

-- Couleurs « bois » de Valheim
local ORANGE = { 1.0, 0.68, 0.22 };
local BROWN_BG = { 0.16, 0.11, 0.07, 0.94 };
local BROWN_EDGE = { 0.55, 0.40, 0.22, 1 };

-- ------------------------------------------------------------------------------------------------
-- Utilitaires
-- ------------------------------------------------------------------------------------------------
-- silent : rafraichissement automatique, ses lignes M| ne sont pas affichees
function WL.Send(command, silent)
	Core.ChannelPush(WL.channel, command, silent, GetTime());
	SendChatMessage(command, "SAY");
end

function WL.SendAll(cmds, silent)
	local i = 1;
	while i <= cmds.n do
		WL.Send(cmds[i], silent);
		i = i + 1;
	end
end

-- Texte au centre de l'ecran (UIErrorsFrame) : un meme texte au plus une fois par seconde (Core.DedupPass), toutes
-- sources confondues. isError : rouge ; sinon jaune (annonces).
WL.screenDedup = Core.NewDedup();
function WL.ScreenMessage(text, isError)
	if ( not Core.DedupPass(WL.screenDedup, text, GetTime()) ) then return; end
	if ( isError ) then
		UIErrorsFrame:AddMessage(text, 1.0, 0.1, 0.1, 1.0);
	else
		UIErrorsFrame:AddMessage(text, 1.0, 0.82, 0.0, 1.0);
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

-- Ressources manquantes : icone assombrie et teintee de rouge, en COULEUR. SetDesaturated(1) donnait en jeu une
-- forme gris clair illisible (la teinte de SetVertexColor n'est pas appliquee a une texture desaturee) : Table de
-- fabrication « grise » dans le menu du marteau (capture 14_placed_instant, 2026-10-26).
local function SetGrey(tex, grey)
	if ( tex.SetDesaturated ) then
		tex:SetDesaturated(nil);
	end
	if ( grey ) then
		tex:SetVertexColor(0.8, 0.5, 0.5);
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
	WL.countsVersion = WL.countsVersion + 1;
end

-- ------------------------------------------------------------------------------------------------
-- Pieces / recettes connues (Valheim) : interrogation silencieuse « .build api known » a l'ouverture du menu ou du panneau
-- de fabrication, et apres BAG_UPDATE (au plus une par Core.KNOWN_POLL s, panneau ouvert). Sans reponse : tout est affiche.
-- ------------------------------------------------------------------------------------------------
function WL.RequestKnown()
	local now = GetTime();
	Core.ChannelRoute(WL.channel, nil, now);       -- oublie une interrogation restee sans reponse
	if ( Core.ChannelHas(WL.channel, "known") ) then return; end
	WL.knownDirty = nil;
	WL.knownForce = nil;
	WL.knownAt = now;
	WL.Send(Core.KnownCommand(), 1);
end

function WL.PanelsShown()
	return (WL.frame and WL.frame:IsVisible()) or (WL.Craft and WL.Craft.IsShown and WL.Craft.IsShown());
end

-- Stations a portee (cercles de portee + lignes S| du panneau de fabrication) : connues localement
function WL.NearStations()
	local near = {};
	local i = 1;
	while WL.rings.stations[i] do
		near[WL.rings.stations[i].kind] = true;
		i = i + 1;
	end
	if ( WL.Craft and WL.Craft.state ) then Core.NearStations(WL.Craft.state.station, near); end
	return near;
end

-- Valheim (MessageHud.QueueUnlockMsg) : « Nouvelle pièce de construction : Feu de camp », « Nouvelle recette : Marteau »
-- quand une connaissance en debloque (premier nom, + n autres). Noms des recettes : WowlheimData.recipes (genere), meme
-- si le panneau de fabrication n'a jamais ete ouvert (KR| ne donne que des identifiants).
function WL.AnnounceKnown()
	local craftRecipes = WL.Craft and WL.Craft.state and WL.Craft.state.recipes;
	local a = Core.KnownAnnouncements(WL.known, Data.pieces, Data.recipes, craftRecipes, Data.items);
	if ( a.piece ) then WL.ShowMessage(a.piece); end
	if ( a.recipe ) then
		if ( WL.Craft and WL.Craft.IsShown() ) then WL.Craft.Message(a.recipe); else WL.ScreenMessage(a.recipe); end
	end
end

-- KN| : premier ramassage d'un objet (« Nouveau matériau : Bois », « Nouvel objet : Marteau »), station decouverte
-- (« Nouvel établi : Table de fabrication ») ou amelioree (Knowledge.cpp : LearnItem / LearnStationLevel)
function WL.AnnounceLearned(m)
	local txt = Core.LearnedText(m, Data.items, Data.stations);
	if ( txt ) then WL.ShowMessage(txt); end
end

function WL.OnKnown()
	if ( WL.frame and WL.frame:IsVisible() ) then WL.Update(); end
	if ( WL.Craft and WL.Craft.IsShown() ) then WL.Craft.Update(); end
end

function WL.EntryAffordable(e)
	if ( e.special ) then return true; end
	local ok = Core.Affordability(e.costs, WL.counts);
	return ok;
end

-- ------------------------------------------------------------------------------------------------
-- Messages
-- ------------------------------------------------------------------------------------------------
-- Un seul affichage par message : dans le panneau du marteau s'il est ouvert, sinon dans UIErrorsFrame. notified : le
-- serveur a deja affiche ce texte (notification, UIErrorsFrame) : ne pas le recopier dans UIErrorsFrame.
function WL.ShowMessage(text, isError, notified)
	if ( WL.frame and WL.frame:IsVisible() ) then
		if ( isError ) then
			WL.msgText:SetText("|cffff4040" .. text .. "|r");
		else
			WL.msgText:SetText(text);
		end
	elseif ( notified ) then
		-- deja a l'ecran (notification du serveur)
	else
		WL.ScreenMessage(text, isError);
	end
end

WL.notify = Core.NewNotify();

function WL.OnSystem(line)
	local m = Core.ParseLine(line);
	if ( not m ) then return; end
	-- commande a laquelle la ligne repond ; les panneaux de fabrication / fonderie affichent eux-memes leurs messages.
	-- Une reponse de pose (sort du marteau, hors canal) n'appartient a aucune commande en attente du canal.
	local entry = Core.ChannelRoute(WL.channel, m, GetTime());
	local placeLine = Core.IsPlaceLine(WL.state, m);
	if ( placeLine ) then entry = nil; end
	Core.GhostCheckOnMessage(WL.gc, m, entry, GetTime());   -- CP| : couleur du fantome (WL.UpdateGhost, a chaque image)
	Core.PieceInfoOnMessage(WL.pi, m, entry, GetTime());    -- PI| : surbrillance / info-bulle de la piece visee (WL.UpdateHover)
	local snd = Core.DestroySound(m, Data.pieces);           -- « Démoli : Mur en bois. » : bruit de bois / pierre brises
	if ( snd and PlaySoundFile ) then PlaySoundFile(snd); end
	local shown = nil;
	if ( not placeLine ) then
		if ( WL.Craft and WL.Craft.OnMessage(m, entry) ) then shown = 1; end
		if ( WL.Smelt and WL.Smelt.OnMessage(m, entry) ) then shown = 1; end
	end
	if ( shown or (entry and entry.silent and (m.type == "M" or m.type == "E")) ) then
		-- deja affiche par un panneau, ou reponse d'un rafraichissement silencieux
	elseif ( m.type == "M" or m.type == "E" ) then
		-- refus de pose : notification + M| + D|place|0 => un seul message (D|place|0 n'affiche rien)
		local n = Core.NotifyLine(WL.notify, WL.state, m, entry, GetTime());
		if ( n ) then WL.ShowMessage(n.text, n.error, n.notified); end
	elseif ( m.type == "S" ) then
		WL.station = m;
	end
	if ( WL.Skills ) then WL.Skills.OnMessage(m); end      -- EN| SK| SKU| SKL| (WowlheimSkills.lua)
	local kev = Core.KnownOnMessage(WL.known, m);
	if ( kev == "update" ) then
		WL.OnKnown();
		WL.AnnounceKnown();
	elseif ( kev == "learned" ) then
		WL.knownForce = 1;        -- KN| : nouvel objet / station : relancer known (pieces / recettes debloquees)
		WL.AnnounceLearned(m);
		WL.OnKnown();
	end
	if ( Core.RingsOnMessage(WL.rings, m) == "update" ) then
		WL.ApplyRings();
	end
	if ( Core.ModelsOnMessage(WL.models, m) == "update" and WL.HammerEquipped() ) then
		WL.QueuePreload();
	end
	if ( placeLine ) then Core.TargetWatchCast(WL.tw, GetTime()); end
	-- un E| qui repond a une commande (removeguid...) n'est pas un refus de pose
	if ( not (entry and m.type == "E") and Core.OnServerMessage(WL.state, m) == "relaunch" ) then
		local start, duration = GetInventoryItemCooldown("player", Core.HAMMER_SLOT);
		WL.relaunchAt = Core.RelaunchTime(GetTime(), start, duration);
	end
	WL.UpdateInfo();
	WL.UpdateBanner();
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

-- Clic droit sur une grande piece refuse par le client (« You are too far away. » : 5 m depuis le CENTRE de l'objet) : si la
-- piece sous la souris est une piece Wowlheim, « .build api use <guid> » (serveur : 3 m du BORD de la boite, puis meme chemin
-- que le clic) et le message rouge est masque. On enveloppe UIErrorsFrame_OnEvent (FrameXML, non protegee), comme
-- ChatFrame_OnEvent ci-dessus ; aucune fonction protegee (TurnOrActionStart...) n'est touchee.
WL.useRetry = Core.NewUseRetry();
function WL.UseTooFar(message)
	if ( not WowlheimGetMouseoverObject or not Core.IsUseTooFar(message, ERR_USE_TOO_FAR) ) then return nil; end
	local guidHex, entry = WowlheimGetMouseoverObject();
	local cmd, mask = Core.UseRetry(WL.useRetry, message, ERR_USE_TOO_FAR, guidHex, entry, GetTime());
	if ( cmd ) then WL.Send(cmd); end
	return mask;
end

WL.origErrorsOnEvent = UIErrorsFrame_OnEvent;
if ( WL.origErrorsOnEvent ) then
	UIErrorsFrame_OnEvent = function(event, message)
		if ( event == "UI_ERROR_MESSAGE" and WL.UseTooFar(message) ) then
			return;
		end
		WL.origErrorsOnEvent(event, message);
	end
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
	-- de la piece choisie (9110000 + id) ; le client l'affiche sous le curseur pendant le ciblage au sol. Rappele AVANT
	-- chaque ciblage (premier et relances de la pose continue) avec la piece de l'etat du marteau.
	local ghost = Core.PlaceObjectId(WL.state);
	if ( WowlheimSetPlaceObject and ghost ) then
		WowlheimSetPlaceObject(ghost);
	end
	WL.ApplyGhostFacing();
	Core.GhostCheckReset(WL.gc);                 -- verdict canplace d'avant la pose perime : nouvelle interrogation
	-- WowlheimUseHammer (DLL) : ciblage accepte meme hors touche / clic (relance apres la pose, OnUpdate, CHAT_MSG)
	WL.lastUse = Core.UseHammer(WowlheimUseHammer, UseInventoryItem, Core.HAMMER_SLOT);
	Core.TargetWatchStart(WL.tw, GetTime());     -- clic droit = fin du ciblage sans pose (WL.WatchTargeting)
end

-- Valheim : le menu disparait pendant la pose pour degager le sol. Masquage SANS annulation (OnHide annule sinon).
function WL.HideForPlacement()
	if ( WL.frame and WL.frame:IsVisible() ) then
		WL.keepPose = 1;
		WL.frame:Hide();
		WL.keepPose = nil;
	end
end

function WL.ChooseEntry(e)
	WL.selected = e;
	WL.relaunchAt = nil;
	if ( e.special ) then
		Core.TargetWatchStop(WL.tw);
		if ( SpellIsTargeting() ) then SpellStopTargeting(); end
		-- silencieux : l'accuse « Marteau : mode ... » du serveur doublerait le rappel de l'addon ci-dessous
		WL.SendAll(Core.ChooseMode(WL.state, e.special), 1);
		WL.Update();
		WL.HideForPlacement();
		if ( e.special == "repair" ) then
			WL.ShowMessage("Réparer : clic droit sur une construction.");
		else
			WL.ShowMessage("Démolir : clic droit sur une construction.");
		end
	else
		-- silencieux : le bandeau « Pièce  -  Rotation : 0° » suffit (l'accuse « ... choisi (rotation 0°). » du serveur
		-- s'affichait en plus au centre) ; ressources manquantes : 2e ligne du bandeau (Valheim : quantites en rouge)
		local cmds = Core.ChoosePiece(WL.state, e.id);
		WL.SendAll(cmds, 1);
		WL.Update();
		WL.HideForPlacement();
		WL.StartTargeting();
	end
	WL.UpdateBanner();
end

-- Clic droit / Echap / fermeture du menu : fin de la pose continue ; le mode Demolir / Reparer reste actif (rappel a l'ecran).
function WL.Cancel()
	WL.relaunchAt = nil;
	Core.TargetWatchStop(WL.tw);
	if ( SpellIsTargeting() ) then SpellStopTargeting(); end
	WL.SendAll(Core.Cancel(WL.state));
	if ( not (WL.selected and WL.selected.special) ) then WL.selected = nil; end
	if ( WL.frame ) then WL.Update(); end
	WL.UpdateBanner();
end

-- Rappel en haut de l'ecran : mode courant (« Mode : Démolir ») tant que le marteau est equipe hors mode construction ;
-- en construction, piece en cours de pose + rotation tant que le menu est masque.
function WL.UpdateBanner()
	local eq = WL.HammerEquipped();
	local name = nil;
	if ( WL.selected and not WL.selected.special and WL.selected.id == WL.state.piece ) then name = WL.selected.name; end
	local place = Core.PlaceBanner(WL.state, eq, WL.frame and WL.frame:IsVisible(), name);
	local warn, missing = nil, nil;
	if ( place and WL.selected and not WL.selected.special ) then
		warn = Core.StationRangeWarning(WL.rings, WL.selected.station, Data.stations);
		missing = Core.MissingText(WL.selected.costs, WL.counts, WL.ItemName);
	end
	-- 2e ligne en rouge : ressources manquantes puis avertissement de portee (zone fixe Core.BANNER_W x BANNER_H : 2 lignes
	-- au plus, centrees ; la fin est coupee si les deux ne tiennent pas : le cercle de portee reste visible au sol).
	-- Valheim : la piece reste choisie, les quantites manquantes sont en rouge.
	local second = missing;
	if ( warn ) then
		if ( second ) then second = second .. "  -  " .. warn; else second = warn; end
	end
	if ( second ) then place = place .. "\n|cffff4040" .. second .. "|r"; end
	if ( not place ) then
		if ( WL.placeBanner ) then WL.placeBanner:Hide(); end
	else
		if ( not WL.placeBanner ) then
			local p = CreateFrame("Frame", "WowlheimPlaceBanner", UIParent);
			p:SetWidth(Core.BANNER_W); p:SetHeight(Core.BANNER_H);
			p:SetPoint("TOP", UIParent, "TOP", 0, -Core.BANNER_TOP);
			p:SetFrameStrata("HIGH");
			local pfs = WL.Label(p, "WowlheimPlaceBannerText", "GameFontNormal", Core.BANNER_W, Core.BANNER_H, "CENTER", "MIDDLE");
			pfs:SetPoint("CENTER", p, "CENTER", 0, 0);
			pfs:SetTextColor(ORANGE[1], ORANGE[2], ORANGE[3]);
			p.text = pfs;
			WL.placeBanner = p;
		end
		WL.placeBanner.text:SetText(place);
		WL.placeBanner:Show();
	end
	local text = Core.ModeBanner(WL.state, eq);
	if ( not text ) then
		if ( WL.banner ) then WL.banner:Hide(); end
		return;
	end
	if ( not WL.banner ) then
		local b = CreateFrame("Frame", "WowlheimModeBanner", UIParent);
		b:SetWidth(Core.BANNER_W); b:SetHeight(Core.BANNER_H);
		b:SetPoint("TOP", UIParent, "TOP", 0, -Core.BANNER_TOP);
		b:SetFrameStrata("HIGH");
		local fs = WL.Label(b, "WowlheimModeBannerText", "GameFontNormalLarge", Core.BANNER_W, Core.BANNER_H, "CENTER", "MIDDLE");
		fs:SetPoint("CENTER", b, "CENTER", 0, 0);
		b.text = fs;
		WL.banner = b;
	end
	if ( WL.state.mode == "repair" ) then
		WL.banner.text:SetTextColor(0.25, 1.0, 0.25);
	else
		WL.banner.text:SetTextColor(1.0, 0.25, 0.25);
	end
	WL.banner.text:SetText(text);
	WL.banner:Show();
end

-- ------------------------------------------------------------------------------------------------
-- Cercle de portee des stations (Valheim : CraftingStation.m_areaMarker). Marteau equipe en mode construction : interrogation
-- silencieuse ".build api stations" toutes les Core.RING_POLL s ; un segment M2 par point du contour (DLL :
-- WowlheimMarkerShow / WowlheimMarkerHide ; sans la DLL, seul l'avertissement du bandeau de pose fonctionne).
-- ------------------------------------------------------------------------------------------------
function WL.HideRings()
	if ( WL.ringCount > 0 and WowlheimMarkerHide ) then
		local i = 0;
		while i < WL.ringCount do
			WowlheimMarkerHide(i);
			i = i + 1;
		end
	end
	WL.ringCount = 0;
end

function WL.ApplyRings()
	if ( not Core.RingsWanted(WL.state, WL.HammerEquipped()) ) then
		WL.HideRings();
		return;
	end
	local list = Core.RingMarkers(WL.rings.stations, Core.RING_MAX);
	if ( WowlheimMarkerShow ) then
		local i = 1;
		while i <= list.n do
			local mk = list[i];
			WowlheimMarkerShow(mk.id, mk.path, mk.x, mk.y, mk.z, mk.o);
			i = i + 1;
		end
		i = list.n;
		while i < WL.ringCount do
			WowlheimMarkerHide(i);
			i = i + 1;
		end
	end
	WL.ringCount = list.n;
	WL.UpdateBanner();
end

-- Appele a chaque image : interrogation periodique, masquage des que le marteau est range ou hors mode construction.
function WL.UpdateRings(now)
	if ( not Core.RingsWanted(WL.state, WL.HammerEquipped()) ) then
		if ( WL.ringCount > 0 ) then WL.HideRings(); end
		WL.ringPollAt = 0;
		if ( WL.rings.version > 0 or WL.rings.tmp ) then WL.rings = Core.NewRings(); end
		return;
	end
	if ( now < WL.ringPollAt ) then return; end
	Core.ChannelRoute(WL.channel, nil, now);       -- oublie une interrogation restee sans reponse (CHANNEL_TIMEOUT)
	if ( not Core.ChannelHas(WL.channel, "stations") ) then
		WL.ringPollAt = now + Core.RING_POLL;
		WL.Send(Core.StationsCommand(), 1);
	end
end

function WL.Rotate(delta)
	WL.SendAll(Core.Rotate(WL.state, delta), 1);       -- silencieux : la rotation est affichee par le bandeau
	WL.ApplyGhostFacing();                             -- le fantome tourne tout de suite, pendant le ciblage
	WL.UpdateInfo();
	WL.UpdateBanner();
end

-- ------------------------------------------------------------------------------------------------
-- Fantome de pose : orientation et couleur (Valheim : rotation a la molette, fantome rouge si la pose est impossible)
-- ------------------------------------------------------------------------------------------------
-- Le serveur pose avec orientation du personnage + rot x 22,5 deg (BuildingMgr::PlaceOrientation) : la DLL ajoute ce meme
-- decalage a l'orientation du personnage a chaque image (le fantome suit aussi les rotations du personnage).
function WL.ApplyGhostFacing()
	if ( WowlheimSetPlaceFacing ) then
		WowlheimSetPlaceFacing(Core.PlaceFacingOffset(WL.state.rot), 1);
	end
end

-- Appele a chaque image : pendant le ciblage de la pose, interrogation canplace (au plus toutes les Core.GHOST_POLL s) et
-- teinte du fantome natif (DLL : WowlheimGhostSetColor(..., 1)) ; teinte retiree hors ciblage.
function WL.UpdateGhost(now)
	local st = WL.state;
	local active = WowlheimGhostGetPos and st.mode == "build" and st.piece and st.continuous and SpellIsTargeting()
		and WL.HammerEquipped();
	if ( not active ) then
		if ( WL.ghostTint and WowlheimGhostSetColor ) then WowlheimGhostSetColor(1, 1, 1, 1, 0, -1); end
		WL.ghostTint = nil;
		WL.HideSnapGhost();
		return;
	end
	local x, y, z, _, _, range, nativeFacing = WowlheimGhostGetPos();
	local pos = nil;
	if ( x ) then pos = { x = x, y = y, z = z }; end
	Core.ChannelRoute(WL.channel, nil, now);       -- oublie une interrogation restee sans reponse (CHANNEL_TIMEOUT)
	local cmd = Core.GhostCheckCommand(WL.gc, st, pos, now, Core.ChannelHas(WL.channel, "canplace"));
	if ( cmd ) then WL.Send(cmd, 1); end
	local e = WL.selected;
	local costs, station = nil, nil;
	if ( e and not e.special and e.id == st.piece ) then costs = e.costs; station = e.station; end
	local valid = Core.GhostValid({ st = st, costs = costs, counts = WL.counts, station = station, rings = WL.rings,
		range = range, gc = WL.gc, now = now });
	local key = Core.GhostColorKey(valid);
	-- Valheim : le fantome est montre au point ACCROCHE. Le fantome natif suit la souris (le client le deplace a chaque image) :
	-- quand le serveur a accroche la piece, il est rendu invisible (alpha 0) et le fantome DLL (meme modele) est pose au point
	-- accroche ; il tourne avec l'orientation du fantome natif (personnage + rotation). Sinon : fantome natif teinte.
	local snap = Core.GhostSnapPos(WL.gc, st, pos, now);
	if ( snap and not WL.SnapGhostReady(now) ) then snap = nil; end
	local path = snap and WL.models.paths[st.piece];
	local nativeKey = key;
	if ( path ) then
		nativeKey = "hidden";
		local c = Core.GHOST_COLORS[key];
		if ( not WL.snapGhost or WL.snapGhost.path ~= path ) then
			WowlheimGhostShow(path);
			WL.snapGhost = { path = path };
		end
		WowlheimGhostPlace(snap.x, snap.y, snap.z);
		WowlheimGhostRotate(nativeFacing or snap.o or 0);
		if ( WL.snapGhost.tint ~= key ) then
			WowlheimGhostSetColor(c[1], c[2], c[3], c[4], c[5]);
			WL.snapGhost.tint = key;
		end
	else
		WL.HideSnapGhost();
	end
	if ( nativeKey ~= WL.ghostTint and WowlheimGhostSetColor ) then
		if ( nativeKey == "hidden" ) then
			WowlheimGhostSetColor(1, 1, 1, 0, 0, 1);
		else
			local c = Core.GHOST_COLORS[nativeKey];
			WowlheimGhostSetColor(c[1], c[2], c[3], c[4], c[5], 1);
		end
		WL.ghostTint = nativeKey;
	end
end

-- Le fantome DLL au point accroche est-il possible ? (DLL avec WowlheimGhostPlace, modeles des pieces connus : MD|).
-- Demande « .build api models » si besoin (au plus toutes les 5 s).
function WL.SnapGhostReady(now)
	if ( not (WowlheimGhostShow and WowlheimGhostPlace and WowlheimGhostRotate and WowlheimGhostSetColor) ) then return nil; end
	if ( WL.models.loaded ) then return 1; end
	if ( not WL.models.unsupported and not Core.ChannelHas(WL.channel, "models") and now - WL.modelsAskAt >= 5 ) then
		WL.modelsAskAt = now;
		WL.Send(Core.ModelsCommand(), 1);
	end
	return nil;
end

function WL.HideSnapGhost()
	if ( WL.snapGhost and WowlheimGhostHide ) then WowlheimGhostHide(); end
	WL.snapGhost = nil;
end

-- ------------------------------------------------------------------------------------------------
-- Controles du mode construction (docs/BUILD_CONTROLS.md)
-- ------------------------------------------------------------------------------------------------
-- Clic milieu (liaison temporaire BUTTON3 -> WOWLHEIM_REMOVE) : demolir la piece sous la souris. La DLL refait le lancer de
-- rayon avec les gameobjects (le ciblage au sol reste actif) ; sans DLL : piece la plus proche (".build api remove").
function WL.RemoveUnderMouse()
	if ( not WL.HammerEquipped() ) then return; end
	Core.TargetWatchRemove(WL.tw, GetTime());     -- si le clic milieu a annule le ciblage : relance, pas de menu
	local guidHex, entry = nil, nil;
	if ( WowlheimGetMouseoverObject ) then guidHex, entry = WowlheimGetMouseoverObject(); end
	local cmd, err = Core.RemoveCommand(WowlheimGetMouseoverObject ~= nil, guidHex, entry);
	if ( cmd ) then
		WL.Send(cmd);
	else
		WL.ShowMessage(err, 1);
	end
end

-- ------------------------------------------------------------------------------------------------
-- Piece visee (Valheim : Player.UpdateWearNTearHover -> WearNTear.Highlight ; docs/BUILD_CONTROLS.md section 9) : a chaque
-- image, marteau equipe, la piece Wowlheim sous la souris est mise en surbrillance par la DLL (WowlheimHighlightObject,
-- reappliquee a chaque image, retiree des que la souris la quitte) ; en modes Demolir / Reparer, petite info-bulle pres du
-- curseur (nom de la piece, action du clic droit). Sans la DLL : rien.
-- ------------------------------------------------------------------------------------------------
WL.hoverGuid = nil;
function WL.HoverClear()
	if ( WL.hoverGuid and WowlheimHighlightObject ) then WowlheimHighlightObject(); end
	WL.hoverGuid = nil;
	if ( WL.hoverTip and WL.hoverTip:IsShown() ) then WL.hoverTip:Hide(); end
end

function WL.HoverTipFrame()
	if ( WL.hoverTip ) then return WL.hoverTip; end
	local w = Core.HOVER_TIP_W;
	local f = CreateFrame("Frame", "WowlheimHoverTip", UIParent);
	f:SetFrameStrata("TOOLTIP");
	f:SetWidth(w); f:SetHeight(40);
	WL.WoodBackdrop(f, 12);
	local name = WL.Label(f, "WowlheimHoverTipName", "GameFontNormal", w - 16, 14, "LEFT", "MIDDLE");
	name:SetPoint("TOPLEFT", f, "TOPLEFT", 8, -7);
	name:SetTextColor(ORANGE[1], ORANGE[2], ORANGE[3]);
	-- lignes de 12 sous le nom (14) : sante, support (pieceinfo), action du clic droit ; placees a chaque affichage
	local health = WL.Label(f, "WowlheimHoverTipHealth", "GameFontHighlightSmall", w - 16, 12, "LEFT", "MIDDLE");
	local support = WL.Label(f, "WowlheimHoverTipSupport", "GameFontHighlightSmall", w - 16, 12, "LEFT", "MIDDLE");
	local action = WL.Label(f, "WowlheimHoverTipAction", "GameFontHighlightSmall", w - 16, 12, "LEFT", "MIDDLE");
	f.name = name; f.health = health; f.support = support; f.action = action;
	f:Hide();
	WL.hoverTip = f;
	return f;
end

-- name, action (HoverTip) ; info = Core.PieceInfoFor (sante / support), nil tant que le serveur n'a pas repondu
function WL.ShowHoverTip(name, action, info)
	local f = WL.HoverTipFrame();
	WL.FitText(f.name, name, Core.HOVER_TIP_W - 16);
	local health, support = Core.PieceInfoLines(info);
	local y = -22;
	local lines = { { f.health, health and health.text, health }, { f.support, support and support.text, support },
		{ f.action, action, nil } };
	local i = 1;
	while lines[i] do
		local fs, text, col = lines[i][1], lines[i][2], lines[i][3];
		if ( text ) then
			fs:ClearAllPoints();
			fs:SetPoint("TOPLEFT", f, "TOPLEFT", 8, y);
			fs:SetText(text);
			if ( col ) then fs:SetTextColor(col.r, col.g, col.b); end
			fs:Show();
			y = y - 14;
		else
			fs:SetText("");
			fs:Hide();
		end
		i = i + 1;
	end
	if ( WL.state.mode == "remove" ) then f.action:SetTextColor(1.0, 0.35, 0.35); else f.action:SetTextColor(0.35, 1.0, 0.35); end
	f:SetHeight(-y + 4);
	if ( GetCursorPosition ) then
		local x, y = GetCursorPosition();
		local s = (UIParent.GetEffectiveScale and UIParent:GetEffectiveScale()) or 1;
		if ( not s or s <= 0 ) then s = 1; end
		f:ClearAllPoints();
		f:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", x / s + Core.HOVER_TIP_DX, y / s - Core.HOVER_TIP_DY);
	end
	if ( not f:IsShown() ) then f:Show(); end
end

function WL.UpdateHover()
	local focus = nil;
	if ( GetMouseFocus ) then focus = GetMouseFocus(); end
	if ( not (WL.inWorld and WowlheimGetMouseoverObject and Core.HoverWanted(WL.state, WL.HammerEquipped())
		and Core.MouseOnWorld(focus, WorldFrame)) ) then
		if ( WL.hoverGuid or (WL.hoverTip and WL.hoverTip:IsShown()) ) then WL.HoverClear(); end
		return;
	end
	local guidHex, entry = WowlheimGetMouseoverObject();
	if ( not Core.IsPieceObject(guidHex, entry) ) then
		WL.HoverClear();
		return;
	end
	-- etat de la piece (serveur) : interrogation silencieuse au changement de piece, puis toutes les PIECEINFO_REFRESH s
	local now = GetTime();
	Core.ChannelRoute(WL.channel, nil, now);       -- oublie une interrogation restee sans reponse (CHANNEL_TIMEOUT)
	local cmd = Core.PieceInfoCommand(WL.pi, guidHex, now, Core.ChannelHas(WL.channel, "pieceinfo"));
	if ( cmd ) then WL.Send(cmd, 1); end
	local info = Core.PieceInfoFor(WL.pi, guidHex, now);
	if ( WowlheimHighlightObject ) then
		if ( WL.hoverGuid and WL.hoverGuid ~= guidHex ) then WowlheimHighlightObject(); end
		-- WearNTear.Highlight : couleur du support (bleu clair tant que l'etat n'est pas connu ou si le support est complet)
		local r, g, b = Core.HighlightColor(info and info.support);
		if ( WowlheimHighlightObject(guidHex, r, g, b, Core.HOVER_GLOW) ) then WL.hoverGuid = guidHex; else WL.hoverGuid = nil; end
	end
	if ( Core.HoverTipWanted(WL.state) ) then
		local name, action = Core.HoverTip(WL.state, entry, Data.pieces);
		WL.ShowHoverTip(name, action, info);
	elseif ( WL.hoverTip and WL.hoverTip:IsShown() ) then
		WL.hoverTip:Hide();
	end
end

-- Liaisons : API du client (absente hors du jeu / avant le chargement des liaisons)
function WL.BindApi()
	if ( not (SetBinding and GetBindingAction) ) then return nil; end
	return {
		action = function(key) return GetBindingAction(key); end,
		set = function(key, action)
			if ( action == nil or action == "" ) then SetBinding(key); else SetBinding(key, action); end
		end,
	};
end

function WL.ApplyBuildKeys()
	local api = WL.BindApi();
	if ( not api ) then return; end
	Core.TempBindApply(WL.tempBinds, api, Core.BuildKeys(WowlheimDB and WowlheimDB.qe));
	WL.buildKeysOn = 1;
end

function WL.RestoreBuildKeys()
	local api = WL.BindApi();
	WL.buildKeysOn = nil;
	if ( not api ) then return; end
	Core.TempBindRestore(WL.tempBinds, api);
end

-- Appele a chaque image et aux evenements : pose / retablit les liaisons temporaires selon le mode du marteau.
function WL.UpdateBuildKeys()
	local want = WL.inWorld and Core.BuildControlsWanted(WL.state, WL.HammerEquipped());
	if ( want and not WL.buildKeysOn ) then
		WL.ApplyBuildKeys();
	elseif ( not want and WL.buildKeysOn ) then
		WL.RestoreBuildKeys();
	end
end

-- Entree dans le monde : liaisons temporaires d'une session precedente (/reload, plantage) retablies, puis liaisons
-- temporaires restees enregistrees (SaveBindings du menu Raccourcis pendant la construction) remises a l'origine.
function WL.RecoverBuildKeys()
	local api = WL.BindApi();
	if ( not api ) then return; end
	Core.TempBindRestore(WL.tempBinds, api);
	Core.TempBindRepair(api);
	WL.buildKeysOn = nil;
end

-- Clic droit pendant le ciblage : le client annule le ciblage. Appele a chaque image.
function WL.WatchTargeting(now)
	if ( not (WL.HammerEquipped() and WL.state.mode == "build" and WL.state.continuous) ) then
		Core.TargetWatchStop(WL.tw);
		return;
	end
	local rightDown = nil;
	if ( IsMouseButtonDown ) then rightDown = IsMouseButtonDown("RightButton"); end
	local act = Core.TargetWatchUpdate(WL.tw, SpellIsTargeting(), now, rightDown);
	if ( act == "menu" ) then
		-- Valheim : clic droit = menu de construction ; la piece reste choisie, pas de nouveau ciblage (choisir une piece le relance)
		WL.relaunchAt = nil;
		WL.state.pending = nil;
		WL.Show();
	elseif ( act == "relaunch" ) then
		WL.relaunchAt = now;
	end
	if ( act and WL.debug and DEFAULT_CHAT_FRAME ) then
		-- diagnostic en jeu (/wl debug) : relance faute de ciblage (UseInventoryItem refuse) ou de reponse du serveur
		DEFAULT_CHAT_FRAME:AddMessage("Wowlheim : ciblage " .. act .. " (échecs de suite : " .. (WL.tw.fails or 0)
			.. ", voie " .. tostring(WL.lastUse) .. ")");
	end
end

-- Prechargement des modeles des pieces connues (DLL : WowlheimPreloadModel), a l'equipement du marteau, par lots.
function WL.QueuePreload()
	if ( not WowlheimPreloadModel or not WL.inWorld ) then return; end
	if ( not WL.models.loaded ) then
		if ( not WL.models.unsupported and not Core.ChannelHas(WL.channel, "models") ) then
			WL.Send(Core.ModelsCommand(), 1);
		end
		return;
	end
	local list = Core.PreloadList(Data.pieces, WL.models, WL.known, WL.counts, WL.NearStations(), WL.preloadDone);
	if ( list.n > 0 ) then WL.preloadQueue = list; WL.preloadPos = 1; end
end

function WL.RunPreload()
	local q = WL.preloadQueue;
	if ( not q ) then return; end
	if ( not WowlheimPreloadModel ) then WL.preloadQueue = nil; return; end
	local k = 0;
	while k < Core.PRELOAD_BATCH and WL.preloadPos <= q.n do
		local path = q[WL.preloadPos];
		WL.preloadDone[path] = true;
		WowlheimPreloadModel(path);
		WL.preloadPos = WL.preloadPos + 1;
		k = k + 1;
	end
	if ( WL.preloadPos > q.n ) then WL.preloadQueue = nil; end
end

function WL.Relaunch()
	WL.relaunchAt = nil;
	local st = WL.state;
	if ( not (st.continuous and st.mode == "build" and st.piece) ) then return; end
	-- Valheim : pose en chaine, meme sans assez de ressources (la piece reste choisie, le bandeau dit ce qui manque, le
	-- serveur refuse la pose) ; le menu ne revient que sur un clic droit / la touche du menu. Pas de WL.Show() ici.
	WL.StartTargeting();
	WL.UpdateBanner();
end

-- NE PAS envelopper TurnOrActionStart / TurnOrActionStop : ce sont des actions protegees du client 1.12 ; les remplacer
-- par une fonction d'addon declenche « Wowlheim has been blocked from an action only available to the Blizzard UI » et
-- casse le clic droit (constate en jeu le 2026-10-26). Le clic droit en construction est detecte par WL.WatchTargeting.

-- Echap en mode pose (piece choisie, pose continue) : fin de la pose, SANS menu du jeu (Valheim : Echap quitte d'abord le
-- placement). Vaut que le ciblage soit actif, deja annule par le client (WL.tw.endedAt) ou en attente de relance (apres une
-- pose, avant la reponse du serveur) : le bandeau « Piece - Rotation » disparait. Menu du marteau ouvert : il est ferme
-- (OnHide -> WL.Cancel). Hors pose (mode Demolir / Reparer, marteau range) : menu du jeu normal.
WL.origToggleGameMenu = ToggleGameMenu;
function WL.InPlaceMode()
	local st = WL.state;
	return st.continuous and st.mode == "build" and st.piece and WL.HammerEquipped();
end
ToggleGameMenu = function(clicked)
	if ( WL.state.continuous and (SpellIsTargeting() or WL.tw.endedAt or WL.InPlaceMode()) ) then
		if ( WL.frame and WL.frame:IsVisible() ) then
			WL.frame:Hide();          -- OnHide : WL.Cancel()
		else
			WL.Cancel();
		end
		return;
	end
	if ( WL.origToggleGameMenu ) then WL.origToggleGameMenu(clicked); end   -- argument d'origine transmis
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

-- ------------------------------------------------------------------------------------------------
-- Mise en page des textes : aucun texte ne deborde de sa zone. Chaque FontString a une largeur ET une hauteur fixes
-- (le client coupe ce qui depasse) ; les noms sont en plus raccourcis proprement avec « ... » (FitText) et le texte
-- complet est donne par une info-bulle. GetStringWidth (1.12) mesure le texte courant ; hors du jeu (test_core.py),
-- estimation a ~6 px par octet (polices FRIZQT : ~5,5 px en Small, ~6,5 en Normal, ~8,5 en Large).
-- ------------------------------------------------------------------------------------------------
local function TextWidth(fs, text, px)
	local w = nil;
	if ( fs.GetStringWidth ) then w = fs:GetStringWidth(); end
	if ( not w or w == 0 ) then w = string.len(text or "") * (px or 6); end
	return w;
end

-- Retire le dernier caractere UTF-8 (octets de continuation 0x80-0xBF compris)
local function Utf8Chop(s)
	local n = string.len(s);
	while n > 0 do
		local c = string.byte(s, n);
		n = n - 1;
		if ( c < 128 or c >= 192 ) then break; end
	end
	return string.sub(s, 1, n);
end

-- Texte d'une ligne, raccourci avec « ... » s'il depasse maxW. Renvoie 1 si le texte a ete raccourci.
local function FitText(fs, text, maxW)
	text = text or "";
	fs:SetText(text);
	if ( not fs.GetStringWidth ) then return nil; end
	local w = fs:GetStringWidth();
	if ( not w or w <= maxW ) then return nil; end
	local s = text;
	while string.len(s) > 0 and w and w > maxW do
		s = Utf8Chop(s);
		fs:SetText(s .. "...");
		w = fs:GetStringWidth();
	end
	return 1;
end

-- Titre (nom d'objet / de piece) : grande police, police normale si le nom est trop long, puis « ... » en dernier recours.
-- SetFontObject remet la couleur de la police : couleur reappliquee.
local function SetTitle(fs, text, maxW, r, g, b)
	if ( GameFontNormalLarge ) then fs:SetFontObject(GameFontNormalLarge); end
	fs:SetText(text or "");
	if ( GameFontNormal and TextWidth(fs, text, 8.5) > maxW ) then fs:SetFontObject(GameFontNormal); end
	if ( r ) then fs:SetTextColor(r, g, b); end
	return FitText(fs, text, maxW);
end

-- FontString a zone fixe : largeur, hauteur (nombre de lignes), alignements. Rien ne peut deborder de cette zone.
local function Label(parent, name, font, w, h, justifyH, justifyV)
	local fs = parent:CreateFontString(name, "OVERLAY", font);
	fs:SetWidth(w); fs:SetHeight(h);
	fs:SetJustifyH(justifyH or "LEFT");
	fs:SetJustifyV(justifyV or "MIDDLE");
	return fs;
end

-- Info-bulle : titre orange + lignes blanches (retour a la ligne automatique). lines : liste (trous / "" ignores).
local function ShowTooltip(owner, title, lines)
	if ( not GameTooltip ) then return; end
	GameTooltip:SetOwner(owner, "ANCHOR_RIGHT");
	GameTooltip:SetText(title or "", ORANGE[1], ORANGE[2], ORANGE[3]);
	local i = 1;
	while lines and i <= (lines.n or table.getn(lines)) do
		if ( lines[i] and lines[i] ~= "" ) then GameTooltip:AddLine(lines[i], 1, 1, 1, 1); end
		i = i + 1;
	end
	GameTooltip:Show();
end

local function HideTooltip()
	if ( GameTooltip ) then GameTooltip:Hide(); end
end

-- Champ de recherche (EditBox 1.12). SetAutoFocus(false) : il ne prend le clavier qu'apres un clic dedans ; tant qu'il a
-- le focus, les touches tapees vont au texte (aucun raccourci ne se declenche : comportement normal d'une EditBox).
-- Echap / Entree : rend le clavier au jeu. onChange(texte) a chaque modification. Texte d'aide grise quand il est vide.
local function SearchBox(name, parent, w, placeholder, onChange, h)
	local eb = CreateFrame("EditBox", name, parent);
	eb:SetWidth(w); eb:SetHeight(h or 20);
	eb:SetAutoFocus(false);
	eb:SetFontObject(GameFontHighlightSmall);
	eb:SetTextInsets(6, 6, 0, 0);
	eb:SetMaxLetters(40);
	eb:EnableMouse(1);
	WoodBackdrop(eb, 12);
	eb:SetBackdropColor(0.06, 0.04, 0.02, 0.95);
	local hint = eb:CreateFontString(name .. "Hint", "ARTWORK", "GameFontDisableSmall");
	hint:SetPoint("LEFT", eb, "LEFT", 7, 0);
	hint:SetWidth(w - 14); hint:SetHeight(12);
	hint:SetJustifyH("LEFT"); hint:SetJustifyV("MIDDLE");
	hint:SetText(placeholder);
	eb.hint = hint;
	eb:SetScript("OnTextChanged", function()
		local t = this:GetText() or "";
		if ( t == "" and not this.focused ) then this.hint:Show(); else this.hint:Hide(); end
		onChange(t);
	end);
	eb:SetScript("OnEscapePressed", function() this:ClearFocus(); end);
	eb:SetScript("OnEnterPressed", function() this:ClearFocus(); end);
	eb:SetScript("OnEditFocusGained", function() this.focused = 1; this.hint:Hide(); end);
	eb:SetScript("OnEditFocusLost", function()
		this.focused = nil;
		if ( (this:GetText() or "") == "" ) then this.hint:Show(); end
	end);
	eb:SetScript("OnHide", function() this:ClearFocus(); end);
	return eb;
end

-- partages avec WowlheimCraft.lua (panneaux de fabrication et de fonderie)
WL.SearchBox = SearchBox;
WL.WoodBackdrop = WoodBackdrop;
WL.AddHighlight = AddHighlight;
WL.SetGrey = SetGrey;
WL.TextWidth = TextWidth;
WL.FitText = FitText;
WL.SetTitle = SetTitle;
WL.Label = Label;
WL.ShowTooltip = ShowTooltip;
WL.HideTooltip = HideTooltip;
WL.ORANGE = ORANGE;
WL.BROWN_BG = BROWN_BG;
WL.BROWN_EDGE = BROWN_EDGE;

-- Position des panneaux (WowlheimCore.PanelPos) : echelle reduite, coin bas-gauche en unites UIParent, memorise dans
-- WowlheimDB.pos[key] apres un deplacement. GetLeft / GetBottom sont dans l'echelle du cadre (x GetScale = UIParent ;
-- comportement 1.12 SUPPOSE, non verifie en jeu).
function WL.ScreenSize()
	local w, h = UIParent:GetWidth(), UIParent:GetHeight();
	if ( not w or w <= 0 or not h or h <= 0 ) then return 1024, 768; end
	return w, h;
end

function WL.PlacePanel(f, key)
	local scale = Core.PANELS[key].scale;
	f:SetScale(scale);
	if ( f.SetClampedToScreen ) then f:SetClampedToScreen(1); end
	local saved = WowlheimDB and WowlheimDB.pos and WowlheimDB.pos[key];
	local sw, sh = WL.ScreenSize();
	local left, bottom = Core.PanelPos(key, saved, sw, sh);
	f:ClearAllPoints();
	f:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", left / scale, bottom / scale);
end

function WL.SavePanel(f, key)
	local l, b = f:GetLeft(), f:GetBottom();
	if ( not l or not b or not WowlheimDB ) then return; end
	local scale = f:GetScale() or Core.PANELS[key].scale;
	if ( not WowlheimDB.pos ) then WowlheimDB.pos = {}; end
	WowlheimDB.pos[key] = { l * scale, b * scale };
end

-- /wl reset : positions par defaut pour les trois panneaux
function WL.ResetPanels()
	if ( WowlheimDB ) then WowlheimDB.pos = nil; end
	if ( WL.frame ) then WL.PlacePanel(WL.frame, "hammer"); end
	if ( WL.Craft and WL.Craft.frame ) then WL.PlacePanel(WL.Craft.frame, "craft"); end
	if ( WL.Smelt and WL.Smelt.frame ) then WL.PlacePanel(WL.Smelt.frame, "smelt"); end
	if ( WL.Skills and WL.Skills.frame ) then WL.PlacePanel(WL.Skills.frame, "skills"); end
end

-- Touches par defaut (WowlheimCore.DEFAULT_KEYS) : une seule fois, seulement sur des touches libres.
-- Touche liee a une action, lisible (« ALT-A » -> « Alt+A ») ; defaut si rien (API absente, aucune touche).
function WL.KeyText(action, default)
	local k = GetBindingKey and GetBindingKey(action);
	if ( not k or k == "" ) then return default; end
	k = string.gsub(k, "ALT%-", "Alt+");
	k = string.gsub(k, "CTRL%-", "Ctrl+");
	k = string.gsub(k, "SHIFT%-", "Maj+");
	k = string.gsub(k, "MOUSEWHEELUP", "molette haut");
	k = string.gsub(k, "MOUSEWHEELDOWN", "molette bas");
	return k;
end

function WL.ApplyDefaultBindings()
	if ( not (WowlheimDB and GetBindingAction and SetBinding and SaveBindings) ) then return nil; end
	return Core.ApplyDefaultBindings(WowlheimDB, {
		action = function(key) return GetBindingAction(key); end,
		keyOf = function(action) return GetBindingKey(action); end,
		set = function(key, action) SetBinding(key, action); end,
		save = function()
			local set = 1;
			if ( GetCurrentBindingSet ) then set = GetCurrentBindingSet(); end
			SaveBindings(set);
		end,
	});
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
	local M, G = WL.MARGIN, WL.GAP;
	local width = M * 2 + WL.COLS * WL.CELL + WL.SCROLL_W;                  -- 496
	local gridH = WL.ROWS * WL.CELL;
	local infoW = width - M * 2;                                            -- 464
	local infoY = WL.GRID_Y + gridH + G;
	local msgY = infoY + WL.INFO_H + G;
	local height = msgY + WL.MSG_H + G;                                     -- 400

	local f = CreateFrame("Frame", "WowlheimFrame", UIParent);
	f:SetWidth(width); f:SetHeight(height);
	-- en bas a droite au-dessus des barres d'action (WowlheimCore.PanelDefaultPos) : le personnage et le sol restent visibles
	WL.PlacePanel(f, "hammer");
	f:SetFrameStrata("MEDIUM");
	if ( f.SetToplevel ) then f:SetToplevel(1); end
	WoodBackdrop(f, 16);
	f:EnableMouse(1);
	f:SetMovable(1);
	f:RegisterForDrag("LeftButton");
	f:SetScript("OnDragStart", function() if ( IsShiftKeyDown() ) then this:StartMoving(); end end);
	f:SetScript("OnDragStop", function() this:StopMovingOrSizing(); WL.SavePanel(this, "hammer"); end);
	f:SetScript("OnMouseUp", function() if ( arg1 == "RightButton" ) then WL.Cancel(); end end);
	-- fermeture du menu par le joueur (Echap, bascule) = fin de la pose ; masquage pour la pose (WL.HideForPlacement) : non
	f:SetScript("OnHide", function()
		if ( WL.searchBox ) then WL.searchBox:ClearFocus(); end
		HideTooltip();
		if ( not WL.keepPose ) then WL.Cancel(); end
		WL.UpdateBanner();
	end);
	f:SetScript("OnShow", function() WL.autoCat = 1; WL.RecountBags(); WL.RequestKnown(); WL.Update(); WL.UpdateBanner(); end);
	EnableWheel(f);
	f:Hide();
	WL.frame = f;
	table.insert(UISpecialFrames, "WowlheimFrame");

	-- Bouton de fermeture (comme Echap ou la touche du menu : fin de la pose), aligne sur la ligne des onglets
	local close = CreateFrame("Button", "WowlheimClose", f);
	close:SetWidth(WL.CLOSE); close:SetHeight(WL.CLOSE);
	close:SetPoint("TOPRIGHT", f, "TOPRIGHT", -M, -WL.TOP);
	WoodBackdrop(close, 12);
	close:SetBackdropColor(0.30, 0.19, 0.09, 0.95);
	local cfs = Label(close, "WowlheimCloseText", "GameFontNormal", WL.CLOSE, WL.CLOSE, "CENTER", "MIDDLE");
	cfs:SetPoint("CENTER", close, "CENTER", 0, 1);
	cfs:SetText("x");
	AddHighlight(close, "Interface\\Buttons\\UI-Listbox-Highlight2");
	close:SetScript("OnClick", function() WL.Hide(); end);

	-- Onglets de categories : largeur proportionnelle au libelle (« Construction lourde » est 3 fois plus long que
	-- « Divers ») + part egale de la place restante ; libelle borne a l'onglet. Place laissee a droite pour la fermeture.
	WL.tabs = {};
	local ncat = table.getn(Data.categories);
	local TAB_GAP = 4;
	local avail = width - M * 2 - WL.CLOSE - G - TAB_GAP * (ncat - 1);    -- 416 pour 5 onglets
	local natural, total = {}, 0;
	local c = 1;
	while c <= ncat do
		local t = CreateFrame("Button", "WowlheimTab" .. c, f);
		local fs = t:CreateFontString("WowlheimTab" .. c .. "Text", "OVERLAY", "GameFontNormalSmall");
		fs:SetText(Data.categories[c]);
		natural[c] = TextWidth(fs, Data.categories[c], 5.5) + 16;
		total = total + natural[c];
		t.label = fs;
		WL.tabs[c] = t;
		c = c + 1;
	end
	local extra = (avail - total) / ncat;
	local x = M;
	c = 1;
	while c <= ncat do
		local t = WL.tabs[c];
		local tw = natural[c] + extra;
		if ( extra < 0 ) then tw = avail / ncat; end        -- libelles trop longs : onglets egaux, libelles raccourcis
		tw = math.floor(tw);
		t:SetWidth(tw); t:SetHeight(WL.TAB_H);
		t:SetPoint("TOPLEFT", f, "TOPLEFT", x, -WL.TOP);
		x = x + tw + TAB_GAP;
		WoodBackdrop(t, 12);
		t:SetID(c);
		local fs = t.label;
		fs:SetWidth(tw - 8); fs:SetHeight(12);
		fs:SetJustifyH("CENTER"); fs:SetJustifyV("MIDDLE");
		fs:SetPoint("CENTER", t, "CENTER", 0, 0);
		FitText(fs, Data.categories[c], tw - 8);
		AddHighlight(t, "Interface\\Buttons\\UI-Listbox-Highlight2");
		t:RegisterForClicks("LeftButtonUp", "RightButtonUp");
		t:SetScript("OnClick", function()
			if ( arg1 == "RightButton" ) then WL.Cancel(); return; end
			WL.SetCategory(this:GetID());
		end);
		EnableWheel(t);
		c = c + 1;
	end

	-- Ligne de recherche : champ a gauche (nom / description, sans accents ni casse ; pendant une recherche, toutes les
	-- categories, onglets deselectionnes) ; rotation et mode a droite, en zones fixes alignees a droite.
	WL.searchBox = SearchBox("WowlheimSearch", f, 200, "Rechercher une pièce...", function(t) WL.SetSearch(t); end, WL.SEARCH_H);
	WL.searchBox:SetPoint("TOPLEFT", f, "TOPLEFT", M, -WL.SEARCH_Y);
	local mode = Label(f, "WowlheimMode", "GameFontNormalSmall", 104, WL.SEARCH_H, "RIGHT", "MIDDLE");
	mode:SetPoint("TOPRIGHT", f, "TOPRIGHT", -M, -WL.SEARCH_Y);
	WL.modeText = mode;
	local rot = Label(f, "WowlheimInfoRot", "GameFontHighlightSmall", 112, WL.SEARCH_H, "RIGHT", "MIDDLE");
	rot:SetPoint("TOPRIGHT", f, "TOPRIGHT", -(M + 104 + G), -WL.SEARCH_Y);
	WL.infoRot = rot;

	-- Grille d'icones
	local grid = CreateFrame("Frame", "WowlheimGrid", f);
	grid:SetWidth(WL.COLS * WL.CELL); grid:SetHeight(gridH);
	grid:SetPoint("TOPLEFT", f, "TOPLEFT", M, -WL.GRID_Y);
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
	local empty = Label(grid, "WowlheimGridEmpty", "GameFontDisableSmall", WL.COLS * WL.CELL - 48, 36, "CENTER", "MIDDLE");
	empty:SetPoint("CENTER", grid, "CENTER", 0, 0);
	empty:Hide();
	WL.emptyText = empty;

	-- Defilement (fleches a droite de la grille ; Maj + molette)
	local up = CreateFrame("Button", "WowlheimScrollUp", f);
	up:SetWidth(20); up:SetHeight(20);
	up:SetPoint("TOPLEFT", grid, "TOPRIGHT", 4, 0);
	up:SetNormalTexture("Interface\\Buttons\\UI-ScrollBar-ScrollUpButton-Up");
	up:SetPushedTexture("Interface\\Buttons\\UI-ScrollBar-ScrollUpButton-Down");
	up:SetDisabledTexture("Interface\\Buttons\\UI-ScrollBar-ScrollUpButton-Disabled");
	up:SetScript("OnClick", function() WL.SetScroll(WL.scroll - 1); end);
	WL.upButton = up;
	local down = CreateFrame("Button", "WowlheimScrollDown", f);
	down:SetWidth(20); down:SetHeight(20);
	down:SetPoint("BOTTOMLEFT", grid, "BOTTOMRIGHT", 4, 0);
	down:SetNormalTexture("Interface\\Buttons\\UI-ScrollBar-ScrollDownButton-Up");
	down:SetPushedTexture("Interface\\Buttons\\UI-ScrollBar-ScrollDownButton-Down");
	down:SetDisabledTexture("Interface\\Buttons\\UI-ScrollBar-ScrollDownButton-Disabled");
	down:SetScript("OnClick", function() WL.SetScroll(WL.scroll + 1); end);
	WL.downButton = down;

	-- Encadre de la piece (sous la grille, comme dans Valheim), 464 x 112, marge interieure 8 :
	--   icone 40 | colonne texte x 56 (nom 1 ligne, description 4 lignes, station 1 ligne en bas)
	--   ressources : 2 colonnes x 3 lignes a droite (icone 28 + « possede/requis »), info-bulle = nom de l'objet.
	-- Sans ressources a afficher (aide, Reparer / Demolir), la description prend toute la largeur.
	local info = CreateFrame("Frame", "WowlheimInfo", f);
	info:SetWidth(infoW); info:SetHeight(WL.INFO_H);
	info:SetPoint("TOPLEFT", f, "TOPLEFT", M, -infoY);
	WoodBackdrop(info, 12);
	info:SetBackdropColor(0.10, 0.07, 0.04, 0.9);
	EnableWheel(info);
	-- info-bulle : nom et description complets. Clic droit / Maj+glisser transmis au panneau (comme partout ailleurs).
	info:EnableMouse(1);
	info:RegisterForDrag("LeftButton");
	info:SetScript("OnDragStart", function() if ( IsShiftKeyDown() ) then WL.frame:StartMoving(); end end);
	info:SetScript("OnDragStop", function() WL.frame:StopMovingOrSizing(); WL.SavePanel(WL.frame, "hammer"); end);
	info:SetScript("OnMouseUp", function() if ( arg1 == "RightButton" ) then WL.Cancel(); end end);
	info:SetScript("OnEnter", function()
		local e = WL.hover or WL.selected;
		if ( e ) then ShowTooltip(this, e.name, { e.desc, WL.infoStation.full, n = 2 }); end
	end);
	info:SetScript("OnLeave", HideTooltip);
	WL.info = info;

	local COST_COL, COST_ROW = 84, 32;
	local costX = infoW - G - (COST_COL * 2 - 4);                       -- 292 : colonnes a 292 et 376, bord a 456
	WL.INFO_TEXT_X = 56;
	WL.INFO_TEXT_W = costX - G - WL.INFO_TEXT_X;                         -- 228 a cote des ressources
	WL.INFO_TEXT_WIDE = infoW - G - WL.INFO_TEXT_X;                      -- 400 sans ressources

	local bigIcon = info:CreateTexture("WowlheimInfoIcon", "ARTWORK");
	bigIcon:SetWidth(40); bigIcon:SetHeight(40);
	bigIcon:SetPoint("TOPLEFT", info, "TOPLEFT", G, -G);
	WL.infoIcon = bigIcon;

	local name = Label(info, "WowlheimInfoName", "GameFontNormalLarge", WL.INFO_TEXT_W, 18, "LEFT", "MIDDLE");
	name:SetPoint("TOPLEFT", info, "TOPLEFT", WL.INFO_TEXT_X, -G);
	name:SetTextColor(ORANGE[1], ORANGE[2], ORANGE[3]);
	WL.infoName = name;

	local desc = Label(info, "WowlheimInfoDesc", "GameFontHighlightSmall", WL.INFO_TEXT_W, 56, "LEFT", "TOP");
	desc:SetPoint("TOPLEFT", info, "TOPLEFT", WL.INFO_TEXT_X, -30);
	WL.infoDesc = desc;

	local station = Label(info, "WowlheimInfoStation", "GameFontNormalSmall", costX - G * 2, 12, "LEFT", "MIDDLE");
	station:SetPoint("BOTTOMLEFT", info, "BOTTOMLEFT", G, G);
	WL.infoStation = station;

	WL.costSlots = {};
	local s = 1;
	while s <= WL.COST_SLOTS do
		local slot = CreateFrame("Frame", "WowlheimCost" .. s, info);
		slot:SetWidth(COST_COL - 4); slot:SetHeight(28);
		slot:SetPoint("TOPLEFT", info, "TOPLEFT", costX + math.mod(s - 1, 2) * COST_COL, -G - math.floor((s - 1) / 2) * COST_ROW);
		slot:EnableMouse(1);
		slot:SetScript("OnMouseUp", function() if ( arg1 == "RightButton" ) then WL.Cancel(); end end);
		slot:SetScript("OnEnter", function()
			if ( this.item ) then
				ShowTooltip(this, WL.ItemName(this.item), { "Possédé : " .. this.have .. "  -  Requis : " .. this.need, n = 1 });
			end
		end);
		slot:SetScript("OnLeave", HideTooltip);
		local ic = slot:CreateTexture("WowlheimCost" .. s .. "Icon", "ARTWORK");
		ic:SetWidth(28); ic:SetHeight(28);
		ic:SetPoint("LEFT", slot, "LEFT", 0, 0);
		local txt = Label(slot, "WowlheimCost" .. s .. "Text", "NumberFontNormal", COST_COL - 4 - 32, 16, "LEFT", "MIDDLE");
		txt:SetPoint("LEFT", ic, "RIGHT", 4, 0);
		slot.icon = ic;
		slot.text = txt;
		WL.costSlots[s] = slot;
		s = s + 1;
	end

	-- Ligne de message (sous l'encadre, toute la largeur, une ligne ; « ... » au-dela)
	local msg = Label(f, "WowlheimMsg", "GameFontHighlightSmall", infoW, WL.MSG_H, "LEFT", "MIDDLE");
	msg:SetPoint("TOPLEFT", f, "TOPLEFT", M, -msgY);
	WL.msgText = msg;
end

-- ------------------------------------------------------------------------------------------------
-- Mise a jour
-- ------------------------------------------------------------------------------------------------
-- Texte de recherche (OnTextChanged du champ) : resultats de toutes les categories tant qu'il n'est pas vide
function WL.SetSearch(text)
	text = text or "";
	if ( text == WL.query ) then return; end
	WL.query = text;
	WL.scroll = 0;
	WL.hover = nil;
	WL.Update();
end

-- Clic sur un onglet pendant une recherche : la recherche est effacee, retour a la categorie (Valheim)
function WL.SetCategory(cat)
	if ( WL.query ~= "" ) then
		WL.query = "";
		if ( WL.searchBox ) then WL.searchBox:SetText(""); WL.searchBox:ClearFocus(); WL.searchBox.hint:Show(); end
	end
	WL.cat = cat;
	WL.scroll = 0;
	WL.hover = nil;
	WL.autoCat = nil;            -- choix du joueur : plus de changement automatique d'onglet jusqu'a la prochaine ouverture
	WL.catRemembered = 1;
	if ( WowlheimDB ) then WowlheimDB.cat = cat; end
	WL.Update();
end

-- A l'ouverture du menu (et tant que le joueur n'a pas clique un onglet) : onglet memorise s'il contient une piece connue ;
-- sinon (premier usage, onglet vide) premier onglet qui en contient une (Core.PickCategory). Reevalue a chaque mise a
-- jour : la reponse known arrive apres l'ouverture et peut vider l'onglet courant.
function WL.AutoCategory()
	if ( not WL.autoCat or WL.query ~= "" ) then return; end
	local remembered = WL.catRemembered or (WowlheimDB and WowlheimDB.cat);
	local cat = Core.PickCategory(Data.pieces, WL.cat, remembered, table.getn(Data.categories), WL.known, WL.counts, WL.NearStations());
	if ( cat ~= WL.cat ) then
		WL.cat = cat;
		WL.scroll = 0;
	end
	WL.catRemembered = 1;
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
		if ( c == WL.cat and not WL.entries.searching ) then
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
	if ( WL.entries.n == 0 ) then
		if ( WL.entries.searching ) then
			WL.emptyText:SetText("Aucune pièce connue ne correspond à cette recherche.");
		else
			WL.emptyText:SetText("Aucune pièce connue ici : ramassez de nouveaux matériaux pour en découvrir.");
		end
		WL.emptyText:Show();
	else
		WL.emptyText:Hide();
	end
	if ( max > 0 ) then
		WL.upButton:Show(); WL.downButton:Show();
		if ( WL.scroll > 0 ) then WL.upButton:Enable(); else WL.upButton:Disable(); end
		if ( WL.scroll < max ) then WL.downButton:Enable(); else WL.downButton:Disable(); end
	else
		WL.upButton:Hide(); WL.downButton:Hide();
	end
end

-- Colonne de texte de l'encadre : etroite a cote des ressources, pleine largeur sans ressources (aide, Reparer / Demolir)
local function InfoTextWidth(wide)
	local w, h = WL.INFO_TEXT_W, 56;
	if ( wide ) then w, h = WL.INFO_TEXT_WIDE, 72; end
	WL.infoName:SetWidth(w);
	WL.infoDesc:SetWidth(w); WL.infoDesc:SetHeight(h);
	return w;
end

function WL.UpdateInfo()
	if ( not WL.frame ) then return; end
	local e = WL.hover or WL.selected;
	local s;
	local rows = { n = 0 };
	if ( e and e.costs ) then
		local _;
		_, rows = Core.Affordability(e.costs, WL.counts);
	end
	local nrows = 0;
	while rows[nrows + 1] do nrows = nrows + 1; end
	local textW = InfoTextWidth(nrows == 0);
	if ( not e ) then
		WL.infoIcon:Hide();
		WL.SetTitle(WL.infoName, "Marteau", textW, ORANGE[1], ORANGE[2], ORANGE[3]);
		-- aide courte, une commande par ligne (touches en orange) ; le detail reste dans docs/BUILD_CONTROLS.md
		WL.infoDesc:SetText(Core.HammerHelp(WL.KeyText("WOWLHEIM_ROTATE_LEFT", "Alt+A"), WL.KeyText("WOWLHEIM_ROTATE_RIGHT", "Alt+E"),
			WL.KeyText("WOWLHEIM_TOGGLE", "Y")));
		WL.infoStation:SetText("");
		WL.infoStation.full = nil;
	else
		WL.infoIcon:Show();
		WL.EntryIcon(WL.infoIcon, e);
		SetGrey(WL.infoIcon, not WL.EntryAffordable(e));
		WL.SetTitle(WL.infoName, e.name, textW, ORANGE[1], ORANGE[2], ORANGE[3]);
		WL.infoDesc:SetText(e.desc or "");
		if ( e.station and e.station ~= "" ) then
			local full = "Requiert : " .. (Data.stations[e.station] or e.station);
			WL.infoStation.full = full;
			FitText(WL.infoStation, full, WL.INFO_TEXT_W + WL.INFO_TEXT_X - WL.GAP);
		else
			WL.infoStation:SetText("");
			WL.infoStation.full = nil;
		end
	end
	-- ressources requises : icone + « possede/requis » (rouge si insuffisant) ; nom de l'objet en info-bulle
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
			slot.item, slot.have, slot.need = r.item, r.have, r.need;
			slot:Show();
		else
			slot.icon:Hide();
			slot.text:SetText("");
			slot.item = nil;
			slot:Hide();
		end
		s = s + 1;
	end
	WL.infoRot:SetText("Rotation : " .. Core.RotDegrees(WL.state.rot) .. "°");
	-- mode seul (zone fixe de 104 px) : la pose continue est rappelee par le bandeau en haut de l'ecran
	local mode = "|cffffad38Construction|r";
	if ( WL.state.mode == "repair" ) then mode = "|cff40ff40Réparer|r";
	elseif ( WL.state.mode == "remove" ) then mode = "|cffff4040Démolir|r"; end
	WL.modeText:SetText(mode);
end

function WL.Update()
	if ( not WL.frame ) then return; end
	WL.AutoCategory();
	WL.entries = Core.MenuEntries(Data.pieces, WL.cat, WL.query, WL.known, WL.counts, WL.NearStations());
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
BINDING_NAME_WOWLHEIM_CRAFT = "Wowlheim : fabrication";
BINDING_NAME_WOWLHEIM_SMELT = "Wowlheim : fonderie / four à charbon";
BINDING_NAME_WOWLHEIM_SKILLS = "Wowlheim : compétences";
BINDING_NAME_WOWLHEIM_REMOVE = "Wowlheim : démolir la pièce sous la souris";

SLASH_WOWLHEIM1 = "/wl";
SLASH_WOWLHEIM2 = "/wowlheim";
SlashCmdList["WOWLHEIM"] = function(msg)
	if ( msg == "reset" ) then
		WL.ResetPanels();
		WL.RestoreBuildKeys();      -- liaisons temporaires retablies (reposees a l'image suivante si le marteau est en main)
		DEFAULT_CHAT_FRAME:AddMessage("Wowlheim : panneaux remis à leur place par défaut, liaisons de la souris rétablies.");
		return;
	end
	if ( msg == "qe on" or msg == "qe off" ) then
		WL.RestoreBuildKeys();
		if ( WowlheimDB ) then
			if ( msg == "qe on" ) then WowlheimDB.qe = 1; else WowlheimDB.qe = nil; end
		end
		WL.UpdateBuildKeys();
		local on = "non";
		if ( msg == "qe on" ) then on = "oui"; end
		DEFAULT_CHAT_FRAME:AddMessage("Wowlheim : Q / E tournent la pièce en construction : " .. on .. ".");
		return;
	end
	if ( msg == "skills" ) then
		if ( WL.Skills ) then WL.Skills.Toggle(); end
		return;
	end
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
		WL.QueuePreload();
	elseif ( not eq and WL.hammerWasEquipped ) then
		WL.Hide();
	end
	WL.hammerWasEquipped = eq;
	WL.UpdateBuildKeys();
	WL.UpdateBanner();
end

-- Titres natifs coupes en « ... » (capture p2/60_bag : sac, nom de zone de la minicarte) : FontString de 12 px de haut pour
-- une police de 12 (GameFontHighlight / GameFontNormal) ; a certaines echelles d'interface la ligne ne tient plus et le
-- client n'affiche que « ... ». Hauteur portee a 16 (largeur et ancrage inchanges).
function WL.FixNativeTitles()
	if ( not getglobal ) then return; end
	local i = 1;
	while i <= 12 do
		local fs = getglobal("ContainerFrame" .. i .. "Name");
		if ( fs and fs.SetHeight ) then fs:SetHeight(16); end
		i = i + 1;
	end
	local z = getglobal("MinimapZoneText");
	if ( z and z.SetHeight ) then z:SetHeight(16); end
	local zb = getglobal("MinimapZoneTextButton");
	if ( zb and zb.SetHeight ) then zb:SetHeight(16); end
end
WL.FixNativeTitles();

local ef = CreateFrame("Frame", "WowlheimEvents", UIParent);
ef:RegisterEvent("VARIABLES_LOADED");
ef:RegisterEvent("PLAYER_ENTERING_WORLD");
ef:RegisterEvent("UNIT_INVENTORY_CHANGED");
ef:RegisterEvent("BAG_UPDATE");
ef:RegisterEvent("CHAT_MSG_SYSTEM");
ef:RegisterEvent("PLAYER_LEAVING_WORLD");
ef:RegisterEvent("PLAYER_LOGOUT");
ef:RegisterEvent("SPELLCAST_START");
ef:RegisterEvent("SPELLCAST_STOP");
ef:RegisterEvent("SPELLCAST_FAILED");
ef:RegisterEvent("SPELLCAST_INTERRUPTED");
ef:SetScript("OnEvent", function()
	if ( event == "CHAT_MSG_SYSTEM" ) then
		if ( arg1 and string.sub(arg1, 1, 4) == Core.PREFIX ) then
			WL.OnSystem(arg1);
		end
	elseif ( event == "SPELLCAST_START" or event == "SPELLCAST_STOP" ) then
		Core.TargetWatchCast(WL.tw, GetTime());      -- le ciblage s'est termine par une pose (clic gauche)
	elseif ( event == "SPELLCAST_FAILED" or event == "SPELLCAST_INTERRUPTED" ) then
		-- pose ratee cote client (portee, deplacement...) : la piece reste choisie, le ciblage est relance
		if ( WL.tw.active or WL.tw.endedAt ) then
			Core.TargetWatchCast(WL.tw, GetTime());
			if ( WL.state.continuous and WL.state.mode == "build" ) then
				WL.state.pending = nil;
				WL.relaunchAt = GetTime() + 0.25;
			end
		end
	elseif ( event == "PLAYER_LEAVING_WORLD" or event == "PLAYER_LOGOUT" ) then
		-- deconnexion, /reload, changement de continent : liaisons d'origine (rien n'est enregistre par SaveBindings)
		WL.inWorld = nil;
		WL.RestoreBuildKeys();
	elseif ( event == "BAG_UPDATE" ) then
		WL.bagsDirty = 1;
		WL.knownDirty = 1;
	elseif ( event == "VARIABLES_LOADED" ) then
		if ( not WowlheimDB ) then WowlheimDB = {}; end
		-- liaisons temporaires d'avant un /reload ou un plantage : retablies a PLAYER_ENTERING_WORLD
		if ( type(WowlheimDB.tempBinds) == "table" ) then
			for k, v in pairs(WL.tempBinds) do WowlheimDB.tempBinds[k] = v; end
		else
			WowlheimDB.tempBinds = WL.tempBinds;
		end
		WL.tempBinds = WowlheimDB.tempBinds;
		if ( WowlheimDB.cat and Data.categories[WowlheimDB.cat] ) then WL.cat = WowlheimDB.cat; end
	elseif ( event == "PLAYER_ENTERING_WORLD" ) then
		WL.bagsDirty = 1;
		WL.RecoverBuildKeys();          -- AVANT ApplyDefaultBindings (SaveBindings) : aucune liaison temporaire enregistree
		-- touches par defaut, une seule fois (liaisons du personnage chargees a l'entree en jeu)
		WL.ApplyDefaultBindings();
		WL.inWorld = 1;
		WL.FixNativeTitles();
		WL.preloadDone = {};            -- la DLL libere les modeles precharges au dechargement de la carte
		-- DLL : apparition ET disparition instantanees des pieces, des arbres / roches (creatures) et des ramassables, au
		-- lieu des fondus de 2 s du client (actif par defaut)
		if ( WowlheimSetInstantFade ) then
			WowlheimSetInstantFade(Core.PIECE_ENTRY_MIN, Core.PIECE_ENTRY_MAX, 9300000, 9300099, 9130000, 9139999);
		end
		WL.CheckHammer();
		if ( WL.HammerEquipped() ) then WL.QueuePreload(); end   -- modeles liberes par la DLL au changement de carte
		if ( WL.Skills ) then WL.Skills.OnEnterWorld(); end   -- competences et endurance (.build api skills)
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
		WL.UpdateBanner();          -- ressources manquantes de la piece en cours de pose
	end
	WL.UpdateRings(GetTime());
	WL.UpdateBuildKeys();
	WL.WatchTargeting(GetTime());
	WL.UpdateHover();               -- piece visee : surbrillance + info-bulle (DLL)
	WL.UpdateGhost(GetTime());
	WL.RunPreload();
	if ( WL.Skills ) then WL.Skills.OnUpdate(GetTime()); end
	-- objets connus : nouvelle interrogation apres un changement des sacs (panneau ouvert) ou une connaissance acquise (KN|,
	-- meme panneaux fermes : annonce « Nouvelle piece »), au plus une par KNOWN_POLL s
	if ( ((WL.knownDirty and WL.PanelsShown()) or WL.knownForce) and not WL.known.unsupported
		and GetTime() - WL.knownAt >= Core.KNOWN_POLL ) then
		WL.RequestKnown();
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
