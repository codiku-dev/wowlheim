#include "Wowlheim/BuildingMgr.h"
#include "Wowlheim/TreeMgr.h"
#include "Wowlheim/Smelter.h"
#include "Wowlheim/Pieces.h"

#include "Database/DatabaseEnv.h"
#include "Entities/GameObject.h"
#include "Entities/Item.h"
#include "Entities/Player.h"
#include "Globals/ObjectAccessor.h"
#include "Globals/ObjectMgr.h"
#include "Log/Log.h"
#include "Mails/Mail.h"
#include "Maps/Map.h"
#include "Server/DBCStores.h"
#include "Server/DBCEnums.h"

#include <algorithm>

BuildingMgr& BuildingMgr::Instance()
{
    static BuildingMgr instance;
    return instance;
}

void BuildingMgr::Load()
{
    m_templates.clear();
    m_pieces.clear();
    m_recipes.clear();
    m_forbiddenAreas.clear();
    m_noBuild.clear();
    m_tools.clear();
    m_nodes.clear();

    auto tplResult = WorldDatabase.Query("SELECT id, name, gameobject_entry, material, max_health, supports, requires_workbench, kind, sx, sy, sz, ext_station, ext_distance, ext_stack, prefab, category, station FROM wowlheim_piece_template");
    if (!tplResult)
    {
        sLog.outString(">> Wowlheim: table wowlheim_piece_template absente ou vide, construction désactivée");
        return;
    }
    do
    {
        Field* f = tplResult->Fetch();
        WLPieceTemplate t;
        t.id = f[0].GetUInt32();
        t.name = f[1].GetCppString();
        t.goEntry = f[2].GetUInt32();
        t.material = uint8(f[3].GetUInt32());
        t.maxHealth = f[4].GetUInt32();
        t.supports = f[5].GetUInt32() != 0;
        t.requiresWorkbench = f[6].GetUInt32() != 0;
        t.kind = f[7].GetCppString();
        t.sx = f[8].GetFloat();
        t.sy = f[9].GetFloat();
        t.sz = f[10].GetFloat();
        t.extStation = f[11].GetCppString();
        t.extDistance = f[12].GetFloat();
        t.extStack = f[13].GetUInt32() != 0;
        t.prefab = f[14].GetCppString();
        t.category = f[15].GetUInt32();
        t.station = f[16].GetCppString();
        if (!ObjectMgr::GetGameObjectInfo(t.goEntry))
        {
            sLog.outErrorDb("Wowlheim: pièce %u (%s) référence un gameobject_template %u inexistant, ignorée", t.id, t.name.c_str(), t.goEntry);
            continue;
        }
        m_templates[t.id] = t;
    } while (tplResult->NextRow());

    if (auto r = WorldDatabase.Query("SELECT piece_id, item_id, `count` FROM wowlheim_piece_cost"))
    {
        do
        {
            Field* f = r->Fetch();
            auto it = m_templates.find(f[0].GetUInt32());
            if (it == m_templates.end())
                continue;
            it->second.costs.push_back(WLItemCount{ f[1].GetUInt32(), f[2].GetUInt32() });
        } while (r->NextRow());
    }

    if (auto r = WorldDatabase.Query("SELECT piece_id, x, y, z FROM wowlheim_piece_snap ORDER BY piece_id, idx"))
    {
        do
        {
            Field* f = r->Fetch();
            auto it = m_templates.find(f[0].GetUInt32());
            if (it != m_templates.end())
                it->second.snaps.push_back(WLPieceTemplate::Snap{ f[1].GetFloat(), f[2].GetFloat(), f[3].GetFloat() });
        } while (r->NextRow());
    }

    if (auto r = WorldDatabase.Query("SELECT id, name, station, output_item, output_count, min_station_level FROM wowlheim_recipe"))
    {
        do
        {
            Field* f = r->Fetch();
            WLRecipe rc;
            rc.id = f[0].GetUInt32();
            rc.name = f[1].GetCppString();
            rc.station = f[2].GetCppString();
            rc.outputItem = f[3].GetUInt32();
            rc.outputCount = f[4].GetUInt32();
            rc.minStationLevel = std::max<uint32>(1, f[5].GetUInt32());
            m_recipes[rc.id] = rc;
        } while (r->NextRow());
    }
    if (auto r = WorldDatabase.Query("SELECT recipe_id, item_id, `count` FROM wowlheim_recipe_ingredient"))
    {
        do
        {
            Field* f = r->Fetch();
            auto it = m_recipes.find(f[0].GetUInt32());
            if (it != m_recipes.end())
                it->second.ingredients.push_back(WLItemCount{ f[1].GetUInt32(), f[2].GetUInt32() });
        } while (r->NextRow());
    }
    if (auto r = WorldDatabase.Query("SELECT area_id FROM wowlheim_forbidden_area"))
    {
        do { m_forbiddenAreas.insert((*r).Fetch()[0].GetUInt32()); } while (r->NextRow());
    }
    if (auto r = WorldDatabase.Query("SELECT map, x, y, radius, name FROM wowlheim_no_build_point"))
    {
        do
        {
            Field* f = r->Fetch();
            m_noBuild.push_back(NoBuildPoint{ f[0].GetUInt32(), f[1].GetFloat(), f[2].GetFloat(), f[3].GetFloat(), f[4].GetCppString() });
        } while (r->NextRow());
    }
    if (auto r = WorldDatabase.Query("SELECT item_id, kind, tier, damage FROM wowlheim_tool"))
    {
        do
        {
            Field* f = r->Fetch();
            m_tools[f[0].GetUInt32()] = Tool{ f[1].GetCppString(), uint8(f[2].GetUInt32()), f[3].GetFloat() };
        } while (r->NextRow());
    }
    if (auto r = WorldDatabase.Query("SELECT gameobject_entry, tool_kind, min_tier FROM wowlheim_node"))
    {
        do
        {
            Field* f = r->Fetch();
            m_nodes[f[0].GetUInt32()] = Node{ f[1].GetCppString(), uint8(f[2].GetUInt32()) };
        } while (r->NextRow());
    }
    sLog.outString(">> Wowlheim: %u modèles de pièces, %u recettes, %u outils, %u nœuds, %u zones interdites, %u points d'exclusion",
                   uint32(m_templates.size()), uint32(m_recipes.size()), uint32(m_tools.size()), uint32(m_nodes.size()), uint32(m_forbiddenAreas.size()), uint32(m_noBuild.size()));

    auto pieceResult = CharacterDatabase.Query("SELECT guid, piece_id, owner_guid, map, x, y, z, o, health FROM wowlheim_piece");
    if (pieceResult)
    {
        do
        {
            Field* f = pieceResult->Fetch();
            WLPiece p;
            p.guid = f[0].GetUInt32();
            p.pieceId = f[1].GetUInt32();
            p.ownerGuid = f[2].GetUInt32();
            p.map = f[3].GetUInt32();
            p.x = f[4].GetFloat();
            p.y = f[5].GetFloat();
            p.z = f[6].GetFloat();
            p.o = f[7].GetFloat();
            p.health = f[8].GetUInt32();
            m_pieces[p.guid] = p;
        } while (pieceResult->NextRow());
    }
    sLog.outString(">> Wowlheim: %u pièces posées chargées", uint32(m_pieces.size()));
    sTreeMgr.Load();
    sSmelterMgr.Load();
    Wowlheim_PieceUseLoad();           // coffres, portes, lits (Pieces.cpp) : contenu et états des pièces posées
    m_dirty = !m_pieces.empty();       // première évaluation de structure au démarrage
}

