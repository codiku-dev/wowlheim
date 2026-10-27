// Commandes de construction Wowlheim : .build list|place|remove|count|support|station|recipes|craft|nocost|bulk|near|perf|rain|grace|dump|stats|api stations|api skills|api removeguid|api use|api models|api canplace|api pieceinfo
#include "Chat/Chat.h"
#include "Entities/GameObject.h"
#include "Entities/Item.h"
#include "Entities/Player.h"
#include "Globals/ObjectMgr.h"
#include "Grids/CellImpl.h"
#include "Grids/GridNotifiers.h"
#include "Grids/GridNotifiersImpl.h"
#include "Maps/Map.h"
#include "Server/WorldSession.h"
#include "Wowlheim/BuildingMgr.h"
#include "Wowlheim/TreeMgr.h"
#include "Wowlheim/Smelter.h"
#include "Wowlheim/Pieces.h"
#include "Wowlheim/Knowledge.h"
#include "Wowlheim/ValheimSkills.h"
#include "Entities/Creature.h"

#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cctype>
#include <cstdlib>

namespace
{
    // Mode API : les réponses sont préfixées « [WL]M| » (ou une ligne structurée « [WL]X|... ») pour que l'addon client
    // les intercepte et les masque dans le chat (tools/client/addon/Wowlheim). Hors mode API, comportement normal.
    bool g_api = false;

    void WLOut(ChatHandler* h, char const* fmt, ...)
    {
        char buf[1024];
        va_list ap;
        va_start(ap, fmt);
        vsnprintf(buf, sizeof(buf), fmt, ap);
        va_end(ap);
        if (g_api)
        {
            std::string line = std::string("[WL]M|") + buf;
            h->SendSysMessage(line.c_str());
        }
        else
            h->SendSysMessage(buf);
    }

    void WLRaw(ChatHandler* h, std::string const& body)           // ligne structurée en mode API uniquement
    {
        if (g_api)
        {
            std::string line = "[WL]" + body;
            h->SendSysMessage(line.c_str());
        }
    }
}

#define PSendSysMessage(...) WLOut(this, __VA_ARGS__)
#define WLSendText(x) WLOut(this, "%s", x)

namespace
{
    WLPieceTemplate const* ResolveTemplate(char* token)
    {
        if (!token)
            return nullptr;
        char* end = nullptr;
        unsigned long id = strtoul(token, &end, 10);
        if (end && *end == '\0')
            return sBuildingMgr.FindTemplate(uint32(id));
        return sBuildingMgr.FindTemplateByName(token);
    }

    std::string ItemName(uint32 id)
    {
        ItemPrototype const* p = ObjectMgr::GetItemPrototype(id);
        return p && p->Name1 ? p->Name1 : ("objet " + std::to_string(id));
    }

    std::string Describe(std::vector<WLItemCount> const& items)
    {
        std::string s;
        for (WLItemCount const& ic : items)
        {
            if (!s.empty())
                s += ", ";
            s += std::to_string(ic.count) + " " + ItemName(ic.itemId);
        }
        return s.empty() ? "gratuit" : s;
    }

    std::string CostsStr(std::vector<WLItemCount> const& items)
    {
        std::string out;
        for (WLItemCount const& ic : items)
        {
            if (!out.empty())
                out += ",";
            out += std::to_string(ic.itemId) + ":" + std::to_string(ic.count);
        }
        return out;
    }

    uint32 NearestPiece(Player* player, float maxDist)
    {
        uint32 bestGuid = 0;
        float bestDist = maxDist;
        for (auto const& kv : sBuildingMgr.Pieces())
        {
            WLPiece const& p = kv.second;
            if (p.map != player->GetMapId())
                continue;
            float dx = p.x - player->GetPositionX(), dy = p.y - player->GetPositionY(), dz = p.z - player->GetPositionZ();
            float d = std::sqrt(dx * dx + dy * dy + dz * dz);
            if (d < bestDist)
            {
                bestDist = d;
                bestGuid = p.guid;
            }
        }
        return bestGuid;
    }
}

bool ChatHandler::HandleBuildListCommand(char* /*args*/)
{
    if (g_api)
    {
        for (auto const& kv : sBuildingMgr.Templates())
        {
            WLPieceTemplate const& t = kv.second;
            WLRaw(this, "P|" + std::to_string(t.id) + "|" + t.name + "|" + t.kind + "|" + std::to_string(t.maxHealth) + "|" + (t.supports ? "1" : "0") + "|" +
                        (t.requiresWorkbench ? "1" : "0") + "|" + CostsStr(t.costs));
        }
        return true;
    }
    WLSendText("Pièces disponibles :");
    for (auto const& kv : sBuildingMgr.Templates())
    {
        WLPieceTemplate const& t = kv.second;
        PSendSysMessage("  %u  %s  [%s]  PV=%u  appui=%s%s  coût : %s", t.id, t.name.c_str(), t.kind.c_str(), t.maxHealth,
                        t.supports ? "oui" : "non", t.requiresWorkbench ? "  établi requis" : "", Describe(t.costs).c_str());
    }
    return true;
}

// .build place <pièce> [avant=3] [droite=0] [haut=0] [rotation°=0]  (mètres, relatifs au joueur)
bool ChatHandler::HandleBuildPlaceCommand(char* args)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    if (!player)
        return false;

    WLPieceTemplate const* tpl = ResolveTemplate(ExtractLiteralArg(&args));
    if (!tpl)
    {
        WLSendText("Pièce inconnue. Utilisez .build list");
        SetSentErrorMessage(true);
        return false;
    }

    float fwd, right, up, rot;
    if (!ExtractOptFloat(&args, fwd, 3.0f) || !ExtractOptFloat(&args, right, 0.0f) || !ExtractOptFloat(&args, up, 0.0f) || !ExtractOptFloat(&args, rot, 0.0f))
        return false;
    float facing = player->GetOrientation();
    float o = facing + rot * 3.14159265f / 180.0f;
    float x = player->GetPositionX() + fwd * std::cos(facing) - right * std::sin(facing);
    float y = player->GetPositionY() + fwd * std::sin(facing) + right * std::cos(facing);
    // accrochage (cahier §5.1 : snap sur grille) : orientation par pas de 22,5° (Player.m_placeRotationDegrees, docs 3.1),
    // position sur une grille de 0,5 m (distance d'accrochage de FindClosestSnapPoints, docs 3.2 point 11)
    constexpr float STEP = 3.14159265f / 8.0f;
    o = std::round(o / STEP) * STEP;
    x = std::round(x * 2.0f) / 2.0f;
    y = std::round(y * 2.0f) / 2.0f;
    // la base de la pièce suit le terrain (hauteur statique serveur) ; repli sur la hauteur du joueur
    float ground = player->GetMap()->GetTerrain()->GetHeightStatic(x, y, player->GetPositionZ() + 2.0f);
    float z = (ground > -100000.0f ? ground : player->GetPositionZ()) + up;

    std::string msg;
    uint32 guid = sBuildingMgr.TryPlace(player, *tpl, x, y, z, o, false, msg);
    WLSendText(msg.c_str());
    if (!guid)
    {
        SetSentErrorMessage(true);
        return false;
    }
    return true;
}

