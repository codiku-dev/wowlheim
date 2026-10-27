// Wowlheim — compétences et endurance « outils » façon Valheim. Règles et preuves : docs/VALHEIM_SKILLS.md.
#include "Wowlheim/ValheimSkills.h"
#include "Wowlheim/BuildingMgr.h"

#include "Chat/Chat.h"
#include "Database/DatabaseEnv.h"
#include "Entities/Item.h"
#include "Entities/Player.h"
#include "Server/WorldSession.h"
#include "Util/Timer.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>

namespace
{
    // Compétences suivies, dans l'ordre de Skills.SkillType (ordre du panneau des compétences de Valheim)
    uint16 const TRACKED[] = { WL_SKILL_AXES, WL_SKILL_PICKAXES, WL_SKILL_WOODCUTTING, WL_SKILL_CRAFTING };

    bool Tracked(uint16 skill)
    {
        for (uint16 s : TRACKED)
            if (s == skill)
                return true;
        return false;
    }

    void ApiTo(Player* player, std::string const& body)
    {
        if (player && player->GetSession())
            ChatHandler(player->GetSession()).SendSysMessage(("[WL]" + body).c_str());
    }
}

WLSkillMgr& WLSkillMgr::Instance()
{
    static WLSkillMgr instance;
    return instance;
}

// SkillDef.m_increseStep (prefab Player, composant Skills)
float WLSkillMgr::IncreaseStep(uint16 skill)
{
    switch (skill)
    {
        case WL_SKILL_AXES:
        case WL_SKILL_PICKAXES:
        case WL_SKILL_WOODCUTTING: return 1.0f;
        case WL_SKILL_CRAFTING:    return 0.25f;
        default:                   return 0.0f;
    }
}

// Skills.Skill.GetNextLevelRequirement (IL 0–39) = 0,5 · floor(niveau + 1)^1,5 + 0,5
float WLSkillMgr::NextLevelRequirement(float level)
{
    return std::pow(std::floor(level + 1.0f), 1.5f) * 0.5f + 0.5f;
}

// Attack.m_attackStamina des prefabs (attaque primaire) ; paliers serveur de tools/valheim/gen_server_sql.py (TOOLS)
float WLSkillMgr::ToolStamina(uint32 itemEntry)
{
    switch (itemEntry)
    {
        case 9201010: return 6.0f;     // AxeStone
        case 9201011: return 6.0f;     // AxeFlint
        case 9201021: return 8.0f;     // AxeBronze
        case 9201031: return 10.0f;    // AxeIron
        case 9201041: return 10.0f;    // AxeIron (palier 4)
        case 9201051: return 14.0f;    // AxeBlackMetal
        case 9201012: return 6.0f;     // PickaxeAntler
        case 9201022: return 8.0f;     // PickaxeBronze
        case 9201032: return 10.0f;    // PickaxeIron
        case 9201042: return 10.0f;    // PickaxeIron (palier 4)
        case 9201052: return 14.0f;    // PickaxeBlackMetal
        case BuildingMgr::HAMMER_ITEM: return 5.0f;   // Hammer
        default: return 0.0f;
    }
}

bool WLSkillMgr::IsBroken(Item* item)
{
    return item && item->GetUInt32Value(ITEM_FIELD_MAXDURABILITY) > 0 && item->GetUInt32Value(ITEM_FIELD_DURABILITY) == 0;
}

WLSkillMgr::PlayerData& WLSkillMgr::Get(uint32 guid)
{
    PlayerData& d = m_players[guid];
    if (!d.loaded)
    {
        d.loaded = true;
        if (auto r = CharacterDatabase.PQuery("SELECT skill, level, acc FROM wowlheim_skill WHERE guid = %u", guid))
        {
            do
            {
                Field* f = r->Fetch();
                SkillData& s = d.skills[uint16(f[0].GetUInt32())];
                s.level = std::min(100.0f, std::max(0.0f, f[1].GetFloat()));
                s.acc = std::max(0.0f, f[2].GetFloat());
            } while (r->NextRow());
        }
    }
    return d;
}

void WLSkillMgr::Save(uint32 guid, uint16 skill, SkillData const& s)
{
    CharacterDatabase.PExecute("REPLACE INTO wowlheim_skill (guid, skill, level, acc) VALUES (%u, %u, %f, %f)",
                               guid, uint32(skill), s.level, s.acc);
}

