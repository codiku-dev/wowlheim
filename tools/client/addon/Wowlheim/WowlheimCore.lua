-- WowlheimCore.lua : logique pure (sans API WoW), testable hors du jeu (tools/client/addon/test_core.py).
-- Lua 5.0 : pas de '#', pas de '%' arithmetique, pas de string.match/gmatch, pas de select, pas de '...'.
-- Protocole serveur -> client : messages systeme commencant par "[WL]" ; format "[WL]<type>|champ|champ..." ; types :
--   M|texte                     message lisible
--   P|id|nom|type|pv|appui|etabli|item:n,item:n   piece du catalogue (ancien protocole, le catalogue vient de WowlheimData)
--   I|item:n,item:n             materiaux Wowlheim du joueur
--   C|id|nom|station|sortie:n|item:n,item:n|niveau_min   recette
--   S|guid|utilisable|couverture|niveau          etabli a portee
--   E|texte   erreur ;   D|commande|1ou0   fin de reponse
-- Client -> serveur : ".build api <commande> [args]" par SendChatMessage (canal SAY) :
--   select <pieceId> <rot 0..15>  |  mode <build|remove|repair>  |  inv
-- La pose elle-meme passe par le sort a cible au sol du marteau (UseInventoryItem(16)).

WowlheimCore = {};
local C = WowlheimCore;

C.PREFIX = "[WL]";
C.ROT_STEPS = 16;          -- pas de 22,5 degres
C.HAMMER_ID = 9201100;
C.HAMMER_SLOT = 16;        -- main droite

-- Decoupe "a|b||d" en table {"a","b","","d"} (Lua 5.0 : pas de gmatch ; string.find avec init).
function C.Split(s, sep)
	local out = {};
	local n = 0;
	local start = 1;
	while true do
		local i = string.find(s, sep, start, true);
		if ( not i ) then
			n = n + 1;
			out[n] = string.sub(s, start);
			break;
		end
		n = n + 1;
		out[n] = string.sub(s, start, i - 1);
		start = i + string.len(sep);
	end
	return out;
end

