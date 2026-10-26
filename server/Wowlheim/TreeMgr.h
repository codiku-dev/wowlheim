// Wowlheim — abattage façon Valheim : les arbres et les bûches sont des créatures (modèles Valheim) que l'on frappe
// à la hache en combat de mêlée normal. Règles reprises de Valheim (prefabs TreeBase/TreeLog, Skills.GetRandomSkillRange) :
// seuls les dégâts de coupe (chop) de l'outil comptent, palier d'outil minimal, arbre -> bûche -> demi-bûches -> bois.
#ifndef WOWLHEIM_TREEMGR_H
#define WOWLHEIM_TREEMGR_H

#include "Common.h"
#include "Entities/ObjectGuid.h"

#include <map>
#include <mutex>
#include <string>
#include <vector>

class Unit;
class Player;
class Creature;
struct CalcDamageInfo;

struct WLTreeInfo
{
    uint32 entry = 0;
    std::string kind;        // tree | log | half | rock
    std::string tool = "axe"; // outil qui l'entame : axe (m_chop) | pick (m_pickaxe) — m_damageModifiers de Valheim
    uint32 rollsMin = 0, rollsMax = 0;   // DropTable de Valheim : m_dropMin..m_dropMax tirages pondérés dans `drops`
    struct Drop { uint32 item; float weight; uint32 stackMin, stackMax; };
    std::vector<Drop> drops;
    uint8 minTier = 0;       // TreeBase/TreeLog.m_minToolTier
    uint32 nextEntry = 0;    // tree -> bûche, bûche -> demi-bûche (m_logPrefab / m_subLogPrefab)
    uint32 nextCount = 0;    // nombre de bûches créées
    float nextSpacing = 0;   // décalage le long de l'axe (m) entre les demi-bûches
    float nextDistance = 0;  // distance au point de chute (m) du centre de la bûche
    uint32 stumpGo = 0;      // souche (gameobject_template) laissée par un arbre
    uint32 stumpSeconds = 0; // durée de vie de la souche (= délai de repousse)
    uint32 dropItem = 0;     // butin direct de l'arbre (TreeBase.m_dropWhenDestroyed, ex. résine)
    uint32 dropMin = 0, dropMax = 0;
    float dropChance = 0;
};

class TreeMgr
{
    public:
        static TreeMgr& Instance();
        void Load();

        WLTreeInfo const* Find(uint32 entry) const;
        bool IsTree(Unit const* u) const;

        // Unit::AttackerStateUpdate, après CalculateMeleeDamage : remplace les dégâts par la coupe Valheim
        void AdjustMelee(Unit* attacker, Unit* victim, CalcDamageInfo* info);
        // Unit::DealDamage : un arbre ne prend que les coups de mêlée (Valheim : m_damageModifiers « Immune » sauf chop)
        bool AllowDamage(Unit* dealer, Unit* victim, bool melee) const;
        // Unit::Kill : l'arbre tombe dans le sens opposé au bûcheron, puis la suite (bûche, souche) apparaît
        void OnKill(Unit* killer, Unit* victim);
        // World::Update (thread du monde, cartes à l'arrêt)
        void Update(uint32 diffMs);

    private:
        struct Pending
        {
            uint32 mapId, instanceId;
            ObjectGuid victim;
            ObjectGuid killer;
            uint32 entry;
            float x, y, z, angle;
            int32 delayMs;
        };
        std::map<uint32, WLTreeInfo> m_trees;
        std::vector<Pending> m_pending;
        mutable std::mutex m_lock;
        std::map<uint32, uint32> m_lastWarn;          // joueur -> horodatage du dernier message (anti-spam)
        void Warn(Player* p, char const* text);
};

#define sTreeMgr TreeMgr::Instance()

// Accroches appelées depuis le cœur (une ligne chacune dans Unit.cpp)
void Wowlheim_AdjustMelee(Unit* attacker, Unit* victim, CalcDamageInfo* info);
bool Wowlheim_AllowDamage(Unit* dealer, Unit* victim, bool melee);
void Wowlheim_OnKill(Unit* killer, Unit* victim);

#endif