// .build api placeat <x> <y> <z> : pose la pièce choisie (select) au point donné, avec accroche (même chemin que le sort du marteau)
bool ChatHandler::HandleBuildPlaceAtCommand(char* args)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    float x, y, z;
    if (!player || !ExtractFloat(&args, x) || !ExtractFloat(&args, y) || !ExtractFloat(&args, z))
        return false;
    sBuildingMgr.PlaceFromSpell(player, x, y, z);
    return true;
}

// .build api select <pièce> [rotation 0-15] : pièce choisie dans le menu du marteau
bool ChatHandler::HandleBuildSelectCommand(char* args)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    if (!player)
        return false;
    WLPieceTemplate const* tpl = ResolveTemplate(ExtractLiteralArg(&args));
    uint32 rot = 0;
    if (!tpl || !ExtractOptUInt32(&args, rot, 0))
    {
        WLSendText("Pièce inconnue.");
        return false;
    }
    WLHammerState& hs = sBuildingMgr.Hammer(player->GetObjectGuid().GetCounter());
    hs.pieceId = tpl->id;
    hs.rot = int32(rot % 16);
    hs.mode = "build";
    // accord : « pièce choisie » quel que soit le genre du nom (l'addon envoie select en silencieux : son bandeau suffit)
    PSendSysMessage("Pièce choisie : %s (rotation %g°).", tpl->name.c_str(), double(hs.rot) * 22.5);
    return true;
}

// .build api mode <build|remove|repair> : mode du marteau (clic droit sur une pièce : démolir / réparer)
bool ChatHandler::HandleBuildModeCommand(char* args)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    char* m = ExtractLiteralArg(&args);
    if (!player || !m || (strcmp(m, "build") && strcmp(m, "remove") && strcmp(m, "repair")))
        return false;
    sBuildingMgr.Hammer(player->GetObjectGuid().GetCounter()).mode = m;
    PSendSysMessage("Marteau : mode %s.", !strcmp(m, "build") ? "construction" : !strcmp(m, "remove") ? "démolition (clic droit sur une pièce)" : "réparation (clic droit sur une pièce)");
    return true;
}

// .build bulk <pièce> <n> : pose n pièces en grille 10 colonnes, pas de 2,2 m devant le joueur (test de charge/persistance, GM, sans coût)
bool ChatHandler::HandleBuildBulkCommand(char* args)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    if (!player)
        return false;

    WLPieceTemplate const* tpl = ResolveTemplate(ExtractLiteralArg(&args));
    uint32 count = 0;
    if (!tpl || !ExtractUInt32(&args, count) || count == 0 || count > 1000)
    {
        WLSendText("Usage : .build bulk <pièce> <1-1000>");
        SetSentErrorMessage(true);
        return false;
    }

    float o = player->GetOrientation();
    float baseX = player->GetPositionX() + 4.0f * std::cos(o);
    float baseY = player->GetPositionY() + 4.0f * std::sin(o);
    float rx = -std::sin(o), ry = std::cos(o);       // vecteur « droite »
    float fx = std::cos(o), fy = std::sin(o);        // vecteur « avant »

    uint32 placed = 0;
    std::string err;
    for (uint32 i = 0; i < count; ++i)
    {
        float col = float(i % 10) * 2.2f, row = float(i / 10) * 2.2f;
        float x = baseX + rx * col + fx * row;
        float y = baseY + ry * col + fy * row;
        float ground = player->GetMap()->GetTerrain()->GetHeightStatic(x, y, player->GetPositionZ() + 2.0f);
        float z = ground > -100000.0f ? ground : player->GetPositionZ();
        if (!sBuildingMgr.Place(player->GetMap(), *tpl, player->GetObjectGuid().GetCounter(), x, y, z, o, err))
            break;
        ++placed;
    }
    PSendSysMessage("%u/%u pièces posées%s%s", placed, count, placed < count ? " — arrêt : " : "", placed < count ? err.c_str() : "");
    return placed == count;
}

bool ChatHandler::HandleBuildRemoveCommand(char* /*args*/)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    if (!player)
        return false;

    bool isGm = m_session->GetSecurity() >= SEC_GAMEMASTER;
    uint32 playerGuid = player->GetObjectGuid().GetCounter();

    uint32 bestGuid = NearestPiece(player, 6.0f);
    if (!bestGuid)
    {
        WLSendText("Aucune pièce à moins de 6 m.");
        SetSentErrorMessage(true);
        return false;
    }
    WLPiece const& piece = sBuildingMgr.Pieces().at(bestGuid);
    if (!isGm && piece.ownerGuid != playerGuid)
    {
        WLSendText("Cette pièce ne vous appartient pas.");
        SetSentErrorMessage(true);
        return false;
    }
    // Player.CheckCanRemovePiece (docs 4.1) : une pièce qui exige un établi ne se démonte que s'il est à portée
    WLPieceTemplate const* tpl = sBuildingMgr.FindTemplate(piece.pieceId);
    std::string stErr;
    if (tpl && !sBuildingMgr.CheckStation(player, *tpl, stErr))
    {
        PSendSysMessage("Démolition impossible : %s.", stErr.c_str());
        SetSentErrorMessage(true);
        return false;
    }

    std::string costText = tpl ? Describe(tpl->costs) : "";
    std::string err;
    bool refund = tpl && !tpl->costs.empty() && !sBuildingMgr.IsNoCost(playerGuid);
    if (!sBuildingMgr.Remove(bestGuid, player->GetMap(), err, false, refund ? player : nullptr))
    {
        PSendSysMessage("Démolition impossible : %s", err.c_str());
        SetSentErrorMessage(true);
        return false;
    }
    if (refund)
        PSendSysMessage("Pièce %u démolie. Ressources rendues : %s.", bestGuid, costText.c_str());
    else
        PSendSysMessage("Pièce %u démolie.", bestGuid);
    return true;
}

