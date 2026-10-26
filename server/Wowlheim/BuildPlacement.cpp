// Wowlheim — marteau façon Valheim : pose à la souris (sort à cible au sol), accroche sur les points d'accroche des pièces,
// démolition / réparation par clic droit sur une pièce selon le mode choisi dans le menu.
#include "Wowlheim/BuildingMgr.h"

#include "Chat/Chat.h"
#include "Entities/GameObject.h"
#include "Entities/Item.h"
#include "Entities/Player.h"
#include "Globals/ObjectMgr.h"
#include "Maps/Map.h"
#include "Server/WorldSession.h"

#include <cmath>

namespace
{
    void Rot(float o, float lx, float ly, float& wx, float& wy)
    {
        float c = std::cos(o), s = std::sin(o);
        wx = lx * c - ly * s;
        wy = lx * s + ly * c;
    }

    // Réponses au canal de l'addon (mêmes lignes [WL] que .build api)
    void Api(Player* player, std::string const& line)
    {
        ChatHandler(player->GetSession()).SendSysMessage(("[WL]" + line).c_str());
    }
}

bool BuildingMgr::IsHammerEquipped(Player* player) const
{
    Item* main = player->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_MAINHAND);
    return main && main->GetEntry() == HAMMER_ITEM;
}

bool BuildingMgr::CheckStation(Player* player, WLPieceTemplate const& tpl, std::string& err) const
{
    // Player.HaveRequirements : HaveBuildStationInRange(m_craftingStation) (docs/VALHEIM_RULES.md 3.4)
    if (tpl.station.empty() || IsNoCost(player->GetObjectGuid().GetCounter()))
        return true;
    if (FindStationInRange(player->GetMap(), player->GetPositionX(), player->GetPositionY(), tpl.station, STATION_RANGE))
        return true;
    std::string name = tpl.station;
    for (auto const& kv : m_templates)
        if (kv.second.kind == tpl.station)
        {
            name = kv.second.name;
            break;
        }
    err = "il faut " + name + " à moins de 10 m";
    return false;
}

bool BuildingMgr::Snap(uint32 mapId, WLPieceTemplate const& tpl, float& x, float& y, float& z, float o) const
{
    if (tpl.snaps.empty())
        return false;
    // Valheim : couple (point du fantôme, point voisin) le plus proche, distance <= 0,5 m, pièces dans 10 m.
    // Adaptation (pas encore de fantôme visible pour viser un point précis) : si aucun couple à 0,5 m, on accepte
    // un couple à moins de 1 m à l'horizontale, situé jusqu'à 4 m au-dessus du point visé (étage sur une pièce posée).
    float bestD = 1.0e9f, bestDx = 0, bestDy = 0, bestDz = 0;
    bool exact = false;
    for (auto const& kv : m_pieces)
    {
        WLPiece const& q = kv.second;
        if (q.map != mapId)
            continue;
        float ddx = q.x - x, ddy = q.y - y;
        if (ddx * ddx + ddy * ddy > SNAP_SEARCH * SNAP_SEARCH)
            continue;
        WLPieceTemplate const* qt = FindTemplate(q.pieceId);
        if (!qt)
            continue;
        for (auto const& es : qt->snaps)
        {
            float ex, ey;
            Rot(q.o, es.x, es.y, ex, ey);
            ex += q.x; ey += q.y;
            float ez = q.z + es.z;
            for (auto const& ns : tpl.snaps)
            {
                float wx, wy;
                Rot(o, ns.x, ns.y, wx, wy);
                wx += x; wy += y;
                float wz = z + ns.z;
                float dx = ex - wx, dy = ey - wy, dz = ez - wz;
                float h = std::sqrt(dx * dx + dy * dy);
                float d3 = std::sqrt(dx * dx + dy * dy + dz * dz);
                bool isExact = d3 <= SNAP_DISTANCE;
                bool loose = h <= 1.0f && dz >= -0.5f && dz <= 4.0f;
                if (!isExact && (exact || !loose))
                    continue;
                float score = isExact ? d3 : h + 0.05f * std::fabs(dz);
                if ((isExact && !exact) || score < bestD)
                {
                    exact = exact || isExact;
                    bestD = score;
                    bestDx = dx; bestDy = dy; bestDz = dz;
                }
            }
        }
    }
    if (bestD > 1.0e8f)
        return false;
    x += bestDx; y += bestDy; z += bestDz;
    return true;
}

