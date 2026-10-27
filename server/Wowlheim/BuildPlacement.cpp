// Wowlheim — marteau façon Valheim : pose à la souris (sort à cible au sol), accroche sur les points d'accroche des pièces,
// démolition / réparation par clic droit sur une pièce selon le mode choisi dans le menu.
#include "Wowlheim/BuildingMgr.h"
#include "Wowlheim/Smelter.h"
#include "Wowlheim/Knowledge.h"
#include "Wowlheim/ValheimSkills.h"
#include "Wowlheim/Pieces.h"

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
    if (FindStationInRange(player->GetMap(), player->GetPositionX(), player->GetPositionY(), tpl.station, StationRange(tpl.station)))
        return true;
    std::string name = tpl.station;
    for (auto const& kv : m_templates)
        if (kv.second.kind == tpl.station)
        {
            name = kv.second.name;
            break;
        }
    err = "il faut " + name + " à moins de 20 m";
    return false;
}

// Pièce de même modèle à moins de MIN_SEPARATION (même règle que le refus « emplacement déjà occupé »)
bool BuildingMgr::OccupiedByIdentical(uint32 mapId, uint32 pieceId, float x, float y, float z) const
{
    for (auto const& kv : m_pieces)
    {
        WLPiece const& q = kv.second;
        if (q.map != mapId || q.pieceId != pieceId)
            continue;
        float dx = q.x - x, dy = q.y - y, dz = q.z - z;
        if (dx * dx + dy * dy + dz * dz < MIN_SEPARATION * MIN_SEPARATION)
            return true;
    }
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
                // un couple qui ramènerait la pièce exactement sur une pièce identique déjà posée (le fantôme visé sur un
                // plancher s'accroche sinon à ses propres coins) est ignoré : l'accroche choisit la place voisine libre
                if (OccupiedByIdentical(mapId, tpl.id, x + dx, y + dy, z + dz))
                    continue;
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

uint32 BuildingMgr::TryPlace(Player* player, WLPieceTemplate const& tpl, float x, float y, float z, float o, bool snap, std::string& msg, bool dryRun)
{
    uint32 playerGuid = player->GetObjectGuid().GetCounter();
    bool noCost = IsNoCost(playerGuid);
    if (Wowlheim_RefuseInCombat(player, msg))          // adaptation WoW : pas de construction en combat (Pieces.cpp)
        return 0;
    if (snap)
        Snap(player->GetMapId(), tpl, x, y, z, o);

    std::string why;
    if (IsForbiddenArea(player->GetMap(), x, y, z, why) || IsForbiddenArea(player->GetMap(), player->GetPositionX(), player->GetPositionY(), player->GetPositionZ(), why))
    {
        msg = "Pose refusée : " + why + ".";
        return 0;
    }
    // Valheim (Player.UpdatePlacementGhost -> Piece.IsOverlapping) : fantôme rouge et pose impossible si la pièce chevauche un
    // objet solide ; ici la géométrie statique de WoW (bâtiments WMO, chariots, rochers... ; Geometry.cpp). Texte de $msg_blocked.
    if (OverlapsWorld(player->GetMap(), tpl, x, y, z, o))
    {
        msg = "Bloqué.";
        return 0;
    }
    if (tpl.kind == "extension" && !noCost && !FindStationInRange(player->GetMap(), x, y, tpl.extStation, tpl.extDistance, false))
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
    if (dryRun)                                         // `.build api canplace` : contrôles de Place sans créer l'objet
    {
        if (!CanPlaceAt(player->GetMap(), tpl, playerGuid, x, y, z, err))
        {
            msg = "Pose refusée : " + err + ".";
            return 0;
        }
        msg.clear();
        return 1;
    }
    uint32 guid = Place(player->GetMap(), tpl, playerGuid, x, y, z, o, err);
    if (!guid)
    {
        msg = "Pose refusée : " + err + ".";
        return 0;
    }
    if (!noCost)
        ConsumeItems(player, tpl.costs);
    auto placed = m_pieces.find(guid);                  // Valheim : poser une station = être à côté -> connue (AddKnownStation)
    if (placed != m_pieces.end())
        sKnowledgeMgr.LearnStation(player, placed->second);
    msg = "Pièce " + tpl.name + " posée (id " + std::to_string(guid) + ")" + (noCost ? " [sans coût]" : "");
    return guid;
}

float BuildingMgr::PlaceOrientation(float playerOrientation, int32 rot)
{
    // Valheim : rotation = m_placeRotation × 22,5° (docs 3.1) ; ici ajoutée à l'orientation du personnage, celle du fantôme
    // natif du client, que la DLL tourne du même angle (WowlheimSetPlaceFacing(rot × π/8, 1), docs/GHOST_PREVIEW.md)
    constexpr float STEP = 3.14159265f / 8.0f;
    float o = playerOrientation + float(rot) * STEP;
    o = std::fmod(o, 2.0f * 3.14159265f);
    if (o < 0)
        o += 2.0f * 3.14159265f;
    return o;
}

bool BuildingMgr::InPlaceReach(Player* player, float x, float y, float z)
{
    // même portée que la démolition : point visé à moins de REMOVE_DISTANCE (horizontal) et écart vertical raisonnable
    return player->GetDistance2d(x, y) <= REMOVE_DISTANCE && std::fabs(z - player->GetPositionZ()) <= REMOVE_DISTANCE;
}

bool BuildingMgr::CanPlaceFromSpell(Player* player, float x, float y, float z, int32 rot, std::string& err, WLPlacePreview* preview)
{
    WLHammerState& hs = Hammer(player->GetObjectGuid().GetCounter());
    WLPieceTemplate const* tpl = FindTemplate(hs.pieceId);
    float const o = PlaceOrientation(player->GetOrientation(), rot);
    // Valheim (Player.UpdatePlacementGhost) : le fantôme est montré APRÈS accroche (FindClosestSnapPoints), valide ou non.
    // Même Snap que la pose (TryPlace snap=true), fait ici pour renvoyer la position accrochée à l'addon.
    float sx = x, sy = y, sz = z;
    bool snapped = tpl && Snap(player->GetMapId(), *tpl, sx, sy, sz, o);
    if (preview)
        *preview = WLPlacePreview{ sx, sy, sz, o, snapped };
    if (!tpl)
    {
        err = "Choisissez d'abord une pièce dans le menu du marteau.";
        return false;
    }
    if (!InPlaceReach(player, x, y, z))
    {
        err = "Trop loin.";
        return false;
    }
    return TryPlace(player, *tpl, sx, sy, sz, o, false, err, true) != 0;
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
    float o = PlaceOrientation(player->GetOrientation(), hs.rot);
    // Valheim (UpdatePlacement IL 1008–1013) : HaveStamina(attackStamina du marteau) avant toute action du marteau
    if (!sWLSkillMgr.HaveStamina(player, WLSkillMgr::ToolStamina(HAMMER_ITEM)))
    {
        Api(player, "E|Vous êtes trop fatigué.");
        sWLSkillMgr.SendStamina(player, true);           // Hud.StaminaBarEmptyFlash
        Api(player, "D|place|0");
        return;
    }
    if (!InPlaceReach(player, x, y, z))
    {
        Api(player, "E|Trop loin.");
        Api(player, "D|place|0");
        return;
    }
    std::string msg;
    uint32 guid = TryPlace(player, *tpl, x, y, z, o, true, msg);
    if (guid)
    {
        // UpdatePlacement IL 1189–1367 : UseStamina(GetBuildStamina), dette de démolition ou RaiseSkill(Fabrication, 1),
        // usure du marteau GetPlaceDurability
        sWLSkillMgr.UseStamina(player, sWLSkillMgr.BuildStamina(player));
        sWLSkillMgr.OnBuildPlace(player);
        if (IsHammerEquipped(player))
            sWLSkillMgr.WearHammer(player, player->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_MAINHAND));
        sWLSkillMgr.SendStamina(player, false);
    }
    // pas de SendNotification : le sort vient du marteau, l'addon affiche la ligne M| (évite le double affichage)
    Api(player, "M|" + msg);
    Api(player, std::string("D|place|") + (guid ? "1" : "0"));
}