// .build near [rayon] : compte les pièces connues (base) et les GameObjects de pièces réellement chargés autour du joueur
bool ChatHandler::HandleBuildNearCommand(char* args)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    if (!player)
        return false;

    float radius;
    if (!ExtractOptFloat(&args, radius, 50.0f))
        return false;

    uint32 known = 0;
    for (auto const& kv : sBuildingMgr.Pieces())
    {
        WLPiece const& p = kv.second;
        if (p.map != player->GetMapId())
            continue;
        float dx = p.x - player->GetPositionX(), dy = p.y - player->GetPositionY();
        if (dx * dx + dy * dy <= radius * radius)
            ++known;
    }

    GameObjectList gameobjects;
    MaNGOS::GameObjectInPosRangeCheck check(*player, player->GetPositionX(), player->GetPositionY(), player->GetPositionZ(), radius);
    MaNGOS::GameObjectListSearcher<MaNGOS::GameObjectInPosRangeCheck> searcher(gameobjects, check);
    Cell::VisitGridObjects(player, searcher, radius);

    uint32 loaded = 0;
    for (GameObject* go : gameobjects)
        if (sBuildingMgr.Pieces().find(go->GetDbGuid()) != sBuildingMgr.Pieces().end())
            ++loaded;

    PSendSysMessage("Rayon %.0f m : %u pièces en base, %u GameObjects de pièces chargés dans le monde.", radius, known, loaded);
    return true;
}

bool ChatHandler::HandleBuildCountCommand(char* /*args*/)
{
    uint32 mine = 0;
    if (m_session && m_session->GetPlayer())
        mine = sBuildingMgr.CountByOwner(m_session->GetPlayer()->GetObjectGuid().GetCounter());
    PSendSysMessage("Pièces : %u au total, %u à vous (plafonds : %u / %u).", uint32(sBuildingMgr.Pieces().size()), mine,
                    BuildingMgr::MAX_PIECES_TOTAL, BuildingMgr::MAX_PIECES_PER_OWNER);
    return true;
}

bool ChatHandler::HandleBuildPerfCommand(char* /*args*/)
{
    PSendSysMessage("Diff tick (600 derniers) : moyenne %u ms, max %u ms, %u pièces.", sBuildingMgr.AverageDiff(), sBuildingMgr.MaxDiff(),
                    uint32(sBuildingMgr.Pieces().size()));
    BuildingMgr::WorldCheckStats const& ws = sBuildingMgr.WorldStats();
    PSendSysMessage("Chevauchement du décor WoW (VMaps) : %llu tests, %llu bloqués, %.1f rayons/test, moyenne %.1f us, max %.1f us.",
                    (unsigned long long)ws.calls, (unsigned long long)ws.blocked, ws.calls ? double(ws.rays) / double(ws.calls) : 0.0,
                    ws.calls ? ws.totalUs / double(ws.calls) : 0.0, ws.maxUs);
    return true;
}

// .build support : valeur de support de la pièce la plus proche (6 m)
bool ChatHandler::HandleBuildSupportCommand(char* /*args*/)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    if (!player)
        return false;
    uint32 bestGuid = NearestPiece(player, 6.0f);
    if (!bestGuid)
    {
        WLSendText("Aucune pièce à moins de 6 m.");
        return true;
    }
    WLPiece const& p = sBuildingMgr.Pieces().at(bestGuid);
    PSendSysMessage("Pièce %u (modèle %u) : z=%.2f, terrain=%.2f, support %.1f, ancrée=%s, PV %u, couverte=%s, usure pluie %.0f s", p.guid, p.pieceId, p.z,
                    player->GetMap()->GetTerrain()->GetHeightStatic(p.x, p.y, p.z + 1.0f), p.support, p.grounded ? "oui" : "non", p.health,
                    p.covered ? "oui" : "non", p.wetSeconds);
    return true;
}

// .build station : stations de fabrication à portée (établi, forge, tailleur de pierre, table d'artisan) : abri, couverture, niveau.
// API : une ligne S|guid|utilisable|couverture%|niveau|type par type de station à portée.
bool ChatHandler::HandleBuildStationCommand(char* /*args*/)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    if (!player)
        return false;
    static char const* const kinds[] = { "workbench", "forge", "stonecutter", "artisan" };
    bool any = false;
    for (char const* kind : kinds)
    {
        WLPiece const* st = sBuildingMgr.FindStationInRange(player->GetMap(), player->GetPositionX(), player->GetPositionY(), kind, BuildingMgr::STATION_RANGE);
        if (!st)
            continue;
        any = true;
        float pct = 0.0f;
        bool usable = sBuildingMgr.StationUsable(*st, pct);
        uint32 level = sBuildingMgr.StationLevel(*st);
        WLRaw(this, "S|" + std::to_string(st->guid) + "|" + (usable ? "1" : "0") + "|" + std::to_string(int(pct * 100.0f)) + "|" + std::to_string(level) + "|" + kind);
        WLPieceTemplate const* t = sBuildingMgr.FindTemplate(st->pieceId);
        if (!strcmp(kind, "workbench"))
            PSendSysMessage("Établi %u : niveau %u, couverture %.0f %% (seuil 70 %%), %s.", st->guid, level, pct * 100.0f, usable ? "utilisable (à l'abri)" : "inutilisable : exposé");
        else
            PSendSysMessage("%s %u : niveau %u, couverture %.0f %%, %s.", t ? t->name.c_str() : kind, st->guid, level, pct * 100.0f, usable ? "utilisable (à l'abri)" : "inutilisable : exposé");
    }
    if (!any)
        WLSendText("Aucune station de fabrication à moins de 20 m.");
    return true;
}

bool ChatHandler::HandleBuildRecipesCommand(char* /*args*/)
{
    if (sBuildingMgr.Recipes().empty())
    {
        WLSendText("Aucune recette.");
        return true;
    }
    WLSendText("Recettes d'établi :");
    for (auto const& kv : sBuildingMgr.Recipes())
    {
        WLRecipe const& r = kv.second;
        if (g_api)
        {
            WLRaw(this, "C|" + std::to_string(r.id) + "|" + r.name + "|" + r.station + "|" + std::to_string(r.outputItem) + ":" + std::to_string(r.outputCount) + "|" + CostsStr(r.ingredients) + "|" + std::to_string(r.minStationLevel));
            continue;
        }
        PSendSysMessage("  %u  %s -> %u x %s  [%s]  (%s niveau %u)", r.id, r.name.c_str(), r.outputCount, ItemName(r.outputItem).c_str(), Describe(r.ingredients).c_str(), r.station.c_str(), r.minStationLevel);
    }
    return true;
}

