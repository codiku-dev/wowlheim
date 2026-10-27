// Wowlheim — connaissances façon Valheim et réparation à la station. Règles et preuves : docs/VALHEIM_RULES.md §10 et §11.
#include "Wowlheim/Knowledge.h"
#include "Wowlheim/BuildingMgr.h"

#include "Chat/Chat.h"
#include "Database/DatabaseEnv.h"
#include "Entities/Bag.h"
#include "Entities/Item.h"
#include "Entities/Player.h"
#include "Globals/ObjectAccessor.h"
#include "Globals/ObjectMgr.h"
#include "Maps/Map.h"
#include "Server/WorldSession.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>

namespace
{
    void Api(ChatHandler* h, std::string const& body)
    {
        h->SendSysMessage(("[WL]" + body).c_str());
    }

    void ApiTo(Player* player, std::string const& body)
    {
        ChatHandler h(player->GetSession());
        Api(&h, body);
    }

    // Liste « a,b,c » découpée en lignes « <préfixe><liste> » d'au plus ~200 caractères (limite d'un message de chat)
    void ApiList(ChatHandler* h, std::string const& prefix, std::vector<std::string> const& elems)
    {
        std::string line;
        for (std::string const& e : elems)
        {
            if (!line.empty() && line.size() + e.size() + 1 > 200)
            {
                Api(h, prefix + line);
                line.clear();
            }
            if (!line.empty())
                line += ",";
            line += e;
        }
        Api(h, prefix + line);          // toujours au moins une ligne (éventuellement vide)
    }

    // Équipement, sac à dos et sacs (pos = (sac << 8) | emplacement, comme Player::GetItemByPos(uint16))
    template <class F>
    void ForEachItem(Player* p, F f)
    {
        for (uint8 s = EQUIPMENT_SLOT_START; s < INVENTORY_SLOT_ITEM_END; ++s)
            if (Item* it = p->GetItemByPos(INVENTORY_SLOT_BAG_0, s))
                f(it, uint16((INVENTORY_SLOT_BAG_0 << 8) | s));
        for (uint8 b = INVENTORY_SLOT_BAG_START; b < INVENTORY_SLOT_BAG_END; ++b)
        {
            Item* bi = p->GetItemByPos(INVENTORY_SLOT_BAG_0, b);
            if (!bi || !bi->IsBag())
                continue;
            Bag* bag = static_cast<Bag*>(bi);
            for (uint32 j = 0; j < bag->GetBagSize(); ++j)
                if (Item* it = bag->GetItemByPos(uint8(j)))
                    f(it, uint16((b << 8) | j));
        }
    }

    std::string ItemName(uint32 id)
    {
        ItemPrototype const* p = ObjectMgr::GetItemPrototype(id);
        return p && p->Name1 ? p->Name1 : ("objet " + std::to_string(id));
    }

    // Stations de fabrication (CraftingStation de Valheim) : types exigés par une pièce ou une recette, plus les 4 connues.
    // Les fonderies / fours / rouet sont des Smelter, pas des CraftingStation : exclus.
    std::set<std::string> const& CraftingKinds()
    {
        static std::set<std::string> kinds;
        static size_t seenTpl = size_t(-1), seenRc = size_t(-1);
        if (seenTpl != sBuildingMgr.Templates().size() || seenRc != sBuildingMgr.Recipes().size())
        {
            kinds = { "workbench", "forge", "stonecutter", "artisan" };
            for (auto const& kv : sBuildingMgr.Templates())
                if (!kv.second.station.empty())
                    kinds.insert(kv.second.station);
            for (auto const& kv : sBuildingMgr.Recipes())
                if (!kv.second.station.empty() && kv.second.station != "charcoal_kiln")
                    kinds.insert(kv.second.station);
            seenTpl = sBuildingMgr.Templates().size();
            seenRc = sBuildingMgr.Recipes().size();
        }
        return kinds;
    }

    bool InDiscoverRange(Player* player, WLPiece const& p, WLPieceTemplate const& t)
    {
        // Valheim : Vector3.Distance(joueur, station) < m_discoverRange (4 m). Adaptation : distance horizontale au BORD de
        // l'emprise (comme FindStationInRange) car la collision WoW tient le joueur à l'extérieur de la boîte des stations.
        if (p.map != player->GetMapId())
            return false;
        float dz = std::fabs(player->GetPositionZ() - (p.z + 0.5f * t.sz));
        if (dz > KnowledgeMgr::DISCOVER_RANGE + 0.5f * t.sz)
            return false;
        return sBuildingMgr.DistToPiece2D(p, player->GetPositionX(), player->GetPositionY()) < KnowledgeMgr::DISCOVER_RANGE;
    }
}

