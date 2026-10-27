#include "Wowlheim/TreeMgr.h"
#include "Wowlheim/BuildingMgr.h"
#include "Wowlheim/ValheimSkills.h"

#include "Database/DatabaseEnv.h"
#include "Entities/Creature.h"
#include "Entities/GameObject.h"
#include "Entities/Item.h"
#include "Entities/Player.h"
#include "Entities/Unit.h"
#include "Log/Log.h"
#include "Maps/Map.h"
#include "Maps/MapManager.h"
#include "Server/WorldSession.h"
#include "Util/Util.h"

#include <cmath>

TreeMgr& TreeMgr::Instance()
{
    static TreeMgr instance;
    return instance;
}

void TreeMgr::Load()
{
    m_trees.clear();
    auto r = WorldDatabase.Query("SELECT entry, kind, min_tier, next_entry, next_count, next_spacing, next_distance, stump_go, stump_seconds, "
                                 "drop_item, drop_min, drop_max, drop_chance, tool, rolls_min, rolls_max FROM wowlheim_tree");
    if (r)
    {
        do
        {
            Field* f = r->Fetch();
            WLTreeInfo t;
            t.entry = f[0].GetUInt32();
            t.kind = f[1].GetCppString();
            t.minTier = uint8(f[2].GetUInt32());
            t.nextEntry = f[3].GetUInt32();
            t.nextCount = f[4].GetUInt32();
            t.nextSpacing = f[5].GetFloat();
            t.nextDistance = f[6].GetFloat();
            t.stumpGo = f[7].GetUInt32();
            t.stumpSeconds = f[8].GetUInt32();
            t.dropItem = f[9].GetUInt32();
            t.dropMin = f[10].GetUInt32();
            t.dropMax = f[11].GetUInt32();
            t.dropChance = f[12].GetFloat();
            t.tool = f[13].GetCppString();
            t.rollsMin = f[14].GetUInt32();
            t.rollsMax = f[15].GetUInt32();
            m_trees[t.entry] = t;
        } while (r->NextRow());
    }
    if (auto d = WorldDatabase.Query("SELECT entry, item, weight, stack_min, stack_max FROM wowlheim_tree_drop"))
    {
        do
        {
            Field* f = d->Fetch();
            auto it = m_trees.find(f[0].GetUInt32());
            if (it != m_trees.end())
                it->second.drops.push_back(WLTreeInfo::Drop{ f[1].GetUInt32(), f[2].GetFloat(), f[3].GetUInt32(), f[4].GetUInt32() });
        } while (d->NextRow());
    }
    sLog.outString(">> Wowlheim: %u arbres, bûches et rochers à abattre ou miner", uint32(m_trees.size()));
}

WLTreeInfo const* TreeMgr::Find(uint32 entry) const
{
    auto it = m_trees.find(entry);
    return it == m_trees.end() ? nullptr : &it->second;
}

bool TreeMgr::IsTree(Unit const* u) const
{
    return u && u->GetTypeId() == TYPEID_UNIT && Find(u->GetEntry()) != nullptr;
}

void TreeMgr::Warn(Player* p, char const* text)
{
    uint32 now = WorldTimer::getMSTime();
    uint32& last = m_lastWarn[p->GetObjectGuid().GetCounter()];
    if (last && WorldTimer::getMSTimeDiff(last, now) < 2500)
        return;
    last = now;
    p->GetSession()->SendNotification("%s", text);
}

namespace
{
    // Coup refusé (Valheim : Attack.Start renvoie false, aucune attaque) : le coup automatique de WoW devient un raté
    void MakeMiss(CalcDamageInfo* info)
    {
        for (auto& sub : info->subDamage)
        {
            sub.damage = 0;
            sub.absorb = 0;
            sub.resist = 0;
        }
        info->totalDamage = 0;
        info->cleanDamage = 0;
        info->blocked_amount = 0;
        info->absorb = 0;
        info->hitOutCome = MELEE_HIT_MISS;
        info->TargetState = VICTIMSTATE_UNAFFECTED;
        info->HitInfo = HITINFO_MISS;
        info->procEx = PROC_EX_MISS;
    }
}