// SK|id|niveau entier|pourcentage vers le niveau suivant (Skill.GetLevelPercentage ; 0 au niveau 100)
void WLSkillMgr::SkillLine(Player* player, uint16 skill, SkillData const& s)
{
    float pct = s.level >= 100.0f ? 0.0f : std::min(1.0f, std::max(0.0f, s.acc / NextLevelRequirement(s.level)));
    ApiTo(player, "SK|" + std::to_string(skill) + "|" + std::to_string(int32(std::floor(s.level))) + "|" +
                  std::to_string(int32(std::floor(pct * 100.0f))));
}

float WLSkillMgr::GetLevel(Player* player, uint16 skill)
{
    if (!player)
        return 0.0f;
    std::lock_guard<std::recursive_mutex> g(m_lock);
    PlayerData& d = Get(player->GetObjectGuid().GetCounter());
    auto it = d.skills.find(skill);
    return it == d.skills.end() ? 0.0f : std::floor(it->second.level);
}

float WLSkillMgr::GetFactor(Player* player, uint16 skill)
{
    return std::min(1.0f, std::max(0.0f, GetLevel(player, skill) / 100.0f));
}

// Skills.RaiseSkill (IL 0–191) / Skills.Skill.Raise (IL 0–124) : un niveau au plus par appel, l'excédent est perdu
void WLSkillMgr::Raise(Player* player, uint16 skill, float amount)
{
    if (!player || !Tracked(skill) || amount <= 0.0f)
        return;
    uint32 guid = player->GetObjectGuid().GetCounter();
    SkillData copy;
    bool leveled = false;
    {
        std::lock_guard<std::recursive_mutex> g(m_lock);
        PlayerData& d = Get(guid);
        SkillData& s = d.skills[skill];
        if (s.level >= 100.0f)
            return;
        s.acc += IncreaseStep(skill) * amount;                  // × Game.m_skillGainRate (1)
        if (s.acc >= NextLevelRequirement(s.level))
        {
            s.level = std::min(100.0f, std::max(0.0f, s.level + 1.0f));
            s.acc = 0.0f;
            leveled = true;
            d.dirty.erase(skill);
            Save(guid, skill, s);
        }
        else
            d.dirty.insert(skill);
        copy = s;
    }
    SkillLine(player, skill, copy);
    if (leveled)                                                // « $msg_skillup $skill_x: niveau » (affiché par l'addon)
        ApiTo(player, "SKU|" + std::to_string(skill) + "|" + std::to_string(int32(std::floor(copy.level))));
}

void WLSkillMgr::SetLevel(Player* player, uint16 skill, float level)
{
    if (!player || !Tracked(skill))
        return;
    uint32 guid = player->GetObjectGuid().GetCounter();
    SkillData copy;
    {
        std::lock_guard<std::recursive_mutex> g(m_lock);
        PlayerData& d = Get(guid);
        SkillData& s = d.skills[skill];
        s.level = std::min(100.0f, std::max(0.0f, level));
        s.acc = 0.0f;
        d.dirty.erase(skill);
        Save(guid, skill, s);
        copy = s;
    }
    SkillLine(player, skill, copy);
}

// Player.OnDeath (IL 25, 1055–1064) : HardDeath() = m_timeSinceDeath > m_hardDeathCooldown (600 s) -> Skills.OnDeath ->
// LowerAllSkills(0,05) (IL 0–119) : niveau −= niveau·0,05, accumulateur remis à 0, message $msg_skills_lowered
void WLSkillMgr::OnDeath(Player* player)
{
    if (!player)
        return;
    uint32 guid = player->GetObjectGuid().GetCounter();
    uint32 now = WorldTimer::getMSTime();
    std::map<uint16, SkillData> copy;
    {
        std::lock_guard<std::recursive_mutex> g(m_lock);
        PlayerData& d = Get(guid);
        bool hard = d.deathMs == 0 || WorldTimer::getMSTimeDiff(d.deathMs, now) > uint32(HARD_DEATH_COOLDOWN * 1000.0f);
        d.deathMs = now ? now : 1;
        d.removeDebt = 0;
        if (!hard)
            return;
        for (auto& kv : d.skills)
        {
            kv.second.level -= kv.second.level * DEATH_LOWER_FACTOR;
            kv.second.acc = 0.0f;
            Save(guid, kv.first, kv.second);
        }
        d.dirty.clear();
        copy = d.skills;
    }
    ApiTo(player, "SKL|" + std::to_string(int32(std::lround(DEATH_LOWER_FACTOR * 100.0f))));
    for (uint16 s : TRACKED)
        SkillLine(player, s, copy[s]);
}

