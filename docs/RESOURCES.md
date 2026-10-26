# Wowlheim — Ressources (phase 4) : audit, choix, résultats, limites

Tout le SQL est **généré par script** (`tools/resources/`), jamais écrit à la main. Rien n'a été appliqué sur `classicmangos` : les scripts ont été validés sur une copie jetable `wl_scratch` (supprimée). L'intégrateur applique `server/sql/world/002..006_*.sql`, puis lance `python tools/resources/check.py` (base réelle).

## 1. Livrables

| Fichier | Rôle |
|---|---|
| `server/sql/world/002_items.sql` | 29 matériaux (classe 7 / sous-classe 11) + 10 outils (classe 2 / sous-classe 14), entrées 9200001–9299999 |
| `server/sql/world/003_nodes.sql` | 23 modèles de nœuds (`gameobject_template` 9101001+) et leurs `gameobject_loot_template` |
| `server/sql/world/004_loot.sql` | 75 références (`reference_loot_template`), 2 296 lignes ajoutées à `creature_loot_template` |
| `server/sql/world/005_node_spawns.sql` | 118 nœuds de **validation** (guid 9500001+) |
| `server/sql/world/006_vendors.sql` | source de secours : 159 lignes `npc_vendor` (stock limité) |
| `tools/resources/rules.py` | source unique de vérité (objets, outils, nœuds, règles de butin, paliers) |
| `tools/resources/generate.py` | produit 002–006 (`python generate.py [items\|nodes\|loot\|spawns\|vendors\|all]`) |
| `tools/resources/build_cache.py`, `common.py`, `classify.py` | cache `cache/` (zones des apparitions, noms de modèles du DBC) ; zone de chaque apparition (fichiers `.map` du client, même algorithme que `GridMap::getArea`), classification des créatures |
| `tools/resources/check.py` | contrôles automatiques (section 7) |
| `tools/resources/validate_scratch.py` | recrée `wl_scratch`, applique 002–006 **deux fois**, lance `check.py`, supprime `wl_scratch` |
| `tools/resources/audit.py`, `simulate.py` | audit chiffré de la base ; simulation de butin d'une créature (sortie dans `audit_result.txt`, `sim_result.txt`, `check_result.txt`) |

Ordre d'application : `002`, `003`, `004`, `005`, `006` (indépendants, tous idempotents : `DELETE` de leur propre plage puis `INSERT`). Régénération : `python build_cache.py` (une fois) puis `python generate.py`.

## 2. Écarts avec la demande (à lire d'abord)

