// Wowlheim — fonderie, four à charbon, haut fourneau, rouet (Valheim `Smelter`). Règles et preuves : docs/VALHEIM_RULES.md §9.
#include "Wowlheim/Smelter.h"
#include "Wowlheim/BuildingMgr.h"

#include "Chat/Chat.h"
#include "Database/DatabaseEnv.h"
#include "Entities/Item.h"
#include "Entities/Player.h"
#include "Globals/ObjectMgr.h"
#include "Log/Log.h"
#include "Server/WorldSession.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <ctime>
#include <sstream>

namespace
{
    // Messages de Valheim (localisation française du jeu, colonne French de localization.txt)
    char const* MSG_FULL = "C'est plein";                              // $msg_itsfull
    char const* MSG_ADDED = "Ajouté";                                  // $msg_added
    char const* MSG_NOPROCESSABLE = "Vous n'avez rien à transformer";  // $msg_noprocessableitems
    char const* MSG_WONTWORK = "Cela ne marchera pas";                 // $msg_wontwork
    char const* MSG_DONTHAVE = "Vous n'avez pas de";                   // $msg_donthaveany
    char const* MSG_WRONGITEM = "Objet inadéquat";                     // $msg_wrongitem
    char const* MSG_REQROOF = "Nécessite un toit";                     // $piece_smelter_reqroof

    constexpr float INTERACT_DISTANCE = 5.0f;   // Player.m_maxInteractDistance (Player::.ctor IL 41-47 : 5)
    constexpr float MAX_ACCUMULATOR = 3600.0f;  // Smelter.UpdateSmelter IL 65-78 : accumulateur plafonné à 3600 s
    constexpr uint32 SAVE_PERIOD_MS = 10000;    // sauvegarde des états modifiés par la simulation (adaptation)

    std::string ItemName(uint32 id)
    {
        ItemPrototype const* p = ObjectMgr::GetItemPrototype(id);
        return p && p->Name1 ? p->Name1 : ("objet " + std::to_string(id));
    }

    void Raw(ChatHandler* h, bool api, std::string const& body)
    {
        if (api)
            h->SendSysMessage(("[WL]" + body).c_str());
    }

    void Out(ChatHandler* h, bool api, std::string const& text)
    {
        h->SendSysMessage(((api ? "[WL]M|" : "") + text).c_str());
    }

    // sphère / boîte orientée (rotation autour de z) : distance du centre au point le plus proche de la boîte
    bool SphereBox(float x, float y, float z, float r, WLBox const& b)
    {
        float dx = x - b.cx, dy = y - b.cy, dz = z - b.cz;
        float c = std::cos(-b.yaw), s = std::sin(-b.yaw);
        float lx = dx * c - dy * s, ly = dx * s + dy * c;
        float qx = std::max(-b.hx, std::min(b.hx, lx));
        float qy = std::max(-b.hy, std::min(b.hy, ly));
        float qz = std::max(-b.hz, std::min(b.hz, dz));
        float ex = lx - qx, ey = ly - qy, ez = dz - qz;
        return ex * ex + ey * ey + ez * ez <= r * r;
    }

    std::string Encode(std::map<uint32, uint32> const& m)
    {
        std::string s;
        for (auto const& kv : m)
            if (kv.second)
                s += (s.empty() ? "" : ",") + std::to_string(kv.first) + ":" + std::to_string(kv.second);
        return s;
    }

    std::string EncodeQueue(std::deque<uint32> const& q)
    {
        std::string s;
        for (uint32 it : q)
            s += (s.empty() ? "" : ",") + std::to_string(it);
        return s;
    }
}

uint32 WLSmelterDef::ConvertTo(uint32 from) const
{
    for (auto const& c : conversion)                   // Smelter.GetItemConversion : premier m_from correspondant
        if (c.first == from)
            return c.second;
    return 0;
}

SmelterMgr& SmelterMgr::Instance()
{
    static SmelterMgr instance;
    return instance;
}