KnowledgeMgr& KnowledgeMgr::Instance()
{
    static KnowledgeMgr instance;
    return instance;
}

bool KnowledgeMgr::IsCraftingStationKind(std::string const& kind) const
{
    return CraftingKinds().count(kind) != 0;
}

KnowledgeMgr::Known& KnowledgeMgr::Get(uint32 playerGuid)
{
    Known& k = m_players[playerGuid];
    if (!k.loaded)
    {
        k.loaded = true;
        if (auto r = CharacterDatabase.PQuery("SELECT item FROM wowlheim_known_item WHERE guid = %u", playerGuid))
        {
            do { k.items.insert(r->Fetch()[0].GetUInt32()); } while (r->NextRow());
        }
        if (auto r = CharacterDatabase.PQuery("SELECT kind, level FROM wowlheim_known_station WHERE guid = %u", playerGuid))
        {
            do
            {
                Field* f = r->Fetch();
                k.stations[f[0].GetCppString()] = std::max<uint32>(1, f[1].GetUInt32());
            } while (r->NextRow());
        }
    }
    return k;
}

bool KnowledgeMgr::LearnItem(Player* player, Known& k, uint32 itemId)
{
    if (itemId < ITEM_MIN || itemId > ITEM_MAX || !k.items.insert(itemId).second)
        return false;
    uint32 guid = player->GetObjectGuid().GetCounter();
    CharacterDatabase.PExecute("INSERT IGNORE INTO wowlheim_known_item (guid, item) VALUES (%u, %u)", guid, itemId);
    // Valheim : MessageHud.QueueUnlockMsg($msg_newmaterial / $msg_newitem) ; l'addon affiche la nouveauté et rafraîchit ses menus
    ApiTo(player, "KN|item|" + std::to_string(itemId));
    return true;
}

bool KnowledgeMgr::LearnStationLevel(Player* player, Known& k, std::string const& kind, uint32 level)
{
    level = std::max<uint32>(1, level);
    auto it = k.stations.find(kind);
    if (it != k.stations.end() && it->second >= level)        // Player.AddKnownStation : mise à jour seulement si niveau supérieur
        return false;
    k.stations[kind] = level;
    uint32 guid = player->GetObjectGuid().GetCounter();
    CharacterDatabase.PExecute("INSERT INTO wowlheim_known_station (guid, kind, level) VALUES (%u, '%s', %u) ON DUPLICATE KEY UPDATE level = GREATEST(level, VALUES(level))",
                               guid, kind.c_str(), level);
    ApiTo(player, "KN|station|" + kind + "|" + std::to_string(level));
    return true;
}

uint32 KnowledgeMgr::ScanInventory(Player* player)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    Known& k = Get(player->GetObjectGuid().GetCounter());
    uint32 learned = 0;
    ForEachItem(player, [&](Item* it, uint16) { if (LearnItem(player, k, it->GetEntry())) ++learned; });
    return learned;
}

void KnowledgeMgr::LearnStation(Player* player, WLPiece const& station)
{
    WLPieceTemplate const* t = sBuildingMgr.FindTemplate(station.pieceId);
    if (!t || !IsCraftingStationKind(t->kind))
        return;
    std::lock_guard<std::recursive_mutex> g(m_lock);
    LearnStationLevel(player, Get(player->GetObjectGuid().GetCounter()), t->kind, sBuildingMgr.StationLevel(station));
}

uint32 KnowledgeMgr::DiscoverStations(Player* player)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    Known& k = Get(player->GetObjectGuid().GetCounter());
    uint32 n = 0;
    for (auto const& kv : sBuildingMgr.Pieces())
    {
        WLPiece const& p = kv.second;
        if (p.map != player->GetMapId())
            continue;
        WLPieceTemplate const* t = sBuildingMgr.FindTemplate(p.pieceId);
        if (!t || !IsCraftingStationKind(t->kind) || !InDiscoverRange(player, p, *t))
            continue;
        if (LearnStationLevel(player, k, t->kind, sBuildingMgr.StationLevel(p)))
            ++n;
    }
    return n;
}

