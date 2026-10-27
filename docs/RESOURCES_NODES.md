# Wowlheim — Ressources du monde : arbres, roches, filons et ramassables de Valheim (2026-10-26)

Retour de Robin en jeu : « le but, c'est que ce soit progressif exactement comme Valheim […] au début on a juste le marteau […] il y a des arbres et des rochers et pas grand-chose de plus autour […] je vois des minerais bizarres qui sont pas du tout les modèles de Valheim » (ex. « Amas de noyaux noirs », nœud de palier 5 vu en zone de niveau 1).

**Ce document remplace l'ancienne version** (4 664 nœuds GameObject aux modèles WoW placés sur les positions des créatures, `008`). Ces nœuds n'existent plus. Rien n'a été appliqué sur `classicmangos` ni sur le serveur en marche : tout est validé sur une copie jetable (`validate_nodes_scratch.py`).

## 1. Ce qui existe maintenant

| Quoi | Où | Nombre |
|---|---|---|
| Positions (d'après le terrain du client : arbres Valheim à 3–15 m des arbres WoW, rochers près des rochers/falaises, silex/chardon/étain sur les berges, cuivre en amas, rien sur routes/villes/eau, palier = palier de la zone) | `tools/resources/place_resources.py` → `C:\Wowlheim\data\wl_terrain\placements.json` (méthode et preuves : `docs/RESOURCES_PLACEMENT.md`) | 16 037 |
| Arbres, roches, filons = **créatures** au modèle Valheim, frappées à la hache / à la pioche (`TreeMgr`) | `012_valheim_content.sql`, `creature` guid 9600001+, `tools/valheim/gen_server_sql.py` | 8 956 |
| Ramassables de Valheim = **GameObjects coffre sans verrou** (un clic, sans outil, absents de `wowlheim_node`), modèle Valheim, butin = `Pickable.m_itemPrefab × m_amount`, réapparition = `m_respawnTimeMinutes` | `012`, `gameobject_template` 9130001–9130013, `gameobject` guid 9501001–9514664 | 7 081 |
| Anciens nœuds GameObject aux modèles WoW (9101001–9101045 : filons d'argent, métal noir, cristal, lin, ossements, racines, roche de Surtling, cristal de givre, amas de noyaux noirs…) | **supprimés** : modèles et butin par `003`, apparitions par `005` et `008` (régénérés, ne contiennent plus qu'un `DELETE`), `wowlheim_node` vidé (`007`, `012`) | 0 |

Plage de guid des ramassables : 9501001–9514664 est **sous** les pièces déjà posées (max 9514669) ; le serveur attribue `max(guid)+1` aux nouvelles pièces, il n'y aura donc jamais de collision lors d'une régénération. Le `DELETE` est limité aux entrées 9130001–9130099.

## 2. Placement par palier (= biome de Valheim)

Types et prefabs : `tools/resources/rules.py`, `PLACEMENTS` (paliers autorisés, prefabs, matériaux obtenus ; `gen_server_sql.py` vérifie ces matériaux contre les DropTable de Valheim). Comptes de `placements.json` :

| Palier (zones) | Biome | Créatures (outil) | Ramassables |
|---|---|---|---|
| 1 (1–15 : Elwynn, Dun Morogh, Tirisfal, Durotar, Mulgore, Teldrassil, Westfall, Loch Modan, Silverpine, Darkshore) | Prairie | hêtre 1 373 (hache en pierre), bouleau 249 et chêne 224 (**hache en bronze** : « trop dur » au début, comme Valheim), sapin 792 (conifères WoW : Dun Morogh, Tirisfal, Silverpine), rocher 659 (`MineRock_Stone`/`Rock_4`, pioche) | branche 1 180, pierre 941, silex 428 (berges), framboisier 366, champignon 377, pissenlit 377 |
| 2 (15–28) | Forêt noire | sapin 643, pin 501, hêtre 153, rocher 387, **cuivre** 157 (amas), **étain** 184 (berges, eau < 15 m) | branche 685, pierre 549, silex 275, myrtillier 244, chardon 219 (bord des rivières/lacs), champignon 219 |
| 3 (28–40) | Marais | **arbre ancien** 694 (`SwampTree1`, hache en bronze → Bois + Écorce ancienne), rocher 361, **fer** 178 (tas de boue `mudpile` → Ferraille, pioche en bois de cerf : `mudpile_frac` `m_minToolTier` 0 ; terrain bas et humide) | chardon 189 |
| 4 (40–52) | Montagne | sapin 767, rocher 423, **argent** 91 (`silvervein`, pioche en fer), **obsidienne** 91 (pioche en fer) | cristal 91 (`Pickable_MountainCaveCrystal` ; adaptation : en surface, pas de grotte) |
| 5 (52–60) | Plaines | bouleau 507, chêne 196, rocher 326 | lin sauvage 411 et orge sauvage 320 (touffes), plaquebière 186, goudron 24 (`Pickable_TarBig`, 15 Goudron) |

Règle stricte : **aucun type d'un palier supérieur dans une zone de palier inférieur** ; le palier de chaque position est recalculé avec la zone des `.map` du serveur (en plus de l'aire ADT) et toute position de bordure où les deux diffèrent est refusée (`place_resources.py`, `Placer.try_add`). Contrôle : `check_nodes.py` §4 → **0** écart sur 16 037.

Pas de nœud pour : sombracier (Valheim : butin des Fulings → « Morceau de sombracier » en butin de palier 5), Bois dur / Œil de naingris / Cœur de surtling / Glande gelée / Noyau noir / Larme de dragon (Valheim : butin de monstres → butin de mobs WoW, `rules.DROP_RULES`).