void SmelterMgr::Load()
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    m_defs.clear();
    m_states.clear();
    auto r = WorldDatabase.Query("SELECT kind, name, fuel_item, max_ore, max_fuel, fuel_per_product, sec_per_product, requires_roof, spawn_stack, "
                                 "smoke_x, smoke_y, smoke_z, smoke_radius FROM wowlheim_smelter");
    if (!r)
    {
        sLog.outString(">> Wowlheim: table wowlheim_smelter absente ou vide, fonderies désactivées");
        return;
    }
    do
    {
        Field* f = r->Fetch();
        WLSmelterDef d;
        d.kind = f[0].GetCppString();
        d.name = f[1].GetCppString();
        d.fuelItem = f[2].GetUInt32();
        d.maxOre = f[3].GetUInt32();
        d.maxFuel = f[4].GetUInt32();
        d.fuelPerProduct = f[5].GetUInt32();
        d.secPerProduct = f[6].GetFloat();
        d.requiresRoof = f[7].GetUInt32() != 0;
        d.spawnStack = f[8].GetUInt32() != 0;
        d.smokeX = f[9].GetFloat();
        d.smokeY = f[10].GetFloat();
        d.smokeZ = f[11].GetFloat();
        d.smokeRadius = f[12].GetFloat();
        m_defs[d.kind] = d;
    } while (r->NextRow());
    if (auto c = WorldDatabase.Query("SELECT kind, from_item, to_item FROM wowlheim_smelter_conversion ORDER BY kind, idx"))
    {
        do
        {
            Field* f = c->Fetch();
            auto it = m_defs.find(f[0].GetCppString());
            if (it != m_defs.end())
                it->second.conversion.emplace_back(f[1].GetUInt32(), f[2].GetUInt32());
        } while (c->NextRow());
    }

    // états persistés ; rattrapage du temps serveur arrêté (Valheim : GetDeltaTime depuis s_startTime, plafonné à 3600 s)
    uint32 loaded = 0;
    time_t now = time(nullptr);
    if (auto s = CharacterDatabase.Query("SELECT guid, fuel, bake, acc, queue, output, updated_at FROM wowlheim_smelter_state"))
    {
        do
        {
            Field* f = s->Fetch();
            uint32 guid = f[0].GetUInt32();
            if (!DefForPiece(guid))
            {
                // pièce disparue (tables de pièces remises à zéro) : l'état ne doit pas se rattacher à un guid réutilisé
                CharacterDatabase.PExecute("DELETE FROM wowlheim_smelter_state WHERE guid = %u", guid);
                continue;
            }
            WLSmelterState st;
            st.fuel = f[1].GetFloat();
            st.bake = f[2].GetFloat();
            st.acc = f[3].GetFloat();
            std::stringstream qs(f[4].GetCppString());
            std::string tok;
            while (std::getline(qs, tok, ','))
                if (!tok.empty())
                    st.queue.push_back(uint32(strtoul(tok.c_str(), nullptr, 10)));
            std::stringstream os(f[5].GetCppString());
            while (std::getline(os, tok, ','))
            {
                size_t p = tok.find(':');
                if (p != std::string::npos)
                    st.output[uint32(strtoul(tok.substr(0, p).c_str(), nullptr, 10))] += uint32(strtoul(tok.substr(p + 1).c_str(), nullptr, 10));
            }
            uint64 updated = f[6].GetUInt64();
            if (updated && uint64(now) > updated)
                st.acc = std::min(MAX_ACCUMULATOR, st.acc + float(uint64(now) - updated));
            st.dirty = true;
            m_states[guid] = st;
            ++loaded;
        } while (s->NextRow());
    }
    sLog.outString(">> Wowlheim: %u stations de fonte (Smelter), %u états chargés", uint32(m_defs.size()), loaded);
}

WLSmelterDef const* SmelterMgr::DefForPiece(uint32 pieceGuid) const
{
    auto const& pieces = sBuildingMgr.Pieces();
    auto it = pieces.find(pieceGuid);
    if (it == pieces.end())
        return nullptr;
    WLPieceTemplate const* t = sBuildingMgr.FindTemplate(it->second.pieceId);
    if (!t)
        return nullptr;
    auto d = m_defs.find(t->kind);
    return d == m_defs.end() ? nullptr : &d->second;
}

