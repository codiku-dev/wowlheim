// Wowlheim — gestion des pièces de construction (phases 2–4).
// Les pièces sont des GameObjects spawnés via la table `gameobject` du cœur (persistance native au redémarrage),
// avec des métadonnées dans `wowlheim_piece` (base characters) et un catalogue `wowlheim_piece_template` (base world).
#ifndef WOWLHEIM_BUILDINGMGR_H
#define WOWLHEIM_BUILDINGMGR_H

#include "Common.h"
#include "Entities/ObjectGuid.h"

#include <deque>
#include <map>
#include <set>
#include <string>
#include <vector>

class Map;
class Player;

struct WLItemCount
{
    uint32 itemId = 0;
    uint32 count = 0;
};

struct WLPieceTemplate
{
    uint32 id = 0;
    std::string name;
    uint32 goEntry = 0;
    uint8 material = 0;          // index MaterialType de Valheim (voir docs/VALHEIM_RULES.md §1.1)
    uint32 maxHealth = 0;
    bool supports = true;        // peut servir d'appui aux autres pièces
    bool requiresWorkbench = false;
    std::string kind;            // floor, wall, roof, pillar, workbench, fire
    float sx = 1, sy = 1, sz = 1; // boîte logique (m) : x/y locaux, z hauteur ; base au niveau de la position de la pièce
    std::string extStation;      // kind=extension : station visée (workbench, forge)
    float extDistance = 5.0f;    // StationExtension.m_maxStationDistance (docs/VALHEIM_RULES.md 8)
    bool extStack = false;       // StationExtension.m_stack
    std::vector<WLItemCount> costs;
    std::string prefab;          // prefab Valheim d'origine (modèle M2 du patch client)
    uint32 category = 0;         // Piece.m_category (0 divers, 1 fabrication, 2 construction, 3 construction lourde, 4 meuble)
    std::string station;         // Piece.m_craftingStation : '' (aucune), workbench, forge, stonecutter
    struct Snap { float x, y, z; };
    std::vector<Snap> snaps;     // points d'accroche Valheim ($hud_snappoint), repère de la pièce (base au sol, centrée)
};

// Marteau : pièce choisie dans le menu, rotation (pas de 22,5°) et mode (Valheim : construire / démolir / réparer)
struct WLHammerState
{
    uint32 pieceId = 0;
    int32 rot = 0;
    std::string mode = "build";
};

struct WLRecipe
{
    uint32 id = 0;
    std::string name;
    std::string station;         // 'workbench'
    uint32 outputItem = 0;
    uint32 outputCount = 1;
    uint32 minStationLevel = 1;  // Recipe.m_minStationLevel
    std::vector<WLItemCount> ingredients;
};

struct WLPiece
{
    uint32 guid = 0;             // guid statique du GameObject (table gameobject)
    uint32 pieceId = 0;
    uint32 ownerGuid = 0;        // guid du personnage
    uint32 map = 0;
    float x = 0, y = 0, z = 0, o = 0;
    uint32 health = 0;

    // état de simulation (non persisté, recalculé)
    float support = 0.0f;        // valeur de support Valheim (docs/VALHEIM_RULES.md 1.2)
    bool grounded = false;
    bool covered = false;        // toit au-dessus (docs 2.2)
    float wetSeconds = 0.0f;     // temps cumulé sous la pluie sans toit (docs 2.1)
    float roofCheckTimer = 0.0f;
    float age = 1.0e9f;          // secondes depuis la pose (les pièces rechargées sont « anciennes »)
};

struct WLBox                     // boîte orientée (rotation autour de z)
{
    float cx, cy, cz, hx, hy, hz, yaw;
};

class BuildingMgr
{
    public:
        static BuildingMgr& Instance();

        void Load();

        WLPieceTemplate const* FindTemplate(uint32 id) const;
        WLPieceTemplate const* FindTemplateByName(std::string const& name) const;
        std::map<uint32, WLPieceTemplate> const& Templates() const { return m_templates; }
        std::map<uint32, WLPiece> const& Pieces() const { return m_pieces; }
        std::map<uint32, WLRecipe> const& Recipes() const { return m_recipes; }
        WLRecipe const* FindRecipe(std::string const& token) const;

