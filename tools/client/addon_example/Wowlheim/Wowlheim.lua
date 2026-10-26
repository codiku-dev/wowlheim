-- Wowlheim.lua : addon d'exemple MINIMAL, ecrit pour Lua 5.0 / client 1.12.1 (build 5875).
-- NON TESTE en jeu (aucun pilotage du client possible). Voir docs/CLIENT_FEASIBILITY.md (H1).
--
-- Contraintes Lua 5.0 respectees : pas d'operateur '#' (-> getn), pas d'operateur '%'
-- (-> mod), pas de select / string.match / string.gmatch / hooksecurefunc / '...' en table
-- (-> variable implicite 'arg'), handlers d'evenements sans parametre : 'this', 'event',
-- 'arg1'..'arg9' sont des GLOBALES.
--
-- Protocole suppose cote serveur (a implementer, NON VERIFIE) : les retours destines a
-- l'addon sont des messages systeme commencant par WL_PREFIX ("[WL] ...").

Wowlheim = {};
local WL = Wowlheim;

WL.WL_PREFIX = "[WL]";
WL.debug = nil;          -- /wldebug : afficher aussi les retours normalement masques
WL.lastSent = 0;         -- GetTime() du dernier envoi
WL.REPLY_WINDOW = 5;     -- secondes pendant lesquelles on accepte une reponse

local function Print(msg)
	DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99Wowlheim|r: " .. msg);
end

-- Retour serveur : affiche dans la zone d'erreurs centrale (pas dans le chat).
local function ShowReply(text)
	UIErrorsFrame:AddMessage(text, 1.0, 0.82, 0.0, 1.0, 5);
end

-- ---------------------------------------------------------------------------
-- Envoi : commande de chat (canal SAY, texte commencant par '.') -> traitee par le serveur.
-- ---------------------------------------------------------------------------
function WL.Send(text)
	WL.lastSent = GetTime();
	SendChatMessage(text, "SAY");
end

SLASH_WLBUILD1 = "/wlbuild";
SlashCmdList["WLBUILD"] = function(msg)
	local id = tonumber(msg);
	if ( not id ) then
		Print("usage : /wlbuild <id_piece>");
		return;
	end
	WL.Send(".build place " .. id);
end

SLASH_WLDEBUG1 = "/wldebug";
SlashCmdList["WLDEBUG"] = function()
	if ( WL.debug ) then WL.debug = nil; else WL.debug = 1; end
	Print("debug " .. (WL.debug and "ON" or "OFF"));
end

-- Variante EXPERIMENTALE par canal d'addon (SendAddonMessage existe dans WoW.exe 5875, mais seuls
-- les types PARTY/RAID/GUILD/BATTLEGROUND sont acceptes ; le serveur doit les intercepter).
SLASH_WLBUILDA1 = "/wlbuilda";
SlashCmdList["WLBUILDA"] = function(msg)
	local id = tonumber(msg);
	if ( not id ) then
		Print("usage : /wlbuilda <id_piece>");
		return;
	end
	WL.lastSent = GetTime();
	SendAddonMessage("WL", "build place " .. id, "GUILD");
end

-- ---------------------------------------------------------------------------
-- Reception : evenements. Les arguments sont dans les globales arg1.. (Lua 5.0 / 1.12).
-- ---------------------------------------------------------------------------
local function IsWLReply(text)
	return text and strfind(text, WL.WL_PREFIX, 1, true) == 1;
end

local frame = CreateFrame("Frame", "WowlheimEventFrame", UIParent);
frame:RegisterEvent("CHAT_MSG_SYSTEM");
frame:RegisterEvent("CHAT_MSG_WHISPER");
frame:RegisterEvent("CHAT_MSG_ADDON");
frame:SetScript("OnEvent", function()
	if ( event == "CHAT_MSG_SYSTEM" or event == "CHAT_MSG_WHISPER" ) then
		if ( IsWLReply(arg1) ) then
			ShowReply(strsub(arg1, strlen(WL.WL_PREFIX) + 2));
		end
	elseif ( event == "CHAT_MSG_ADDON" ) then
		-- arg1 = prefixe, arg2 = texte, arg3 = type (PARTY/RAID/GUILD/BATTLEGROUND), arg4 = emetteur
		-- (ordre des arguments : INFERE, non verifie dans le client)
		if ( arg1 == "WL" ) then
			ShowReply(arg2);
		end
	end
end);

-- ---------------------------------------------------------------------------
-- Masquage : en 1.12 il n'y a PAS de ChatFrame_AddMessageEventFilter. Le XML des fenetres de chat
-- appelle la globale ChatFrame_OnEvent(event) a chaque evenement ; on la remplace par un wrapper.
-- ---------------------------------------------------------------------------
local Orig_ChatFrame_OnEvent = ChatFrame_OnEvent;
function ChatFrame_OnEvent(event)
	if ( not WL.debug and (event == "CHAT_MSG_SYSTEM" or event == "CHAT_MSG_WHISPER") and IsWLReply(arg1) ) then
		return;   -- on ne laisse pas passer a la fenetre de chat
	end
	Orig_ChatFrame_OnEvent(event);
end

Print("charge. /wlbuild <id>  /wldebug");
