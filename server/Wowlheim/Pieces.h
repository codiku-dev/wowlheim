// Wowlheim — pièces utilisables sans marteau, façon Valheim : coffres (Container), portes / portails / volets (Door), lits (Bed).
// Règles lues dans le CIL de Valheim (analysis/valheim/dis/Container._all.txt, Door._all.txt, Bed._all.txt) : docs/VALHEIM_RULES.md §14.
// Valeurs par pièce (m_width, m_height, m_privacy, m_checkGuardStone, m_canNotBeClosed, m_keyItem…) : table world `wowlheim_piece_use`,
// générée par tools/valheim/gen_server_sql.py (build_piece_use) depuis les prefabs. État par pièce posée (base characters) :
// `wowlheim_container` (contenu des coffres) et `wowlheim_piece_state` (porte ouverte / fermée, propriétaire du lit).
#ifndef WOWLHEIM_PIECES_H
#define WOWLHEIM_PIECES_H

#include "Common.h"

#include <map>
#include <mutex>
#include <string>
#include <vector>

class ChatHandler;
class Map;
class Player;
struct WLPiece;
struct WLBox;

struct WLPieceUseDef
{
    uint32 pieceId = 0;
    std::string kind;            // container | door | bed
    std::string name;            // Container.m_name / Door.m_name (traduits) ; lit : nom de la pièce
    uint32 width = 0;            // Container.m_width
    uint32 height = 0;           // Container.m_height
    uint8 privacy = 2;           // Container.m_privacy : 0 Private, 1 Group, 2 Public
    bool checkGuardStone = false;// m_checkGuardStone (PrivateArea.CheckAccess ; les balises ne sont pas simulées)
    bool canNotBeClosed = false; // Door.m_canNotBeClosed
    uint32 keyItem = 0;          // Door.m_keyItem (objet Wowlheim ; 0 = aucune clé)
    bool consumeKey = false;     // Door.m_consumeKey
};

struct WLChestSlot
{
    uint32 item = 0;
    uint32 count = 0;
    uint32 durability = 0;       // durabilité de l'objet (outils) ; 0 si l'objet n'en a pas
    int32 randomProp = 0;        // ITEM_FIELD_RANDOM_PROPERTIES_ID
    bool bound = false;          // objet lié (ITEM_DYNFLAG_BINDED) : il le reste à la sortie du coffre
};

struct WLChest
{
    std::vector<WLChestSlot> slots;   // m_width × m_height cases, de gauche à droite puis de haut en bas (Inventory de Valheim)
    uint32 openBy = 0;                // Container.m_inUse : personnage qui a le coffre ouvert (0 : libre)
};

struct WLPieceUseState
{
    int8 door = 0;               // ZDOVars.s_state : 0 fermée, 1 / -1 ouverte d'un côté ou de l'autre (Door.RPC_UseDoor)
    uint32 bedOwner = 0;         // ZDOVars.s_owner (guid du personnage)
    std::string bedOwnerName;    // ZDOVars.s_ownerName
};

class PieceUseMgr
{
    public:
        static PieceUseMgr& Instance();
        void Load();                                     // après le chargement des pièces (BuildingMgr::Load)

        WLPieceUseDef const* DefForPiece(uint32 pieceGuid) const;
        // Clic sur la pièce sans marteau (ou marteau en mode construction) : coffre, porte, lit. true si traité.
        bool OnUse(Player* player, uint32 pieceGuid);
        // Piece.CanBeRemoved -> Container.CanBeRemoved : coffre privé (m_privacy 0) non vide = démolition refusée
        bool CanBeRemoved(uint32 pieceGuid, std::string& err);
        // Démolition / effondrement : contenu du coffre rendu (Container.OnDestroyed -> DropAllItems), état effacé
        void OnPieceRemoved(uint32 pieceGuid, Player* to, uint32 ownerGuid);
        // Abri (Cover) : boîte du battant d'une porte ouverte (tourné de 90° autour de ses gonds) ; false si fermée / pas une porte
        bool OpenDoorBox(WLPiece const& p, WLBox& box) const;
        // .build api chest ... / .build api piece ...
        bool HandleChestCommand(ChatHandler* h, Player* player, char* args);
        bool HandlePieceCommand(ChatHandler* h, Player* player, char* args);

        static constexpr float INTERACT_DISTANCE = 5.0f; // Player.m_maxInteractDistance (5 m), mesuré au bord de la pièce

    private:
        std::map<uint32, WLPieceUseDef> m_defs;          // piece_id -> définition
        std::map<uint32, WLChest> m_chests;              // guid de la pièce -> contenu
        std::map<uint32, WLPieceUseState> m_states;      // guid de la pièce -> état (portes, lits)
        mutable std::recursive_mutex m_lock;

        WLChest& Chest(uint32 guid, WLPieceUseDef const& def);
        bool ChestAccess(Player* player, WLPiece const& piece, WLPieceUseDef const& def, std::string& err) const;
        bool ChestInUse(uint32 guid, Player* player);
        void SendChest(Player* player, uint32 guid, WLPieceUseDef const& def);
        void SaveChest(uint32 guid, Player* player);
        uint32 PutItem(Player* player, uint32 guid, WLPieceUseDef const& def, uint8 bag, uint8 slot, uint32 count, int32 toSlot, std::string& err);
        uint32 TakeSlot(Player* player, uint32 guid, uint32 slot, uint32 count, std::string& err);
        void SaveState(uint32 guid);

        void UseDoor(Player* player, WLPiece const& piece, WLPieceUseDef const& def);
        void ApplyDoorPose(Map* map, WLPiece const& piece, int8 state) const;
        void DoorPose(WLPiece const& piece, int8 state, float& x, float& y, float& o) const;
        void UseBed(Player* player, WLPiece const& piece, WLPieceUseDef const& def);
        void BedSpawnPoint(WLPiece const& piece, float& x, float& y, float& z) const;
};

#define sPieceUseMgr PieceUseMgr::Instance()

// Accroches (BuildingMgr / BuildPlacement / Geometry / BuildCommands)
void Wowlheim_PieceUseLoad();
bool Wowlheim_PieceUse(Player* player, uint32 pieceGuid);
bool Wowlheim_PieceCanBeRemoved(uint32 pieceGuid, std::string& err);
void Wowlheim_PieceUseRemoved(uint32 pieceGuid, Player* to, uint32 ownerGuid);
bool Wowlheim_OpenDoorBox(WLPiece const& p, WLBox& box);
bool Wowlheim_ChestCommand(ChatHandler* h, Player* player, char* args);
bool Wowlheim_PieceCommand(ChatHandler* h, Player* player, char* args);
// Refus des actions du marteau en combat (adaptation WoW : Valheim n'a pas cette règle). true = refusé, err rempli.
bool Wowlheim_RefuseInCombat(Player* player, std::string& err);

#endif