void TreeMgr::AdjustMelee(Unit* attacker, Unit* victim, CalcDamageInfo* info)
{
    if (!attacker || !victim || info->hitOutCome == MELEE_HIT_EVADE)
        return;
    WLTreeInfo const* tree = victim->GetTypeId() == TYPEID_UNIT ? Find(victim->GetEntry()) : nullptr;
    Player* p = attacker->GetTypeId() == TYPEID_PLAYER ? static_cast<Player*>(attacker) : nullptr;

    // Outil Valheim en main droite (hache / pioche) : endurance « outils » (docs/VALHEIM_SKILLS.md §2.4)
    Item* main = p && info->attackType == BASE_ATTACK ? p->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_MAINHAND) : nullptr;
    std::string kind;
    uint8 tier = 0;
    float chop = 0.0f;
    bool isTool = main && sBuildingMgr.GetTool(main->GetEntry(), kind, tier, chop) && (kind == "axe" || kind == "pick");
    bool broken = isTool && WLSkillMgr::IsBroken(main);          // Humanoid.EquipItem : un outil cassé ne s'équipe pas
    uint16 weaponSkill = kind == "axe" ? WL_SKILL_AXES : WL_SKILL_PICKAXES;   // ItemData.m_shared.m_skillType
    float cost = isTool && !broken ? sWLSkillMgr.AttackStamina(p, main->GetEntry(), weaponSkill) : 0.0f;

    if (!tree)
    {
        // Combat avec un outil Valheim : chaque coup coûte de l'endurance (Attack.Update IL 92–120), refusé si elle manque
        // (Attack.Start IL 564–613) ; une hache qui touche une créature monte Haches de 1,5 (DoMeleeAttack IL 3274–3343)
        if (!p || !isTool || broken)
            return;
        if (!sWLSkillMgr.HaveStamina(p, cost + 0.1f))
        {
            MakeMiss(info);
            Warn(p, "Vous êtes trop fatigué.");
            sWLSkillMgr.SendStamina(p, true);
            return;
        }
        sWLSkillMgr.UseStamina(p, cost);
        bool hit = info->hitOutCome != MELEE_HIT_MISS && info->hitOutCome != MELEE_HIT_DODGE && info->hitOutCome != MELEE_HIT_PARRY;
        if (hit)
        {
            if (kind == "axe")
                sWLSkillMgr.Raise(p, WL_SKILL_AXES, 1.5f);      // m_raiseSkillAmount (1) × 1,5 : un Character a été touché
            sBuildingMgr.ConsumeToolDurability(p);              // usure : m_useDurabilityDrain (1) si un objet est touché
        }
        sWLSkillMgr.SendStamina(p, false);
        return;
    }

    uint32 damage = 0;
    if (p)
    {
        bool pick = tree->tool == "pick";
        if (!isTool)
            Warn(p, pick ? "Il faut une pioche pour miner cette roche." : "Il faut une hache pour abattre un arbre.");
        else if (broken)
            Warn(p, "Votre outil est cassé : faites-le réparer à une station.");
        else if (!sWLSkillMgr.HaveStamina(p, cost + 0.1f))
        {
            // Valheim : pas d'attaque, la barre d'endurance clignote (Hud.StaminaBarEmptyFlash)
            Warn(p, "Vous êtes trop fatigué.");
            sWLSkillMgr.SendStamina(p, true);
        }
        else
        {
            sWLSkillMgr.UseStamina(p, cost);
            if (kind != tree->tool)
                // mauvais outil : le coup a lieu (endurance), mais ni gain ni usure (DestructibleType & m_skillHitType = 0)
                Warn(p, pick ? "Il faut une pioche pour miner cette roche." : "Il faut une hache pour abattre un arbre.");
            else
            {
                // hache sur un arbre : m_specialHitSkill = Couper du bois ; pioche sur la roche : Pioches. Gain et usure même
                // si le palier est trop faible (l'ensemble des compétences est rempli avant IDestructible.Damage).
                uint16 skill = pick ? WL_SKILL_PICKAXES : WL_SKILL_WOODCUTTING;
                sWLSkillMgr.Raise(p, skill, 1.0f);
                sBuildingMgr.ConsumeToolDurability(p);
                if (tier < tree->minTier)
                    Warn(p, pick ? "Trop dur : il faut une meilleure pioche." : "Trop dur : il faut une meilleure hache.");   // « $msg_toohard »
                else
                {
                    // Skills.GetRandomSkillRange (IL 0-53) : centre = Lerp(0,4 ; 1 ; compétence), plage ±0,15 bornée à [0,1].
                    float const f = sWLSkillMgr.GetFactor(p, skill);
                    float mid = 0.4f + 0.6f * f;
                    float lo = std::max(0.0f, mid - 0.15f), hi = std::min(1.0f, mid + 0.15f);
                    damage = std::max<uint32>(1, uint32(std::lround(chop * frand(lo, hi))));
                }
            }
            sWLSkillMgr.SendStamina(p, false);
        }
    }

    for (auto& sub : info->subDamage)
    {
        sub.damage = 0;
        sub.absorb = 0;
        sub.resist = 0;
    }
    info->subDamage[0].damage = damage;
    info->totalDamage = damage;
    info->cleanDamage = damage;
    info->blocked_amount = 0;
    info->absorb = 0;
    info->hitOutCome = MELEE_HIT_NORMAL;
    info->TargetState = damage ? VICTIMSTATE_NORMAL : VICTIMSTATE_IS_IMMUNE;
    info->HitInfo = HITINFO_NORMALSWING2;
    info->procEx = damage ? PROC_EX_NORMAL_HIT : PROC_EX_IMMUNE;
}