WLPieceTemplate const* BuildingMgr::FindTemplate(uint32 id) const
{
    auto it = m_templates.find(id);
    return it == m_templates.end() ? nullptr : &it->second;
}

namespace
{
    bool IEquals(std::string const& a, std::string const& b)
    {
        if (a.size() != b.size())
            return false;
        for (size_t i = 0; i < a.size(); ++i)
            if (tolower(static_cast<unsigned char>(a[i])) != tolower(static_cast<unsigned char>(b[i])))
                return false;
        return true;
    }
}

WLPieceTemplate const* BuildingMgr::FindTemplateByName(std::string const& name) const
{
    // anciens noms courts (commandes et tests d'avant le catalogue Valheim) -> id de pièce conservé
    static std::map<std::string, uint32> const aliases = {
        { "plancher", 1 }, { "mur", 2 }, { "toit", 3 }, { "poteau", 4 }, { "feu", 5 }, { "établi", 6 }, { "forge", 7 },
        { "billot", 8 }, { "étendoir", 9 }, { "soufflet", 10 }, { "enclume", 11 }, { "étau", 12 } };
    std::string low;
    for (char c : name)
        low += char(tolower(static_cast<unsigned char>(c)));
    auto al = aliases.find(low);
    if (al == aliases.end() && name == "Établi")
        al = aliases.find("établi");
    if (al == aliases.end() && name == "Étau")
        al = aliases.find("étau");
    if (al != aliases.end())
        return FindTemplate(al->second);
    for (auto const& kv : m_templates)
        if (IEquals(kv.second.name, name) || IEquals(kv.second.prefab, name) || IEquals(kv.second.kind, name))
            return &kv.second;
    return nullptr;
}