// .build craft <recette> : fabrication à l'établi, qui doit être à portée ET à l'abri (CraftingStation.CheckUsable, docs 2.4)
bool ChatHandler::HandleBuildCraftCommand(char* args)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    if (!player)
        return false;
    char* token = ExtractLiteralArg(&args);
    WLRecipe const* r = token ? sBuildingMgr.FindRecipe(token) : nullptr;
    if (!r)
    {
        WLSendText("Recette inconnue. Utilisez .build recipes");
        SetSentErrorMessage(true);
        return false;
    }
    // Recipe.m_craftingStation nul : fabrication à la main, sans station (marteau, hache en pierre)
    WLPiece const* st = r->station.empty() ? nullptr : sBuildingMgr.FindStationInRange(player->GetMap(), player->GetPositionX(), player->GetPositionY(), r->station, BuildingMgr::STATION_RANGE);
    if (!st && !r->station.empty())
    {
        PSendSysMessage("Il faut une station (%s) à moins de 20 m.", r->station.c_str());
        SetSentErrorMessage(true);
        return false;
    }
    float pct = 0.0f;
    // CraftingStation.CheckUsable : l'abri n'est exigé que des stations qui le demandent (m_craftRequireRoof) ; le four à charbon n'en a pas
    if (st && r->station != "charcoal_kiln" && !sBuildingMgr.StationUsable(*st, pct))
    {
        // même texte que le refus de réparation (Knowledge.cpp, PrepareRepair) : l'addon dédoublonne les textes identiques
        PSendSysMessage("Station exposée (couverture %.0f %%, il faut un toit et au moins 70 %%).", pct * 100.0f);
        SetSentErrorMessage(true);
        return false;
    }
    // niveau de station requis (Recipe.m_minStationLevel ; niveau = 1 + extensions, docs 8)
    uint32 stationLevel = st ? sBuildingMgr.StationLevel(*st) : 1;
    if (stationLevel < r->minStationLevel)
    {
        PSendSysMessage("Niveau de station insuffisant (%u, il faut %u) : posez des extensions à moins de 5 m.", stationLevel, r->minStationLevel);
        SetSentErrorMessage(true);
        return false;
    }
    std::string missing;
    if (!sBuildingMgr.HasItems(player, r->ingredients, missing))
    {
        PSendSysMessage("Ressources manquantes : %s.", missing.c_str());
        SetSentErrorMessage(true);
        return false;
    }
    if (st)
        sKnowledgeMgr.LearnStation(player, *st);         // fabriquer = être à la station -> connue (UpdateStations)
    sBuildingMgr.ConsumeItems(player, r->ingredients);
    std::vector<WLItemCount> out{ WLItemCount{ r->outputItem, r->outputCount } };
    uint32 mailed = sBuildingMgr.GiveItems(player, player->GetObjectGuid().GetCounter(), out, "Fabrication");
    if (st)                                              // InventoryGui.DoCrafting IL 1761–1818 : station.m_craftingSkill (Fabrication) +1
        sWLSkillMgr.Raise(player, WL_SKILL_CRAFTING, 1.0f);
    PSendSysMessage("Fabriqué : %u x %s%s.", r->outputCount, ItemName(r->outputItem).c_str(), mailed ? " (sac plein : envoyé par courrier)" : "");
    return true;
}

// .build nocost [on|off] : pose sans coût ni établi (équivalent de Player.m_noPlacementCost), GM
bool ChatHandler::HandleBuildNoCostCommand(char* args)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    if (!player)
        return false;
    uint32 guid = player->GetObjectGuid().GetCounter();
    char* token = ExtractLiteralArg(&args);
    bool on = token ? (strcmp(token, "off") != 0) : !sBuildingMgr.IsNoCost(guid);
    sBuildingMgr.SetNoCost(guid, on);
    PSendSysMessage("Pose sans coût : %s.", on ? "activée" : "désactivée");
    return true;
}

// .build rain <secondes> : période d'usure sous la pluie (Valheim : 60), pour accélérer les tests
bool ChatHandler::HandleBuildRainCommand(char* args)
{
    float period;
    if (!ExtractOptFloat(&args, period, 60.0f) || period < 1.0f)
        return false;
    sBuildingMgr.SetRainPeriod(period);
    PSendSysMessage("Période d'usure sous la pluie : %.0f s (Valheim : 60 s).", period);
    return true;
}

bool ChatHandler::HandleBuildStatsCommand(char* /*args*/)
{
    PSendSysMessage("Pièces détruites par la simulation depuis le démarrage : %u.", sBuildingMgr.LastCollapsed());
    return true;
}

// .build dump [n] : liste les n premières pièces (z, support, ancrage, PV)
bool ChatHandler::HandleBuildDumpCommand(char* args)
{
    uint32 limit;
    if (!ExtractOptUInt32(&args, limit, 20))
        return false;
    uint32 i = 0;
    for (auto const& kv : sBuildingMgr.Pieces())
    {
        if (i++ >= limit)
            break;
        WLPiece const& p = kv.second;
        PSendSysMessage("%u modèle %u z=%.2f support=%.1f ancrée=%s PV=%u", p.guid, p.pieceId, p.z, p.support, p.grounded ? "oui" : "non", p.health);
    }
    return true;
}

// .build grace <secondes> : délai avant usure/effondrement d'une pièce neuve (Valheim, pièces posées par un joueur : 0)
bool ChatHandler::HandleBuildGraceCommand(char* args)
{
    float seconds;
    if (!ExtractOptFloat(&args, seconds, 0.0f) || seconds < 0.0f)
        return false;
    sBuildingMgr.SetGraceSeconds(seconds);
    PSendSysMessage("Délai de grâce des pièces neuves : %.0f s (Valheim : 0 pour les pièces posées par un joueur).", seconds);
    return true;
}

