// Wowlheim — coffres, portes et lits façon Valheim (composants Container, Door, Bed). Règles : docs/VALHEIM_RULES.md §14.
#include "Wowlheim/Pieces.h"
#include "Wowlheim/BuildingMgr.h"

#include "Chat/Chat.h"
#include "Database/DatabaseEnv.h"
#include "Entities/Bag.h"
#include "Entities/GameObject.h"
#include "Entities/Item.h"
#include "Entities/Player.h"
#include "Globals/ObjectAccessor.h"
#include "Globals/ObjectMgr.h"
#include "Log/Log.h"
#include "Mails/Mail.h"
#include "Maps/Map.h"
#include "Server/Opcodes.h"
#include "Server/WorldPacket.h"
#include "Server/WorldSession.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <set>
#include <sstream>

namespace
{
    // Messages de Valheim (colonne French de localization.txt)
    char const* MSG_CANTOPEN = "Ne peut être ouvert";                         // $msg_cantopen (Container.Interact IL 67)
    char const* MSG_INUSE = "Utilisé par quelqu'un d’autre";                  // $msg_inuse (Container.RPC_OpenResponse IL 35)
    char const* MSG_CANTREMOVENOW = "Ne peut être retiré pour l'instant";     // $msg_cantremovenow (Player.RemovePiece IL 283)
    char const* MSG_SPAWNPOINTSET = "Point de réapparition créé";             // $msg_spawnpointset (Bed.Interact IL 117)
    char const* MSG_BEDNEEDROOF = "Le lit requiert un toit";                  // $msg_bedneedroof (Bed.CheckExposure IL 25)
    char const* MSG_BEDTOOEXPOSED = "Le lit est trop exposé";                 // $msg_bedtooexposed (Bed.CheckExposure IL 50)
    char const* MSG_NOROOM = "Votre inventaire est plein";                    // $msg_noroom
    char const* MSG_FULL = "Inventaire plein";                                // $inventory_full (coffre plein)
    char const* MSG_WRONGITEM = "Objet inadéquat";                            // $msg_wrongitem
    char const* MSG_NEEDKEY = "Clé nécessaire : ";                            // $msg_door_needkey
    char const* MSG_USINGKEY = "Clé utilisée : ";                             // $msg_door_usingkey
    char const* MSG_COMBAT = "Impossible en combat.";                         // adaptation WoW (Valheim n'a pas cette règle)

    constexpr float PI = 3.14159265f;
    constexpr float BED_EXPOSURE_MIN = 0.8f;      // Bed.CheckExposure IL 41 : couverture >= 0,8
    constexpr float BED_SPAWN_HEIGHT = 0.5f;      // adaptation : point d'apparition (enfant « spawnpoint ») 0,5 m au-dessus de la base

    void Api(ChatHandler* h, std::string const& body)
    {
        h->SendSysMessage(("[WL]" + body).c_str());
    }

    std::string ItemName(uint32 id)
    {
        ItemPrototype const* p = ObjectMgr::GetItemPrototype(id);
        return p && p->Name1 ? p->Name1 : ("objet " + std::to_string(id));
    }

    uint32 MaxStack(uint32 entry)
    {
        ItemPrototype const* p = ObjectMgr::GetItemPrototype(entry);
        return p && p->GetMaxStackSize() > 1 ? p->GetMaxStackSize() : 1;
    }

    // Emplacement Lua (GetContainerItemInfo : sac 0 = sac à dos 1..16, sacs 1..4 : 1..n) -> (sac, case) du serveur
    bool LuaToServerPos(uint32 luaBag, uint32 luaSlot, uint8& bag, uint8& slot)
    {
        if (luaSlot < 1)
            return false;
        if (luaBag == 0)
        {
            if (luaSlot > uint32(INVENTORY_SLOT_ITEM_END - INVENTORY_SLOT_ITEM_START))
                return false;
            bag = INVENTORY_SLOT_BAG_0;
            slot = uint8(INVENTORY_SLOT_ITEM_START + luaSlot - 1);
            return true;
        }
        if (luaBag > uint32(INVENTORY_SLOT_BAG_END - INVENTORY_SLOT_BAG_START) || luaSlot > 255)
            return false;
        bag = uint8(INVENTORY_SLOT_BAG_START + luaBag - 1);
        slot = uint8(luaSlot - 1);
        return true;
    }

    // Toutes les positions d'objets des sacs (sac à dos + sacs équipés), pour putitem / stackall
    template <class F> void ForEachBagItem(Player* player, F f)
    {
        for (uint8 s = INVENTORY_SLOT_ITEM_START; s < INVENTORY_SLOT_ITEM_END; ++s)
            if (Item* it = player->GetItemByPos(INVENTORY_SLOT_BAG_0, s))
                f(it, uint8(INVENTORY_SLOT_BAG_0), s);
        for (uint8 b = INVENTORY_SLOT_BAG_START; b < INVENTORY_SLOT_BAG_END; ++b)
        {
            Item* bagItem = player->GetItemByPos(INVENTORY_SLOT_BAG_0, b);
            if (!bagItem || !bagItem->IsBag())
                continue;
            Bag* bag = static_cast<Bag*>(bagItem);
            for (uint32 s = 0; s < bag->GetBagSize(); ++s)
                if (Item* it = player->GetItemByPos(b, uint8(s)))
                    f(it, b, uint8(s));
        }
    }