-- "9200001:2,9200002:1" -> { {item=9200001,count=2}, {item=9200002,count=1} } (n = nombre d'entrees)
function C.ParseItems(s)
	local list = {};
	local n = 0;
	if ( not s or s == "" ) then
		list.n = 0;
		return list;
	end
	local parts = C.Split(s, ",");
	local i = 1;
	while parts[i] do
		local kv = C.Split(parts[i], ":");
		n = n + 1;
		list[n] = { item = tonumber(kv[1]), count = tonumber(kv[2]) };
		i = i + 1;
	end
	list.n = n;
	return list;
end

-- Analyse une ligne "[WL]..." ; renvoie une table {type=..., ...} ou nil si ce n'est pas une ligne du protocole.
function C.ParseLine(line)
	if ( not line or string.sub(line, 1, 4) ~= C.PREFIX ) then
		return nil;
	end
	local body = string.sub(line, 5);
	local f = C.Split(body, "|");
	local t = f[1];
	if ( t == "M" ) then
		return { type = "M", text = string.sub(body, 3) };
	elseif ( t == "P" ) then
		return { type = "P", id = tonumber(f[2]), name = f[3], kind = f[4], hp = tonumber(f[5]), supports = (f[6] == "1"), bench = (f[7] == "1"), cost = C.ParseItems(f[8]) };
	elseif ( t == "I" ) then
		return { type = "I", items = C.ParseItems(f[2]) };
	elseif ( t == "C" ) then
		local out = C.Split(f[5] or "", ":");
		return { type = "C", id = tonumber(f[2]), name = f[3], station = f[4], outItem = tonumber(out[1]), outCount = tonumber(out[2]), ingredients = C.ParseItems(f[6]), minLevel = tonumber(f[7]) or 1 };
	elseif ( t == "S" ) then
		return { type = "S", guid = tonumber(f[2]), usable = (f[3] == "1"), cover = tonumber(f[4]), level = tonumber(f[5]) or 1 };
	elseif ( t == "E" ) then
		return { type = "E", text = string.sub(body, 3) };
	elseif ( t == "D" ) then
		return { type = "D", command = f[2], ok = (f[3] == "1") };
	end
	return { type = "?", raw = body };
end

-- Ancienne commande de pose par decalage (conservee pour le debogage : /wl place ...).
function C.PlaceCommand(id, fwd, right, up, rot)
	return ".build api place " .. id .. " " .. (fwd or 3) .. " " .. (right or 0) .. " " .. (up or 0) .. " " .. (rot or 0);
end

function C.SelectCommand(id, rot)
	return ".build api select " .. id .. " " .. (rot or 0);
end

function C.ModeCommand(mode)
	return ".build api mode " .. mode;
end

-- Une pose est-elle possible avec cet inventaire ? (liste {item,count} ; aide seulement : le serveur reste l'autorite)
function C.CanAfford(cost, inv)
	local missing = {};
	local m = 0;
	local i = 1;
	while cost[i] do
		local have = 0;
		local j = 1;
		while inv[j] do
			if ( inv[j].item == cost[i].item ) then
				have = inv[j].count;
			end
			j = j + 1;
		end
		if ( have < cost[i].count ) then
			m = m + 1;
			missing[m] = { item = cost[i].item, have = have, need = cost[i].count };
		end
		i = i + 1;
	end
	return m == 0, missing;
end

-- ------------------------------------------------------------------------------------------------
-- Inventaire (sacs) et couts au format WowlheimData : costs = { {itemId, n}, ... } ; counts = { [itemId] = n }
-- ------------------------------------------------------------------------------------------------

-- "|cffffffff|Hitem:9200001:0:0:0|h[Bois]|h|r" -> 9200001
function C.ItemIdFromLink(link)
	if ( not link ) then return nil; end
	local _, _, id = string.find(link, "item:(%d+)");
	if ( id ) then return tonumber(id); end
	return nil;
end

-- Compte les objets des sacs 0..4. api = { numSlots(bag), link(bag, slot), count(bag, slot) } (fonctions WoW enveloppees).
function C.CountBags(api)
	local counts = {};
	local bag = 0;
	while bag <= 4 do
		local slots = api.numSlots(bag) or 0;
		local slot = 1;
		while slot <= slots do
			local id = C.ItemIdFromLink(api.link(bag, slot));
			if ( id ) then
				local n = api.count(bag, slot) or 1;
				if ( n < 1 ) then n = 1; end
				counts[id] = (counts[id] or 0) + n;
			end
			slot = slot + 1;
		end
		bag = bag + 1;
	end
	return counts;
end

-- Renvoie ok, lignes { {item, need, have, ok}, ... } (n = nombre de lignes)
function C.Affordability(costs, counts)
	local rows = {};
	local n = 0;
	local all = true;
	local i = 1;
	while costs and costs[i] do
		local item = costs[i][1];
		local need = costs[i][2];
		local have = counts[item] or 0;
		n = n + 1;
		rows[n] = { item = item, need = need, have = have, ok = (have >= need) };
		if ( have < need ) then all = false; end
		i = i + 1;
	end
	rows.n = n;
	return all, rows;
end

-- ------------------------------------------------------------------------------------------------
-- Catalogue par categorie (Divers commence par les outils Reparer / Demolir, comme le marteau de Valheim)
-- ------------------------------------------------------------------------------------------------
C.SPECIALS = {
	{ special = "repair", name = "Réparer", desc = "Répare une construction endommagée : choisissez cet outil puis faites un clic droit sur la pièce posée.", station = "" },
	{ special = "remove", name = "Démolir", desc = "Démolit une construction : choisissez cet outil puis faites un clic droit sur la pièce posée. Une partie des matériaux est rendue.", station = "" },
};

function C.CategoryEntries(pieces, cat)
	local list = {};
	local n = 0;
	if ( cat == 1 ) then
		local s = 1;
		while C.SPECIALS[s] do
			n = n + 1;
			list[n] = C.SPECIALS[s];
			s = s + 1;
		end
	end
	local i = 1;
	while pieces and pieces[i] do
		if ( pieces[i].cat == cat ) then
			n = n + 1;
			list[n] = pieces[i];
		end
		i = i + 1;
	end
	list.n = n;
	return list;
end

-- Nombre maximal de lignes de defilement d'une grille cols x rows contenant n icones.
function C.MaxScroll(n, cols, rows)
	local total = math.ceil(n / cols);
	if ( total <= rows ) then return 0; end
	return total - rows;
end

function C.Clamp(v, lo, hi)
	if ( v < lo ) then return lo; end
	if ( v > hi ) then return hi; end
	return v;
end

-- ------------------------------------------------------------------------------------------------
-- Etat du marteau (pose continue facon Valheim). Les fonctions renvoient la liste des commandes de chat a envoyer
-- (n = nombre) et, pour ChoosePiece, s'il faut lancer le ciblage au sol (UseInventoryItem).
-- ------------------------------------------------------------------------------------------------
function C.NewState()
	return { mode = "build", rot = 0, piece = nil, continuous = nil, pending = nil };
end

local function Cmds()
	return { n = 0 };
end

local function Push(list, cmd)
	list.n = list.n + 1;
	list[list.n] = cmd;
end

function C.RotStep(rot, delta)
	local r = (rot or 0) + delta;
	while r < 0 do r = r + C.ROT_STEPS; end
	while r >= C.ROT_STEPS do r = r - C.ROT_STEPS; end
	return r;
end

function C.RotDegrees(rot)
	return rot * 22.5;
end

-- Clic gauche sur une piece : mode build si besoin, select, puis ciblage au sol.
function C.ChoosePiece(st, id)
	local out = Cmds();
	if ( st.mode ~= "build" ) then
		st.mode = "build";
		Push(out, C.ModeCommand("build"));
	end
	st.piece = id;
	Push(out, C.SelectCommand(id, st.rot));
	st.continuous = 1;
	st.pending = 1;
	return out, true;
end

-- Clic sur Reparer / Demolir.
function C.ChooseMode(st, mode)
	local out = Cmds();
	st.continuous = nil;
	st.pending = nil;
	if ( st.mode ~= mode ) then
		st.mode = mode;
		Push(out, C.ModeCommand(mode));
	end
	return out;
end

-- Molette / touches : renvoie la commande select a envoyer (ou rien si aucune piece choisie).
function C.Rotate(st, delta)
	local out = Cmds();
	st.rot = C.RotStep(st.rot, delta);
	if ( st.piece and st.mode == "build" ) then
		Push(out, C.SelectCommand(st.piece, st.rot));
	end
	return out;
end

-- Clic droit / Echap / fermeture : fin de la pose continue ; sortie des modes demolir/reparer.
function C.Cancel(st)
	local out = Cmds();
	st.continuous = nil;
	st.pending = nil;
	if ( st.mode ~= "build" ) then
		st.mode = "build";
		Push(out, C.ModeCommand("build"));
	end
	return out;
end

-- Le message du serveur annonce-t-il une pose reussie ?
function C.IsPlaceSuccess(m)
	if ( not m ) then return false; end
	if ( m.type == "D" and m.command == "place" and m.ok ) then return true; end
	if ( m.type == "M" and m.text and (string.find(m.text, "posée", 1, true) or string.find(m.text, "posee", 1, true)) ) then return true; end
	return false;
end

function C.IsPlaceFailure(m)
	if ( not m ) then return false; end
	if ( m.type == "D" and m.command == "place" and not m.ok ) then return true; end
	return false;
end

-- Traite un message serveur pour la pose continue. Renvoie "relaunch" si le ciblage doit etre relance.
-- Une pose = une seule relance (D|place|1 et M|...posee... peuvent arriver tous les deux : pending deduplique).
function C.OnServerMessage(st, m)
	if ( not st.pending ) then return nil; end
	if ( C.IsPlaceSuccess(m) ) then
		st.pending = nil;
		if ( st.continuous and st.mode == "build" and st.piece ) then
			return "relaunch";
		end
	elseif ( C.IsPlaceFailure(m) or (m and m.type == "E") ) then
		st.pending = nil;
		st.continuous = nil;
	end
	return nil;
end

-- Instant de relance compte tenu du temps de recharge du marteau (GetInventoryItemCooldown : start, duration).
function C.RelaunchTime(now, start, duration, delay)
	local t = now + (delay or 0.25);
	if ( start and duration and start > 0 and duration > 0 ) then
		local ready = start + duration + 0.05;
		if ( ready > t ) then t = ready; end
	end
	return t;
end