// .build removeid <guid> : démolit une pièce par son guid (GM, sans remboursement)
bool ChatHandler::HandleBuildRemoveIdCommand(char* args)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    uint32 guid;
    if (!player || !ExtractUInt32(&args, guid))
        return false;
    std::string err;
    if (!sBuildingMgr.Remove(guid, player->GetMap(), err))
    {
        PSendSysMessage("Démolition impossible : %s", err.c_str());
        return false;
    }
    PSendSysMessage("Pièce %u démolie.", guid);
    return true;
}

// .build repair : répare la pièce la plus proche (6 m) à l'établi : soin complet, sans coût (Player.Repair, docs 1.6)
bool ChatHandler::HandleBuildRepairCommand(char* /*args*/)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    if (!player)
        return false;
    uint32 guid = NearestPiece(player, 6.0f);
    if (!guid)
    {
        WLSendText("Aucune pièce à moins de 6 m.");
        SetSentErrorMessage(true);
        return false;
    }
    WLPiece const& piece = sBuildingMgr.Pieces().at(guid);
    bool isGm = m_session->GetSecurity() >= SEC_GAMEMASTER;
    if (!isGm && piece.ownerGuid != player->GetObjectGuid().GetCounter())
    {
        WLSendText("Cette pièce ne vous appartient pas.");
        SetSentErrorMessage(true);
        return false;
    }
    std::string stErr;
    WLPieceTemplate const* rtpl = sBuildingMgr.FindTemplate(piece.pieceId);
    if (rtpl && !sBuildingMgr.CheckStation(player, *rtpl, stErr))
    {
        PSendSysMessage("Réparation impossible : %s.", stErr.c_str());
        SetSentErrorMessage(true);
        return false;
    }
    std::string err;
    if (!sBuildingMgr.Repair(guid, err))
    {
        PSendSysMessage("Réparation impossible : %s.", err.c_str());
        SetSentErrorMessage(true);
        return false;
    }
    PSendSysMessage("Pièce %u réparée.", guid);
    return true;
}

// .build inv : vos matériaux Wowlheim (9200000-9299999) et outils (9201000-9201999)
bool ChatHandler::HandleBuildInvCommand(char* /*args*/)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    if (!player)
        return false;
    std::string line;
    std::vector<WLItemCount> have;
    for (uint32 id = 9200001; id < 9201999; ++id)
    {
        uint32 n = player->GetItemCount(id);
        if (!n)
            continue;
        have.push_back(WLItemCount{ id, n });
        if (!line.empty())
            line += ", ";
        line += std::to_string(n) + " " + ItemName(id);
    }
    if (g_api)
    {
        WLRaw(this, "I|" + CostsStr(have));
        return true;
    }
    PSendSysMessage("Inventaire Wowlheim : %s", line.empty() ? "vide" : line.c_str());
    return true;
}

namespace
{
    struct WLTreeCheck
    {
        WorldObject const* obj; float range;
        WorldObject const& GetFocusObject() const { return *obj; }
        bool operator()(Unit* u) { return sTreeMgr.IsTree(u) && obj->IsWithinDistInMap(u, range); }
    };
}

// .build api trees [rayon=30] : arbres et bûches proches (T|guid|entrée|nature|x|y|z|vivant|PV) — diagnostic et tests
bool ChatHandler::HandleBuildTreesCommand(char* args)
{
    Player* player = m_session ? m_session->GetPlayer() : nullptr;
    float radius;
    if (!player || !ExtractOptFloat(&args, radius, 30.0f))
        return false;
    UnitList units;
    WLTreeCheck check{ player, radius };
    MaNGOS::UnitListSearcher<WLTreeCheck> searcher(units, check);
    Cell::VisitGridObjects(player, searcher, radius);
    for (Unit* u : units)
    {
        WLTreeInfo const* t = sTreeMgr.Find(u->GetEntry());
        char buf[200];
        snprintf(buf, sizeof(buf), "T|%u|%u|%s|%.2f|%.2f|%.2f|%u|%u", u->GetObjectGuid().GetCounter(), u->GetEntry(), t ? t->kind.c_str() : "?",
                 u->GetPositionX(), u->GetPositionY(), u->GetPositionZ(), u->IsAlive() ? 1 : 0, u->GetHealth());
        WLRaw(this, buf);
    }
    PSendSysMessage("%u arbres/bûches à moins de %.0f m.", uint32(units.size()), radius);
    return true;
}

namespace
{
    // Point du contour de la zone de construction d'une station, dans le repère local de sa boîte (centre, sans rotation)
    struct WLOutlinePoint { float x, y, o; };

    // Contour de la zone « distance horizontale au bord de la boîte < R » (BuildingMgr::DistToPiece2D, FindStationInRange) :
    // rectangle de demi-côtés (hx, hy) agrandi de R = 4 côtés droits + 4 quarts de cercle. Pour une station de 1-2 m, c'est
    // presque le cercle de Valheim. Échantillonné en n points régulièrement espacés (milieux des segments), avec la tangente.
    // Valheim (CircleProjector de piece_workbench, lu dans le bundle) : 80 segments sur un cercle de 20 m, soit un pas de 1,57 m.
    void StationOutline(float hx, float hy, float R, std::vector<WLOutlinePoint>& out)
    {
        float const PI = 3.14159265f;
        float const arc = 0.5f * PI * R;
        float const len[8] = { 2 * hy, arc, 2 * hx, arc, 2 * hy, arc, 2 * hx, arc };
        float total = 0.0f;
        for (float l : len)
            total += l;
        int n = int(total / 1.57f + 0.5f);
        n = std::max(24, std::min(n, 96));
        out.clear();
        for (int i = 0; i < n; ++i)
        {
            float s = (i + 0.5f) * total / n;
            int k = 0;
            while (k < 7 && s > len[k])
            {
                s -= len[k];
                ++k;
            }
            WLOutlinePoint p{};
            switch (k)
            {
                case 0: p = { hx + R, -hy + s, 0.5f * PI }; break;         // côté +x, vers +y
                case 2: p = { hx - s, hy + R, PI }; break;                 // côté +y, vers -x
                case 4: p = { -hx - R, hy - s, 1.5f * PI }; break;         // côté -x, vers -y
                case 6: p = { -hx + s, -hy - R, 0.0f }; break;             // côté -y, vers +x
                default:                                                   // coins : quart de cercle de centre (±hx, ±hy)
                {
                    float cx = (k == 1 || k == 7) ? hx : -hx;
                    float cy = (k == 1 || k == 3) ? hy : -hy;
                    float a = (k - 1) * 0.25f * PI + (R > 0 ? s / R : 0.0f);   // k=1 : 0..π/2, 3 : π/2..π, 5 : π..3π/2, 7 : 3π/2..2π
                    p = { cx + R * std::cos(a), cy + R * std::sin(a), a + 0.5f * PI };
                    break;
                }
            }
            out.push_back(p);
        }
    }