// Smelter.UpdateRoof : Cover.IsUnderRoof(m_roofCheckPoint) seulement si m_requiresRoof ; ici le rayon de toit de la pièce
bool SmelterMgr::RoofOk(uint32 guid, WLSmelterDef const& def) const
{
    if (!def.requiresRoof)
        return true;
    auto it = sBuildingMgr.Pieces().find(guid);
    return it != sBuildingMgr.Pieces().end() && sBuildingMgr.HaveRoofAbove(it->second);
}

// SmokeSpawner.IsBlocked / TestBlocked : Physics.CheckSphere(position du SmokeSpawner, m_testRadius, couche 31 = SmokeBall).
// Adaptation : les boules de fumée (physique) ne sont pas simulées ; on considère la sortie bloquée quand une pièce posée
// occupe la sphère de test (la fumée ne peut pas s'en échapper). L'accumulation de fumée sous un toit fermé n'est pas simulée.
bool SmelterMgr::SmokeBlocked(uint32 guid, WLSmelterDef const& def) const
{
    if (def.smokeRadius <= 0)
        return false;
    auto const& pieces = sBuildingMgr.Pieces();
    auto it = pieces.find(guid);
    if (it == pieces.end())
        return false;
    WLPiece const& p = it->second;
    float c = std::cos(p.o), s = std::sin(p.o);
    float sx = p.x + def.smokeX * c - def.smokeY * s;
    float sy = p.y + def.smokeX * s + def.smokeY * c;
    float sz = p.z + def.smokeZ;
    for (auto const& kv : pieces)
    {
        WLPiece const& q = kv.second;
        if (q.map != p.map || q.guid == p.guid)
            continue;
        // les autres fours et fonderies sont des dômes / cheminées : leur boîte pleine déborderait largement de leur forme
        // (four à charbon : 3,7 m au centre, 1,5 m à 2,25 m du centre) ; ils ne bouchent pas la fumée d'une voisine
        if (DefForPiece(q.guid))
            continue;
        float dx = q.x - sx, dy = q.y - sy;
        if (dx * dx + dy * dy > 15.0f * 15.0f)
            continue;
        if (SphereBox(sx, sy, sz, def.smokeRadius, sBuildingMgr.BoxOf(q)))
            return true;
    }
    return false;
}

std::string SmelterMgr::Blocked(uint32 guid, WLSmelterDef const& def, WLSmelterState const& st) const
{
    // Smelter.IsActive (IL 0-65) / conditions de UpdateSmelter (IL 139-224)
    if (def.maxOre && st.queue.empty())
        return "noore";
    if (def.maxFuel && st.fuel <= 0.0f)
        return "nofuel";
    if (def.secPerProduct <= 0.0f)
        return "off";
    if (!RoofOk(guid, def))
        return "roof";
    if (SmokeBlocked(guid, def))
        return "smoke";
    return "";
}