void KnowledgeMgr::Update(uint32 diffMs)
{
    m_timer += diffMs;
    if (m_timer < 1000)                         // Player.UpdateStations : m_stationDiscoverTimer > 1 s
        return;
    m_timer = 0;

    // Appelé depuis World::Update avant sMapMgr.Update : aucune carte ne tourne en parallèle.
    std::vector<Player*> players;
    {
        std::lock_guard<std::mutex> lg(HashMapHolder<Player>::GetLock());
        for (auto const& kv : sObjectAccessor.GetPlayers())
            if (kv.second && kv.second->IsInWorld() && kv.second->GetSession())
                players.push_back(kv.second);
    }
    // stations posées (une fois par tick)
    std::vector<std::pair<WLPiece const*, WLPieceTemplate const*>> stations;
    for (auto const& kv : sBuildingMgr.Pieces())
    {
        WLPieceTemplate const* t = sBuildingMgr.FindTemplate(kv.second.pieceId);
        if (t && IsCraftingStationKind(t->kind))
            stations.push_back({ &kv.second, t });
    }
    std::lock_guard<std::recursive_mutex> g(m_lock);
    for (Player* player : players)
    {
        // Valheim : Player.OnInventoryChanged -> AddKnownItem pour chaque objet du sac (ici : balayage chaque seconde)
        ScanInventory(player);
        if (stations.empty())
            continue;
        Known& k = Get(player->GetObjectGuid().GetCounter());
        for (auto const& st : stations)
            if (InDiscoverRange(player, *st.first, *st.second))
                LearnStationLevel(player, k, st.second->kind, sBuildingMgr.StationLevel(*st.first));
    }
}

// Player.HaveRequirements(Piece, RequirementMode.IsKnown) : station de la pièce connue (m_knownStations.ContainsKey)
// ET chaque ressource (m_amount > 0) dans m_knownMaterial.
bool KnowledgeMgr::PieceKnown(Player* player, WLPieceTemplate const& tpl)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    Known& k = Get(player->GetObjectGuid().GetCounter());
    if (!tpl.station.empty() && !k.stations.count(tpl.station))
        return false;
    for (WLItemCount const& c : tpl.costs)
        if (c.count > 0 && !k.items.count(c.itemId))
            return false;
    return true;
}

// Player.HaveRequirements(Recipe, discover=true) : KnowStationLevel(station, m_minStationLevel) puis
// HaveRequirementItems(discover=true) : chaque ingrédient (m_amount > 0) dans m_knownMaterial.
bool KnowledgeMgr::RecipeKnown(Player* player, WLRecipe const& r)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    Known& k = Get(player->GetObjectGuid().GetCounter());
    if (!r.station.empty())
    {
        auto it = k.stations.find(r.station);
        if (it == k.stations.end() || it->second < r.minStationLevel)
            return false;
    }
    for (WLItemCount const& c : r.ingredients)
        if (c.count > 0 && !k.items.count(c.itemId))
            return false;
    return true;
}

void KnowledgeMgr::SendKnown(ChatHandler* h, Player* player)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    ScanInventory(player);                      // le sac actuel compte tout de suite (pas d'attente du balayage)
    DiscoverStations(player);
    Known& k = Get(player->GetObjectGuid().GetCounter());
    std::vector<std::string> items, stations, pieces, recipes;
    for (uint32 id : k.items)
        items.push_back(std::to_string(id));
    for (auto const& kv : k.stations)
        stations.push_back(kv.first + ":" + std::to_string(kv.second));
    // Player.UpdateAvailablePiecesList : m_noPlacementCost -> toutes les pièces sont proposées
    bool all = sBuildingMgr.IsNoCost(player->GetObjectGuid().GetCounter());
    for (auto const& kv : sBuildingMgr.Templates())
        if (all || PieceKnown(player, kv.second))
            pieces.push_back(std::to_string(kv.first));
    for (auto const& kv : sBuildingMgr.Recipes())
        if (RecipeKnown(player, kv.second))
            recipes.push_back(std::to_string(kv.first));
    ApiList(h, "K|item:", items);
    ApiList(h, "KS|", stations);
    ApiList(h, "KP|", pieces);
    ApiList(h, "KR|", recipes);
}

bool Wowlheim_KnownCommand(ChatHandler* h, Player* player)
{
    if (!player)
        return false;
    sKnowledgeMgr.SendKnown(h, player);
    return true;
}