WLRecipe const* BuildingMgr::FindRecipe(std::string const& token) const
{
    char* end = nullptr;
    unsigned long id = strtoul(token.c_str(), &end, 10);
    if (end && *end == '\0')
    {
        auto it = m_recipes.find(uint32(id));
        return it == m_recipes.end() ? nullptr : &it->second;
    }
    for (auto const& kv : m_recipes)
        if (IEquals(kv.second.name, token))
            return &kv.second;
    return nullptr;
}

void BuildingMgr::RecordDiff(uint32 diff)
{
    m_diffs.push_back(diff);
    if (m_diffs.size() > 600)
        m_diffs.pop_front();
}

uint32 BuildingMgr::AverageDiff() const
{
    if (m_diffs.empty())
        return 0;
    uint64 sum = 0;
    for (uint32 d : m_diffs)
        sum += d;
    return uint32(sum / m_diffs.size());
}

uint32 BuildingMgr::MaxDiff() const
{
    uint32 m = 0;
    for (uint32 d : m_diffs)
        if (d > m)
            m = d;
    return m;
}

uint32 BuildingMgr::CountByOwner(uint32 ownerGuid) const
{
    uint32 n = 0;
    for (auto const& kv : m_pieces)
        if (kv.second.ownerGuid == ownerGuid)
            ++n;
    return n;
}

bool BuildingMgr::Repair(uint32 guid, std::string& err)
{
    auto it = m_pieces.find(guid);
    if (it == m_pieces.end())
    {
        err = "pièce inconnue";
        return false;
    }
    WLPieceTemplate const* t = FindTemplate(it->second.pieceId);
    if (!t)
    {
        err = "modèle inconnu";
        return false;
    }
    if (it->second.health >= t->maxHealth)
    {
        err = "la pièce est déjà en parfait état";
        return false;
    }
    it->second.health = t->maxHealth;
    CharacterDatabase.PExecute("UPDATE wowlheim_piece SET health = %u WHERE guid = %u", it->second.health, guid);
    return true;
}