// Smelter.UpdateSmelter (IL 46-416) : l'accumulateur reçoit le temps écoulé (plafond 3600 s) et la simulation avance par
// pas d'une seconde ; à chaque pas, si la station est active : combustible -= 1 / (secPerProduct / fuelPerProduct)
// (remis à 0 sous 0,0001), minuterie += 1 ; minuterie >= secPerProduct → 0, on retire le premier minerai et on produit
// sa conversion (m_spawnStack = 0 : un objet à la fois).
void SmelterMgr::Step(uint32 guid, WLSmelterDef const& def, WLSmelterState& st, float seconds)
{
    st.acc = std::min(MAX_ACCUMULATOR, st.acc + seconds);
    float power = 1.0f;                                    // m_windmill nul : puissance 1
    // toit et fumée : évalués une fois par appel, avant la boucle (UpdateRoof / UpdateSmoke, IL 14-26)
    bool environmentOk = RoofOk(guid, def) && !SmokeBlocked(guid, def);
    while (st.acc >= 1.0f)
    {
        st.acc -= 1.0f;
        if (def.maxFuel && !(st.fuel > 0.0f))
            continue;
        if (def.maxOre && st.queue.empty())
            continue;
        if (!(def.secPerProduct > 0.0f) || !environmentOk)
            continue;
        float dt = 1.0f * power;
        if (def.maxFuel > 0)
        {
            float secPerFuel = def.secPerProduct / float(def.fuelPerProduct);
            st.fuel -= dt / secPerFuel;
            if (st.fuel < 0.0001f)
                st.fuel = 0.0f;
        }
        st.bake += dt;
        st.dirty = true;
        if (st.bake >= def.secPerProduct)
        {
            st.bake = 0.0f;
            uint32 ore = st.queue.empty() ? 0 : st.queue.front();
            if (!st.queue.empty())
                st.queue.pop_front();                       // RemoveOneOre : décale item1.. vers item0..
            if (uint32 to = def.ConvertTo(ore))
                st.output[to] += 1;                         // QueueProcessed → Spawn(ore, 1)
        }
    }
}

void SmelterMgr::Update(uint32 diffMs)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    if (m_defs.empty())
        return;
    m_tickMs += diffMs;
    m_saveMs += diffMs;
    if (m_tickMs >= 1000)                                  // InvokeRepeating("UpdateSmelter", 1, 1)
    {
        float seconds = float(m_tickMs) / 1000.0f;
        m_tickMs = 0;
        for (auto it = m_states.begin(); it != m_states.end();)
        {
            WLSmelterDef const* def = DefForPiece(it->first);
            if (!def)
            {
                CharacterDatabase.PExecute("DELETE FROM wowlheim_smelter_state WHERE guid = %u", it->first);
                it = m_states.erase(it);
                continue;
            }
            Step(it->first, *def, it->second, seconds);
            ++it;
        }
    }
    if (m_saveMs >= SAVE_PERIOD_MS)
    {
        m_saveMs = 0;
        for (auto& kv : m_states)
            if (kv.second.dirty)
                Save(kv.first, kv.second);
    }
}

void SmelterMgr::Save(uint32 guid, WLSmelterState& st)
{
    st.dirty = false;
    std::string q = EncodeQueue(st.queue), o = Encode(st.output);
    CharacterDatabase.escape_string(q);
    CharacterDatabase.escape_string(o);
    CharacterDatabase.PExecute("REPLACE INTO wowlheim_smelter_state (guid, fuel, bake, acc, queue, output, updated_at) VALUES (%u, %f, %f, %f, '%s', '%s', " UI64FMTD ")",
                               guid, st.fuel, st.bake, st.acc, q.c_str(), o.c_str(), uint64(time(nullptr)));
}

// Smelter.OnAddOre (IL 0-257) : objet transformable (FindCookableItem : premier m_from de m_conversion présent dans le sac),
// IsItemAllowed, file < m_maxOre, une unité retirée du sac et ajoutée en fin de file.
bool SmelterMgr::AddOre(Player* player, uint32 guid, WLSmelterDef const& def, uint32 itemId, std::string& msg)
{
    if (!def.maxOre)
    {
        msg = MSG_WRONGITEM;
        return false;
    }
    if (!itemId)
    {
        for (auto const& c : def.conversion)
            if (player->GetItemCount(c.first) > 0)
            {
                itemId = c.first;
                break;
            }
        if (!itemId)
        {
            msg = MSG_NOPROCESSABLE;
            return false;
        }
    }
    else if (player->GetItemCount(itemId) == 0)
    {
        msg = std::string(MSG_DONTHAVE) + " " + ItemName(itemId);
        return false;
    }
    if (!def.ConvertTo(itemId))
    {
        msg = MSG_WONTWORK;
        return false;
    }
    WLSmelterState& st = State(guid);
    if (st.queue.size() >= def.maxOre)
    {
        msg = MSG_FULL;
        return false;
    }
    player->DestroyItemCount(itemId, 1, true);
    st.queue.push_back(itemId);
    st.dirty = true;
    msg = std::string(MSG_ADDED) + " " + ItemName(itemId);
    return true;
}

