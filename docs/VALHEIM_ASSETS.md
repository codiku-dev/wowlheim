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

## Adaptations (écarts assumés avec Valheim)

- Pièces recentrées (base au sol, centre en x/y) : le serveur pose une pièce par sa base.
- Accroche : 0,5 m comme Valheim ; repli à 1 m à l'horizontale (jusqu'à 4 m au-dessus) faute de visée précise.
- Arbres, bûches et roches = créatures frappées en mêlée ; compétence de bûcheronnage/minage fixée à 0.
- MineRock : zones regroupées (PV et butin × nombre de zones), 3 zones touchées par coup [INFÉRÉ].
- Minerai → métal direct (pas de fonderie).
- Outils : modèles agrandis ×1,3 (les outils de Valheim sont petits à côté des armes de WoW).
