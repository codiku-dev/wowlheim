# Wowlheim — Nœuds de ressources de production (phase 4, suite)

Remplace les 118 nœuds « de validation » (005, trois zones de départ) par des nœuds de **production** sur les continents (cartes 0 et 1). Tout le SQL est généré par script, lecture seule de `classicmangos` et des cartes `.map` du client ; **rien n'a été appliqué sur `classicmangos`** (validation sur une copie jetable `wl_scratch2`, supprimée ; vérifié : `show databases` ne la liste plus).

## 1. Livrables

| Fichier | Rôle |
|---|---|
| `server/sql/world/008_node_spawns_production.sql` | **4 664 nœuds**, guid 9510001–9514664, rejouable (idempotent), 434 Ko |
| `tools/resources/gen_nodes_production.py` | générateur (`python gen_nodes_production.py [--stats]`, ≈ 1 min 30 ; déterministe : deux exécutions donnent un fichier identique, vérifié par `cmp`) ; journal : `gen_nodes_production_result.txt` |
| `tools/resources/nodes_common.py` | paramètres (plafonds, rayons, espacements, répartition par type) et fonctions partagées |
| `tools/resources/nodes_terrain.py` | lecture du terrain statique (hauteur, trous, eau) dans les `.map` : réécriture Python de `GridMap::getHeightFrom*`, `isHole`, `getLiquidStatus` (source lu dans `C:\Wowlheim\src`) |
| `tools/resources/check_nodes.py` | contrôles (section 4) ; sortie : `check_nodes_result.txt` |
| `tools/resources/validate_nodes_scratch.py` | crée `wl_scratch2`, copie 6 tables, applique 003, 005, 010 puis 008 **deux fois**, lance `check_nodes.py`, supprime la base |