bool TreeMgr::AllowDamage(Unit* /*dealer*/, Unit* victim, bool melee) const
{
    return melee || !IsTree(victim);
}

void TreeMgr::OnKill(Unit* killer, Unit* victim)
{
    if (victim && victim->GetTypeId() == TYPEID_PLAYER)
        sWLSkillMgr.OnDeath(static_cast<Player*>(victim));    // Player.OnDeath : perte de 5 % des compétences (HardDeath)
    WLTreeInfo const* tree = victim && victim->GetTypeId() == TYPEID_UNIT ? Find(victim->GetEntry()) : nullptr;
    if (!tree || !tree->nextEntry && !tree->dropItem && !tree->stumpGo && tree->drops.empty())
        return;
    float angle = victim->GetOrientation();
    if (killer && tree->kind == "tree")
    {
        // l'arbre tombe à l'opposé du bûcheron (Valheim : impulsion du coup sur la bûche)
        angle = std::atan2(victim->GetPositionY() - killer->GetPositionY(), victim->GetPositionX() - killer->GetPositionX());
        if (angle < 0)
            angle += 2.0f * float(M_PI);
        victim->SetFacingTo(angle);
    }
    Pending p;
    p.mapId = victim->GetMapId();
    p.instanceId = victim->GetInstanceId();
    p.victim = victim->GetObjectGuid();
    p.killer = killer ? killer->GetObjectGuid() : ObjectGuid();
    p.entry = tree->entry;
    p.x = victim->GetPositionX(); p.y = victim->GetPositionY(); p.z = victim->GetPositionZ();
    p.angle = angle;
    p.delayMs = tree->kind == "tree" ? 2200 : tree->kind == "rock" ? 700 : 350;   // laisser l'animation (chute, éclatement) se jouer
    std::lock_guard<std::mutex> guard(m_lock);
    m_pending.push_back(p);
}