// Démolition par un joueur (Player.RemovePiece, docs/VALHEIM_RULES.md 4.1–4.2) : partagée par le clic en mode Démolir
// (OnPieceUse) et `.build api removeguid` (clic milieu, docs/BUILD_CONTROLS.md §5). Le marteau et la portée sont vérifiés
// par l'appelant.
bool BuildingMgr::TryRemoveByPlayer(Player* player, uint32 goGuid, std::string& err, std::string& name)
{
    auto it = m_pieces.find(goGuid);
    if (it == m_pieces.end())
    {
        err = "Aucune pièce.";
        return false;
    }
    WLPiece const piece = it->second;
    WLPieceTemplate const* tpl = FindTemplate(piece.pieceId);
    name = tpl ? tpl->name : std::string("Pièce");
    uint32 playerGuid = player->GetObjectGuid().GetCounter();
    bool isGm = player->GetSession()->GetSecurity() >= SEC_GAMEMASTER;
    if (Wowlheim_RefuseInCombat(player, err))           // adaptation WoW : pas de démolition en combat (Pieces.cpp)
        return false;
    if (!sWLSkillMgr.HaveStamina(player, WLSkillMgr::ToolStamina(HAMMER_ITEM)))
    {
        err = "Vous êtes trop fatigué.";                // Valheim : HaveStamina(attackStamina) avant démolition
        sWLSkillMgr.SendStamina(player, true);
        return false;
    }
    if (!isGm && piece.ownerGuid != playerGuid)
    {
        err = "Cette pièce ne vous appartient pas.";
        return false;
    }
    if (tpl && !CheckStation(player, *tpl, err))        // Player.CheckCanRemovePiece (docs 4.1)
    {
        err = "Démolition impossible : " + err + ".";
        return false;
    }
    if (!Wowlheim_PieceCanBeRemoved(goGuid, err))       // Piece.CanBeRemoved : coffre personnel non vide (Pieces.cpp)
        return false;
    bool refund = tpl && !tpl->costs.empty() && !IsNoCost(playerGuid);
    if (!Remove(goGuid, player->GetMap(), err, false, refund ? player : nullptr))
    {
        if (err.empty())
            err = "Démolition impossible.";
        return false;
    }
    // Player.RemovePiece / UpdatePlacement IL 661–703 : UseStamina(GetBuildStamina), dette +1, usure GetPlaceDurability
    Item* hammerItem = player->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_MAINHAND);
    sWLSkillMgr.UseStamina(player, sWLSkillMgr.BuildStamina(player));
    sWLSkillMgr.OnBuildRemove(player);
    if (hammerItem && hammerItem->GetEntry() == HAMMER_ITEM)
        sWLSkillMgr.WearHammer(player, hammerItem);
    sWLSkillMgr.SendStamina(player, false);
    return true;
}