    // .build api stations [rayon=40] : stations de fabrication proches et contour de leur zone de construction, pour le
    // cercle de portée affiché par l'addon quand le marteau est en mode construction (Valheim : CraftingStation.m_areaMarker).
    //   ST|guid|kind|x|y|z|portée|dedans|n      dedans = 1 si le JOUEUR est dans la zone (c'est sa position que CheckStation teste)
    //   SG|guid|premier|x,y,z,o;x,y,z,o;...      n points du contour (sol sous le point), par lignes de 6
    // Les stations sont les pièces dont le kind est exigé par au moins une pièce du catalogue (Piece.m_craftingStation).
    // .build api models : prefab Valheim de chaque pièce du catalogue (modèle World\Wowlheim\<prefab>.m2 du patch client),
    // pour le préchargement des modèles par l'addon (WowlheimPreloadModel, docs/BUILD_CONTROLS.md §4.2).
    // Réponse : MD|id:prefab,id:prefab,... (lignes de 200 caractères au plus, concaténées par l'addon), puis D|models|1.
    bool Wowlheim_ModelsCommand(ChatHandler* h)
    {
        std::string line;
        for (auto const& kv : sBuildingMgr.Templates())
        {
            if (kv.second.prefab.empty())
                continue;
            std::string item = std::to_string(kv.first) + ":" + kv.second.prefab;
            if (!line.empty() && line.size() + item.size() + 1 > 200)
            {
                WLRaw(h, "MD|" + line);
                line.clear();
            }
            line += (line.empty() ? "" : ",") + item;
        }
        if (!line.empty())
            WLRaw(h, "MD|" + line);
        return true;
    }

    // .build api removeguid <guidHex> : clic milieu en mode construction (Valheim : bouton Remove → Player.RemovePiece),
    // pièce visée sous la souris (WowlheimGetMouseoverObject, docs/BUILD_CONTROLS.md §3, §5). Réponse M|<nom> démolie. ou E|<raison>,
    // puis D|removeguid|1/0 (ajouté par HandleBuildApiCommand). Le mode du marteau n'est pas changé.
    // Premier mot de args : GUID hexadécimal (16 chiffres au plus, préfixe 0x accepté) ; false si invalide
    bool WLParseGuidHex(char* args, ObjectGuid& guid)
    {
        std::string hex;
        for (char const* c = args ? args : ""; *c; ++c)       // premier mot (sans strtok : non réentrant)
        {
            if (*c == ' ' || *c == '	')
            {
                if (hex.empty())
                    continue;
                break;
            }
            hex += *c;
        }
        if (hex.size() > 2 && hex[0] == '0' && (hex[1] == 'x' || hex[1] == 'X'))
            hex = hex.substr(2);
        bool valid = !hex.empty() && hex.size() <= 16;
        for (char c : hex)
            valid = valid && std::isxdigit(static_cast<unsigned char>(c));
        if (valid)
            guid = ObjectGuid(uint64(std::strtoull(hex.c_str(), nullptr, 16)));
        return valid;
    }

    bool Wowlheim_RemoveGuidCommand(ChatHandler* h, Player* player, char* args)
    {
        if (!player)
            return false;
        ObjectGuid guid;
        if (!WLParseGuidHex(args, guid))
        {
            WLRaw(h, "E|GUID invalide.");
            return false;
        }
        uint32 entry = guid.GetEntry();
        if (!guid.IsGameObject() || entry < 9110000 || entry > 9119999)
        {
            WLRaw(h, "E|Rien à démolir.");
            return false;
        }
        auto const& pieces = sBuildingMgr.Pieces();
        auto it = pieces.find(guid.GetCounter());
        WLPieceTemplate const* tpl = it != pieces.end() ? sBuildingMgr.FindTemplate(it->second.pieceId) : nullptr;
        if (it == pieces.end() || !tpl || tpl->goEntry != entry)
        {
            WLRaw(h, "E|Rien à démolir.");
            return false;
        }
        if (!sBuildingMgr.IsHammerEquipped(player))
        {
            WLRaw(h, "E|Équipez le marteau.");
            return false;
        }
        WLPiece const& piece = it->second;
        // Valheim : point visé à moins de m_maxPlaceDistance (5 m) ; ici distance horizontale au bord de la pièce et écart
        // vertical entre la boîte de la pièce [z, z + hauteur] et le personnage (pieds .. tête) <= 5 m
        float px = player->GetPositionX(), py = player->GetPositionY();
        if (piece.map != player->GetMapId() || sBuildingMgr.DistToPiece2D(piece, px, py) > BuildingMgr::REMOVE_DISTANCE
            || sBuildingMgr.VerticalGap(piece, player->GetPositionZ()) > BuildingMgr::REMOVE_DISTANCE)
        {
            WLRaw(h, "E|Trop loin.");
            return false;
        }
        std::string err, name;
        if (!sBuildingMgr.TryRemoveByPlayer(player, piece.guid, err, name))
        {
            WLRaw(h, "E|" + err);
            return false;
        }
        WLRaw(h, "M|Démoli : " + name + ".");
        return true;
    }

    // .build api use <guidHex> : clic droit sur une pièce que le client 1.12 refuse (« You are too far away. » : il mesure 5 m
    // depuis le CENTRE de l'objet, trop court pour une fonderie ou une forge de plusieurs mètres). L'addon renvoie alors la pièce
    // sous la souris (WowlheimGetMouseoverObject) ; même vérification que HandleGameObjectUseOpcode (USE_DISTANCE du bord de la
    // boîte, BuildingMgr::InUseRange) puis même chemin que CMSG_GAMEOBJ_USE : GameObject::Use -> Wowlheim_OnPieceUse (SM| de
    // la fonderie, OPEN|craft de l'établi, démolir / réparer selon le mode du marteau). D|use|1/0 ajouté par HandleBuildApiCommand.
    bool Wowlheim_UseGuidCommand(ChatHandler* h, Player* player, char* args)
    {
        if (!player)
            return false;
        ObjectGuid guid;
        if (!WLParseGuidHex(args, guid))
        {
            WLRaw(h, "E|GUID invalide.");
            return false;
        }
        uint32 entry = guid.GetEntry();
        auto const& pieces = sBuildingMgr.Pieces();
        auto it = guid.IsGameObject() && entry >= 9110000 && entry <= 9119999 ? pieces.find(guid.GetCounter()) : pieces.end();
        WLPieceTemplate const* tpl = it != pieces.end() ? sBuildingMgr.FindTemplate(it->second.pieceId) : nullptr;
        GameObject* go = tpl && tpl->goEntry == entry && player->IsInWorld() ? player->GetMap()->GetGameObject(guid) : nullptr;
        if (!go || !go->IsSpawned())
        {
            WLRaw(h, "E|Rien à utiliser.");
            return false;
        }
        if (player->IsBeingTeleported() || !player->IsSelfMover())
            return false;
        if (!sBuildingMgr.InUseRange(player, it->second))
        {
            WLRaw(h, "E|Vous êtes trop loin.");
            return false;
        }
        if (go->HasFlag(GAMEOBJECT_FLAGS, GO_FLAG_IN_USE | GO_FLAG_NO_INTERACT) || !go->CanUseNow(player))
            return false;
        go->Use(player);
        return true;
    }