Aucun fichier existant de `tools/resources/` n'est modifié. Ordre d'application : 003 et 005 (déjà en base), 010 (table des points d'exclusion, déjà en base), puis 008.

## 2. Résultat chiffré

- **4 664 nœuds** (plafond fixé : 6 000) : Royaumes de l'Est 1 833, Kalimdor 2 831 ; par palier T1 1 125, T2 1 080, T3 732, T4 984, T5 743 ; les 23 modèles 9101001–9101045 sont tous utilisés (de 52 à 515 exemplaires).
- 37 zones (20 sur la carte 0, 17 sur la carte 1) ; 54 régions (zone × palier), dont 21 « poches » (section 3, point 4). Détail par zone : `gen_nodes_production_result.txt` et section 5 de `check_nodes_result.txt`.
- Réapparition = celle du type (bois et lin 120–180 s, pierre 150–210 s, minerai/cristal/obsidienne 300–420 s, caches de passage 900–1 200 s), `spawnMask` 1.
- guid 9510001–9514664 : la plage 9500001–9500999 (005) n'est pas touchée (118 nœuds de validation inchangés, vérifié).

### Plafond et charge (proposition : ≤ 6 000 nœuds au total)

Chaque spawn est un GameObject chargé avec sa grille serveur (533,33 m). Mesures sur la copie : 47 488 GameObjects hors production dans la base, la production en ajoute 4 664 (**+ 9,8 %**) ; au plus **23 nœuds par grille** (moyenne 7,3 sur 636 grilles occupées, plafond appliqué 32) ; au plus **45 par bloc de 1 km²** (moyenne 19,1 sur 244 blocs, plafond 45). Densité visée : 30 nœuds/km² de « surface couverte » (cellules de 250 m contenant au moins un candidat : 154,5 km² au total ; cette surface est celle où se trouvent des créatures, pas la surface géographique des zones), plafond par (zone, palier) 30/km², sauf les petites régions rajoutées pour la couverture (jusqu'à 60/km² dans la plus petite, Stonetalon T1, 0,25 km²). Le plafond de 6 000 est une marge de sécurité (+ 12,6 % de GameObjects au maximum) : **le coût en tick n'est pas mesuré** (en phase 2, 2 000 pièces statiques n'ont pas eu de coût mesurable au repos ; rien de mesuré avec des joueurs).

## 3. Algorithme (positions déduites des données du jeu)

1. **Candidats** : positions de la table `creature` (cartes 0/1). Écartées : rang ≠ 0 (élites, rares, boss : 5 334), critters et totems (2 797), créatures à drapeaux PNJ / civiles / gardes (4 921), patrouilles à waypoints (1 231 : routes), déplacement sans sol ou volantes (474), assistants invisibles et cibles d'entraînement de niveau ≤ 1 (type 9/10 : 1 182, dont 1 129 « Scourge Invasion Minion, finder »). Les apparitions à entrées multiples (`creature_spawn_entry`) doivent toutes les satisfaire. **z et orientation viennent de la créature** ; la rotation est dérivée de l'orientation comme en 005. Aucune position inventée.
2. **Exclusions** (rejets chiffrés dans le journal) : rayon **100 m** autour des 104 points de `010_nobuild_points.sql` (lus dans le fichier : 335 candidats) ; rayon **50 m** autour de toute créature à drapeaux PNJ / civile / garde (5 599 créatures : villages, camps, avant-postes ; 2 129) ; aires de villes, capitales, arènes (drapeaux `AreaTable` `0x100|0x200|0x08|0x20|0x80`, les mêmes que `BuildingMgr.cpp` : 120) ; intérieurs par le **nom d'aire** (même motif que 005 : Mine, Cave, Abbey, Crypt… : 1 271) ; eau à moins de 6 m dans le terrain (2 383) ; **z de la créature à plus de −1/+1,5 m du terrain statique** (3 364 : bâtiments, ponts, grottes sous la montagne) ; trous de terrain ; zones sans palier (< 30 apparitions : Moonglade, etc.). Pas d'instance ni de champ de bataille (cartes 0/1 seulement).
3. **Zone** : lue dans les `.map` (`common.zone_of`, même algorithme que `GridMap::getArea`) ; **palier de zone** = niveau médian des créatures de la zone (`generate.zone_tiers`, celui de `RESOURCES.md`) ; **faction de zone** = `rules.ZONE_FACTION` (non modifiée ; toute zone absente = contestée).
4. **Palier d'un nœud** : niveau médian des créatures non élites du voisinage (bloc de 3×3 cellules de 200 m), mêmes bornes que partout (T1 < 15 ≤ T2 < 28 ≤ T3 < 40 ≤ T4 < 52 ≤ T5). Un palier n'est utilisé dans une zone que s'il est celui de la zone, ou son palier **voisin** à condition d'y avoir au moins 25 candidats (« poche » : p. ex. le haut niveau de Silverpine, T2 dans une zone T1). Un candidat est rejeté si un second estimateur (disque de 300 m) donne plus d'un palier d'écart (21 rejets). Résultat : 3 725 nœuds au palier de leur zone, 939 à ±1 (poches). **Écart avec la consigne** : le palier d'un nœud n'est donc pas toujours celui de la médiane de zone (Barrens T1 en poche, Barrens T2, etc.) ; le critère « bon palier de niveau de zone » est respecté à ±1 palier, avec ce niveau local, pas à la lettre.
5. **Quotas** proportionnels à la surface couverte de chaque région, répartis par type selon `nodes_common.TIER_WEIGHTS` (p. ex. T3 : souche 30 %, rocher 24 %, fer 40 %, cache 6 %), minimum 5 par type quand la région compte ≥ 25 candidats. Les régions de moins de 0,75 km² ne sont gardées que si elles sont nécessaires pour atteindre 3 zones par (continent, faction, palier) (2 régions ajoutées).
6. **Tirage** déterministe (crc32 du guid de la créature et du type), espacements : **12 m** entre deux nœuds quelconques (nœuds 005 compris), **40 m** entre nœuds du même type (bois, pierre, lin), **60 m** (minerais, cristal, obsidienne), **150 m** (caches de passage) ; plafonds par bloc de 1 km² et par grille serveur ; un nœud par position de créature.

## 4. Contrôles (`check_nodes_result.txt`, base `wl_scratch2`, comparaison à `classicmangos`) : 0 erreur de forme, 5 constats de couverture

Vérifié avec preuve (tous `[OK]` dans le fichier) : guid dans 9510001–9599999 et uniques ; chaque `id` existe dans `gameobject_template` ; plafond 4 664 ≤ 6 000 ; 008 appliquée deux fois de suite, même résultat (4 664 lignes) ; lignes `gameobject` hors production identiques à `classicmangos` (compte + somme crc32 : 47 488) ; aucun nœud à moins de 100 m d'un point 010 (le plus proche : 103,7 m) ni à moins de 50 m d'une créature à drapeaux PNJ (contrôle recalculé depuis la base) ; **chaque nœud est exactement à la position, z et orientation d'une créature** de `creature` (4 664 / 4 664) ; créature source non élite, ni critter ni totem, sans drapeaux PNJ ; aucun doublon de position ; espacement minimal 12,0 m (tous nœuds), plus petits espacements par type ≥ seuils ; z à −0,93/+1,47 m du terrain statique (moyenne 0,08) ; aucun nœud en eau (6 m), en aire intérieure (nom) ni de ville ; palier du nœud à ±1 du palier de zone et à ±1 du niveau local mesuré par un estimateur indépendant (4 543 exacts sur 4 664, 121 à ±1).

### Couverture par type de nœud × continent × faction (zones comptant ≥ 4 nœuds du type, cible ≥ 3)

87 combinaisons sur 92 atteignent 3 zones ou plus. **Les 5 constats concernent un seul cas : Horde, Royaumes de l'Est, palier 1 (arbre de la prairie, rocher de la prairie, ossements de cerf ; donc les ressources Bois et Andouiller) : 2 zones seulement (Tirisfal Glades, Silverpine Forest).** Cause : avec `rules.ZONE_FACTION` (Dun Morogh, Elwynn, Loch Modan, Westfall = Alliance), aucune zone « contestée » des Royaumes de l'Est n'a de créatures de palier 1 en quantité (Hillsbrad : < 5 candidats de palier 1, Alterac : idem). Le générateur affiche « COUVERTURE IMPOSSIBLE » pour ce cas. **Non corrigé par choix** : il faudrait soit autoriser le palier 1 en dehors de ses zones (pas de données pour le justifier), soit reclasser une zone, soit assouplir la règle (la Horde dispose aussi du Bois par butin et vendeurs, voir `RESOURCES.md`). Décision laissée à Robin. Autres minimums à 3 (limite, pas de marge) : palier 5 sur les Royaumes de l'Est (Burning Steppes, Eastern Plaguelands, Western Plaguelands) pour les deux factions.

Par ressource (chance ≥ 20 % sur un nœud, les 20 ressources de nœud), tous les autres couples (continent, faction) ont ≥ 3 zones (pierre 13–18, résine 12–17, bois de cœur 12–16, etc.).

## 5. Ce qui n'est pas vérifié, limites

- **Rien n'a été vu en jeu** : ni l'accessibilité des positions (une créature peut se tenir sur une corniche, derrière un décor), ni le rendu des modèles (voir `RESOURCES.md` §6), ni la taille des arbres, ni la hauteur réelle : le z est celui de la créature ; je l'ai comparé au **terrain statique seulement** (les modèles — bâtiments, ponts, arbres de décor — ne sont pas pris en compte, pas de mmaps/vmaps utilisées). Le contrôle d'eau ne voit que les liquides du terrain, pas l'eau des modèles.
- Les nœuds sont **là où il y a des créatures** (camps de monstres) : aucun nœud dans les grandes zones vides, peu de nœuds loin des mobs ; les filons et cristaux sont posés en terrain ouvert, jamais dans les mines ni les grottes (exclues comme en 005) : c'est cohérent avec « créatures non élites » mais pas avec le décor attendu d'un filon. Les patrouilles de routes sont écartées, pas toutes les routes.
- `check_nodes.py` réutilise `nodes_terrain.py` et `nodes_common.py` (terrain, eau, paramètres) : ces contrôles ne sont pas indépendants du générateur. Indépendants : provenance des positions, exclusions PNJ/010, espacements, estimateur de niveau local (disque 300 m, lecture directe de la base), couverture.
- Faction des zones : classification manuelle de `rules.py`, non vérifiée par les données. « Zone comptée » = ≥ 4 nœuds du type : seuil de mon choix.
- Équilibrage non évalué : densité (30/km² de surface couverte), répartition par type (fer 40 % au palier 3, etc.), 8 % de caches, temps de réapparition ; aucune mesure de farm, ni de coût serveur avec des joueurs.
- `ZONE_FACTION` classe Wetlands, Duskwood, Redridge comme Alliance : le palier 2 Horde des Royaumes de l'Est repose sur Hillsbrad, la poche de Silverpine et celle d'Alterac (3 zones, dont deux poches).

## 6. Piège de guid à connaître avant d'appliquer (constat fait pendant ce travail)

`classicmangos.gameobject` contient déjà **11 pièces de construction** de guid 9500119–9500129 (id 9100001–9100011, posées par le serveur : il attribue `max(guid) + 1`). Elles sont **dans la plage de 005**, dont le `DELETE ... BETWEEN 9500001 AND 9500999` les effacerait si 005 était rejouée (005 non modifiée, hors périmètre). Après 008 et un redémarrage, les nouvelles pièces recevront des guid ≥ 9514665, donc **dans la plage de production** : c'est pourquoi le `DELETE` de 008 est limité aux guid de la plage **et** aux entrées 9101001–9101999. Appliquer 008 **serveur arrêté** (le compteur de guid du serveur est lu au démarrage). Les contrôles ignorent les pièces (id 9100001–9100999) dans la comparaison de base.

## 7. Régénérer / revalider

```
cd tools/resources
python gen_nodes_production.py          # écrit server/sql/world/008_node_spawns_production.sql et gen_nodes_production_result.txt
python validate_nodes_scratch.py        # wl_scratch2 : copie, 003 + 005 + 010 + 008 (x2), check_nodes.py -> check_nodes_result.txt, suppression
```
Code retour de `check_nodes.py` : 0 tout OK, 1 erreur de forme, 3 formes OK mais constats de couverture (état actuel : 3).