## 3. Départ (Valheim : on n'a que le marteau)

- Kit de départ : **le marteau seul** (`011_hammer_starter.sql` ; les 20 Bois sont retirés). Les personnages existants gardent leur sac.
- Premier objectif, l'établi : 10 Bois → ramasser 10 branches (1 Bois chacune, sans outil). Puis la hache en pierre **à la main** (recette 100, sans station : 5 Bois, 4 Pierre) → abattre les hêtres.
- Branches à moins de 600 m de chaque point de départ (`check_nodes.py` §7) : humains 22, orcs/trolls 15, nains/gnomes 35, elfes de la nuit 31, morts-vivants 23, taurens 41 ; pierres 7 à 30. Réapparition des branches : 240 min (Valheim). Seuil de constat : 15 (= 10 + 5 Bois).
- Réapparition des ramassables : `Pickable.m_respawnTimeMinutes` (branche, silex, champignon, pissenlit, chardon : 240 min ; baies : 300 min). **Adaptation** : Valheim met 0 (« ne repousse jamais ») pour la pierre, le lin et l'orge sauvages, le goudron, le cristal ; sur un serveur partagé ils reviennent après 240 min.
- Arbres et roches : réapparition 600 s (inchangé).

## 4. Budget de charge

Total 16 037 (cible de la coordination : ordre de 15 000) = 8 956 créatures-ressources (`NullAI`, immobiles) + 7 081 GameObjects. Réglages dans `place_resources.py` : `TREE_RATIO` par palier (1 : 0,18 ; 2 : 0,12 ; 3 : 0,25 ; 4 : 0,08 ; 5 : 0,10), `TIER_DENSITY` (1 : 1,0 ; 2 : 0,55 ; 3 : 0,8 ; 4 : 0,6 ; 5 : 0,6 : la prairie, zones de départ, garde la densité pleine), densité des rochers 25 → 14 /km², fer 5 → 8 /km². **Coût serveur non mesuré ici** (démarrage et `.build perf` : `prod_node_test.py`, lancé par la coordination).

## 5. Contrôles

`python tools/resources/validate_nodes_scratch.py` : copie 14 tables dans `wl_scratch2`, applique 001, 002, 003, 005, 006, 007, 008, 010, 011, 012 **deux fois** (sans erreur, mêmes comptes), lance `check_nodes.py`, écrit `check_nodes_result.txt`, supprime la copie. Résultat : **formes toutes OK** (code 3 : constats de couverture seulement) :
- 0 ligne 9101xxx (modèles, butin, apparitions), `wowlheim_node` vide ;
- 13 modèles de ramassables : type 3, sans verrou, butin = entrée, `data3 = 1`, `displayId` présent dans le `GameObjectDisplayInfo.dbc` du patch ; butin d'objets existants ;
- 7 081 ramassables et 8 956 créatures en base = les positions de `placements.json` (0 écart) ; chaque créature a son modèle, son `wowlheim_tree` et son `creature_model_info` ;
- z à moins de 1,5 m du terrain statique (`.map`) : 16 037/16 037 ; dans l'eau : 4 ; silex/chardon/étain sans eau à moins de 15 m (`.map`) : 7/703, 1/408, 3/185 ;
- 0 position à moins de 50 m d'un PNJ/civil/garde ou à moins de 100 m d'un point 010 ;
- kit = marteau seul, 0 vendeur, plus d'outil inventé, hache en pierre à la main, établi = 10 Bois, 14 recettes valides ;
- lignes `gameobject` hors plages Wowlheim identiques à `classicmangos` (47 370).

Constats (27) : couverture « 3 zones par continent et par faction » non atteinte pour certains types, conséquence voulue de la règle stricte « palier = palier de la zone » (plus de poches de palier voisin) : Horde des Royaumes de l'Est au palier 2 = Hillsbrad seulement (cuivre, étain, pin, myrtille) ; Kalimdor palier 2 Alliance = Ashenvale + Stonetalon ; palier 5 de Kalimdor = Silithus + Winterspring ; goudron : 1 zone sur les Royaumes de l'Est. Les objets correspondants restent accessibles aux deux factions dans les zones contestées.

## 6. Limites (non vérifié)

- **Rien n'a été vu en jeu** (modèles des ramassables, clic de ramassage, taille des buissons) ; SQL non appliqué à `classicmangos`, serveur non redémarré, patch client non installé (consignes).
- Zones et eau des contrôles : terrain statique (`.map`) ; l'eau des WMO n'est pas vue ; le type de liquide (magma) est écarté côté `place_resources.py` mais pas recontrôlé.
- `Pickable_MountainCaveCrystal` et `Pickable_TarBig` n'ont pas de texture (`_MainTex`) : exportés en couleur unie (`build_assets.py`, `FLAT_COLOR`).
- `silvervein` : la veine se brise d'un coup en `silvervein_frac` (MineRock5, 100 fragments de 50 PV dont 89 hors sol comptés, butin 2–3 tirages par fragment : Pierre 1 / Minerai d'argent 0,5) ; regroupée en une créature (PV ÷ 8 : 8 fragments abattus par coup pour les MineRock5 à soutien, calage sur la durée de jeu, non mesuré). Rocher, cuivre et tas de boue suivent la même chaîne (`rock4_coast_frac`, `rock4_copper_frac`, `mudpile_frac`) : valeurs et sources dans `docs/VALHEIM_RULES.md` §13.