// Smelter.OnAddFuel (IL 0-269) : bon objet, combustible <= m_maxFuel - 1, objet présent ; RPC_AddFuel : +1
bool SmelterMgr::AddFuel(Player* player, uint32 guid, WLSmelterDef const& def, std::string& msg)
{
    if (!def.fuelItem || !def.maxFuel)
    {
        msg = MSG_WRONGITEM;                                // le four à charbon n'a pas d'interrupteur de combustible
        return false;
    }
    WLSmelterState& st = State(guid);
    if (st.fuel > float(def.maxFuel - 1))
    {
        msg = MSG_FULL;
        return false;
    }
    if (player->GetItemCount(def.fuelItem) == 0)
    {
        msg = std::string(MSG_DONTHAVE) + " " + ItemName(def.fuelItem);
        return false;
    }
    player->DestroyItemCount(def.fuelItem, 1, true);
    st.fuel += 1.0f;
    st.dirty = true;
    msg = std::string(MSG_ADDED) + " " + ItemName(def.fuelItem);
    return true;
}

// Adaptation : Valheim fait tomber chaque produit au point « output » de la station ; ici les produits restent dans la station
// jusqu'à ce qu'un joueur les récupère (sac ; ce qui ne rentre pas reste dans la station).
uint32 SmelterMgr::Take(Player* player, uint32 guid, std::string& msg)
{
    WLSmelterState& st = State(guid);
    uint32 taken = 0;
    std::string got;
    for (auto& kv : st.output)
    {
        if (!kv.second)
            continue;
        ItemPosCountVec dest;
        uint32 noSpace = 0;
        uint8 res = player->CanStoreNewItem(NULL_BAG, NULL_SLOT, dest, kv.first, kv.second, &noSpace);
        uint32 n = (res == EQUIP_ERR_OK) ? kv.second : kv.second - std::min(kv.second, noSpace);
        if (!n || dest.empty())
            continue;
        if (Item* item = player->StoreNewItem(dest, kv.first, true, Item::GenerateItemRandomPropertyId(kv.first)))
            player->SendNewItem(item, n, true, false);
        kv.second -= n;
        taken += n;
        got += (got.empty() ? "" : ", ") + std::to_string(n) + " " + ItemName(kv.first);
    }
    for (auto it = st.output.begin(); it != st.output.end();)
        it = it->second ? std::next(it) : st.output.erase(it);
    if (taken)
    {
        st.dirty = true;
        msg = "Récupéré : " + got;
    }
    else
        msg = st.output.empty() ? "Rien à récupérer." : "Sac plein.";
    return taken;
}

std::string SmelterMgr::StatusLine(uint32 guid, WLSmelterDef const& def, WLSmelterState const& st) const
{
    std::map<uint32, uint32> q;
    for (uint32 it : st.queue)
        q[it] += 1;
    std::string why = Blocked(guid, def, st);
    char buf[512];
    snprintf(buf, sizeof(buf), "SM|%u|%s|%s|%u|%u|%.2f|%u|%u|%.1f|%.0f|%u|%s|%s|%s", guid, def.kind.c_str(), def.name.c_str(),
             uint32(st.queue.size()), def.maxOre, st.fuel, def.maxFuel, def.fuelItem, st.bake, def.secPerProduct,
             why.empty() ? 1u : 0u, why.empty() ? "ok" : why.c_str(), Encode(q).c_str(), Encode(st.output).c_str());
    return buf;
}

