// Wowlheim — stations de transformation façon Valheim (composant `Smelter` des prefabs `smelter`, `charcoal_kiln`,
// `blastfurnace` (haut fourneau) et `piece_spinningwheel` (rouet)).
// Règles lues dans le CIL de Valheim (docs/VALHEIM_RULES.md §9) : file de minerai (m_maxOre), combustible fractionnaire
// (m_maxFuel, m_fuelPerProduct), un produit toutes les m_secPerProduct secondes, pas d'une seconde, rattrapage plafonné
// à 3600 s, arrêt si la fumée est bloquée ou s'il manque un toit exigé (m_requiresRoof).
// Valeurs par station : table world `wowlheim_smelter` (+ `wowlheim_smelter_conversion`), générée par
// tools/valheim/gen_server_sql.py depuis les prefabs. État par pièce posée : table characters `wowlheim_smelter_state`.
#ifndef WOWLHEIM_SMELTER_H
#define WOWLHEIM_SMELTER_H

#include "Common.h"

#include <deque>
#include <map>
#include <mutex>
#include <string>
#include <vector>

class Player;
class ChatHandler;

struct WLSmelterDef
{
    std::string kind;            // = WLPieceTemplate::kind de la pièce (smelter | charcoal_kiln)
    std::string name;            // Smelter.m_name (traduit)
    uint32 fuelItem = 0;         // m_fuelItem (0 : pas de combustible, ex. four à charbon)
    uint32 maxOre = 0;           // m_maxOre
    uint32 maxFuel = 0;          // m_maxFuel
    uint32 fuelPerProduct = 0;   // m_fuelPerProduct
    float secPerProduct = 0;     // m_secPerProduct
    bool requiresRoof = false;   // m_requiresRoof
    bool spawnStack = false;     // m_spawnStack (sans effet ici : les produits restent dans la station)
    float smokeX = 0, smokeY = 0, smokeZ = 0; // SmokeSpawner (repère de la pièce posée, m)
    float smokeRadius = 0;       // SmokeSpawner.m_testRadius
    std::vector<std::pair<uint32, uint32>> conversion;   // m_conversion (m_from -> m_to), dans l'ordre de Valheim
    uint32 ConvertTo(uint32 from) const;
};

struct WLSmelterState
{
    std::deque<uint32> queue;              // minerai en file (Valheim : item0..itemN, on retire le premier)
    float fuel = 0;                        // ZDOVars.s_fuel (fractionnaire)
    float bake = 0;                        // ZDOVars.s_bakeTimer
    float acc = 0;                         // ZDOVars.s_accTime
    std::map<uint32, uint32> output;       // produits en attente de récupération (adaptation : Valheim les fait tomber au sol)
    bool dirty = false;
};

class SmelterMgr
{
    public:
        static SmelterMgr& Instance();
        void Load();                        // après BuildingMgr::Load (catalogue et pièces chargés)
        void Update(uint32 diffMs);         // depuis BuildingMgr::Update

        WLSmelterDef const* DefForPiece(uint32 pieceGuid) const;
        // Clic sur la station sans marteau : récupère les produits, ajoute minerai puis combustible depuis le sac.
        bool OnUse(Player* player, uint32 pieceGuid);
        // Démolition / effondrement : contenu rendu (Valheim : Smelter.DropAllItems → au sol)
        void OnPieceRemoved(uint32 pieceGuid, Player* to, uint32 ownerGuid);
        // .build api smelter <status|add|take> ...
        bool HandleCommand(ChatHandler* handler, Player* player, char* args, bool api);

    private:
        std::map<std::string, WLSmelterDef> m_defs;
        std::map<uint32, WLSmelterState> m_states;   // guid de la pièce -> état
        std::recursive_mutex m_lock;
        uint32 m_tickMs = 0;
        uint32 m_saveMs = 0;

        WLSmelterState& State(uint32 guid) { return m_states[guid]; }
        void Step(uint32 guid, WLSmelterDef const& def, WLSmelterState& st, float seconds);
        // Smelter.IsActive / UpdateSmelter : raison d'arrêt ("" si actif)
        std::string Blocked(uint32 guid, WLSmelterDef const& def, WLSmelterState const& st) const;
        bool SmokeBlocked(uint32 guid, WLSmelterDef const& def) const;
        bool RoofOk(uint32 guid, WLSmelterDef const& def) const;
        // Smelter.OnAddOre / OnAddFuel (une unité par appel, comme une pression de l'interrupteur) ; msg : texte de Valheim
        bool AddOre(Player* player, uint32 guid, WLSmelterDef const& def, uint32 itemId, std::string& msg);
        bool AddFuel(Player* player, uint32 guid, WLSmelterDef const& def, std::string& msg);
        uint32 Take(Player* player, uint32 guid, std::string& msg);
        std::string StatusLine(uint32 guid, WLSmelterDef const& def, WLSmelterState const& st) const;
        std::string StatusText(uint32 guid, WLSmelterDef const& def, WLSmelterState const& st) const;
        uint32 Nearest(Player* player, float range) const;
        void Save(uint32 guid, WLSmelterState& st);
};

#define sSmelterMgr SmelterMgr::Instance()

// .build api smelter ... (BuildCommands.cpp, HandleBuildApiCommand)
bool Wowlheim_SmelterCommand(ChatHandler* h, Player* player, char* args, bool api);

#endif