void Wowlheim_SendStationLines(ChatHandler* h, Player* player)
{
    static char const* const kinds[] = { "workbench", "forge", "stonecutter", "artisan" };
    for (char const* kind : kinds)
    {
        WLPiece const* st = sBuildingMgr.FindStationInRange(player->GetMap(), player->GetPositionX(), player->GetPositionY(), kind, BuildingMgr::STATION_RANGE);
        if (!st)
            continue;
        float pct = 0.0f;
        bool usable = sBuildingMgr.StationUsable(*st, pct);
        Api(h, "S|" + std::to_string(st->guid) + "|" + (usable ? "1" : "0") + "|" + std::to_string(int(pct * 100.0f)) + "|" +
               std::to_string(sBuildingMgr.StationLevel(*st)) + "|" + kind);
    }
}

// ---------------------------------------------------------------------------------------------------------------------
// Réparation à la station (InventoryGui.CanRepair / RepairOneItem, docs/VALHEIM_RULES.md §11)
namespace
{
    // Station de réparation : celle donnée (guid) si à portée, sinon la station de fabrication la plus proche (20 m)
    WLPiece const* RepairStation(Player* player, char* args, std::string& err)
    {
        uint32 wanted = 0;
        if (args && *args)
            wanted = uint32(std::strtoul(args, nullptr, 10));
        WLPiece const* best = nullptr;
        float bestD = BuildingMgr::STATION_RANGE;
        for (auto const& kv : sBuildingMgr.Pieces())
        {
            WLPiece const& p = kv.second;
            if (p.map != player->GetMapId() || (wanted && p.guid != wanted))
                continue;
            WLPieceTemplate const* t = sBuildingMgr.FindTemplate(p.pieceId);
            if (!t || !sKnowledgeMgr.IsCraftingStationKind(t->kind))
                continue;
            float d = sBuildingMgr.DistToPiece2D(p, player->GetPositionX(), player->GetPositionY());
            if (d < bestD)
            {
                bestD = d;
                best = &p;
            }
        }
        if (!best)
            err = wanted ? "station introuvable ou à plus de 20 m" : "aucune station de fabrication à moins de 20 m";
        return best;
    }

    WLRecipe const* RecipeFor(uint32 itemId)
    {
        for (auto const& kv : sBuildingMgr.Recipes())           // ObjectDB.GetRecipe : première recette produisant l'objet
            if (kv.second.outputItem == itemId)
                return &kv.second;
        return nullptr;
    }

    // InventoryGui.CanRepair(item) pour la station `kind` de niveau `level` (station nulle : seulement avec NoCostCheat)
    bool CanRepair(Item* it, std::string const& kind, uint32 level, bool noCost)
    {
        uint32 entry = it->GetEntry();
        if (entry < KnowledgeMgr::ITEM_MIN || entry > KnowledgeMgr::ITEM_MAX || !it->GetUInt32Value(ITEM_FIELD_MAXDURABILITY))
            return false;                                        // SharedData.m_canBeReparied : objets Wowlheim à durabilité
        if (noCost)                                              // Player.NoCostCheat() -> true
            return true;
        WLRecipe const* r = RecipeFor(entry);
        if (!r || kind.empty())
            return false;
        // m_repairStation (ou, à défaut d'égalité, m_craftingStation) du nom de la station courante. La base n'a pas de colonne
        // repair_station : les recettes sans station (Marteau, Hache en pierre, Massue) ont m_repairStation = piece_workbench.
        bool stationOk = (r->station == kind) || (r->station.empty() && kind == "workbench");
        if (!stationOk)
            return false;
        return std::min<uint32>(level, 4) >= r->minStationLevel;   // Mathf.Min(GetLevel(), 4) >= m_minStationLevel
    }

    bool Worn(Item* it)                                          // Inventory.GetWornItems : durabilité < max
    {
        uint32 maxD = it->GetUInt32Value(ITEM_FIELD_MAXDURABILITY);
        return maxD && it->GetUInt32Value(ITEM_FIELD_DURABILITY) < maxD;
    }

    struct RepairCtx
    {
        WLPiece const* st = nullptr;
        std::string kind;
        uint32 level = 0;
        bool noCost = false;
    };