    bool SameStack(WLChestSlot const& a, WLChestSlot const& b)
    {
        return a.item == b.item && a.durability == b.durability && a.randomProp == b.randomProp && a.bound == b.bound;
    }
}

PieceUseMgr& PieceUseMgr::Instance()
{
    static PieceUseMgr instance;
    return instance;
}

void PieceUseMgr::Load()
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    m_defs.clear();
    m_chests.clear();
    m_states.clear();
    auto r = WorldDatabase.Query("SELECT piece_id, kind, name, width, height, privacy, check_guard, can_not_be_closed, key_item, consume_key FROM wowlheim_piece_use");
    if (!r)
    {
        sLog.outString(">> Wowlheim: table wowlheim_piece_use absente ou vide, coffres / portes / lits inactifs");
        return;
    }
    do
    {
        Field* f = r->Fetch();
        WLPieceUseDef d;
        d.pieceId = f[0].GetUInt32();
        d.kind = f[1].GetCppString();
        d.name = f[2].GetCppString();
        d.width = f[3].GetUInt32();
        d.height = f[4].GetUInt32();
        d.privacy = uint8(f[5].GetUInt32());
        d.checkGuardStone = f[6].GetUInt32() != 0;
        d.canNotBeClosed = f[7].GetUInt32() != 0;
        d.keyItem = f[8].GetUInt32();
        d.consumeKey = f[9].GetUInt32() != 0;
        m_defs[d.pieceId] = d;
    } while (r->NextRow());

    std::set<uint32> orphans;
    uint32 items = 0;
    if (auto c = CharacterDatabase.Query("SELECT guid, slot, item_id, `count`, durability, random_property, bound FROM wowlheim_container"))
    {
        do
        {
            Field* f = c->Fetch();
            uint32 guid = f[0].GetUInt32();
            WLPieceUseDef const* def = DefForPiece(guid);
            if (!def || def->kind != "container")
            {
                orphans.insert(guid);                    // pièce disparue : le contenu ne doit pas se rattacher à un guid réutilisé
                continue;
            }
            WLChest& chest = Chest(guid, *def);
            uint32 slot = f[1].GetUInt32();
            if (slot >= chest.slots.size())
                continue;
            WLChestSlot& s = chest.slots[slot];
            s.item = f[2].GetUInt32();
            s.count = f[3].GetUInt32();
            s.durability = f[4].GetUInt32();
            s.randomProp = f[5].GetInt32();
            s.bound = f[6].GetUInt32() != 0;
            ++items;
        } while (c->NextRow());
    }
    for (uint32 guid : orphans)
        CharacterDatabase.PExecute("DELETE FROM wowlheim_container WHERE guid = %u", guid);
    orphans.clear();
    if (auto s = CharacterDatabase.Query("SELECT guid, door_state, bed_owner, bed_owner_name FROM wowlheim_piece_state"))
    {
        do
        {
            Field* f = s->Fetch();
            uint32 guid = f[0].GetUInt32();
            if (!DefForPiece(guid))
            {
                orphans.insert(guid);
                continue;
            }
            WLPieceUseState& st = m_states[guid];
            st.door = int8(f[1].GetInt32());
            st.bedOwner = f[2].GetUInt32();
            st.bedOwnerName = f[3].GetCppString();
        } while (s->NextRow());
    }
    for (uint32 guid : orphans)
        CharacterDatabase.PExecute("DELETE FROM wowlheim_piece_state WHERE guid = %u", guid);
    sLog.outString(">> Wowlheim: %u pièces utilisables (coffres, portes, lits), %u coffres (%u cases occupées), %u états",
                   uint32(m_defs.size()), uint32(m_chests.size()), items, uint32(m_states.size()));
}

WLPieceUseDef const* PieceUseMgr::DefForPiece(uint32 pieceGuid) const
{
    auto const& pieces = sBuildingMgr.Pieces();
    auto it = pieces.find(pieceGuid);
    if (it == pieces.end())
        return nullptr;
    auto d = m_defs.find(it->second.pieceId);
    return d == m_defs.end() ? nullptr : &d->second;
}

WLChest& PieceUseMgr::Chest(uint32 guid, WLPieceUseDef const& def)
{
    WLChest& c = m_chests[guid];
    size_t n = size_t(std::max<uint32>(1, def.width * def.height));
    if (c.slots.size() != n)
        c.slots.resize(n);
    return c;
}

// Container.Interact (IL 5–81) : m_checkGuardStone -> PrivateArea.CheckAccess (balise), puis CheckAccess(joueur) selon m_privacy
// (0 Private : créateur seulement, 1 Group : personne, 2 Public : tout le monde).
// Adaptation : les balises (PrivateArea) ne sont pas simulées ; un coffre est donc traité comme protégé par la balise de son
// bâtisseur : propriétaire (créateur de la pièce) et MJ seulement, quel que soit m_privacy.
bool PieceUseMgr::ChestAccess(Player* player, WLPiece const& piece, WLPieceUseDef const& /*def*/, std::string& err) const
{
    if (player->GetSession()->GetSecurity() >= SEC_GAMEMASTER || piece.ownerGuid == player->GetObjectGuid().GetCounter())
        return true;
    err = MSG_CANTOPEN;
    return false;
}