// ---------------------------------------------------------------------------------------------------------------------
// Zones interdites : drapeaux de zone du client (capitales, villes, arènes) + table wowlheim_forbidden_area.
// Construction réservée aux continents (cartes 0 et 1) : jamais en instance ni en champ de bataille.
bool BuildingMgr::IsForbiddenArea(Map* map, float x, float y, float z, std::string& why) const
{
    if (map->GetId() != 0 && map->GetId() != 1)
    {
        why = "la construction n'est possible que sur les continents";
        return true;
    }
    for (NoBuildPoint const& np : m_noBuild)
    {
        if (np.map != map->GetId())
            continue;
        float dx = np.x - x, dy = np.y - y;
        if (dx * dx + dy * dy < np.radius * np.radius)
        {
            why = "construction interdite près d'un village (" + np.name + ")";
            return true;
        }
    }
    uint32 areaId = map->GetTerrain()->GetAreaId(x, y, z);
    constexpr uint32 cityFlags = AREA_FLAG_CAPITAL | AREA_FLAG_CITY | AREA_FLAG_SLAVE_CAPITAL | AREA_FLAG_SLAVE_CAPITAL2 | AREA_FLAG_ARENA;
    AreaTableEntry const* area = GetAreaEntryByAreaID(areaId);
    for (int depth = 0; area && depth < 3; ++depth)
    {
        if (area->flags & cityFlags)
        {
            why = "construction interdite en ville";
            return true;
        }
        if (m_forbiddenAreas.count(area->ID))
        {
            why = "construction interdite dans cette zone";
            return true;
        }
        area = area->zone ? GetAreaEntryByAreaID(area->zone) : nullptr;
    }
    return false;
}

// ---------------------------------------------------------------------------------------------------------------------
// Objets : coûts, consommation, remise
bool BuildingMgr::HasItems(Player* player, std::vector<WLItemCount> const& items, std::string& missing) const
{
    for (WLItemCount const& ic : items)
    {
        uint32 have = player->GetItemCount(ic.itemId);
        if (have >= ic.count)
            continue;
        ItemPrototype const* proto = ObjectMgr::GetItemPrototype(ic.itemId);
        missing = std::string(proto && proto->Name1 ? proto->Name1 : "objet inconnu") + " (" + std::to_string(have) + "/" + std::to_string(ic.count) + ")";
        return false;
    }
    return true;
}

void BuildingMgr::ConsumeItems(Player* player, std::vector<WLItemCount> const& items) const
{
    for (WLItemCount const& ic : items)
        player->DestroyItemCount(ic.itemId, ic.count, true);
}

uint32 BuildingMgr::GiveItems(Player* player, uint32 receiverGuid, std::vector<WLItemCount> const& items, std::string const& mailSubject) const
{
    uint32 mailed = 0;
    std::vector<WLItemCount> overflow;
    for (WLItemCount const& ic : items)
    {
        uint32 remaining = ic.count;
        if (player)
        {
            ItemPosCountVec dest;
            uint32 noSpace = 0;
            uint8 msg = player->CanStoreNewItem(NULL_BAG, NULL_SLOT, dest, ic.itemId, ic.count, &noSpace);
            uint32 storable = (msg == EQUIP_ERR_OK) ? ic.count : ic.count - noSpace;
            if (storable > 0 && !dest.empty())
            {
                if (Item* item = player->StoreNewItem(dest, ic.itemId, true, Item::GenerateItemRandomPropertyId(ic.itemId)))
                    player->SendNewItem(item, storable, true, false);
                remaining = ic.count - storable;
            }
        }
        if (remaining)
            overflow.push_back(WLItemCount{ ic.itemId, remaining });
    }

    if (overflow.empty())
        return 0;

    // courrier : au plus 12 pièces jointes par message ; piles limitées à la taille de pile de l'objet
    MailDraft* draft = nullptr;
    uint32 attached = 0;
    ObjectGuid receiver(HIGHGUID_PLAYER, receiverGuid);
    auto flush = [&]()
    {
        if (draft)
        {
            draft->SendMailTo(MailReceiver(ObjectAccessor::FindPlayer(receiver), receiver), MailSender(MailMessageType(MAIL_NORMAL), uint32(0)));
            delete draft;
            draft = nullptr;
            attached = 0;
        }
    };
    for (WLItemCount const& ic : overflow)
    {
        ItemPrototype const* proto = ObjectMgr::GetItemPrototype(ic.itemId);
        uint32 stack = proto && proto->Stackable ? proto->Stackable : 1;
        uint32 left = ic.count;
        while (left)
        {
            if (!draft)
                draft = new MailDraft(mailSubject, std::string("Ressources Wowlheim."));
            uint32 n = std::min(left, stack);
            if (Item* item = Item::CreateItem(ic.itemId, n, nullptr))
            {
                item->SaveToDB();
                draft->AddItem(item);
                ++attached;
                mailed += n;
            }
            left -= n;
            if (attached >= 12)
                flush();
        }
    }
    flush();
    return mailed;
}

