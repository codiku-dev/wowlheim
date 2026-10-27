// Simulation d'intégrité structurelle et d'usure — règles issues de docs/VALHEIM_RULES.md (extraction REA).
// Adaptation WoW : pas de physique, voisinage par distance entre centres ; sol = hauteur de terrain serveur.
#include "Wowlheim/BuildingMgr.h"
#include "Wowlheim/TreeMgr.h"
#include "Wowlheim/Smelter.h"
#include "Wowlheim/Knowledge.h"

#include "Database/DatabaseEnv.h"
#include "Globals/ObjectMgr.h"
#include "Log/Log.h"
#include "Maps/Map.h"
#include "Maps/MapManager.h"
#include "Weather/Weather.h"

#include <algorithm>
#include <cmath>
#include <unordered_map>
#include <vector>

namespace
{
    // docs/VALHEIM_RULES.md §1.1 — WearNTear::GetMaterialProperties (IL 0–353)
    struct Material { float maxSupport, minSupport, lossH, lossV; };
    constexpr Material MATERIALS[9] =
    {
        {  100,  10, 0.2f,        0.125f },       // 0 Wood
        { 1000, 100, 1.0f,        0.125f },       // 1 Stone      (table de sauts : cas 1 → IL 114)
        { 1500,  20, 0.0769231f,  0.0769231f },   // 2 Iron       (cas 2 → IL 144)
        {  140,  10, 0.1666667f,  0.1f },         // 3 HardWood   (cas 3 → IL 84)
        { 1500, 100, 0.5f,        0.125f },       // 4 Marble
        { 2000, 100, 0.3333333f,  0.1f },         // 5 Ashstone
        { 5000, 100, 0.25f,       0.0666667f },   // 6 Ancient
        { 1000, 100, 0.3333333f,  0.125f },       // 7 Ice
        {  200,  10, 0.2f,        0.0769231f }    // 8 Timberwood
    };

    Material const& MaterialOf(uint8 index) { return MATERIALS[index < 9 ? index : 0]; }

    constexpr float NEIGHBOR_RADIUS = 3.0f;     // adaptation : rayon de contact entre pièces (Valheim : chevauchement de colliders)
    constexpr float GROUND_BURY_MAX = 3.0f;     // adaptation : enfouissement maximal compté comme ancré
constexpr float GROUND_TOLERANCE = 0.75f;   // adaptation : une pièce dont la base est à moins de 0,75 m du terrain est ancrée
    constexpr float ROOF_RADIUS = 1.2f;         // adaptation : demi-largeur de la colonne de toit
    constexpr float COM_EPS = 0.1f;             // Valheim : d = distance + 0,1 (UpdateSupport IL 758–796)
    constexpr float PI_F = 3.14159265f;

    struct PieceCell { int x, y; bool operator==(PieceCell const& o) const { return x == o.x && y == o.y; } };
    struct PieceCellHash { size_t operator()(PieceCell const& c) const { return size_t(uint32(c.x) * 73856093u) ^ size_t(uint32(c.y) * 19349663u); } };

    typedef std::unordered_map<PieceCell, std::vector<WLPiece*>, PieceCellHash> PieceGrid;
    constexpr float CELL = 4.0f;

    PieceCell PieceCellOf(float x, float y) { return PieceCell{ int(std::floor(x / CELL)), int(std::floor(y / CELL)) }; }

    bool IsStructural(WLPieceTemplate const* t)
    {
        // WearNTear.m_noSupportWear : vrai pour les éléments de structure, pas pour le feu de camp ni l'établi (choix de conception)
        return t && (t->kind == "floor" || t->kind == "wall" || t->kind == "roof" || t->kind == "pillar");
    }
}