// Container.m_inUse (RPC_RequestOpen IL 66–150) : un seul joueur à la fois. Le coffre se libère quand celui qui l'a ouvert le ferme
// (chest close), s'éloigne au-delà de la distance d'interaction, change de carte ou se déconnecte.
bool PieceUseMgr::ChestInUse(uint32 guid, Player* player)
{
    auto it = m_chests.find(guid);
    if (it == m_chests.end() || !it->second.openBy || it->second.openBy == player->GetObjectGuid().GetCounter())
        return false;
    Player* other = ObjectAccessor::FindPlayer(ObjectGuid(HIGHGUID_PLAYER, it->second.openBy));
    auto pit = sBuildingMgr.Pieces().find(guid);
    if (other && pit != sBuildingMgr.Pieces().end() && other->GetMapId() == pit->second.map &&
        sBuildingMgr.DistToPiece2D(pit->second, other->GetPositionX(), other->GetPositionY()) <= INTERACT_DISTANCE + 1.0f)
        return true;
    it->second.openBy = 0;
    return false;
}

// CH|guid|nom|largeur|hauteur|privacy|cases occupées  puis  CI|guid|case|objet|nombre|durabilité|durabilité max  puis  CE|guid
void PieceUseMgr::SendChest(Player* player, uint32 guid, WLPieceUseDef const& def)
{
    ChatHandler h(player->GetSession());
    WLChest& c = Chest(guid, def);
    uint32 used = 0;
    for (WLChestSlot const& s : c.slots)
        used += s.item ? 1 : 0;
    Api(&h, "CH|" + std::to_string(guid) + "|" + def.name + "|" + std::to_string(def.width) + "|" + std::to_string(def.height) + "|" +
            std::to_string(def.privacy) + "|" + std::to_string(used));
    for (size_t i = 0; i < c.slots.size(); ++i)
    {
        WLChestSlot const& s = c.slots[i];
        if (!s.item)
            continue;
        ItemPrototype const* p = ObjectMgr::GetItemPrototype(s.item);
        Api(&h, "CI|" + std::to_string(guid) + "|" + std::to_string(i) + "|" + std::to_string(s.item) + "|" + std::to_string(s.count) + "|" +
                std::to_string(s.durability) + "|" + std::to_string(p ? p->MaxDurability : 0));
    }
    Api(&h, "CE|" + std::to_string(guid));
}

// Coffre et sacs du joueur enregistrés dans la même transaction : un objet déplacé ne peut ni disparaître ni se dédoubler
// si le serveur s'arrête entre deux sauvegardes du personnage.
void PieceUseMgr::SaveChest(uint32 guid, Player* player)
{
    auto it = m_chests.find(guid);
    CharacterDatabase.BeginTransaction();
    if (player)
        player->SaveInventoryAndGoldToDB();
    CharacterDatabase.PExecute("DELETE FROM wowlheim_container WHERE guid = %u", guid);
    if (it != m_chests.end())
        for (size_t i = 0; i < it->second.slots.size(); ++i)
        {
            WLChestSlot const& s = it->second.slots[i];
            if (s.item && s.count)
                CharacterDatabase.PExecute("INSERT INTO wowlheim_container (guid, slot, item_id, `count`, durability, random_property, bound) VALUES (%u, %u, %u, %u, %u, %i, %u)",
                                           guid, uint32(i), s.item, s.count, s.durability, s.randomProp, s.bound ? 1u : 0u);
        }
    CharacterDatabase.CommitTransaction();
}

void PieceUseMgr::SaveState(uint32 guid)
{
    auto it = m_states.find(guid);
    if (it == m_states.end())
        return;
    std::string name = it->second.bedOwnerName;
    CharacterDatabase.escape_string(name);
    CharacterDatabase.PExecute("REPLACE INTO wowlheim_piece_state (guid, door_state, bed_owner, bed_owner_name) VALUES (%u, %i, %u, '%s')",
                               guid, int32(it->second.door), it->second.bedOwner, name.c_str());
}

