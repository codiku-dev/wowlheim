"""Applique (une seule fois) les modifications « niveaux de station et extensions » aux sources Wowlheim.
Script d'aide ponctuel ; idempotent (sans effet s'il a déjà été appliqué)."""
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def rd(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def wr(rel, s):
    open(os.path.join(ROOT, rel), "w", encoding="utf-8").write(s)


def rep(s, old, new, name):
    if new in s:
        return s
    assert old in s, name
    return s.replace(old, new, 1)


# --- SQL 007 : niveaux de station proposés
s = rd("server/sql/world/007_tools_recipes.sql")
if "min_station_level" not in s:
    s += """
-- Niveau de station requis (Recipe.m_minStationLevel). Valeurs = PROPOSITION de conception : le DLL ne contient pas les recettes
-- (données de prefabs Unity, docs/VALHEIM_RULES.md 8.9). Forge : 3 extensions possibles -> niveau max 4 ; établi : 2 -> niveau max 3.
UPDATE `wowlheim_recipe` SET `min_station_level` = 2 WHERE `id` IN (105, 106);
UPDATE `wowlheim_recipe` SET `min_station_level` = 3 WHERE `id` IN (107, 108);
UPDATE `wowlheim_recipe` SET `min_station_level` = 4 WHERE `id` IN (109, 110);
"""
    wr("server/sql/world/007_tools_recipes.sql", s)

# --- BuildingMgr.h
s = rd("server/Wowlheim/BuildingMgr.h")
s = rep(s, "    float sx = 1, sy = 1, sz = 1; // boîte logique (m) : x/y locaux, z hauteur ; base au niveau de la position de la pièce\n",
        "    float sx = 1, sy = 1, sz = 1; // boîte logique (m) : x/y locaux, z hauteur ; base au niveau de la position de la pièce\n"
        "    std::string extStation;      // kind=extension : station visée (workbench, forge)\n"
        "    float extDistance = 5.0f;    // StationExtension.m_maxStationDistance (docs/VALHEIM_RULES.md 8)\n"
        "    bool extStack = false;       // StationExtension.m_stack\n", "h1")
s = rep(s, "    uint32 outputCount = 1;\n    std::vector<WLItemCount> ingredients;",
        "    uint32 outputCount = 1;\n    uint32 minStationLevel = 1;  // Recipe.m_minStationLevel\n    std::vector<WLItemCount> ingredients;", "h2")
s = rep(s, "        // CraftingStation.CheckUsable : toit au-dessus et couverture >= 0,7",
        "        // CraftingStation.GetLevel : 1 + extensions comptées (distance 3D < m_maxStationDistance de l'extension, une par type sauf m_stack)\n"
        "        uint32 StationLevel(WLPiece const& station) const;\n"
        "        // CraftingStation.CheckUsable : toit au-dessus et couverture >= 0,7", "h3")
wr("server/Wowlheim/BuildingMgr.h", s)

# --- BuildingMgr.cpp : chargement
s = rd("server/Wowlheim/BuildingMgr.cpp")
s = rep(s, "max_health, supports, requires_workbench, kind, sx, sy, sz FROM wowlheim_piece_template",
        "max_health, supports, requires_workbench, kind, sx, sy, sz, ext_station, ext_distance, ext_stack FROM wowlheim_piece_template", "c1")
s = rep(s, "        t.sz = f[10].GetFloat();\n",
        "        t.sz = f[10].GetFloat();\n        t.extStation = f[11].GetCppString();\n        t.extDistance = f[12].GetFloat();\n        t.extStack = f[13].GetUInt32() != 0;\n", "c2")
s = rep(s, "SELECT id, name, station, output_item, output_count FROM wowlheim_recipe",
        "SELECT id, name, station, output_item, output_count, min_station_level FROM wowlheim_recipe", "c3")
s = rep(s, "            rc.outputCount = f[4].GetUInt32();\n",
        "            rc.outputCount = f[4].GetUInt32();\n            rc.minStationLevel = std::max<uint32>(1, f[5].GetUInt32());\n", "c4")
wr("server/Wowlheim/BuildingMgr.cpp", s)

# --- Geometry.cpp : StationLevel
s = rd("server/Wowlheim/Geometry.cpp")
if "StationLevel" not in s:
    s = s.replace("#include <cmath>", "#include <cmath>\n#include <set>", 1)
    s += """
// CraftingStation.GetLevel (docs/VALHEIM_RULES.md 8) : 1 + nombre d'extensions comptées.
// Une extension compte si sa distance 3D à la station est < son m_maxStationDistance, si elle vise cette station, et si son type
// n'est pas déjà compté (sauf m_stack). Le type d'une extension = son modèle de pièce (Piece.m_name).
uint32 BuildingMgr::StationLevel(WLPiece const& station) const
{
    WLPieceTemplate const* st = FindTemplate(station.pieceId);
    if (!st)
        return 1;
    uint32 level = 1;
    std::set<uint32> seenTypes;
    for (auto const& kv : m_pieces)
    {
        WLPiece const& p = kv.second;
        if (p.map != station.map)
            continue;
        WLPieceTemplate const* t = FindTemplate(p.pieceId);
        if (!t || t->kind != "extension" || t->extStation != st->kind)
            continue;
        float dx = p.x - station.x, dy = p.y - station.y, dz = p.z - station.z;
        if (std::sqrt(dx * dx + dy * dy + dz * dz) >= t->extDistance)
            continue;
        if (!t->extStack && !seenTypes.insert(t->id).second)
            continue;
        ++level;
    }
    return level;
}
"""
    wr("server/Wowlheim/Geometry.cpp", s)

# --- BuildCommands.cpp
s = rd("server/Wowlheim/BuildCommands.cpp")
old = "    // station requise à portée (Player.HaveRequirements : HaveBuildStationInRange, docs 3.4)"
new = ("    // extension : il faut une station compatible à moins de m_maxStationDistance de l'emplacement (statut Valheim ExtensionMissingStation, docs 3.2 point 1)\n"
       "    if (tpl->kind == \"extension\" && !noCost && !sBuildingMgr.FindStationInRange(player->GetMap(), x, y, tpl->extStation, tpl->extDistance))\n"
       "    {\n"
       "        PSendSysMessage(\"Pose refusée : il faut une station (%s) à moins de %.0f m de l'emplacement.\", tpl->extStation.c_str(), tpl->extDistance);\n"
       "        SetSentErrorMessage(true);\n"
       "        return false;\n"
       "    }\n\n") + old
s = rep(s, old, new, "b1")
old = ('    bool usable = sBuildingMgr.StationUsable(*st, pct);\n'
       '    WLRaw(this, "S|" + std::to_string(st->guid) + "|" + (usable ? "1" : "0") + "|" + std::to_string(int(pct * 100.0f)));\n')
new = ('    bool usable = sBuildingMgr.StationUsable(*st, pct);\n'
       '    uint32 level = sBuildingMgr.StationLevel(*st);\n'
       '    WLRaw(this, "S|" + std::to_string(st->guid) + "|" + (usable ? "1" : "0") + "|" + std::to_string(int(pct * 100.0f)) + "|" + std::to_string(level));\n')
s = rep(s, old, new, "b2")
s = rep(s, 'PSendSysMessage("Établi %u : couverture %.0f %% (seuil 70 %%), %s.", st->guid, pct * 100.0f,',
        'PSendSysMessage("Établi %u : niveau %u, couverture %.0f %% (seuil 70 %%), %s.", st->guid, level, pct * 100.0f,', "b3")
old = ("    std::string missing;\n    if (!sBuildingMgr.HasItems(player, r->ingredients, missing))\n    {\n"
       "        PSendSysMessage(\"Ressources manquantes : %s.\", missing.c_str());\n        SetSentErrorMessage(true);\n        return false;\n    }\n"
       "    sBuildingMgr.ConsumeItems(player, r->ingredients);")
new = ("    // niveau de station requis (Recipe.m_minStationLevel ; niveau = 1 + extensions, docs 8)\n"
       "    uint32 stationLevel = sBuildingMgr.StationLevel(*st);\n"
       "    if (stationLevel < r->minStationLevel)\n"
       "    {\n"
       "        PSendSysMessage(\"Niveau de station insuffisant (%u, il faut %u) : posez des extensions à moins de 5 m.\", stationLevel, r->minStationLevel);\n"
       "        SetSentErrorMessage(true);\n"
       "        return false;\n"
       "    }\n") + old
s = rep(s, old, new, "b4")
s = rep(s, 'PSendSysMessage("  %u  %s -> %u x %s  [%s]", r.id, r.name.c_str(), r.outputCount, ItemName(r.outputItem).c_str(), Describe(r.ingredients).c_str());',
        'PSendSysMessage("  %u  %s -> %u x %s  [%s]  (%s niveau %u)", r.id, r.name.c_str(), r.outputCount, ItemName(r.outputItem).c_str(), Describe(r.ingredients).c_str(), r.station.c_str(), r.minStationLevel);', "b5")
s = rep(s, '+ CostsStr(r.ingredients));', '+ CostsStr(r.ingredients) + "|" + std::to_string(r.minStationLevel));', "b6")
wr("server/Wowlheim/BuildCommands.cpp", s)

# --- addon : champs niveau
s = rd("tools/client/addon/Wowlheim/WowlheimCore.lua")
s = rep(s, "ingredients = C.ParseItems(f[6]) };", "ingredients = C.ParseItems(f[6]), minLevel = tonumber(f[7]) or 1 };", "l1")
s = rep(s, 'cover = tonumber(f[4]) };', 'cover = tonumber(f[4]), level = tonumber(f[5]) or 1 };', "l2")
s = s.replace("--   S|guid|utilisable|couverture                 etabli a portee", "--   S|guid|utilisable|couverture|niveau          etabli a portee")
s = s.replace("--   C|id|nom|station|sortie:n|item:n,item:n      recette", "--   C|id|nom|station|sortie:n|item:n,item:n|niveau_min   recette")
wr("tools/client/addon/Wowlheim/WowlheimCore.lua", s)
print("patch appliqué")