void BuildingMgr::DamagePiece(WLPiece& p, uint32 damage, Map* map)
{
    // WearNTear.ApplyDamage (IL 0–186) : santé -= dégâts ; <= 0 → destruction
    if (damage >= p.health)
    {
        std::string err;
        uint32 guid = p.guid;
        sLog.outString("Wowlheim: pièce %u détruite (support %.1f, PV %u)", guid, p.support, p.health);
        Remove(guid, map, err, true);     // invalide p ; remboursement par courrier au propriétaire (docs 4.2)
        ++m_lastCollapsed;
        return;
    }
    p.health -= damage;
    CharacterDatabase.PExecute("UPDATE wowlheim_piece SET health = %u WHERE guid = %u", p.health, p.guid);
}

float BuildingMgr::GetSupportOf(uint32 guid) const
{
    auto it = m_pieces.find(guid);
    return it == m_pieces.end() ? -1.0f : it->second.support;
}

// WearNTear::GetSupportColorValue (IL 0–51) : support >= maxSupport -> -1 (surbrillance bleu clair) ;
// sinon Clamp01((support - minSupport) / (maxSupport * 0,5 - minSupport)). Lu par `.build api pieceinfo`.
float BuildingMgr::SupportColorValue(WLPiece const& p) const
{
    WLPieceTemplate const* t = FindTemplate(p.pieceId);
    Material const& m = MaterialOf(t ? t->material : 0);
    if (!(p.support < m.maxSupport))
        return -1.0f;
    float den = m.maxSupport * 0.5f - m.minSupport;
    float v = den != 0.0f ? (p.support - m.minSupport) / den : 0.0f;
    return v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v);
}