        uint32 CountByOwner(uint32 ownerGuid) const;

        // Mesure du tick (diff en ms) sur une fenêtre glissante de 600 mises à jour
        void RecordDiff(uint32 diff);
        uint32 AverageDiff() const;
        uint32 MaxDiff() const;

        // Retourne le guid du GameObject créé, 0 en cas d'échec (err rempli).
        uint32 Place(Map* map, WLPieceTemplate const& tpl, uint32 ownerGuid, float x, float y, float z, float o, std::string& err);
        // refund : les ressources de la pièce sont rendues (docs/VALHEIM_RULES.md 4.2) au joueur donné (sac, sinon courrier),
        // ou, si refundTo est nul et refundByMail vrai, par courrier au propriétaire (effondrement).
        bool Remove(uint32 guid, Map* map, std::string& err, bool refundByMail = false, Player* refundTo = nullptr);

        // Réparation (docs 1.6) : soin complet, sans coût de ressource
        bool Repair(uint32 guid, std::string& err);

        // ---- zones, coûts, stations (phase 4)
        bool IsForbiddenArea(Map* map, float x, float y, float z, std::string& why) const;
        bool HasItems(Player* player, std::vector<WLItemCount> const& items, std::string& missing) const;
        void ConsumeItems(Player* player, std::vector<WLItemCount> const& items) const;
        // Donne les objets au joueur (sac) ; ce qui ne rentre pas part par courrier. Renvoie le nombre d'objets envoyés par courrier.
        uint32 GiveItems(Player* player, uint32 receiverGuid, std::vector<WLItemCount> const& items, std::string const& mailSubject) const;
        bool IsNoCost(uint32 playerGuid) const { return m_noCost.count(playerGuid) != 0; }
        void SetNoCost(uint32 playerGuid, bool on) { if (on) m_noCost.insert(playerGuid); else m_noCost.erase(playerGuid); }
        // Établi : cherche une station du type donné à moins de `range` (distance horizontale, comme Valheim)
        WLPiece const* FindStationInRange(Map* map, float x, float y, std::string const& kind, float range) const;
        static constexpr float STATION_RANGE = 10.0f;     // CraftingStation.m_rangeBuild (valeur du constructeur, docs 3.4)
        // Abri (Cover.GetCoverForPoint) : 17 rayons, 30 m ; renvoie la fraction de rayons bloqués par des pièces
        void GetCover(uint32 mapId, float x, float y, float z, float& coverPct, bool& underRoof, uint32 ignoreGuid = 0) const;
        // CraftingStation.GetLevel : 1 + extensions comptées (distance 3D < m_maxStationDistance de l'extension, une par type sauf m_stack)
        uint32 StationLevel(WLPiece const& station) const;
        // CraftingStation.CheckUsable : toit au-dessus et couverture >= 0,7
        bool StationUsable(WLPiece const& station, float& coverPct) const;
        bool HaveRoofAbove(WLPiece const& piece) const;

        // ---- marteau (pose à la souris : sort WL_PLACE_SPELL lancé par le marteau, cible au sol)
        static constexpr uint32 WL_PLACE_SPELL = 40001;              // tools/valheim/gen_client_patch.py
        static constexpr float SNAP_DISTANCE = 0.5f;                 // Player.FindClosestSnapPoints (docs/VALHEIM_RULES.md 3.2 point 11)
        static constexpr float SNAP_SEARCH = 10.0f;                  // pièces voisines examinées (même source)
        WLHammerState& Hammer(uint32 playerGuid) { return m_hammer[playerGuid]; }
        // Contrôles de pose (zone, station, extension, ressources) + accroche + pose + consommation. msg : texte pour le joueur.
        uint32 TryPlace(Player* player, WLPieceTemplate const& tpl, float x, float y, float z, float o, bool snap, std::string& msg);
        // Accroche Valheim : déplace (x,y,z) pour superposer le point d'accroche le plus proche d'une pièce voisine
        bool Snap(uint32 mapId, WLPieceTemplate const& tpl, float& x, float& y, float& z, float o) const;
        bool CheckStation(Player* player, WLPieceTemplate const& tpl, std::string& err) const;
        // Clic droit sur une pièce (GameObject::Use) : démolir / réparer selon le mode du marteau ; true si traité
        bool OnPieceUse(Player* player, uint32 goGuid);
        // Spell::cast du sort de pose : pose la pièce choisie au point visé
        void PlaceFromSpell(Player* player, float x, float y, float z);
        bool IsHammerEquipped(Player* player) const;
        static constexpr uint32 HAMMER_ITEM = 9201100;

