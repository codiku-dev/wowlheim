# Wowlheim — Placement crédible des ressources Valheim d'après le terrain de WoW

Demande de Robin : arbres Valheim près des arbres de WoW, rochers près des montagnes, bordures et autres rochers, silex et chardon près de l'eau, cuivre en grands gisements. Jusqu'ici, les nœuds de production (`008`, `docs/RESOURCES_NODES.md`) reprenaient les positions des créatures, donc des camps de monstres. Ce travail lit le **terrain du client** et **propose** des positions. Il n'écrit **ni SQL ni base**, ne lance ni serveur ni client, et ne modifie aucun fichier existant du dépôt. Le branchement sur `gen_server_sql.py` / `gen_nodes_production.py` reste à faire.

> **Branché le 2026-10-26** (`gen_server_sql.py` lit `placements.json` ; détail : `docs/RESOURCES_NODES.md`). Réglages modifiés à cette occasion dans `place_resources.py` : `TREE_RATIO` par palier (1 : 0,18 ; 2 : 0,12 ; 3 : 0,25 ; 4 : 0,08 ; 5 : 0,10) et `TIER_DENSITY` (1 : 1,0 ; 2 : 0,55 ; 3 : 0,8 ; 4 : 0,6 ; 5 : 0,6) pour un budget d'environ 16 000 placements ; rochers 25 → 14 /km², fer 5 → 8 /km² ; marais = **arbre ancien** (`swamp` → `SwampTree1`, ajouté au serveur) ; montagne = sapins seulement, plaines = bouleaux et chênes seulement (Valheim) ; nouveaux types `dandelion` (P1), `cloudberry`, `barley`, `tar` (P5), `crystal` (P4), chardon aussi au palier 3 ; toute position dont le palier recalculé avec les `.map` du serveur diffère (bordure de zone) est refusée. Les chiffres des sections ci-dessous sont ceux de la première version (32 215 placements).