void WLSkillMgr::OnBuildRemove(Player* player)
{
    if (!player)
        return;
    std::lock_guard<std::recursive_mutex> g(m_lock);
    PlayerData& d = Get(player->GetObjectGuid().GetCounter());
    d.removeDebt = std::min(MAX_REMOVE_DEBT, d.removeDebt + 1);
}

// Player.UpdatePlacement (IL 1250–1292) : dette de démolition d'abord, sinon RaiseSkill(Fabrication, 1)
void WLSkillMgr::OnBuildPlace(Player* player)
{
    if (!player)
        return;
    {
        std::lock_guard<std::recursive_mutex> g(m_lock);
        PlayerData& d = Get(player->GetObjectGuid().GetCounter());
        if (d.removeDebt > 0)
        {
            --d.removeDebt;
            return;
        }
    }
    Raise(player, WL_SKILL_CRAFTING, 1.0f);
}

// Player.UpdateStats (IL 132–254) : regen = r + (1 − s/M)·r·k, après le délai ; forme fermée de l'équation
// ds/dt = r(1 + k) − (r·k/M)·s : s(t) = s∞ − (s∞ − s0)·exp(−r·k·t/M), s∞ = M(1 + k)/k, bornée à M.
float WLSkillMgr::StaminaNow(PlayerData const& d, uint32 now) const
{
    float const M = BASE_STAMINA;
    if (!d.useMs)
        return std::min(M, d.stamina);
    float t = WorldTimer::getMSTimeDiff(d.useMs, now) / 1000.0f - STAMINA_REGEN_DELAY;
    if (t <= 0.0f)
        return d.stamina;
    float const r = STAMINA_REGEN, k = STAMINA_REGEN_TIME_MULT;
    float s;
    if (k <= 0.0f)
        s = d.stamina + r * t;
    else
    {
        float inf = M * (1.0f + k) / k;
        s = inf - (inf - d.stamina) * std::exp(-r * k * t / M);
    }
    return std::min(M, s);
}

float WLSkillMgr::GetStamina(Player* player)
{
    if (!player)
        return 0.0f;
    std::lock_guard<std::recursive_mutex> g(m_lock);
    return StaminaNow(Get(player->GetObjectGuid().GetCounter()), WorldTimer::getMSTime());
}

bool WLSkillMgr::HaveStamina(Player* player, float amount)
{
    return GetStamina(player) > amount;                         // Player.HaveStamina (IL 57–66) : strictement supérieur
}

// Player.UseStamina / RPC_UseStamina (IL 0–59) : stamina = max(0, stamina − v) ; m_staminaRegenTimer = m_staminaRegenDelay
void WLSkillMgr::UseStamina(Player* player, float amount)
{
    if (!player || amount <= 0.0f)
        return;
    std::lock_guard<std::recursive_mutex> g(m_lock);
    PlayerData& d = Get(player->GetObjectGuid().GetCounter());
    uint32 now = WorldTimer::getMSTime();
    d.stamina = std::max(0.0f, StaminaNow(d, now) - amount);    // × Game.m_staminaRate (1)
    d.useMs = now ? now : 1;
}

void WLSkillMgr::SetStamina(Player* player, float value)
{
    if (!player)
        return;
    std::lock_guard<std::recursive_mutex> g(m_lock);
    PlayerData& d = Get(player->GetObjectGuid().GetCounter());
    uint32 now = WorldTimer::getMSTime();
    d.stamina = std::min(BASE_STAMINA, std::max(0.0f, value));
    d.useMs = now ? now : 1;
}

// EN|cur×10|max×10|délai restant avant régénération (ms)|clignotement (Hud.StaminaBarEmptyFlash)
void WLSkillMgr::SendStamina(Player* player, bool flash)
{
    if (!player)
        return;
    float cur;
    uint32 delay = 0;
    {
        std::lock_guard<std::recursive_mutex> g(m_lock);
        PlayerData& d = Get(player->GetObjectGuid().GetCounter());
        uint32 now = WorldTimer::getMSTime();
        cur = StaminaNow(d, now);
        if (d.useMs)
        {
            uint32 since = WorldTimer::getMSTimeDiff(d.useMs, now);
            uint32 full = uint32(STAMINA_REGEN_DELAY * 1000.0f);
            delay = since < full ? full - since : 0;
        }
    }
    ApiTo(player, "EN|" + std::to_string(int32(std::lround(cur * 10.0f))) + "|" +
                  std::to_string(int32(std::lround(BASE_STAMINA * 10.0f))) + "|" + std::to_string(delay) + "|" + (flash ? "1" : "0"));
}