// Inventory.AddItem (Valheim) : un objet empilable complète d'abord les piles identiques du coffre, puis occupe la première case
// libre (de gauche à droite, de haut en bas) ; toSlot >= 0 : case visée (vide, ou pile du même objet). Renvoie le nombre déposé.
uint32 PieceUseMgr::PutItem(Player* player, uint32 guid, WLPieceUseDef const& def, uint8 bag, uint8 slot, uint32 count, int32 toSlot, std::string& err)
{
    Item* it = player->GetItemByPos(bag, slot);
    if (!it || !Player::IsInventoryPos(bag, slot))
    {
        err = "Aucun objet à cet emplacement.";
        return 0;
    }
    ItemPrototype const* proto = it->GetProto();
    bool chargesChanged = false;
    for (uint8 i = 0; i < MAX_ITEM_PROTO_SPELLS; ++i)
        chargesChanged = chargesChanged || it->GetSpellCharges(i) != proto->Spells[i].SpellCharges;
    bool enchanted = false;
    for (uint32 e = 0; e < MAX_ENCHANTMENT_SLOT; ++e)
        enchanted = enchanted || it->GetEnchantmentId(EnchantmentSlot(e)) != 0;
    // objets dont le coffre ne garderait pas tout l'état : sacs, objets enchantés, temporaires, à charges entamées, avec texte, emballés
    if (it->IsBag() || it->IsInTrade() || enchanted || chargesChanged || it->GetUInt32Value(ITEM_FIELD_DURATION) ||
        it->GetUInt32Value(ITEM_FIELD_ITEM_TEXT_ID) || it->HasFlag(ITEM_FIELD_FLAGS, ITEM_DYNFLAG_WRAPPED))
    {
        err = MSG_WRONGITEM;
        return 0;
    }
    WLChestSlot src;
    src.item = it->GetEntry();
    src.durability = proto->MaxDurability ? it->GetUInt32Value(ITEM_FIELD_DURABILITY) : 0;
    src.randomProp = it->GetItemRandomPropertyId();
    src.bound = it->IsSoulBound();
    uint32 want = count ? std::min(count, it->GetCount()) : it->GetCount();
    uint32 maxStack = MaxStack(src.item);

    WLChest& c = Chest(guid, def);
    std::vector<std::pair<size_t, uint32>> plan;          // (case, quantité ajoutée)
    uint32 left = want;
    if (toSlot >= 0)
    {
        if (size_t(toSlot) >= c.slots.size())
        {
            err = "Case inconnue.";
            return 0;
        }
        WLChestSlot const& d = c.slots[toSlot];
        if (d.item && !SameStack(d, src))
        {
            err = "Case occupée.";
            return 0;
        }
        uint32 room = d.item ? (maxStack > d.count ? maxStack - d.count : 0) : maxStack;
        uint32 n = std::min(left, room);
        if (n)
            plan.emplace_back(size_t(toSlot), n);
        left -= n;
    }
    else
    {
        for (size_t i = 0; i < c.slots.size() && left; ++i)       // piles identiques d'abord
        {
            WLChestSlot const& d = c.slots[i];
            if (d.item && SameStack(d, src) && d.count < maxStack)
            {
                uint32 n = std::min(left, maxStack - d.count);
                plan.emplace_back(i, n);
                left -= n;
            }
        }
        for (size_t i = 0; i < c.slots.size() && left; ++i)       // puis cases libres
            if (!c.slots[i].item)
            {
                uint32 n = std::min(left, maxStack);
                plan.emplace_back(i, n);
                left -= n;
            }
    }
    uint32 placed = want - left;
    if (!placed)
    {
        err = MSG_FULL;
        return 0;
    }
    uint32 destroy = placed;
    player->DestroyItemCount(*it, destroy, true);           // it peut être détruit ici
    for (auto const& pl : plan)
    {
        WLChestSlot& d = c.slots[pl.first];
        if (!d.item)
        {
            d = src;
            d.count = 0;
        }
        d.count += pl.second;
    }
    return placed;
}

// Sortie d'une case vers les sacs du joueur (ce qui ne rentre pas reste dans le coffre). Renvoie le nombre pris.
uint32 PieceUseMgr::TakeSlot(Player* player, uint32 guid, uint32 slot, uint32 count, std::string& err)
{
    auto cit = m_chests.find(guid);
    if (cit == m_chests.end() || slot >= cit->second.slots.size() || !cit->second.slots[slot].item)
    {
        err = "Case vide.";
        return 0;
    }
    WLChestSlot& s = cit->second.slots[slot];
    ItemPrototype const* proto = ObjectMgr::GetItemPrototype(s.item);
    if (!proto)
    {
        err = "Objet inconnu.";
        return 0;
    }
    uint32 want = count ? std::min(count, s.count) : s.count;
    ItemPosCountVec dest;
    uint32 noSpace = 0;
    InventoryResult res = player->CanStoreNewItem(NULL_BAG, NULL_SLOT, dest, s.item, want, &noSpace);
    uint32 n = (res == EQUIP_ERR_OK) ? want : want - std::min(want, noSpace);
    if (!n || dest.empty())
    {
        err = MSG_NOROOM;
        return 0;
    }
    Item* item = player->StoreNewItem(dest, s.item, true, s.randomProp);
    if (!item)
    {
        err = MSG_NOROOM;
        return 0;
    }
    if (proto->MaxDurability)
        item->SetUInt32Value(ITEM_FIELD_DURABILITY, std::min<uint32>(s.durability, proto->MaxDurability));
    if (s.bound)
        item->SetBinding(true);
    player->SendNewItem(item, n, true, false);
    s.count -= n;
    if (!s.count)
        s = WLChestSlot();
    return n;
}

bool PieceUseMgr::OnUse(Player* player, uint32 pieceGuid)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    WLPieceUseDef const* def = DefForPiece(pieceGuid);
    if (!def)
        return false;
    WLPiece const piece = sBuildingMgr.Pieces().at(pieceGuid);
    ChatHandler h(player->GetSession());
    if (def->kind == "container")
    {
        std::string err;
        if (!ChestAccess(player, piece, *def, err))
        {
            Api(&h, "E|" + err);
            return true;
        }
        if (ChestInUse(pieceGuid, player))
        {
            Api(&h, std::string("E|") + MSG_INUSE);
            return true;
        }
        Chest(pieceGuid, *def).openBy = player->GetObjectGuid().GetCounter();
        SendChest(player, pieceGuid, *def);
        Api(&h, "OPEN|chest|" + std::to_string(pieceGuid));       // InventoryGui.Show(container) : dernière ligne
        return true;
    }
    if (def->kind == "door")
    {
        UseDoor(player, piece, *def);
        return true;
    }
    if (def->kind == "bed")
    {
        UseBed(player, piece, *def);
        return true;
    }
    return false;
}

