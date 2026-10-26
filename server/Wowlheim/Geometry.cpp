// Géométrie logique des pièces : boîtes orientées, rayons, abri (Cover), stations.
// Remplace les raycasts Unity de Valheim (docs/VALHEIM_RULES.md 2.2–2.4) par des tests rayon/boîte sur les pièces posées.
#include "Wowlheim/BuildingMgr.h"

#include "Maps/Map.h"

#include <cmath>
#include <set>

namespace
{
    // 17 rayons de Cover.CreateCoverRays (assembly_utils.dll, IL 0–514) : haut ; 4 axes + 4 diagonales horizontaux ; 8 directions vers le haut.
    // Valheim est en y-haut ; ici z est la verticale.
    struct Dir { float x, y, z; };
    const Dir COVER_RAYS[17] =
    {
        { 0, 0, 1 },
        { 1, 0, 0 }, { -1, 0, 0 }, { 0, 1, 0 }, { 0, -1, 0 },
        { -1, -1, 0 }, { 1, -1, 0 }, { -1, 1, 0 }, { 1, 1, 0 },
        { -1, 0, 1 }, { 1, 0, 1 }, { 0, 1, 1 }, { 0, -1, 1 },
        { -1, -1, 1 }, { 1, -1, 1 }, { -1, 1, 1 }, { 1, 1, 1 }
    };

    // Rayon contre boîte orientée (rotation yaw autour de z). Renvoie vrai si touché avant maxT.
    bool RayBox(float ox, float oy, float oz, float dx, float dy, float dz, float maxT, WLBox const& b)
    {
        float c = std::cos(b.yaw), s = std::sin(b.yaw);
        // passage dans le repère local de la boîte (rotation inverse)
        float px = ox - b.cx, py = oy - b.cy, pz = oz - b.cz;
        float lox = c * px + s * py, loy = -s * px + c * py, loz = pz;
        float ldx = c * dx + s * dy, ldy = -s * dx + c * dy, ldz = dz;
        float tmin = 0.0f, tmax = maxT;
        float lo[3] = { lox, loy, loz }, ld[3] = { ldx, ldy, ldz }, h[3] = { b.hx, b.hy, b.hz };
        for (int i = 0; i < 3; ++i)
        {
            if (std::fabs(ld[i]) < 1e-6f)
            {
                if (lo[i] < -h[i] || lo[i] > h[i])
                    return false;
            }
            else
            {
                float t1 = (-h[i] - lo[i]) / ld[i], t2 = (h[i] - lo[i]) / ld[i];
                if (t1 > t2) std::swap(t1, t2);
                tmin = std::max(tmin, t1);
                tmax = std::min(tmax, t2);
                if (tmin > tmax)
                    return false;
            }
        }
        return true;
    }
}

WLBox BuildingMgr::BoxOf(WLPiece const& p) const
{
    WLPieceTemplate const* t = FindTemplate(p.pieceId);
    float sx = t ? t->sx : 1, sy = t ? t->sy : 1, sz = t ? t->sz : 1;
    return WLBox{ p.x, p.y, p.z + sz * 0.5f, sx * 0.5f, sy * 0.5f, sz * 0.5f, p.o };
}

// Cover.GetCoverForPoint (docs 2.3) : underRoof = rayon vertical de 100 m ; coverPct = rayons (30 m) bloqués / 17.
void BuildingMgr::GetCover(uint32 mapId, float x, float y, float z, float& coverPct, bool& underRoof, uint32 ignoreGuid) const
{
    underRoof = false;
    uint32 hits = 0;
    std::vector<WLBox> boxes;
    for (auto const& kv : m_pieces)
    {
        WLPiece const& p = kv.second;
        if (p.map != mapId || p.guid == ignoreGuid)
            continue;
        float dx = p.x - x, dy = p.y - y;
        if (dx * dx + dy * dy > 40.0f * 40.0f)
            continue;
        boxes.push_back(BoxOf(p));
    }
    for (int i = 0; i < 17; ++i)
    {
        Dir d = COVER_RAYS[i];
        float n = std::sqrt(d.x * d.x + d.y * d.y + d.z * d.z);
        d.x /= n; d.y /= n; d.z /= n;
        float len = i == 0 ? 100.0f : 29.5f;      // IsUnderRoof : 100 m ; rayons de couverture : 30 − rayon (0,5)
        bool hit = false;
        for (WLBox const& b : boxes)
            if (RayBox(x, y, z, d.x, d.y, d.z, len, b))
            {
                hit = true;
                break;
            }
        if (i == 0)
            underRoof = hit;
        if (hit)
            ++hits;
    }
    // Valheim compte le rayon vertical dans les 17 (la table CreateCoverRays commence par (0,1,0))
    coverPct = float(hits) / 17.0f;
}

