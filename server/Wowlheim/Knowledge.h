// Wowlheim — connaissances du joueur façon Valheim (docs/VALHEIM_RULES.md §10) et réparation des objets à la station (§11).
//  - matériaux connus : Player.m_knownMaterial (objet Wowlheim déjà possédé une fois, Player.AddKnownItem via OnInventoryChanged)
//  - stations connues : Player.m_knownStations (type -> plus haut niveau vu à moins de 4 m, CraftingStation.UpdateKnownStationsInRange)
//  - pièces / recettes connues : Player.HaveRequirements(piece, RequirementMode.IsKnown) / HaveRequirements(recipe, discover=true)
// Persistance : base characters, wowlheim_known_item / wowlheim_known_station (server/sql/characters/003_wowlheim_known.sql).
#ifndef WOWLHEIM_KNOWLEDGE_H
#define WOWLHEIM_KNOWLEDGE_H

#include "Common.h"

#include <map>
#include <mutex>
#include <set>
#include <string>
#include <vector>

class ChatHandler;
class Player;
struct WLPiece;
struct WLPieceTemplate;
struct WLRecipe;

class KnowledgeMgr
{
    public:
        static KnowledgeMgr& Instance();

        // Appelé par BuildingMgr::Update : toutes les secondes (Player.UpdateStations : m_stationDiscoverTimer > 1 s),
        // balayage du sac de chaque joueur connecté et découverte des stations à portée.
        void Update(uint32 diffMs);

        // Objets Wowlheim du sac/équipement -> connus. Renvoie le nombre de nouveaux objets.
        uint32 ScanInventory(Player* player);
        // Stations à moins de DISCOVER_RANGE -> connues (au niveau actuel). Renvoie le nombre de nouveautés.
        uint32 DiscoverStations(Player* player);
        // Le joueur pose / utilise une station : connue au niveau actuel (Player.AddKnownStation)
        void LearnStation(Player* player, WLPiece const& station);

        bool IsCraftingStationKind(std::string const& kind) const;
        bool PieceKnown(Player* player, WLPieceTemplate const& tpl);
        bool RecipeKnown(Player* player, WLRecipe const& recipe);

        // .build api known : K|item:..., KS|kind:niveau,..., KP|id,..., KR|id,...
        void SendKnown(ChatHandler* h, Player* player);

        static constexpr float DISCOVER_RANGE = 4.0f;           // CraftingStation.m_discoverRange (constructeur et prefabs : 4)
        static constexpr uint32 ITEM_MIN = 9200000, ITEM_MAX = 9299999;

    private:
        struct Known
        {
            bool loaded = false;
            std::set<uint32> items;
            std::map<std::string, uint32> stations;             // kind -> niveau
        };
        Known& Get(uint32 playerGuid);
        bool LearnItem(Player* player, Known& k, uint32 itemId);
        bool LearnStationLevel(Player* player, Known& k, std::string const& kind, uint32 level);

        std::map<uint32, Known> m_players;
        std::recursive_mutex m_lock;
        uint32 m_timer = 0;
};

#define sKnowledgeMgr KnowledgeMgr::Instance()

// Commandes .build api (BuildCommands.cpp)
bool Wowlheim_KnownCommand(ChatHandler* h, Player* player);
bool Wowlheim_RepairItemsCommand(ChatHandler* h, Player* player, char* args);
bool Wowlheim_RepairableCommand(ChatHandler* h, Player* player, char* args);
bool Wowlheim_WearCommand(ChatHandler* h, Player* player, char* args);
// Lignes S|guid|utilisable|couverture%|niveau|type des stations à portée (même format que .build api station)
void Wowlheim_SendStationLines(ChatHandler* h, Player* player);

#endif