1. **Références de butin en 8300000+, pas 9300000+.** `creature_loot_template.mincountOrRef` est un `MEDIUMINT` *signé* (min −8 388 608) et une référence y est stockée en négatif. Essai sur `wl_scratch` : l'insertion de −9304010 échoue (`ERROR 1264 Out of range value for column 'mincountOrRef'`). Plage retenue : `8300000 + palier*1000 + catégorie*10`. Le code serveur ne doit pas supposer 9300000+.
2. **Les nœuds ne sont verrouillés par rien** (`data0` = 0, aucune compétence) comme demandé : tant que le code serveur n'exige pas l'outil, un nœud est récoltable à la main. Vérifié dans le source (`GameObject::Use`, cas `GAMEOBJECT_TYPE_CHEST`) : avec `lockId = 0` le coffre passe directement en `GO_JUST_DEACTIVATED` et s'ouvre au clic ; c'est donc le code serveur (hook sur l'ouverture) qui devra refuser sans outil.
3. **Aucun outil n'est équipable « normalement » comme arme de classe** : classe 2 / sous-classe 14 (« Divers », comme le *Mining Pick* 2901 de la base : emplacement main droite, aucune maîtrise requise). Le code serveur peut donc tester « outil dans l'inventaire » ou « outil équipé » sans contrainte de classe.
4. **Le critère « ≥ 3 sources par ressource » n'est pas atteint au sens strict (butin + nœud + vendeur) pour les peaux, os, entrailles, fourrure** : pas de nœud pertinent (section 7.5). Ils ont 2 types de sources vérifiés + 8 à 17 familles de créatures distinctes ; une conversion est proposée seulement pour deux d'entre eux.

## 3. Audit chiffré de la base (lecture seule de `classicmangos`, `tools/resources/audit_result.txt`)

- `creature_template` : 10 384 modèles ; 60 677 apparitions sur les cartes 0 et 1 (6 394 modèles) ; 14 301 lignes `creature_spawn_entry` (apparitions à entrée multiple, prises en compte).
- Zone de chaque apparition : calculée depuis les `.map` extraits (`C:\Wowlheim\data\maps`) + `AreaTable.dbc`. Vérifié sur des points connus : Northshire → `Elwynn Forest / Northshire Valley`, Valley of Trials → `Durotar / Valley of Trials`, Goldshire → `Goldshire`, Ratchet → `The Barrens / Ratchet`. 43 apparitions sans zone (ignorées).
- Un `LootId` = un modèle de créature, sauf 1 groupe (`16243`, 4 variantes de *Plague Slime*) : **aucun partage dangereux dans cette base**. Tous les `LootId` existent déjà dans `creature_loot_template`.
- 408 modèles de créatures vivantes n'ont aucun butin (`LootId = 0`, 2 602 apparitions, surtout des PNJ « Watcher… » et des personnages de test niveau 1) : **non touchés** (leur donner un `LootId` serait modifier une ligne existante).

Exclusions (premier motif rencontré) : `LootId = 0` : 6 141 ; apparaît aussi en instance/champ de bataille : 830 ; aucune apparition sur les cartes 0/1 : 439 ; rang 4 (rare) : 263 ; rang 2 (rare élite) : 116 ; rang 3 (boss) : 92 ; garde/civil : 84 ; drapeaux PNJ (vendeur, entraîneur…) : 14 ; type critter : 2.
**Éligibles : 2 403 modèles, 49 501 apparitions** (rang 0 ou 1).

Éligibles par palier (modèles / apparitions) : T1 428/12 454 ; T2 555/10 418 ; T3 500/7 825 ; T4 465/9 454 ; T5 455/9 350. Humanoïdes : 1 095 modèles, bêtes : 567, morts-vivants : 166, démons : 99, élémentaires : 124, dragonnets : 76, géants : 20, mécaniques : 12, « non spécifié » (oozes, silithides, hydres) : 95.

Niveau médian des créatures par zone → palier (extraits ; liste complète dans `audit_result.txt`) : Elwynn/Dun Morogh/Tirisfal/Durotar/Teldrassil/Mulgore 7,5 → T1 ; Westfall/Darkshore/Loch Modan 14,5 → T1 ; Redridge/Barrens/Stonetalon 15–20 → T2 ; Hillsbrad 25,5 → T2 ; Arathi/STV/Desolace 33–38 → T3 ; Swamp of Sorrows/Hinterlands/Tanaris 41–47 → T4 ; Burning Steppes/EPL/Winterspring 54–57 → T5.

## 4. Matériaux (002)

Paliers : borne basse incluse, borne haute exclue, niveau = (MinLevel+MaxLevel)/2 → T1 < 15 ≤ T2 < 28 ≤ T3 < 40 ≤ T4 < 52 ≤ T5 (le cahier donne « 1–15, 15–28… » sans trancher les bornes).

Tous : qualité 1 (passage : 2), pile 100, aucune compétence / sort / serrure requis (vérifié par `check.py`), `description` = « Wowlheim », classe 7 sous-classe 11 (« Autre »). Prix de revente 4 cuivre × 3^(palier−1) (passage ×5, bronze ×2) ; prix chez le PNJ = revente × 10 (base uniquement ; jamais passage ni bronze). `displayid` = celui d'un objet existant (donc connu du client) : bois 7375 (*Wooden Stock*), pierre 4714, silex 18107, résine 8283, cuir 7400/6687, minerais 4681/4690/4689/7355, os 7350, fourrure 7294, cristal 6546, obsidienne 20769, métal noir 20658 (*Thorium Ore*), lin 7383, fil 4752… (liste exacte dans `rules.py`).

| Palier | Matériaux de base (butin + nœud + vendeur) | Fabriqué | Matériau de passage |
|---|---|---|---|
| 1 Prairie | 9200001 Bois, 9200002 Pierre, 9200003 Silex, 9200004 Résine, 9200005 Peau de cerf, 9200006 Chutes de cuir | — | **9200009 Andouiller** |
| 2 Forêt noire | 9200011 Bois fin, 9200012 Bois de cœur, 9200013 Cuivre, 9200014 Étain, 9200016 Peau de troll | 9200015 Bronze | **9200019 Œil de gréling** |
| 3 Marais | 9200021 Fer, 9200022 Écorce ancienne, 9200023 Fragments d'os, 9200024 Entrailles | — | **9200029 Noyau de Surtling** |
| 4 Montagne | 9200031 Argent, 9200032 Obsidienne, 9200033 Fourrure de loup, 9200034 Cristal | — | **9200039 Glande de gel** |
| 5 Plaines | 9200041 Métal noir, 9200042 Lin, 9200043 Fil de lin, 9200044 Peau de lox | — | **9200049 Noyau noir** |

**Matériaux de passage (définition proposée)** : un par palier, de qualité verte, jamais vendu ; ingrédient du *pic* du palier (donc nécessaire pour ouvrir les nœuds du palier suivant, voir 5). Deux sources répétables vérifiées en base : (a) butin de créatures du palier à taux bas (3–10 %, quantité 1) sur 2 à 5 catégories de créatures ; (b) un nœud « cache » dédié (9101041–9101045), quantité 1–2, réapparition 15–20 min. Les noms sont mon choix d'inspiration Valheim (andouiller, œil de gréling, noyau de Surtling, glande de gel, noyau noir) ; **les noms français exacts du jeu Valheim n'ont pas été vérifiés**. Le « Bronze » n'a aucune source de butin, de nœud ou de vendeur : il ne s'obtient que par conversion (section 5), qui reste à coder.

Risque d'affichage non vérifié : « œ », « É », « Œ » dans les noms (enUS) : le client est en anglais ; je n'ai pas pu tester le rendu de ces glyphes en jeu (noms imposés par le cahier pour « Bois de cœur » ; seul « Œil de gréling » est de mon choix).

## 5. Outils (002) et recettes proposées

Armes à faibles dégâts, main droite (InventoryType 21), classe 2 / 14, sans durabilité, `RequiredLevel` = niveau d'entrée du palier, non liées. Entrées : 9201000 + palier×10 + 1 (hache) ou + 2 (pic).

| Entrée | Outil | Palier | Dégâts | Modèle (displayid existant) |
|---|---|---|---|---|
| 9201011 / 9201012 | Hache en silex / Pic en andouiller | 1 | 1–3 | 7429 (*Axe, Stone Basic*) / 7493 (*Item, Pick*) |
| 9201021 / 9201022 | Hache de bronze / Pic de bronze | 2 | 2–5 | 7428 / 6568 (*Mining Pick*) |
| 9201031 / 9201032 | Hache de fer / Pic de fer | 3 | 4–8 | 7428 / 6568 |
| 9201041 / 9201042 | Hache d'argent / Pic d'argent | 4 | 6–12 | 7426 / 14039 |
| 9201051 / 9201052 | Hache de métal noir / Pic de métal noir | 5 | 8–16 | 7427 / 14039 |

**Recettes proposées (non créées : elles iront dans la table du code serveur)**. Station : Établi (T1), Forge (T2+).

| Outil | Station | Ingrédients |
|---|---|---|
| Hache en silex | Établi | 4 Bois, 3 Silex, 1 Résine |
| Pic en andouiller | Établi | 4 Bois, 2 Andouiller, 2 Chutes de cuir |
| Hache de bronze | Forge | 4 Bois fin, 5 Bronze, 1 Bois de cœur, 2 Résine |
| Pic de bronze | Forge | 3 Bois fin, 6 Bronze, 2 Œil de gréling, 2 Peau de troll |
| Hache de fer | Forge | 4 Bois de cœur, 6 Fer, 2 Écorce ancienne, 2 Chutes de cuir |
| Pic de fer | Forge | 3 Bois de cœur, 8 Fer, 2 Noyau de Surtling, 2 Fragments d'os |
| Hache d'argent | Forge | 4 Bois de cœur, 6 Argent, 2 Fourrure de loup, 2 Cristal |
| Pic d'argent | Forge | 3 Bois de cœur, 8 Argent, 2 Glande de gel, 2 Obsidienne |
| Hache de métal noir | Forge | 4 Bois de cœur, 6 Métal noir, 3 Fil de lin, 2 Peau de lox |
| Pic de métal noir | Forge | 3 Bois de cœur, 8 Métal noir, 2 Noyau noir, 2 Peau de lox |

Conversions proposées (sources de secours, non implémentées) : 2 Cuivre + 1 Étain → 2 Bronze (Forge) ; 2 Lin → 1 Fil de lin ; 5 Bois → 1 Bois fin ; 5 Bois fin → 1 Bois de cœur ; 6 Pierre → 2 Silex ; 3 Peau de cerf → 4 Chutes de cuir.

Règle de contrôle d'outil proposée pour le code serveur : nœud de palier N (colonne « palier » de la section 6) → outil du bon type de palier ≥ max(1, N−1) (hache pour `bois`/`plante`, pic pour `pierre`/`minerai`/`passage`). Ainsi le pic d'andouiller (T1) ouvre cuivre et étain (T2), ce qui évite la circularité « le bronze exige du cuivre exigeant un outil en bronze ». Les outils de palier 1 se fabriquent avec des matériaux de palier 1 obtenus **par butin de créatures ou chez un vendeur** (sans outil) : c'est une des raisons d'être des sources de butin.

## 6. Nœuds de ressources (003)

Type 3 (CHEST), `data0` = 0 (aucun verrou), `data1` = table de butin (même numéro que l'entrée), `data3` = 1 (le nœud disparaît une fois pillé et revient après le délai d'apparition). Chaque nœud donne le matériau principal à 100 % en quantité variable, plus un secondaire éventuel. Réapparition : bois 120–180 s, pierre 150–210 s, minerai/cristal/obsidienne 300–420 s, lin 120–180 s, caches de passage 900–1 200 s.

Choix des modèles : `displayId` pris dans `GameObjectDisplayInfo.dbc` (extrait, 1 638 enregistrements ; `generate.py` et `check.py` vérifient l'existence de l'identifiant). Les filons réutilisent les modèles de compétence des filons vanilla (taille 0,5 comme eux).

| Entrée | Nom | Pal. | Type | displayId : modèle | Butin |
|---|---|---|---|---|---|
| 9101001 | Arbre de la prairie | 1 | bois | 5975 `WestFallTree01` | Bois 2–4 ; Résine 25 % |
| 9101002 | Arbre de la forêt noire | 2 | bois | 927 `IronForgeTree01` (conifère) | Bois fin 2–4 ; Bois de cœur 30 % ; Résine 20 % |
| 9101003 | Vieille souche du marais | 3 | bois | 2474 `DeadwindPassMidTree02` (arbre mort) | Écorce ancienne 1–3 ; Bois de cœur 50 % |
| 9101004 | Pin de montagne | 4 | bois | 6158 `AeriePeaksStump01` | Bois de cœur 2–4 ; Résine 20 % |
| 9101005 | Arbre des plaines | 5 | bois | 967 `ArathiTree04` | Bois de cœur 2–4 ; Résine 20 % |
| 9101011–9101015 | Rocher (prairie, moussu, marais, montagne, plaines) | 1–5 | pierre | 4315 `WestFallBoulder01`, 248 `ArathiRock01`, 3992 `PlaguelandRock05`, 5737 `BurningSteppesBoulders01`, 4320 `UngoroRock06` | Pierre 2–4 ; Silex 40 %/30 % (T1/T2) |
| 9101021 | Filon de cuivre | 2 | minerai | 310 `copper_Miningnode_01` | Cuivre 2–4 |
| 9101022 | Filon d'étain | 2 | minerai | 315 `tin_Miningnode_01` | Étain 2–4 |
| 9101023 | Gisement de fer | 3 | minerai | 312 `Iron_Miningnode_01` | Fer 2–4 |
| 9101024 | Filon d'argent | 4 | minerai | 314 `TrueSilver_Miningnode_01` | Argent 2–4 |
| 9101025 | Filon de métal noir | 5 | minerai | 3951 `Thorium_Miningnode_01` | Métal noir 2–4 |
| 9101026 | Gisement d'obsidienne | 4 | minerai | 6650 `Obsidian_Miningnode_01` | Obsidienne 2–3 |
| 9101027 | Formation de cristal | 4 | minerai | 2971 `UngoroCrystal_Blue01` | Cristal 2–3 |
| 9101031 | Plant de lin | 5 | plante | 2315 `Bush_Sungrass` (plante d'herboristerie, par défaut) | Lin 2–4 |
| 9101041–9101045 | Ossements de cerf, Racines de gréling, Roche de Surtling, Cristal de givre, Amas de noyaux noirs | 1–5 | passage | 6328 `BlastedLandsBonePile02`, 148 `SwampSorrowRoot02`, 3711 `LavaRock01`, 2975 `UngoroCrystal_Blue02`, 2571 `DarkIronNode` | matériau de passage du palier 1–2 |

**Non vérifié** : aucun de ces modèles n'a été vu en jeu ; l'échelle des arbres (`size` 1,0) et le comportement du clic sur un modèle d'arbre sont supposés ; le DBC prouve seulement que l'identifiant existe, pas que le rendu est correct.

### Apparitions de validation (005)

`gen_spawns` (dans `generate.py`) ne place **que** des nœuds de validation : 118 nœuds = Elwynn Forest 47, Durotar 47, Dun Morogh 24, `guid` 9500001+ (< 9599999), réapparition = celle du type de nœud (courte). Contenu : un échantillon de **chacun** des 23 modèles près de Northshire (21 dans `Northshire Valley`) et de Valley of Trials (21 dans `Valley of Trials`) ; plus 14 arbres et 10 rochers de palier 1 dans chacune des 3 zones. Coordonnées = positions de la table `creature` (créatures non élites, niveau ≤ 12, hors aires intérieures dont le nom contient Mine/Cave/Abbey/Crypt…), espacement ≥ 12 m, choix déterministe (CRC32 du guid de la créature) ; `z` et orientation viennent de la créature, la rotation est dérivée de l'orientation. **Aucune position n'est inventée, mais le `z` n'a pas été contrôlé contre le terrain** (mmaps absentes) : un nœud peut être légèrement enterré ou flottant. Pas de nœuds de production pour les paliers 2–5 (hors périmètre « validation »).

## 7. Butin de mobs (004)

### 7.1 Critères d'éligibilité (`classify.py`, relus indépendamment par `check.py` en SQL)

Un modèle reçoit du butin seulement si : rang 0 ou 1 (exclus rare, rare élite, boss) ; type ni inconnu, ni critter, ni totem ; `LootId > 0` ; `NpcFlags` limités à gossip/questgiver ; ni civil ni garde ; **toutes** ses apparitions sont sur les cartes 0 ou 1 (une seule apparition en instance/champ de bataille l'exclut) et il en a au moins une. Un `LootId` partagé n'est modifié que si tous ses modèles sont éligibles, de même palier et de même catégorie (en pratique : un seul groupe de 4 modèles dans la base, tous identiques ; 107 `LootId` éligibles n'ont aucune règle pour leur catégorie/palier et ne reçoivent rien). Aucune ligne existante n'est modifiée : on **ajoute** une ligne de référence par `LootId` (`item` = id de la référence, `mincountOrRef` = −id, `ChanceOrQuestChance` = 100) ; elle est tirée 2 fois pour les élites normales (`maxcount` = 2, sémantique `LootTemplate::Process` lue dans `LootMgr.cpp`).

### 7.2 Catégories (heuristiques sur `CreatureType`, `Family`, nom anglais)

Humanoïde → `LOGGER` (nom : logger/lumberjack/woodcutter), `MINER` (miner, trogg, kobold, digger, dark iron, thaurissan…), `BRUTE` (troll, ogre, gnoll, ettin, brute…), sinon `HUMANOID` ; Bête → `BEAST_SPIDER` (famille 3), `BEAST_BASILISK` (nom), `BEAST_MAMMAL` (familles loup/félin/ours/sanglier/gorille/hyène, ou famille 0 avec un nom de mammifère), sinon `BEAST_OTHER` ; Mort-vivant, Géant, Mécanique, Dragonnet, Démon, « Non spécifié » (`OTHER`) par type ; Élémentaire → `ELEM_PLANT` (nom : timber, creeper, moss, treant…), `ELEM_ROCK` (rock, stone, golem, magma, crystal…), `ELEM_OTHER`. **Les catégories à base de noms sont des heuristiques et peuvent se tromper** (ex. un « Creeper » bête de famille 3 est classé araignée).

### 7.3 Règles (extrait : taux par mort, quantité) — table complète : `rules.DROP_RULES`

Un monstre de palier t lâche les ressources du palier t aux taux ci-dessous, et les matériaux **de base** du palier t−1 à 35 % de leur taux (plancher 8 %, quantité ≤ 2) : « retour en arrière ». Les matériaux fabriqués (bronze) ne sont jamais lâchés ; un monstre n'obtient **jamais** de ressource d'un autre palier (vérifié par `check.py`).

| Ressource | Catégories et taux principaux |
|---|---|
| Bois / Bois fin | bûcheron 50 %, élémentaire-plante 50 %, géant 25 %, humanoïde 20 % (1–3) |
| Pierre | mineur 50 %, élémentaire-roche 50 %, géant 40 %, mécanique 30 %, humanoïde 15 % |
| Silex | mineur 40 %, brute 30 %, élémentaire-roche 30 %, humanoïde 25 % |
| Résine | élémentaire-plante 45 %, araignée 30 %, humanoïde 10 % |
| Peau de cerf | bête-mammifère 50 %, autre bête 20 % |
| Chutes de cuir | brute 45 %, humanoïde 45 %, mammifère 30 %, mort-vivant 25 % |
| Cuivre / Étain | mineur 45/40 %, roche 40/35 %, mécanique 30/25 %, humanoïde 15/12 % |
| Peau de troll | géant 50 %, brute 45 %, mammifère 25 % |
| Fer | mineur 45 %, roche 40 %, mécanique 35 %, géant 20 %, humanoïde 12 % |
| Écorce ancienne | plante 45 %, bûcheron 35 %, géant 30 %, « non spécifié » 15 %, humanoïde 10 % |
| Fragments d'os / Entrailles | mort-vivant 50 % / bête 45 % ; autres bêtes 20 % |
| Argent / Obsidienne | mineur 40 %, roche 35 % / roche 40 %, dragonnet 35 %, géant 30 %, mineur 25 %, démon 20 % |
| Fourrure de loup / Cristal | mammifère 50 % / basilic 40 %, roche 30 %, géant 20 %… |
| Métal noir | mineur 40 %, roche 35 %, mécanique 35 %, démon 25 %, géant 20 % |
| Lin / Fil de lin | plante 40 %, humanoïde 25 % / humanoïde 35 %, mort-vivant 25 %, plante 25 % |
| Peau de lox | mammifère 50 %, autre bête 25 % |
| Matériaux de passage | 3–10 % selon la catégorie |

Les matériaux de base ont tous un taux principal dans 30–60 % avec quantité variable (contrôlé par `check.py`). Les valeurs 30–60 % sont celles des catégories « de métier » (bêtes à peau, mineurs…) ; les catégories secondaires sont plus basses pour éviter qu'un monstre quelconque ne rende tout.

### 7.4 Simulation (`sim_result.txt`, 20 000 morts ; sémantique du serveur reproduite, pas le serveur)

Large Crag Boar (niv. 6–7) : Peau de cerf 50,3 %, Chutes 30,1 %, Andouiller 8,0 %. Rockjaw Trogg (niv. 1–2) : Pierre 50 % (1,0/mort), Silex 40 %, Chutes 46 %, Bois 20 %, Résine 10 %. Shadowhide Gnoll (niv. 22–23, brute) : Peau de troll 45 %, Bois fin 20 %, Cuivre 15 %, Étain 12 %… (plus du palier 1 à 8–16 %). Skeletal Warder (niv. 28–29) : Fragments d'os 49,6 %. Wandering Protector (élite) : Écorce ancienne 60 %, Fer 40 %, Peau de troll 36 %. **Une mort peut ajouter jusqu'à 6 lignes** de butin Wowlheim (humanoïdes de palier 1) : ça agrandit la fenêtre de butin ; si c'est trop, réduire `HUMANOID` dans `rules.py`.

## 8. Source de secours : vendeurs (006)

Matériaux **de base** uniquement, stock limité (20, réapprovisionné toutes les 30 min), au prix de revente ×10 (T1 : 40 cuivre ; T5 : 32 argent 40 cuivre). Vendeurs : PNJ existants de sous-titre « General… » ou « Trade… » (à défaut aubergistes/mineurs/forgerons), hors capitales, dans les zones dont le niveau médian correspond au palier ; au plus 6 zones par (continent, palier) : 33 vendeurs choisis. Les ressources de passage et le bronze ne sont jamais vendus.

## 9. Résultats des contrôles (`check_result.txt`, base `wl_scratch` + comparaison à `classicmangos`)

**Formes (toutes OK, code retour 0)** : 39 objets présents, description « Wowlheim », aucune compétence/sort/serrure ; les 24 identifiants imposés par le cahier présents et bien nommés ; 75 références / 264 lignes valides (miroir de `LootStore::IsValidItemTemplate` : chance > 0, min ≤ max, objet existant, références existantes) ; aucune référence ne contient une ressource hors palier ; 2 296 lignes ajoutées, **0** sur rang rare/élite rare/boss/PNJ/critter/totem, **0** sur un `LootId` d'une créature hors cartes 0/1, 0 `LootId` partagé ; 23 nœuds : type 3, `data0` = 0, `displayId` présent dans le DBC ; lignes hors plages Wowlheim **identiques** à `classicmangos` dans 7 tables (compte + somme CRC32) : `creature_loot_template` 151 800, `reference_loot_template` 32 972, `item_template` 17 718, `gameobject_template` 10 750, `gameobject_loot_template` 12 547, `npc_vendor` 11 694, `gameobject` 47 370 (au moment du contrôle ; un autre travail peut faire dériver ce dernier chiffre). Scripts appliqués **deux fois** de suite sans erreur.

**Zones par continent (butin de palier natif, ≥ 10 apparitions par zone)** : chaque matériau de base couvre ≥ 3 zones sur Royaumes de l'Est et sur Kalimdor (de 4 à 10 zones ; minimum : Fourrure de loup 4/4, Peau de lox 4/6, Noyau de Surtling 6/4). Couverture par palier (toutes ressources du palier) : EK 7 / 9 / 10 / 10 / 9 zones, Kalimdor 7 / 5 / 5 / 7 / 9 zones pour T1…T5. Par faction (Alliance/Horde ; zones contestées comptées pour les deux ; **classification des zones manuelle, non vérifiée par les données**) : le plus bas est « Horde, Royaumes de l'Est, palier 1 » : 2 zones (Tirisfal, Silverpine) pour Bois, Pierre, Silex, etc. ; l'exigence du cahier (3 zones par continent) ne porte pas sur la faction.

Sources par ressource : voir le tableau de `check_result.txt` (section 2). Résumé : Bois, Pierre, Silex, Résine, Bois fin, Bois de cœur, Cuivre, Étain, Fer, Écorce ancienne, Argent, Obsidienne, Cristal, Métal noir, Lin = **3 types de sources vérifiés** (butin + nœud + vendeur) ; les passages = 2 (butin + nœud) ; peaux, os, entrailles, fourrure, fil de lin = 2 (butin + vendeur) ; bronze = 0 (conversion seulement).

## 10. Ce qui NE PEUT PAS être satisfait avec les données du jeu (ou n'est pas vérifié)

Constats listés par `check.py` (section 5) :

1. **Peau de cerf, Chutes de cuir, Peau de troll, Fragments d'os, Entrailles, Fourrure de loup, Peau de lox, Fil de lin : pas de nœud** (une peau ou une fourrure ne se récolte pas dans un arbre ou un rocher). Ils ont ≥ 3 sources au sens « familles de créatures indépendantes + vendeur » (4 à 18) mais seulement 2 *types* de sources. Proposition : un nœud « Carcasse/dépouille » (GameObject) *ou* une conversion serveur ; deux conversions sont déjà proposées (Chutes de cuir, Fil de lin).
2. **Bois et Silex : seulement 2 types de créatures (humanoïdes, élémentaires)** — il n'existe pas de géants au palier 1 et aucune bête ne justifie du bois/silex. Les autres sources (nœud + vendeur) portent le total à 4 sources indépendantes.
3. **Bronze** : aucune source de butin/nœud/vendeur par conception ; dépend d'une conversion à coder.
4. **Vendeurs de secours insuffisants dans trois (continent, palier)** : palier 4 Royaumes de l'Est (2 zones), palier 5 Royaumes de l'Est (1 zone : Eastern Plaguelands), palier 5 Kalimdor (2 zones : Winterspring, Silithus) : il n'y a pas assez de vendeurs « General/Trade » existants dans ces zones. Proposition : ajouter des PNJ vendeurs dans les camps (Light's Hope, Chillwind, Morgan's Vigil, Cenarion Hold…), ce qui sort de mon périmètre.
5. **Noeuds de production absents** pour les paliers 2–5 (seuls les échantillons de validation existent) : le critère « nœud comme source » n'est « vérifié » que comme *modèle défini*, pas comme présence en jeu.
6. **Non vérifié** : le chargement du butin par le serveur réel (jamais lancé : un autre travail utilise le serveur), l'accessibilité des zones (pas de mmaps), les modèles à l'écran, la hauteur des nœuds, le rendu des glyphes accentués, l'équilibrage (taux et prix choisis par moi, aucun test en jeu), la faction des zones.

## 11. Limites et pièges connus

- Les noms anglais du jeu servent aux heuristiques ; un client localisé n'y change rien (la base reste en anglais).
- `gameobject` : `spawnMask` = 1 comme les apparitions vanilla de la base ; `animprogress` n'existe pas dans ce schéma.
- Les plages d'objets 9200001–9299999 couvrent aussi les outils 9201xxx : `002_items.sql` supprime toute la plage avant d'insérer.
- Le champ `Quality` conditionne les taux (`Rate.Drop.Item.Normal/Uncommon`) : tous valent 1 dans `mangosd.conf` (lu, non modifié).
- Les scripts utilisent des tables MyISAM (pas de transaction) : en cas d'échec au milieu d'un script, le rejouer en entier suffit (idempotent).
- Pour régénérer après un changement de `rules.py` : `python build_cache.py` (si la base de créatures a changé), `python generate.py`, `python validate_scratch.py`.
