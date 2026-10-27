-- WowlheimCore.lua : logique pure (sans API WoW), testable hors du jeu (tools/client/addon/test_core.py).
-- Lua 5.0 : pas de '#', pas de '%' arithmetique, pas de string.match/gmatch, pas de select, pas de '...'.
-- Protocole serveur -> client : messages systeme commencant par "[WL]" ; format "[WL]<type>|champ|champ..." ; types :
--   M|texte                     message lisible
--   P|id|nom|type|pv|appui|etabli|item:n,item:n   piece du catalogue (ancien protocole, le catalogue vient de WowlheimData)
--   I|item:n,item:n             materiaux Wowlheim du joueur
--   C|id|nom|station|sortie:n|item:n,item:n|niveau_min   recette
--   S|guid|utilisable|couverture|niveau          etabli a portee (seul l'etabli est detecte par le serveur)
--   SM|guid|kind|nom|file|maxMinerai|combustible|maxComb|objetComb|cuisson|secParProduit|actif|raison|file item:n|produits item:n
--                               fonderie / four a charbon (server/Wowlheim/Smelter.cpp, SmelterMgr::StatusLine)
--   A|n                         nombre d'unites ajoutees (smelter add)
--   ST|guid|kind|x|y|z|portee|dedans|n  station proche (stations) ; SG|guid|premier|x,y,z,o;...  contour de sa zone au sol
--   K|item:id,id,...  KS|kind:niveau,...  KP|piece,...  KR|recette,...   connaissances (known ; Valheim : m_knownMaterial,
--                               m_knownStations ; KP / KR : pieces / recettes connues calculees par le serveur). Listes longues
--                               coupees en plusieurs lignes au meme prefixe (concatenees) ; fin D|known|1
--   KN|item|id  KN|station|kind|niveau   connaissance acquise (spontane) : l'addon relance known
--   RS|guid|kind|niveau  RI|item|durabilite|max   station de reparation et objet abime reparable (repairable [guid])
--   R|item,item,...             objets repares (repairitems [guid]), puis M|Réparé : ...
--   OPEN|craft|guid|kind        clic sur une table de fabrication / forge / tailleur / table d'artisan (APRES ses lignes S|)
--   EN|cur10|max10|delai_ms|clignote  SK|id|niveau|pct  SKU|id|niveau  SKL|pct   endurance et competences (skills)
--   MD|id:prefab,id:prefab,...  modeles des pieces (models ; World\\Wowlheim\\<prefab>.m2), lignes concatenees jusqu'a D|models
--   CP|1|x|y|z|o|a  CP|0|x|y|z|o|a|raison   la pose au point donne serait acceptee / refusee (canplace : couleur du
--                               fantome) ; x, y, z, o : position APRES accroche, a = 1 si accrochee (ancien serveur : CP|1, CP|0|raison)
--   PI|guidHex|pv|pvmax|support|nom   etat de la piece visee (pieceinfo ; support = GetSupportColorValue, -1 = complet)
--   E|texte   erreur ;   D|commande|1ou0   fin de reponse
-- Client -> serveur : ".build api <commande> [args]" par SendChatMessage (canal SAY) :
--   select <pieceId> <rot 0..15>  |  mode <build|remove|repair>  |  inv  |  recipes  |  station  |  craft <id>  |  known
--   repairable  |  repairitems  |  skills
--   smelter status [guid]  |  smelter add <ore|fuel|itemId> [n] [guid]  |  smelter take [guid]
--   stations                    (cercles de portee des stations, marteau en mode construction)
--   removeguid <guidHex>        (clic milieu : demolir la piece sous la souris, docs/BUILD_CONTROLS.md)  |  models
--   use <guidHex>               (clic droit refuse par le client, « You are too far away. » : utiliser la piece a 3 m de son bord)
--   canplace <x> <y> <z> <rot>  (pendant le ciblage, au plus toutes les C.GHOST_POLL s : fantome vert / rouge, accroche)
--   pieceinfo <guidHex>         (piece sous la souris, marteau en main : sante et support, C.PIECEINFO_REFRESH s)
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

-- "x,y,z,o;x,y,z,o" -> { {x=,y=,z=,o=}, ... } (n = nombre de points ; un point incomplet est ignore)
function C.ParsePoints(s)
	local list = { n = 0 };
	if ( not s or s == "" ) then return list; end
	local parts = C.Split(s, ";");
	local i = 1;
	while parts[i] do
		local v = C.Split(parts[i], ",");
		local x, y, z, o = tonumber(v[1]), tonumber(v[2]), tonumber(v[3]), tonumber(v[4]);
		if ( x and y and z ) then
			list.n = list.n + 1;
			list[list.n] = { x = x, y = y, z = z, o = o or 0 };
		end
		i = i + 1;
	end
	return list;
end

-- "9200001,9200002" -> {9200001, 9200002} (numbers = true) ; "workbench,forge" -> {"workbench","forge"} ; entrees vides ignorees
function C.ParseList(s, numbers)
	local list = { n = 0 };
	if ( not s or s == "" ) then return list; end
	local parts = C.Split(s, ",");
	local i = 1;
	while parts[i] do
		local v = parts[i];
		if ( numbers ) then v = tonumber(v); end
		if ( v and v ~= "" ) then
			list.n = list.n + 1;
			list[list.n] = v;
		end
		i = i + 1;
	end
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
		return { type = "S", guid = tonumber(f[2]), usable = (f[3] == "1"), cover = tonumber(f[4]), level = tonumber(f[5]) or 1, kind = f[6] or "workbench" };
	elseif ( t == "SM" ) then
		return { type = "SM", guid = tonumber(f[2]), kind = f[3] or "", name = f[4] or "", queue = tonumber(f[5]) or 0,
			maxOre = tonumber(f[6]) or 0, fuel = tonumber(f[7]) or 0, maxFuel = tonumber(f[8]) or 0, fuelItem = tonumber(f[9]) or 0,
			bake = tonumber(f[10]) or 0, secPerProduct = tonumber(f[11]) or 0, active = (f[12] == "1"), why = f[13] or "",
			queueItems = C.ParseItems(f[14]), output = C.ParseItems(f[15]) };
	elseif ( t == "A" ) then
		return { type = "A", added = tonumber(f[2]) or 0 };
	elseif ( t == "ST" ) then
		return { type = "ST", guid = tonumber(f[2]), kind = f[3] or "", x = tonumber(f[4]) or 0, y = tonumber(f[5]) or 0,
			z = tonumber(f[6]) or 0, range = tonumber(f[7]) or 0, inside = (f[8] == "1"), n = tonumber(f[9]) or 0 };
	elseif ( t == "SG" ) then
		return { type = "SG", guid = tonumber(f[2]), first = tonumber(f[3]) or 0, points = C.ParsePoints(f[4]) };
	elseif ( t == "K" ) then
		-- « K|item:9200001,9200002 » : prefixe « item: » eventuel devant une entree (ignore)
		local raw = C.ParseList(f[2], false);
		local items = { n = 0 };
		local i = 1;
		while i <= raw.n do
			local _, _, id = string.find(raw[i], "(%d+)$");
			if ( id ) then items.n = items.n + 1; items[items.n] = tonumber(id); end
			i = i + 1;
		end
		return { type = "K", items = items };
	elseif ( t == "KS" ) then
		-- « KS|workbench:2,forge:1 » -> stations = { "workbench", "forge" }, levels = { workbench = 2, forge = 1 }
		local raw = C.ParseList(f[2], false);
		local out = { n = 0 };
		local levels = {};
		local i = 1;
		while i <= raw.n do
			local kv = C.Split(raw[i], ":");
			if ( kv[1] ~= "" ) then
				out.n = out.n + 1;
				out[out.n] = kv[1];
				levels[kv[1]] = tonumber(kv[2]) or 1;
			end
			i = i + 1;
		end
		return { type = "KS", stations = out, levels = levels };
	elseif ( t == "KP" ) then
		return { type = "KP", ids = C.ParseList(f[2], true) };
	elseif ( t == "KR" ) then
		return { type = "KR", ids = C.ParseList(f[2], true) };
	elseif ( t == "KN" ) then
		-- connaissance acquise : KN|item|<id>  ou  KN|station|<kind>|<niveau>
		if ( f[2] == "station" ) then
			return { type = "KN", what = "station", kind = f[3] or "", level = tonumber(f[4]) or 1 };
		end
		return { type = "KN", what = f[2] or "", item = tonumber(f[3]) };
	elseif ( t == "RS" ) then
		return { type = "RS", guid = tonumber(f[2]), kind = f[3] or "", level = tonumber(f[4]) or 1 };
	elseif ( t == "RI" ) then
		return { type = "RI", item = tonumber(f[2]), dur = tonumber(f[3]) or 0, max = tonumber(f[4]) or 0 };
	elseif ( t == "R" ) then
		return { type = "R", items = C.ParseList(f[2], true) };
	elseif ( t == "OPEN" ) then
		return { type = "OPEN", what = f[2] or "", guid = tonumber(f[3]), kind = f[4] or "" };
	elseif ( t == "EN" ) then
		return { type = "EN", cur = (tonumber(f[2]) or 0) / 10, max = (tonumber(f[3]) or 500) / 10, delay = (tonumber(f[4]) or 0) / 1000,
			flash = (f[5] == "1") };
	elseif ( t == "SK" ) then
		return { type = "SK", id = tonumber(f[2]), level = tonumber(f[3]) or 0, pct = tonumber(f[4]) or 0 };
	elseif ( t == "SKU" ) then
		return { type = "SKU", id = tonumber(f[2]), level = tonumber(f[3]) or 0 };
	elseif ( t == "SKL" ) then
		return { type = "SKL", pct = tonumber(f[2]) or 0 };
	elseif ( t == "MD" ) then
		-- « MD|1:wood_floor,2:woodwall » -> models = { {id = 1, prefab = "wood_floor"}, ... }
		local raw = C.ParseList(f[2], false);
		local out = { n = 0 };
		local i = 1;
		while i <= raw.n do
			local kv = C.Split(raw[i], ":");
			local id = tonumber(kv[1]);
			if ( id and kv[2] and kv[2] ~= "" ) then
				out.n = out.n + 1;
				out[out.n] = { id = id, prefab = kv[2] };
			end
			i = i + 1;
		end
		return { type = "MD", models = out };
	elseif ( t == "CP" ) then
		-- « CP|1|x|y|z|o|a » / « CP|0|x|y|z|o|a|Ressources manquantes : 2 Bois. » (canplace) : position apres accroche, puis
		-- la raison (reste de la ligne) ; ancien serveur « CP|1 » / « CP|0|raison » (sans position)
		local x, y, z, o = tonumber(f[3] or ""), tonumber(f[4] or ""), tonumber(f[5] or ""), tonumber(f[6] or "");
		if ( x and y and z and o and (f[7] == "0" or f[7] == "1") ) then
			local why = "";
			local i = 8;
			while f[i] do
				if ( i > 8 ) then why = why .. "|"; end
				why = why .. f[i];
				i = i + 1;
			end
			return { type = "CP", ok = (f[2] == "1"), why = why, x = x, y = y, z = z, o = o, snapped = (f[7] == "1") };
		end
		local why = "";
		if ( f[3] ) then why = string.sub(body, 6); end
		return { type = "CP", ok = (f[2] == "1"), why = why };
	elseif ( t == "PI" ) then
		-- « PI|F1108B0172000123|300|400|0.250|Mur en bois » : le nom est le reste de la ligne
		local name = f[6] or "";
		local i = 7;
		while f[i] do name = name .. "|" .. f[i]; i = i + 1; end
		return { type = "PI", guid = string.upper(f[2] or ""), hp = tonumber(f[3] or "") or 0, hpMax = tonumber(f[4] or "") or 0,
			support = tonumber(f[5] or "") or -1, name = name };
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

-- Clic droit / Echap / fermeture : fin de la pose continue. Le mode demolir / reparer est CONSERVE (Valheim : on choisit
-- Demolir puis on vise la piece, menu ferme) ; seul le choix d'une piece (ChoosePiece) repasse en construction. Le mode
-- courant reste rappele a l'ecran (ModeBanner) tant que le marteau est equipe.
function C.Cancel(st)
	local out = Cmds();
	st.continuous = nil;
	st.pending = nil;
	return out;
end

-- Rappel du mode courant (texte affiche en haut de l'ecran) : nil en mode construction ou marteau range.
C.MODE_NAMES = { remove = "Démolir", repair = "Réparer" };
function C.ModeBanner(st, equipped)
	if ( not equipped or not st or st.mode == "build" ) then return nil; end
	return "Mode : " .. (C.MODE_NAMES[st.mode] or st.mode);
end

-- Rotation lisible : 0 -> "0", 3 -> "67,5" (virgule decimale)
function C.RotText(rot)
	local d = C.RotDegrees(rot or 0);
	if ( math.floor(d) == d ) then return string.format("%d", d); end
	local s = string.gsub(string.format("%.1f", d), "%.", ",");
	return s;
end

-- Rappel de la piece en cours de pose (menu masque, facon Valheim) : « Mur  -  Rotation : 22,5° ». nil si le marteau est
-- range, hors mode construction, sans piece, hors pose continue ou menu affiche (l'encadre du menu montre deja tout).
function C.PlaceBanner(st, equipped, menuShown, name)
	if ( not equipped or not st or st.mode ~= "build" or not st.piece or not st.continuous or menuShown ) then return nil; end
	return (name or ("Pièce " .. st.piece)) .. "  -  Rotation : " .. C.RotText(st.rot) .. "°";
end

-- Clic droit dans le monde (TurnOrActionStart / TurnOrActionStop), marteau equipe. Valheim : clic droit = menu.
--   wasTargeting / isTargeting : ciblage au sol a l'appui / au relachement ; held : duree de l'appui (s).
-- Renvoie "cancel" (le clic droit a annule le ciblage : fin de la pose continue), "menu" (rouvrir le menu) ou nil
-- (rotation de camera = appui long, menu deja ouvert, ou Demolir / Reparer : le clic droit vise alors une construction).
C.CLICK_MAX = 0.3;
function C.RightClickAction(st, equipped, wasTargeting, isTargeting, menuShown, held)
	if ( not equipped or not st ) then return nil; end
	if ( wasTargeting ) then
		if ( not isTargeting ) then return "cancel"; end
		return nil;
	end
	if ( isTargeting or (held or 0) > C.CLICK_MAX or menuShown or st.mode ~= "build" ) then return nil; end
	return "menu";
end

-- GameObject du fantome natif (DLL : WowlheimSetPlaceObject) de la piece choisie ; nil sans piece.
C.GHOST_BASE = 9110000;
function C.PlaceObjectId(st)
	if ( not st or not st.piece ) then return nil; end
	return C.GHOST_BASE + st.piece;
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

-- Refus de pose (server/Wowlheim/BuildPlacement.cpp : TryPlace) : « Pose refusée : ... » / « Ressources manquantes : ... »
function C.IsPlaceRefusal(text)
	if ( not text ) then return false; end
	return string.find(text, "Pose refus", 1, true) == 1 or string.find(text, "Ressources manquantes", 1, true) == 1;
end

-- La ligne est-elle la reponse a une pose en cours (sort du marteau, hors canal des commandes) ?
function C.IsPlaceLine(st, m)
	if ( not st or not st.pending or not m ) then return false; end
	if ( m.type == "D" ) then return m.command == "place"; end
	if ( m.type ~= "M" ) then return false; end
	return C.IsPlaceSuccess(m) or C.IsPlaceRefusal(m.text);
end

-- ------------------------------------------------------------------------------------------------
-- Affichage des messages du serveur : UN message par evenement. Pour un refus de pose le serveur envoie une notification
-- M|texte + D|place|0 (plus de notification du serveur) ; pour un refus de
-- demolition / reparation : notification + E|texte. L'addon ne recopie donc pas ces textes dans UIErrorsFrame, et
-- D|place|0 n'affiche rien. Renvoie nil (rien a afficher) ou { text, error, notified } (notified : deja dans UIErrorsFrame).
-- ------------------------------------------------------------------------------------------------
C.NOTIFY_DEDUP = 2;        -- secondes : un meme texte recu deux fois de suite n'est affiche qu'une fois

function C.NewNotify()
	return { last = nil, t = 0 };
end

function C.NotifyLine(ns, st, m, entry, now)
	if ( not m or (m.type ~= "M" and m.type ~= "E") or not m.text ) then return nil; end
	local n = { text = m.text, error = (m.type == "E") };
	-- Le serveur n'envoie plus de notification pour ces refus (BuildPlacement.cpp : seules les lignes M|/E| partent) :
	-- l'addon est le seul a les afficher, une fois.
	if ( m.type == "M" and C.IsPlaceRefusal(m.text) ) then
		n.error = true;
	end
	now = now or 0;
	if ( ns.last == m.text and (now - ns.t) <= C.NOTIFY_DEDUP ) then return nil; end
	ns.last = m.text;
	ns.t = now;
	return n;
end

-- Messages au centre de l'ecran (UIErrorsFrame) : un meme texte n'y est affiche qu'une fois par C.SCREEN_DEDUP s, quelle
-- que soit sa source (marteau, fabrication, fonderie, annonces) et meme si d'autres textes s'intercalent.
C.SCREEN_DEDUP = 1;

function C.NewDedup()
	return { seen = {} };
end

-- true : afficher (et memoriser) ; false : meme texte deja affiche il y a moins de C.SCREEN_DEDUP s
function C.DedupPass(dd, text, now)
	if ( not text or text == "" ) then return false; end
	now = now or 0;
	local t = dd.seen[text];
	if ( t and (now - t) < C.SCREEN_DEDUP and now >= t ) then return false; end
	dd.seen[text] = now;
	-- menage : les textes anciens sont oublies
	for k, v in pairs(dd.seen) do
		if ( now - v > 30 ) then dd.seen[k] = nil; end
	end
	return true;
end

-- Traite un message serveur pour la pose continue. Renvoie "relaunch" si le ciblage doit etre relance.
-- Une pose = une seule relance (D|place|1 et M|...posee... peuvent arriver tous les deux : pending deduplique).
-- Valheim : un refus (D|place|0, E| : trop fatigue, hors de portee de l'etabli...) ne deselectionne pas la piece ; le
-- ciblage est relance aussi (sinon, menu masque et sans ciblage, le clic droit redeviendrait la camera de WoW).
function C.OnServerMessage(st, m)
	if ( not st.pending ) then return nil; end
	if ( C.IsPlaceSuccess(m) or C.IsPlaceFailure(m) or (m and m.type == "E") ) then
		st.pending = nil;
		if ( st.continuous and st.mode == "build" and st.piece ) then
			return "relaunch";
		end
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

-- ------------------------------------------------------------------------------------------------
-- Canal : file des commandes envoyees par l'addon. Le serveur traite les commandes d'une session dans l'ordre et termine
-- chaque reponse par D|<commande>|0/1 : une ligne recue appartient donc a la plus ancienne commande en attente. Les
-- commandes « silencieuses » (rafraichissements automatiques) ne doivent pas afficher leurs lignes M|.
-- ------------------------------------------------------------------------------------------------
C.CHANNEL_TIMEOUT = 6;     -- secondes : une commande sans D| (refusee, deconnexion...) est oubliee
-- commandes et seuls types de lignes qu'elles renvoient (+ D|). Une valeur texte n'accepte que ce texte exact : un ancien
-- serveur repond « E|commande inconnue » a known / repairable, a rattacher a la commande (silencieuse) et non a afficher.
-- Une table de textes accepte les lignes qui COMMENCENT par l'un d'eux : repairable (interrogation silencieuse toutes les
-- 5 s) repond « E|Station exposée (...) » / « E|Réparation impossible : ... » (Knowledge.cpp, PrepareRepair) ; sans cela
-- ces refus etaient attribues a la commande suivante (craft : « fabrication refusee » en rouge) ou affiches au centre.
C.CHANNEL_STRUCTURED = { stations = { ST = 1, SG = 1 }, known = { K = 1, KS = 1, KP = 1, KR = 1, E = "commande inconnue" },
	repairable = { RS = 1, RI = 1, E = { "commande inconnue", "Station exposée", "Réparation impossible" } },
	-- select / mode (envoyes en silencieux par le menu du marteau) : seul leur accuse leur appartient (« Pièce choisie : Mur
	-- (rotation 0°). », ancien serveur « Mur choisi (rotation 0°). » ; « Marteau : mode ... ») ; un refus de pose ou une
	-- autre erreur recue entre-temps reste affiche
	select = { M = function(t) return string.find(t, "choisi", 1, true) ~= nil; end, E = "commande inconnue" },
	mode = { M = { "Marteau : mode" }, E = "commande inconnue" },
	skills = { SK = 1, EN = 1, E = "commande inconnue" },
	canplace = { CP = 1, E = "commande inconnue" },
	pieceinfo = { PI = 1, E = { "commande inconnue", "Rien à inspecter", "GUID invalide" } },
	models = { MD = 1, E = "commande inconnue" } };

-- ".build api smelter status 12" -> "smelter"
function C.CommandName(cmd)
	if ( not cmd ) then return nil; end
	local _, _, name = string.find(cmd, "^%.build api (%S+)");
	return name;
end

function C.NewChannel()
	return { n = 0 };
end

local function ChannelDrop(ch, count)
	local i = 1;
	while i + count <= ch.n do
		ch[i] = ch[i + count];
		i = i + 1;
	end
	while i <= ch.n do
		ch[i] = nil;
		i = i + 1;
	end
	ch.n = ch.n - count;
end

function C.ChannelPush(ch, cmd, silent, now)
	local name = C.CommandName(cmd);
	if ( not name ) then return; end
	ch.n = ch.n + 1;
	ch[ch.n] = { cmd = name, silent = silent, t = now or 0 };
end

-- Une commande de ce nom est-elle en attente ?
function C.ChannelHas(ch, name)
	local i = 1;
	while i <= ch.n do
		if ( ch[i].cmd == name ) then return true; end
		i = i + 1;
	end
	return false;
end

-- Renvoie l'entree {cmd, silent} a laquelle la ligne m repond (nil si aucune) ; D| retire l'entree (et les precedentes, perdues).
function C.ChannelRoute(ch, m, now)
	while ch.n > 0 and now and (now - ch[1].t) > C.CHANNEL_TIMEOUT do
		ChannelDrop(ch, 1);
	end
	if ( not m ) then return nil; end
	if ( m.type == "D" ) then
		local i = 1;
		while i <= ch.n do
			if ( ch[i].cmd == m.command ) then
				local e = ch[i];
				ChannelDrop(ch, i);
				return e;
			end
			i = i + 1;
		end
		return nil;
	end
	-- une commande a reponse fixe (C.CHANNEL_STRUCTURED) n'est l'auteur que de ses propres types de lignes : un M|, E|, SM|...
	-- recu pendant qu'elle attend appartient a la commande suivante ou a personne (sinon l'interrogation silencieuse des
	-- stations avalerait un vrai message)
	local i = 1;
	while i <= ch.n do
		local only = C.CHANNEL_STRUCTURED[ch[i].cmd];
		local allowed = only and only[m.type];
		if ( type(allowed) == "string" ) then
			allowed = (m.text == allowed);
		elseif ( type(allowed) == "function" ) then
			allowed = (m.text and allowed(m.text)) and true or false;
		elseif ( type(allowed) == "table" ) then
			local list = allowed;
			allowed = false;
			local k = 1;
			while list[k] do
				if ( m.text and string.find(m.text, list[k], 1, true) == 1 ) then allowed = true; end
				k = k + 1;
			end
		end
		if ( not only or allowed ) then return ch[i]; end
		i = i + 1;
	end
	return nil;
end

-- ------------------------------------------------------------------------------------------------
-- Fabrication (Valheim : onglet Fabrication de l'inventaire). Recettes : lignes C| (".build api recipes") ;
-- station : ligne S| (".build api station" : le serveur ne detecte aujourd'hui que l'etabli « workbench »).
-- ------------------------------------------------------------------------------------------------
C.DETECTABLE = { workbench = 1, forge = 1, stonecutter = 1, artisan = 1 };   -- stations signalees par le serveur (une ligne S| par type a portee)

-- Station de ce type parmi celles a portee : `station` est la station principale (premiere ligne S|), .all = toutes par type.
function C.StationFor(station, kind)
	if ( not station ) then return nil; end
	if ( station.all ) then return station.all[kind]; end
	if ( station.kind == kind ) then return station; end
	return nil;
end
C.STATION_ICON = { workbench = "WL_workbench", forge = "WL_forge", stonecutter = "WL_stonecutter", artisan = "WL_artisanstation",
	charcoal_kiln = "WL_coal_kiln", smelter = "WL_smelter" };

function C.RecipesCommand() return ".build api recipes"; end
function C.StationCommand() return ".build api station"; end
function C.CraftCommand(id) return ".build api craft " .. id; end

function C.NewCraft()
	return { recipes = { n = 0 }, tmp = nil, station = nil, stationPending = nil, stationNew = nil, busy = nil, loaded = nil };
end

-- Demande des recettes : la liste sera remplacee a la reception de D|recipes.
function C.CraftRequestRecipes(cs)
	cs.tmp = { n = 0 };
	return C.RecipesCommand();
end

-- Demande de la station : sans ligne S| avant D|station, il n'y a pas d'etabli a portee.
function C.CraftRequestStation(cs)
	cs.stationPending = 1;
	cs.stationNew = nil;
	return C.StationCommand();
end

-- Traite une ligne serveur ; renvoie "recipes", "station", "crafted", "craftfail", "open" ou nil.
-- OPEN|craft|guid|kind : clic sur une station de fabrication en jeu, envoye APRES ses lignes S| (stations a portee). Les S|
-- non sollicitees (hors interrogation station) sont regroupees dans cs.loose ; OPEN en fait la station courante.
function C.CraftOnMessage(cs, m)
	if ( not m ) then return nil; end
	if ( m.type == "OPEN" ) then
		if ( m.what ~= "craft" ) then return nil; end
		if ( cs.loose and not cs.stationPending ) then cs.station = cs.loose; end
		cs.loose = nil;
		cs.opened = m;
		return "open";
	elseif ( m.type == "C" ) then
		if ( not cs.tmp ) then cs.tmp = { n = 0 }; end
		cs.tmp.n = cs.tmp.n + 1;
		cs.tmp[cs.tmp.n] = m;
	elseif ( m.type == "S" ) then
		-- une ligne par type de station a portee : la premiere est la station principale, toutes dans .all
		local target = "station";
		if ( cs.stationPending ) then target = "stationNew"; end
		if ( not cs[target] or not cs[target].all or cs[target].all[m.kind] ) then
			m.all = {};
			cs[target] = m;
		end
		cs[target].all[m.kind] = m;
		if ( not cs.stationPending ) then
			-- groupe de S| spontanees (clic sur une station) : remplace par OPEN la station courante
			if ( not cs.loose or cs.loose.all[m.kind] ) then
				cs.loose = { guid = m.guid, usable = m.usable, cover = m.cover, level = m.level, kind = m.kind, type = "S", all = {} };
			end
			cs.loose.all[m.kind] = m;
		end
		return "station";
	elseif ( m.type == "D" ) then
		if ( m.command == "recipes" ) then
			cs.recipes = cs.tmp or { n = 0 };
			cs.tmp = nil;
			cs.loaded = 1;
			return "recipes";
		elseif ( m.command == "station" ) then
			cs.loose = nil;
			if ( cs.stationPending ) then
				cs.station = cs.stationNew;
				cs.stationPending = nil;
				cs.stationNew = nil;
			end
			return "station";
		elseif ( m.command == "craft" ) then
			cs.busy = nil;
			if ( m.ok ) then return "crafted"; end
			return "craftfail";
		end
	end
	return nil;
end

-- Ingredients C| ({item,count}) -> couts WowlheimData ({itemId, n})
function C.ItemsToCosts(list)
	local out = {};
	local i = 1;
	while list and list[i] do
		out[i] = { list[i].item, list[i].count };
		i = i + 1;
	end
	return out;
end

-- Etat d'une recette : ressources (possede/requis), station et niveau. station = derniere ligne S| (ou nil).
-- reason : nil | "nostation" | "exposed" | "level" | "resources"
function C.CraftCheck(r, counts, station)
	local all, rows = C.Affordability(C.ItemsToCosts(r.ingredients), counts or {});
	local c = { rows = rows, haveAll = all, station = r.station or "", minLevel = r.minLevel or 1, stationOk = true, levelOk = true };
	if ( c.station == "" ) then
		c.hand = true;
	elseif ( C.DETECTABLE[c.station] ) then
		station = C.StationFor(station, c.station);
		if ( station ) then
			c.curLevel = station.level or 1;
			c.cover = station.cover;
			c.levelOk = (c.curLevel >= c.minLevel);
			c.stationOk = station.usable and true or false;
			if ( not c.stationOk ) then c.reason = "exposed"; end
		else
			c.stationOk = false;
			c.levelOk = false;
			c.reason = "nostation";
		end
	else
		c.unknown = true;          -- forge, tailleur de pierre... : presence et niveau verifies par le serveur a la fabrication
	end
	if ( not c.reason and not c.levelOk ) then c.reason = "level"; end
	if ( not c.reason and not c.haveAll ) then c.reason = "resources"; end
	c.ok = (c.reason == nil);
	return c;
end

-- Bouton « Fabriquer » : actif si la recette est realisable et qu'aucune fabrication n'est en cours.
function C.CraftButtonEnabled(check, busy)
	if ( busy or not check ) then return false; end
	return check.ok and true or false;
end

-- Texte de station requis / actuel ; renvoie texte, ok
function C.StationText(check, names)
	local nm = (names and names[check.station]) or check.station;
	if ( check.hand ) then
		return "Sans station (fabrication à la main)", true;
	elseif ( check.reason == "nostation" ) then
		return "Requiert : " .. nm .. " à portée (20 m)", false;
	elseif ( check.reason == "exposed" ) then
		return nm .. " exposée : il faut un toit (couverture " .. (check.cover or 0) .. " %, 70 % requis)", false;
	elseif ( check.unknown ) then
		return "Requiert : " .. nm .. " niveau " .. check.minLevel .. " (vérifié par le serveur)", true;
	elseif ( not check.levelOk ) then
		return nm .. " niveau " .. check.minLevel .. " requis (actuel : " .. check.curLevel .. ")", false;
	end
	return nm .. " niveau " .. check.minLevel .. " (actuel : " .. check.curLevel .. ")", true;
end

-- Aide du menu du marteau (encadre sans piece survolee) : 4 lignes courtes, touches en orange, une ligne vide apres la
-- premiere (5 lignes de GameFontHighlightSmall dans la zone de 72 px). rotL, rotR, menu : touches liees (WL.KeyText).
function C.HammerHelp(rotL, rotR, menu)
	local function K(t) return "|cffffad38" .. t .. "|r"; end
	return "Choisissez une pièce, puis visez le sol.\n\n"
		.. K("Clic gauche") .. " : poser   -   " .. K("Clic milieu") .. " : démolir la pièce visée\n"
		.. K("Molette") .. " ou " .. K((rotL or "Alt+A") .. " / " .. (rotR or "Alt+E")) .. " : tourner la pièce\n"
		.. K("Clic droit") .. " ou " .. K(menu or "Y") .. " : ce menu   -   " .. K("Échap") .. " : fin de la pose";
end

-- Fiche de recette : 2 lignes « Station : Forge » / « Niveau 2 requis (actuel : 1) » ; renvoie ligne1, ligne2, ok
function C.StationLines(check, names)
	local nm = (names and names[check.station]) or check.station;
	if ( check.hand ) then
		return "Station : aucune", "Fabrication à la main", true;
	elseif ( check.reason == "nostation" ) then
		return "Station : " .. nm, "Introuvable : approchez-vous à moins de 20 m", false;
	elseif ( check.reason == "exposed" ) then
		return "Station : " .. nm, "Exposée : il faut un toit (couverture " .. (check.cover or 0) .. " %, 70 % requis)", false;
	elseif ( check.unknown ) then
		return "Station : " .. nm, "Niveau " .. check.minLevel .. " requis (vérifié à la fabrication)", true;
	end
	return "Station : " .. nm, "Niveau " .. check.minLevel .. " requis (actuel : " .. (check.curLevel or 0) .. ")",
		check.levelOk and true or false;
end

-- Stations a portee (lignes S| : station.all) -> { [kind] = true } (stations connues localement)
function C.NearStations(station, out)
	out = out or {};
	if ( station and station.all ) then
		for k in pairs(station.all) do out[k] = true; end
	elseif ( station and station.kind ) then
		out[station.kind] = true;
	end
	return out;
end

-- Liste du panneau (Valheim) : recettes sans station + recettes de la station a portee (toutes si showAll) ;
-- realisables d'abord, puis les autres, chacune dans l'ordre du serveur. Entrees { r = recette, check = CraftCheck }.
-- opts (facultatif) : query (recherche : toutes les stations, filtre nom + description), items (WowlheimData.items pour la
-- description de l'objet produit), known (C.NewKnown : recettes aux materiaux / station inconnus cachees, facon Valheim).
function C.RecipeList(recipes, counts, station, showAll, opts)
	opts = opts or {};
	local words = C.SearchWords(opts.query);
	local near = C.NearStations(station);
	local okList, koList = {}, {};
	local nok, nko = 0, 0;
	local i = 1;
	while recipes and recipes[i] do
		local r = recipes[i];
		local st = r.station or "";
		local show = (showAll or words.n > 0 or st == "" or C.StationFor(station, st));
		if ( show and words.n > 0 ) then
			local it = opts.items and r.outItem and opts.items[r.outItem];
			show = C.EntryMatches(words, r.name, it and it.desc);
		end
		if ( show ) then
			show = C.RecipeKnown(opts.known, r, counts, near);
		end
		if ( show ) then
			local e = { r = r, check = C.CraftCheck(r, counts, station) };
			if ( e.check.ok ) then
				nok = nok + 1; okList[nok] = e;
			else
				nko = nko + 1; koList[nko] = e;
			end
		end
		i = i + 1;
	end
	local out = { n = 0 };
	i = 1;
	while i <= nok do out.n = out.n + 1; out[out.n] = okList[i]; i = i + 1; end
	i = 1;
	while i <= nko do out.n = out.n + 1; out[out.n] = koList[i]; i = i + 1; end
	return out;
end

-- ------------------------------------------------------------------------------------------------
-- Recherche (menu du marteau, panneau de fabrication) : insensible a la casse et aux accents. Lua 5.0 et textes UTF-8 :
-- string.lower ne touche pas aux lettres accentuees, d'ou la table de remplacement (sequences UTF-8, sans caractere magique).
-- ------------------------------------------------------------------------------------------------
C.FOLD = {
	{ "à", "a" }, { "â", "a" }, { "ä", "a" }, { "á", "a" }, { "ã", "a" }, { "å", "a" },
	{ "À", "a" }, { "Â", "a" }, { "Ä", "a" }, { "Á", "a" },
	{ "ç", "c" }, { "Ç", "c" },
	{ "é", "e" }, { "è", "e" }, { "ê", "e" }, { "ë", "e" }, { "É", "e" }, { "È", "e" }, { "Ê", "e" }, { "Ë", "e" },
	{ "î", "i" }, { "ï", "i" }, { "í", "i" }, { "ì", "i" }, { "Î", "i" }, { "Ï", "i" },
	{ "ô", "o" }, { "ö", "o" }, { "ó", "o" }, { "ò", "o" }, { "õ", "o" }, { "ø", "o" }, { "Ô", "o" }, { "Ö", "o" },
	{ "ù", "u" }, { "û", "u" }, { "ü", "u" }, { "ú", "u" }, { "Ù", "u" }, { "Û", "u" }, { "Ü", "u" },
	{ "ÿ", "y" }, { "ý", "y" }, { "Ÿ", "y" }, { "ñ", "n" }, { "Ñ", "n" },
	{ "œ", "oe" }, { "Œ", "oe" }, { "æ", "ae" }, { "Æ", "ae" },
	{ "’", "'" },
};

-- « Œil de naingris » -> « oeil de naingris »
function C.Fold(s)
	if ( not s ) then return ""; end
	local i = 1;
	while C.FOLD[i] do
		s = string.gsub(s, C.FOLD[i][1], C.FOLD[i][2]);
		i = i + 1;
	end
	return string.lower(s);
end

-- Mots de la recherche (repliés) : { "mur", "bois", n = 2 } ; n = 0 si la recherche est vide
function C.SearchWords(query)
	local words = { n = 0 };
	if ( not query or query == "" ) then return words; end
	local parts = C.Split(C.Fold(query), " ");
	local i = 1;
	while parts[i] do
		if ( parts[i] ~= "" ) then
			words.n = words.n + 1;
			words[words.n] = parts[i];
		end
		i = i + 1;
	end
	return words;
end

-- Tous les mots apparaissent-ils dans le nom ou la description ?
function C.EntryMatches(words, name, desc)
	if ( not words or words.n == 0 ) then return true; end
	local text = C.Fold(name) .. " " .. C.Fold(desc);
	local i = 1;
	while i <= words.n do
		if ( not string.find(text, words[i], 1, true) ) then return false; end
		i = i + 1;
	end
	return true;
end

-- ------------------------------------------------------------------------------------------------
-- Pieces / recettes connues (Valheim : Player.m_knownMaterial / m_knownStations). Une piece ou une recette n'apparait que
-- si TOUS ses materiaux sont connus (deja possedes au moins une fois) et sa station (s'il y en a une) connue ; sinon elle
-- est cachee. Serveur : ".build api known" -> K|item,item,... KS|station,... D|known|1. Tant qu'aucune reponse n'est
-- recue (ou ancien serveur : E|commande inconnue + D|known|0), tout est affiche. Union locale : un objet present dans les
-- sacs, une station a portee sont connus.
-- ------------------------------------------------------------------------------------------------
C.KNOWN_POLL = 1;          -- s : intervalle minimal entre deux interrogations sur BAG_UPDATE

function C.KnownCommand() return ".build api known"; end

function C.NewKnown()
	return { loaded = nil, items = {}, stations = {}, levels = {}, pieces = nil, recipes = nil, tmp = nil, unsupported = nil,
		version = 0, newPieces = { n = 0 }, newRecipes = { n = 0 } };
end

local function NewKnownTmp()
	return { items = {}, stations = {}, levels = {}, pieces = nil, recipes = nil };
end

-- ids presents dans cur mais pas dans old (old nil : rien de nouveau, premiere reponse)
local function KnownDiff(old, cur)
	local out = { n = 0 };
	if ( not old or not cur ) then return out; end
	for id in pairs(cur) do
		if ( not old[id] ) then out.n = out.n + 1; out[out.n] = id; end
	end
	table.sort(out);
	return out;
end

-- Renvoie "update" a la fin de la reponse (D|known), "learned" sur KN| (connaissance acquise : relancer known), nil sinon.
-- Apres une mise a jour, ks.newPieces / ks.newRecipes = ids decouverts depuis la reponse precedente (« Nouvelle piece »).
function C.KnownOnMessage(ks, m)
	if ( not m ) then return nil; end
	if ( m.type == "K" or m.type == "KS" or m.type == "KP" or m.type == "KR" ) then
		if ( not ks.tmp ) then ks.tmp = NewKnownTmp(); end
		local t = ks.tmp;
		local list, dest = m.items, t.items;
		if ( m.type == "KS" ) then
			list, dest = m.stations, t.stations;
			for k, lv in pairs(m.levels) do t.levels[k] = lv; end
		elseif ( m.type == "KP" ) then
			if ( not t.pieces ) then t.pieces = {}; end
			list, dest = m.ids, t.pieces;
		elseif ( m.type == "KR" ) then
			if ( not t.recipes ) then t.recipes = {}; end
			list, dest = m.ids, t.recipes;
		end
		local i = 1;
		while i <= list.n do
			dest[list[i]] = true;
			i = i + 1;
		end
	elseif ( m.type == "KN" ) then
		if ( m.what == "station" and m.kind ~= "" ) then
			ks.stations[m.kind] = true;
			if ( (ks.levels[m.kind] or 0) < m.level ) then ks.levels[m.kind] = m.level; end
		elseif ( m.item ) then
			ks.items[m.item] = true;
		end
		return "learned";
	elseif ( m.type == "D" and m.command == "known" ) then
		ks.newPieces = { n = 0 };
		ks.newRecipes = { n = 0 };
		if ( m.ok ) then
			local t = ks.tmp or NewKnownTmp();
			if ( ks.loaded ) then
				ks.newPieces = KnownDiff(ks.pieces, t.pieces);
				ks.newRecipes = KnownDiff(ks.recipes, t.recipes);
			end
			ks.items = t.items;
			ks.stations = t.stations;
			ks.levels = t.levels;
			ks.pieces = t.pieces;
			ks.recipes = t.recipes;
			ks.loaded = 1;
			ks.unsupported = nil;
			ks.version = ks.version + 1;
		elseif ( not ks.loaded ) then
			ks.unsupported = 1;      -- ancien serveur : on affiche tout, plus d'interrogation sur BAG_UPDATE
		end
		ks.tmp = nil;
		return "update";
	end
	return nil;
end

-- Piece / recette connue : liste du serveur (KP / KR, regle Valheim deja appliquee) OU calcul local (union : objets des
-- sacs, stations a portee). Sans liste KP / KR (serveur qui ne l'envoie pas) : calcul local seul.
function C.PieceKnown(ks, p, counts, near)
	if ( not ks or not ks.loaded or p.special ) then return true; end
	if ( ks.pieces and ks.pieces[p.id] ) then return true; end
	return C.IsKnown(ks, p.costs, p.station, counts, near);
end

function C.RecipeKnown(ks, r, counts, near)
	if ( not ks or not ks.loaded ) then return true; end
	if ( ks.recipes and r.id and ks.recipes[r.id] ) then return true; end
	return C.IsKnown(ks, C.ItemsToCosts(r.ingredients), r.station or "", counts, near, r.minLevel);
end

-- costs = { {itemId, n}, ... } ; station = "" ou type ; counts = sacs ; near = { [kind] = true } stations a portee ;
-- minLevel : niveau de station requis (recettes) : la station doit etre connue a ce niveau (sauf station a portee).
function C.IsKnown(ks, costs, station, counts, near, minLevel)
	if ( not ks or not ks.loaded ) then return true; end
	local isNear = near and station and near[station];
	if ( station and station ~= "" and not ks.stations[station] and not isNear ) then return false; end
	if ( station and station ~= "" and not isNear and minLevel and ks.levels and ks.levels[station]
		and ks.levels[station] < minLevel ) then return false; end
	local i = 1;
	while costs and costs[i] do
		local id = costs[i][1];
		if ( not ks.items[id] and not (counts and (counts[id] or 0) > 0) ) then return false; end
		i = i + 1;
	end
	return true;
end

-- Entrees du menu du marteau : categorie cat, ou, pendant une recherche, toutes les categories (onglets deselectionnes,
-- comme Valheim). Pieces inconnues cachees (IsKnown) ; Reparer / Demolir toujours connus. list.searching = recherche active.
function C.MenuEntries(pieces, cat, query, known, counts, near)
	local words = C.SearchWords(query);
	if ( words.n == 0 ) then
		local base = C.CategoryEntries(pieces, cat);
		local list = { n = 0 };
		local i = 1;
		while i <= base.n do
			local e = base[i];
			if ( C.PieceKnown(known, e, counts, near) ) then
				list.n = list.n + 1;
				list[list.n] = e;
			end
			i = i + 1;
		end
		return list;
	end
	local list = { n = 0, searching = true };
	local s = 1;
	while C.SPECIALS[s] do
		if ( C.EntryMatches(words, C.SPECIALS[s].name, C.SPECIALS[s].desc) ) then
			list.n = list.n + 1;
			list[list.n] = C.SPECIALS[s];
		end
		s = s + 1;
	end
	local maxCat = 0;
	local i = 1;
	while pieces and pieces[i] do
		if ( (pieces[i].cat or 0) > maxCat ) then maxCat = pieces[i].cat; end
		i = i + 1;
	end
	local c = 1;
	while c <= maxCat do
		i = 1;
		while pieces[i] do
			local p = pieces[i];
			if ( p.cat == c and C.EntryMatches(words, p.name, p.desc) and C.PieceKnown(known, p, counts, near) ) then
				list.n = list.n + 1;
				list[list.n] = p;
			end
			i = i + 1;
		end
		c = c + 1;
	end
	return list;
end

-- Nombre de vraies pieces connues de la categorie (Reparer / Demolir non comptes)
function C.CategoryPieceCount(pieces, cat, known, counts, near)
	local list = C.MenuEntries(pieces, cat, "", known, counts, near);
	local n = 0;
	local i = 1;
	while i <= list.n do
		if ( not list[i].special ) then n = n + 1; end
		i = i + 1;
	end
	return n;
end

-- Onglet a l'ouverture du menu (Valheim : onglet memorise). remembered : l'onglet vient d'un choix du joueur ; sinon
-- (premier usage) ou si l'onglet courant ne contient aucune piece connue : premier onglet qui en contient une. Aucun :
-- onglet courant inchange.
function C.PickCategory(pieces, cat, remembered, ncat, known, counts, near)
	if ( remembered and cat and C.CategoryPieceCount(pieces, cat, known, counts, near) > 0 ) then return cat; end
	local c = 1;
	while c <= (ncat or 0) do
		if ( C.CategoryPieceCount(pieces, c, known, counts, near) > 0 ) then return c; end
		c = c + 1;
	end
	return cat or 1;
end

-- ------------------------------------------------------------------------------------------------
-- Annonces de decouverte (Valheim : MessageHud.QueueUnlockMsg, textes francais de Valheim) :
--   $msg_newmaterial « Nouveau matériau », $msg_newitem « Nouvel objet », $msg_newpiece « Nouvelle pièce de construction »,
--   $msg_newrecipe « Nouvelle recette », $msg_newstation « Nouvel établi », $msg_newstation_level « Établi mis à niveau ».
-- Texte : « <libelle> : <premier nom> » (+ n autres).
-- ------------------------------------------------------------------------------------------------
C.UNLOCK = { material = "Nouveau matériau", item = "Nouvel objet", piece = "Nouvelle pièce de construction",
	recipe = "Nouvelle recette", station = "Nouvel établi", stationLevel = "Établi mis à niveau" };
C.TOOL_MIN = 9201000;      -- objets >= : outils et marteau (« Nouvel objet ») ; en dessous : materiaux

function C.UnlockText(label, names)
	if ( not names or names.n == 0 ) then return nil; end
	local s = label .. " : " .. names[1];
	if ( names.n > 1 ) then s = s .. " (+" .. (names.n - 1) .. ")"; end
	return s;
end

-- Nom d'une piece (WowlheimData.pieces) ; repli « pièce <id> »
function C.PieceName(pieces, id)
	local i = 1;
	while pieces and pieces[i] do
		if ( pieces[i].id == id ) then return pieces[i].name; end
		i = i + 1;
	end
	return "pièce " .. id;
end

-- Nom d'une recette : WowlheimData.recipes (genere, toujours present), sinon lignes C| deja recues (panneau de fabrication),
-- sinon nom de l'objet produit ; repli « recette <id> »
function C.RecipeName(dataRecipes, craftRecipes, items, id)
	local r = dataRecipes and dataRecipes[id];
	if ( r and r.name ) then return r.name; end
	local i = 1;
	while craftRecipes and craftRecipes[i] do
		if ( craftRecipes[i].id == id and craftRecipes[i].name ) then return craftRecipes[i].name; end
		i = i + 1;
	end
	if ( r and r.out and items and items[r.out] ) then return items[r.out].name; end
	return "recette " .. id;
end

-- Annonces apres une reponse known (ks.newPieces / ks.newRecipes) : { piece = texte|nil, recipe = texte|nil }
function C.KnownAnnouncements(ks, pieces, dataRecipes, craftRecipes, items)
	local out = {};
	local names = { n = 0 };
	local i = 1;
	while ks and ks.newPieces and i <= ks.newPieces.n do
		names.n = names.n + 1;
		names[names.n] = C.PieceName(pieces, ks.newPieces[i]);
		i = i + 1;
	end
	out.piece = C.UnlockText(C.UNLOCK.piece, names);
	names = { n = 0 };
	i = 1;
	while ks and ks.newRecipes and i <= ks.newRecipes.n do
		names.n = names.n + 1;
		names[names.n] = C.RecipeName(dataRecipes, craftRecipes, items, ks.newRecipes[i]);
		i = i + 1;
	end
	out.recipe = C.UnlockText(C.UNLOCK.recipe, names);
	return out;
end

-- Annonce d'une ligne KN| (objet ramasse pour la premiere fois, station decouverte / amelioree) ; nil si rien a dire
function C.LearnedText(m, items, stationNames)
	if ( not m or m.type ~= "KN" ) then return nil; end
	if ( m.what == "station" ) then
		if ( not m.kind or m.kind == "" ) then return nil; end
		local nm = (stationNames and stationNames[m.kind]) or m.kind;
		if ( (m.level or 1) > 1 ) then return C.UNLOCK.stationLevel .. " : " .. nm .. " niveau " .. m.level; end
		return C.UNLOCK.station .. " : " .. nm;
	end
	if ( not m.item ) then return nil; end
	local it = items and items[m.item];
	local nm = (it and it.name) or ("objet " .. m.item);
	if ( m.item >= C.TOOL_MIN ) then return C.UNLOCK.item .. " : " .. nm; end
	return C.UNLOCK.material .. " : " .. nm;
end

-- ------------------------------------------------------------------------------------------------
-- Ressources manquantes de la piece en cours de pose (Valheim : Hud.SetupPieceInfo, quantites en rouge) :
-- « Manque : Bois 3/10, Pierre 0/2 » ; nil si tout est la. itemName(id) -> nom.
-- ------------------------------------------------------------------------------------------------
function C.MissingText(costs, counts, itemName)
	local ok, rows = C.Affordability(costs, counts or {});
	if ( ok ) then return nil; end
	local s = nil;
	local i = 1;
	while i <= rows.n do
		local r = rows[i];
		if ( not r.ok ) then
			local nm = (itemName and itemName(r.item)) or ("objet " .. r.item);
			local part = nm .. " " .. r.have .. "/" .. r.need;
			if ( s ) then s = s .. ", " .. part; else s = part; end
		end
		i = i + 1;
	end
	return "Manque : " .. s;
end

-- ------------------------------------------------------------------------------------------------
-- Reparation a la station (Valheim : bouton Reparer du panneau de fabrication, repare les objets abimes reparables a la
-- station courante). Serveur : ".build api repairable" -> RI|item|durabilite|max ... D|repairable ;
-- ".build api repairitems" -> R|item,item,... D|repairitems.
-- ------------------------------------------------------------------------------------------------
-- guid facultatif : station visee (celle du panneau) ; sans guid, le serveur prend la station la plus proche
function C.RepairableCommand(guid)
	if ( guid ) then return ".build api repairable " .. guid; end
	return ".build api repairable";
end
function C.RepairItemsCommand(guid)
	if ( guid ) then return ".build api repairitems " .. guid; end
	return ".build api repairitems";
end

function C.NewRepair()
	return { list = { n = 0 }, byItem = {}, tmp = nil, loaded = nil, unsupported = nil, busy = nil, repaired = nil };
end

-- Renvoie "repairable" (liste recue), "repaired" (fin de reparation) ou nil.
function C.RepairOnMessage(rp, m)
	if ( not m ) then return nil; end
	if ( m.type == "E" and m.text == "commande inconnue" ) then
		rp.unknownCmd = 1;             -- ancien serveur (repond ainsi a toute commande api inconnue, puis D|<cmd>|0)
	elseif ( m.type == "RS" ) then
		rp.tmpStation = m;             -- station de reparation (RS|guid|kind|niveau), avant les RI|
	elseif ( m.type == "RI" ) then
		if ( not rp.tmp ) then rp.tmp = { n = 0 }; end
		rp.tmp.n = rp.tmp.n + 1;
		rp.tmp[rp.tmp.n] = m;
	elseif ( m.type == "R" ) then
		rp.repaired = m.items;
	elseif ( m.type == "D" and m.command == "repairable" ) then
		if ( m.ok ) then
			rp.list = rp.tmp or { n = 0 };
			rp.byItem = {};
			local i = 1;
			while i <= rp.list.n do
				local e = rp.list[i];
				local cur = rp.byItem[e.item];
				-- plusieurs exemplaires du meme objet : on retient le plus abime
				if ( not cur or (e.max > 0 and cur.max > 0 and e.dur / e.max < cur.dur / cur.max) ) then rp.byItem[e.item] = e; end
				i = i + 1;
			end
			rp.station = rp.tmpStation;
			rp.loaded = 1;
		else
			-- refus (pas de station a portee...) : plus rien a reparer ; ancien serveur : plus d'interrogation
			rp.list = { n = 0 };
			rp.byItem = {};
			rp.station = nil;
			if ( rp.unknownCmd ) then rp.unsupported = 1; end
		end
		rp.tmp = nil;
		rp.tmpStation = nil;
		rp.unknownCmd = nil;
		return "repairable";
	elseif ( m.type == "D" and m.command == "repairitems" ) then
		rp.busy = nil;
		return "repaired";
	end
	return nil;
end

-- Bouton « Reparer » : actif s'il y a quelque chose a reparer ici et aucune reparation en cours ; renvoie actif, libelle.
function C.RepairButton(rp)
	local n = (rp and rp.list and rp.list.n) or 0;
	if ( n > 0 ) then return (not rp.busy), "Réparer (" .. n .. ")"; end
	return false, "Réparer";
end

-- Indication pour un objet abime reparable a la station : « Abîmé (40 %) : réparable ici » ; nil sinon.
function C.RepairText(rp, item)
	local e = rp and rp.byItem and item and rp.byItem[item];
	if ( not e ) then return nil; end
	local pct = 0;
	if ( e.max and e.max > 0 ) then pct = math.floor(e.dur * 100 / e.max); end
	return "Abîmé (" .. pct .. " %) : réparable ici";
end

-- ------------------------------------------------------------------------------------------------
-- Fonderie / four a charbon (Valheim : composant Smelter ; serveur : server/Wowlheim/Smelter.cpp)
-- ------------------------------------------------------------------------------------------------
C.SMELT_STATUS = { ok = "En marche", noore = "Vide", nofuel = "Plus de combustible", off = "À l'arrêt",
	roof = "Nécessite un toit", smoke = "Fumée bloquée" };

function C.SmelterStatusCommand(guid)
	if ( guid ) then return ".build api smelter status " .. guid; end
	return ".build api smelter status";
end

function C.SmelterAddCommand(what, n, guid)
	local s = ".build api smelter add " .. what .. " " .. (n or 1);
	if ( guid ) then s = s .. " " .. guid; end
	return s;
end

function C.SmelterTakeCommand(guid)
	if ( guid ) then return ".build api smelter take " .. guid; end
	return ".build api smelter take";
end

-- Vue du panneau : textes, fractions des barres, etat des boutons. counts = sacs ; conversion = { {de, vers}, ... } (WowlheimData.smelters)
function C.SmelterView(sm, counts, conversion)
	local v = {};
	counts = counts or {};
	v.kiln = (sm.maxFuel == 0);
	v.oreText = sm.queue .. "/" .. sm.maxOre;
	v.oreFrac = 0;
	if ( sm.maxOre > 0 ) then v.oreFrac = C.Clamp(sm.queue / sm.maxOre, 0, 1); end
	v.hasFuel = (sm.maxFuel > 0);
	v.fuelFrac = 0;
	v.fuelText = "";
	if ( v.hasFuel ) then
		v.fuelFrac = C.Clamp(sm.fuel / sm.maxFuel, 0, 1);
		v.fuelText = math.ceil(sm.fuel - 0.0001) .. "/" .. sm.maxFuel;   -- combustible fractionnaire arrondi a l'unite superieure
	end
	v.progress = 0;
	if ( sm.secPerProduct > 0 ) then v.progress = C.Clamp(sm.bake / sm.secPerProduct, 0, 1); end
	v.progressText = math.floor(sm.bake) .. "/" .. math.floor(sm.secPerProduct) .. " s";
	v.ready = 0;
	local i = 1;
	while sm.output and sm.output[i] do
		v.ready = v.ready + sm.output[i].count;
		i = i + 1;
	end
	v.status = C.SMELT_STATUS[sm.why] or sm.why;
	v.active = sm.active;
	-- minerai transformable present dans les sacs (Smelter.FindCookableItem : premier m_from present)
	v.oreHave = 0;
	v.oreItem = nil;
	if ( conversion ) then
		i = 1;
		while conversion[i] do
			local n = counts[conversion[i][1]] or 0;
			if ( n > 0 ) then
				if ( not v.oreItem ) then v.oreItem = conversion[i][1]; end
				v.oreHave = v.oreHave + n;
			end
			i = i + 1;
		end
	else
		v.oreHave = 1;             -- conversions inconnues : le serveur decidera
	end
	v.fuelHave = 0;
	if ( v.hasFuel ) then v.fuelHave = counts[sm.fuelItem] or 0; end
	v.oreRoom = sm.maxOre - sm.queue;
	if ( v.oreRoom < 0 ) then v.oreRoom = 0; end
	v.fuelRoom = 0;
	if ( v.hasFuel ) then v.fuelRoom = math.floor(sm.maxFuel - sm.fuel); end   -- OnAddFuel : refuse si fuel > maxFuel - 1
	if ( v.fuelRoom < 0 ) then v.fuelRoom = 0; end
	v.canAddOre = (sm.maxOre > 0 and v.oreRoom > 0 and v.oreHave > 0);
	v.canAddFuel = (v.hasFuel and v.fuelRoom > 0 and v.fuelHave > 0);
	v.canTake = (v.ready > 0);
	return v;
end

-- Nombre d'unites a ajouter : 1 par clic (interrupteur de Valheim) ; Maj+clic = remplir (maintien de l'interrupteur).
function C.SmelterAddCount(v, what, fill)
	if ( not fill ) then return 1; end
	local room, have = v.oreRoom, v.oreHave;
	if ( what == "fuel" ) then room, have = v.fuelRoom, v.fuelHave; end
	local n = room;
	if ( have < n ) then n = have; end
	if ( n < 1 ) then n = 1; end
	return n;
end

-- Produit pret de la fonderie : « Cuivre x4 »
function C.OutputLabel(name, count)
	return (name or "?") .. " x" .. (count or 1);
end

function C.NewSmelt()
	return { sm = nil, guid = nil };
end

-- Traite une ligne serveur pour le panneau de fonderie. entry = commande a laquelle la ligne repond (ChannelRoute), visible =
-- panneau affiche. Renvoie "open" (SM non sollicite : clic sur la station en jeu), "update", "lost" (station hors de portee) ou nil.
function C.SmeltOnMessage(ss, m, entry, visible)
	if ( not m ) then return nil; end
	if ( m.type == "SM" ) then
		ss.sm = m;
		ss.guid = m.guid;
		-- un SM d'un rafraichissement silencieux arrive apres la fermeture du panneau : ne pas le rouvrir
		if ( not visible and not (entry and entry.silent and entry.cmd == "smelter") ) then return "open"; end
		return "update";
	elseif ( m.type == "E" and entry and entry.cmd == "smelter" ) then
		if ( m.text == "aucune station" or m.text == "trop loin" ) then
			ss.sm = nil;
			ss.guid = nil;
			return "lost";
		end
	end
	return nil;
end

-- ------------------------------------------------------------------------------------------------
-- Cercle de portee des stations (Valheim : CraftingStation.m_areaMarker, un cercle de segments au sol). Marteau equipe en
-- mode construction : l'addon interroge ".build api stations" (server/Wowlheim/BuildCommands.cpp) et pose un segment
-- (modele M2, DLL : WowlheimMarkerShow) par point du contour de la zone de chaque station proche :
--   ST|guid|kind|x|y|z|portee|dedans|n   puis   SG|guid|premier|x,y,z,o;...   (contour : distance au bord de la station
--   = portee, celle que le serveur teste a la pose, mesuree depuis la position du JOUEUR) ; fin : D|stations.
-- Vert : le joueur est dans la zone ; rouge : hors zone.
-- ------------------------------------------------------------------------------------------------
C.RING_POLL = 1.5;         -- secondes entre deux interrogations (la couleur suit le joueur avec ce retard au plus)
C.RING_MAX = 256;          -- marqueurs de la DLL (MAX_MARKERS)
C.RING_MODELS = { inside = "World\\Wowlheim\\wl_station_ring_in.m2", outside = "World\\Wowlheim\\wl_station_ring_out.m2" };

function C.StationsCommand() return ".build api stations"; end

function C.NewRings()
	return { stations = { n = 0 }, tmp = nil, version = 0 };
end

-- Le cercle doit-il etre affiche ? Marteau equipe et mode construction (pas Demolir / Reparer).
function C.RingsWanted(st, equipped)
	if ( not equipped or not st ) then return false; end
	return st.mode == "build";
end

-- Traite une ligne serveur ; renvoie "update" quand la liste complete est recue (D|stations), nil sinon.
function C.RingsOnMessage(rs, m)
	if ( not m ) then return nil; end
	if ( m.type == "ST" ) then
		if ( not rs.tmp ) then rs.tmp = { n = 0 }; end
		m.points = {};
		rs.tmp.n = rs.tmp.n + 1;
		rs.tmp[rs.tmp.n] = m;
	elseif ( m.type == "SG" ) then
		local s = nil;
		local i = 1;
		while rs.tmp and rs.tmp[i] do
			if ( rs.tmp[i].guid == m.guid ) then s = rs.tmp[i]; end
			i = i + 1;
		end
		if ( s ) then
			local k = 1;
			while k <= m.points.n do
				s.points[m.first + k] = m.points[k];
				k = k + 1;
			end
		end
	elseif ( m.type == "D" and m.command == "stations" ) then
		if ( m.ok ) then
			rs.stations = rs.tmp or { n = 0 };
			rs.version = rs.version + 1;
		end
		rs.tmp = nil;
		return "update";
	end
	return nil;
end

-- Liste des segments a afficher : { {id=0.., path, x, y, z, o, guid}, ... } (n), au plus max (les stations arrivent de la
-- plus proche a la plus lointaine ; les dernieres sont coupees).
function C.RingMarkers(stations, max, models)
	local out = { n = 0 };
	max = max or C.RING_MAX;
	models = models or C.RING_MODELS;
	local i = 1;
	while stations and stations[i] do
		local s = stations[i];
		local path = models.outside;
		if ( s.inside ) then path = models.inside; end
		local k = 1;
		while k <= (s.n or 0) and out.n < max do
			local p = s.points[k];
			if ( p ) then
				out.n = out.n + 1;
				out[out.n] = { id = out.n - 1, path = path, x = p.x, y = p.y, z = p.z, o = p.o, guid = s.guid };
			end
			k = k + 1;
		end
		i = i + 1;
	end
	return out;
end

-- Le joueur est-il dans la zone d'une station de ce type ? nil si inconnu (aucune liste recue).
function C.InStationRange(rs, kind)
	if ( not rs or rs.version == 0 ) then return nil; end
	local i = 1;
	while rs.stations[i] do
		if ( rs.stations[i].kind == kind and rs.stations[i].inside ) then return true; end
		i = i + 1;
	end
	return false;
end

-- Avertissement du bandeau de pose : nil si la piece n'exige pas de station, si le joueur est a portee ou si l'on ne sait pas.
function C.StationRangeWarning(rs, kind, names)
	if ( not kind or kind == "" ) then return nil; end
	if ( C.InStationRange(rs, kind) ~= false ) then return nil; end
	if ( kind == "workbench" ) then return "Hors de portée de la table de fabrication"; end
	return "Hors de portée : " .. ((names and names[kind]) or kind);
end

-- ------------------------------------------------------------------------------------------------
-- Competences et endurance « outils » facon Valheim (docs/VALHEIM_SKILLS.md ; serveur : server/Wowlheim/ValheimSkills.cpp).
--   EN|cur10|max10|delai_ms|clignote   endurance (dixiemes) ; regeneration simulee ici entre deux lignes (forme fermee)
--   SK|id|niveau|pourcentage            competence (barre de progression : Skill.GetLevelPercentage)
--   SKU|id|niveau                       niveau gagne ($msg_skillup)   SKL|pourcentage   perte a la mort ($msg_skills_lowered)
-- Commande : ".build api skills" (lignes SK| puis EN|).
-- ------------------------------------------------------------------------------------------------
C.SKILLS = {               -- ordre de Skills.SkillType (panneau des competences de Valheim)
	{ id = 7, name = "Haches", icon = "WL_axe_bronze", desc = "Combat à la hache : réduit l'endurance des coups de hache (jusqu'à -33 %)." },
	{ id = 12, name = "Pioches", icon = "WL_pickaxe_antler", desc = "Minage : dégâts sur la roche et endurance des coups de pioche (jusqu'à -33 %)." },
	{ id = 13, name = "Couper du bois", icon = "WL_wood", desc = "Coupe des arbres et des bûches : dégâts de coupe." },
	{ id = 107, name = "Fabrication", icon = "WL_hammer", desc = "Marteau et stations : endurance (jusqu'à -50 %) et usure du marteau." },
	n = 4,
};
C.SKILL_UP_TITLE = "Compétence améliorée";        -- $msg_skillup (localisation francaise de Valheim)
C.SKILLS_LOWERED = "Compétences abaissées";       -- $msg_skills_lowered
C.STAMINA = { regen = 6, timeMult = 1 };          -- prefab Player : m_staminaRegen, m_staminaRegenTimeMultiplier
-- outils Valheim (main droite) : la barre d'endurance s'affiche quand l'un d'eux est en main
C.TOOL_IDS = { [9201010] = "axe", [9201011] = "axe", [9201021] = "axe", [9201031] = "axe", [9201041] = "axe", [9201051] = "axe",
	[9201012] = "pick", [9201022] = "pick", [9201032] = "pick", [9201042] = "pick", [9201052] = "pick", [9201100] = "hammer" };

function C.SkillsCommand() return ".build api skills"; end

function C.SkillName(id)
	local i = 1;
	while i <= C.SKILLS.n do
		if ( C.SKILLS[i].id == id ) then return C.SKILLS[i].name; end
		i = i + 1;
	end
	return "Compétence " .. tostring(id);
end

function C.IsToolId(id)
	return id ~= nil and C.TOOL_IDS[id] ~= nil;
end

-- etat : { cur, max, at (GetTime de la ligne), delay (s), flashAt, known }
function C.NewStamina()
	return { cur = 50, max = 50, at = 0, delay = 0, flashAt = nil, known = nil };
end

-- Endurance a l'instant now : Player.UpdateStats, regen = r + (1 - s/M)·r·k apres le delai ; forme fermee
-- s(t) = s_inf - (s_inf - s0)·exp(-r·k·t/M), s_inf = M(1+k)/k, bornee a M (meme calcul que le serveur).
function C.StaminaNow(sa, now)
	local M = sa.max;
	if ( not M or M <= 0 ) then return 0; end
	local t = (now or 0) - sa.at - sa.delay;
	if ( t <= 0 or sa.cur >= M ) then return math.min(M, sa.cur); end
	local r, k = C.STAMINA.regen, C.STAMINA.timeMult;
	local s;
	if ( k <= 0 ) then
		s = sa.cur + r * t;
	else
		local inf = M * (1 + k) / k;
		s = inf - (inf - sa.cur) * math.exp(-r * k * t / M);
	end
	if ( s > M ) then s = M; end
	return s;
end

-- Ligne EN| : renvoie "flash" si le serveur a refuse une action faute d'endurance, "update" sinon
function C.StaminaOnMessage(sa, m, now)
	if ( not m or m.type ~= "EN" ) then return nil; end
	sa.cur = m.cur; sa.max = m.max; sa.delay = m.delay; sa.at = now or 0; sa.known = 1;
	if ( m.flash ) then
		sa.flashAt = now or 0;
		return "flash";
	end
	return "update";
end

C.STAMINA_FLASH = 1.0;     -- s : duree du clignotement (Hud.StaminaBarEmptyFlash)

-- Barre visible : outil Valheim en main (hache, pioche, marteau) ou endurance en cours de regeneration / clignotement
function C.StaminaBarVisible(sa, now, toolEquipped)
	if ( toolEquipped ) then return true; end
	if ( sa.flashAt and (now - sa.flashAt) < C.STAMINA_FLASH ) then return true; end
	return C.StaminaNow(sa, now) < sa.max - 0.05;
end

-- Clignotement : alpha de la barre (1 hors clignotement ; 4 alternances par seconde pendant STAMINA_FLASH)
function C.StaminaFlashAlpha(sa, now)
	if ( not sa.flashAt ) then return 1; end
	local t = now - sa.flashAt;
	if ( t < 0 or t >= C.STAMINA_FLASH ) then return 1; end
	local q = math.floor(t * 8);
	if ( q - 2 * math.floor(q / 2) == 0 ) then return 0.25; end
	return 1;
end

function C.NewSkills()
	return { levels = {}, pct = {}, loaded = nil };
end

-- Lignes SK| / SKU| / SKL| : renvoie (evenement, texte) ; evenement = "update" | "levelup" | "lowered"
function C.SkillsOnMessage(sk, m)
	if ( not m ) then return nil; end
	if ( m.type == "SK" ) then
		sk.levels[m.id] = m.level; sk.pct[m.id] = m.pct; sk.loaded = 1;
		return "update";
	elseif ( m.type == "SKU" ) then
		sk.levels[m.id] = m.level;
		return "levelup", C.SkillName(m.id) .. " niveau " .. m.level;
	elseif ( m.type == "SKL" ) then
		return "lowered", C.SKILLS_LOWERED .. " (-" .. m.pct .. " %)";
	end
	return nil;
end

-- Ligne i du panneau : { id, name, icon, desc, level, pct (0..1) }
function C.SkillRow(sk, i)
	local d = C.SKILLS[i];
	return { id = d.id, name = d.name, icon = d.icon, desc = d.desc, level = sk.levels[d.id] or 0, pct = (sk.pct[d.id] or 0) / 100 };
end

-- ------------------------------------------------------------------------------------------------
-- Touches par defaut et disposition des panneaux (ergonomie)
-- ------------------------------------------------------------------------------------------------
-- Touches par defaut, libres dans WTF\DefaultBindings.wtf du client 1.12.1 (extrait de patch.MPQ). Libres par defaut :
-- I, J, Y (lettres), ALT-A, ALT-E, CTRL-MOLETTE. Les liaisons par defaut d'un addon 1.12 ne s'appliquent pas seules :
-- ApplyDefaultBindings les pose UNE fois (WowlheimDB.bindingsDone), et seulement sur une touche libre pour une action
-- encore sans touche (jamais d'ecrasement d'un choix du joueur ni d'une liaison du jeu).
--   Y : menu du marteau (main gauche, au-dessus de T/G) ; I : fabrication (« inventaire », Tab de Valheim) ;
--   J : fonderie / four a charbon (s'ouvre aussi seule au clic sur la station) ;
--   ALT-A / ALT-E et CTRL + molette : tourner la piece. En AZERTY, A et E encadrent Z (avancer) comme Q / E dans Valheim.
--   Maj+K (version 2) : panneau des competences (K = competences de WoW ; Maj+K est libre).
-- since : version des liaisons qui a introduit la touche (posee une seule fois, a la mise a jour de l'addon).
C.BINDINGS_VERSION = 2;
C.DEFAULT_KEYS = {
	{ key = "Y", action = "WOWLHEIM_TOGGLE" },
	{ key = "I", action = "WOWLHEIM_CRAFT" },
	{ key = "J", action = "WOWLHEIM_SMELT" },
	{ key = "ALT-A", action = "WOWLHEIM_ROTATE_LEFT" },
	{ key = "ALT-E", action = "WOWLHEIM_ROTATE_RIGHT" },
	{ key = "CTRL-MOUSEWHEELDOWN", action = "WOWLHEIM_ROTATE_LEFT" },
	{ key = "CTRL-MOUSEWHEELUP", action = "WOWLHEIM_ROTATE_RIGHT" },
	{ key = "SHIFT-K", action = "WOWLHEIM_SKILLS", since = 2 },
};

-- api : { action = function(key) -> action liee ou "" / nil, keyOf = function(action) -> touche ou nil,
--         set = function(key, action), save = function() }. Renvoie la liste des touches posees (n), ou nil si deja fait.
-- Une action qui avait deja une touche AVANT l'appel (choix du joueur) n'en recoit pas d'autre.
function C.ApplyDefaultBindings(db, api)
	if ( not db or (db.bindingsDone or 0) >= C.BINDINGS_VERSION ) then return nil; end
	local done = db.bindingsDone or 0;
	local out = { n = 0 };
	local hadKey = {};
	local i = 1;
	while C.DEFAULT_KEYS[i] do
		local a = C.DEFAULT_KEYS[i].action;
		if ( hadKey[a] == nil ) then
			local k = api.keyOf(a);
			hadKey[a] = (k ~= nil and k ~= "");
		end
		i = i + 1;
	end
	i = 1;
	while C.DEFAULT_KEYS[i] do
		local d = C.DEFAULT_KEYS[i];
		local cur = api.action(d.key);
		if ( (d.since or 1) > done and (cur == nil or cur == "") and not hadKey[d.action] ) then
			api.set(d.key, d.action);
			out.n = out.n + 1;
			out[out.n] = d.key;
		end
		i = i + 1;
	end
	if ( out.n > 0 ) then api.save(); end
	db.bindingsDone = C.BINDINGS_VERSION;
	return out;
end

-- Panneaux : taille de construction (w, h) et echelle par defaut (taille a l'ecran = w * scale).
C.PANELS = {
	-- tailles construites (marges de 16, pas de 8) ; marteau 400 x 0,85 = 340 et fonderie 236 x 0,85 = 200,6 : en 1024x768 la
	-- fonderie (haut a 640, sous le bandeau) finit a 439,4, au-dessus du marteau (96 + 340 = 436).
	hammer = { w = 496, h = 400, scale = 0.85 },     -- Wowlheim.lua : 16 + 10 x 44 + 24 + 16 ; 12 + 24 + 8 + 20 + 8 + 176 + 8 + 112 + 8 + 16 + 8
	craft = { w = 600, h = 412, scale = 0.8 },       -- WowlheimCraft.lua : en-tete 28, recherche 20, liste / fiche 324, message 24
	smelt = { w = 328, h = 236, scale = 0.85 },      -- WowlheimCraft.lua : en-tete 32, 3 barres, produits, boutons 24, message 12
	skills = { w = 260, h = 192, scale = 0.85 },     -- WowlheimSkills.lua : titre 44 + 4 lignes de 34 (30 + 4) - 4 + marge 16
};
-- Barre d'endurance (Hud de Valheim : barre jaune) : juste au-dessus des bandeaux « Mode : … » / rappel de pose (TOP -96)
C.STAMINA_BAR = { w = 200, h = 8, top = 82 };
-- Zones a laisser libres (coordonnees UIParent, 768 de haut) : barres d'action en bas (96), barres verticales a droite
-- (100), bandeaux « Mode : … » / rappel de pose en haut au centre (TOP -96, 400 x 30), cadres joueur / cible en haut a gauche.
C.BOTTOM_BARS = 96;
C.RIGHT_BARS = 100;
C.BANNER_TOP = 96;
C.BANNER_H = 32;          -- 2 lignes au plus (piece + rotation, puis ressources manquantes / avertissement de portee en rouge)
C.BANNER_W = 480;

-- Taille a l'ecran d'un panneau
function C.PanelSize(key)
	local p = C.PANELS[key];
	return p.w * p.scale, p.h * p.scale;
end

-- Position par defaut (coin bas-gauche, unites UIParent) : marteau en bas a droite au-dessus des barres d'action ;
-- fabrication en haut a gauche sous les cadres joueur / cible ; fonderie a droite de la fabrication. Le centre de l'ecran
-- (personnage, sol devant lui) reste libre des 16:9.
function C.PanelDefaultPos(key, sw, sh)
	sw = sw or 1024; sh = sh or 768;
	local w, h = C.PanelSize(key);
	if ( key == "hammer" ) then
		return sw - C.RIGHT_BARS - w, C.BOTTOM_BARS;
	elseif ( key == "craft" ) then
		return 16, sh - 130 - h;
	end
	if ( key == "skills" ) then
		-- en haut, a droite de la fonderie : loin de la fenetre de discussion (bas gauche) et du menu du marteau (bas droite)
		local cw2 = C.PanelSize("craft");
		local fw = C.PanelSize("smelt");
		return 16 + cw2 + 8 + fw + 8, sh - 128 - h;
	end
	local cw = C.PanelSize("craft");
	return 16 + cw + 8, sh - 128 - h;   -- juste sous le bandeau (haut a 640 sur 768) : au-dessus du menu du marteau en 1024x768
end

-- Position memorisee (WowlheimDB.pos[key] = { left, bottom }) ramenee dans l'ecran, sinon position par defaut.
function C.PanelPos(key, saved, sw, sh)
	sw = sw or 1024; sh = sh or 768;
	if ( not saved or not saved[1] or not saved[2] ) then return C.PanelDefaultPos(key, sw, sh); end
	local w, h = C.PanelSize(key);
	return C.Clamp(saved[1], 0, math.max(0, sw - w)), C.Clamp(saved[2], 0, math.max(0, sh - h));
end

-- Rectangle a l'ecran { l, b, r, t }
function C.PanelRect(key, left, bottom)
	local w, h = C.PanelSize(key);
	return { l = left, b = bottom, r = left + w, t = bottom + h };
end

function C.BannerRect(sw, sh)
	sw = sw or 1024; sh = sh or 768;
	return { l = sw / 2 - C.BANNER_W / 2, r = sw / 2 + C.BANNER_W / 2, t = sh - C.BANNER_TOP, b = sh - C.BANNER_TOP - C.BANNER_H };
end

function C.StaminaBarRect(sw, sh)
	sw = sw or 1024; sh = sh or 768;
	local b = C.STAMINA_BAR;
	return { l = sw / 2 - b.w / 2, r = sw / 2 + b.w / 2, t = sh - b.top, b = sh - b.top - b.h };
end

function C.RectsOverlap(a, b)
	return a.l < b.r and b.l < a.r and a.b < b.t and b.b < a.t;
end

-- ------------------------------------------------------------------------------------------------
-- Controles du mode construction (docs/BUILD_CONTROLS.md) : marteau equipe en mode construction, le ciblage au sol du sort
-- de pose est actif en continu ; clic gauche = poser (la piece reste choisie), clic droit = menu (le client annule le
-- ciblage : l'addon detecte « ciblage termine sans pose »), clic milieu = demolir la piece sous la souris, molette = tourner.
-- Aucune fonction protegee : liaisons TEMPORAIRES (SetBinding sans SaveBindings), retablies a la sortie du mode.
-- ------------------------------------------------------------------------------------------------
C.PIECE_ENTRY_MIN = 9110000;
C.PIECE_ENTRY_MAX = 9119999;
C.BUILD_KEYS = {
	{ key = "BUTTON3", action = "WOWLHEIM_REMOVE" },            -- d'origine : MOVEANDSTEER
	{ key = "MOUSEWHEELUP", action = "WOWLHEIM_ROTATE_RIGHT" },  -- d'origine : CAMERAZOOMIN
	{ key = "MOUSEWHEELDOWN", action = "WOWLHEIM_ROTATE_LEFT" }, -- d'origine : CAMERAZOOMOUT
};
-- option (/wl qe on) : Q / E tournent la piece comme dans Valheim (d'origine : pas lateraux STRAFELEFT / STRAFERIGHT)
C.BUILD_KEYS_QE = {
	{ key = "Q", action = "WOWLHEIM_ROTATE_LEFT" },
	{ key = "E", action = "WOWLHEIM_ROTATE_RIGHT" },
};
-- liaisons d'origine du client 1.12.1 (WTF\DefaultBindings.wtf), pour reparer une liaison temporaire restee enregistree
C.BUILD_KEYS_ORIGINAL = { BUTTON3 = "MOVEANDSTEER", MOUSEWHEELUP = "CAMERAZOOMIN", MOUSEWHEELDOWN = "CAMERAZOOMOUT",
	Q = "STRAFELEFT", E = "STRAFERIGHT" };

-- Les liaisons temporaires doivent-elles etre posees ? Marteau equipe, mode construction (pas Demolir / Reparer : le clic
-- droit y garde son sens WoW, utiliser la construction visee).
function C.BuildControlsWanted(st, equipped)
	if ( not equipped or not st ) then return false; end
	return st.mode == "build";
end

function C.BuildKeys(qe)
	local out = { n = 0 };
	local i = 1;
	while C.BUILD_KEYS[i] do out.n = out.n + 1; out[out.n] = C.BUILD_KEYS[i]; i = i + 1; end
	if ( qe ) then
		i = 1;
		while C.BUILD_KEYS_QE[i] do out.n = out.n + 1; out[out.n] = C.BUILD_KEYS_QE[i]; i = i + 1; end
	end
	return out;
end

-- Action temporaire posee par l'addon sur cette touche (nil : touche non geree)
function C.BuildKeyAction(key)
	local i = 1;
	while C.BUILD_KEYS[i] do
		if ( C.BUILD_KEYS[i].key == key ) then return C.BUILD_KEYS[i].action; end
		i = i + 1;
	end
	i = 1;
	while C.BUILD_KEYS_QE[i] do
		if ( C.BUILD_KEYS_QE[i].key == key ) then return C.BUILD_KEYS_QE[i].action; end
		i = i + 1;
	end
	return nil;
end

-- saved : { [touche] = action precedente ("" = aucune) } (aussi dans WowlheimDB.tempBinds : survit a /reload et a un plantage).
-- api : { action = function(key) -> action liee, set = function(key, action) (action "" : delier) }. JAMAIS de SaveBindings.
-- Renvoie le nombre de touches posees.
function C.TempBindApply(saved, api, keys)
	local n = 0;
	local i = 1;
	while i <= keys.n do
		local d = keys[i];
		if ( saved[d.key] == nil ) then
			local cur = api.action(d.key) or "";
			if ( cur ~= d.action ) then
				saved[d.key] = cur;
				api.set(d.key, d.action);
				n = n + 1;
			end
		end
		i = i + 1;
	end
	return n;
end

-- Retablit les liaisons memorisees ; une touche que le joueur a reliee entre-temps (Menu > Raccourcis) n'est pas touchee.
-- Renvoie le nombre de touches retablies.
function C.TempBindRestore(saved, api)
	local n = 0;
	local keys = {};
	for k in pairs(saved) do table.insert(keys, k); end
	table.sort(keys);
	local i = 1;
	while keys[i] do
		local k = keys[i];
		local cur = api.action(k) or "";
		if ( cur == C.BuildKeyAction(k) ) then
			api.set(k, saved[k]);
			n = n + 1;
		end
		saved[k] = nil;
		i = i + 1;
	end
	return n;
end

-- Liaison temporaire restee enregistree sans memoire de l'ancienne valeur (SaveBindings par le menu Raccourcis pendant la
-- construction) : remise a la liaison d'origine du client. Renvoie le nombre de touches reparees.
function C.TempBindRepair(api)
	local n = 0;
	for k, orig in pairs(C.BUILD_KEYS_ORIGINAL) do
		if ( (api.action(k) or "") == C.BuildKeyAction(k) ) then
			api.set(k, orig);
			n = n + 1;
		end
	end
	return n;
end

-- Clic milieu : commande de demolition de la piece sous la souris. guidHex, entry : WowlheimGetMouseoverObject() de la DLL ;
-- hasApi : la DLL fournit l'API. Renvoie la commande, ou nil + message (« Rien à démolir. »).
C.REMOVE_FALLBACK = ".build api remove";       -- sans DLL : piece la plus proche a 6 m
-- Objet sous la souris (WowlheimGetMouseoverObject) : est-ce une piece Wowlheim (guid de 16 chiffres hexadecimaux) ?
function C.IsPieceObject(guidHex, entry)
	entry = tonumber(entry);
	return guidHex ~= nil and entry ~= nil and entry >= C.PIECE_ENTRY_MIN and entry <= C.PIECE_ENTRY_MAX
		and string.len(guidHex) == 16 and not string.find(guidHex, "[^0-9A-Fa-f]");
end

function C.RemoveCommand(hasApi, guidHex, entry)
	if ( not hasApi ) then return C.REMOVE_FALLBACK; end
	if ( C.IsPieceObject(guidHex, entry) ) then
		return ".build api removeguid " .. guidHex;
	end
	return nil, "Rien à démolir.";
end

-- ------------------------------------------------------------------------------------------------
-- Piece visee (Valheim : Player.UpdateWearNTearHover -> WearNTear.Highlight, en mode construction : la piece sous le
-- viseur prend la couleur de son support ; Hud : nom de la piece pres du viseur). DLL : WowlheimGetMouseoverObject +
-- WowlheimHighlightObject (docs/BUILD_CONTROLS.md section 9). Surbrillance dans les trois modes du marteau (Valheim : tout
-- le mode construction) ; info-bulle (nom, action) en modes Demolir / Reparer seulement (en pose, le bandeau suffit).
-- ------------------------------------------------------------------------------------------------
C.HOVER_GLOW = 0.4;                         -- _EmissionColor = couleur * 0.4
C.HOVER_TIP_W = 200;                        -- info-bulle : largeur, decalage depuis le curseur (droite, bas)
C.HOVER_TIP_DX = 18;
C.HOVER_TIP_DY = 18;
function C.HoverWanted(st, equipped)
	if ( not equipped or not st ) then return false; end
	return st.mode == "build" or st.mode == "remove" or st.mode == "repair";
end
-- La souris est-elle sur le monde ? focus = GetMouseFocus() (1.12 : WorldFrame sur le monde, nil possible) : sur un cadre
-- d'interface (sac, barre d'actions, panneau...), ni surbrillance ni info-bulle de piece (capture p2/120_deposit).
function C.MouseOnWorld(focus, world)
	return focus == nil or focus == world;
end
-- Info-bulle de la piece visee : dans les trois modes (Valheim, marteau en main : nom + sante de la piece visee) ; ligne
-- d'action en Demolir / Reparer seulement.
function C.HoverTipWanted(st)
	return st ~= nil and (st.mode == "build" or st.mode == "remove" or st.mode == "repair");
end

-- Unity Color.RGBToHSV / HSVToRGB (hdr : V peut depasser 1)
function C.RGBToHSV(r, g, b)
	local mx = math.max(r, math.max(g, b));
	local mn = math.min(r, math.min(g, b));
	local d = mx - mn;
	if ( mx <= 0 or d <= 0 ) then return 0, 0, mx; end
	local h;
	if ( mx == r ) then h = (g - b) / d;
	elseif ( mx == g ) then h = 2 + (b - r) / d;
	else h = 4 + (r - g) / d; end
	h = h / 6;
	if ( h < 0 ) then h = h + 1; end
	return h, d / mx, mx;
end
function C.HSVToRGB(h, s, v)
	if ( s <= 0 ) then return v, v, v; end
	local h6 = h * 6;
	local i = math.floor(h6);
	local f = h6 - i;
	local p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f));
	i = math.mod(i, 6);
	if ( i == 0 ) then return v, t, p;
	elseif ( i == 1 ) then return q, v, p;
	elseif ( i == 2 ) then return p, v, t;
	elseif ( i == 3 ) then return p, q, v;
	elseif ( i == 4 ) then return t, p, v; end
	return v, p, q;
end

-- WearNTear.Highlight : support = GetSupportColorValue (0 = support minimal .. 1 = solide ; nil ou < 0 = support complet ou
-- inconnu -> bleu clair (0.6, 0.8, 1)). Sinon Lerp(rouge, vert, v) en HSV, saturation Lerp(1, 0.5, v), valeur
-- Lerp(1.2, 0.9, v). Renvoie r, g, b (diffuse ; l'emissif vaut r, g, b * C.HOVER_GLOW).
function C.HighlightColor(support)
	if ( not support or support < 0 ) then return 0.6, 0.8, 1.0; end
	local v = support;
	if ( v > 1 ) then v = 1; end
	local h = C.RGBToHSV(1 - v, v, 0);
	return C.HSVToRGB(h, 1 - 0.5 * v, 1.2 - 0.3 * v);
end

-- Info-bulle de la piece visee : nom (catalogue), action du clic droit dans le mode courant. nil hors piece Wowlheim.
function C.HoverTip(st, entry, pieces)
	entry = tonumber(entry);
	if ( not entry or entry < C.PIECE_ENTRY_MIN or entry > C.PIECE_ENTRY_MAX ) then return nil; end
	local name = C.PieceName(pieces, entry - C.GHOST_BASE);
	local action = nil;
	if ( st and st.mode == "remove" ) then action = "Clic droit : démolir";
	elseif ( st and st.mode == "repair" ) then action = "Clic droit : réparer"; end
	return name, action;
end

-- ------------------------------------------------------------------------------------------------
-- Etat de la piece visee (".build api pieceinfo <guid>" -> PI|guid|pv|pvmax|support|nom) : couleur de la surbrillance
-- (WearNTear.Highlight / GetSupportColorValue) et lignes « Santé : 75 % » / support de l'info-bulle. Une interrogation
-- silencieuse au changement de piece visee, puis toutes les C.PIECEINFO_REFRESH s tant que la souris reste dessus.
-- ------------------------------------------------------------------------------------------------
C.PIECEINFO_REFRESH = 2;   -- s
C.PIECEINFO_KEEP = 10;     -- s : au-dela, l'etat recu est oublie (couleur bleu clair par defaut)
function C.NewPieceInfo()
	return { asked = nil, at = -100, last = nil, unsupported = nil };
end

function C.PieceInfoCommand(pi, guidHex, now, pending)
	if ( pi.unsupported or pending or not guidHex ) then return nil; end
	local g = string.upper(guidHex);
	if ( pi.asked == g and now - pi.at < C.PIECEINFO_REFRESH ) then return nil; end
	pi.asked = g;
	pi.at = now;
	return ".build api pieceinfo " .. g;
end

-- Ligne recue pour pieceinfo (entry = ChannelRoute) ; "update" si l'etat change
function C.PieceInfoOnMessage(pi, m, entry, now)
	if ( not m or not entry or entry.cmd ~= "pieceinfo" ) then return nil; end
	if ( m.type == "PI" ) then
		pi.last = { guid = m.guid, hp = m.hp, hpMax = m.hpMax, support = m.support, name = m.name, at = now or 0 };
		return "update";
	elseif ( m.type == "E" and m.text == "commande inconnue" ) then
		pi.unsupported = 1;      -- ancien serveur : couleur « support complet », sans sante
		return "update";
	end
	return nil;
end

-- Etat connu de la piece guidHex (ou nil)
function C.PieceInfoFor(pi, guidHex, now)
	local l = pi.last;
	if ( not l or not guidHex or l.guid ~= string.upper(guidHex) ) then return nil; end
	if ( now and now - l.at > C.PIECEINFO_KEEP ) then return nil; end
	return l;
end

-- Lignes de l'info-bulle : « Santé : 75 % » et etat du support ({ text, r, g, b }). info = PieceInfoFor (nil : rien).
-- Support (GetSupportColorValue) : -1 complet (ancree au sol ou soutenue au maximum), puis solide / moyen / faible / critique,
-- dans la couleur de la surbrillance.
function C.PieceInfoLines(info)
	if ( not info ) then return nil, nil; end
	local pct = 100;
	if ( info.hpMax and info.hpMax > 0 ) then pct = math.floor(100 * info.hp / info.hpMax + 0.5); end
	if ( pct > 100 ) then pct = 100; end
	if ( pct < 0 ) then pct = 0; end
	local health = { text = "Santé : " .. pct .. " %", r = 1, g = 1, b = 1 };
	if ( pct <= 25 ) then health.r, health.g, health.b = 1, 0.35, 0.3;
	elseif ( pct <= 60 ) then health.r, health.g, health.b = 1, 0.82, 0.3; end
	local v = info.support;
	local word;
	if ( not v or v < 0 ) then word = "Support : complet";
	elseif ( v >= 0.75 ) then word = "Support : solide";
	elseif ( v >= 0.4 ) then word = "Support : moyen";
	elseif ( v >= 0.15 ) then word = "Support : faible";
	else word = "Support : critique"; end
	local r, g, b = C.HighlightColor(v);
	if ( r > 1 ) then r = 1; end
	if ( g > 1 ) then g = 1; end
	if ( b > 1 ) then b = 1; end
	return health, { text = word, r = r, g = g, b = b };
end

-- ------------------------------------------------------------------------------------------------
-- Son de demolition (Valheim : WearNTear.m_destroyedEffect, bois / pierre / metal qui se brise) : sons du client 1.12
-- (Sound\Doodad, SoundEntries.dbc) selon la matiere principale de la piece, deduite de ses couts (WowlheimData).
-- ------------------------------------------------------------------------------------------------
C.DESTROY_SOUNDS = {
	wood = "Sound\\Doodad\\DeadmineDoor01Destroy.wav",          -- porte en bois des Mortemines enfoncee (SoundEntries 3079)
	stone = "Sound\\Doodad\\G_CaveinClosed.wav",                  -- eboulement de roches (SoundEntries 4634)
	metal = "Sound\\Doodad\\BlackRockDoorSingleDestroy.wav",      -- porte de Rochenoire detruite (SoundEntries 6533)
};
C.STONE_ITEMS = { [9200002] = true, [9200032] = true };                       -- Pierre, Obsidienne
C.METAL_ITEMS = { [9200013] = true, [9200014] = true, [9200015] = true, [9200021] = true, [9200031] = true, [9200041] = true };

-- Matiere d'une piece du catalogue : celle du cout le plus eleve (pierre / metal / bois par defaut)
function C.PieceMaterial(p)
	local best, n = "wood", 0;
	local i = 1;
	while p and p.costs and p.costs[i] do
		local id, k = p.costs[i][1], p.costs[i][2] or 0;
		local mat = "wood";
		if ( C.STONE_ITEMS[id] ) then mat = "stone"; elseif ( C.METAL_ITEMS[id] ) then mat = "metal"; end
		if ( k > n ) then best, n = mat, k; end
		i = i + 1;
	end
	return best;
end

-- Ligne serveur « M|Démoli : Mur en bois. » (removeguid, clic en mode Demolir) -> chemin du son, ou nil
function C.DestroySound(m, pieces)
	if ( not m or m.type ~= "M" or not m.text ) then return nil; end
	local _, _, name = string.find(m.text, "^Démoli : (.+)%.$");
	if ( not name ) then return nil; end
	local i = 1;
	while pieces and pieces[i] do
		if ( pieces[i].name == name ) then return C.DESTROY_SOUNDS[C.PieceMaterial(pieces[i])]; end
		i = i + 1;
	end
	return C.DESTROY_SOUNDS.wood;
end

-- Clic droit sur une grande piece (fonderie, forge...) : le client 1.12 mesure 5 m depuis le CENTRE de l'objet et refuse avant
-- d'envoyer CMSG_GAMEOBJ_USE (« You are too far away. », ERR_USE_TOO_FAR, UI_ERROR_MESSAGE). Valheim : on interagit a ~2-3 m
-- de la surface. Si la piece sous la souris est une piece Wowlheim, l'addon envoie « .build api use <guid> » (le serveur
-- verifie 3 m du bord de la boite puis suit le chemin de GameObject::Use) et masque le message rouge.
-- UseRetry(ur, message, tooFarText, guidHex, entry, now) -> commande ou nil, masquer (true : ne pas afficher le message).
-- Un meme clic peut produire plusieurs erreurs : une seule commande par piece en C.USE_RETRY s (les suivantes sont masquees).
C.USE_TOO_FAR = "You are too far away.";      -- ERR_USE_TOO_FAR du client anglais (repli si la constante est absente)
C.USE_RETRY = 0.25;
function C.NewUseRetry()
	return { guid = nil, at = nil };
end

function C.IsUseTooFar(message, tooFarText)
	if ( not message ) then return false; end
	return message == (tooFarText or C.USE_TOO_FAR) or message == C.USE_TOO_FAR;
end

function C.UseRetry(ur, message, tooFarText, guidHex, entry, now)
	if ( not C.IsUseTooFar(message, tooFarText) or not C.IsPieceObject(guidHex, entry) ) then return nil, false; end
	now = now or 0;
	if ( ur.guid == guidHex and ur.at and now >= ur.at and (now - ur.at) < C.USE_RETRY ) then
		return nil, true;
	end
	ur.guid = guidHex;
	ur.at = now;
	return ".build api use " .. guidHex, true;
end

-- Fin du ciblage au sol sans pose = clic droit (le client annule le ciblage ; seul l'effet « maison » tourne a la place).
-- tw.active : notre ciblage est en cours ; tw.endedAt : il vient de finir ; tw.castAt : sort / pose vu (SPELLCAST_*, D|place) ;
-- tw.removeAt : clic milieu (s'il a annule le ciblage, on le relance au lieu d'ouvrir le menu).
C.RIGHTCLICK_WINDOW = 0.3;
-- Pose en chaine : aucun etat sans issue. Un UseInventoryItem qui ne donne pas de ciblage (refuse par le client) etait
-- abandonne en silence apres ARM_TIMEOUT : bandeau affiche, pas de fantome, clic gauche sans effet, Echap ouvrant le menu
-- du jeu (regression constatee en jeu, captures p2/115-118). Desormais : nouvelle tentative, puis menu apres ARM_RETRIES
-- echecs de suite ; une pose vue (clic gauche) sans reponse du serveur dans PLACE_WAIT s relance aussi le ciblage.
C.ARM_TIMEOUT = 0.5;       -- s : UseInventoryItem sans ciblage au bout de ce delai = tentative ratee
C.ARM_RETRIES = 3;         -- tentatives ratees de suite avant de rouvrir le menu (la piece reste choisie)
C.PLACE_WAIT = 2;          -- s : pose vue (SPELLCAST_*, D|place) sans relance par le serveur -> relance quand meme
-- Demarrage du ciblage du marteau. En 1.12, UseInventoryItem appele par un addon hors d'une touche / d'un clic (OnUpdate,
-- evenement CHAT_MSG : relance apres la pose) est refuse EN SILENCE par le client (Spell_C_CastSpell -> CanPerformAction(2)
-- 0x494a50 : code d'addon sans evenement materiel). La DLL fournit WowlheimUseHammer(slot) qui fait le meme appel avec le
-- drapeau « touche en cours » ([0xcf4dc4]) : pose en chaine de Valheim. Sans DLL : UseInventoryItem (premiere pose,
-- declenchee par un clic, seulement). Renvoie "dll" ou "lua" (voie utilisee) et, pour "dll", 1 si le ciblage a commence.
function C.UseHammer(useHammer, useItem, slot)
	slot = slot or C.HAMMER_SLOT;
	if ( useHammer ) then
		return "dll", useHammer(slot);
	end
	useItem(slot);
	return "lua";
end

function C.NewTargetWatch()
	return { armedAt = nil, active = nil, endedAt = nil, castAt = nil, removeAt = nil, fails = 0, waitAt = nil };
end

-- Juste apres UseInventoryItem : la surveillance commence quand SpellIsTargeting() devient vrai.
function C.TargetWatchStart(tw, now)
	tw.armedAt = now or 0; tw.active = nil; tw.endedAt = nil; tw.castAt = nil; tw.waitAt = nil;
end

-- Arret voulu par l'addon (Echap, choix de Demolir / Reparer, annulation, marteau range)
function C.TargetWatchStop(tw)
	tw.armedAt = nil; tw.active = nil; tw.endedAt = nil; tw.castAt = nil; tw.waitAt = nil; tw.fails = 0;
end

function C.TargetWatchCast(tw, now)
	if ( tw.active or tw.endedAt ) then tw.castAt = now; end
end

function C.TargetWatchRemove(tw, now)
	tw.removeAt = now;
end

local function Recent(t, now)
	return t and now - t <= C.RIGHTCLICK_WINDOW;
end

-- A chaque image. targeting : SpellIsTargeting() ; rightDown : IsMouseButtonDown("RightButton") si disponible (non verifie
-- en 1.12). Renvoie "menu" (clic droit, ou ciblage impossible a relancer : ouvrir le menu), "relaunch" (clic milieu qui a
-- annule le ciblage, UseInventoryItem sans ciblage, pose sans reponse du serveur) ou nil.
function C.TargetWatchUpdate(tw, targeting, now, rightDown)
	if ( tw.armedAt ) then
		if ( targeting ) then
			tw.armedAt = nil;
			tw.active = 1;
			tw.fails = 0;
		elseif ( now - tw.armedAt > C.ARM_TIMEOUT ) then
			tw.armedAt = nil;
			tw.fails = (tw.fails or 0) + 1;
			if ( tw.fails >= C.ARM_RETRIES ) then
				tw.fails = 0;
				return "menu";
			end
			return "relaunch";
		end
		return nil;
	end
	if ( tw.active ) then
		if ( targeting ) then return nil; end
		tw.active = nil;
		if ( Recent(tw.castAt, now) ) then tw.castAt = nil; tw.waitAt = now; return nil; end
		if ( Recent(tw.removeAt, now) ) then tw.removeAt = nil; return "relaunch"; end
		if ( rightDown ) then return "menu"; end
		tw.endedAt = now;
		return nil;
	end
	if ( tw.endedAt ) then
		if ( tw.castAt and tw.castAt >= tw.endedAt ) then
			tw.endedAt = nil; tw.castAt = nil; tw.waitAt = now;
			return nil;
		end
		if ( now - tw.endedAt >= C.RIGHTCLICK_WINDOW ) then
			tw.endedAt = nil;
			return "menu";
		end
		return nil;
	end
	-- pose vue, en attente de D|place / M| (le serveur relance via WL.relaunchAt -> TargetWatchStart efface waitAt)
	if ( tw.waitAt and not targeting and now - tw.waitAt >= C.PLACE_WAIT ) then
		tw.waitAt = nil;
		return "relaunch";
	end
	return nil;
end

-- ------------------------------------------------------------------------------------------------
-- Prechargement des modeles des pieces (DLL : WowlheimPreloadModel, docs/BUILD_CONTROLS.md §4.2). Les chemins viennent du
-- serveur (".build api models" -> MD|id:prefab,... ; WowlheimData ne contient pas les prefabs) : World\Wowlheim\<prefab>.m2.
-- ------------------------------------------------------------------------------------------------
C.MODEL_DIR = "World\\Wowlheim\\";
C.PRELOAD_BATCH = 10;      -- modeles par image (ne pas figer l'ecran)

function C.ModelsCommand() return ".build api models"; end

function C.NewModels()
	return { paths = {}, tmp = nil, loaded = nil, unsupported = nil };
end

-- Renvoie "update" a D|models (liste complete), nil sinon.
function C.ModelsOnMessage(ms, m)
	if ( not m ) then return nil; end
	if ( m.type == "MD" ) then
		if ( not ms.tmp ) then ms.tmp = {}; end
		local i = 1;
		while i <= m.models.n do
			ms.tmp[m.models[i].id] = C.MODEL_DIR .. m.models[i].prefab .. ".m2";
			i = i + 1;
		end
	elseif ( m.type == "D" and m.command == "models" ) then
		if ( m.ok and ms.tmp ) then
			ms.paths = ms.tmp;
			ms.loaded = 1;
		elseif ( not m.ok ) then
			ms.unsupported = 1;
		end
		ms.tmp = nil;
		return "update";
	end
	return nil;
end

-- Chemins a precharger : pieces connues (C.PieceKnown ; toutes tant que known n'a pas repondu), sans celles deja faites (done).
function C.PreloadList(pieces, ms, known, counts, near, done)
	local out = { n = 0 };
	local seen = {};
	local i = 1;
	while pieces[i] do
		local p = pieces[i];
		local path = ms.paths[p.id];
		if ( path and not done[path] and not seen[path] and C.PieceKnown(known, p, counts or {}, near or {}) ) then
			seen[path] = true;
			out.n = out.n + 1;
			out[out.n] = path;
		end
		i = i + 1;
	end
	return out;
end

-- ------------------------------------------------------------------------------------------------
-- Fantome de pose (fantome natif du sort 40001, DLL ; docs/GHOST_PREVIEW.md §2quater).
-- Orientation : le serveur pose avec orientation du personnage + rot x 22,5 deg (BuildingMgr::PlaceOrientation) ; la DLL
-- ajoute le meme decalage a l'orientation native (celle du personnage) a chaque image : WowlheimSetPlaceFacing(decalage, 1).
-- Couleur (Valheim : Player.SetPlacementGhostValid) : normal si la pose est possible, rouge sinon. Controles locaux
-- immediats (ressources des sacs, zone des stations recue par ST|, portee du sort lue par la DLL) et verdict du serveur
-- (".build api canplace x y z rot" : portee 8 m, zone, station, ressources, accroche, emplacement occupe), au plus
-- toutes les C.GHOST_POLL s et seulement quand le point vise ou la rotation change (ou toutes les C.GHOST_REFRESH s).
-- ------------------------------------------------------------------------------------------------
C.ROT_RAD = math.pi / 8;   -- 22,5 deg
C.GHOST_POLL = 0.25;       -- s entre deux canplace (<= 4 par seconde : sous l'anti-flood du chat, 10 messages dans la meme seconde)
C.GHOST_REFRESH = 1;       -- s : nouvelle interrogation meme immobile (le joueur, les sacs ou les pieces voisines changent)
C.GHOST_MOVE = 0.1;        -- m : deplacement du point vise qui justifie une nouvelle interrogation
C.GHOST_STALE = 1.5;       -- s : un verdict du serveur plus ancien est ignore (controles locaux seuls)
-- r, g, b, alpha, lueur (DLL : WowlheimGhostSetColor(r, g, b, a, lueur, 1) ; 1 = fantome natif)
C.GHOST_COLORS = { valid = { 1, 1, 1, 1, 0 }, invalid = { 1, 0.25, 0.2, 0.75, 0.45 } };

function C.PlaceFacingOffset(rot)
	return (rot or 0) * C.ROT_RAD;
end

function C.CanPlaceCommand(x, y, z, rot)
	return string.format(".build api canplace %.2f %.2f %.2f %d", x, y, z, rot or 0);
end

function C.NewGhostCheck()
	return { at = -100, x = nil, y = nil, z = nil, piece = nil, rot = nil,
		ok = nil, why = nil, answerAt = -100, answerPiece = nil, answerRot = nil, unsupported = nil, snap = nil };
end

-- Nouveau ciblage (relance apres une pose) : le verdict precedent ne vaut plus (la piece vient d'etre posee a ce point) ;
-- nouvelle interrogation des la premiere image. L'ancien serveur (unsupported) reste memorise.
function C.GhostCheckReset(gc)
	gc.at = -100; gc.x = nil; gc.y = nil; gc.z = nil; gc.piece = nil; gc.rot = nil;
	gc.ok = nil; gc.why = nil; gc.answerAt = -100; gc.answerPiece = nil; gc.answerRot = nil; gc.snap = nil;
end

-- Commande canplace a envoyer maintenant, ou nil. pos = { x, y, z } (WowlheimGhostGetPos) ; pending : une interrogation
-- canplace attend encore sa reponse (une seule a la fois).
function C.GhostCheckCommand(gc, st, pos, now, pending)
	if ( gc.unsupported or pending or not pos or not st or not st.piece or st.mode ~= "build" ) then return nil; end
	if ( now - gc.at < C.GHOST_POLL ) then return nil; end
	local changed = gc.x == nil or gc.piece ~= st.piece or gc.rot ~= st.rot
		or math.abs(pos.x - gc.x) > C.GHOST_MOVE or math.abs(pos.y - gc.y) > C.GHOST_MOVE or math.abs(pos.z - gc.z) > C.GHOST_MOVE;
	if ( not changed and now - gc.at < C.GHOST_REFRESH ) then return nil; end
	gc.at = now;
	gc.x = pos.x; gc.y = pos.y; gc.z = pos.z;
	gc.piece = st.piece; gc.rot = st.rot;
	return C.CanPlaceCommand(pos.x, pos.y, pos.z, st.rot);
end

-- Ligne recue pour la commande canplace (entry = ChannelRoute) ; "update" si le verdict change d'etat.
function C.GhostCheckOnMessage(gc, m, entry, now)
	if ( not m or not entry or entry.cmd ~= "canplace" ) then return nil; end
	if ( m.type == "CP" ) then
		gc.ok = m.ok;
		gc.why = m.why;
		gc.answerAt = now or 0;
		gc.answerPiece = gc.piece;
		gc.answerRot = gc.rot;
		-- position apres accroche (nouveau serveur) pour le point interroge (gc.x, gc.y, gc.z : une seule question a la fois)
		if ( m.x and gc.x ) then
			gc.snap = { x = m.x, y = m.y, z = m.z, o = m.o, snapped = m.snapped, qx = gc.x, qy = gc.y, qz = gc.z };
		else
			gc.snap = nil;
		end
		return "update";
	elseif ( m.type == "E" and m.text == "commande inconnue" ) then
		gc.unsupported = 1;          -- ancien serveur : controles locaux seuls
		gc.ok = nil;
		return "update";
	end
	return nil;
end

-- Le fantome est-il valide ? Renvoie valid, raison (nil si valide).
--   o.st (etat du marteau), o.costs, o.counts, o.station (kind exige), o.rings, o.range (DLL : 0 dans la portee du sort,
--   1 hors portee, 3 inconnu), o.gc (verdict du serveur), o.now.
-- Ordre : hors portee du sort (le client refuserait le lancement) ; verdict recent du serveur pour la meme piece / rotation
-- (il fait foi : mode sans cout, accroche...) ; sinon controles locaux (ressources, zone des stations).
function C.GhostValid(o)
	if ( o.range == 1 ) then return false, "Trop loin."; end
	local gc = o.gc;
	if ( gc and gc.ok ~= nil and o.st and gc.answerPiece == o.st.piece and gc.answerRot == o.st.rot
		and (o.now or 0) - gc.answerAt <= C.GHOST_STALE ) then
		if ( gc.ok ) then return true, nil; end
		return false, gc.why;
	end
	if ( o.costs and o.counts ) then
		local ok = C.Affordability(o.costs, o.counts);
		if ( not ok ) then return false, "Ressources manquantes."; end
	end
	local warn = C.StationRangeWarning(o.rings, o.station);
	if ( warn ) then return false, warn; end
	return true, nil;
end

-- Fantome accroche (Valheim : Player.UpdatePlacementGhost montre le fantome au point accroche). Renvoie la position
-- accrochee { x, y, z, o } du dernier verdict du serveur, ou nil (pas d'accroche, verdict perime, autre piece / rotation,
-- ou point vise deplace de plus de C.GHOST_SNAP_KEEP m depuis la question : le fantome suit alors la souris).
C.GHOST_SNAP_KEEP = 0.75;  -- m
function C.GhostSnapPos(gc, st, pos, now)
	local s = gc and gc.snap;
	if ( not s or not s.snapped or not st or not pos ) then return nil; end
	if ( gc.answerPiece ~= st.piece or gc.answerRot ~= st.rot or (now or 0) - gc.answerAt > C.GHOST_STALE ) then return nil; end
	local dx, dy, dz = pos.x - s.qx, pos.y - s.qy, pos.z - s.qz;
	if ( dx * dx + dy * dy + dz * dz > C.GHOST_SNAP_KEEP * C.GHOST_SNAP_KEEP ) then return nil; end
	return s;
end

-- Couleur a donner au fantome : "valid" / "invalid".
function C.GhostColorKey(valid)
	if ( valid ) then return "valid"; end
	return "invalid";
end