std::string SmelterMgr::StatusText(uint32 guid, WLSmelterDef const& def, WLSmelterState const& st) const
{
    std::string why = Blocked(guid, def, st);
    char buf[512];
    std::string out;
    for (auto const& kv : st.output)
        out += (out.empty() ? "" : ", ") + std::to_string(kv.second) + " " + ItemName(kv.first);
    if (def.maxFuel)
        snprintf(buf, sizeof(buf), "%s : à transformer %u/%u, %s %.1f/%u, cuisson %.0f/%.0f s, %s. Transformé : %s.", def.name.c_str(),
                 uint32(st.queue.size()), def.maxOre, ItemName(def.fuelItem).c_str(), st.fuel, def.maxFuel, st.bake, def.secPerProduct,
                 why.empty() ? "en marche" : why == "roof" ? MSG_REQROOF : why == "smoke" ? "fumée bloquée" : "à l'arrêt",
                 out.empty() ? "rien" : out.c_str());
    else
        snprintf(buf, sizeof(buf), "%s : à transformer %u/%u, cuisson %.0f/%.0f s, %s. Transformé : %s.", def.name.c_str(),
                 uint32(st.queue.size()), def.maxOre, st.bake, def.secPerProduct,
                 why.empty() ? "en marche" : why == "roof" ? MSG_REQROOF : why == "smoke" ? "fumée bloquée" : "à l'arrêt",
                 out.empty() ? "rien" : out.c_str());
    return buf;
}

uint32 SmelterMgr::Nearest(Player* player, float range) const
{
    uint32 best = 0;
    float bestD = range * range;
    for (auto const& kv : sBuildingMgr.Pieces())
    {
        WLPiece const& p = kv.second;
        if (p.map != player->GetMapId() || !DefForPiece(p.guid))
            continue;
        // distance 2D au bord de l'emprise (adaptation : Valheim mesure au point d'interaction ; ici la boîte de la pièce)
        float d = sBuildingMgr.DistToPiece2D(p, player->GetPositionX(), player->GetPositionY());
        d *= d;
        if (d <= bestD)
        {
            bestD = d;
            best = p.guid;
        }
    }
    return best;
}

bool SmelterMgr::OnUse(Player* player, uint32 pieceGuid)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    WLSmelterDef const* def = DefForPiece(pieceGuid);
    if (!def)
        return false;
    // Clic : on récupère les produits prêts (Smelter.OnEmpty / ramassage) et le panneau s'ouvre sur l'état (ligne SM|).
    // Le minerai et le combustible s'ajoutent depuis le panneau, un par clic comme l'interrupteur add_ore / add_wood de
    // Valheim, ou en remplissant (Maj+clic) : un clic sur la station ne vide plus le sac d'un coup.
    std::string msg;
    Take(player, pieceGuid, msg);
    WLSmelterState& st = State(pieceGuid);
    std::string text = msg.rfind("Récupéré", 0) == 0 ? msg + "." : std::string();
    ChatHandler h(player->GetSession());                // l'addon affiche M| (plus de SendNotification : double affichage)
    h.SendSysMessage(("[WL]" + StatusLine(pieceGuid, *def, st)).c_str());
    if (!text.empty())
        h.SendSysMessage(("[WL]M|" + text).c_str());
    Save(pieceGuid, st);
    return true;
}

void SmelterMgr::OnPieceRemoved(uint32 pieceGuid, Player* to, uint32 ownerGuid)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    auto it = m_states.find(pieceGuid);
    if (it == m_states.end())
        return;
    WLSmelterDef const* def = DefForPiece(pieceGuid);
    // Smelter.DropAllItems (IL 0-318) : produits, combustible entier restant (int)fuel, puis tout le minerai en file
    std::map<uint32, uint32> back = it->second.output;
    if (def && def->fuelItem && it->second.fuel >= 1.0f)
        back[def->fuelItem] += uint32(it->second.fuel);
    for (uint32 ore : it->second.queue)
        back[ore] += 1;
    std::vector<WLItemCount> items;
    for (auto const& kv : back)
        if (kv.second)
            items.push_back(WLItemCount{ kv.first, kv.second });
    // Adaptation : Valheim fait tomber ces objets au sol ; ici au démolisseur (sac, puis courrier) ou par courrier au propriétaire
    if (!items.empty())
        sBuildingMgr.GiveItems(to, ownerGuid, items, "Contenu de la station");
    CharacterDatabase.PExecute("DELETE FROM wowlheim_smelter_state WHERE guid = %u", pieceGuid);
    m_states.erase(it);
}