// WearNTear::UpdateSupport (docs §1.2), résolu par relaxation jusqu'à convergence.
uint32 BuildingMgr::RecomputeSupport(Map* map)
{
    std::vector<WLPiece*> pieces;
    PieceGrid grid;
    for (auto& kv : m_pieces)
    {
        WLPiece& p = kv.second;
        if (p.map != map->GetId())
            continue;
        pieces.push_back(&p);
        grid[PieceCellOf(p.x, p.y)].push_back(&p);
    }

    // ancrage au terrain (IL 622–651) : support = max
    for (WLPiece* p : pieces)
    {
        WLPieceTemplate const* t = FindTemplate(p->pieceId);
        Material const& m = MaterialOf(t ? t->material : 0);
        float h = map->GetTerrain()->GetHeightStatic(p->x, p->y, p->z + 1.0f);   // statique : exclut les GameObjects dynamiques (nos pièces)
        float above = p->z - h;                       // adaptation : la base touche ou pénètre le terrain (collider Terrain, IL 622–651)
        p->grounded = above <= GROUND_TOLERANCE && above >= -GROUND_BURY_MAX;
        p->support = p->grounded ? m.maxSupport : 0.0f;
    }

    for (int iter = 0; iter < 64; ++iter)
    {
        bool changed = false;
        std::vector<float> next(pieces.size());
        for (size_t i = 0; i < pieces.size(); ++i)
        {
            WLPiece* p = pieces[i];
            WLPieceTemplate const* t = FindTemplate(p->pieceId);
            Material const& m = MaterialOf(t ? t->material : 0);
            if (p->grounded)
            {
                next[i] = m.maxSupport;
                continue;
            }

            float best = 0.0f;
            struct Pt { float x, y, v; };
            std::vector<Pt> pts;
            PieceCell c = PieceCellOf(p->x, p->y);
            for (int dx = -1; dx <= 1; ++dx)
                for (int dy = -1; dy <= 1; ++dy)
                {
                    auto it = grid.find(PieceCell{ c.x + dx, c.y + dy });
                    if (it == grid.end())
                        continue;
                    for (WLPiece* n : it->second)
                    {
                        if (n == p)
                            continue;
                        WLPieceTemplate const* nt = FindTemplate(n->pieceId);
                        if (!nt || !nt->supports || n->support <= 0.0f)
                            continue;
                        float vx = n->x - p->x, vy = n->y - p->y, vz = (n->z + nt->sz * 0.5f) - (p->z + (t ? t->sz : 1.0f) * 0.5f);
                        float dist = std::sqrt(vx * vx + vy * vy + vz * vz);
                        if (dist > NEIGHBOR_RADIUS)
                            continue;
                        float d = dist + COM_EPS;
                        float s = n->support;
                        // IL 825–842 : candidat horizontal
                        best = std::max(best, s - m.lossH * d * s);
                        // IL 877–981 : appui situé sous la pièce → perte interpolée selon l'inclinaison
                        if (vz < 0.05f && dist > 0.001f)
                        {
                            float dirz = vz / dist;                         // composante verticale normalisée
                            if (dirz < 0.0f)
                            {
                                float t01 = std::acos(1.0f - std::fabs(dirz)) / (PI_F / 2.0f);
                                float loss = m.lossH + (m.lossV - m.lossH) * std::min(1.0f, std::max(0.0f, t01));
                                best = std::max(best, s - loss * d * s);
                            }
                        }
                        // IL 983–1069 : point d'appui mémorisé avec la perte verticale (pour l'étape à deux appuis)
                        pts.push_back(Pt{ vx, vy, s - m.lossV * d * s });
                    }
                }

            // IL 1173–1366 : deux appuis opposés (angle horizontal >= 100°) → moyenne
            for (size_t a = 0; a + 1 < pts.size(); ++a)
                for (size_t b = a + 1; b < pts.size(); ++b)
                {
                    float avg = (pts[a].v + pts[b].v) * 0.5f;
                    if (avg <= best)
                        continue;
                    float la = std::sqrt(pts[a].x * pts[a].x + pts[a].y * pts[a].y);
                    float lb = std::sqrt(pts[b].x * pts[b].x + pts[b].y * pts[b].y);
                    if (la < 0.001f || lb < 0.001f)
                        continue;
                    float cosang = (pts[a].x * pts[b].x + pts[a].y * pts[b].y) / (la * lb);
                    float ang = std::acos(std::max(-1.0f, std::min(1.0f, cosang))) * 180.0f / PI_F;
                    if (ang >= 100.0f)
                        best = avg;
                }

            next[i] = std::min(best, m.maxSupport);      // IL 1371–1388
        }
        for (size_t i = 0; i < pieces.size(); ++i)
        {
            if (std::fabs(pieces[i]->support - next[i]) > 0.001f)
                changed = true;
            pieces[i]->support = next[i];
        }
        if (!changed)
            break;
    }

    // HaveSupport : support >= minSupport (IL 0–17)
    uint32 weak = 0;
    for (WLPiece* p : pieces)
    {
        WLPieceTemplate const* t = FindTemplate(p->pieceId);
        if (IsStructural(t) && p->support < MaterialOf(t->material).minSupport)
            ++weak;
    }
    return weak;
}