    // .build api canplace <x> <y> <z> [rot 0-15] : couleur du fantôme (Valheim : SetPlacementGhostValid). Mêmes contrôles que
    // la pose par le sort du marteau (BuildingMgr::CanPlaceFromSpell, accroche comprise), sans rien poser. Réponse :
    // CP|1|x|y|z|o|accroche  ou  CP|0|x|y|z|o|accroche|raison, puis D|canplace|1 : x, y, z, o = position et orientation de la
    // pièce APRÈS accroche (Valheim : le fantôme est montré au point accroché), accroche = 1 si un point d'accroche a été pris.
    // Appelée par l'addon au plus toutes les 0,25 s pendant le ciblage (docs/GHOST_PREVIEW.md, fantôme accroché).
    bool Wowlheim_CanPlaceCommand(ChatHandler* h, Player* player, char* args)
    {
        if (!player || !args)
            return false;
        float x, y, z;
        int rot = -1;
        if (std::sscanf(args, "%f %f %f %d", &x, &y, &z, &rot) < 3)
            return false;
        if (rot < 0)
            rot = sBuildingMgr.Hammer(player->GetObjectGuid().GetCounter()).rot;
        std::string err;
        WLPlacePreview pv;
        pv.x = x; pv.y = y; pv.z = z;
        bool ok = sBuildingMgr.CanPlaceFromSpell(player, x, y, z, int32(rot % 16), err, &pv);
        char buf[96];
        snprintf(buf, sizeof(buf), "|%.2f|%.2f|%.2f|%.3f|%d", pv.x, pv.y, pv.z, pv.o, pv.snapped ? 1 : 0);
        WLRaw(h, ok ? std::string("CP|1") + buf : std::string("CP|0") + buf + "|" + err);
        return true;
    }

    // .build api pieceinfo <guidHex> : état de la pièce sous la souris (Valheim, marteau en main : WearNTear.Highlight colore
    // la pièce selon GetSupportColorValue, le Hud affiche sa santé). Réponse PI|guidHex|pv|pvmax|support|nom, support =
    // SupportColorValue (-1 complet, 0..1 sinon), puis D|pieceinfo|1 ; E|Rien à inspecter. si ce n'est pas une pièce.
    bool Wowlheim_PieceInfoCommand(ChatHandler* h, Player* player, char* args)
    {
        if (!player)
            return false;
        ObjectGuid guid;
        if (!WLParseGuidHex(args, guid))
        {
            WLRaw(h, "E|GUID invalide.");
            return false;
        }
        uint32 entry = guid.GetEntry();
        auto const& pieces = sBuildingMgr.Pieces();
        auto it = guid.IsGameObject() && entry >= 9110000 && entry <= 9119999 ? pieces.find(guid.GetCounter()) : pieces.end();
        WLPieceTemplate const* tpl = it != pieces.end() ? sBuildingMgr.FindTemplate(it->second.pieceId) : nullptr;
        if (!tpl || tpl->goEntry != entry || it->second.map != player->GetMapId())
        {
            WLRaw(h, "E|Rien à inspecter.");
            return false;
        }
        WLPiece const& p = it->second;
        char buf[160];
        snprintf(buf, sizeof(buf), "PI|%016llX|%u|%u|%.3f|", (unsigned long long)guid.GetRawValue(), p.health,
                 tpl->maxHealth ? tpl->maxHealth : p.health, sBuildingMgr.SupportColorValue(p));
        WLRaw(h, std::string(buf) + tpl->name);
        return true;
    }