// .build api smelter status [guid]
// .build api smelter add <ore|fuel|id_objet> [nombre] [guid]
// .build api smelter take [guid]
bool SmelterMgr::HandleCommand(ChatHandler* h, Player* player, char* args, bool api)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    std::vector<std::string> a;
    {
        std::stringstream ss(args ? args : "");
        std::string t;
        while (ss >> t)
            a.push_back(t);
    }
    if (a.empty())
    {
        Out(h, api, "Usage : .build api smelter status|add <ore|fuel|id> [nombre] [guid]|take [guid]");
        Raw(h, api, "E|usage");
        return false;
    }
    std::string sub = a[0];
    auto parseGuid = [&](size_t idx) -> uint32
    {
        if (a.size() > idx)
            return uint32(strtoul(a[idx].c_str(), nullptr, 10));
        return Nearest(player, INTERACT_DISTANCE);
    };
    size_t guidIdx = sub == "add" ? 3 : 1;
    uint32 guid = parseGuid(guidIdx);
    WLSmelterDef const* def = guid ? DefForPiece(guid) : nullptr;
    if (!def)
    {
        Out(h, api, "Aucune station de transformation (fonderie, four, haut fourneau, rouet) à moins de 5 m.");
        Raw(h, api, "E|aucune station");
        return false;
    }
    auto pit = sBuildingMgr.Pieces().find(guid);
    if (pit != sBuildingMgr.Pieces().end())
    {
        WLPiece const& p = pit->second;
        if (p.map != player->GetMapId() || sBuildingMgr.DistToPiece2D(p, player->GetPositionX(), player->GetPositionY()) > INTERACT_DISTANCE)
        {
            Out(h, api, "Station trop loin (5 m au plus).");
            Raw(h, api, "E|trop loin");
            return false;
        }
    }
    WLSmelterState& st = State(guid);
    bool ok = true;
    if (sub == "status")
        Out(h, api, StatusText(guid, *def, st));
    else if (sub == "take")
    {
        std::string msg;
        ok = Take(player, guid, msg) > 0;
        Out(h, api, msg);
    }
    else if (sub == "add")
    {
        if (a.size() < 2)
        {
            Out(h, api, "Usage : .build api smelter add <ore|fuel|id> [nombre] [guid]");
            return false;
        }
        uint32 count = a.size() > 2 ? std::max<uint32>(1, uint32(strtoul(a[2].c_str(), nullptr, 10))) : 1;
        bool fuel = a[1] == "fuel";
        uint32 itemId = (a[1] == "ore" || fuel) ? 0 : uint32(strtoul(a[1].c_str(), nullptr, 10));
        if (!fuel && def->fuelItem && itemId == def->fuelItem)
            fuel = true;
        uint32 added = 0;
        std::string msg;
        for (uint32 i = 0; i < count; ++i)
        {
            if (!(fuel ? AddFuel(player, guid, *def, msg) : AddOre(player, guid, *def, itemId, msg)))
                break;
            ++added;
        }
        ok = added > 0;
        Out(h, api, added ? "Ajouté " + std::to_string(added) + (fuel ? " " + ItemName(def->fuelItem) : " objet(s) à transformer") + (added < count ? " (" + msg + ")" : "") : msg);
        if (!ok)
            Raw(h, api, "E|" + msg);
        Raw(h, api, "A|" + std::to_string(added));
    }
    else
    {
        Out(h, api, "Sous-commande inconnue : status, add, take.");
        Raw(h, api, "E|commande inconnue");
        return false;
    }
    Raw(h, api, StatusLine(guid, *def, st));
    if (st.dirty)
        Save(guid, st);
    return ok;
}

bool Wowlheim_SmelterCommand(ChatHandler* h, Player* player, char* args, bool api)
{
    return player && sSmelterMgr.HandleCommand(h, player, args, api);
}