bool PieceUseMgr::CanBeRemoved(uint32 pieceGuid, std::string& err)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    WLPieceUseDef const* def = DefForPiece(pieceGuid);
    if (!def || def->kind != "container" || def->privacy != 0)   // Container.CanBeRemoved IL 0–25 : seul un coffre privé non vide refuse
        return true;
    auto it = m_chests.find(pieceGuid);
    if (it == m_chests.end())
        return true;
    for (WLChestSlot const& s : it->second.slots)
        if (s.item)
        {
            err = MSG_CANTREMOVENOW;
            return false;
        }
    return true;
}

// Container.OnDestroyed -> DropAllItems (IL 0–163) : tout le contenu tombe au sol. Adaptation : au démolisseur (sacs), le reste par
// courrier au propriétaire (effondrement : tout par courrier), avec la durabilité et la liaison de chaque objet.
void PieceUseMgr::OnPieceRemoved(uint32 pieceGuid, Player* to, uint32 ownerGuid)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    auto cit = m_chests.find(pieceGuid);
    if (cit != m_chests.end())
    {
        std::vector<WLChestSlot> overflow;
        for (WLChestSlot& s : cit->second.slots)
        {
            if (!s.item)
                continue;
            if (to)
            {
                std::string err;
                uint32 idx = uint32(&s - &cit->second.slots[0]);
                while (s.item && TakeSlot(to, pieceGuid, idx, 0, err))
                    ;
            }
            if (s.item)
                overflow.push_back(s);
        }
        if (to)
            to->SaveInventoryAndGoldToDB();
        if (!overflow.empty())
        {
            ObjectGuid receiver(HIGHGUID_PLAYER, ownerGuid);
            MailDraft* draft = nullptr;
            uint32 attached = 0;
            auto flush = [&]()
            {
                if (!draft)
                    return;
                draft->SendMailTo(MailReceiver(ObjectAccessor::FindPlayer(receiver), receiver), MailSender(MailMessageType(MAIL_NORMAL), uint32(0)));
                delete draft;
                draft = nullptr;
                attached = 0;
            };
            for (WLChestSlot const& s : overflow)
            {
                Item* item = Item::CreateItem(s.item, s.count, nullptr, uint32(s.randomProp));
                if (!item)
                    continue;
                if (ItemPrototype const* p = ObjectMgr::GetItemPrototype(s.item))
                    if (p->MaxDurability)
                        item->SetUInt32Value(ITEM_FIELD_DURABILITY, std::min<uint32>(s.durability, p->MaxDurability));
                if (s.bound)
                    item->SetBinding(true);
                item->SaveToDB();
                if (!draft)
                    draft = new MailDraft("Contenu du coffre", std::string("Coffre démoli : son contenu vous est rendu."));
                draft->AddItem(item);
                if (++attached >= 12)
                    flush();
            }
            flush();
        }
        CharacterDatabase.PExecute("DELETE FROM wowlheim_container WHERE guid = %u", pieceGuid);
        m_chests.erase(cit);
    }
    if (m_states.erase(pieceGuid))
        CharacterDatabase.PExecute("DELETE FROM wowlheim_piece_state WHERE guid = %u", pieceGuid);
}

// ---------------------------------------------------------------------------------------------------------------------------
// Portes (Door) : Interact (IL 0–461) -> Open(direction du joueur) -> RPC_UseDoor (IL 0–115). État 0 = fermée ; à l'ouverture,
// 1 si le joueur est derrière la porte (Dot(transform.forward, joueur − porte) < 0), −1 sinon : le battant s'écarte du joueur.
// Adaptation : les modèles de Wowlheim n'ont pas d'animation d'ouverture ; le GameObject entier tourne de 90° autour de ses gonds
// (bout −y local du battant, la largeur de la porte étant sur l'axe local y) et sa position est enregistrée (table gameobject).
void PieceUseMgr::DoorPose(WLPiece const& piece, int8 state, float& x, float& y, float& o) const
{
    x = piece.x;
    y = piece.y;
    o = piece.o;
    if (!state)
        return;
    WLPieceTemplate const* t = sBuildingMgr.FindTemplate(piece.pieceId);
    float h = (t ? t->sy : 2.0f) * 0.5f;
    float c = std::cos(piece.o), s = std::sin(piece.o);
    float hx = piece.x + h * s, hy = piece.y - h * c;      // gonds = repère de la pièce (0, −h)
    o = piece.o + (state > 0 ? -0.5f * PI : 0.5f * PI);
    x = hx - h * std::sin(o);
    y = hy + h * std::cos(o);
    o = std::fmod(o, 2.0f * PI);
    if (o < 0)
        o += 2.0f * PI;
}

