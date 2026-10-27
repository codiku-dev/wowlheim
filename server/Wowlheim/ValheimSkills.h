// Wowlheim — compétences et endurance « outils » façon Valheim (docs/VALHEIM_SKILLS.md).
//  - compétences par personnage (Skills / Skills.Skill) : Couper du bois (13), Pioches (12), Fabrication (107), Haches (7) ;
//    montée Skill.Raise (accumulateur, palier 0,5·(niveau+1)^1,5 + 0,5), facteur floor(niveau)/100, perte de 5 % à la mort
//    (HardDeath : plus de 600 s depuis la mort précédente).
//  - endurance séparée de WoW (ni mana, ni rage, ni énergie ; jamais consommée par la course) : max 50, régénération
//    Valheim (6/s + (1 − s/max)·6/s, 1 s après chaque dépense), consommée par les coups de hache / pioche Valheim et par le
//    marteau (pose, démolition, réparation).
// Persistance : base characters, wowlheim_skill (server/sql/characters/004_wowlheim_skill.sql). Endurance non persistée.
// Canal de l'addon : EN|cur×10|max×10|délai_ms|clignotement ; SK|id|niveau|pourcentage ; SKU|id|niveau ; SKL|pourcentage.
#ifndef WOWLHEIM_VALHEIMSKILLS_H
#define WOWLHEIM_VALHEIMSKILLS_H

#include "Common.h"

#include <map>
#include <mutex>
#include <set>
#include <string>

class ChatHandler;
class Item;
class Player;

enum WLSkillType : uint16
{
    WL_SKILL_AXES        = 7,      // Skills.SkillType.Axes
    WL_SKILL_PICKAXES    = 12,     // Skills.SkillType.Pickaxes
    WL_SKILL_WOODCUTTING = 13,     // Skills.SkillType.WoodCutting
    WL_SKILL_CRAFTING    = 107,    // Skills.SkillType.Crafting (PieceTable.m_skill du marteau)
};

class WLSkillMgr
{
    public:
        static WLSkillMgr& Instance();

        // ---- compétences
        float GetLevel(Player* player, uint16 skill);             // Skills.GetSkillLevel : niveau entier (floor)
        float GetFactor(Player* player, uint16 skill);            // Skills.GetSkillFactor : Clamp01(niveau / 100)
        void Raise(Player* player, uint16 skill, float amount);   // Player.RaiseSkill -> Skill.Raise (× m_increseStep)
        void SetLevel(Player* player, uint16 skill, float level); // commande de test (MJ)
        void OnDeath(Player* player);                             // Player.OnDeath -> HardDeath ? Skills.OnDeath
        // Valheim : Player.m_buildRemoveDebt (+1 par démolition, plafond 20) ; une pose paie la dette avant de monter la compétence
        void OnBuildRemove(Player* player);
        void OnBuildPlace(Player* player);

        // ---- endurance
        float GetStamina(Player* player);
        float GetMaxStamina() const { return BASE_STAMINA; }
        bool HaveStamina(Player* player, float amount);           // Player.HaveStamina : stamina > amount
        void UseStamina(Player* player, float amount);            // Player.UseStamina : relance le délai de régénération
        void SetStamina(Player* player, float value);             // commande de test (MJ)
        void SendStamina(Player* player, bool flash);

        // ---- outils
        static float ToolStamina(uint32 itemEntry);               // Attack.m_attackStamina du prefab (0 : pas un outil Valheim)
        // Attack.GetAttackStamina : s − 0,33·s·facteur(compétence de l'arme)
        float AttackStamina(Player* player, uint32 itemEntry, uint16 weaponSkill);
        // Player.GetBuildStamina : s − 0,5·s·facteur(Fabrication)
        float BuildStamina(Player* player);
        // Usure du marteau par pose : Player.GetPlaceDurability = 1 − 0,5·facteur(Fabrication) (fraction accumulée)
        void WearHammer(Player* player, Item* hammer);
        // Outil Valheim cassé (durabilité 0) : Valheim refuse de l'équiper (Humanoid.EquipItem IL 79–106)
        static bool IsBroken(Item* item);

        // ---- canal de l'addon
        void SendSkills(ChatHandler* h, Player* player);          // SK|... pour chaque compétence suivie + EN|...

        // Écriture périodique des accumulateurs modifiés (appelé par TreeMgr::Update, thread du monde)
        void Update(uint32 diffMs);

        static constexpr float BASE_STAMINA = 50.0f;              // prefab Player : m_baseStamina
        static constexpr float STAMINA_REGEN = 6.0f;              // m_staminaRegen
        static constexpr float STAMINA_REGEN_TIME_MULT = 1.0f;    // m_staminaRegenTimeMultiplier
        static constexpr float STAMINA_REGEN_DELAY = 1.0f;        // m_staminaRegenDelay (s)
        static constexpr float HARD_DEATH_COOLDOWN = 600.0f;      // m_hardDeathCooldown (s)
        static constexpr float DEATH_LOWER_FACTOR = 0.05f;        // Skills.m_DeathLowerFactor
        static constexpr int32 MAX_REMOVE_DEBT = 20;              // Player.m_buildRemoveDebt (plafond)

    private:
        struct SkillData
        {
            float level = 0.0f;
            float acc = 0.0f;
        };
        struct PlayerData
        {
            bool loaded = false;
            std::map<uint16, SkillData> skills;
            std::set<uint16> dirty;
            float stamina = BASE_STAMINA;       // valeur au moment de la dernière dépense
            uint32 useMs = 0;                   // getMSTime de la dernière dépense (0 : jamais)
            uint32 deathMs = 0;                 // getMSTime de la mort précédente (0 : aucune depuis le démarrage)
            int32 removeDebt = 0;
            float hammerWear = 0.0f;            // usure fractionnaire du marteau en attente
        };
        PlayerData& Get(uint32 guid);
        float StaminaNow(PlayerData const& d, uint32 now) const;
        static float IncreaseStep(uint16 skill);
        static float NextLevelRequirement(float level);
        void Save(uint32 guid, uint16 skill, SkillData const& s);
        void SkillLine(Player* player, uint16 skill, SkillData const& s);

        std::map<uint32, PlayerData> m_players;
        std::recursive_mutex m_lock;
        uint32 m_saveTimer = 0;
};

#define sWLSkillMgr WLSkillMgr::Instance()

// .build api skills [stamina <v> | set <id> <niveau>] : lignes SK| + EN| (sous-commandes de test réservées aux MJ)
bool Wowlheim_SkillsCommand(ChatHandler* h, Player* player, char* args);

#endif