// Attack.GetAttackStamina (IL 0–188) : s − 0,33·s·GetSkillFactor(arme.m_shared.m_skillType)
float WLSkillMgr::AttackStamina(Player* player, uint32 itemEntry, uint16 weaponSkill)
{
    float s = ToolStamina(itemEntry);
    if (s <= 0.0f)
        return 0.0f;
    return s - s * 0.33f * GetFactor(player, weaponSkill);
}

// Player.GetBuildStamina (IL 0–96) : s − 0,5·s·GetSkillFactor(PieceTable.m_skill = Fabrication), s = attackStamina du marteau
float WLSkillMgr::BuildStamina(Player* player)
{
    float s = ToolStamina(BuildingMgr::HAMMER_ITEM);
    return s - s * 0.5f * GetFactor(player, WL_SKILL_CRAFTING);
}

// Player.GetPlaceDurability (IL 0–62) : drain − drain·m_placementDurabilityMax (0,5)·facteur(Fabrication), drain = 1
void WLSkillMgr::WearHammer(Player* player, Item* hammer)
{
    if (!player || !hammer)
        return;
    float wear = 1.0f - 0.5f * GetFactor(player, WL_SKILL_CRAFTING);
    int32 points = 0;
    {
        std::lock_guard<std::recursive_mutex> g(m_lock);
        PlayerData& d = Get(player->GetObjectGuid().GetCounter());
        d.hammerWear += wear;
        points = int32(std::floor(d.hammerWear + 1e-4f));
        d.hammerWear -= float(points);
    }
    if (points > 0)
        player->DurabilityPointsLoss(hammer, points);
}

void WLSkillMgr::SendSkills(ChatHandler* h, Player* player)
{
    if (!player)
        return;
    std::map<uint16, SkillData> copy;
    {
        std::lock_guard<std::recursive_mutex> g(m_lock);
        copy = Get(player->GetObjectGuid().GetCounter()).skills;
    }
    (void)h;
    for (uint16 s : TRACKED)
        SkillLine(player, s, copy[s]);
    SendStamina(player, false);
}

// Accumulateurs modifiés écrits toutes les 30 s (les niveaux gagnés sont écrits tout de suite)
void WLSkillMgr::Update(uint32 diffMs)
{
    m_saveTimer += diffMs;
    if (m_saveTimer < 30000)
        return;
    m_saveTimer = 0;
    std::lock_guard<std::recursive_mutex> g(m_lock);
    for (auto& kv : m_players)
    {
        for (uint16 s : kv.second.dirty)
            Save(kv.first, s, kv.second.skills[s]);
        kv.second.dirty.clear();
    }
}

// .build api skills                  : SK| par compétence suivie, puis EN|
// .build api skills stamina <v>      : (MJ) fixe l'endurance (tests)
// .build api skills set <id> <niveau>: (MJ) fixe un niveau (tests)
bool Wowlheim_SkillsCommand(ChatHandler* h, Player* player, char* args)
{
    if (!player)
        return false;
    char* sub = args ? strtok(args, " ") : nullptr;
    if (sub && (!strcmp(sub, "stamina") || !strcmp(sub, "set")))
    {
        if (player->GetSession()->GetSecurity() < SEC_GAMEMASTER)
        {
            h->SendSysMessage("[WL]E|réservé aux MJ");
            return false;
        }
        if (!strcmp(sub, "stamina"))
        {
            char* v = strtok(nullptr, " ");
            if (!v)
                return false;
            sWLSkillMgr.SetStamina(player, float(atof(v)));
        }
        else
        {
            char* id = strtok(nullptr, " ");
            char* lv = strtok(nullptr, " ");
            if (!id || !lv)
                return false;
            sWLSkillMgr.SetLevel(player, uint16(atoi(id)), float(atof(lv)));
        }
    }
    sWLSkillMgr.SendSkills(h, player);
    return true;
}