void PieceUseMgr::ApplyDoorPose(Map* map, WLPiece const& piece, int8 state) const
{
    float x, y, o;
    DoorPose(piece, state, x, y, o);
    GameObjectData const* data = sObjectMgr.GetGOData(piece.guid);
    if (!data)
        return;
    GameObject* go = (map && map->GetId() == piece.map) ? map->GetGameObject(ObjectGuid(HIGHGUID_GAMEOBJECT, data->id, piece.guid)) : nullptr;
    sObjectMgr.RemoveGameobjectFromGrid(piece.guid, data);
    if (go && go->IsInWorld())
    {
        // même chemin que .gobject move (Level2.cpp) : retiré de la carte (disparaît chez les clients), déplacé, remis (réapparaît)
        map->Remove(go, false);
        go->Relocate(x, y, piece.z, o);
        go->SetFloatValue(GAMEOBJECT_POS_X, x);
        go->SetFloatValue(GAMEOBJECT_POS_Y, y);
        go->SetFloatValue(GAMEOBJECT_POS_Z, piece.z);
        go->UpdateRotationFields();
        map->Add(go);
        go->SaveToDB();                                    // GameObjectData + table gameobject
    }
    else
    {
        GameObjectData& d = sObjectMgr.NewGOData(piece.guid);
        d.posX = x;
        d.posY = y;
        d.orientation = o;
        d.rotation0 = 0.0f;
        d.rotation1 = 0.0f;
        d.rotation2 = std::sin(o * 0.5f);
        d.rotation3 = std::cos(o * 0.5f);
        WorldDatabase.PExecute("UPDATE gameobject SET position_x = %f, position_y = %f, orientation = %f, rotation0 = 0, rotation1 = 0, rotation2 = %f, rotation3 = %f WHERE guid = %u",
                               x, y, o, d.rotation2, d.rotation3, piece.guid);
    }
    sObjectMgr.AddGameobjectToGrid(piece.guid, sObjectMgr.GetGOData(piece.guid));
}

void PieceUseMgr::UseDoor(Player* player, WLPiece const& piece, WLPieceUseDef const& def)
{
    ChatHandler h(player->GetSession());
    WLPieceUseState& st = m_states[piece.guid];
    // CanInteract (IL 0–102) : une porte à clé ou qui ne se referme pas (m_canNotBeClosed) n'est plus utilisable une fois ouverte
    if ((def.keyItem || def.canNotBeClosed) && st.door != 0)
        return;
    // m_checkGuardStone : balises non simulées -> tout le monde peut ouvrir (aucune balise ne protège la porte)
    if (def.keyItem)                                       // HaveKey / m_consumeKey (IL 50–366)
    {
        if (!player->GetItemCount(def.keyItem))
        {
            Api(&h, "E|" + std::string(MSG_NEEDKEY) + ItemName(def.keyItem));
            return;
        }
        if (def.consumeKey)
            player->DestroyItemCount(def.keyItem, 1, true);
        Api(&h, "M|" + std::string(MSG_USINGKEY) + ItemName(def.keyItem));
    }
    if (st.door == 0)
    {
        float fx = std::cos(piece.o), fy = std::sin(piece.o);        // transform.forward (Unity z = x local WoW)
        float dx = player->GetPositionX() - piece.x, dy = player->GetPositionY() - piece.y;
        st.door = (fx * dx + fy * dy < 0.0f) ? 1 : -1;
    }
    else
        st.door = 0;
    ApplyDoorPose(player->GetMap(), piece, st.door);
    SaveState(piece.guid);
    Api(&h, "DR|" + std::to_string(piece.guid) + "|" + std::to_string(int32(st.door)));
}

bool PieceUseMgr::OpenDoorBox(WLPiece const& p, WLBox& box) const
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    auto it = m_states.find(p.guid);
    if (it == m_states.end() || it->second.door == 0)
        return false;
    float x, y, o;
    DoorPose(p, it->second.door, x, y, o);
    box.cx = x;
    box.cy = y;
    box.yaw = o;
    return true;
}

// ---------------------------------------------------------------------------------------------------------------------------
// Lits (Bed.Interact IL 0–349) : lit sans propriétaire -> CheckExposure, propriétaire = joueur, point d'apparition = lit,
// « Point de réapparition créé ». Lit du joueur -> (dormir, non repris) / CheckExposure puis point d'apparition. Lit d'un autre :
// rien. CheckExposure (IL 0–100) : Cover.GetCoverForPoint(spawnPoint) -> toit obligatoire, couverture >= 0,8. Le feu proche
// (CheckFire), l'humidité (CheckWet) et les ennemis (CheckEnemies) ne servent qu'à dormir.
// Adaptation : point d'apparition de Valheim = foyer (homebind) du personnage, comme une auberge.
void PieceUseMgr::BedSpawnPoint(WLPiece const& piece, float& x, float& y, float& z) const
{
    x = piece.x;
    y = piece.y;
    z = piece.z + BED_SPAWN_HEIGHT;
}

void PieceUseMgr::UseBed(Player* player, WLPiece const& piece, WLPieceUseDef const& /*def*/)
{
    ChatHandler h(player->GetSession());
    WLPieceUseState& st = m_states[piece.guid];
    uint32 me = player->GetObjectGuid().GetCounter();
    if (st.bedOwner && st.bedOwner != me)
    {
        Api(&h, "M|Lit de " + st.bedOwnerName);           // Valheim : Interact sans effet ; survol « <nom>'s $piece_bed »
        return;
    }
    float x, y, z;
    BedSpawnPoint(piece, x, y, z);
    float pct = 0.0f;
    bool roof = false;
    sBuildingMgr.GetCover(piece.map, x, y, z, pct, roof, piece.guid);
    if (!roof)
    {
        Api(&h, std::string("E|") + MSG_BEDNEEDROOF);
        return;
    }
    if (pct < BED_EXPOSURE_MIN)
    {
        Api(&h, std::string("E|") + MSG_BEDTOOEXPOSED);
        return;
    }
    if (!st.bedOwner)
    {
        st.bedOwner = me;                                  // SetOwner(id, nom)
        st.bedOwnerName = player->GetName();
        SaveState(piece.guid);
    }
    uint32 area = player->GetMap()->GetTerrain()->GetAreaId(x, y, z);
    player->SetHomebindToLocation(WorldLocation(piece.map, x, y, z, piece.o), area);
    WorldPacket data(SMSG_BINDPOINTUPDATE, 5 * 4);         // même paquet que Spell::EffectBind (pierre de foyer)
    data << float(x) << float(y) << float(z) << uint32(piece.map) << uint32(area);
    player->SendDirectMessage(data);
    Api(&h, std::string("M|") + MSG_SPAWNPOINTSET);
    Api(&h, "BD|" + std::to_string(piece.guid) + "|" + std::to_string(me));
}