        // ---- récolte (nœuds + outils)
        bool CheckHarvest(Player* player, uint32 goEntry, std::string& err) const;
        void ConsumeToolDurability(Player* player) const;
        bool IsNodeEntry(uint32 entry) const { return m_nodes.find(entry) != m_nodes.end(); }
        // outil Wowlheim : genre (axe|pick), palier, dégâts de coupe/minage de Valheim (ItemDrop m_damages.m_chop / m_pickaxe)
        bool GetTool(uint32 itemId, std::string& kind, uint8& tier, float& damage) const;

        // Simulation Valheim : appelé à chaque World::Update (diff en ms)
        void Update(uint32 diffMs);
        void MarkDirty() { m_dirty = true; }
        // Recalcule le support de toutes les pièces d'une carte ; renvoie le nombre de pièces sous le minimum.
        uint32 RecomputeSupport(Map* map);
        float GetSupportOf(uint32 guid) const;
        float GraceSeconds() const { return m_grace; }
        void SetGraceSeconds(float seconds) { m_grace = seconds; }
        float RainPeriod() const { return m_rainPeriod; }
        void SetRainPeriod(float seconds) { m_rainPeriod = seconds; }
        uint32 LastCollapsed() const { return m_lastCollapsed; }

        static constexpr float MIN_SEPARATION = 0.5f;     // m, entre deux pièces identiques
        static constexpr uint32 MAX_PIECES_TOTAL = 20000;
        static constexpr uint32 MAX_PIECES_PER_OWNER = 2000;

        WLBox BoxOf(WLPiece const& p) const;

    private:
        std::map<uint32, WLPieceTemplate> m_templates;
        std::map<uint32, WLPiece> m_pieces;
        std::map<uint32, WLRecipe> m_recipes;
        std::map<uint32, WLHammerState> m_hammer;
        std::set<uint32> m_forbiddenAreas;
        struct NoBuildPoint { uint32 map; float x, y, radius; std::string name; };
        std::vector<NoBuildPoint> m_noBuild;       // villages et camps (wowlheim_no_build_point, généré depuis les aubergistes et maîtres de vol)
        std::set<uint32> m_noCost;
        struct Tool { std::string kind; uint8 tier; float damage; };
        struct Node { std::string toolKind; uint8 minTier; };
        std::map<uint32, Tool> m_tools;
        std::map<uint32, Node> m_nodes;
        std::deque<uint32> m_diffs;
        bool m_dirty = false;
        uint32 m_simTimerMs = 0;
        float m_rainPeriod = 60.0f;   // Valheim : 60 s (WearNTear.UpdateWear IL 266)
        uint32 m_lastCollapsed = 0;
        float m_grace = 0.0f;         // Valheim : OnPlaced met m_createTime à -1 → une pièce posée par un joueur est évaluée aussitôt ; la grâce de 30 s ne concerne que les pièces chargées/générées (docs/VALHEIM_RULES.md 1.3)
        void UpdateInner(uint32 diffMs);
        void ApplyRainWear(Map* map, float dt);
        void DamagePiece(WLPiece& p, uint32 damage, Map* map);
};

#define sBuildingMgr BuildingMgr::Instance()

// Accroches appelées depuis le cœur (Spell::cast, GameObject::Use)
void Wowlheim_PlaceFromSpell(Player* player, float x, float y, float z);
bool Wowlheim_OnPieceUse(Player* player, uint32 goGuid);

#endif