uint32 BuildingMgr::TryPlace(Player* player, WLPieceTemplate const& tpl, float x, float y, float z, float o, bool snap, std::string& msg)
{
    uint32 playerGuid = player->GetObjectGuid().GetCounter();
    bool noCost = IsNoCost(playerGuid);
    if (snap)
        Snap(player->GetMapId(), tpl, x, y, z, o);

    std::string why;
    if (IsForbiddenArea(player->GetMap(), x, y, z, why) || IsForbiddenArea(player->GetMap(), player->GetPositionX(), player->GetPositionY(), player->GetPositionZ(), why))
    {
        msg = "Pose refusée : " + why + ".";
        return 0;
    }
    if (tpl.kind == "extension" && !noCost && !FindStationInRange(player->GetMap(), x, y, tpl.extStation, tpl.extDistance))
    {
        char buf[200];
        snprintf(buf, sizeof(buf), "Pose refusée : il faut une station (%s) à moins de %.0f m de l'emplacement.", tpl.extStation.c_str(), tpl.extDistance);
        msg = buf;
        return 0;
    }
    std::string err;
    if (!CheckStation(player, tpl, err))
    {
        msg = "Pose refusée : " + err + ".";
        return 0;
    }
    std::string missing;
    if (!noCost && !HasItems(player, tpl.costs, missing))
    {
        msg = "Ressources manquantes : " + missing + ".";
        return 0;
    }
    uint32 guid = Place(player->GetMap(), tpl, playerGuid, x, y, z, o, err);
    if (!guid)
    {
        msg = "Pose refusée : " + err + ".";
        return 0;
    }
    if (!noCost)
        ConsumeItems(player, tpl.costs);
    msg = "Pièce " + tpl.name + " posée (id " + std::to_string(guid) + ")" + (noCost ? " [sans coût]" : "");
    return guid;
}

void BuildingMgr::PlaceFromSpell(Player* player, float x, float y, float z)
{
    WLHammerState& hs = Hammer(player->GetObjectGuid().GetCounter());
    WLPieceTemplate const* tpl = FindTemplate(hs.pieceId);
    if (!tpl)
    {
        player->GetSession()->SendNotification("Choisissez d'abord une pièce dans le menu du marteau.");
        Api(player, "D|place|0");
        return;
    }
    // Valheim : rotation = orientation de la vue + m_placeRotation × 22,5° (docs 3.1) ; ici l'orientation du personnage,
    // la même que celle du fantôme natif du client (docs/GHOST_PREVIEW.md)
    constexpr float STEP = 3.14159265f / 8.0f;
    float o = player->GetOrientation() + float(hs.rot) * STEP;
    o = std::fmod(o, 2.0f * 3.14159265f);
    if (o < 0)
        o += 2.0f * 3.14159265f;
    std::string msg;
    uint32 guid = TryPlace(player, *tpl, x, y, z, o, true, msg);
    if (!guid)
        player->GetSession()->SendNotification("%s", msg.c_str());
    Api(player, "M|" + msg);
    Api(player, std::string("D|place|") + (guid ? "1" : "0"));
}

bool BuildingMgr::OnPieceUse(Player* player, uint32 goGuid)
{
    auto it = m_pieces.find(goGuid);
    if (it == m_pieces.end())
        return false;
    if (!IsHammerEquipped(player))
        return true;                                    // pièce : aucune action sans le marteau
    WLHammerState& hs = Hammer(player->GetObjectGuid().GetCounter());
    WLPiece const piece = it->second;
    WLPieceTemplate const* tpl = FindTemplate(piece.pieceId);
    uint32 playerGuid = player->GetObjectGuid().GetCounter();
    bool isGm = player->GetSession()->GetSecurity() >= SEC_GAMEMASTER;
    std::string err;
    if (hs.mode == "remove")
    {
        if (!isGm && piece.ownerGuid != playerGuid)
            err = "Cette pièce ne vous appartient pas.";
        else if (tpl && !CheckStation(player, *tpl, err))        // Player.CheckCanRemovePiece (docs 4.1)
            err = "Démolition impossible : " + err + ".";
        else
        {
            bool refund = tpl && !tpl->costs.empty() && !IsNoCost(playerGuid);
            if (Remove(goGuid, player->GetMap(), err, false, refund ? player : nullptr))
            {
                Api(player, "M|" + (tpl ? tpl->name : std::string("Pièce")) + " démolie.");
                Api(player, "D|remove|1");
                return true;
            }
        }
    }
    else if (hs.mode == "repair")
    {
        if (tpl && !CheckStation(player, *tpl, err))
            err = "Réparation impossible : " + err + ".";
        else if (Repair(goGuid, err))
        {
            Api(player, "M|" + (tpl ? tpl->name : std::string("Pièce")) + " réparée.");
            Api(player, "D|repair|1");
            return true;
        }
    }
    else
        return true;
    if (!err.empty())
    {
        player->GetSession()->SendNotification("%s", err.c_str());
        Api(player, "E|" + err);
    }
    return true;
}

void Wowlheim_PlaceFromSpell(Player* player, float x, float y, float z) { sBuildingMgr.PlaceFromSpell(player, x, y, z); }
bool Wowlheim_OnPieceUse(Player* player, uint32 goGuid) { return sBuildingMgr.OnPieceUse(player, goGuid); }