bool BuildingMgr::OnPieceUse(Player* player, uint32 goGuid)
{
    auto it = m_pieces.find(goGuid);
    if (it == m_pieces.end())
        return false;
    WLHammerState& hs = Hammer(player->GetObjectGuid().GetCounter());
    bool hammer = IsHammerEquipped(player);
    if (!hammer || hs.mode == "build")
    {
        // coffre (Container), porte / portail / volet (Door), lit (Bed) : Pieces.cpp
        if (Wowlheim_PieceUse(player, goGuid))
            return true;
        // fonderie / four à charbon / haut fourneau / rouet : échange (Smelter.cpp)
        if (sSmelterMgr.OnUse(player, goGuid))
            return true;
        // station de fabrication (CraftingStation.Interact -> InventoryGui.Show(station)) : l'addon ouvre le panneau de fabrication.
        // Lignes S| des stations à portée d'abord, puis OPEN|craft|guid|kind (dernière ligne : déclencheur de l'ouverture).
        WLPieceTemplate const* stpl = FindTemplate(it->second.pieceId);
        if (stpl && sKnowledgeMgr.IsCraftingStationKind(stpl->kind))
        {
            sKnowledgeMgr.LearnStation(player, it->second);
            ChatHandler h(player->GetSession());
            Wowlheim_SendStationLines(&h, player);
            Api(player, "OPEN|craft|" + std::to_string(goGuid) + "|" + stpl->kind);
        }
        return true;
    }
    WLPieceTemplate const* tpl = FindTemplate(it->second.pieceId);
    std::string err;
    if (hs.mode == "remove")
    {
        std::string name;
        if (TryRemoveByPlayer(player, goGuid, err, name))
        {
            Api(player, "M|Démoli : " + name + ".");
            Api(player, "D|remove|1");
            return true;
        }
    }
    else if (hs.mode == "repair")
    {
        Item* hammerItem = player->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_MAINHAND);
        if (Wowlheim_RefuseInCombat(player, err))       // adaptation WoW : pas de réparation en combat (Pieces.cpp)
        {
            Api(player, "E|" + err);
            return true;
        }
        if (!sWLSkillMgr.HaveStamina(player, WLSkillMgr::ToolStamina(HAMMER_ITEM)))
        {
            Api(player, "E|Vous êtes trop fatigué.");  // Valheim : HaveStamina(attackStamina) avant réparation
            sWLSkillMgr.SendStamina(player, true);
            return true;
        }
        if (tpl && !CheckStation(player, *tpl, err))
            err = "Réparation impossible : " + err + ".";
        else if (Repair(goGuid, err))
        {
            // Player.Repair (IL 216–288) : UseStamina(GetBuildStamina), durabilité −= m_useDurabilityDrain (1)
            sWLSkillMgr.UseStamina(player, sWLSkillMgr.BuildStamina(player));
            if (hammerItem)
                player->DurabilityPointsLoss(hammerItem, 1);
            sWLSkillMgr.SendStamina(player, false);
            Api(player, "M|" + (tpl ? tpl->name : std::string("Pièce")) + " réparée.");
            Api(player, "D|repair|1");
            return true;
        }
    }
    if (!err.empty())
        Api(player, "E|" + err);                        // l'addon affiche E| (plus de SendNotification : double affichage)
    return true;
}