// ---------------------------------------------------------------------------------------------------------------------
// Contrôles de Place sans rien créer (plafonds, emplacement occupé, gameobject_template) : partagés avec `.build api canplace`
bool BuildingMgr::CanPlaceAt(Map* map, WLPieceTemplate const& tpl, uint32 ownerGuid, float x, float y, float z, std::string& err) const
{
    if (!map)
    {
        err = "carte indisponible";
        return false;
    }
    if (m_pieces.size() >= MAX_PIECES_TOTAL)
    {
        err = "plafond global de pièces atteint";
        return false;
    }
    if (CountByOwner(ownerGuid) >= MAX_PIECES_PER_OWNER)
    {
        err = "plafond de pièces par joueur atteint";
        return false;
    }

    // Emplacement occupé : refuse une pièce de même modèle à moins de MIN_SEPARATION d'une pièce existante
    // (équivalent de Player.IsOverlappingOtherPiece, docs/VALHEIM_RULES.md 3.2 point 11 : même nom à moins de 0,05 m).
    for (auto const& kv : m_pieces)
    {
        WLPiece const& q = kv.second;
        if (q.map != map->GetId() || q.pieceId != tpl.id)
            continue;
        float dx = q.x - x, dy = q.y - y, dz = q.z - z;
        if (dx * dx + dy * dy + dz * dz < MIN_SEPARATION * MIN_SEPARATION)
        {
            err = "emplacement déjà occupé par une pièce identique";
            return false;
        }
    }

    if (!ObjectMgr::GetGameObjectInfo(tpl.goEntry))
    {
        err = "gameobject_template inconnu";
        return false;
    }
    return true;
}

uint32 BuildingMgr::Place(Map* map, WLPieceTemplate const& tpl, uint32 ownerGuid, float x, float y, float z, float o, std::string& err)
{
    if (!CanPlaceAt(map, tpl, ownerGuid, x, y, z, err))
        return 0;
    GameObjectInfo const* info = ObjectMgr::GetGameObjectInfo(tpl.goEntry);

    uint32 lowGuid = sObjectMgr.GenerateStaticGameObjectLowGuid();
    if (!lowGuid)
    {
        err = "plus de guid statique libre";
        return 0;
    }

    GameObject* go = GameObject::CreateGameObject(info->id);
    if (!go->Create(lowGuid, lowGuid, info->id, map, x, y, z, o))
    {
        delete go;
        err = "création du GameObject refusée";
        return 0;
    }

    go->SaveToDB(map->GetId());
    if (!go->LoadFromDB(lowGuid, map, lowGuid, 0))
    {
        delete go;
        err = "chargement du GameObject refusé";
        return 0;
    }
    sObjectMgr.AddGameobjectToGrid(lowGuid, sObjectMgr.GetGOData(lowGuid));

    WLPiece p;
    p.guid = lowGuid;
    p.pieceId = tpl.id;
    p.ownerGuid = ownerGuid;
    p.map = map->GetId();
    p.x = x; p.y = y; p.z = z; p.o = o;
    p.health = tpl.maxHealth;
    p.age = 0.0f;
    m_pieces[lowGuid] = p;

    m_dirty = true;
    CharacterDatabase.PExecute("INSERT INTO wowlheim_piece (guid, piece_id, owner_guid, map, x, y, z, o, health, placed_at) VALUES (%u, %u, %u, %u, %f, %f, %f, %f, %u, NOW())",
                               lowGuid, tpl.id, ownerGuid, p.map, x, y, z, o, p.health);
    return lowGuid;
}

