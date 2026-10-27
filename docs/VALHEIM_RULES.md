# Règles Valheim extraites par REA (phase 3, parties 1 et 2)

Source : `assembly_valheim.dll` (SHA-256 `94998885b103d6e5f5480123eaee0a093e82af2ddeeee37536c15bf555f24f3a`) et `assembly_utils.dll` (pour `Cover`), via REA 6.8.0 `inspect-managed-members` (CIL statique, rien n'est exécuté).
Preuves : désassemblages dans `analysis/valheim/dis/*.txt` (générés par `analysis/rea.cjs` à partir de REA ; les fichiers `*._all.txt` contiennent tous les corps d'un type). Chaque règle cite méthode + offsets IL. Ces fichiers dérivent du jeu : ne pas distribuer.

Légende : **[PROUVÉ]** lu directement dans le CIL · **[INFÉRÉ]** déduit du CIL, un maillon non lu · **[NON EXTRAIT]** pas encore analysé.

Outils (dossier `analysis/`) :
- `rea.cjs` : `dis <Type> <Méthode|*>` (résout les jetons 0x06…/0x04… de n'importe quel type en l'extrayant à la demande grâce aux plages de lignes de `members_ALL.json`, résout les `ldstr`, les `MethodSpec` génériques par nom et décode les tables de `switch`), `fields <Type>` (champs + valeur des constantes), `strings`, `callers`.
- `consts.cjs` : lit la table `Constant` du DLL (valeurs d'enum et de champs `const`, absentes de la sortie REA) → `valheim/constants.json`.
- `sweep.cjs` : balaie les 966 noms de types du DLL (0 erreur) et enregistre dans `valheim/callers_sweep.json` tous les appels directs vers `WearNTear`, `WearNTearUpdater` et `Piece` : c'est ce qui prouve la liste exhaustive des appelants. Limite : les appels par interface/événement/`SendMessage` ou par le moteur Unity (`Awake`, `Update`…) n'apparaissent pas comme appels directs.
- Les valeurs de `switch` et de constantes n'étant pas dans la sortie REA, elles sont relues dans les octets du DLL (`rea.cjs`, `consts.cjs`) : c'est ce qui a permis de découvrir l'erreur du §1.1.

## 1. Intégrité structurelle (`WearNTear`)

### 1.1 Constantes par matériau — `WearNTear::GetMaterialProperties` (IL 0–353) [PROUVÉ]
Signature : `(out maxSupport, out minSupport, out horizontalLoss, out verticalLoss)`. Ordre prouvé par `GetMaxSupport` (renvoie la local 0), `GetMinSupport` (local 1), et par l'usage dans `UpdateSupport` (§1.2) : le 3ᵉ paramètre sert à l'horizontale, le 4ᵉ à la verticale.
Enum `WearNTear+MaterialType` lue dans la table `Constant` : Wood=0, Stone=1, Iron=2, HardWood=3, Marble=4, Ashstone=5, Ancient=6, Ice=7, Timberwood=8 (`dis/_enums.txt`) [PROUVÉ].
Table de `switch` (IL 8) décodée : `0→IL54, 1→IL114, 2→IL144, 3→IL84, 4→IL174, 5→IL204, 6→IL234, 7→IL264, 8→IL294`. **Les blocs ne sont donc pas dans l'ordre de l'enum** (voir §6).

| Index | Matériau | Bloc IL | maxSupport | minSupport | perte horizontale | perte verticale |
|---|---|---|---|---|---|---|
| 0 | Wood | 54 | 100 | 10 | 0,2 | 0,125 |
| 1 | Stone | 114 | 1000 | 100 | 1 | 0,125 |
| 2 | Iron | 144 | 1500 | 20 | 0,0769 | 0,0769 |
| 3 | HardWood | 84 | 140 | 10 | 0,1667 | 0,1 |
| 4 | Marble | 174 | 1500 | 100 | 0,5 | 0,125 |
| 5 | Ashstone | 204 | 2000 | 100 | 0,3333 | 0,1 |
| 6 | Ancient | 234 | 5000 | 100 | 0,25 | 0,0667 |
| 7 | Ice | 264 | 1000 | 100 | 0,3333 | 0,125 |
| 8 | Timberwood | 294 | 200 | 10 | 0,2 | 0,0769 |

Valeur hors 0–8 : tout à 0 (IL 324–353). Les valeurs par pièce (`m_materialType`, `m_supports`, `m_health`…) sont des données de prefab Unity [NON EXTRAIT]. Valeurs par défaut du constructeur (`WearNTear..ctor`) : `m_health=100`, `m_supports=true`, `m_noSupportWear=true`, `m_noRoofWear=true`, `m_support=1`, `m_haveRoof=true`, `m_staticPosition=true`.

### 1.2 Calcul du support — `WearNTear::UpdateSupport` (IL 0–1452) [PROUVÉ]
Notation : `COM` = `GetCOM()` (= position + rotation·`m_comOffset`, IL 0–38), `max/min` du §1.1, `lossH`/`lossV`.
Boîtes de test : `SetupColliders` (IL 0–435) prend chaque collider non-trigger sans rigidbody ; pour un `BoxCollider` : centre monde, taille = `lossyScale × size`, **+0,3 sur chaque axe puis ×0,5** (demi-extensions, donc la boîte est élargie de 0,15 m de chaque côté) (IL 319–405) ; pour les autres colliders : `bounds` (IL 263–314), même élargissement. Masque `s_rayMask` = `LayerMask.GetMask("piece","Default","static_solid","Default_small","terrain")` (`WearNTear::Awake` IL 290–348).
1. **Cache** (IL 0–227) : si la liste de colliders en cache est non vide, on parcourt les colliders ; la boucle s'arrête (donc cache invalidé) au premier collider détruit/null (IL 52–60), sans `WearNTear` parent (IL 65–82), dont `m_supports` est faux (IL 84–91), ou dont la position a changé (IL 103–133). On compte les voisins dont `GetSupport()` est identique à la valeur mise en cache (IL 135–180) et on retient le plus grand support voisin. **Sortie immédiate seulement si** `nb_identiques == nb_positions_en_cache` **et** `plus_grand_support_voisin > m_support` (IL 196–221) ; sinon `ClearCachedSupport()` puis recalcul complet (IL 222).
2. `OverlapBoxNonAlloc` avec `s_rayMask` pour chaque boîte (IL 307–352). On ignore : colliders avec rigidbody, triggers, ses propres colliders (`m_colliders.Contains`) (IL 562–605).
3. **Notification des voisins** (IL 359–539) : si `m_clearCachedSupport` est vrai (posé par `OnPlaced`, §3.3), chaque `WearNTear` chevauchant reçoit `ClearCachedSupport()` direct s'il est possédé localement (IL 453–467), sinon un RPC `"RPC_ClearCachedSupport"` à son propriétaire ZDO (IL 469–517) ; puis `m_clearCachedSupport = false` (IL 537–539). **C'est ainsi qu'une pièce nouvellement posée force ses voisines à recalculer.**
4. **Ancrage au terrain** : collider sur la couche `s_terrainLayer` (= `LayerMask.NameToLayer("terrain")`, `Awake` IL 3–43) → `grounded = true` (IL 617–651).
5. **Collider sans composant `WearNTear`** (rocher, objet statique…) : `m_support = max`, cache vidé, valeur publiée dans le ZDO si elle a changé, arrêt (IL 656–732). Toucher un solide non-pièce donne le support complet.
6. **Voisin `WearNTear` avec `m_supports == true`** (IL 737–1069), `s = voisin.GetSupport()` :
   - `d = min(dist(COM, voisin.COM), dist(COM, voisin.position)) + 0,1` ; le min n'est pas pris si `m_forceCorrectCOMCalculation` (IL 749–816).
   - candidat horizontal : `best = max(best, s − lossH·d·s)` (IL 816–842).
   - `p = FindSupportPoint(COM, voisin, collider)`. Si `p.y < COM.y + 0,05` et `dir = normalisé(p − COM)` avec `dir.y < 0` : `t = acos(1 − |dir.y|)/(π/2)`, `loss = lerp(lossH, lossV, t)`, `best = max(best, s − loss·d·s)` (IL 877–981). `dir.y = −1` → `lossV` ; `dir.y → 0` → `lossH`.
   - le point est mémorisé avec la valeur `s − lossV·d·s` (IL 983–1069) pour l'étape 8, et ajouté au cache (collider, position du collider, support voisin).
7. **Si `grounded`** : `m_support = max` (publié dans le ZDO si changé), fin (IL 1117–1172).
8. **Support à deux appuis** (IL 1173–1366) : pour chaque paire (i<j) de points mémorisés, `avg = (v_i + v_j)/2` ; si `avg > best` et si l'angle (plan horizontal, y mis à 0) entre `p_i − COM` et `p_j − COM` est **≥ 100°** (IL 1326–1336 : `blt.un` saute si < 100) alors `best = avg`.
9. `m_support = min(best, max)`, publié dans le ZDO si changé (IL 1371–1433). Si `!HaveSupport()` le cache est vidé (IL 1438–1447).

`HaveSupport` = `m_support ≥ GetMinSupport()` (IL 0–17). `GetSupport` : sans `m_nview` valide ou sans propriétaire → `GetMaxSupport` ; propriétaire local → `m_support` ; sinon valeur ZDO `s_support` (défaut `GetMaxSupport`) (IL 0–87). `m_support` initial = `GetMaxSupport()` (`Awake` IL 395–400). `FindSupportPoint` (IL 0–88) : `MeshCollider` non convexe → raycast vers le bas depuis le COM (10 m) → point d'impact, sinon milieu `(COM + voisin.COM)/2` ; collider normal → `ClosestPoint(COM)`.
**`UpdateSupport` n'a qu'un seul appelant : `UpdateWear` IL 310** (balayage exhaustif, §1.4) ; les pièces dont `m_noSupportWear` est faux ne recalculent donc jamais leur support.

### 1.3 Usure et effondrement — `WearNTear::UpdateWear(time)` (IL 0–1484) [PROUVÉ]
Conditions d'exécution (IL 0–111) : ZDO valide ; **propriétaire local** (`IsOwner`) ; `ShouldUpdate(time)` ; sinon tout est sauté (saut IL 1419). Si la pièce est **hors zone active** (`ZNetScene.OutsideActiveArea(position)`, comparaison par zone avec la position de référence du `ZNet`), le support est remis à `GetMaxSupport()` (ZDO) et la fonction se termine (IL 42–111). Rayon de la zone active : [NON EXTRAIT].
- `ShouldUpdate(time)` (IL 0–36) : renvoie vrai si `m_createTime < 0` ; sinon vrai si `time − m_createTime > 30`, sinon `m_addPreSnow`. `m_createTime = Time.time` à l'`Awake` (IL 382–388) mais `OnPlaced` le met à **−1** (§3.3) : **une pièce posée par un joueur s'use dès son premier passage ; la grâce de 30 s ne concerne que les pièces dont `OnPlaced` n'est pas appelé** (chargées avec le monde, générées).
- Accumulateur local `dmg%` (en % de `m_health`), alimenté par : pluie (§2.1, +5), support (ci-dessous, =100), événement persistant (`m_eventDamage ± m_eventDamageDeviation`, IL 329–486), biome 64 (`DeepNorth`) neige lourde (IL 502–954), biome 32 (`AshLands`) cendres/lave (IL 955–1289), hors biome requis (`+m_outsideRequiredBiomeDamage`, IL 1289–1335). Biomes : `Heightmap+Biome` lue dans la table `Constant` (`AshLands=32`, `DeepNorth=64`). Détails neige/cendres/lave/événement : [NON EXTRAIT].
- Si `m_noSupportWear` : `UpdateSupport()` puis, si `!HaveSupport()`, `dmg% = 100` (assignation, pas addition) (IL 301–328). La pièce est détruite au prochain `UpdateWear` éligible.
- Si `dmg% > 0` et `!CanBeRemoved()` (délégué à `Piece::CanBeRemoved`) : `dmg% = 0` (IL 1349–1371).
- Si `dmg% > 0` : `dégâts = dmg%/100 · m_health` ; **si la clé globale 37 (`GlobalKeys.NoBuildingFall`) est active, rien n'est appliqué** (IL 1393–1407, ce qui coupe aussi pluie/cendres/neige) ; sinon `ApplyDamage(dégâts, null)` (IL 1409–1413).
- `ApplyDamage(dmg, hit)` (IL 0–186) : `h = ZDO.health` ; si `h ≤ 0` rien ; `h −= dmg` ; écrit le ZDO ; si `h ≤ 0` → `Destroy(hit, false)`, sinon RPC `RPC_HealthChanged(h)` à tous.
- `RPC_HealthChanged(h)` (IL 0–42) : `m_healthPercentage = clamp01(h/m_health)`, **`ClearCachedSupport()`**, mise à jour visuelle.

### 1.4 Cadence des mises à jour — `WearNTearUpdater` [PROUVÉ]
Seul appelant de `UpdateWear` : `WearNTearUpdater::UpdateWearNTear` IL 212 ; appelants de `UpdateCover` : IL 84 du même, plus une lambda de commande de console de test (`<>c.<InitTerminal>b__7_115` IL 49, hors jeu normal) (balayage exhaustif des 966 types, `callers_sweep.json`). Seuls appelants externes de `WearNTear.Remove` : `Player.RemovePiece` IL 334 et `ItemDrop.Eat` IL 178 (consommation d'une pièce « festin ») ; de `WearNTear.Repair` : `Player.Repair` IL 81 ; de `WearNTear.OnPlaced` : `Player.PlacePiece` IL 135. `WearNTear::Awake/Start` ne contiennent aucun `InvokeRepeating` ni coroutine (`Start` abonne seulement `ClearCachedSupport` à l'événement `Heightmap.m_clearConnectedWearNTearCache`, IL 22–54 ; `OnDestroy` le désabonne). `Awake` s'enregistre dans `s_allInstances` (IL 353–377).
Constantes : `c_UpdatesPerFrame = 50`, `c_WearNTearTime = 1` (champs const lus dans la table `Constant`) ; `m_updatesPerFrame` initial = 50 (`.ctor` IL 1–3).
- `Start` : `m_sleepUntil = m_sleepUntilNext = time + 1` (IL 0–26).
- `Update()` chaque frame : si `time < m_sleepUntil` sortie ; sinon `UpdateWearNTear(deltaTime, time)` (IL 0–30).
- `UpdateWearNTear(dt, time)` :
  - **Début de cycle** si `m_sleepUntilNext == m_sleepUntil` (IL 6–23) : `m_sleepUntilNext = time + 1`, `UpdateCover(dt)` sur toutes les instances actives (`Behaviour.enabled`), `UpdateAshlandsMaterialValues(time)` sur toutes, puis retour (IL 28–161). Ce passage n'appelle pas `UpdateWear`.
  - **Frames suivantes** (IL 162–237) : à partir de `m_index`, au plus `m_updatesPerFrame` instances reçoivent `UpdateWear(time)` (si `enabled`) ; `m_index` avance, remis à 0 quand la liste est épuisée (IL 237–251).
  - Quand une passe complète se termine (`m_index == 0`, IL 256–262), `diff = m_sleepUntilNext − time` (IL 267–275). Si `|diff| < 0,1` rien. Sinon `m_updatesPerFrame` : `diff < −0,8` : +20 ; `< −0,4` : +15 ; `< −0,2` : +10 ; `< 0` : +5 ; `> 0,8` : −20 ; `> 0,6` : −15 ; `> 0,3` : −10 ; `> 0,2` : −5 (IL 277–499). Puis `m_sleepUntil = m_sleepUntilNext` (IL 504–511) et `m_updatesPerFrame` borné à **[5, 100]** (IL 516–548).
- **Conséquence** : chaque pièce reçoit `UpdateWear` **une fois par passe**, et le contrôleur cale la durée d'un cycle (début de cycle → début du suivant) sur **1 s** ; si la passe se termine avant, on dort jusqu'à l'échéance, si elle est plus lente (plafond 100 pièces par frame) le cycle s'allonge. Donc **cadence nominale : 1 `UpdateWear` par pièce par seconde** (pluie : horloge `time`, §2.1 ; support : recalcul au plus 1 fois par seconde et par pièce) [PROUVÉ pour le code ; la valeur « 1 s » est la cible du contrôleur, la cadence effective dépend de la charge].
- **`UpdateCover` reçoit le `deltaTime` d'une seule frame par cycle** (`dt` passé à l'IL 83 est `Time.deltaTime`, pas le temps écoulé depuis le dernier appel). Son accumulateur `m_updateCoverTimer` (init `Random(0,4)`, `Awake` IL 553–568) doit dépasser 4 (§2.2) : il faut donc ≈ `4/dt` cycles, soit environ 240 s à 60 FPS ou 120 s à 30 FPS [INFÉRÉ : arithmétique à partir du CIL, dépend du `dt` moyen ; sur un serveur WoW on choisira un pas explicite]. Le « 4 s » du §2.2 est un seuil d'accumulateur, pas une période murale.

### 1.5 Destruction, démontage et cascade — `Destroy`, `Remove`, `RPC_Remove`, `OnDestroy`, `ClearCachedSupport` [PROUVÉ]
- `Remove(blockDrop)` (IL 0–45) : si ZDO valide, `InvokeRPC("RPC_Remove", blockDrop)` (surcharge sans cible : propriétaire du ZDO [INFÉRÉ sur la sémantique de la surcharge]). `RPC_Remove(sender, blockDrop)` (IL 0–35) : seulement si propriétaire local → `Destroy(null, blockDrop)`.
- `Destroy(hit, blockDrop)` (IL 0–385), dans l'ordre :
  1. Si le `GetComponent<T>` générique (type non nommé par REA, [INFÉRÉ] `Bed` puisque `Bed.GetSpawnPoint` est appelé sur le résultat) renvoie un composant et que l'on est propriétaire local : `Game.RemoveCustomSpawnPoint(bed.GetSpawnPoint())` (IL 0–53).
  2. ZDO `s_health = 0` et `s_support = 0` (IL 58–109), champs locaux `m_support = m_health = 0` (IL 110–127).
  3. **`ClearCachedSupport()` sur soi uniquement** (IL 132–133).
  4. Si `m_piece` valide **et `!blockDrop`** : `Piece.DropResources(hit)` (IL 138–161) → remboursement, §4.2.
  5. `m_onDestroyed` (IL 166–180).
  6. Si `m_destroyNoise > 0` et (`hit == null` ou `hit.m_hitType != 20`, soit `HitType.CinderFire`) : `Player.GetClosestPlayer(position, 10).AddNoise(m_destroyNoise)` (IL 185–248).
  7. Effet `m_destroyedEffect` à la position/rotation de la pièce (IL 253–334).
  8. Si `m_autoCreateFragments` : `InvokeRPC(Everybody, "RPC_CreateFragments")` (IL 335–364). `RPC_CreateFragments` (IL 0–73) active les `m_fragmentRoots` (ou la pièce entière) et appelle `Destructible.CreateFragments(obj, false)`. `CreateFragments` ne crée que des objets visuels côté client (nouveau GameObject sur la couche `effect`, maillage + rigidbody, échelle ×0,9, `TimedDestruction` 2 à 4 s) : **les fragments n'ont aucun effet de jeu** (`Destructible.CreateFragments`, IL 0–390).
  9. `ZNetScene.Destroy(gameObject)` (IL 369–380).
- **Cascade** : `Destroy` ne prévient pas directement les voisines. Les voisines détectent la perte parce que leur cache `m_supportColliders` contient le collider détruit, qui est testé `== null` (`UnityEngine.Object::op_Equality`, `UpdateSupport` IL 52–60) ; elles invalident alors leur cache et recalculent au prochain `UpdateWear` éligible (≈ 1 par seconde, §1.4), et ne s'effondrent que si `m_support < min` ([INFÉRÉ] pour la sémantique Unity « objet détruit == null », non lue dans le CIL). Chaque pièce qui s'effondre déclenche la même chose chez ses propres voisines : l'effondrement progresse par vagues, au plus à la cadence d'une passe de `WearNTearUpdater` par maillon (plusieurs maillons par passe si l'ordre de `s_allInstances` s'y prête).
- Autres déclencheurs d'invalidation de cache (balayage exhaustif des appelants de `ClearCachedSupport`) : `RPC_HealthChanged` IL 29 (tout changement de santé reçu), `RPC_ClearCachedSupport` (§1.2 étape 3), l'événement `Heightmap.m_clearConnectedWearNTearCache` invoqué par `Heightmap.Regenerate` IL 74–85 (le terrain a changé), et les cas internes à `UpdateSupport` (IL 223, 698, 1447).
- `WearNTear::OnDestroy` (IL 0–133) : retire l'instance de `s_allInstances` (échange avec le dernier, `m_myIndex`) et se désabonne de l'événement `Heightmap`.

### 1.6 Réparation — `WearNTear::Repair` / `RPC_Repair` [PROUVÉ]
- `WearNTear.Repair()` (IL 0–106) : faux si ZDO invalide ; faux si `ZDO.health ≥ m_health` (pièce intacte, IL 21–51) ; faux si `Time.time − m_lastRepair < 1` (IL 52–72) ; sinon `m_lastRepair = Time.time` et `InvokeRPC("RPC_Repair")`, renvoie vrai.
- `RPC_Repair` (IL 0–95) : propriétaire local uniquement ; `ZDO.health = m_health` (**réparation complète d'un coup**, IL 27–49) puis `RPC_HealthChanged(m_health)` à tous (IL 54–90).
- Côté joueur, `Player.Repair(item, piece)` (IL 0–320) : exige `InPlaceMode` ; cible = `GetHoveringPiece()` ; `CheckCanRemovePiece(piece)` (établi requis à portée, §4.1) ; `PrivateArea.CheckAccess(pos, 0, flash=true, ward=false)` ; `WearNTear.Repair()`. En cas de succès : effet `m_placeEffect`, message `$msg_repaired`, `UseStamina(GetBuildStamina())`, `UseEitr(attackEitr)`, et si l'outil `m_useDurability` : durabilité −= `m_useDurabilityDrain × Game.m_durabilityRate` (IL 216–288). Sinon message « `<nom> $msg_doesnotneedrepair` ». **Aucune ressource n'est consommée par la réparation.** `UpdatePlacement` n'appelle `Player.Repair` que si la pièce sélectionnée a `m_repairPiece` (IL 1025–1036).

## 2. Pluie et abri

### 2.1 Pluie — `WearNTear::UpdateWear` (IL 112–301) [PROUVÉ]
- `m_rainWet = !protégéBouclier && !m_haveRoof && m_noRoofWear ? EnvMan.IsWet() : false` (IL 141–169). L'appel (jeton 0x060015b8 dans le doc précédent) est **`EnvMan::IsWet()`** [PROUVÉ, résolu par `rea.cjs`]. `ShieldGenerator.IsInsideShieldCached` fournit `protégéBouclier` (IL 112–134).
- `EnvMan.IsWet()` renvoie le booléen statique `s_isWet` (IL 0–5), recalculé par `EnvMan.CalculateWet` = `EnvSetup.m_isWet` de l'environnement courant (IL 0–18).
- Pour une pièce `m_noRoofWear`, non protégée, avec `GetHealthPercentage() > 0,5` et `IsWet()` (pièce : `m_rainWet` ou sous l'eau, IL 0–16) :
  - `m_rainTimer == 0` → `m_rainTimer = time`.
  - sinon, si `time − m_rainTimer > 60` → `m_rainTimer = time` et `dmg% += 5` (IL 212–288).
  - si pas mouillée : `m_rainTimer = 0` (IL 290–296).
  Donc −5 % de `m_health` par tranche de 60 s de pluie, **tant que `m_healthPercentage > 0,5` avant le coup** : la pluie ne s'applique plus une fois la santé ≤ 50 %, mais un coup donné à 50,1 % amène à 45,1 % (la version précédente écrivait « jamais en dessous de 50 % », inexact). `m_healthPercentage` n'est mis à jour que par `RPC_HealthChanged` et `Awake`. Rien n'est appliqué si la clé globale `NoBuildingFall` est active (§1.3).

### 2.2 Toit d'une pièce — `UpdateCover` / `HaveRoof` / `RoofCheck` [PROUVÉ]
- `UpdateCover(dt)` (IL 0–88) : `m_updateCoverTimer += dt` ; si `> 4` : si `EnvMan.IsWet()` (IL 28) **ou** `m_biome == 64` (DeepNorth) alors `m_haveRoof = HaveRoof()` ; si `m_inAshlands` : `m_haveAshRoof = HaveAshRoof()` ; timer remis à 0. Le toit n'est évalué que quand il pleut (ou en DeepNorth) ; `m_haveRoof` vaut **vrai par défaut** (`.ctor` IL 221–223) donc une pièce est considérée couverte tant que le premier calcul n'a pas eu lieu. Cadence réelle : voir §1.4 (le `dt` est celui d'une frame par cycle).
- `HaveRoof()` (IL 0–49) : `m_roof` déjà trouvé et encore vivant → vrai ; sinon `RoofCheck(position, out m_roof, m_roofCheckOffset)`. Un toit trouvé est donc mémorisé tant que son objet existe.
- `RoofCheck(p, out toit, offset)` (IL 0–141) : `SphereCastNonAlloc` rayon **0,1**, direction haut, portée **100 m**, masque `s_rayMask`, depuis `p + (0, offset, 0)`. Le premier hit qui n'est pas un descendant de la pièce (`Utils.IsAncestor`) et dont le tag n'est pas **`"leaky"`** est un toit. Masque `s_rayMask` : couches `piece`, `Default`, `static_solid`, `Default_small`, `terrain` (`Awake` IL 290–348). Tag littéral résolu : `"leaky"` (IL 101).

### 2.3 Abri du joueur — `Player::UpdateCover`, `Player::InShelter`, `Cover` (`assembly_utils.dll`) [PROUVÉ]
- `Player.UpdateCover(dt)` est appelé depuis `Player.FixedUpdate` (IL 149) ; accumulateur > 1 s → `Cover.GetCoverForPoint(Character.GetCenterPoint(), out coverPercentage, out underRoof, 0,5)` (IL 0–66).
- `Player.InShelter()` = `m_coverPercentage ≥ 0,8` **et** `m_underRoof` (IL 0–21).
- `Cover.IsUnderRoof(p)` : sphere cast haut, rayon 0,1, portée 100 m, masque `m_coverRayMask` ; vrai si un hit n'a pas le tag **`"leaky"`** (IL 0–88).
- `Cover.GetCoverForPoint(p, out pct, out underRoof, radius)` : `underRoof = IsUnderRoof(p)` ; lance **17 rayons** (haut ; 4 axes horizontaux + 4 diagonales ; 8 inclinés vers le haut ; table `CreateCoverRays`, IL 0–514), longueur `30 − radius`, depuis `p + rayon·radius` ; `pct = nb_rayons_touchés / 17` (IL 0–102).
- `Cover.Setup` (IL 0–76) : masque `m_coverRayMask` = `LayerMask.GetMask("Default","static_solid","Default_small","piece","terrain","vehicle")` (6 couches, littéraux désormais résolus dans `dis/Cover.Setup.txt`).

### 2.4 Établi — `CraftingStation::CheckUsable` [PROUVÉ]
- Si `m_craftRequireRoof` et que le joueur n'a pas **`Player.NoCostCheat()`** (le jeton 0x06000336 du doc précédent, décrit à tort comme « noclip/créatif ») : `Cover.GetCoverForPoint(m_roofCheckPoint.position, …, 0,5)`. Si `!underRoof` → `$msg_stationneedroof`, refus ; si `coverPercentage < 0,7` → `$msg_stationtooexposed`, refus (IL 0–91).
- Si `m_craftRequireFire`, pas de `NoCostCheat` et pas de feu (`m_haveFire`) → `$msg_needfire`, refus (IL 92–135).
- **Un établi exige un toit au-dessus ET ≥ 70 % de couverture sur ses 17 rayons**, pas seulement un toit.

## 3. Placement (`Player`, `Piece`) [PROUVÉ sauf mention]

### 3.1 Boucle de pose — `Player::UpdatePlacement(bool, dt)` (IL 0–2067)
Appelée depuis `Player.Update` (IL 1368). Conditions : `InPlaceMode`, pas mort, pas de menu de sélection (IL 7–45). Pose (bouton `Attack`/`JoyPlace`, mémorisé dans `m_placePressedTime`, fenêtre 0,2 s ; IL 841–900) :
- délai : `Time.time − m_lastToolUseTime > m_placeDelay` ; `m_placeDelay = 0,4` s par défaut du constructeur de `Player` (IL 118–124) [INFÉRÉ pour la valeur effective : le prefab Unity peut la surcharger] ;
- `HaveStamina(item.m_attack.m_attackStamina)` sinon `Hud.StaminaBarEmptyFlash()` (IL 996–1018, 1437) ;
- pièce sélectionnée `m_repairPiece` → `Player.Repair` (§1.6) ; `m_removePiece` (et `canRemove`) → `RemovePiece` (§4.1) ; sinon, si un fantôme existe (IL 1070–1082) :
  1. si `!m_noPlacementCost` : `HaveRequirements(piece, CanBuild)` sinon message `$msg_missingrequirement` (IL 1087–1104, 1420–1430) ;
  2. `TryPlacePiece(piece)` (§3.3) ; en cas de succès :
  3. **consommation des ressources** si la clé globale `Piece.FreeBuildKey(piece)` n'est pas active : `ConsumeResources(piece.m_resources, 0, −1, 1)` (IL 1154–1184, §3.4) ;
  4. `UseStamina(GetBuildStamina())` (IL 1189–1196) ; compétence : si `m_buildRemoveDebt > 0` alors `dette −= 1`, sinon `RaiseSkill(m_buildPieces.m_skill, 1)` (IL 1250–1292) ; durabilité de l'outil −= `GetPlaceDurability × Game.m_durabilityRate` si `m_useDurability` (IL 1333–1367) ; effet `m_buildEffect`.
- Rotation : molette / touches par pas de `m_placeRotationDegrees = 22,5°` (`Player..ctor` IL 708–714), donc 16 orientations ; seuil molette 0,1 (IL 1563–1668).
- `GetBuildStamina()` (IL 0–96) = `s·(1 − 0,5·skillFactor)` avec `s = attackStamina·(1 + GetEquipmentHomeItemModifier())` modifié par `SEMan.ModifyHomeItemStaminaUsage` : la compétence de construction réduit jusqu'à 50 % le coût en endurance.

### 3.2 Fantôme et règles de placement — `Player::PieceRayTest`, `UpdatePlacementGhost(flashGuard)`, `GetPlacementStatus`
**Distance et cible** — `PieceRayTest` (IL 0–312) : raycast depuis la caméra, vers l'avant, **50 m**, masque `m_placeRayMask` (ou `m_placeWaterRayMask` si la pièce a `m_waterPiece` ou `m_noInWater`). Masques (`Player::Awake` IL 160–388) : `m_placeRayMask` = `Default, static_solid, Default_small, piece, piece_nonsolid, terrain, vehicle` ; `m_placeWaterRayMask` = idem + `Water` ; `m_removeRayMask` = comme `m_placeRayMask`. Le collider touché ne doit **pas** avoir de rigidbody (IL 123–145) et la distance **œil du joueur (`Character.m_eye`) → point d'impact** doit être **< `m_maxPlaceDistance` + `piece.m_extraPlacementDistance`** (entier) (IL 66–174). `m_maxPlaceDistance = 5` m au constructeur de `Player` (IL 31–36) [INFÉRÉ pour la valeur effective, surcharge de prefab possible]. Sans hit valide : fantôme masqué, statut `NoRayHits` (12) (IL 2820–2860).
**Statut** — enum `Player+PlacementStatus` (`dis/_enums.txt`, table `Constant`) : Valid 0, Invalid 1, BlockedbyPlayer 2, NoBuildZone 3, PrivateZone 4, MoreSpace 5, NoTeleportArea 6, ExtensionMissingStation 7, WrongBiome 8, NeedCultivated 9, NeedDirt 10, NotInDungeon 11, NoRayHits 12, DeepSnow 13, NoSnow 14. `GetPlacementStatus()` renvoie `m_placementStatus` (IL 0–6). `UpdatePlacementGhost` repart de `Valid` (IL 158–160) puis chaque test ci-dessous écrase le statut (**le dernier test échoué l'emporte**), et `SetPlacementGhostValid(status == 0)` conclut (IL 2865–2875).
Ordre des tests dans `UpdatePlacementGhost` (IL = offset du `stfld m_placementStatus`) :
1. Extension de station (`StationExtension` sur la pièce) : aucune station à portée → 7 (IL 415–417) ; `OtherExtensionInRange(m_spaceRequirement)` → 5 (IL 437–439).
2. `m_blockRadius > 0` et `m_blockingPieces` non vide : `OverlapSphere(pos, m_blockRadius, "piece")` ; une autre pièce de même `m_name` qu'une pièce de `m_blockingPieces` → 5 (IL 444–635).
3. `m_mustConnectTo` : `OverlapSphere(pos, m_connectRadius)` ; il faut une pièce d'un autre `ZNetView` dont le nom contient celui de `m_mustConnectTo` (et, si `m_mustBeAboveConnected`, qui est celle touchée par un raycast vers le bas) sinon → 1 (IL 635–827).
4. Surface touchée = `WearNTear` avec `m_supports == false` → 1 (IL 832–852).
5. `m_waterPiece` sans collider d'eau touché (et pas de pose alternative) → 1 ; `m_noInWater` avec eau touchée → 1 (IL 857–905).
6. `m_groundPiece` sans heightmap touchée : fantôme masqué, statut 1, **sortie immédiate** (IL 910–947) ; `m_groundOnly` sans heightmap → 1 (IL 948–968) ; `m_cultivatedGroundOnly` : pas de heightmap ou `!Heightmap.IsCultivated(point)` → 9 (IL 973–1004) ; `m_vegetationGroundOnly` : heightmap absente, ou biome `AshLands` avec `GetVegetationMask > 0,1`, ou autre biome avec masque `< 0,25` → 10 (IL 1009–1088).
7. `m_notOnWood` : surface = pièce `WearNTear` de matériau Wood (0) ou HardWood (3) → 1 (IL 1093–1140) ; `m_notOnTiltingSurface` : normale `y < 0,8` → 1 (IL 1145–1169) ; `m_inCeilingOnly` : normale `y > −0,5` → 1 (IL 1174–1198) ; `m_notOnFloor` : normale `y > 0,1` → 1 (IL 1203–1227). **Il n'y a pas d'autre test de pente** : seul `m_notOnTiltingSurface` (≈ 36,9°) en réalise un.
8. `m_onlyInTeleportArea` et point hors `EffectArea` de type 16 → 6 (IL 1232–1262).
9. `!m_allowedInDungeons` et joueur à l'intérieur (`Character.InInterior`) sans `EnvMan.CheckInteriorBuildingOverride` ni clé `DungeonBuild` (34) → 11 (IL 1267–1312).
10. `!m_allowedInDeepSnow`, biome courant `DeepNorth` (64), heightmap trouvée et `GetCultivationMask(pos) > m_deepSnowBuildHeight` (0,15 au constructeur de `Player`, IL 415–421) → 13 (IL 1317–1363) ; `m_requireDeepSnow` : hors DeepNorth, ou heightmap absente, ou masque ≤ 0 → 14 (IL 1368–1414).
11. Positionnement du fantôme (IL 1480–2041) : pose du fantôme au point d'impact ; pour les pièces `m_groundPiece`/`m_clipGround` (avec heightmap) ou `m_clipEverything`, le fantôme est posé directement sur le point d'impact (« pose alternative » : si `m_allowAltGroundPlacement` et selon `AltPlace`/`m_altPlace`, la hauteur du point devient `ZoneSystem.GetGroundHeight(position du joueur)` ; les deux composants testés au préalable (IL 1793–1835) sont des `GetComponent<T>` non nommés, conditions exactes [INFÉRÉ]) ; sinon il est déplacé de façon que le point de ses colliders (non-trigger, convexes) le plus proche de l'impact coïncide avec celui-ci. **Accrochage** (si pas de pose alternative) : `FindClosestSnapPoints(ghost, 0,5, …)` cherche, parmi les pièces dans 10 m, le couple (point d'accrochage du fantôme, point d'accrochage voisin) le plus proche, distance **≤ 0,5 m** ; points d'accrochage = enfants de la pièce avec le tag `"snappoint"` (`Piece.GetSnapPoints`, IL 0–55) ; le fantôme est translaté pour les superposer sauf si `IsOverlappingOtherPiece` (une pièce de même nom à moins de **0,05 m**, et — si `!m_allowRotatedOverlap` — quel que soit l'angle, sinon angle ≤ 10°) l'interdit (IL 2443–2611 ; `IsOverlappingOtherPiece` IL 0–125). Sélection manuelle du point d'accrochage par touches (`m_manualSnapPoint`).
12. `Location.IsInsideNoBuildLocation(pos du fantôme)` → 3 (IL 2632–2641).
13. `PrivateArea.CheckAccess(pos, rayon (m_radius si la pièce est un PrivateArea, sinon 0), flash = flashGuardStone, wardCheck = la pièce est un PrivateArea)` faux → 4 (IL 2646–2721). Logique interne de `CheckAccess` : [NON EXTRAIT].
14. `CheckPlacementGhostVSPlayers()` vrai → 2 (IL 2724–2735). Corps (IL 0–269) : `Character.GetCharactersInRange(position du joueur, 30, liste)` (**tous les `Character`**, pas seulement les joueurs) ; si un collider non-trigger actif du fantôme (les `MeshCollider` non convexes sont ignorés) a une pénétration (`Physics.ComputePenetration`) avec le collider d'un de ces personnages → vrai.
15. `m_onlyInBiome` : `Heightmap.FindBiome(pos) & m_onlyInBiome == 0` → 8 (IL 2739–2779).
16. `m_noClipping` et `TestGhostClipping(ghost, 0,2)` → 1 (IL 2784–2813). `TestGhostClipping` (IL 0–150) : `OverlapSphere(position du fantôme, rayon 10, m_placeRayMask)` ; pour chaque collider du fantôme × chaque collider trouvé, `ComputePenetration` avec profondeur de pénétration **> 0,2** → vrai.
**Il n'existe pas, dans `UpdatePlacementGhost`, de test de chevauchement général, d'eau profonde, de hauteur de construction ou de nombre maximal de pièces** : le chevauchement n'est refusé que par les points 2, 14, 16 (et par l'accrochage). Les valeurs `m_noClipping`, `m_groundOnly`… de chaque prefab sont des données Unity [NON EXTRAIT].

### 3.3 Validation et création — `TryPlacePiece`, `PlacePiece`, `Piece.OnPlaced`, `WearNTear.OnPlaced`
- `TryPlacePiece(piece)` (IL 0–489) : relance `UpdatePlacementGhost(true)`, lit `m_placementStatus` et, pour tout statut ≠ 0, affiche un message et renvoie faux. Table de `switch` (IL 17) décodée (index = statut − 1) : Invalid(1) et NoRayHits(12) → `$msg_invalidplacement` ; BlockedbyPlayer → `$msg_blocked` ; NoBuildZone → `$msg_nobuildzone` ; PrivateZone → `$msg_privatezone` ; MoreSpace → `$msg_needspace` ; NoTeleportArea → `$msg_noteleportarea` ; ExtensionMissingStation → `$msg_extensionmissingstation` ; WrongBiome → `$msg_wrongbiome` ; NeedCultivated → `$msg_needcultivated` ; NeedDirt → `$msg_needdirt` ; NotInDungeon → `$msg_notindungeon` ; DeepSnow → `$msg_snowtoodeep` ; NoSnow → `$msg_nosnow`. **`TryPlacePiece` ne vérifie ni ne consomme les ressources** (fait avant/après par `UpdatePlacement`, §3.1). En cas de succès : statistiques, puis `PlacePiece(piece, position du fantôme, rotation du fantôme, …)`.
- `PlacePiece(piece, pos, rot, doAttack, cheated)` (IL 0–661) : `Instantiate(prefab, pos, rot)` ; `Piece.SetCreator(playerID, platformUserID)` (IL 55–85) ; si PrivateArea : `Setup(nom du joueur)` ; **`WearNTear.OnPlaced()`** (IL 121–135) ; effets ; `ItemDrop.MakePiece(true)` ; appel de tous les `IPlaced.OnPlaced()` du prefab (IL 237–279) ; effet `m_placeEffect` ; statistiques de hauteur ; `Character.AddNoise(50)` (IL 614–620). `Piece.OnPlaced` (IPlaced) ne fait quelque chose que si `m_harvest` : récolte les `Pickable` récoltables dans le rayon `Lerp(m_harvestRadius, m_harvestRadiusMaxLevel, skill Farming)` puis détruit la pièce (IL 0–155).
- `WearNTear.OnPlaced()` (IL 0–18) : `m_createTime = −1` (donc `ShouldUpdate` vrai tout de suite, §1.3) et `m_clearCachedSupport = true` (les voisines seront notifiées au prochain `UpdateSupport`, §1.2 étape 3). `Piece.IsPlacedByPlayer()` = `m_creator > 0` (IL 0–10) ; `m_creator` vient du ZDO `s_creator` (`Piece.Awake` IL 88–112).

### 3.4 Coût et vérification des ressources [PROUVÉ]
- `Piece+Requirement` (champs : `m_resItem`, `m_amount`, `m_extraAmountOnlyOneIngredient`, `m_amountPerLevel`, `m_upgraderResource`, `m_recover`) ; défauts du constructeur : `m_amount = 1`, `m_amountPerLevel = 1`, `m_recover = true`. `GetAmount(quality)` : `quality ≤ 1` → `m_amount` ; sinon `floor(niveau·m_amountPerLevel + (m_upgraderResource ? m_amount : 0))` avec `niveau = quality−1` si `quality < 4`, sinon `4 + (quality−4)/2` (IL 0–80).
- `HaveRequirements(piece, mode)` (`Player`, IL 0–343 ; `RequirementMode` : CanBuild 0, IsKnown 1, CanAlmostBuild 2) :
  - Si `piece.m_craftingStation` : en mode 1 ou 2, la station doit être dans `m_knownStations` ; en mode 0 (`CanBuild`), il faut **`CraftingStation.HaveBuildStationInRange(nom, position du joueur)`** ou la clé globale `NoWorkbench` (27) (IL 0–96). La portée de construction d'une station = `GetStationBuildRange()` = `m_rangeBuild + nb_extensions · m_extraRangePerLevel` (`GetExtensions` IL 61–84, mis à jour au plus toutes les 2 s : IL 1–27) ; `m_rangeBuild = 10` au constructeur [INFÉRÉ pour la valeur effective] ; distance **horizontale** (le `y` du joueur est remplacé par celui de la station), strictement `< portée` (`HaveBuildStationInRange` IL 0–117).
  - DLC requis installé (IL 97–130).
  - Mode ≠ 1 et clé globale `Piece.FreeBuildKey()` active → vrai (coût nul) (IL 131–154). `FreeBuildKey` (IL 0–33) renvoie la clé 25 (`NoCraftCost`) si la pièce porte un des deux composants testés (lus comme `GetComponent<T>` génériques non nommés), sinon la clé 24 (`NoBuildCost`).
  - Pour chaque `Requirement` avec `m_resItem` et `m_amount > 0` : mode 0 → `Inventory.CountItems(nom, −1, true) ≥ m_amount` (valeur brute `m_amount`, pas `GetAmount`) ; mode 1 → matériau connu (`m_knownMaterial`) ; mode 2 → `Inventory.HaveItem(nom, true)` (IL 169–337).
- `ConsumeResources(reqs, qualityLevel=0, itemQuality=−1, multiplier=1)` (IL 0–133) : pour chaque `Requirement` valide (en sautant ceux dont `m_upgraderResource` ne correspond pas à `CraftingStation.m_upgrader` de la station courante), `Inventory.RemoveItem(nom, GetAmount(qualityLevel)·multiplier, itemQuality, true)` : pose normale = `m_amount` unités de chaque ressource.
- Pose gratuite : `Player.m_noPlacementCost` (cheat, `get_PlacementCostDisabled` IL 0–6) saute `HaveRequirements` ; clés globales 24/25 évitent `ConsumeResources`.

## 4. Démontage et remboursement

### 4.1 Démontage — `Player::RemovePiece`, `CheckCanRemovePiece` [PROUVÉ]
- Déclenchement (`UpdatePlacement` IL 536–829) : bouton `Remove` relâché dans les 0,2 s, `Time.time − m_lastToolUseTime > m_removeDelay` (0,25 s au constructeur de `Player`, IL 130–135), `canRemove` selon `PieceTable.m_canRemovePieces` / `m_canRemoveFeasts`, et `HaveStamina(attackStamina)`. En cas de succès : `UseStamina(GetBuildStamina())`, `m_buildRemoveDebt` +1 (plafond 20, si l'outil a une compétence), durabilité −= `GetPlaceDurability × m_durabilityRate`, effet `m_destroyEffect`.
- `RemovePiece()` (IL 0–575) : raycast caméra 50 m masque `m_removeRayMask` ; le point d'impact doit être à **< `m_maxPlaceDistance` de l'œil** (IL 37–82) ; pièce = `GetComponentInParent<Piece>` du collider (ou `TerrainModifier.FindClosestModifierPieceInRange(point, 2,5)` pour le terrain) ; **`Piece.m_canBeRemoved` doit être vrai** (défaut vrai ; IL 157–166) ; `Location.IsInsideNoBuildLocation` → `$msg_nobuildzone` ; `PrivateArea.CheckAccess(pos, 0, flash=true, ward=false)` → `$msg_privatezone` ; `CheckCanRemovePiece(piece)` ; `Piece.CanBeRemoved()` (conteneur non vide / bateau, §4.2) sinon `$msg_cantremovenow` (IL 255–297). Puis `IRemoved.OnRemoved()` ; si la pièce a un `WearNTear` : **`WearNTear.Remove(false)`** → `Destroy(null, false)` donc **remboursement** (§1.5, §4.2) ; sinon, si c'est un objet destructible, `Character.Damage(HitData(1e10))` ; sinon `ClaimOwnership`, `Piece.DropResources(null)` et `ZNetScene.Destroy` (IL 314–526).
- `CheckCanRemovePiece(piece)` (IL 0–88) : sauf `m_noPlacementCost`, si `piece.m_craftingStation` existe il faut `HaveBuildStationInRange(nom, position du joueur)` ou la clé `NoWorkbench` (27), sinon `$msg_missingstation` : **on ne démonte (ni ne répare) un établi/une pièce liée à un établi que si la station requise est à portée du joueur**.
- La destruction par effondrement (`UpdateWear` → `ApplyDamage` → `Destroy(null, false)`) passe par le même `Destroy` : elle rembourse aussi (§4.2).

### 4.2 Remboursement — `Piece::DropResources(hit)` (IL 0–588) [PROUVÉ]
`Destroy` l'appelle si `!blockDrop` (§1.5) ; `RemovePiece` pour les objets sans `WearNTear`. Règles :
- Si la clé globale `Piece.FreeBuildKey()` est active : aucun remboursement (IL 0–18).
- Pour chaque `Requirement` avec `m_resItem != null` et **`m_recover == true`** (IL 70–77) : `n = m_amount` (**quantité complète, indépendante de la santé de la pièce**) ; si la pièce porte un `Feast`, `n = floor(n·GetStackPercentige())` ; `n > 0` requis (IL 111–150) ; `Game.CheckDropConversion` peut remplacer/ajuster l'objet et `n` (IL 155–177) ; **si la pièce n'a pas été posée par un joueur (`!IsPlacedByPlayer`) : `n = max(1, n/3)`** (division entière) (IL 179–197).
- Livraison : si `m_destroyedLootPrefab` est défini, l'objet est ajouté à un `Container` créé à `position + haut · m_returnResourceHeightOffset` (défaut 1) en répétant par piles de `m_maxStackSize` (IL 199–409) ; sinon `n` est instancié en `ItemDrop` à la même position, par piles de `m_maxStackSize` (IL 422–570). **Les objets tombent au sol ; il n'y a pas de crédit direct dans l'inventaire du joueur.**
- `Piece.CanBeRemoved()` (IL 0–47) : `Container.CanBeRemoved()` si un conteneur est présent parmi les enfants, sinon `Ship.CanBeRemoved()`, sinon vrai. `WearNTear.CanBeRemoved()` y délègue (IL 0–26). Le champ `Piece.m_canBeRemoved` n'est lu que par `Player.RemovePiece`.

## 5. Non extrait à ce stade
- Données de prefab Unity (assets) : `m_health`, `m_materialType`, `m_supports`, `m_noSupportWear`, `m_noRoofWear`, `m_comOffset`, listes `m_resources`, `m_recover` par ressource, `m_craftingStation`, valeurs sérialisées surchargeant les défauts de constructeur (`m_maxPlaceDistance`, `m_placeDelay`, `m_rangeBuild`, `m_extraRangePerLevel`…), `attackStamina` des outils, `m_deepSnowBuildHeight` effectif.
- Rayon de la zone active (`ZNetScene.PointInsideActiveArea`, champs de `ZoneSystem`) : `OutsideActiveArea` est lu jusqu'à ces appels.
- `PrivateArea.CheckAccess` (logique de garde), `Location.IsInsideNoBuildLocation`, `Heightmap.IsCultivated/GetVegetationMask/GetCultivationMask/FindBiome`, `TerrainModifier`.
- `Player.SetupPlacementGhost` (construction du fantôme), `UpdateStations`, `UpdateWearNTearHover` : désassemblés (`dis/`), non analysés.
- `WearNTear.RPC_Damage` (résistances `m_damages`, `m_minToolTier`, `PrivateArea.OnObjectDamaged`) ; `UpdateWear` : détails neige lourde, cendres, lave, événements persistants, dégâts hors biome requis (structure repérée au §1.3, formules non détaillées).
- `Game.CheckDropConversion`, sémantique exacte de `ZNetView.InvokeRPC(string, …)` sans cible, `Inventory.CountItems/RemoveItem` (qualité, niveau de monde).
- Sémantique Unity (non lisible dans le CIL) : destruction différée, `== null` sur objet détruit, ordre de `OverlapBoxNonAlloc`, tailles de tampons (128 colliders pour `s_tempColliders`, `.cctor`) pouvant tronquer les voisins d'une pièce très entourée.
- Types de paramètres affichés `class:NNNN` / `valuetype:NNNN` dans les `.txt` : index TypeDef/TypeRef non résolus en noms (purement cosmétique).

## 6. Corrections apportées à la version précédente de ce document
1. **§1.1 (erreur grave)** : les lignes Stone, Iron et HardWood avaient été déduites de l'ordre des blocs du `switch`. La table de sauts du CIL (IL 8) n'est pas dans l'ordre de l'enum : `Stone → bloc IL114 (1000/100, pertes 1 / 0,125)`, `Iron → IL144 (1500/20, 0,0769 / 0,0769)`, `HardWood → IL84 (140/10, 0,1667 / 0,1)`. L'ancienne table donnait Stone 140, Iron 1000, HardWood 1500. Les autres matériaux étaient corrects. L'association nom → index est maintenant [PROUVÉ] (valeurs d'enum lues dans la table `Constant`).
2. **§1.2** : la condition de sortie rapide du cache omettait `plus_grand_support_voisin > m_support` et le détail de la boucle ; l'étape de notification des voisins (`m_clearCachedSupport`) et le masque `s_rayMask` (désormais [PROUVÉ]) étaient absents ; l'élargissement des boîtes (+0,15 m) est ajouté.
3. **§1.3** : l'ancienne version ne mentionnait ni le test de propriété (`IsOwner`), ni la sortie hors zone active, ni la clé `NoBuildingFall`, et décrivait la grâce de 30 s comme générale alors qu'`OnPlaced` met `m_createTime` à −1 (les pièces posées par un joueur s'usent immédiatement).
4. **§2.1** : « jamais en dessous de 50 % » était inexact (le test est fait avant le coup, une pièce à 50,1 % passe à 45,1 %) ; l'appel `0x060015b8` est maintenant [PROUVÉ] `EnvMan.IsWet()`.
5. **§2.2** : le seuil « 4 s » est un accumulateur alimenté avec le `deltaTime` d'une frame par cycle (§1.4), pas une période murale ; `m_haveRoof` vaut vrai par défaut ; tag « leaky » et couches de `s_rayMask` résolus.
6. **§2.3** : tag `"leaky"` et six couches de `m_coverRayMask` résolus (littéraux auparavant non lus) ; `Player.UpdateCover` est appelé depuis `FixedUpdate`.
7. **§2.4** : l'appel 0x06000336 est `Player.NoCostCheat()` (cheat « sans coût »), pas un mode noclip/créatif.
8. Ancienne section « Non extrait » : cascade/`Destroy`/`Remove`, fréquence d'appel de `UpdateWear` et règles de placement sont maintenant extraites (§1.4, §1.5, §3, §4).

## 7. Adaptation prévue à WoW (hypothèses de conception, non vérifiées)
- Pas de physique Unity : remplacer `OverlapBox` / `SphereCast` / `Raycast` par une **grille de pièces** (voisinage discret) côté serveur ; pour le toit et la couverture, un test sur grille « existe-t-il une pièce de toit au-dessus dans la colonne » (en gardant l'idée d'un tag « qui ne couvre pas », équivalent de `"leaky"`).
- Le « terrain » (ancrage) = sol ADT/vmap sous la pièce (test de hauteur serveur), les rochers/WMO = « solide non-pièce » (support max).
- Valeurs numériques : reprendre les constantes du §1.1 (corrigées) telles quelles, puis équilibrer par test.
- Cadence : un pas de simulation explicite (par exemple 1 s par passe, N pièces par tick) plutôt que de reproduire l'accumulateur de `UpdateCover` ; l'invalidation de cache à la pose / à la destruction / au changement de santé est à conserver.
- Placement : conserver l'ordre « dernier test échoué l'emporte » ou, mieux, renvoyer le premier échec ; remboursement = ressources `m_recover` complètes (÷3 si pièce non posée par un joueur), déposées au sol ; réparation = soin complet sans coût de ressource, station requise à portée.

## 8. Stations, extensions et niveaux (`CraftingStation`, `StationExtension`, `Recipe`, `Player`, `InventoryGui`)

Source : même DLL (SHA-256 en tête de document). Désassemblages : `analysis/valheim/dis/CraftingStation._all.txt`, `StationExtension._all.txt`, `Recipe._all.txt`, `Player.{RequiredCraftingStation,HaveRequirements,AddKnownStation,KnowStationLevel,UpdateStations,SetCraftingStation,GetAvailableRecipes,UpdateKnownRecipesList,ResetCharacter,ResetCharacterKnownItems,FixedUpdate}.txt`, `InventoryGui._all.txt` (+ `InventoryGui.CanRepair.txt`), `EffectArea._all.txt`, `MonoUpdaters._all.txt`, `ItemSets.AddKnown.txt` ; énumérations dans `dis/_enums.txt` (ajout de `EffectArea+Type`). Ce § précise la ligne « `UpdateStations` … non analysés » du §5 (désormais analysé). Aucune section existante n'est modifiée : aucune erreur n'a été trouvée dans §2.4 ni §3 (les valeurs `m_rangeBuild = 10`, `GetStationBuildRange`, `HaveBuildStationInRange` y sont confirmées ici avec leurs offsets).

Outil ajouté : `analysis/callscan.cjs` (`node callscan.cjs CraftingStation,StationExtension,Recipe '<regex de champs>'`) décode **linéairement tous les corps IL** (11 048 méthodes) depuis les tables de métadonnées et liste les appelants directs et les accès aux champs, en une seconde, sans REA (validé : il retrouve exactement les appels déjà lus à la main). Résultat : `valheim/callers_CraftingStation.json`. Même limite que `sweep.cjs` : pas d'appels par `SendMessage`/réflexion/moteur Unity (les `InvokeRepeating("CheckFire")`, `Awake`, `Start`… sont lus dans le CIL des types eux-mêmes).

Légende des valeurs numériques : **[CIL]** constante lisible dans un constructeur ou un littéral (donc *valeur par défaut* : un prefab Unity peut la surcharger) ; **[PREFAB]** aucune valeur dans le CIL (champ sérialisé) ; **[NON EXTRAIT]**.

### 8.1 Formule du niveau d'une station [PROUVÉ]
- `CraftingStation::GetLevel(bool)` (IL 0–9) = **`1 + GetExtentionCount(b)`** (le booléen sert à rafraîchir les extensions). `GetExtentionCount(b)` (IL 0–21) : si `b`, appelle `GetExtensions()` (résultat ignoré), puis renvoie `m_attachedExtensions.Count`. Aucun plafond ni table dans le CIL : le niveau maximal dépend uniquement du nombre de types d'extensions présents dans les prefabs.
- Tous les appelants de `GetLevel` (balayage exhaustif) passent `true` : `Player.RequiredCraftingStation` (IL 106), `Player.AddKnownStation` (IL 2), `InventoryGui.UpdateRecipe` (IL 96 et 1088), `InventoryGui.CanRepair` (IL 210). Le cache de 2 s (§8.3) s'applique donc toujours.
- `CraftingStation::GetExtensions()` (IL 0–201) reconstruit `m_attachedExtensions` : `Clear` (IL 33), puis `StationExtension.FindExtensions(this, position de la station, liste)` (IL 38–56). Seule fonction qui alimente la liste.

### 8.2 Comptage des extensions — `StationExtension::FindExtensions` (IL 0–119) [PROUVÉ]
Pour chaque extension `x` du registre statique `m_allExtensions` (ordre d'`Awake`) :
1. **Distance** : `Vector3.Distance(x.position, station.position) < x.m_maxStationDistance` (IL 21–44) : distance **3D euclidienne**, **seuil strict**, seuil **propre à l'extension** (pas à la station) ;
2. **Même station** : `x.m_craftingStation.m_name == station.m_name` (comparaison de chaînes, IL 46–68) : on compare des **noms**, pas des instances ;
3. **Empilement** : si `!x.m_stack` et qu'une extension de même `GetExtensionName()` (= `Piece.m_name`, `ExtensionInList` IL 0–64) est déjà dans la liste, `x` est ignorée (IL 70–85) ; sinon `x` est ajoutée (IL 87).

Conséquences :
- `niveau = 1 + Σ_types ( m_stack ? n_type : min(1, n_type) )`, où `n_type` = nombre d'extensions de ce type (même `Piece.m_name`) dans leur rayon propre. Deux instances d'un type non empilable comptent **une seule fois** ; un type avec `m_stack = true` compte chaque instance.
- **Aucune exclusivité** : une extension à portée de deux stations de même nom compte pour les deux (chaque station relit toute la liste statique). L'ordre de la liste n'influence pas le total.
- Les stations et extensions « fantômes » de prévisualisation ne comptent pas : `StationExtension.Awake` (IL 0–13) et `CraftingStation.Start` (IL 0–38) sortent si le `ZNetView` n'a pas de ZDO ; l'enregistrement dans `m_allExtensions` (Awake IL 26–32) et `m_allStations` (Start IL 39–45) vient après ; retrait dans `OnDestroy` (extension IL 31–42, station IL 0–11).
- Défauts du constructeur d'extension (`StationExtension..ctor`, IL 0–32) : `m_maxStationDistance = 5` [CIL], `m_connectionOffset = (0,0,0)` ; `m_stack = false`, `m_continousConnection = false` (valeurs initiales). `m_craftingStation` (prefab de la station visée), `m_spaceRequirement` (champ de `Piece`), les `m_maxStationDistance` / `m_stack` effectifs : [PREFAB].
- Autres méthodes (placement ou cosmétique) : `OtherExtensionInRange(r)` (IL 0–90) = existe-t-il une **autre** extension (n'importe quel type, n'importe quelle station) à distance 3D `< r` ; `FindClosestStationInRange(pos)` (IL 0–23) délègue à `CraftingStation.FindClosestStationInRange(nom, pos, m_maxStationDistance)` (station de même nom la plus proche, distance 3D `< portée`, IL 0–112) ; `FindStationsInRange` idem avec liste ; `GetConnectionPoint` = `transform.TransformPoint(m_connectionOffset)` (IL 0–17) ; `StartConnectionEffect` / `StopConnectionEffect` / `UpdateConnection` (`InvokeRepeating("UpdateConnection", 1, 4)` si `m_continousConnection`, Awake IL 37–61) : lien visuel extension → station, **sans incidence sur le niveau**. Le placement (§3) utilise `FindClosestStationInRange` (aucune station → `ExtensionMissingStation`) et `OtherExtensionInRange(m_spaceRequirement)` (→ `MoreSpace`) : `Player.UpdatePlacementGhost` IL 376–439.
- **L'extension ne « déverrouille » rien directement** : aucun code ne relie une extension à une recette ; seule la valeur `1 + n` de `GetLevel` est comparée à `Recipe.m_minStationLevel` (§8.5).

### 8.3 Cadence et cache [PROUVÉ]
- `m_updateExtensionTimer` : initialisé à **2** dans `Start` (IL 121–127), donc le premier `GetExtensions` recalcule immédiatement ; incrémenté du `deltaTime` de la frame par `CraftingStation.CustomUpdate(dt, t)` (IL 42–55), appelé chaque frame par `MonoUpdaters.Update` (IL 356–374 : `CraftingStation.get_Instances()`, liste alimentée par `OnEnable`/`OnDisable`) ; `CustomUpdate` sort sans rien faire si le `ZNetView` est invalide (IL 0–27). Aucun autre accès au timer (balayage).
- `GetExtensions` : si `m_updateExtensionTimer < 2` → renvoie la liste en cache (IL 6–11) ; sinon timer = 0 (IL 16–22) et recalcul. **Une extension posée ou détruite n'est vue qu'au plus ~2 s plus tard.** Le littéral 2 est dans le code ; le champ `m_updateExtensionInterval = 2` n'est jamais lu.
- Après recalcul : `m_buildRange = m_rangeBuild + GetExtentionCount(false) · m_extraRangePerLevel` (IL 61–84) ; si `m_areaMarker` existe, le rayon de son cercle = `m_buildRange` (IL 89–114) ; le rayon du collider `m_effectAreaCollider` (sphère ou capsule) aussi (IL 119–190) [la portée gameplay de cette zone dépend du type d'`EffectArea` du prefab : NON EXTRAIT]. `m_buildRange` vaut 0 avant le premier calcul.
- `GetStationBuildRange()` (IL 0–13) = `GetExtensions()` puis `m_buildRange`.
- `PokeInUse()` (IL 0–17) : `m_useTimer = 0` + `TriggerExtensionEffects()` (appelle `GetExtensions()` et fait clignoter le lien de chaque extension 1 s). `m_useTimer` vaut 10 au constructeur ; le GameObject `m_inUseObject` n'est actif que tant que `m_useTimer < 1` (`CustomUpdate` IL 56–109) : cosmétique. `ShowAreaMarker` (IL 0–58) affiche le cercle 0,5 s et appelle `PokeInUse`. Les effets `m_craftItemEffects` / `m_craftItemDoneEffects` / `m_craftItemDoneFailEffects` / `m_repairItemDoneEffects` sont instanciés à la position du joueur (`InventoryGui.OnCraftPressed` IL 411–480, `DoCrafting` IL 1984–2031) : cosmétiques, sans règle.
- `Player.UpdateStations(dt)` (appelé par `Player.FixedUpdate` IL 154–156 avec `fixedDeltaTime`) : accumulateur `m_stationDiscoverTimer` ; si `> 1` → remise à 0 puis `CraftingStation.UpdateKnownStationsInRange(player)` (IL 0–39). Puis, si le joueur a une station courante : hors `InUseDistance` → ferme l'inventaire et `SetCraftingStation(null)` (IL 61–92) ; inventaire fermé → `SetCraftingStation(null)` (IL 93–107) ; sinon `PokeInUse()` (IL 108–114), rotation du joueur vers la station (IL 119–225) et animation `"crafting"` = `m_useAnimation` (IL 230–259).
- `CraftingStation.InUseDistance(player)` (IL 0–35) : distance 3D joueur–station `< m_useDistance`. `Interact` (IL 0–68) exige `InUseDistance`, puis `CheckUsable(player, true)`, puis `Player.SetCraftingStation` et `InventoryGui.Show(null, 3)`.

### 8.4 Valeurs de `CraftingStation` lisibles dans le CIL (`.ctor` IL 0–152) [CIL, défauts]
| Champ | Défaut CIL | Rôle prouvé |
|---|---|---|
| `m_discoverRange` | 4 | rayon (3D, `< station.m_discoverRange`) de « découverte » (`UpdateKnownStationsInRange` IL 33–60) |
| `m_rangeBuild` | 10 | base de la portée de construction (§8.3) |
| `m_extraRangePerLevel` | aucun (0) [PREFAB] | portée ajoutée **par extension comptée** |
| `m_useDistance` | 2 | distance d'utilisation (`InUseDistance`) |
| `m_craftRequireRoof` | true | `CheckUsable` : toit + 70 % de couverture (§2.4) |
| `m_craftRequireFire` | true | `CheckUsable` : `m_haveFire` (§8.6) |
| `m_craftingSkill` | 107 = `Skills.SkillType.Crafting` | compétence du bonus de craft des empilables (`DoCrafting` IL 228–335 : tirage `Random.value < skillFactor · m_craftBonusChance`) |
| `m_hasCraftTab`, `m_canRepair` | true, true | onglets Craft / Réparation |
| `m_useTimer` | 10 | voir §8.3 |
| `m_upgrader`, `m_showBasicRecipies`, `m_haveFire`, `m_name` (""), `m_useAnimation` | false, false, false, "", 0 (valeurs initiales) | **valeurs effectives dans les prefabs** [PREFAB] |

### 8.5 Niveau requis par une recette [PROUVÉ]
- `Recipe::GetRequiredStationLevel(quality)` (IL 0–16) = **`max(1, m_minStationLevel) + (quality − 1)`**. `quality` est la qualité **visée** : 1 pour une fabrication ; `m_quality + 1` pour l'amélioration d'un objet (`InventoryGui.UpdateRecipe` IL 258–287, `DoCrafting` IL 26–39). Chaque amélioration exige donc **un niveau de station de plus**.
- `Recipe::GetRequiredStation(quality)` (IL 0–32) : `m_craftingStation` s'il est défini ; sinon, **si `quality > 1`**, `m_repairStation` ; sinon null.
- Défauts `Recipe..ctor` (IL 0–58) : `m_minStationLevel = 1`, `m_amount = 1`, `m_enabled = true`, `m_qualityResultAmountMultiplier = 1`, `m_listSortWeight = 100`, `m_resources` = tableau vide. `m_craftingStation`, `m_repairStation`, `m_requireOnlyOneIngredient`, `m_noCraftOnlyUpgrade`, contenu de `m_resources`, liste `ObjectDB.m_recipes` : [PREFAB].
- `Recipe::GetAmount(quality, out, out, multiplier)` (IL 0–89) : `n = m_amount` ; si `m_requireOnlyOneIngredient` : `n += ceil((m_quality_de_l'objet_choisi − 1) · m_amount · m_qualityResultAmountMultiplier) + extra` où `extra` est une sortie de `Player.GetFirstRequiredItem` (non analysée) ; résultat `n · multiplier`. Hors niveau de station ; noté pour l'amélioration.
- **`Player::RequiredCraftingStation(recipe, quality, checkLevel)` (IL 0–146)**, seule méthode qui compare `GetLevel()` et le niveau requis :
  1. `station = recipe.GetRequiredStation(quality)` (IL 0–7) ;
  2. si le joueur a une station courante **`m_upgrader`** → **vrai sans autre test** (IL 8–36 : ni nom, ni niveau) ;
  3. si `station != null` : pas de station courante → faux (IL 46–61) ; **noms (`m_name`) différents** → faux (IL 62–87) ; si `checkLevel` et `m_currentStation.GetLevel(true) < recipe.GetRequiredStationLevel(quality)` → faux (IL 88–115) ; sinon vrai ;
  4. si `station == null` (recette « de base ») : station courante dont `m_showBasicRecipies` est faux → faux (IL 116–143) ; sinon vrai.
- `Player::HaveRequirements(recipe, discover, quality, amount)` (IL 0–136) : si `discover` (« connaît-on la recette ? ») et que `recipe.m_craftingStation` est défini, il faut **`KnowStationLevel(station.m_name, recipe.m_minStationLevel)`** (IL 0–40 ; niveau **brut**, sans `max(1,·)` ni `+ quality − 1`) ; si `!discover` : `RequiredCraftingStation(recipe, quality, true)` (IL 43–55). Puis DLC (IL 56–119), puis `HaveRequirementItems` (matériaux connus si `discover`, possédés sinon).
- Liste affichée : `Player::GetAvailableRecipes` (IL 0–523) retient une recette activée (ou saisonnière), connue (`m_knownRecipes`) ou, sinon, si la clé globale `AllRecipesUnlocked` (28) ou `m_noPlacementCost` est active, et pour laquelle **`RequiredCraftingStation(recipe, 1, checkLevel = false)`** est vrai (IL 468–477) : **le niveau n'est pas testé pour l'affichage** (la recette est visible mais grisée).
- Interface, `InventoryGui.UpdateRecipe` : niveau de la station affiché = `GetLevel(true)` (IL 94–137) ; niveau requis affiché = `GetRequiredStationLevel(quality)`, ou **1 si la station est `m_upgrader`** (IL 985–1007) ; ce texte clignote en rouge (`Mathf.Sin(Time.time · 10) > 0`) si `GetLevel(true) < requis`, sauf si la clé **`NoCraftCost` (25)** est active (IL 1077–1177). Le bouton « Fabriquer » est actif si `(HaveRequirements(recipe, false, quality, nb) ET station utilisable) OU NoCostCheat OU (NoCraftCost ET station utilisable)` (IL 1223–1309, l'« utilisable » = `CheckUsable(player, false)` quand la recette exige une station). `DoCrafting` refait `HaveRequirements(recipe, false, quality, nb)` (IL 139–177) et abandonne si faux, sauf `NoCostCheat` ou `NoCraftCost`.
- **Réparation** : `InventoryGui.CanRepair(item)` (IL 0–234) : objet réparable (`m_canBeReparied`) ; `NoCostCheat()` → vrai ; station courante requise ; recette de l'objet (`ObjectDB.GetRecipe`) avec `m_craftingStation` ou `m_repairStation` ; la station courante doit porter le nom de `m_repairStation` (IL 119–155), sinon celui de `m_craftingStation` (IL 157–193), ou l'objet doit venir d'un niveau de monde plus bas que `Game.m_worldLevel` (IL 195–206, sémantique du niveau de monde non analysée) ; puis **`min(GetLevel(true), 4) ≥ recipe.m_minStationLevel`** (IL 208–231). **Le niveau de station compte au plus pour 4 en réparation** ; la qualité de l'objet n'intervient pas. `ItemData.GetTooltip` affiche `$item_repairlevel = m_minStationLevel` (IL 723–787). `RepairOneItem` (IL 62) et `HaveRepairableItems` (IL 64) exigent `CheckUsable(player, true)`.
- Aucune autre méthode du DLL ne lit `m_minStationLevel`, `GetRequiredStationLevel` ou `GetLevel` (balayage exhaustif ; `Achievements.GetCraftableItems` ne lit que `m_craftingStation`).

### 8.6 Toit, feu : `CheckUsable` et `CheckFire` [PROUVÉ]
- `CheckUsable(player, showMessage)` : voir §2.4 (toit puis feu). Le test `m_craftRequireFire` (IL 92–135) est ignoré avec `NoCostCheat`.
- `CheckFire()` (IL 0–52) : `m_haveFire = EffectArea.IsPointPlus025InsideBurningArea(station.position)`, puis active/désactive `m_haveFireObject`. Planifié par `InvokeRepeating("CheckFire", 1, 1)` dans `Start` **seulement si** `m_craftRequireFire` est vrai (IL 92–116) : première évaluation à 1 s, puis chaque seconde ; `m_haveFire` vaut faux avant.
- `IsPointPlus025InsideBurningArea(p)` (IL 0–71) : `p` est-il dans l'une des `Bounds` de `EffectArea.s_BurningAreas` ? Ces bornes sont construites une seule fois dans `EffectArea.Awake` (IL 203–276) pour les zones dont `m_type & 8` (enum `EffectArea+Type` : Heat 1, Fire 2, PlayerBase 4, **Burning 8**, Teleport 16, NoMonsters 32, WarmCozyArea 64, PrivateProperty 128) : `collider.bounds` **agrandie de (0,25 ; 0,25 ; 0,25)** par `Bounds.Expand` (soit +0,125 de chaque côté [INFÉRÉ : sémantique Unity de `Expand(Vector3)`]). Les bornes sont figées à l'`Awake` (une zone qui bouge ne met pas sa boîte à jour). Taille et position des colliders de feu : [PREFAB].

### 8.7 Stations connues et déblocage de recettes [PROUVÉ]
- `Player.m_knownStations : Dictionary<string, int>` (nom → **niveau maximal vu**), sauvegardé dans `Player.Save` (IL 163–237 : compte, puis paires chaîne + entier) et relu par `Load` (IL 301–342), vidé par `ResetCharacter` (IL 27–33) et `ResetCharacterKnownItems` (IL 11–17) (commandes de console `Terminal`).
- `Player::AddKnownStation(station)` (IL 0–176) : `niveau = station.GetLevel(true)` ; nom inconnu → ajout + message « nouvelle station » + journal (IL 102–171) ; nom connu avec un niveau **strictement inférieur** → mise à jour + message « niveau » (IL 29–95) ; dans les deux cas `UpdateKnownRecipesList()` (IL 96 / 171). **Le niveau connu ne baisse jamais** (aucune écriture à la baisse dans le DLL).
- `KnowStationLevel(nom, niveau)` (IL 0–25) : `m_knownStations[nom] ≥ niveau` (faux si absent).
- Déclencheurs d'`AddKnownStation` (balayage exhaustif) : (a) `CraftingStation.UpdateKnownStationsInRange(player)` : pour **chaque station de `m_allStations`** à distance 3D `< station.m_discoverRange` du joueur (IL 12–60), au plus ~1 fois par seconde (§8.3) ; (b) `Player.SetCraftingStation(s)` (IL 25), donc chaque ouverture de station ; (c) `Player.PlacePiece` (IL 26–43) sur le `CraftingStation` du prefab instancié (avant son `Start` : `m_attachedExtensions` est encore vide, donc niveau 1 [INFÉRÉ]) ; (d) `ItemSets.AddKnown` (IL 0–42) : ensembles de départ/cheat (`ItemSet.m_knownStations`, contenu en prefab).
- `UpdateKnownRecipesList()` (IL 0–420) parcourt `ObjectDB.m_recipes` : toute recette activée dont l'objet n'est pas déjà connu et pour laquelle `HaveRequirements(recipe, discover = true, 0, 1)` est vrai est ajoutée (`AddKnownRecipe`) ; idem pour les pièces des `PieceTable` possédées (`HaveRequirements(piece, IsKnown)` = station connue **par nom**, quel que soit son niveau). Appelée aussi par `AddKnownItem` (IL 230), `OnInventoryChanged` (IL 763), `Player.Awake` (IL 930). **Une recette se « débloque » donc quand le joueur connaît la station au niveau brut `m_minStationLevel` et connaît les matériaux** ; la connaissance est permanente, alors que la *fabrication* exige le niveau **actuel** de la station ouverte (§8.5).
- Pièces : `HaveRequirements(piece, mode)` (§3) n'utilise que le **nom** de la station (connue pour les modes 1 et 2 ; à portée de construction pour le mode 0 ; clé `NoWorkbench` = 27). **Le niveau n'a donc aucun effet sur la possibilité de poser une pièce**, seulement sur la portée de construction (`m_extraRangePerLevel`) et sur les recettes d'objets.

### 8.8 Portée de construction (rappel du §3, avec offsets) [PROUVÉ]
`HaveBuildStationInRange(nom, pos)` (IL 0–117) : première station de même nom (ordre de `m_allStations`, **pas la plus proche**) telle que `Distance(station.position, (pos.x, station.y, pos.z)) < station.GetStationBuildRange()` : distance **horizontale** (IL 42–82). `Hud.SetupPieceInfo` (IL 409, 586) l'utilise pour l'info-bulle et affiche le cercle (`ShowAreaMarker`).

### 8.9 Lisible dans le CIL ou non
| Donnée | Statut |
|---|---|
| `niveau = 1 + nb d'extensions comptées` ; empilement par `Piece.m_name` ; filtre par nom de station ; distance 3D stricte `< m_maxStationDistance` de l'extension ; cache 2 s | **[PROUVÉ]** |
| `niveau requis = max(1, m_minStationLevel) + qualité − 1` ; station `m_upgrader` ; réparation plafonnée à 4 ; `NoCraftCost` | **[PROUVÉ]** |
| Défauts : `m_maxStationDistance` 5, `m_rangeBuild` 10, `m_discoverRange` 4, `m_useDistance` 2, `m_minStationLevel` 1, seuils 1 s / 2 s | **[CIL]** (défauts de constructeur) |
| `m_extraRangePerLevel`, valeurs effectives des champs ci-dessus par prefab, `m_stack` par extension, `m_spaceRequirement`, `m_upgrader` / `m_showBasicRecipies` / `m_craftRequireRoof` / `m_craftRequireFire` par station | **[NON EXTRAIT]** : prefabs Unity |
| Liste des pièces qui sont des `StationExtension` et station visée par chacune | **[NON EXTRAIT]** : prefabs |
| Noms de stations (établi, forge…) : aucun littéral correspondant dans le DLL (recherche dans toutes les chaînes UTF-16, y compris la table `#US`) | **[NON EXTRAIT]** |
| Niveau maximal d'une station | **[NON EXTRAIT]** (= nombre de types d'extensions des prefabs + 1) |
| **Tableau « niveau d'établi → recettes déblocables »** | **Impossible depuis le CIL** : les recettes (`ObjectDB.m_recipes` : `m_craftingStation`, `m_minStationLevel`, `m_maxQuality`, `m_resources`) et les extensions sont des données de prefabs / `ScriptableObject`, aucune n'est construite dans le code. Il faut les lire dans les assets Unity (hors périmètre de cet extracteur). |
| Dimensions des colliders de feu (zones `Burning`) | **[NON EXTRAIT]** |

### 8.10 Adaptation à WoW (proposition de conception ; non vérifiée en jeu)
**Données (DB de contenu, côté serveur)**
- `station_template(stationKey, rangeBuild = 10, extraRangePerLevel, discoverRange = 4, useDistance = 2, requireRoof, requireFire, upgrader, showBasicRecipes)`.
- `extension_template(typeKey, stationKey, maxStationDistance = 5, stack = 0, spaceRequirement)`.
- `recipe(recipeId, stationKey, minStationLevel = 1, repairStationKey, maxQuality, …)` : le tableau « niveau → recettes » est une simple requête sur cette table, à remplir par le design (l'extraction ne le fournit pas).
- Persistance joueur : `character_known_station(guid, stationKey, maxLevel)` (équivalent de `m_knownStations`, monotone croissant).

**Comptage serveur (équivalent de `GetExtensions`)**
```cpp
// positions 3D, même map obligatoire ; unités : 1 m Valheim ~ 1 yd WoW, à équilibrer
uint32 CountExtensions(StationInst const& s) {
    std::unordered_set<uint32> seenTypes;                 // dédoublonnage par typeKey (= Piece.m_name)
    uint32 n = 0;
    for (ExtensionInst const* x : extensionIndex.QueryRadius(s.mapId, s.pos, s.tpl->maxExtDist)) {  // index spatial (grille)
        ExtensionTemplate const& t = *x->tpl;
        if (t.stationKey != s.tpl->stationKey) continue;              // comparaison de clés (noms), pas d'instances
        if (!(s.pos.GetExactDist(x->pos) < t.maxStationDistance))      // 3D, strict, rayon PROPRE à l'extension
            continue;
        if (!t.stack && !seenTypes.insert(t.typeKey).second) continue; // un seul exemplaire par type si !stack
        ++n;
    }
    return n;
}
uint32 GetLevel(StationInst const& s)      { return 1 + CountExtensions(s); }
float  GetBuildRange(StationInst const& s) { return s.tpl->rangeBuild + CountExtensions(s) * s.tpl->extraRangePerLevel; }
```
- `s.tpl->maxExtDist` = maximum des `maxStationDistance` des extensions de cette station (précalculé) pour borner la requête spatiale.
- **Pas de comptage exclusif** (parité Valheim) : une extension sert toutes les stations de même type à portée. Imposer l'exclusivité serait un **écart volontaire** à documenter.
- **Cache** : Valheim relit au plus toutes les 2 s (prise en compte retardée de ~2 s). Côté serveur, préférer l'**invalidation par évènement** (pose/destruction d'une extension ou d'une station, chargement de zone) avec recalcul paresseux ; recalculer de toute façon `GetLevel` au moment de la demande de fabrication (autorité serveur, jamais de confiance au client). Reproduire les 2 s n'a pas d'intérêt gameplay.
- Prévisualisation (fantôme) : ne pas enregistrer dans l'index tant que la pièce n'est pas réellement posée (équivalent du test ZDO).

**Fabrication, découverte, réparation**
```cpp
uint32 RequiredLevel(Recipe const& r, uint32 quality /* visée, 1 = neuf */) {
    return std::max<uint32>(1, r.minStationLevel) + (quality - 1);
}
bool StationAllows(Player const& p, Recipe const& r, uint32 quality, bool checkLevel) {
    StationInst const* cur = p.GetCurrentStation();      // ouverte : dist3D < useDistance et CheckUsable (toit/feu) OK
    StationKey need = r.stationKey ? r.stationKey : (quality > 1 ? r.repairStationKey : 0);
    if (cur && cur->tpl->upgrader) return true;           // station « upgrader » : aucun autre test (IL 8-36)
    if (need)
        return cur && cur->tpl->stationKey == need &&
               (!checkLevel || GetLevel(*cur) >= RequiredLevel(r, quality));
    return !cur || cur->tpl->showBasicRecipes;            // recettes de base
}
bool RecipeDiscoverable(Player const& p, Recipe const& r) {   // permanent ; niveau BRUT
    return !r.stationKey || p.KnownStationLevel(r.stationKey) >= r.minStationLevel;
}
bool CanRepair(StationInst const& cur, Recipe const& r) {     // après contrôle du nom de station (repair puis craft)
    return std::min<uint32>(GetLevel(cur), 4) >= r.minStationLevel;   // plafond 4 prouvé (IL 215)
}
```
- Connaissance des stations : `maxLevel = max(maxLevel, GetLevel)` à l'ouverture, à la pose, et par un balayage d'environ 1 s des stations à `< discoverRange` du joueur ; jamais à la baisse ; relancer la recherche de recettes découvrables à chaque hausse.
- Pièces liées à une station : test par **nom** et par portée de construction `< rangeBuild + n · extraRangePerLevel` en distance **horizontale** (plan XY), première station trouvée ; le niveau n'intervient pas.
- Feu : remplacer les `Bounds` figées par « un objet-feu allumé (type Burning) contient le point de la station, boîte agrandie de 0,125 » évalué chaque seconde, uniquement pour les stations `requireFire`.
- Tests de non-régression à écrire : (1) deux extensions de même type non empilables dans le rayon → +1 ; avec `stack` → +2 ; (2) distance exactement égale à `maxStationDistance` → non comptée ; (3) extension d'un autre `stationKey` → non comptée ; (4) extension hors de *son* rayon mais dans la portée de la station → non comptée (le rayon est celui de l'extension) ; (5) amélioration à la qualité 3 d'une recette `minStationLevel = 2` exige le niveau 4 ; (6) station `upgrader` ouverte → toute recette passe `StationAllows` ; (7) niveau connu jamais décroissant après destruction d'extensions ; (8) une même extension sert deux établis voisins.

### 8.11 Inconnues à lever (par ordre d'impact)
1. Extensions de chaque station avec `m_maxStationDistance`, `m_stack`, `m_extraRangePerLevel` effectifs (prefabs).
2. `ObjectDB.m_recipes` : station, `m_minStationLevel`, `m_maxQuality`, matériaux (assets).
3. `m_upgrader` / `m_showBasicRecipies` / toit / feu par prefab de station.
4. Sémantique du niveau de monde dans `CanRepair` (IL 195–206).
5. Taille des zones de feu (`Burning`) des prefabs.

## 9. Fonderie et four à charbon (`Smelter`) — 2026-10-26

Sources : prefabs `smelter` et `charcoal_kiln` (composant `Smelter`, typetrees des bundles, `C:\Wowlheim\valheim_extract\valheim_data.json`),
enfants des prefabs (Transform + `SmokeSpawner`, lus par script UnityPy), CIL de `Smelter` et `SmokeSpawner`
(`analysis/valheim/dis/Smelter._all.txt`, `SmokeSpawner._all.txt`, extraits par `node analysis/rea.cjs dis Smelter '*'`).
Mise en œuvre : `server/Wowlheim/Smelter.{h,cpp}`, tables `wowlheim_smelter(_conversion)` (générées par `gen_server_sql.py`, `build_smelters`)
et `wowlheim_smelter_state` (`server/sql/characters/002_wowlheim_smelter.sql`).

### 9.1 Valeurs des prefabs [PROUVÉ, données]
| Champ | `smelter` (Fonderie) | `charcoal_kiln` (Four à charbon) |
|---|---|---|
| `m_fuelItem` | `Coal` (Charbon) | aucun |
| `m_maxOre` | 10 | 25 |
| `m_maxFuel` | 20 | 0 |
| `m_fuelPerProduct` | 2 | 0 |
| `m_secPerProduct` | 30,0 | 15,0 |
| `m_spawnStack` | 0 | 0 |
| `m_requiresRoof` | 0 | 0 |
| `m_windmill` | nul | nul |
| `m_conversion` (ordre du prefab) | CopperOre→Copper, IronOre→Iron, IronScrap→Iron, BronzeScrap→Bronze, TinOre→Tin, SilverOre→Silver, CopperScrap→Copper | Wood→Coal, FineWood→Coal, RoundLog→Coal |
| `SmokeSpawner` (enfant `_enabled/SmokeSpawner`) | position locale (0 ; 4,58 ; 0), `m_testRadius` 0,75, `m_testMask` = couche 31 | (0 ; 3,48 ; 0), 0,75, couche 31 |
| `Piece.m_resources` / station | 20 Pierre, 5 Noyau de Surtling ; établi | 20 Pierre, 5 Noyau de Surtling ; établi |
| Interrupteurs | `add_ore`, `add_wood` (`Switch.m_holdRepeatInterval` 0,2 s) | `add_ore` seulement (pas de `m_addWoodSwitch`) |

Haut fourneau et rouet (même composant, même code serveur ; kinds `blastfurnace` et `spinningwheel`, lus par `vh_dump.py` le 2026-10-26) :

| Champ | `blastfurnace` (Haut fourneau) | `piece_spinningwheel` (Roue / rouet) |
|---|---|---|
| `m_fuelItem` | `Coal` (Charbon) | aucun |
| `m_maxOre` / `m_maxFuel` / `m_fuelPerProduct` | 10 / 20 / 2 | 40 / 0 / 0 |
| `m_secPerProduct` | 30,0 | 30,0 |
| `m_requiresRoof` / `m_spawnStack` | 0 / 0 | **1** / 0 |
| `m_conversion` | FlametalOreNew→FlametalNew, BlackMetalScrap→BlackMetal, FlametalOreNew→FlametalNew, GoldOre→Gold | Flax→LinenThread |
| `SmokeSpawner` | `_enabled/SmokeSpawner` (0 ; 5,318 ; 0,652), `m_testRadius` 0,75 | aucun (`m_smokeSpawner` nul : jamais bloqué) |
| `Piece.m_resources` / station | 20 Pierre, 5 Noyau de Surtling, 10 Fer, 20 Bois fin ; table d'artisan | 20 Bois fin, 10 Clous en fer, 5 Chutes de cuir ; table d'artisan |

Serveur : seule BlackMetalScrap→BlackMetal est gardée (Flametal, Gold absents). `BlackMetalScrap` = objet 9200081 « Morceau de sombracier »
(nom français de Valheim, comme « Sombracier » pour 9200041) ; sources : butin (rules.py : humanoïdes 35 %, mécaniques/brutes/mineurs 30 %, palier 5).
Lin (9200042) : nœud « Plant de lin » 9101031 et butin. Position du SmokeSpawner : Unity → WoW par `vh_mesh.U2W` (x = z Unity, y = −x Unity, z = y Unity) + recentrage du modèle.

La couche 31 est celle du prefab `SmokeBall` (boule de fumée physique, `SphereCollider` + `Rigidbody`) ; les pièces sont en couche 10.
Objets (ItemDrop) : Minerai de cuivre, Minerai d'étain, Ferraille, Minerai d'argent, Minerai de fer : `m_maxStackSize` 30 ; Charbon 50.
Interaction : `Player.m_maxInteractDistance` = 5 (`Player::.ctor` IL 41–47 ; valeur du constructeur, le prefab joueur peut la changer [NON VÉRIFIÉ]).

### 9.2 Ajout de minerai — `Smelter::OnAddOre` (IL 0–257) [PROUVÉ]
1. Sans objet choisi : `FindCookableItem` = premier `m_from` de `m_conversion` (ordre de la liste) présent dans l'inventaire ; aucun → « Vous n'avez rien à transformer » (`$msg_noprocessableitems`).
2. `IsItemAllowed(nom)` faux → « Cela ne marchera pas » (`$msg_wontwork`).
3. `GetQueueSize() >= m_maxOre` → « C'est plein » (`$msg_itsfull`).
4. Sinon « Ajouté <objet> », **une** unité retirée de l'inventaire, `RPC_AddOre` → `QueueOre` : ajout en fin de file (`item<N>`, `s_queued` + 1).

### 9.3 Ajout de combustible — `OnAddFuel` (IL 0–269), `RPC_AddFuel` [PROUVÉ]
Mauvais objet → « Objet inadéquat » ; `GetFuel() > m_maxFuel − 1` → « C'est plein » ; pas de combustible → « Vous n'avez pas de <objet> » ;
sinon une unité retirée et `fuel += 1`. Le combustible est un **réel** (consommé par fractions).

### 9.4 Simulation — `UpdateSmelter` (IL 0–416), appelée chaque seconde (`Awake` : `InvokeRepeating("UpdateSmelter", 1, 1)`) [PROUVÉ]
- `UpdateRoof` (si `m_requiresRoof` : `Cover.IsUnderRoof(m_roofCheckPoint)`) et `UpdateSmoke` (`m_blockedSmoke = SmokeSpawner.IsBlocked()`) une fois par appel.
- `accumulateur += GetDeltaTime()` (temps réel écoulé depuis la dernière mise à jour, `s_startTime`), **plafonné à 3600 s** (IL 65–78).
- Tant que `accumulateur >= 1` : `accumulateur −= 1` puis, si (`m_maxFuel` = 0 ou `fuel > 0`) et (`m_maxOre` = 0 ou file non vide) et `m_secPerProduct > 0`
  et (pas de toit exigé ou toit) et fumée non bloquée :
  - si `m_maxFuel > 0` : `fuel −= 1 / (m_secPerProduct / m_fuelPerProduct)` ; `fuel < 0,0001` → 0 (IL 235–284) ;
  - `bakeTimer += 1` ; si `bakeTimer >= m_secPerProduct` : `bakeTimer = 0`, `RemoveOneOre` (retire le **premier** de la file), `QueueProcessed(minerai)`.
- `m_spawnStack` = 0 → `QueueProcessed` appelle `Spawn(minerai, 1)` : la conversion `m_to` est instanciée au point `output` (objet au sol), une unité à la fois.
- Conséquences : fonderie = 1 lingot / 30 s pour 2 Charbon (1 Charbon / 15 s, consommé seconde par seconde, seulement s'il y a du minerai) ;
  four = 1 Charbon / 15 s par Bois, sans combustible. La minuterie n'est pas remise à zéro quand la station s'arrête.
- `IsActive` (IL 0–65) : mêmes conditions (sert aux effets visuels).

### 9.5 Fumée — `SmokeSpawner::IsBlocked` / `TestBlocked` [PROUVÉ]
Station inactive : `Physics.CheckSphere(position, m_testRadius, m_testMask)` ; active : bloquée si aucune fumée n'a pu être émise depuis plus de 4 s
(l'émission teste la même sphère). Le masque (couche 31) ne voit que les **boules de fumée** : la station s'arrête quand la fumée qu'elle émet
s'accumule autour de la cheminée (pièce fermée sans évent).

### 9.6 Destruction — `DropAllItems` (IL 0–318) [PROUVÉ]
Produits en attente (`SpawnProcessed`), puis `(int)fuel` unités de combustible, puis chaque minerai encore en file : tout tombe au sol.

### 9.7 Adaptations à WoW (écarts assumés)
- **Sortie** : Valheim fait tomber chaque produit au sol ; ici les produits restent dans la station et le joueur les récupère (clic ou `take`) ; ce qui ne rentre pas dans le sac reste dans la station. À la démolition, contenu rendu au démolisseur (sac, puis courrier) ou par courrier au propriétaire (effondrement, ou démolition en mode « sans coût »).
- **Interaction** : un clic sur la station sans marteau = récupérer les produits et ouvrir le panneau ; le minerai et le combustible s'ajoutent depuis le panneau, une unité par clic comme les interrupteurs `add_ore` / `add_wood` (Maj+clic : remplir selon les règles 9.2/9.3 jusqu'au refus). Utilisation acceptée à 3 m du bord de la pièce (`.build api use`, repli de l'addon sur « You are too far away. »). Commandes : `.build api smelter status|add <ore|fuel|id> [n] [guid]|take [guid]` (lignes `[WL]SM|guid|type|nom|file|maxOre|combustible|maxFuel|objetCombustible|minuterie|secParProduit|actif|raison|file id:n,...|produits id:n,...`, `[WL]A|n` ajoutés, `[WL]E|...`). Station la plus proche à 5 m (distance au centre de la pièce, pas au collider comme Valheim).
- **Fumée** : les boules de fumée (physique) ne sont pas simulées ; la cheminée est jugée bloquée quand une pièce posée occupe la sphère de test (rayon 0,75 m autour du point du `SmokeSpawner`). L'accumulation de fumée sous un toit fermé **n'est pas reproduite** (une fonderie dans une maison sans évent fonctionne ici). Les autres fours et fonderies ne comptent pas comme obstacle : leur boîte pleine déborderait de leur forme réelle (dôme du four à charbon).
- **Temps** : les stations tournent tant que le serveur tourne (pas de zones déchargées) ; après un arrêt du serveur, rattrapage du temps écoulé plafonné à 3600 s comme `GetDeltaTime`. État sauvegardé toutes les 10 s et à chaque interaction.
- **Conversions** : BronzeScrap et CopperScrap n'existent pas sur le serveur → conversions omises. Les roches donnent le butin de Valheim : gisement de cuivre → Minerai de cuivre (+ Pierre), étain → Minerai d'étain, tas de boue (`mudpile`) → Ferraille, veine d'argent → Minerai d'argent (+ Pierre) ; détail §13.
- **Toit** : `m_requiresRoof` = 0 pour les deux stations ; s'il était vrai, le serveur utiliserait `BuildingMgr::HaveRoofAbove` (rayon vertical) au lieu de `Cover.IsUnderRoof`.

## 10. Connaissance : matériaux, stations, pièces et recettes connues (`Player`) — 2026-10-26 [PROUVÉ, CIL d'`assembly_valheim.dll`]
Extraction : `cd analysis && node rea.cjs dis Player <méthode> --stdout` (et `CraftingStation`). Une pièce du marteau ou une recette n'apparaît dans les menus que si le joueur la **connaît** ; la connaissance est définitive (ensembles enregistrés dans le profil).
- **Matériau connu** — `Player.OnInventoryChanged` (IL 50–52) appelle `AddKnownItem(item)` pour **chaque objet de l'inventaire** à chaque changement ; `AddKnownItem` (IL 22–66) ajoute `m_shared.m_name` à `m_knownMaterial` s'il n'y est pas, affiche `$msg_newmaterial` (type Material) / `$msg_newtrophy` / `$msg_newitem` (IL 86–196), puis `UpdateKnownRecipesList()` (IL 230). Posséder une fois suffit ; perdre l'objet ne l'oublie pas.
- **Station connue** — `Player.UpdateStations` (IL 0–39) : toutes les **1 s** (`m_stationDiscoverTimer > 1`), `CraftingStation.UpdateKnownStationsInRange(player)` : pour chaque station posée, si `Vector3.Distance(joueur, station) < m_discoverRange` (IL 33–60) → `Player.AddKnownStation(station)`. `m_discoverRange` = **4 m** (constructeur `CraftingStation..ctor` IL 12–17 ; même valeur dans les prefabs workbench, forge, stonecutter, artisanstation, blackforge… de `valheim_data.json`). `AddKnownStation` (IL 0–176) mémorise `m_knownStations[m_name] = GetLevel(true)` et ne met à jour que si le niveau est **supérieur** (IL 29–46), puis `UpdateKnownRecipesList()`.
- **Pièce connue** — `UpdateKnownRecipesList` (IL 180–351) parcourt les pièces des tables possédées (marteau) et appelle `HaveRequirements(piece, RequirementMode.IsKnown)` (IL 337–341 ; `RequirementMode` : CanBuild = 0, **IsKnown = 1**, CanAlmostBuild = 2). `HaveRequirements(Piece, mode)` en mode 1 : si `m_craftingStation` non nul, `m_knownStations.ContainsKey(station.m_name)` (IL 13–46, niveau indifférent) ; puis pour chaque ressource avec `m_amount > 0`, `m_knownMaterial.Contains(resItem.m_name)` (IL 201–240). Les quantités ne comptent pas.
- **Recette connue** — même méthode, IL 14–147 : pour chaque recette activée non encore connue, `HaveRequirements(recipe, discover = true, 0, 1)` : `KnowStationLevel(station.m_name, m_minStationLevel)` (IL 0–42 ; `m_knownStations[nom] >= niveau`, `KnowStationLevel` IL 0–23) puis `HaveRequirementItems(recipe, discover = true)` : chaque ingrédient (`m_amount > 0`) dans `m_knownMaterial` (IL 90–187 ; avec `m_requireOnlyOneIngredient`, un seul suffit). Connue → `AddKnownRecipe` (définitif).
- **Menus** — `UpdateAvailablePiecesList` (IL 0–51) : `PieceTable.UpdateAvailable(m_knownRecipes, …, m_noPlacementCost || clé globale 26)` → le marteau ne propose que les pièces connues, sauf triche « sans coût » (tout). Le panneau de fabrication ne liste que les recettes connues.
- **Pose / fabrication** : pas d'autre contrôle de connaissance dans Valheim : on ne choisit que ce que le menu propose, et la pose / fabrication exigent déjà les ressources en sac (donc connues) et une station à portée (celle où l'on fabrique est forcément à < 4 m, donc connue à son niveau). **Wowlheim ne bloque donc pas côté serveur** ; le filtrage est fait par l'addon avec `.build api known`. Équivalent sauf cas limite (pose à 4–10 m d'une station jamais approchée à 4 m, acceptée par le serveur).

**Wowlheim** (`server/Wowlheim/Knowledge.*`, tables `wowlheim_known_item` / `wowlheim_known_station`, `server/sql/characters/003_wowlheim_known.sql`) :
- toutes les secondes, depuis `BuildingMgr::Update`, balayage de l'équipement + sac à dos + sacs de chaque joueur connecté : tout objet 9200000–9299999 (matériaux et outils) devient connu (au lieu d'`OnInventoryChanged`, sans toucher au cœur) ; chaque `.build api known` balaie d'abord le sac ;
- stations (workbench, forge, stonecutter, artisan + les `station` du catalogue ; fonderies/fours = `Smelter`, exclus) : connues au niveau actuel (`StationLevel`) quand le joueur est à **< 4 m du bord** de l'emprise et à < 4 m verticalement (adaptation : Valheim mesure au centre ; la collision WoW tient le joueur hors de la boîte), quand il **pose** une station, l'**utilise** (clic) ou y **fabrique** ;
- `.build api known` : `[WL]K|item:<id>,<id>,...`, `[WL]KS|<kind>:<niveau>,...`, `[WL]KP|<pièce>,...` (règle IsKnown ; toutes en mode sans coût), `[WL]KR|<recette>,...` (règle discover) ; chaque liste est découpée en lignes d'au plus ~200 caractères qui répètent le préfixe (au moins une ligne, éventuellement vide) ; puis `[WL]D|known|1`. Nouveautés poussées sans demande : `[WL]KN|item|<id>` et `[WL]KN|station|<kind>|<niveau>` (équivalent de `MessageHud.QueueUnlockMsg`).

## 11. Réparation des objets à la station (`InventoryGui`) — 2026-10-26 [PROUVÉ]
- `InventoryGui.CanRepair(item)` (IL 0–234) : faux si `!m_shared.m_canBeReparied` ; **vrai** si `Player.NoCostCheat()` ; faux sans station courante ; `recipe = ObjectDB.GetRecipe(item)`, faux si nulle ou sans `m_craftingStation` ni `m_repairStation` ; accepté si `m_repairStation.m_name == station.m_name` **ou** `m_craftingStation.m_name == station.m_name` (IL 119–193), à condition que `Mathf.Min(station.GetLevel(), 4) >= recipe.m_minStationLevel` (IL 208–232) ; sinon faux (la branche `m_worldLevel` ne concerne que les objets d'anciens niveaux de monde).
- `InventoryGui.RepairOneItem()` (IL 0–332) : station courante obligatoire (sauf triche) et `CraftingStation.CheckUsable(player, false)` (abri, IL 47–69) ; parcourt `Inventory.GetWornItems` (objets usés, équipés ou non) et répare **le premier** réparable : `m_durability = GetMaxDurability()` (IL 170–177), **gratuitement**, message `$msg_repaired`, puis s'arrête (`leave`, IL 283) — un objet par clic ; sinon « No more item to repair ». `HaveRepairableItems` (IL 0–168) applique le même filtre (bouton actif).
- Données (`valheim_data.json`) : Marteau, Hache en pierre, Massue : `m_craftingStation` nul, `m_repairStation` = piece_workbench ; Hache en silex, Pioche de bois de cerf : workbench ; outils en bronze, fer… : forge.

**Wowlheim** (`Knowledge.cpp`) : réparables = objets Wowlheim (9200000–9299999) à `MaxDurability` > 0 et durabilité < max, dont la première recette `wowlheim_recipe` (par id) a `station` = type de la station, ou `station` vide et station = workbench (pas de colonne `repair_station` en base ; à ajouter dans `tools/valheim/gen_server_sql.py` pour une fidélité complète) ; `min(StationLevel, 4) >= min_station_level` ; station abritée (`StationUsable`). Station = celle du guid donné (à 10 m) ou la station de fabrication la plus proche à 10 m. Sans coût : tout objet Wowlheim usé, même sans station.
- `.build api repairable [guid]` → `[WL]RS|<guid station>|<kind>|<niveau>` puis `[WL]RI|<objet>|<durabilité>|<max>` par objet usé réparable, `[WL]D|repairable|1` ; erreur : `[WL]E|...` puis `[WL]D|repairable|0`.
- `.build api repairitems [guid]` → répare d'un coup **tous** ces objets (adaptation : Valheim, un par clic) par `Player::DurabilityRepair(pos, false)` sans coût ; `[WL]R|<objet>,<objet>,...` (vide si rien), `[WL]M|Réparé : …` ou `[WL]M|Aucun objet à réparer.`, `[WL]D|repairitems|1`.

## 12. Clic sur une station de fabrication — 2026-10-26
Valheim : `CraftingStation.Interact` → `InventoryGui.Show(station)` (panneau de fabrication). Wowlheim : `BuildingMgr::OnPieceUse` (appelé par `GameObject::Use` pour les entrées 9110000–9119999 ; les stations sont des `gameobject_template` type 10 goober, flags 0, data 0 : déjà cliquables, rien à changer dans `gen_server_sql.py`). Sans marteau, ou marteau en mode construction : fonderie / four / rouet / haut fourneau → échange `Smelter` inchangé ; station de fabrication → lignes `[WL]S|guid|utilisable|couverture%|niveau|kind` des stations à 10 m (format de `.build api station`), puis **en dernier** `[WL]OPEN|craft|<guid>|<kind>` ; la station devient connue. Marteau en mode démolir / réparer : démolition / réparation de la pièce, pas d'OPEN. Avant ce correctif, le clic sur une table ne renvoyait rien au client (le « il ne se passe absolument rien » de Robin).

## 13. Roches et filons : stats des prefabs que Valheim place réellement — 2026-10-26
Le visuel des roches vient du prefab **placé dans le monde** par Valheim (`build_assets.py`, table `VISUAL`) ; les stats viennent désormais du **même** prefab (`gen_server_sql.py`, table `ROCK_SOURCE`, fonction `build_rocks`). Les anciens `MineRock_Copper` / `MineRock_Stone` / `MineRock_Iron` (composant `MineRock`, 20–40 PV) sont des prototypes inutilisés du jeu : ils ne servent plus que de clé (entrée de créature, nom affiché `ROCK_NAMES`, type de placement de `rules.py`).

**Chaîne de Valheim** [PROUVÉ, données des prefabs] : le prefab du monde est un `Destructible` (`m_health` 1, `m_spawnWhenDestroyed` = `*_frac`) qui se brise au premier coup en un `MineRock5`. Chaque **zone** du `MineRock5` a `m_health` PV, exige `m_minToolTier`, et tire à sa destruction **sa propre** `m_dropItems` (`DropTable.GetDropList` : avec la probabilité `m_dropChance`, `Random.Range(m_dropMin, m_dropMax + 1)` tirages pondérés par `m_weight`). Zones = **colliders actifs** du prefab `*_frac` (`MineRock5.Awake` : une `HitArea` par `Collider` de `GetComponentsInChildren<Collider>()` ; les renderers « extra » enfants d'un collider ne comptent pas).

**Règle des zones atteignables** (2026-10-26, demande de la coordination : fidélité à l'expérience de jeu) : on ne compte que les zones dont le **haut dépasse le sol**. Pour chaque collider, `vh_dump.hit_areas` calcule le point le plus haut de son maillage de collision (Unity y, racine du prefab à l'origine = sol où Valheim pose le prefab) → champ `hit_area_tops` de `valheim_data.json` ; `gen_server_sql.reachable_areas` garde les zones de haut > 0. Le M2 posé ici a la même origine au sol (racine du modèle = position de la créature) et une échelle uniforme (`VISUAL` : 0,4 pour `rock4_*`, coupe à −1 m ; 1 pour `mudpile`, `silvervein`) : le signe de la hauteur, donc le test, est le même. Une zone en partie enterrée mais qui dépasse est comptée ; une zone entièrement sous le sol (atteignable dans Valheim seulement en creusant, impossible sur le terrain WoW) ne l'est pas. Jamais d'après les sommets du visuel.

| Créature (nom affiché) | Prefab du monde → fracture | Zones hors sol / total | PV / zone (`m_health`) | Palier Valheim → serveur (`m_minToolTier` + 1) | DropTable par zone (`m_dropItems`) |
|---|---|---|---|---|---|
| `MineRock_Stone` (Rocher) | `rock4_coast` → `rock4_coast_frac` | 69 / 130 | 50 | 0 → 1 | 4–8 tirages, chance 1 : Pierre (poids 0, seule entrée) |
| `MineRock_Copper` (Gisement de cuivre) | `rock4_copper` → `rock4_copper_frac` | 69 / 130 | 50 | 0 → 1 | 2–4 tirages, chance 1 : Pierre 1 / Minerai de cuivre 0,5 |
| `MineRock_Iron` (Tas de boue) | `mudpile` → `mudpile_frac` | 20 / 20 | 5 | 0 → 1 | 1 tirage, **chance 0,3** : Ferraille 1 / Os desséché 0,01 |
| `silvervein` (Veine d'argent) | `silvervein` → `silvervein_frac` | 89 / 100 | 50 | 2 → 3 | 2–3 tirages, chance 1 : Pierre 1 / Minerai d'argent 0,5 |

Hauteur du haut des zones de `rock4_*_frac` (Unity, m) : de −10,28 à 3,97 ; 69 au-dessus de 0, 64 au-dessus de 0,5, 54 au-dessus de 1 (le seuil exact compte peu). `mudpile_frac` : toutes entre 0,34 et 1,33. `silvervein_frac` : de −0,68 à 2,03.

Les autres roches (`Rock_4`, `MineRock_Tin`, `MineRock_Obsidian`) sont des `Destructible` + `DropOnDestroyed` à une seule zone (inchangées).

**Adaptation serveur** (une créature par roche, `creature_template` + `wowlheim_tree` + `wowlheim_tree_drop`) :
- PV = PV d'une zone × zones comptées / **diviseur** (zones « abattues » par coup ; le butin reste celui de **toutes** les zones comptées) :
  - **3** pour un `MineRock5` sans soutien (`m_supportCheck` 0 : `mudpile_frac`) : la pioche frappe plusieurs zones par coup (`Attack.m_multiHit`, arc de 120°) — hypothèse **[INFÉRÉ, non mesuré]** ;
  - **8** pour un `MineRock5` à soutien (`m_supportCheck` 1 : `rock4_coast_frac`, `rock4_copper_frac`, `silvervein_frac`) : multiHit + effondrement des zones qui ne sont plus soutenues. **Calage sur la durée de jeu de Valheim (≈ 60 coups pour un gisement au départ), décision de coordination du 2026-10-26, NON mesuré** dans Valheim ; à remplacer par une mesure si on en fait une.
- Tirages : `TreeMgr` tire un entier uniforme `[rolls_min, rolls_max]`. Bornes choisies (`total_rolls`) pour avoir la **même moyenne et la même variance** que la somme des zones de Valheim (zone : Bernoulli(`m_dropChance`) × uniforme `[m_dropMin, m_dropMax]`). Une seule zone avec chance 1 : bornes = `[m_dropMin, m_dropMax]` exactement.
- Poids total nul (`rock4_coast_frac`, Pierre poids 0) : dans Valheim `Random.Range(0, 0)` = 0 ≤ 0, la première entrée est toujours tirée ; le serveur ne tire rien sur un total nul → poids 1 écrit sur la première entrée (même résultat).
- Objets absents du serveur (Os desséché / `WitheredBone`) : entrée omise, son poids (1 %) revient à la Ferraille.

| Roche | Avant (SQL après le seul changement de visuel) | Toutes les zones, ÷ 3 | Zones hors sol, ÷ 3 | **Retenu : zones hors sol, ÷ 8 si soutien** |
|---|---|---|---|---|
| Rocher (9300104) | 1 zone, 20 PV, palier 1, 1–2 Pierre (avant le visuel : 24 zones, 160 PV, 24–48 Pierre) | 130 zones, 2 166 PV, 753–807 Pierre | 69 zones, 1 150 PV | **69 zones, 431 PV**, palier 1, **394–434 Pierre** (moyenne 414) |
| Gisement de cuivre (9300101) | 1 zone, 20 PV, palier 1, 1–2 tirages Pierre 1 / Minerai de cuivre 0,5 | 130 zones, 2 166 PV, 374–406 tirages | 69 zones, 1 150 PV | **69 zones, 431 PV**, palier 1, **196–218 tirages** (≈ 138 Pierre + **69 Minerai de cuivre**) |
| Tas de boue (9300102) | 14 zones (sommets du visuel), 186 PV, palier 2, 14–28 tirages Minerai de fer→Ferraille 0,5 / Pierre 1 | 20 zones, 33 PV, 3–9 Ferraille | idem | **20 zones, 33 PV (÷ 3, pas de soutien)**, **palier 1** (pioche en bois de cerf), **3–9 Ferraille** (moyenne 6), plus de Pierre |
| Veine d'argent (9300107) | 100 zones, 1 666 PV, palier 3, 200–300 tirages | 100 zones, 1 666 PV, 242–258 tirages | 89 zones, 1 483 PV | **89 zones, 556 PV**, palier 3, **215–230 tirages** (≈ 74 Minerai d'argent) |

**Durée de minage** (dégâts de pioche × [0,25 ; 0,55] au niveau 0, soit ≈ 7 par coup à la pioche en bois de cerf, ≈ 10 en bronze, ≈ 13 en fer) : rocher ou gisement de cuivre ≈ **60 coups** au début (≈ 43 en bronze), veine d'argent ≈ **43 coups** à la pioche en fer, tas de boue ≈ 5 coups. (Avec ÷ 3 : ≈ 160 coups pour un rocher, ce qui était trop long par rapport au jeu.)

Remarques : `rock4_*` mesure 24 × 28 m dont 17 m enterrés ; ici la roche est réduite (×0,4, `VISUAL`) et seules ses 69 zones hors sol sont comptées. Le butin de toutes les zones est remis d'un coup au mineur (`BuildingMgr::GiveItems`, le surplus par courrier) au lieu de tomber zone par zone.


## 14. Coffres, portes, lits (`Container`, `Door`, `Bed`) et refus en combat — 2026-10-26

Source : `analysis/valheim/dis/Container._all.txt`, `Door._all.txt`, `Bed._all.txt`, `Piece.CanBeRemoved.txt` (CIL, `node analysis/rea.cjs dis <Type> '*'`). Code : `server/Wowlheim/Pieces.cpp` ; valeurs par pièce : `wowlheim_piece_use` (gen_server_sql.py `build_piece_use`) ; état : `classiccharacters.wowlheim_container`, `wowlheim_piece_state` (`server/sql/characters/005_wowlheim_piece_use.sql`). Test : `tools/pieces_test.py` ; panneau : `tools/client/addon/Wowlheim/WowlheimPieces.lua`.

**Coffres** [PROUVÉ] — prefabs : Coffre (`piece_chest_wood`) 5 × 2, Coffre renforcé (`piece_chest`) 6 × 4, Coffre personnel (`piece_chest_private`) 3 × 2 `m_privacy` 0, Coffre en sombracier (`piece_chest_blackmetal`) 8 × 4 ; les autres `m_privacy` 2, `m_checkGuardStone` 1 (le coffre personnel 0).
- `Container.Interact` (IL 5–81) : si `m_checkGuardStone`, `PrivateArea.CheckAccess` (balise) ; puis `CheckAccess(joueur)` (IL 0–47) : `m_privacy` 0 (Private) = créateur de la pièce seulement, 1 (Group) = personne, 2 (Public) = tout le monde ; refus : « Ne peut être ouvert » (`$msg_cantopen`).
- `RPC_RequestOpen` (IL 66–150) : un seul joueur à la fois (`m_inUse`) ; sinon « Utilisé par quelqu'un d’autre » (`$msg_inuse`).
- `Piece.CanBeRemoved` → `Container.CanBeRemoved` (IL 0–25) : seul un coffre **privé non vide** refuse la démolition (« Ne peut être retiré pour l'instant », `$msg_cantremovenow`, `Player.RemovePiece` IL 283) ; un coffre public se démolit plein.
- `OnDestroyed` → `DropAllItems` (IL 0–163) : tout le contenu tombe au sol.
- `TakeAll` (« Prendre tout ») et `StackAll` (« Objets similaires »).
- **Adaptations** : (1) les balises (`PrivateArea`, `guard_stone`) ne sont pas simulées ; un coffre est traité comme protégé par la balise de son bâtisseur : **propriétaire et MJ seulement**, quel que soit `m_privacy` (un coffre public de Valheim hors balise serait ouvert à tous). (2) Contenu rendu au démolisseur (sacs), le reste par courrier au propriétaire (effondrement : tout par courrier), durabilité et liaison conservées. (3) Interface : panneau de l'addon (grille m_width × m_height), dépôt par clic droit dans les sacs comme à la banque ; pas de vrai conteneur WoW (un GameObject coffre de 1.12 ne sait que donner du butin). (4) Objets refusés (« Objet inadéquat ») : sacs, objets enchantés, temporaires, à charges entamées, avec texte, emballés (le coffre ne garderait pas cet état). (5) Coffre et sacs du joueur enregistrés dans une même transaction (ni perte ni duplication à l'arrêt du serveur). (6) Le coffre se libère quand celui qui l'a ouvert le ferme, s'éloigne (> 5 m du bord) ou se déconnecte.

**Portes** [PROUVÉ] — `wood_door`, `wood_gate`, `wood_window` (volet), `wood_fence_gate`, `iron_grate`, `darkwood_gate` : `m_keyItem` nul, `m_canNotBeClosed` 0, `m_checkGuardStone` 1.
- `Interact` (IL 0–461) : `CanInteract` (porte à clé ou `m_canNotBeClosed` : plus utilisable une fois ouverte), balise, clé (`HaveKey`, `m_consumeKey`), puis `Open(direction du joueur)` : `RPC_UseDoor` (IL 0–115) bascule `s_state` 0 → **1 si `Dot(forward, joueur − porte) < 0`, −1 sinon** (le battant s'écarte du joueur), sinon → 0. Aucun message.
- Abri : `Cover` lance ses rayons contre les colliders ; le battant ouvert (enfant animé) ne bouche plus la baie. **Adaptation** : les modèles n'ont pas d'animation ; le GameObject tourne de 90° autour de ses gonds (bout −y local, la largeur de la porte étant sur l'axe local y), pose enregistrée dans `gameobject` ; `BuildingMgr::GetCover` utilise la boîte tournée de la porte ouverte (`Geometry.cpp`), la pièce garde sa pose fermée pour les appuis et l'accroche (comme la racine du prefab dans Valheim). Balises non simulées : tout le monde peut ouvrir une porte.

**Lits** [PROUVÉ] — `bed`, `piece_bed02` (`m_monsterCheckRadius` 20).
- `Interact` (IL 0–349) : lit sans propriétaire → `CheckExposure`, puis propriétaire = joueur et point d'apparition = lit, « Point de réapparition créé » (`$msg_spawnpointset`) ; lit du joueur, pas encore point d'apparition → `CheckExposure` puis point d'apparition ; lit du joueur déjà point d'apparition → dormir (`EnvMan.CanSleep`, `CheckEnemies`, `CheckExposure`, `CheckFire`, `CheckWet`) ; lit d'un autre → rien.
- `CheckExposure` (IL 0–100) : `Cover.GetCoverForPoint(spawnPoint)` → pas de toit : « Le lit requiert un toit » ; couverture < 0,8 : « Le lit est trop exposé ». **Le feu (`CheckFire`) n'est exigé que pour dormir**, pas pour le point d'apparition.
- **Adaptations** : point d'apparition = foyer (homebind, comme une auberge, `SMSG_BINDPOINTUPDATE`) ; dormir n'est pas repris (un lit déjà point d'apparition le redéfinit) ; point testé = centre du lit, 0,5 m au-dessus de sa base (l'enfant `spawnpoint` du prefab n'est pas extrait) ; le lit lui-même est exclu des rayons ; démolir le lit ne rend pas l'ancien foyer.

**Combat** — Valheim n'interdit pas de construire en combat (aucun test dans `UpdatePlacement`, `TryPlacePiece`, `RemovePiece`, `Repair`) : **règle propre à Wowlheim**, pose (dont le fantôme `canplace`), démolition et réparation au marteau refusées si `IsInCombat()` : « Impossible en combat. » (pas de message de Valheim).

**Marteau** [PROUVÉ, prefab `Hammer`] — `m_maxDurability` 100, `m_useDurabilityDrain` 1, `m_placementDurabilityMax` 0,5 : `MaxDurability` 100 dans 012 (gen_server_sql.py vérifie que les constantes du serveur, `WLSkillMgr::WearHammer` et la réparation à −1, correspondent au prefab) ; les marteaux déjà possédés (durabilité 0 enregistrée) sont remis à 100 une seule fois (005). Réparable à l'établi (`Recipe_Hammer` sans station → `m_repairStation` = établi, §11).