// ---------------------------------------------------------------------------------------------------------------------------
// .build api chest open|close|put|putitem|take|takeall|stackall|move <guid> ...
//   open <guid>                          : CH| / CI| / CE| puis OPEN|chest|guid (même chose qu'un clic sur le coffre)
//   close <guid>                         : libère le coffre (Container.SetInUse(false))
//   put <guid> <sac> <case> [nombre] [case du coffre] : dépose depuis un emplacement Lua (sac 0 = sac à dos, cases depuis 1)
//   putitem <guid> <objet> [nombre]      : dépose un objet pris n'importe où dans les sacs
//   take <guid> <case> [nombre]          : reprend une case (0 .. largeur × hauteur − 1)
//   takeall <guid>                       : Container.TakeAll (« Prendre tout »)
//   stackall <guid>                      : Container.StackAll (« Objets similaires » : dépose ce que le coffre contient déjà)
//   move <guid> <de> <vers>              : déplace / échange / complète deux cases du coffre
// Chaque commande qui modifie le coffre renvoie son contenu (CH| CI| CE|) ; A|nombre déplacé.
bool PieceUseMgr::HandleChestCommand(ChatHandler* h, Player* player, char* args)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    std::vector<std::string> a;
    {
        std::stringstream ss(args ? args : "");
        std::string t;
        while (ss >> t)
            a.push_back(t);
    }
    if (a.size() < 2)
    {
        Api(h, "E|usage : chest open|close|put|putitem|take|takeall|stackall|move <guid> ...");
        return false;
    }
    auto num = [&](size_t i, long def) -> long { return a.size() > i ? std::strtol(a[i].c_str(), nullptr, 10) : def; };
    std::string sub = a[0];
    uint32 guid = uint32(std::strtoul(a[1].c_str(), nullptr, 10));
    WLPieceUseDef const* def = DefForPiece(guid);
    if (!def || def->kind != "container")
    {
        Api(h, "E|Aucun coffre.");
        return false;
    }
    WLPiece const& piece = sBuildingMgr.Pieces().at(guid);
    if (sub == "close")
    {
        WLChest& c = Chest(guid, *def);
        if (c.openBy == player->GetObjectGuid().GetCounter())
            c.openBy = 0;
        return true;
    }
    std::string err;
    if (!ChestAccess(player, piece, *def, err))
    {
        Api(h, "E|" + err);
        return false;
    }
    if (piece.map != player->GetMapId() || sBuildingMgr.DistToPiece2D(piece, player->GetPositionX(), player->GetPositionY()) > INTERACT_DISTANCE
        || sBuildingMgr.VerticalGap(piece, player->GetPositionZ()) > INTERACT_DISTANCE)
    {
        Api(h, "E|Trop loin.");                          // InventoryGui : le coffre se ferme quand on s'éloigne
        Api(h, "CX|" + std::to_string(guid));
        return false;
    }
    if (ChestInUse(guid, player))
    {
        Api(h, std::string("E|") + MSG_INUSE);
        return false;
    }
    WLChest& c = Chest(guid, *def);
    c.openBy = player->GetObjectGuid().GetCounter();
    uint32 moved = 0;
    bool changed = false;
    if (sub == "open")
    {
        SendChest(player, guid, *def);
        Api(h, "OPEN|chest|" + std::to_string(guid));
        return true;
    }
    else if (sub == "put")
    {
        uint8 bag, slot;
        if (!LuaToServerPos(uint32(num(2, 0)), uint32(num(3, 0)), bag, slot))
            err = "Emplacement invalide.";
        else
            moved = PutItem(player, guid, *def, bag, slot, uint32(std::max(0L, num(4, 0))), int32(num(5, -1)), err);
    }
    else if (sub == "putitem")
    {
        uint32 entry = uint32(num(2, 0));
        uint32 want = uint32(std::max(0L, num(3, 0)));
        std::vector<std::pair<uint8, uint8>> pos;
        ForEachBagItem(player, [&](Item* it, uint8 b, uint8 s) { if (it->GetEntry() == entry) pos.emplace_back(b, s); });
        if (pos.empty())
            err = "Vous n'avez pas de " + ItemName(entry);
        for (auto const& p : pos)
        {
            uint32 n = PutItem(player, guid, *def, p.first, p.second, want ? want - moved : 0, -1, err);
            moved += n;
            if (!n || (want && moved >= want))
                break;
        }
    }
    else if (sub == "take")
    {
        long slot = num(2, -1);
        moved = slot < 0 ? 0 : TakeSlot(player, guid, uint32(slot), uint32(std::max(0L, num(3, 0))), err);
        if (slot < 0)
            err = "Case inconnue.";
    }
    else if (sub == "takeall")
    {
        // Container.TakeAll -> Inventory.MoveAll : toutes les cases, dans l'ordre, tant que les sacs ont de la place
        for (uint32 i = 0; i < c.slots.size(); ++i)
            if (c.slots[i].item)
                moved += TakeSlot(player, guid, i, 0, err);
        if (moved && err == MSG_NOROOM)
            Api(h, std::string("E|") + MSG_NOROOM);
    }
    else if (sub == "stackall")
    {
        // Container.StackAll -> Inventory.StackAll : les objets des sacs dont le coffre a déjà un exemplaire y sont déposés
        std::set<uint32> inChest;
        for (WLChestSlot const& s : c.slots)
            if (s.item)
                inChest.insert(s.item);
        std::vector<std::pair<uint8, uint8>> pos;
        ForEachBagItem(player, [&](Item* it, uint8 b, uint8 s) { if (inChest.count(it->GetEntry())) pos.emplace_back(b, s); });
        for (auto const& p : pos)
            moved += PutItem(player, guid, *def, p.first, p.second, 0, -1, err);
    }
    else if (sub == "move")
    {
        long from = num(2, -1), to = num(3, -1);
        if (from < 0 || to < 0 || size_t(from) >= c.slots.size() || size_t(to) >= c.slots.size() || !c.slots[from].item || from == to)
            err = "Case inconnue.";
        else
        {
            WLChestSlot& s = c.slots[from];
            WLChestSlot& d = c.slots[to];
            uint32 maxStack = MaxStack(s.item);
            if (d.item && SameStack(d, s) && d.count < maxStack)
            {
                uint32 n = std::min(s.count, maxStack - d.count);  // compléter la pile visée
                d.count += n;
                s.count -= n;
                if (!s.count)
                    s = WLChestSlot();
                moved = n;
            }
            else
            {
                std::swap(s, d);                           // case vide ou objet différent : échange
                moved = d.count;
            }
            changed = true;
        }
    }
    else
    {
        Api(h, "E|commande inconnue");
        return false;
    }
    changed = changed || moved > 0;
    if (changed)
        SaveChest(guid, sub == "move" ? nullptr : player);
    if (!moved && !err.empty())
        Api(h, "E|" + err);
    Api(h, "A|" + std::to_string(moved));
    SendChest(player, guid, *def);
    return moved > 0;
}