> **Points de départ et couverture (2026-10-26, 16 361 placements).** Contrôle `tools/resources/start_check.py` (`--source json` par défaut, `--source db` pour lire ce que la base contient ; sortie `start_check_result.txt`) : pour chaque départ de race (Comté du Nord, Coldridge, Vallée des épreuves, Camp Narache, Shadowglen, Deathknell), compte ce qui est **atteignable à pied** (grille de 4,17 m, marche refusée au-delà de 50° entre deux cases, nage permise) et **sans danger** (aucune créature de niveau ≥ 6 à 40 m) : branches ≥ 15 et pierres ≥ 8 à moins de 150 m de marche (établi 10 Bois + hache en pierre 5 Bois/4 Pierre, recettes de Valheim), hêtres ≥ 5 et arbres de palier 0 (hêtre, sapin, pin : `m_minToolTier` 0) ≥ 10 à 300 m, rochers ≥ 3 à 300 m, silex ≥ 6 (hache en silex) à 400 m et chardon ≥ 3 à 500 m sur une berge (eau `.map` à < 15 m) — rayon porté à « première eau atteignable sans danger + 250/350 m » quand il n'y a pas d'eau plus près (Coldridge : aucune eau dans la vallée, premier lac = Iceflow Lake à 1 119 m de marche) ; cuivre/étain : aucun dans la zone de départ ni à moins de 1 000 m de marche. Il refait aussi la couverture continent × faction × type. `place_resources.py` : passe dédiée `start_pass` avant tout le reste (`START_QUOTA`), chardon autorisé au palier 1 (berge du départ seulement), cuivre/étain refusés à moins de 1 100 m d'un départ (`ORE_START_EXCL` : un amas d'étain des berges de la Southfury était à 318 m de marche de la Vallée des épreuves), hêtres près des conifères aux paliers 1 (20 %) et 2 (10 %), goudron en mares de 4 à 7 (`tar`, au moins une mare par zone), au moins 4 arbres de chaque essence feuillue du biome par zone boisée (`SPECIES_MIN`), casques de décor `armorhelm*` (classés « tree » par le mot-clé « elm ») retirés des ancres. Couverture (`nodes_common.coverage_report`, utilisée par `check_nodes.py`) : une zone est **exigible** pour un type si la faction y a accès, si son palier est un palier où le type est placé partout et, pour un arbre, si WoW y a au moins 10 arbres non exotiques ; on exige min(3, zones exigibles). Les 24 cas où moins de 3 zones sont exigibles (Horde des Royaumes de l'Est au palier 2 : seulement Hillsbrad ; paliers 1 et 5 de Kalimdor : 2 zones par faction ; Mille pointes sans arbre) sont des constats **structurels**, tous couverts ; il n'y a plus de manque.

## 1. Fichiers

| Fichier | Rôle |
|---|---|
| `tools/resources/terrain_scan.py` | lit les ADT 1.12 (MPQ en lecture seule, priorité de `tools/client/mpq_layers.py`) et produit `C:\Wowlheim\data\wl_terrain\{0,1}_*` (≈ 75 s) |
| `tools/resources/terrain_grid.py` | accès au terrain extrait en coordonnées serveur : hauteur, pente, eau, route, aire |
| `tools/resources/terrain_verify.py` | contrôles de la conversion des coordonnées → `wl_terrain\verify.txt` |
| `tools/resources/place_resources.py` | propose les positions → `wl_terrain\placements.json`, journal `tools/resources/place_resources_result.txt` (≈ 35 s) |
| `tools/resources/place_check.py` | statistiques, contrôles recalculés, vérifications ponctuelles, cartes → `wl_terrain\checks.txt`, `wl_terrain\maps\*.png` |

Interpréteur : `C:\Wowlheim\tools\unity_venv\Scripts\python.exe`, qui fournit numpy et Pillow. Le module `mpyq` est importé depuis `tools/client/.venv`. `place_resources.py` lit aussi MySQL (`classicmangos`, en lecture seule) et `cache/spawns.tsv`.

Sorties du scan (par carte : 0 = Azeroth, 1 = Kalimdor) :
- `{m}_grid.npz` : par tuile, les hauteurs MCVT (grilles 129² et 128²), les trous, le niveau et le type de l'eau MCLQ par case de 4,17 m (1 rivière/lac, 2 océan, 3 magma, 4 slime), l'alpha des textures de route et l'AreaTable.ID de chaque chunk ;
- `{m}_trees.json`, `{m}_rocks.json`, `{m}_flora.json` (buissons, souches et troncs, champignons) : les doodads M2 placés (MDDF), avec leur position, leur échelle et leur modèle, dédupliqués par uniqueId ;
- `{m}_wmos.json` : les WMO (MODF) avec leur boîte englobante en coordonnées monde ;
- `{m}_water.json` : un résumé par chunk ; `{m}_slopes.json` : la pente maximale et la part de cases à plus de 35° par chunk ;
- `{m}_models.tsv` : l'inventaire de tous les modèles M2 avec la classe attribuée, à relire pour ajuster les règles ; `{m}_road_textures.txt` : les textures reconnues comme routes.

Extraits : Azeroth compte 687 tuiles, 35 141 arbres, 5 418 rochers, 51 692 buissons/souches/champignons et 1 508 WMO. Kalimdor compte 1 018 tuiles, 30 841 arbres, 8 856 rochers, 48 655 buissons/souches/champignons et 1 413 WMO.

## 2. Conversion des coordonnées (vérifiée)

- Tuile `Map_A_B`, chunk MCNK (ligne r = indexY, colonne c = indexX), sommet (i, j) : `X = (32−B)·533,33 − (8r+i)·4,1667`, `Y = (32−A)·533,33 − (8c+j)·4,1667`.
- Doodads MDDF et MODF (p0, p1, p2) : `X = 17066,67 − p2`, `Y = 17066,67 − p0`, `Z = p1`.

Preuves (`verify.txt`) :
1. La position stockée dans l'en-tête de chacun des MCNK des deux continents est égale à la formule à 0,05 m près : **0 écart**.
2. Les hauteurs ADT, comparées à `nodes_terrain.height` (fichiers `.map` du serveur, issus de l'extracteur de mangos) sur 3 000 points aléatoires par carte, ont un écart **médian de 0,001 m** et un 99e centile de 0,006 m. Le fond marin est exclu, car l'extracteur borne les hauteurs à −500 m.
3. Le masque d'eau MCLQ s'accorde avec `nodes_terrain.has_water` à 100 % (carte 0) et 99,9 % (carte 1).
4. Pieds des arbres de WoW : avec la conversion retenue, |z − sol| a une médiane de 0,61 m et 88 % des arbres sont à moins de 2 m du sol. Avec les axes permutés, la médiane est de 536 m ; avec les signes inversés, de 542 m. Seule la conversion retenue pose les arbres au sol.
5. Points connus (PNJ de la base face aux WMO) :
   - Innkeeper Farley (Goldshire) est dans `goldshireinn.wmo`, à 8 m de son origine ;
   - Marshal McBride, Deputy Willem et Brother Sammuel sont dans la boîte de `nsabbey.wmo` (abbaye de Northshire) ;
   - Innkeeper Renee (Brill) est dans `duskwood_inn.wmo` ;
   - Innkeeper Grosk (Razor Hill) est dans `orcinn.wmo`, à 4 m.

## 3. Classes de doodads (`terrain_scan.classify_model`, sur le nom du fichier M2)

1. Les « faux amis » sont écartés d'abord : street, lamp, fence, tomb, statue, bridge, wall, pillar, rune, grindstone, nest, underwater, barnacle, steppingstone, seaweed, spine, bone, ruin, post, gate, cage…
2. **deadwood** (stump, fallen, log, root, trunk).
3. **mushroom**.
4. **bush** (bush, shrub, plant, fern, grass, reed, cactus…).
5. **tree** (tree, pine, oak, birch, palm, willow, canopy…).
6. **rock** (rock, boulder, stone, cliff, crag, outcrop…).
7. À défaut de mot-clé, le dossier `\trees\` ou `\rocks\` décide.

Exemples : `elwynntreecanopy02` → tree, `elwynnbush09` → bush, `elwynntreestump02` → deadwood, `elwynnstonefence` → écarté, `elwynncliffrock01` → rock. L'inventaire complet et la classe de chaque modèle sont dans `{m}_models.tsv`.

## 4. Biomes de Valheim par palier, et règles de placement

Le palier est celui de la zone, calculé par `generate.zone_tiers` (niveau médian des créatures ; les zones de moins de 30 apparitions et la zone 0 sont exclues). La zone d'un point vient de l'AreaTable.ID du chunk ADT.

| Palier | Biome Valheim | Arbres (feuillu WoW / conifère WoW) | Autres |
|---|---|---|---|
| 1 (1–15) | Prairie | hêtre 75 %, bouleau 13 %, chêne 12 % / sapin | rocher, pierre, branche, silex (berges), framboise (près des buissons WoW), champignon |
| 2 (15–28) | Forêt noire | sapin 50 %, pin 35 %, hêtre 15 % / sapin 55 %, pin 45 % | rocher, pierre, branche, silex, **cuivre en amas**, **étain sur les berges**, **chardon au bord des rivières et lacs**, myrtille, champignon |
| 3 (28–40) | Marais | chêne 70 %, bouleau 30 % / sapin (adaptation : les vieux arbres du marais n'existent pas parmi les essences du serveur) | rocher, **fer** sur terrain bas, plat et humide (eau à moins de 30 m, sous la médiane de hauteur de la zone) |
| 4 (40–52) | Montagne | bouleau 40 %, sapin 60 % / sapin 70 %, pin 30 % | rocher, **argent** et **obsidienne** en hauteur (≥ 75e centile de la zone, pente de 12 à 40°, pied de falaise) |
| 5 (52–60) | Plaines | bouleau 70 %, chêne 30 % / pin | rocher, **lin** en touffes de 3 à 6 plants sur terrain plat (< 8°), sans eau à moins de 30 m |

Le mot « myrtille » (blueberry) de la demande s'ajoute à la liste des kinds. Les essences sont celles du serveur (`TREE_SPECIES` : Beech1, FirTree, Pinetree_01, Birch1, Oak1).

Règles :
- **Arbres** : 40 % des arbres de WoW éligibles (paramètre `TREE_RATIO`) reçoivent un arbre Valheim placé à 3–15 m de l'arbre WoW (minimum : 2 × l'échelle du doodad). L'arbre Valheim n'est jamais à moins de 3 m d'un tronc ou d'une souche de WoW, et deux arbres Valheim sont à 5 m au moins l'un de l'autre. La pente doit rester sous 35°.
  - Un modèle conifère (pine, snow, winter, alterac, ironforge…) donne un sapin ou un pin, d'où les sapins de Dun Morogh et de Silverpine.
  - Les palmiers, la jungle et les cactus (`EXOTIC_RE`) n'ont pas d'équivalent Valheim : aucun arbre près d'eux (5 945 ignorés, p. ex. Durotar et Tanaris).
- **Rochers** : priorité aux rochers de WoW (2,5 à 8 m × échelle), puis aux pieds de falaise (case de moins de 25° avec, à moins de 2 cases, une case de plus de 45° plus haute de 3 m), puis aux pentes de 25 à 40°. **Pierres** : près des rochers de WoW ou sur terrain plat. **Branches** : près des troncs morts, sinon sous les arbres (2 à 7 m).
- **Berges** (silex, chardon, étain) : case sèche avec de l'eau (rivière, lac ou océan ; jamais de magma) dans un disque de 2,24 cases (9,3 m), sol au moins 0,3 m au-dessus du niveau de l'eau voisine. Le chardon n'est placé qu'au bord des rivières et lacs. L'étain est placé par groupes de 1 ou 2.
- **Cuivre** : AMAS de 3 à 8 filons, à 6–18 m du centre, espacés de 5 m ; le centre est en pied de falaise ou près d'un rocher de WoW. On compte 1 amas par km² de terre (au moins 2 par zone) et 300 m au moins entre deux amas.
- **Densités** par km² de terre de la zone (les zones de WoW sont petites : Elwynn = 3,8 km²) : rocher 25, pierre 20, branche 25, silex 10, baies 10, champignon 8, chardon 8, étain 5 groupes, fer 5, argent 3, obsidienne 3, touffes de lin 4. Tout se règle dans `KINDS`, en tête de `place_resources.py`.
- **Exclusions**, avec les mêmes sources que le reste du projet :
  - villes (drapeaux d'aire `CITY_FLAGS`) et intérieurs (`INDOOR` sur le nom d'aire) ;
  - points 010 (rayon 100 m) et PNJ, civils et gardes (rayon 50 m) ;
  - **bâtiments** : boîte WMO + 6 m, pour les WMO de moins de 300 m de côté ;
  - **routes** : alpha ≥ 100 d'une texture de route, au point ou à 4 m ;
  - eau (niveau ≥ sol − 0,3 m), trous du terrain.
- Ailleurs, l'espacement entre deux ressources quelconques est de 3 m au moins. Le z est la hauteur du terrain MCVT au point ; l'orientation est déterministe (crc32). Tout le tirage est déterministe.

Format de `placements.json` : `items = [{map, x, y, z, o, kind, tier, zone, anchor}]`. Le champ `anchor` dit pourquoi le point a été choisi, par exemple « a 6.1 m de l'arbre WoW felwoodtree02.mdx (2818.9, -2956.0) », « berge : sol …, eau riviere/lac au niveau … » ou « amas copper (x, y) de 5 ».

## 5. Résultat (exécution du 2026-10-26)

**32 215 positions** proposées :

| Type | Nombre |
|---|---|
| sapin | 6 460 |
| bouleau | 3 714 |
| hêtre | 3 623 |
| pin | 2 273 |
| chêne | 1 664 |
| rocher | 5 464 |
| branche | 2 429 |
| pierre | 1 940 |
| silex | 927 |
| champignon | 778 |
| lin | 691 |
| myrtille | 436 |
| chardon | 401 |
| framboise | 366 |
| étain | 333 |
| cuivre | 273 (49 amas) |
| argent | 151 |
| obsidienne | 151 |
| fer | 141 |

Par palier :

| Palier | Positions |
|---|---|
| T1 | 10 193 |
| T2 | 10 297 |
| T3 | 2 048 |
| T4 | 5 190 |
| T5 | 4 487 |

Détail par zone : `place_resources_result.txt` et `checks.txt`.

Contrôles (`checks.txt`), recalculés par force brute numpy, sans les index ni les candidats du générateur :

| Contrôle | Résultat |
|---|---|
| z − hauteur MCVT | ≤ 0,015 m |
| Positions dans l'eau | 0 |
| Arbres : distance à l'arbre WoW le plus proche | min 3,05 m, médiane 7,2 / 7,6 m (cartes 0 / 1), max 15,00 m |
| Arbres à moins de 3 m d'un tronc | 0 |
| Silex, chardons, étain avec de l'eau à 12 m au plus | 1 653 sur 1 661 |
| Hauteur du sol au-dessus de l'eau (berges) | médiane 1,6 à 1,9 m |
| Rochers près d'un rocher WoW ou d'une pente ≥ 25° | 5 449 sur 5 464 |
| Amas de cuivre | 3 à 8 filons (moyenne 5,2–5,8), étendue de 14 à 35 m |

Écarts restants :
- 8 positions de berge n'ont pas d'eau à 12 m selon l'échantillonnage en anneau du contrôle (24 directions) : le générateur, lui, travaille par case ;
- 1 berge est à −0,14 m sous le niveau d'une autre étendue d'eau voisine ;
- 8 rochers dépassent 12 m de leur rocher WoW, quand ce rocher est à grande échelle.

Vérifications ponctuelles (`checks.txt`) :
1. Hêtre (−9647,0 ; −1379,8 ; z 53,3), Elwynn : arbre WoW `elwynntreecanopy01` à (−9642,8 ; −1394,1), à 15,0 m.
2. Sapin (2814,7 ; −2960,4), Ashenvale : `felwoodtree02` à 6,1 m.
3. Silex (−9793,7 ; 544,0 ; z 33,28), Elwynn : eau à 4 m, niveau 31,71 m, donc sol 1,57 m au-dessus de l'eau.
4. Rocher (−303,8 ; −4849,9), Durotar : `durotarrock03` à 3,3 m.
5. Amas de cuivre à (−9989 ; −1473), Duskwood : 4 filons sur 14 m.
6. Étain (335,2 ; −2269,5 ; z 242,79), The Barrens : eau à 5 m, sol 2,0 m au-dessus de l'eau.

Cartes (`C:\Wowlheim\data\wl_terrain\maps\`, nord en haut, 1 px = 2,08 m) : Elwynn, Dun Morogh, Tirisfal, Durotar, Mulgore, Teldrassil, Duskwood, Ashenvale. On y voit le relief ombré, les falaises en brun, l'eau en bleu (l'océan plus foncé), les routes en beige, les arbres et rochers de WoW, les boîtes des WMO en rouge et les placements colorés par type. Constats visuels :
- Elwynn : les hêtres suivent les forêts de WoW ; du silex sur les berges du lac de Stone Cairn et de la rivière du sud ; aucun placement sur les routes pavées ni dans les fermes.
- Duskwood : sapins et pins partout, 3 amas de cuivre au pied des reliefs, étain et chardons le long des rivières du nord et de l'ouest.
- Durotar : presque pas d'arbres (palmiers ignorés) ; rochers et pierres dans les reliefs ; silex le long de la côte.

## 6. Limites

- **Rien n'est vu en jeu.** Ce sont des propositions : aucun SQL n'est écrit ni appliqué.
- **Terrain seulement.** Les sols des WMO (ponts, grottes, villes) et leurs liquides ne sont pas lus. Les grands WMO (plus de 300 m) ne sont pas exclus : les villes le sont par les drapeaux d'aire, mais une grotte ou une ruine géante peut contenir des placements.
- **Routes** : seules les textures nommées road, path, cobble, brick… sont reconnues. Les chemins en terre battue faits d'une texture « Dirt » générique (une partie d'Elwynn, par exemple) ne sont pas exclus.
- **Classification des modèles** par le nom : les erreurs sont possibles. L'inventaire `{m}_models.tsv` permet de corriger les règles.
- **Palier de zone, pas biome réel.** Swamp of Sorrows est au palier 4, donc reçoit de l'argent et de l'obsidienne ; Tanaris (désert) reçoit argent, obsidienne et rochers ; Winterspring (palier 5) garde des pins près de ses conifères enneigés, ce qui privilégie la cohérence visuelle sur le biome des Plaines. Le palier 3 n'a pas les vieux arbres du marais (chêne à la place). Le fer est rare (141) car il exige un terrain bas, plat et humide.
- **Densité et charge serveur** : environ 18 000 arbres et 14 000 autres ressources, contre 4 664 nœuds pour `008`. Si chacune devient une créature ou un GameObject, la charge n'est pas mesurée. `TREE_RATIO` et `KINDS` permettent de réduire.
- **Paliers** : les zones sans palier (moins de 30 apparitions : Moonglade, etc.) n'ont rien. Les poches de palier local de `008` ne sont pas reprises : le palier est celui de la zone.
- Les contrôles sur l'eau et la pente de `place_check.py` relisent la même extraction (`terrain_grid`). Ils ne sont indépendants que de la logique de sélection, pas de la lecture des ADT. La lecture des ADT est elle-même validée contre les `.map` du serveur (section 2).

## 7. Régénérer

```
cd tools/resources
C:\Wowlheim\tools\unity_venv\Scripts\python.exe terrain_scan.py      # ADT -> wl_terrain (≈ 75 s)
C:\Wowlheim\tools\unity_venv\Scripts\python.exe terrain_verify.py    # verify.txt
C:\Wowlheim\tools\unity_venv\Scripts\python.exe place_resources.py   # placements.json (≈ 35 s, lit classicmangos)
C:\Wowlheim\tools\unity_venv\Scripts\python.exe place_check.py       # checks.txt + maps\*.png
C:\Wowlheim\tools\unity_venv\Scripts\python.exe start_check.py       # departs + couverture (code 0 = tout passe ; --source db : la base)
cd ..\valheim
C:\Wowlheim\tools\unity_venv\Scripts\python.exe gen_server_sql.py    # 012_valheim_content.sql (n'applique rien)
```