void TreeMgr::Update(uint32 diffMs)
{
    sWLSkillMgr.Update(diffMs);                                // écriture périodique des accumulateurs de compétence
    std::vector<Pending> due;
    {
        std::lock_guard<std::mutex> guard(m_lock);
        for (auto it = m_pending.begin(); it != m_pending.end();)
        {
            it->delayMs -= int32(diffMs);
            if (it->delayMs <= 0)
            {
                due.push_back(*it);
                it = m_pending.erase(it);
            }
            else
                ++it;
        }
    }
    for (Pending const& p : due)
    {
        WLTreeInfo const* tree = Find(p.entry);
        Map* map = sMapMgr.FindMap(p.mapId, p.instanceId);
        Creature* corpse = map ? map->GetCreature(p.victim) : nullptr;
        if (!tree || !corpse)
            continue;
        float dx = std::cos(p.angle), dy = std::sin(p.angle);

        // bûches : le long de l'axe de chute (arbre) ou de part et d'autre du centre (bûche -> demi-bûches)
        for (uint32 i = 0; i < tree->nextCount; ++i)
        {
            float along = tree->nextDistance;
            if (tree->nextCount > 1)
                along += (float(i) - 0.5f * float(tree->nextCount - 1)) * tree->nextSpacing;
            float x = p.x + dx * along, y = p.y + dy * along;
            float z = map->GetTerrain()->GetHeightStatic(x, y, p.z + 3.0f);
            if (z < INVALID_HEIGHT + 1.0f)
                z = p.z;
            corpse->SummonCreature(tree->nextEntry, x, y, z, p.angle, TEMPSPAWN_TIMED_OR_DEAD_DESPAWN, 5 * MINUTE * IN_MILLISECONDS);
        }

        // souche (Valheim : m_stubPrefab), jusqu'à la repousse de l'arbre
        if (tree->stumpGo)
        {
            GameObject* stump = new GameObject;
            uint32 lowGuid = map->GenerateLocalLowGuid(HIGHGUID_GAMEOBJECT);
            if (stump->Create(lowGuid, lowGuid, tree->stumpGo, map, p.x, p.y, p.z, p.angle))
            {
                // objet temporaire : visible tout de suite, supprimé à l'échéance (GameObject::Update, branche « despawn timer »).
                // Sans SetSpellId (m_spawnedByDefault = false), IsSpawned() est faux tant que le délai court : la souche
                // restait invisible pendant stumpSeconds puis apparaissait pour de bon (GameObject.h IsSpawned).
                stump->SetSpellId(0);
                stump->SetRespawnTime(tree->stumpSeconds);
                map->Add(stump);
            }
            else
                delete stump;
        }

        // butin propre à l'arbre (résine, etc.) : directement au bûcheron
        if (tree->dropItem && rand_chance_f() < tree->dropChance * 100.0f)
            if (Player* killer = map->GetPlayer(p.killer))
            {
                uint32 n = urand(tree->dropMin, std::max(tree->dropMin, tree->dropMax));
                if (n)
                    sBuildingMgr.GiveItems(killer, killer->GetObjectGuid().GetCounter(), { WLItemCount{ tree->dropItem, n } }, "Abattage");
            }

        // DropTable de Valheim (rochers, filons) : tirages pondérés, ramassés par le mineur
        if (!tree->drops.empty())
            if (Player* killer = map->GetPlayer(p.killer))
            {
                float total = 0;
                for (auto const& d : tree->drops)
                    total += d.weight;
                std::map<uint32, uint32> got;
                uint32 rolls = urand(tree->rollsMin, std::max(tree->rollsMin, tree->rollsMax));
                for (uint32 i = 0; i < rolls && total > 0; ++i)
                {
                    float r = frand(0.0f, total);
                    for (auto const& d : tree->drops)
                    {
                        if ((r -= d.weight) > 0)
                            continue;
                        got[d.item] += urand(d.stackMin, std::max(d.stackMin, d.stackMax));
                        break;
                    }
                }
                std::vector<WLItemCount> items;
                for (auto const& g : got)
                    items.push_back(WLItemCount{ g.first, g.second });
                if (!items.empty())
                    sBuildingMgr.GiveItems(killer, killer->GetObjectGuid().GetCounter(), items, "Minage");
            }

        // arbre couché remplacé par le tronc ; tronc, bûche et roche brisés disparaissent (Valheim : le bois tombe et est ramassé)
        if (tree->kind == "tree" || tree->kind == "log" || tree->kind == "rock" || tree->kind == "half")
            corpse->ForcedDespawn();
    }
}

void Wowlheim_AdjustMelee(Unit* attacker, Unit* victim, CalcDamageInfo* info) { sTreeMgr.AdjustMelee(attacker, victim, info); }
bool Wowlheim_AllowDamage(Unit* dealer, Unit* victim, bool melee) { return sTreeMgr.AllowDamage(dealer, victim, melee); }
void Wowlheim_OnKill(Unit* killer, Unit* victim) { sTreeMgr.OnKill(killer, victim); }
