# Import des assets et données de Valheim dans WoW 1.12.1

Usage privé, non distribué (cahier des charges, « Droits »). Les fichiers produits sont des artefacts locaux hors dépôt
(`C:\Wowlheim\valheim_extract`, `C:\Wowlheim\wl_assets`). Outils : `tools/valheim/` ; exécuter les scripts Unity avec
`C:\Wowlheim\tools\unity_venv\Scripts\python.exe` (UnityPy, Pillow, numpy).

## Chaîne complète

| Étape | Script | Entrée → sortie |
|---|---|---|
| Index des bundles | `vh_index.py` | `StreamingAssets/SoftRef/manifest_extended` → `index.json` (chemin d'asset → bundle) |
| Données de jeu | `vh_dump_all.py`, `vh_dump.py` | MonoBehaviours des prefabs (typetrees des bundles) : table du marteau, `Piece`, `WearNTear`, `TreeBase`, `TreeLog`, `MineRock`, `Destructible`, `DropOnDestroyed`, `ItemDrop`, `Recipe_*` → `valheim_data.json` |
| Traductions | `vh_loc.py` | `resources.assets` (TextAsset `localization`) → `localization.txt` (colonne French) |
| Modèles | `build_assets.py` (+ `vh_mesh.py`, `wowfmt.py`) | LOD0 de l'état « neuf » (sans Worn/Broken/WET), Unity (main gauche, Y en haut) → WoW (main droite, Z en haut) ; M2 v256 + BLP2 ; collisions ; animations des arbres (chute, couché, secousse) et des roches (éclatement) ; points d'accroche `$hud_snappoint` → `wl_assets/mpq`, `manifest.json` |
| Icônes | `build_icons.py` | sprites `Piece.m_icon` / `m_icons` → `Interface\Icons\WL_*.blp` (64×64) |
| Patch client | `gen_client_patch.py [--install]` | DBC (GameObjectDisplayInfo 20000+, CreatureModelData 3000+, CreatureDisplayInfo 25000+, ItemDisplayInfo 70000+, Spell 40001, SpellIcon 3000) → `patch-3.MPQ` ; mêmes DBC copiés dans `C:\Wowlheim\data\dbc` (originaux : `dbc_orig`) ; `wl_ids.json` |
| Serveur + addon | `gen_server_sql.py` | `server/sql/world/012_valheim_content.sql` et `tools/client/addon/Wowlheim/WowlheimData.lua` |
| Contrôle hors jeu | `m2_preview.py` | rendu logiciel d'un M2 (géométrie, UV, textures BLP) |

Ordre de reconstruction : `build_assets.py` → `build_icons.py` → `gen_client_patch.py --install` → `gen_server_sql.py` →
`python tools/apply_sql.py --backup` → redémarrer mangosd et le client.

## Format M2 1.12 : points vérifiés en jeu (2026-10-26)

Comparaison octet par octet avec des M2 d'origine du client (`GrainCrate01.m2`, `Axe_1H_Hatchet_A_01.m2`) puis essais en jeu :
- en-tête de 324 octets ; sommet de 48 octets (deux jeux d'UV) ; os de 108 octets ; vue embarquée de 44 octets, 4 vues ;
- **`boneCountMax` des 4 vues doit décroître (256, 75, 53, 21)** : avec 256 partout le modèle est invisible ;
- BLP2 palette : **toujours un plan alpha 8 bits** (sans alpha, le client affiche des blocs colorés) ;
- piste de transparence sans plage d'interpolation, table des animations jouables copiée d'un modèle d'origine.

### Textures et matériaux (corrections du 2026-10-26 soir)

- **Textures de modèles en DXT, comme le client d'origine** (`wowfmt.write_blp`, `fmt="dxt"` par défaut) : relevé de
  800 en-têtes de `texture.MPQ` / `interface.MPQ` — `World\`, `Creature\`, `Item\ObjectComponents\` sont toujours en
  BLP2 compression 2 : DXT1 `(2, 0, 0, 1)` opaque, DXT3 `(2, 8, 1, 1)` avec alpha ; la palette `(1, 8, 8)` ne sert
  qu'aux textures de personnage composées et à l'interface. Nos textures palette ressortaient délavées / rosées sur les
  modèles (troncs, roches, dessus de l'établi, feuillage en plaques pâles). Les **icônes restent en palette**
  (`build_icons.py`, `fmt="palette"`), correctes en jeu.
- **Décalage de 4 octets des niveaux de mipmap** : l'en-tête BLP2 fait 1172 octets (fichiers d'origine : premier niveau à
  1172), `wowfmt` écrivait 1176. Corrigé dans les deux écritures ; en-têtes des 472 icônes existantes corrigés sur place.
- **Alpha testé décidé par le matériau Valheim** (`vh_mesh.mat_info`, `build_assets.is_alpha_tex`) : shader
  `Custom/Vegetation`, `Custom/Grass`, `Custom/Rug`, `_Mode` 1 (Cutout) ou `_ALPHATEST_ON`, sinon le nom (`CUTOUT`) ;
  écorces / bûches / souches exclues (leur alpha = mousse). Sapins, pins, buissons, bannières, lin, orge, pissenlit,
  tapis, lit, guirlande étaient opaques ; « DarkWoodChair » n'est plus découpé (« hair » dans « chair »).
  Texels transparents recolorés par leurs voisins (pas de liseré), couverture alpha conservée dans les mipmaps.
- **Teinte `_Color` du matériau cuite dans la texture** (`vh_mesh.mat_tint`, texture nommée `<nom>_cRRGGBB`) :
  établi 0.62, écorces de chêne / bouleau 0.69, branches du marais (0.38, 0.41, 0.22)...
- **Outils tenus en main** : le M2 avait une texture de type 0 au nom **vide** (aucun fichier chargé → outil blanc) ;
  il porte maintenant le chemin de sa texture (`World\Wowlheim\Textures\weapons.blp`, etc.).
- **Icône grise du menu du marteau** : l'addon désaturait l'icône d'une pièce non abordable (`SetGrey`) ; elle reste
  en couleur, teintée de rouge (0.8, 0.5, 0.5).
- **Rochers en aplats pastel** : les M2 étaient opaques (blend 0, DXT1 `(2, 0, 0, 1)`), sans triplanaire en cause
  (`_TriplanarMap` 0 sur tous les `Custom/StaticRock`). Cause : `MineRock_Copper` / `MineRock_Iron` / `MineRock_Stone`
  sont des **prototypes inutilisés** de Valheim (24 galets « default », texture 64 px ocre/vert ou orange, très claire :
  saturée en pastel sous l'éclairage WoW, étirée sur des galets de 1,5 m). `build_assets.VISUAL` garde le nom de jeu
  (PV / butin du serveur inchangés) mais prend le modèle que Valheim place : cuivre → `rock4_copper` (roche grise,
  veines cuivre / vert-de-gris), pierre → `rock4_coast`, fer → `mudpile` (tas de boue des cryptes). `rock4_*`
  (24 × 28 m, 17 m enterrés) ramené à 0,4 (≈ 10 × 11 m, 1,6 m hors sol, jupe de 1 m sous le sol).
  **À régénérer côté serveur** (`gen_server_sql.py`) : `combat_reach` des roches vient de la bbox du manifeste.
- **`_MainTex_ST` appliqué aux UV** (`vh_mesh.ST_SHADERS` : `Standard`, `Custom/StaticRock`) : filon d'argent ×2,5,
  rocher ×2, `rock4_*` ×8, silex ×0,2, souches, enclume étaient étirés. `Custom/Piece` exclu (planches −0,56 × 0,12 :
  le tuilage n'y sert pas au placement ; pièces de pierre, fonderie, forge, four : UV0 justes, inchangés).
  `Custom/Trilinearmap` (boue) : projection triplanaire « boîte » par face, échelle `_UVScale`.
- **`lay_down` limité aux bûches d'arbres** (genre `tree`) : `wood_pole_log` était couché le long de X ; `vh_colliders.py`
  n'applique plus de rotation (boîtes régénérées).
- `m2_preview.py` rend désormais par pixel (UV interpolées, alpha testé à 128 si blend 1, deux faces si drapeau 0x04,
  magenta si la texture est absente) : `tools/valheim/out/*_before.png` / `*_after.png`.

## Monde progressif : arbres, roches, filons et ramassables de Valheim (2026-10-26)

Détail du placement et des contrôles : `docs/RESOURCES_NODES.md` ; règles : `docs/RESOURCES.md` §0.

- **Prefabs ajoutés** (`vh_dump.py` → `extra4.json`, `extra5.json`, fusionnés dans `valheim_data.json` ; sauvegarde `valheim_data.json.bak_avant_ramassables`) : `Pickable_*` (Branch, Stone, Flint, Mushroom, Dandelion, Thistle, Flax_Wild, Barley_Wild, TarBig, MountainCaveCrystal…), `RaspberryBush`, `BlueberryBush`, `CloudberryBush`, `SwampTree1` (+ `_log`, `_Stub`), `silvervein` / `silvervein_frac` (MineRock5), `FreezeGland`, `BlackCore`, `Mushroom`.
- **Modèles** (`build_assets.py`) : nouveau genre `pickable` (`PICKABLES`, 13 modèles, sans collision) ; `SwampTree1`, `SwampTree1_log`, `SwampTree1_Stub` (arbre ancien du marais : animations de chute comme les autres arbres) ; `silvervein` (roche, animation d'éclatement). `Pickable_MountainCaveCrystal` et `Pickable_TarBig` sans `_MainTex` → couleur unie (`FLAT_COLOR`). Icônes : `build_icons.py --only FreezeGland BlackCore` (Champignon existait). `manifest.json` / `icons.json` sauvegardés (`*.bak_avant_ramassables`).
- **Patch client** (`gen_client_patch.py`, sans `--install`) : `GameObjectDisplayInfo` des ramassables (genre `pickable`), créatures de `SwampTree1`/`silvervein`, `ItemDisplayInfo` de 9200039 Glande gelée, 9200049 Noyau noir, 9200082 Champignon ; objets retirés : 9201041, 9201042, 9201052. `patch-3.MPQ` régénéré, **non installé**.
- **Serveur** (`gen_server_sql.py` → `012`) :
  - ramassables : `gameobject_template` 9130001–9130013 (identifiants stables `PICK_IDS`), type 3 sans verrou, butin = `Pickable.m_itemPrefab` × `m_amount` (Goudron ×15, Lin et Orge ×2, autres ×1), réapparition `m_respawnTimeMinutes` (0 dans Valheim → 240 min, [ADAPTATION] serveur partagé) ;
  - créatures : essences et roches par type de `rules.PLACEMENTS` ; `SwampTree1` : le tronc final se brise directement en Bois / Écorce ancienne (10 tirages, `TreeLog` sans `m_subLogPrefab`), hache en bronze (`m_minToolTier` 2) ; `silvervein` : PV et butin de `silvervein_frac` (100 fragments × 50 PV, palier de pioche 2 + 1 = pioche en fer), mêmes regroupement et hypothèse « 3 fragments par coup » que les autres filons ;
  - contrôle : les matériaux annoncés par `rules.PLACEMENTS` (`gives`) doivent figurer dans les DropTable de Valheim (assertion) ;
  - outils lus dans les prefabs (palier, dégâts, durabilité) ; recettes : toutes les `Recipe_*` réalisables (`RECIPE_IDS`, identifiants stables) ; noms français et piles de Valheim pour tous les objets.
- `tools/client/addon/Wowlheim/WowlheimData.lua` (généré par le même script) : + Glande gelée, Noyau noir, Champignon ; − Pioche en sombracier.

## Adaptations (écarts assumés avec Valheim)

- Pièces recentrées (base au sol, centre en x/y) : le serveur pose une pièce par sa base.
- Accroche : 0,5 m comme Valheim ; repli à 1 m à l'horizontale (jusqu'à 4 m au-dessus) faute de visée précise.
- Arbres, bûches et roches = créatures frappées en mêlée ; compétence de bûcheronnage/minage fixée à 0.
- MineRock : zones regroupées (PV et butin × nombre de zones), 3 zones touchées par coup [INFÉRÉ].
- Minerai : les filons donnent le minerai de Valheim (objets 9200060–9200064 ; icônes : `build_icons.py --only CopperOre TinOre IronScrap SilverOre IronOre`), fondu à la fonderie / au four à charbon (docs/VALHEIM_RULES.md §9, adaptations §9.7).
- Outils : modèles agrandis ×1,3 (les outils de Valheim sont petits à côté des armes de WoW).

## Catalogue du marteau (2026-10-26) : 162 pièces sur les 397 de Valheim

Table `_HammerPieceTable` de Valheim : 398 entrées dont l'outil Réparer, soit **397 pièces**. Importées : **161 pièces de la table + `wood_wall_roof`** (ancien prefab du « Mur en bois 26° », gardé car déjà posé en base) = **162** (`build_assets.py` PIECES, `gen_server_sql.py` PIECE_IDS).
Identifiants **stables** dans `gen_server_sql.py` (`PIECE_IDS`) : 1–83 = catalogue d'origine, 84–162 = extension ; toute nouvelle pièce s'ajoute à la suite (avant, les identifiants 13+ étaient attribués par ordre alphabétique et changeaient à chaque ajout de modèle).

Ajoutées (79) par onglet : Construction 25 (croix de toit 26/45°, poutre en bûche 67°, fer et bois ×5, bois sombre ×17 : poteaux, poutres, arche, séparateur, toits de bardeaux, portail), Construction lourde 6 (cage en fer ×4, portail de fer, mur de cristal), Fabrication 3 (table d'artisan, rouet, haut fourneau), Meuble 28 (trônes ×2, chaise de bois sombre, longue table lourde, coffres personnel et en sombracier, support d'armure, présentoir horizontal, torches en fer ×3, braseros ×3, tapis de lox et de paille, bannières 02–11, guirlandes ×2), Divers 17 (portail de bûches, clôture en pierre, dragon/corbeau/loup décoratifs, cible, tas de bois précieux/robuste, de silex, de barres ×6, de charbon, d'os).
Modèles : `vh_mesh.export_prefab` a deux options (désactivées par défaut, les modèles existants sont inchangés — vérifié : boîtes et sommets identiques) : `skinned` (SkinnedMeshRenderer en pose de liaison : table d'artisan, rouet, haut fourneau) et `flat_color` (sous-maillage sans `_MainTex` → texture unie de `_Color` : mur de cristal, tas de barres d'étain/cuivre/bronze/argent). Le haut fourneau (13 684 triangles) n'a pas de collision (> 4 000 triangles).
Stations : `kind` d'une station = nom de `Piece.m_craftingStation` (`artisan` pour la table d'artisan) ; machines Smelter = nom du prefab sans `piece_` (`blastfurnace`, `spinningwheel` : **leurs conversions ne sont pas encore branchées** dans `build_smelters`/`Smelter.cpp`, ce sont pour l'instant des stations sans effet).

**Non importées (236)** et pourquoi (liste calculée depuis `valheim_data.json`) :

| Motif | Nb | Pièces |
|---|---|---|
| Biome après les Plaines (Brumes, Terres de cendres, Grand Nord) : matériaux hors des 5 paliers du cahier (niveaux 1–60) — marbre noir, bois d'Yggdrasil, cendrebois, grise-pierre, flametal, sapin nordique, or-sang, jute, peaux d'askvin/élan/phoque/lièvre, eitr, noyaux… — ou station de ces biomes (forge noire, table de galdr, raffinerie d'eitr, fonderie/four à givre) | 131 | blackmarble_* (14), dvergr (6 dont `piece_dvergr_metal_wall_2x2`, cuivre mais station Forge noire), ashwood_* (27), grausten (26), flametal (3), stave_gate, drawbridge, icecube, cauldron_ext5–7, artisan_ext1, blackforge + 5 ext., magetable + 4 ext., FrostFoundry, eitrrefinery, FrostKiln, sapcollector, EternalPyre, ashwood_bed, trônes marbre/os/élan, bancs/table marbre et cendrebois, pots ×3, torche de feu-follet, lanternes dvergr/lave/couverte, tapis lièvre/askvin/élan, jute ×5, piles yggdrasil/cendrebois/sapin/marbre/grise-pierre/flametal/or/crânes, portal_stone, shieldgenerator |
| Onglet `DEEPNORTH` (libellé non traduit : contenu non publié) | 57 | toutes les variantes 67° sauf `wood_log_67` et `woodiron_beam_67` (onglet Construction), stave_* et scale_* (sapin nordique), meubles « sculptés », penderie, coffre grise-pierre, lanterne de neige, tapis de phoque |
| Mécanique absente dans WoW | 23 | cuisine (poste de cuisson ×2, chaudron + 3 ext., table de préparation, four, moulin), hydromel (chaudron, fermenteur), ruche et nid d'oiseaux, fontaine aux feux-follets, oblitérateur, baignoire, barbier, table de cartographie, mannequin, piège, pont-levis rustique, pierre de compagnie, squelette d'askvin |
| Saisonnier désactivé dans Valheim (`m_enabled = 0`) | 9 | Yuleklapp ×3, lanterne d'Halloween, mât de Cocagne, gui, couronne/guirlande/arbre de fête |
| Véhicules, bateaux, armes de siège | 8 | Cart, Raft, Karve, VikingShip, VikingShip_Ashlands, baliste, bélier, catapulte |
| Objet sans source possible ici | 5 | trésors (pièces de monnaie, rubis, colliers : `treasure_stack`, `treasure_pile`, `piece_chest_treasure`), `piece_chest_barrel` et `Candle_resin` (cercles de tonneau / mèche : vendus par la sorcière, aucune recette) |
| Autre | 3 | `wood_wall_roof_a` (doublon de `wood_wall_roof` : même nom, même coût), `fire_pit_iron` (objet « Ironpit » trouvé, pas de recette), `rug_Bjorn` (3 trophées d'ours à créer pour un seul tapis) |

Les portails : `portal_wood` est gardé (déjà au catalogue ; téléportation non implémentée, pièce décorative) ; `portal_stone` exclu (grise-pierre, noyau fondu).

### Matériaux des pièces (objets 9200051–9200057 et 9200070–9200080)

Noms et icônes de Valheim (`ITEM`/`NEW_ITEMS` de `gen_server_sql.py`, `ITEM_PREFAB` de `gen_client_patch.py`) ; palier, prix et sources dans `tools/resources/rules.py` (même source que 002/004/006). Prefabs ajoutés à `valheim_data.json` par `vh_dump.py` (`extra3.json`) : Blueberries, Carrot, Bloodbag, WolfClaw, DragonTear, Cloudberry, Barley, Flax, Entrails. Correctif : l'icône de 9200024 « Entrailles » était celle de la Viscosité (Guck) ; elle est maintenant celle des Entrailles, et 9200042 « Lin » reçoit l'icône du lin.

| Objet | Valheim | Pal. | Sources (butin WoW : catégorie, taux principal ; plus aucun vendeur depuis le 2026-10-26) |
|---|---|---|---|
| 9200051 Charbon | Coal | 2 | mineurs 35 %, élémentaires de feu 30 %, démons 15 % ; four à charbon (Smelter) |
| 9200052 Chaîne | Chain | 3 | morts-vivants 35 % (spectres de Valheim), mécaniques 25 %, brutes (ogres) 20 % — n'avait **aucune** source (Valheim : butin, pas de recette) |
| 9200053/54 Clous en bronze/fer | BronzeNails/IronNails | 2/3 | recettes de Valheim (forge) |
| 9200055 Plumes | Feathers | 1 | oiseaux 55 % (nouvelle catégorie `BEAST_BIRD` : charognards, haut-trotteurs, chouettes) |
| 9200056 Roue à aiguiser | SharpeningStone | 3 | recette de Valheim (tailleur de pierre) |
| 9200057 Goudron | Tar | 5 | limons/« non spécifié » 45 %, élémentaires 30 % (bêtes de goudron d'Un'Goro), élémentaires-plantes 30 % |
| 9200070 Framboises / 9200071 Pissenlit | Raspberry / Dandelion | 1 | élémentaires-plantes 45/40 % ; mammifères 20 % / humanoïdes 10 % |
| 9200072 Myrtilles / 9200073 Chardon / 9200074 Carotte | Blueberries / Thistle / Carrot | 2 | plantes 45/40/30 % ; mammifères 20 % / humanoïdes 12 % / mammifères 15 % |
| 9200075 Viscosité / 9200076 Poche de sang | Guck / Bloodbag | 3 | limons 50 %, plantes 25 %, bêtes 15 % / bêtes (crocilisques, chauves-souris…) 35 %, morts-vivants 15 % |
| 9200077 Griffes de Fenris | WolfClaw | 4 | mammifères (loups, worgs) 35 %, brutes (gnolls) 15 % |
| 9200078 Larme de dragon | DragonTear | 4 (passage) | draconiens 10 %, élémentaires 4 % (pour la table d'artisan ; l'ancien nœud « Cristal de givre » est supprimé) |
| 9200079 Plaquebières / 9200080 Orge | Cloudberry / Barley | 5 | plantes 40/35 % ; mammifères 15 % / humanoïdes 15 % |

Contrôles (`tools/resources/validate_scratch.py`) : formes **toutes OK** ; constats : Plumes 1 zone sur les Royaumes de l'Est (peu d'oiseaux de palier 1 hors Westfall), Chaîne 2 zones sur Kalimdor, Goudron/Pissenlit/Chardon/Orge 2 familles de créatures seulement (+ vendeurs).