    bool PrepareRepair(ChatHandler* h, Player* player, char* args, RepairCtx& c)
    {
        c.noCost = sBuildingMgr.IsNoCost(player->GetObjectGuid().GetCounter());
        std::string err;
        c.st = RepairStation(player, args, err);
        if (!c.st)
        {
            if (c.noCost)                                        // RepairOneItem : sans station, seulement avec NoCostCheat
                return true;
            Api(h, "E|Réparation impossible : " + err + ".");
            return false;
        }
        WLPieceTemplate const* t = sBuildingMgr.FindTemplate(c.st->pieceId);
        c.kind = t ? t->kind : "";
        c.level = sBuildingMgr.StationLevel(*c.st);
        float pct = 0.0f;
        if (!sBuildingMgr.StationUsable(*c.st, pct))             // CraftingStation.CheckUsable(player, false)
        {
            char buf[160];
            snprintf(buf, sizeof(buf), "E|Station exposée (couverture %.0f %%, il faut un toit et au moins 70 %%).", pct * 100.0f);
            Api(h, buf);
            return false;
        }
        sKnowledgeMgr.LearnStation(player, *c.st);
        return true;
    }
}

// .build api repairable [guid_station] : RS|guid|kind|niveau puis RI|objet|durabilité|max par objet usé réparable ici
bool Wowlheim_RepairableCommand(ChatHandler* h, Player* player, char* args)
{
    if (!player)
        return false;
    RepairCtx c;
    if (!PrepareRepair(h, player, args, c))
        return false;
    Api(h, "RS|" + std::to_string(c.st ? c.st->guid : 0) + "|" + c.kind + "|" + std::to_string(c.level));
    ForEachItem(player, [&](Item* it, uint16)
    {
        if (Worn(it) && CanRepair(it, c.kind, c.level, c.noCost))
            Api(h, "RI|" + std::to_string(it->GetEntry()) + "|" + std::to_string(it->GetUInt32Value(ITEM_FIELD_DURABILITY)) + "|" +
                   std::to_string(it->GetUInt32Value(ITEM_FIELD_MAXDURABILITY)));
    });
    return true;
}

// .build api wear <objet> <durabilité> (MJ, tests) : fixe la durabilité des exemplaires portés de cet objet, en jeu
// (écrire item_instance hors connexion ne suffit pas : le personnage reste en mémoire après la déconnexion)
bool Wowlheim_WearCommand(ChatHandler* h, Player* player, char* args)
{
    if (!player || player->GetSession()->GetSecurity() < SEC_GAMEMASTER || !args)
        return false;
    uint32 entry = 0, dur = 0;
    if (sscanf(args, "%u %u", &entry, &dur) != 2)
    {
        Api(h, "E|usage : wear <objet> <durabilité>");
        return false;
    }
    uint32 n = 0;
    ForEachItem(player, [&](Item* it, uint16)
    {
        uint32 maxD = it->GetUInt32Value(ITEM_FIELD_MAXDURABILITY);
        if (it->GetEntry() != entry || !maxD)
            return;
        it->SetUInt32Value(ITEM_FIELD_DURABILITY, std::min(dur, maxD));
        it->SetState(ITEM_CHANGED, player);
        ++n;
    });
    Api(h, "M|" + std::to_string(n) + " objet(s) usé(s).");
    return n > 0;
}

// .build api repairitems [guid_station] : répare (gratuitement, durabilité au maximum) tous les objets usés réparables
// à cette station ; R|objet,objet,... (Valheim répare un objet par clic : RepairOneItem ; ici tous en une fois)
bool Wowlheim_RepairItemsCommand(ChatHandler* h, Player* player, char* args)
{
    if (!player)
        return false;
    RepairCtx c;
    if (!PrepareRepair(h, player, args, c))
        return false;
    std::vector<uint16> todo;
    std::vector<std::string> ids;
    std::string names;
    ForEachItem(player, [&](Item* it, uint16 pos)
    {
        if (Worn(it) && CanRepair(it, c.kind, c.level, c.noCost))
        {
            todo.push_back(pos);
            ids.push_back(std::to_string(it->GetEntry()));
            names += (names.empty() ? "" : ", ") + ItemName(it->GetEntry());
        }
    });
    for (uint16 pos : todo)
        player->DurabilityRepair(pos, false, 1.0f);              // sans coût (Valheim : réparation gratuite)
    std::string line = "R|";
    for (size_t i = 0; i < ids.size(); ++i)
        line += (i ? "," : "") + ids[i];
    Api(h, line);
    Api(h, "M|" + (todo.empty() ? std::string("Aucun objet à réparer.") : "Réparé : " + names + "."));   // $msg_repaired
    return true;
}
