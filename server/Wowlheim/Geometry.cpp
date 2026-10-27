// Géométrie logique des pièces : boîtes orientées, rayons, abri (Cover), stations.
// Remplace les raycasts Unity de Valheim (docs/VALHEIM_RULES.md 2.2–2.4) par des tests rayon/boîte sur les pièces posées.
#include "Wowlheim/BuildingMgr.h"
#include "Wowlheim/Pieces.h"

#include "Maps/Map.h"
#include "vmap/VMapFactory.h"

#include <algorithm>
#include <chrono>
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
        WLBox b = BoxOf(p);
        Wowlheim_OpenDoorBox(p, b);                // porte ouverte : battant tourné de 90° (Pieces.cpp), la baie ne couvre plus
        boxes.push_back(b);
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

// Distance horizontale (2D) d'un point au bord de la boîte orientée de la pièce (0 si le point est dans l'emprise).
float BuildingMgr::DistToPiece2D(WLPiece const& p, float x, float y) const
{
    WLBox b = BoxOf(p);
    float dx = x - b.cx, dy = y - b.cy;
    float c = std::cos(-b.yaw), s = std::sin(-b.yaw);
    float lx = std::fabs(dx * c - dy * s), ly = std::fabs(dx * s + dy * c);
    float ex = std::max(0.0f, lx - b.hx), ey = std::max(0.0f, ly - b.hy);
    return std::sqrt(ex * ex + ey * ey);
}

// fromEdge (défaut) : distance du joueur au bord de l'emprise de la station (adaptation : Valheim mesure depuis le transform de la
// station, rayon m_rangeBuild 10 m ; ici les stations sont des boîtes de plusieurs mètres, on mesure depuis leur bord pour que
// « à côté de la station » suffise). fromEdge = false : distance centre à centre (extensions, m_maxStationDistance).
WLPiece const* BuildingMgr::FindStationInRange(Map* map, float x, float y, std::string const& kind, float range, bool fromEdge) const
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
        float d = fromEdge ? DistToPiece2D(p, x, y) : std::sqrt(dx * dx + dy * dy);   // distance horizontale (docs 3.4)
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