// WearNTear.RoofCheck (docs 2.2) : rayon vertical vers le haut, 100 m, depuis le sommet de la pièce, hors pièce elle-même.
bool BuildingMgr::HaveRoofAbove(WLPiece const& piece) const
{
    WLPieceTemplate const* t = FindTemplate(piece.pieceId);
    float top = piece.z + (t ? t->sz : 1.0f);
    for (auto const& kv : m_pieces)
    {
        WLPiece const& o = kv.second;
        if (o.map != piece.map || o.guid == piece.guid)
            continue;
        float dx = o.x - piece.x, dy = o.y - piece.y;
        if (dx * dx + dy * dy > 6.0f * 6.0f)
            continue;
        if (RayBox(piece.x, piece.y, top, 0, 0, 1, 100.0f, BoxOf(o)))
            return true;
    }
    return false;
}

WLPiece const* BuildingMgr::FindStationInRange(Map* map, float x, float y, std::string const& kind, float range) const
{
    WLPiece const* best = nullptr;
    float bestD = range;
    for (auto const& kv : m_pieces)
    {
        WLPiece const& p = kv.second;
        if (p.map != map->GetId())
            continue;
        WLPieceTemplate const* t = FindTemplate(p.pieceId);
        if (!t || t->kind != kind)
            continue;
        float dx = p.x - x, dy = p.y - y;
        float d = std::sqrt(dx * dx + dy * dy);               // distance horizontale (docs 3.4)
        if (d < bestD)
        {
            bestD = d;
            best = &p;
        }
    }
    return best;
}

// CraftingStation.CheckUsable (docs 2.4) : m_craftRequireRoof → toit au-dessus ET couverture >= 0,7.
bool BuildingMgr::StationUsable(WLPiece const& station, float& coverPct) const
{
    WLPieceTemplate const* t = FindTemplate(station.pieceId);
    float z = station.z + (t ? t->sz : 1.0f) * 0.6f;      // m_roofCheckPoint : un peu au-dessus du milieu de la station
    bool underRoof = false;
    GetCover(station.map, station.x, station.y, z, coverPct, underRoof, station.guid);
    return underRoof && coverPct >= 0.7f;
}

// CraftingStation.GetLevel (docs/VALHEIM_RULES.md 8) : 1 + nombre d'extensions comptées.
// Une extension compte si sa distance 3D à la station est < son m_maxStationDistance, si elle vise cette station, et si son type
// n'est pas déjà compté (sauf m_stack). Le type d'une extension = son modèle de pièce (Piece.m_name).
uint32 BuildingMgr::StationLevel(WLPiece const& station) const
{
    WLPieceTemplate const* st = FindTemplate(station.pieceId);
    if (!st)
        return 1;
    uint32 level = 1;
    std::set<uint32> seenTypes;
    for (auto const& kv : m_pieces)
    {
        WLPiece const& p = kv.second;
        if (p.map != station.map)
            continue;
        WLPieceTemplate const* t = FindTemplate(p.pieceId);
        if (!t || t->kind != "extension" || t->extStation != st->kind)
            continue;
        float dx = p.x - station.x, dy = p.y - station.y, dz = p.z - station.z;
        if (std::sqrt(dx * dx + dy * dy + dz * dz) >= t->extDistance)
            continue;
        if (!t->extStack && !seenTypes.insert(t->id).second)
            continue;
        ++level;
    }
    return level;
}