// .build api piece state <guid>  -> PS|guid|kind|porte|propriétaire du lit|nom
// .build api piece combat on|off -> (MJ, tests) met le personnage en combat (environ 5 s) / l'en sort
bool PieceUseMgr::HandlePieceCommand(ChatHandler* h, Player* player, char* args)
{
    std::lock_guard<std::recursive_mutex> g(m_lock);
    std::vector<std::string> a;
    {
        std::stringstream ss(args ? args : "");
        std::string t;
        while (ss >> t)
            a.push_back(t);
    }
    if (a.size() >= 2 && a[0] == "state")
    {
        uint32 guid = uint32(std::strtoul(a[1].c_str(), nullptr, 10));
        WLPieceUseDef const* def = DefForPiece(guid);
        if (!def)
        {
            Api(h, "E|Pièce sans usage.");
            return false;
        }
        WLPieceUseState st;
        auto it = m_states.find(guid);
        if (it != m_states.end())
            st = it->second;
        Api(h, "PS|" + std::to_string(guid) + "|" + def->kind + "|" + std::to_string(int32(st.door)) + "|" + std::to_string(st.bedOwner) + "|" + st.bedOwnerName);
        return true;
    }
    if (a.size() >= 2 && a[0] == "combat" && player->GetSession()->GetSecurity() >= SEC_GAMEMASTER)
    {
        if (a[1] == "on")
            player->SetInCombatState(true);                // minuterie de combat (5 s) comme après un coup en JcJ
        else
            player->ClearInCombat();
        Api(h, std::string("M|") + (player->IsInCombat() ? "En combat." : "Hors combat."));
        return true;
    }
    Api(h, "E|usage : piece state <guid> | piece combat on|off");
    return false;
}

// ---------------------------------------------------------------------------------------------------------------------------
void Wowlheim_PieceUseLoad() { sPieceUseMgr.Load(); }
bool Wowlheim_PieceUse(Player* player, uint32 pieceGuid) { return player && sPieceUseMgr.OnUse(player, pieceGuid); }
bool Wowlheim_PieceCanBeRemoved(uint32 pieceGuid, std::string& err) { return sPieceUseMgr.CanBeRemoved(pieceGuid, err); }
void Wowlheim_PieceUseRemoved(uint32 pieceGuid, Player* to, uint32 ownerGuid) { sPieceUseMgr.OnPieceRemoved(pieceGuid, to, ownerGuid); }
bool Wowlheim_OpenDoorBox(WLPiece const& p, WLBox& box) { return sPieceUseMgr.OpenDoorBox(p, box); }
bool Wowlheim_ChestCommand(ChatHandler* h, Player* player, char* args) { return player && sPieceUseMgr.HandleChestCommand(h, player, args); }
bool Wowlheim_PieceCommand(ChatHandler* h, Player* player, char* args) { return player && sPieceUseMgr.HandlePieceCommand(h, player, args); }

bool Wowlheim_RefuseInCombat(Player* player, std::string& err)
{
    if (!player || !player->IsInCombat())
        return false;
    err = MSG_COMBAT;
    return true;
}