bool BuildingMgr::Remove(uint32 guid, Map* map, std::string& err, bool refundByMail, Player* refundTo)
{
    auto it = m_pieces.find(guid);
    if (it == m_pieces.end())
    {
        err = "pièce inconnue";
        return false;
    }

    // Remboursement (docs/VALHEIM_RULES.md 4.2) : quantité complète de chaque ressource, indépendante de la santé.
    // Valheim fait tomber les objets au sol ; ici ils vont dans le sac du démolisseur ou, à défaut / en cas d'effondrement, par courrier.
    if (WLPieceTemplate const* tpl = FindTemplate(it->second.pieceId))
    {
        if ((refundTo || refundByMail) && !tpl->costs.empty())
            GiveItems(refundTo, it->second.ownerGuid, tpl->costs, "Pièce démolie");
    }

    // fonderie / four à charbon : contenu rendu (Smelter.DropAllItems), avant l'effacement de la pièce
    sSmelterMgr.OnPieceRemoved(guid, refundTo, it->second.ownerGuid);
    // coffre : contenu rendu (Container.OnDestroyed -> DropAllItems) ; porte / lit : état effacé (Pieces.cpp)
    Wowlheim_PieceUseRemoved(guid, refundTo, it->second.ownerGuid);

    sLog.outString("Wowlheim: démolition de la pièce %u", guid);
    GameObjectData const* data = sObjectMgr.GetGOData(guid);
    GameObject* obj = (data && map) ? map->GetGameObject(ObjectGuid(HIGHGUID_GAMEOBJECT, data->id, guid)) : nullptr;
    if (obj)
    {
        obj->SetRespawnTime(0);
        obj->Delete();
        obj->DeleteFromDB();
    }
    else if (data)
    {
        // objet non chargé (grille inactive) : suppression directe des données
        sObjectMgr.RemoveGameobjectFromGrid(guid, data);
        sObjectMgr.DeleteGOData(guid);
        WorldDatabase.PExecute("DELETE FROM gameobject WHERE guid = '%u'", guid);
    }

    CharacterDatabase.PExecute("DELETE FROM wowlheim_piece WHERE guid = %u", guid);
    m_pieces.erase(it);
    m_dirty = true;
    return true;
}

// ---------------------------------------------------------------------------------------------------------------------
// Récolte : un nœud demande l'outil équipé en main droite (jamais une arme WoW), du palier voulu.
bool BuildingMgr::CheckHarvest(Player* player, uint32 goEntry, std::string& err) const
{
    auto nit = m_nodes.find(goEntry);
    if (nit == m_nodes.end())
        return true;                                // pas un nœud Wowlheim
    Item* main = player->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_MAINHAND);
    if (main)
    {
        auto tit = m_tools.find(main->GetEntry());
        if (tit != m_tools.end() && tit->second.kind == nit->second.toolKind && tit->second.tier >= nit->second.minTier)
            return true;
    }
    err = nit->second.toolKind == "axe" ? "Il faut une hache de bûcheron équipée en main droite." : "Il faut un pic équipé en main droite.";
    if (nit->second.minTier > 1)
        err += " (palier " + std::to_string(nit->second.minTier) + " ou plus)";
    return false;
}

bool BuildingMgr::GetTool(uint32 itemId, std::string& kind, uint8& tier, float& damage) const
{
    auto it = m_tools.find(itemId);
    if (it == m_tools.end())
        return false;
    kind = it->second.kind;
    tier = it->second.tier;
    damage = it->second.damage;
    return true;
}

void BuildingMgr::ConsumeToolDurability(Player* player) const
{
    player->DurabilityPointLossForEquipSlot(EQUIPMENT_SLOT_MAINHAND);
}