void Wowlheim_PlaceFromSpell(Player* player, float x, float y, float z) { sBuildingMgr.PlaceFromSpell(player, x, y, z); }
float BuildingMgr::VerticalGap(WLPiece const& p, float pz) const
{
    WLPieceTemplate const* tpl = FindTemplate(p.pieceId);
    float top = p.z + (tpl ? tpl->sz : 1.0f);
    if (pz > top)
        return pz - top;
    if (pz + 2.0f < p.z)
        return p.z - (pz + 2.0f);
    return 0.0f;
}

bool BuildingMgr::InUseRange(Player* player, WLPiece const& p) const
{
    return p.map == player->GetMapId()
        && DistToPiece2D(p, player->GetPositionX(), player->GetPositionY()) <= USE_DISTANCE
        && VerticalGap(p, player->GetPositionZ()) <= USE_DISTANCE;
}

bool Wowlheim_OnPieceUse(Player* player, uint32 goGuid) { return sBuildingMgr.OnPieceUse(player, goGuid); }
bool Wowlheim_PieceInUseRange(Player* player, uint32 goEntry, uint32 goGuid)
{
    if (!player || goEntry < 9110000 || goEntry > 9119999)
        return false;
    auto it = sBuildingMgr.Pieces().find(goGuid);
    return it != sBuildingMgr.Pieces().end() && sBuildingMgr.InUseRange(player, it->second);
}