    bool Wowlheim_StationsCommand(ChatHandler* h, Player* player, char* args)
    {
        if (!player)
            return false;
        float radius = 40.0f;
        if (args && *args)
        {
            float r = float(std::atof(args));
            if (r > 0.0f)
                radius = std::min(r, 100.0f);
        }
        std::set<std::string> kinds;
        for (auto const& kv : sBuildingMgr.Templates())
            if (!kv.second.station.empty())
                kinds.insert(kv.second.station);

        Map* map = player->GetMap();
        float const px = player->GetPositionX(), py = player->GetPositionY();
        float const R = BuildingMgr::STATION_RANGE;
        std::vector<std::pair<float, WLPiece const*>> found;
        for (auto const& kv : sBuildingMgr.Pieces())
        {
            WLPiece const& p = kv.second;
            if (p.map != map->GetId())
                continue;
            WLPieceTemplate const* t = sBuildingMgr.FindTemplate(p.pieceId);
            if (!t || !kinds.count(t->kind))
                continue;
            float dx = p.x - px, dy = p.y - py;
            float d = std::sqrt(dx * dx + dy * dy);
            if (d <= radius)
                found.push_back({ d, &p });
        }
        std::sort(found.begin(), found.end(), [](auto const& a, auto const& b) { return a.first < b.first; });
        if (found.size() > 6)                       // l'addon affiche au plus 256 segments (DLL : WowlheimMarkerShow)
            found.resize(6);

        std::vector<WLOutlinePoint> outline;
        for (auto const& fd : found)
        {
            WLPiece const& st = *fd.second;
            WLPieceTemplate const* t = sBuildingMgr.FindTemplate(st.pieceId);
            WLBox b = sBuildingMgr.BoxOf(st);
            bool inside = sBuildingMgr.DistToPiece2D(st, px, py) < R;
            StationOutline(b.hx, b.hy, R, outline);
            char buf[256];
            snprintf(buf, sizeof(buf), "ST|%u|%s|%.2f|%.2f|%.2f|%.1f|%d|%u", st.guid, t->kind.c_str(), st.x, st.y, st.z, R, inside ? 1 : 0,
                     uint32(outline.size()));
            WLRaw(h, buf);

            // planchers proches : le contour passe dessus plutôt que sur le terrain qu'ils recouvrent
            std::vector<WLPiece const*> floors;
            for (auto const& kv : sBuildingMgr.Pieces())
            {
                WLPiece const& f = kv.second;
                if (f.map != st.map)
                    continue;
                WLPieceTemplate const* ft = sBuildingMgr.FindTemplate(f.pieceId);
                if (!ft || ft->kind != "floor" || ft->sz > 0.6f)
                    continue;
                float dx = f.x - st.x, dy = f.y - st.y;
                if (dx * dx + dy * dy < (R + 12.0f) * (R + 12.0f))
                    floors.push_back(&f);
            }

            float const c = std::cos(st.o), s = std::sin(st.o);
            float const twoPi = 6.28318531f;
            std::string line;
            uint32 first = 0, inLine = 0;
            for (uint32 i = 0; i < outline.size(); ++i)
            {
                WLOutlinePoint const& lp = outline[i];
                float wx = st.x + c * lp.x - s * lp.y;
                float wy = st.y + s * lp.x + c * lp.y;
                float wo = std::fmod(lp.o + st.o, twoPi);
                if (wo < 0)
                    wo += twoPi;
                // sol sous le point (terrain + WMO), cherché à partir d'un peu au-dessus de la station ; sinon plus haut (colline)
                float wz = map->GetHeight(wx, wy, st.z + 4.0f);
                if (wz <= INVALID_HEIGHT)
                    wz = map->GetHeight(wx, wy, st.z + 60.0f);
                if (wz <= INVALID_HEIGHT)
                    wz = st.z;
                for (WLPiece const* f : floors)
                {
                    float top = f->z + sBuildingMgr.FindTemplate(f->pieceId)->sz;
                    if (top > wz && top < st.z + 4.0f && sBuildingMgr.DistToPiece2D(*f, wx, wy) <= 0.01f)
                        wz = top;
                }
                char pt[64];
                snprintf(pt, sizeof(pt), "%s%.1f,%.1f,%.2f,%.2f", inLine ? ";" : "", wx, wy, wz + 0.05f, wo);
                line += pt;
                if (++inLine == 6 || i + 1 == outline.size())
                {
                    WLRaw(h, "SG|" + std::to_string(st.guid) + "|" + std::to_string(first) + "|" + line);
                    line.clear();
                    inLine = 0;
                    first = i + 1;
                }
            }
        }
        return true;
    }
}

// .build api <commande> [args] : exécute la commande avec des réponses structurées préfixées [WL] (canal de l'addon client)
bool ChatHandler::HandleBuildApiCommand(char* args)
{
    char* sub = ExtractLiteralArg(&args);
    if (!sub)
        return false;
    std::string cmd = sub;
    g_api = true;
    bool ok = true;
    if (cmd == "list") ok = HandleBuildListCommand(args);
    else if (cmd == "place") ok = HandleBuildPlaceCommand(args);
    else if (cmd == "remove") ok = HandleBuildRemoveCommand(args);
    else if (cmd == "models") ok = Wowlheim_ModelsCommand(this);
    else if (cmd == "removeguid") ok = Wowlheim_RemoveGuidCommand(this, m_session ? m_session->GetPlayer() : nullptr, args);
    else if (cmd == "use") ok = Wowlheim_UseGuidCommand(this, m_session ? m_session->GetPlayer() : nullptr, args);
    else if (cmd == "count") ok = HandleBuildCountCommand(args);
    else if (cmd == "support") ok = HandleBuildSupportCommand(args);
    else if (cmd == "station") ok = HandleBuildStationCommand(args);
    else if (cmd == "recipes") ok = HandleBuildRecipesCommand(args);
    else if (cmd == "craft") ok = HandleBuildCraftCommand(args);
    else if (cmd == "repair") ok = HandleBuildRepairCommand(args);
    else if (cmd == "inv") ok = HandleBuildInvCommand(args);
    else if (cmd == "select") ok = HandleBuildSelectCommand(args);
    else if (cmd == "mode") ok = HandleBuildModeCommand(args);
    else if (cmd == "placeat") ok = HandleBuildPlaceAtCommand(args);
    else if (cmd == "trees") ok = HandleBuildTreesCommand(args);
    else if (cmd == "canplace") ok = Wowlheim_CanPlaceCommand(this, m_session ? m_session->GetPlayer() : nullptr, args);
    else if (cmd == "pieceinfo") ok = Wowlheim_PieceInfoCommand(this, m_session ? m_session->GetPlayer() : nullptr, args);
    else if (cmd == "stations") ok = Wowlheim_StationsCommand(this, m_session ? m_session->GetPlayer() : nullptr, args);
    else if (cmd == "known") ok = Wowlheim_KnownCommand(this, m_session ? m_session->GetPlayer() : nullptr);
    else if (cmd == "repairitems") ok = Wowlheim_RepairItemsCommand(this, m_session ? m_session->GetPlayer() : nullptr, args);
    else if (cmd == "repairable") ok = Wowlheim_RepairableCommand(this, m_session ? m_session->GetPlayer() : nullptr, args);
    else if (cmd == "wear") ok = Wowlheim_WearCommand(this, m_session ? m_session->GetPlayer() : nullptr, args);
    else if (cmd == "skills") ok = Wowlheim_SkillsCommand(this, m_session ? m_session->GetPlayer() : nullptr, args);
    else if (cmd == "smelter") ok = Wowlheim_SmelterCommand(this, m_session ? m_session->GetPlayer() : nullptr, args, true);
    else if (cmd == "chest") ok = Wowlheim_ChestCommand(this, m_session ? m_session->GetPlayer() : nullptr, args);
    else if (cmd == "piece") ok = Wowlheim_PieceCommand(this, m_session ? m_session->GetPlayer() : nullptr, args);
    else
    {
        WLRaw(this, "E|commande inconnue");
        ok = false;
    }
    WLRaw(this, std::string("D|") + cmd + "|" + (ok ? "1" : "0"));      // fin de réponse : drapeau de succès
    g_api = false;
    SetSentErrorMessage(false);
    return true;
}