// WearNTear::UpdateWear — usure par la pluie (docs §2.1) : -5 % de PV max toutes les 60 s sous la pluie sans toit,
// jamais en dessous de 50 % de santé par la pluie seule.
void BuildingMgr::ApplyRainWear(Map* map, float dt)
{
    std::vector<WLPiece*> pieces;
    PieceGrid grid;
    for (auto& kv : m_pieces)
        if (kv.second.map == map->GetId())
        {
            pieces.push_back(&kv.second);
            grid[PieceCellOf(kv.second.x, kv.second.y)].push_back(&kv.second);
        }

    WeatherSystem* ws = map->GetWeatherSystem();
    if (!ws)
        return;
    std::unordered_map<uint32, bool> rainingByZone;

    std::vector<uint32> toDamage;
    for (WLPiece* p : pieces)
    {
        WLPieceTemplate const* t = FindTemplate(p->pieceId);
        if (!t || t->maxHealth == 0 || t->kind == "fire" || p->age < m_grace)
            continue;

        uint32 zone = map->GetTerrain()->GetZoneId(p->x, p->y, p->z);
        auto rit = rainingByZone.find(zone);
        if (rit == rainingByZone.end())
        {
            Weather* w = ws->FindOrCreateWeather(zone);
            rit = rainingByZone.emplace(zone, w && w->IsRaining()).first;
        }
        bool wet = rit->second;

        // UpdateCover : le toit n'est réévalué que quand il pleut, toutes les 4 s (IL 0–88) ; rayon vertical contre les boîtes des pièces
        if (wet)
        {
            p->roofCheckTimer += dt;
            if (p->roofCheckTimer >= 4.0f)
            {
                p->roofCheckTimer = 0.0f;
                p->covered = HaveRoofAbove(*p);
            }
        }

        bool rainWet = wet && !p->covered;
        float healthPct = float(p->health) / float(t->maxHealth);
        if (rainWet && healthPct > 0.5f)
        {
            p->wetSeconds += dt;
            if (p->wetSeconds >= m_rainPeriod)
            {
                p->wetSeconds = 0.0f;
                toDamage.push_back(p->guid);
            }
        }
        else
            p->wetSeconds = 0.0f;
    }

    for (uint32 guid : toDamage)
    {
        auto it = m_pieces.find(guid);
        if (it == m_pieces.end())
            continue;
        WLPieceTemplate const* t = FindTemplate(it->second.pieceId);
        if (t)
            DamagePiece(it->second, std::max<uint32>(1, t->maxHealth * 5 / 100), map);   // +5 % de PV max
    }
    if (!toDamage.empty())
        m_dirty = true;
}

void BuildingMgr::Update(uint32 diffMs)
{
    try
    {
        sTreeMgr.Update(diffMs);
        sSmelterMgr.Update(diffMs);
        sKnowledgeMgr.Update(diffMs);
        UpdateInner(diffMs);
    }
    catch (std::exception const& e)
    {
        sLog.outError("Wowlheim: exception dans la simulation : %s", e.what());
    }
}

void BuildingMgr::UpdateInner(uint32 diffMs)
{
    if (m_pieces.empty())
        return;
    m_simTimerMs += diffMs;
    if (m_simTimerMs < 1000)
        return;
    float dt = float(m_simTimerMs) / 1000.0f;
    m_simTimerMs = 0;
    bool dirty = m_dirty;
    m_dirty = false;
    for (auto& kv : m_pieces)
        kv.second.age += dt;

    std::vector<uint32> mapIds;
    for (auto const& kv : m_pieces)
        if (std::find(mapIds.begin(), mapIds.end(), kv.second.map) == mapIds.end())
            mapIds.push_back(kv.second.map);

    for (uint32 mapId : mapIds)
    {
        Map* map = sMapMgr.FindMap(mapId, 0);
        if (!map)
            continue;               // aucune simulation sur une carte sans joueur (comme Valheim hors zone chargée)

        ApplyRainWear(map, dt);

        // Effondrement : une vague par seconde. Les pièces sous minSupport reçoivent 100 % de dégâts (UpdateWear IL 301–328).
        if (dirty)
        {
            RecomputeSupport(map);
            std::vector<uint32> doomed;
            for (auto const& kv : m_pieces)
            {
                WLPiece const& p = kv.second;
                if (p.map != mapId)
                    continue;
                WLPieceTemplate const* t = FindTemplate(p.pieceId);
                if (IsStructural(t) && p.support < MaterialOf(t->material).minSupport)
                {
                    if (p.age >= m_grace)
                        doomed.push_back(p.guid);
                    else
                        m_dirty = true;      // en période de grâce : à réévaluer au prochain tick (Valheim : ShouldUpdate)
                }
            }
            for (uint32 guid : doomed)
            {
                auto it = m_pieces.find(guid);
                if (it != m_pieces.end())
                    DamagePiece(it->second, it->second.health, map);
            }
        }
    }
}