// Piece.IsOverlapping de Valheim (Physics.OverlapBox de la boîte de la pièce contre les collisions solides, docs/VALHEIM_RULES.md 3.2)
// transposé à la géométrie statique de WoW, les VMaps (WMO et doodads M2 avec collision ; le terrain n'y est pas) :
//  1. segments horizontaux dans la boîte réduite de 10 % (tolère les contacts), à plusieurs hauteurs : grille de lignes espacées
//     d'au plus 0,5 m dans chaque axe local + 2 diagonales ; le niveau bas est à 0,3 m au-dessus de la base (ou à mi-hauteur
//     pour les pièces plates comme le plancher) ;
//  2. arêtes verticales (4 coins + centre) entre le niveau bas et le haut de la boîte ;
//  3. boîte entièrement DANS une coque fermée (chariot, rocher : aucun segment ne coupe de paroi) : toit à moins de 6 m au-dessus
//     et parois dans les 8 directions à moins de 4 m du bord de la boîte. Pas dans un bâtiment WMO (getAreaInfo : sol de WMO
//     sous la pièce) où une pièce intérieure est permise.
// Les pièces Wowlheim sont des GameObjects (arbre dynamique), pas dans les VMaps : elles ne se bloquent pas entre elles.
// Coût mesuré (sonde VMaps hors serveur, Comté du Nord) : 11 à 41 rayons, 2 à 5 µs en moyenne, 36 µs au plus ; `.build perf`.
bool BuildingMgr::OverlapsWorld(Map* map, WLPieceTemplate const& tpl, float x, float y, float z, float o) const
{
    if (!map)
        return false;
    auto t0 = std::chrono::steady_clock::now();
    VMAP::IVMapManager* vm = VMAP::VMapFactory::createOrGetVMapManager();
    uint32 const mapId = map->GetId();
    uint32 rays = 0;
    auto hit = [&](float ax, float ay, float az, float bx, float by, float bz)
    {
        ++rays;
        return !vm->isInLineOfSight(mapId, ax, ay, az, bx, by, bz, false);
    };

    auto run = [&]() -> bool
    {
        float const hx = tpl.sx * 0.45f, hy = tpl.sy * 0.45f, sz = tpl.sz;
        float const zb = z + std::max(std::min(0.3f, sz * 0.5f), sz * 0.05f);
        float const zt = std::max(zb, z + sz * 0.95f);
        std::vector<float> levels{ zb };
        if (zt - zb > 0.25f)
        {
            int n = int(std::ceil((zt - zb) / 1.0f));
            for (int i = 1; i <= n; ++i)
                levels.push_back(zb + (zt - zb) * float(i) / float(n));
        }
        float const c = std::cos(o), s = std::sin(o);
        auto world = [&](float lx, float ly, float& wx, float& wy) { wx = x + lx * c - ly * s; wy = y + lx * s + ly * c; };
        int const nx = std::max(2, std::min(9, int(std::ceil(2.0f * hx / 0.5f)) + 1));
        int const ny = std::max(2, std::min(9, int(std::ceil(2.0f * hy / 0.5f)) + 1));
        float ax, ay, bx, by;
        for (float lz : levels)
        {
            for (int i = 0; i < ny; ++i)
            {
                float ly = -hy + 2.0f * hy * float(i) / float(ny - 1);
                world(-hx, ly, ax, ay); world(hx, ly, bx, by);
                if (hit(ax, ay, lz, bx, by, lz))
                    return true;
            }
            for (int i = 0; i < nx; ++i)
            {
                float lx = -hx + 2.0f * hx * float(i) / float(nx - 1);
                world(lx, -hy, ax, ay); world(lx, hy, bx, by);
                if (hit(ax, ay, lz, bx, by, lz))
                    return true;
            }
            world(-hx, -hy, ax, ay); world(hx, hy, bx, by);
            if (hit(ax, ay, lz, bx, by, lz))
                return true;
            world(-hx, hy, ax, ay); world(hx, -hy, bx, by);
            if (hit(ax, ay, lz, bx, by, lz))
                return true;
        }
        if (zt > zb + 0.1f)
        {
            float const corners[5][2] = { { -hx, -hy }, { hx, -hy }, { hx, hy }, { -hx, hy }, { 0.0f, 0.0f } };
            for (auto const& p : corners)
            {
                world(p[0], p[1], ax, ay);
                if (hit(ax, ay, zb, ax, ay, zt))
                    return true;
            }
        }
        // 3. coque fermée
        float wz = zb;
        uint32 flags; int32 adtId, rootId, groupId;
        if (vm->getAreaInfo(mapId, x, y, wz, flags, adtId, rootId, groupId) && wz <= zb + 0.5f && wz > zb - 10.0f)
            return false;
        if (!hit(x, y, zb, x, y, zb + 6.0f))
            return false;
        for (int k = 0; k < 8; ++k)
        {
            float const a = float(k) * 3.14159265f / 4.0f, dx = std::cos(a), dy = std::sin(a);
            float const reach = std::min(std::fabs(dx) > 1e-4f ? hx / std::fabs(dx) : 1e9f, std::fabs(dy) > 1e-4f ? hy / std::fabs(dy) : 1e9f) + 4.0f;
            world(dx * reach, dy * reach, bx, by);
            if (!hit(x, y, zb, bx, by, zb))
                return false;
        }
        return true;
    };

    bool const blocked = run();
    double const us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t0).count();
    ++m_worldStats.calls;
    m_worldStats.rays += rays;
    m_worldStats.totalUs += us;
    m_worldStats.maxUs = std::max(m_worldStats.maxUs, us);
    if (blocked)
        ++m_worldStats.blocked;
    return blocked;
}
