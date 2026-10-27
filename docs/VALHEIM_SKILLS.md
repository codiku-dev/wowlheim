# Compétences et endurance de Valheim — règles extraites et adaptation à Wowlheim

Source : `assembly_valheim.dll` (CIL lu avec `analysis/rea.cjs dis <Type> <Méthode> --stdout`) et prefabs Unity
(`tools/valheim/vh_dump.py` : `Player`, `AxeStone`…`AxeBlackMetal`, `PickaxeAntler`…`PickaxeBlackMetal`, `Hoe`, `Cultivator` ;
le marteau est lu à `Assets/GameElements/Items/tools/Hammer.prefab`, car le nom `Hammer` seul désigne un autre prefab, `HammerItemElement`).
Les offsets sont des offsets IL dans la méthode citée. [PROUVÉ] = lu dans le CIL ou dans le prefab ; [CONCEPTION] = proposition pour WoW.

Demande de Robin : des points de compétence comme dans Valheim (miner monte le minage, couper monte la coupe), une endurance
consommée par **tous les outils** Valheim, mais **pas par la course**. La durabilité des objets doit aussi être comparable (§5).

---

## 1. Compétences (`Skills`, `Skills.Skill`, `Skills.SkillDef`) [PROUVÉ]

### 1.1 Constantes
| Constante | Valeur | Source |
|---|---|---|
| `Skills.c_MaxSkillLevel` | 100 | champ littéral 0x040003a5 |
| `Skills.c_RandomSkillMin` | 0,4 | 0x040003a4 |
| `Skills.c_RandomSkillRange` | 0,15 | 0x040003a3 |
| `Skills.m_DeathLowerFactor` | **0,05** | prefab `Player`, composant `Skills` |
| `Skills.m_useSkillCap` / `m_totalSkillCap` | false / 500 | prefab (plafond total désactivé) |
| `Game.m_skillGainRate`, `m_skillReductionRate`, `m_staminaRate`, `m_staminaRegenRate`, `m_durabilityRate` | 1 | `Game..cctor` IL 108–193 |

### 1.2 Gain : `Skills.RaiseSkill(type, factor)` → `Skill.Raise(factor)`
- `Player.RaiseSkill(type, v)` (IL 0–42) : `v *= SEMan.ModifyRaiseSkill` (effets de statut, 1 par défaut), puis `Skills.RaiseSkill`.
- `Skills.RaiseSkill` (IL 0–191) : `type == None` → rien. `Skill.Raise(v)` ; si un niveau est gagné : `RebalanceSkills` si plafond
  (désactivé), `Player.OnSkillLevelup` (effet `m_skillLevelupEffects`), message « `$msg_skillup $skill_<nom>: <niveau entier>` »
  (centre de l'écran si l'ancien niveau entier vaut 0, coin sinon : IL 64–72), avec l'icône de la compétence.
- `Skill.Raise(v)` (IL 0–124) :
  ```
  si m_level >= 100 : return false
  m_accumulator += m_info.m_increseStep * v * Game.m_skillGainRate
  si m_accumulator >= GetNextLevelRequirement() :
      m_level = Clamp(m_level + 1, 0, 100) ; m_accumulator = 0 ; return true
  ```
  Un seul niveau par appel ; l'excédent est perdu (accumulateur remis à 0).
- `Skill.GetNextLevelRequirement()` (IL 0–39) = `0,5 · floor(m_level + 1)^1,5 + 0,5`.
- `Skill.GetLevelPercentage()` (IL 0–39) = `Clamp01(m_accumulator / GetNextLevelRequirement())` (0 au niveau 100) : la barre
  de progression du panneau des compétences.

Coût cumulé (accumulateur total pour atteindre le niveau L depuis 0, `Σ_{k=1..L} (0,5·k^1,5 + 0,5)`) :

| Niveau | 1 | 5 | 10 | 20 | 50 | 100 |
|---|---|---|---|---|---|---|
| Points (pas 1,0) = coups utiles de hache/pioche | 1 | 16,6 | 76 | 390 | 3 649 | 20 301 |
| Poses au marteau (pas 0,25) | 4 | 66 | 305 | 1 562 | 14 597 | 81 202 |

### 1.3 `SkillDef.m_increseStep` (prefab `Player`, liste `Skills.m_skills`)
Épées 1, Arcs 1,5, **Haches 1**, **Bûcheronnage (WoodCutting) 1**, Mains nues 1, Couteaux 1, Masses 1, Armes d'hast 1,
Lances 1,5, Blocage 0,5, **Pioches 1**, Saut 0,5, Discrétion 0,5, Course 0,2, Nage 0,3, Équitation 0,2, Magie élémentaire 1,
Magie du sang 1, Arbalètes 1, Pêche 0,25, Cuisine 0,25, Agriculture 0,25, **Fabrication (Crafting) 0,25**, Esquive 0,25.

Valeurs de `Skills.SkillType` : None 0, Swords 1, Knives 2, Clubs 3, Polearms 4, Spears 5, Blocking 6, **Axes 7**, Bows 8,
ElementalMagic 9, BloodMagic 10, Unarmed 11, **Pickaxes 12**, **WoodCutting 13**, Crossbows 14, Jump 100, Sneak 101, Run 102,
Swim 103, Fishing 104, Cooking 105, Farming 106, **Crafting 107**, Dodge 108, Ride 110, All 999.
**Il n'existe pas de compétence « Construction »** : le marteau utilise **Crafting (107)**, qui est aussi montée par la fabrication.

### 1.4 Niveau et facteur
- `Skills.GetSkillLevel(t)` (IL 0–47) = `floor(m_level modifié par SEMan.ModifySkillLevel)` : **niveau entier**.
- `Skills.GetSkillFactor(t)` (IL 0–27) = `Clamp01(GetSkillLevel(t) / 100)` (0 si `None`).
- `Skills.GetRandomSkillRange(min, max, t)` (IL 0–53) : `c = Lerp(0,4 ; 1 ; f)`, `min = Clamp01(c − 0,15)`, `max = Clamp01(c + 0,15)`.
  `GetRandomSkillFactor` tire uniformément dans `[min, max]` et multiplie **tous les dégâts** du coup (`DoMeleeAttack` IL 1844–1857).
  Niveau 0 : ×[0,25 ; 0,55] (moyenne 0,40). Niveau 50 : ×[0,55 ; 0,85]. Niveau 100 : ×[0,85 ; 1].

### 1.5 Perte à la mort
- `Player.OnDeath` (IL 25, 1033–1064) : si la clé globale de monde 22 (mode « perte totale ») → `Skills.Clear()` ; sinon si
  `HardDeath()` → `Skills.OnDeath()`.
- `Player.HardDeath()` (IL 0–14) = `m_timeSinceDeath > m_hardDeathCooldown` ; `m_hardDeathCooldown = 600 s` (prefab).
  Une mort moins de 10 min après la précédente ne fait rien perdre (Valheim affiche alors l'effet « pas de perte de compétence »).
- `Skills.OnDeath()` (IL 0–18) = `LowerAllSkills(m_DeathLowerFactor · Game.m_skillReductionRate)` = `LowerAllSkills(0,05)`.
- `LowerAllSkills(f)` (IL 0–119) : pour chaque compétence, `m_level −= m_level · f` (perte de 5 % du niveau, fractionnaire) et
  `m_accumulator = 0` ; message `$msg_skills_lowered`.

### 1.6 Quel outil monte quelle compétence, et de combien — `Attack.DoMeleeAttack` [PROUVÉ]
Pour chaque objet touché qui est un `IDestructible` (IL 1739–1843) :
```
skill = arme.m_shared.m_skillType
si attack.m_specialHitSkill != None et (type_destructible & attack.m_specialHitType) : skill = m_specialHitSkill ; ajouter skill à l'ensemble
sinon si (type_destructible & attack.m_skillHitType) : ajouter skill à l'ensemble
facteur de dégâts aléatoire = GetRandomSkillFactor(skill)      // la compétence qui roule les dégâts est celle-là
```
Après l'impact, **une fois par coup** (et non par objet touché), pour chaque compétence de l'ensemble (IL 3274–3343) :
`RaiseSkill(skill, m_raiseSkillAmount × (1,5 si un Character a été touché, sinon 1))`.
`DestructibleType` : None 0, Default 1, **Tree 2**, Character 4, Everything 7.

| Outil (prefab) | `m_skillType` | `m_skillHitType` | Spécial | Effet |
|---|---|---|---|---|
| Haches `Axe*` | Axes 7 | Character 4 | `m_specialHitSkill` WoodCutting 13 sur `m_specialHitType` Tree 2 | arbre/bûche/souche → **Bûcheronnage +1** par coup, dégâts roulés avec Bûcheronnage ; créature → Haches +1,5 |
| Pioches `Pickaxe*` | Pickaxes 12 | Default 1 | — | roche/minerai (Default) → **Pioches +1** par coup ; créature : rien |
| Marteau | Crafting 107 (`PieceTable.m_skill` = 107) | — | — | **Fabrication +1×0,25** par pose (§3) |
| Houe `Hoe` | None 0 | — | — | aucune compétence |
| Cultivateur | Farming 106 | — | — | Agriculture (hors périmètre) |

`m_raiseSkillAmount = 1` pour toutes ces attaques. Conséquences exactes :
- le gain a lieu **même si l'outil est d'un palier trop faible** (« `$msg_toohard` ») : l'ensemble est rempli avant l'appel
  `IDestructible.Damage` (IL 1823–1843 contre 2591) et le palier est vérifié côté cible ;
- pas de gain avec le mauvais outil (pioche sur arbre : 1 & 2 = 0 ; hache sur roche : 4 & 1 = 0 et spécial limité aux arbres) ;
- pas de gain si le coup ne touche rien.

---

## 2. Endurance [PROUVÉ]

### 2.1 Valeurs du prefab `Player` (elles remplacent celles du constructeur, `Player..ctor` IL 152–190 : 75 / 5 / 1 / 1)
| Champ | Valeur |
|---|---|
| `m_baseStamina` | **50** |
| `m_staminaRegen` | **6** /s |
| `m_staminaRegenTimeMultiplier` | 1 |
| `m_staminaRegenDelay` | **1 s** |
| `m_runStaminaDrain` / `m_sneakStaminaDrain` / `m_jumpStaminaUsage` / `m_dodgeStaminaUsage` | 8 /s, 5 /s, 10, 15 (**non repris**, voir §4) |
| `m_blockStaminaDrain` / `m_encumberedStaminaDrain` | 10 / 5 /s (non repris) |

Maximum : `Player.GetTotalFoodValue` (IL 0–65) = `m_baseStamina + Σ nourriture.m_stamina`, appliqué par `SetMaxStamina` dans
`UpdateFood` (IL 324). Sans nourriture : **50**.

### 2.2 Régénération — `Player.UpdateStats(dt)` (IL 45–281)
```
mult = 1 ; si blocage : mult = 0,8
si (nage hors du sol) ou en attaque ou en esquive ou course sur un mur, ou surchargé : mult = 0
regen = (m_staminaRegen + (1 − stamina/max) · m_staminaRegen · m_staminaRegenTimeMultiplier) · mult · SEMan.ModifyStaminaRegen
m_staminaRegenTimer −= dt
si stamina < max et m_staminaRegenTimer <= 0 : stamina = min(max, stamina + regen · dt · Game.m_staminaRegenRate)
```
De 6 /s (presque plein) à 12 /s (vide). Forme fermée (utile au serveur et à l'addon), après le délai :
`s(t) = min(M ; 2M − (2M − s0)·exp(−6·t / M))`. Avec M = 50 : de 0 à plein en 5,8 s + 1 s de délai = **6,8 s**.

### 2.3 Consommation — `Player.UseStamina(v)` / `RPC_UseStamina` / `HaveStamina`
- `UseStamina` (IL 0–94) : `v *= Game.m_staminaRate` ; `RPC_UseStamina` (IL 0–59) : `stamina = max(0, stamina − v)` et
  **`m_staminaRegenTimer = m_staminaRegenDelay`** (1 s) : chaque dépense relance le délai.
- `HaveStamina(v)` (IL 57–66) = `stamina > v` (strict).

### 2.4 Coût d'un coup d'outil — `Attack.GetAttackStamina()` (IL 0–188)
```
s = m_attackStamina (0 si ≤ 0)
f = GetSkillFactor(arme.m_shared.m_skillType)          // Haches pour une hache, PAS Bûcheronnage ; Pioches pour une pioche
s *= 1 + modificateur d'équipement (attaque, ou « home item » pour les outils de base) ; SEMan.ModifyAttackStaminaUsage
s = s − 0,33 · s · f                                   // jusqu'à −33 % au niveau 100
```
- Refus : `Attack.Start` (IL 564–613) : si `s > 0` et `!HaveStamina(s + 0,1)` → `Hud.StaminaBarEmptyFlash()` (la barre clignote)
  et **l'attaque n'a pas lieu** (pas d'animation, pas de dégâts, pas de gain, pas d'usure).
- Débit : `Attack.Update` (IL 92–120), au premier tick de l'attaque : `UseStamina(GetAttackStamina())` — **chaque coup**, qu'il
  touche ou non.

| Outil | `m_attackStamina` (primaire) | secondaire |
|---|---|---|
| AxeStone, AxeFlint | 6 | 12 |
| AxeBronze | 8 | 16 |
| AxeIron | 10 | 20 |
| AxeBlackMetal | 14 | 28 |
| PickaxeAntler | 6 | 20 |
| PickaxeBronze | 8 | 20 |
| PickaxeIron | 10 | 20 |
| PickaxeBlackMetal | 14 | 20 |
| Hammer | 5 | — |
| Hoe, Cultivator | 5 | — |

Avec 50 points : 8 coups de hache de pierre d'affilée, 6 de hache de bronze ; puis environ 1 s de délai et 1 coup par seconde environ.

### 2.5 Marteau (déjà dans `docs/VALHEIM_RULES.md` §3.1/§4.1, rappel)
- Vérification avant pose, démontage et réparation : `HaveStamina(m_attack.m_attackStamina)` (5, coût brut).
- Débit : `UseStamina(GetBuildStamina())`, `GetBuildStamina` (IL 0–96) = `s − 0,5·s·GetSkillFactor(PieceTable.m_skill = Fabrication)`.
- Pose (`UpdatePlacement` IL 1250–1292) : si `m_buildRemoveDebt > 0` → dette −1, sinon `RaiseSkill(Fabrication, 1)` (→ +0,25).
  Démontage : dette +1 (plafond 20) : démolir puis reposer ne fait pas monter la compétence.
- La fabrication à une station dont `m_craftingSkill = Crafting` monte aussi Fabrication de 1 × quantité
  (`InventoryGui.DoCrafting` IL 1761–1818).

---

## 3. Durabilité des outils (pour « une résistance comparable ») [PROUVÉ]
- `ItemData.GetMaxDurability(q)` (IL 0–34) = `m_maxDurability + max(0, q − 1) · m_durabilityPerLevel`.
- Coup d'outil : `DoMeleeAttack` (IL 3054–3140), **seulement si au moins un objet est touché** :
  `durabilité −= m_useDurabilityDrain (1) · Game.m_durabilityRate`.
- Marteau : `Player.GetPlaceDurability` (IL 0–62) = `drain − drain · m_placementDurabilityMax (0,5) · GetSkillFactor(m_placementDurabilitySkill = Fabrication)`.

| Outil | `m_maxDurability` | `+/niveau` | Coups (qualité 1) |
|---|---|---|---|
| AxeStone / AxeFlint | 100 | 30 | 100 |
| AxeBronze | 125 | 50 | 125 |
| AxeIron / AxeBlackMetal | 175 | 50 | 175 |
| PickaxeAntler | 100 | 50 | 100 |
| PickaxeBronze | 120 | 50 | 120 |
| PickaxeIron | 150 | 50 | 150 |
| PickaxeBlackMetal | 210 | 50 | 210 |
| Hammer | 100 | 100 | 100 poses (200 au niveau 100 de Fabrication) |
| Hoe / Cultivator | 200 | 200 | 200 |

Dégâts de coupe/minage (rappel) : haches 20/30/40/50/60 en `m_chop`, pioches 18/25/33/49 en `m_pickaxe`.

---

## 4. Proposition de conception pour Wowlheim [CONCEPTION]

### 4.1 Compétences suivies (par personnage)
| Id (= Valheim) | Nom affiché | Montée | Effet |
|---|---|---|---|
| 13 WoodCutting | Bûcheronnage | +1 par coup de hache Valheim sur un arbre, une bûche ou une souche (`wowlheim_tree.kind` ≠ `rock`), y compris quand le palier est trop faible | facteur des dégâts de coupe (`GetRandomSkillRange`) |
| 12 Pickaxes | Pioches (minage) | +1 par coup de pioche sur une roche ou un minerai (`kind = rock`), même palier trop faible | facteur des dégâts de minage **et** réduction d'endurance des coups de pioche (−33 % au niveau 100) |
| 107 Crafting | Fabrication | +0,25 par pose réussie (sauf dette de démontage) ; +0,25 × quantité par fabrication à une station | coût d'endurance du marteau (−50 % au niveau 100) et usure du marteau par pose (−50 %) |
| 7 Axes (option) | Haches | +1,5 par coup de hache Valheim sur une créature | réduction d'endurance des coups de hache (−33 % au niveau 100) |

Fidélité : dans Valheim, c'est la compétence **Haches** (et non Bûcheronnage) qui réduit le coût d'endurance de la hache. Deux
options pour la phase B : (a) fidèle : suivre aussi Haches, montée en frappant des créatures ; (b) simplification : appliquer
Bûcheronnage à la réduction. Recommandation : (a), c'est quatre lignes de plus et le panneau reste juste. La houe n'existe pas
ici ; le cultivateur (Agriculture) est hors périmètre.

Les noms affichés seront pris dans la localisation française du jeu (`$skill_woodcutting`, `$skill_pickaxes`, `$skill_crafting`,
`$skill_axes` via `tools/valheim/vh_loc.py`) en phase B.

Mort d'un joueur (point d'accroche : `Wowlheim_OnKill` quand `victim` est un `Player`, ou `Player::JustDied`) : si plus de 600 s
depuis la mort précédente, `level −= 0,05·level`, `acc = 0` pour chaque compétence ; message « Vos compétences ont diminué ».

Stockage (base characters) :
```sql
CREATE TABLE wowlheim_skill (
  guid INT UNSIGNED NOT NULL, skill SMALLINT UNSIGNED NOT NULL,
  level FLOAT NOT NULL DEFAULT 0, acc FLOAT NOT NULL DEFAULT 0,
  PRIMARY KEY (guid, skill));
```
Chargé paresseusement par personnage (comme `KnowledgeMgr` : `wowlheim_known_item`), écrit à chaque montée de niveau et à la
déconnexion ou périodiquement pour l'accumulateur. `last_death` en mémoire (le délai de 10 min ne survit pas à un redémarrage : acceptable).

### 4.2 Endurance « outils » séparée de WoW
- Réserve propre à Wowlheim, **indépendante de la mana, de la rage et de l'énergie**, et **jamais consommée par la course, le saut,
  la nage ni l'esquive**.
- Max = 50 (`m_baseStamina` ; pas de nourriture Valheim ici). Régénération Valheim exacte (§2.2) : délai 1 s après chaque dépense,
  puis `s(t) = min(M ; 2M − (2M − s0)·exp(−6t/M))`. Calcul **paresseux** côté serveur (stocker `s0`, `tUse` ; évaluer à la
  demande) : pas de tick par joueur. Le multiplicateur 0 « en attaque » de Valheim est ignoré (les coups automatiques de WoW
  s'enchaînent et la régénération ne reprendrait jamais) ; le délai de 1 s, relancé à chaque coup, suffit à le reproduire.
- Consommée par : coup de hache ou de pioche Valheim sur un arbre ou une roche (`GetAttackStamina`), pose, démontage et
  réparation au marteau (`GetBuildStamina`). Pas de persistance : pleine à la connexion.
- Endurance insuffisante (`stamina <= coût + 0,1` pour un coup ; `stamina <= 5` brut pour le marteau) : action refusée, aucune
  dégradation, aucun gain, ligne `EN|…|1` (clignotement de la barre) et message « Trop fatigué » limité par `TreeMgr::Warn`.

### 4.3 Points d'accroche serveur (phase B)
**`TreeMgr::AdjustMelee`** (`server/Wowlheim/TreeMgr.cpp` l. 88–130), dans la branche joueur :
1. Calculer `cost = stam·(1 − 0,33·f)` avec `stam` = `m_attackStamina` de l'outil (à ajouter à `wowlheim_tool` : 6/6/8/10/10/14 pour les
   haches, 6/8/10/10/14 pour les pioches, palier serveur → prefab de `TOOLS`) et `f` = facteur Haches (ou Bûcheronnage, option b) / Pioches.
2. Si `!HaveStamina(cost + 0,1)` : `damage = 0`, `EN|…|1`, retour (pas d'usure, pas de gain). Sinon `UseStamina(cost)`.
3. Mauvais outil : coût débité (le coup a eu lieu), ni gain ni usure (Valheim : rien n'est touché comme destructible compatible).
   Remarque : sans outil Valheim en main, rien n'est débité (la hache WoW ordinaire n'est pas un outil Valheim).
4. Bon outil (palier suffisant ou non) : `RaiseSkill(13 ou 12, 1)`, usure −1 (agent durabilité), puis, si palier suffisant,
   `skill = GetSkillFactor(13 ou 12)` à la place du `0.0f` actuel (l. 111).
5. Coup de hache Valheim sur une créature (hors arbre) : `RaiseSkill(7, 1,5)` et coût d'endurance (option a). Point d'accroche à
   ajouter dans `Wowlheim_AdjustMelee` pour les victimes non arbres.

**`BuildingMgr::PlaceFromSpell`** (`server/Wowlheim/BuildPlacement.cpp` l. 159–181) : avant `TryPlace`, `HaveStamina(5)` sinon
`E|Trop fatigué` + `EN|…|1` + `D|place|0`. Après succès (`guid != 0`) : `UseStamina(5·(1 − 0,5·f107))`, dette de démontage
puis `RaiseSkill(107, 1)`, usure du marteau `1 − 0,5·f107`. Mêmes vérification et débit dans `OnPieceUse` pour `remove`
(dette +1, plafond 20) et `repair`. Fabrication : `RaiseSkill(107, quantité)` dans le traitement de la recette (Knowledge/craft)
quand la station est un établi ou une forge (`m_craftingSkill = Crafting`).

Nouveau module proposé : `server/Wowlheim/Skills.cpp/.h` (`SkillMgr` : `GetLevel`, `GetFactor`, `Raise`, `OnDeath`,
`GetStamina`, `HaveStamina`, `UseStamina`, envoi des lignes [WL]).

### 4.4 Lignes [WL] (canal addon, `ChatHandler::SendSysMessage("[WL]" + …)`)
Préfixes libres vérifiés : déjà utilisés `A C D E I K KN KP KR KS M OPEN P R RI RS S SG SM ST T`.
| Ligne | Quand | Format |
|---|---|---|
| `EN` | à chaque dépense, à chaque refus, à la connexion | `EN|<cur>|<max>|<delayMs>|<flash>`, `cur` et `max` en dixièmes (`cur=372` ⇒ 37,2) ; `delayMs` = délai restant avant régénération ; `flash` 1 si refus |
| `SK` | à la connexion et à chaque gain | `SK|<id>|<niveau entier>|<pourcentage 0–100 vers le niveau suivant>` (`GetLevelPercentage`) |
| `SKU` | montée de niveau | `SKU|<id>|<niveau>` : l'addon affiche « Compétence améliorée : Bûcheronnage 12 » (et l'effet) |
| `SKL` | perte à la mort | `SKL|<pourcentage perdu>` (5) suivi de lignes `SK` |

L'addon simule la régénération avec la formule fermée de §2.2 entre deux `EN` (aucun envoi périodique). Commande de
resynchronisation : `.build api skills` → toutes les lignes `SK` + une `EN`.

### 4.5 Addon (`tools/client/addon/Wowlheim`)
- **Barre d'endurance** jaune (style Valheim), sous la barre de vie du joueur ou au centre-bas, visible seulement quand
  `cur < max` ou quand un outil Valheim est en main ; clignote quand `flash=1` (`Hud.StaminaBarEmptyFlash`).
- **Panneau « Compétences »** (bouton dans le menu Wowlheim) : une ligne par compétence suivie (icône, nom, niveau, barre de
  progression = pourcentage `SK`), triée comme le panneau Valheim (ordre de `Skills.SkillType`).
- Message de montée de niveau au centre de l'écran (`$msg_skillup`).

---

## 5. À vérifier en phase B
- Nom affiché exact des compétences dans la localisation française du jeu.
- Durabilité : coordonner avec l'agent qui ajoute `MaxDurability` (valeurs §3, usure −1 seulement quand un objet est touché).
- Le palier serveur 4 de `TOOLS` réutilise `AxeIron` et `PickaxeIron` : même coût d'endurance (10) que le palier 3.

---

## 6. Implémentation (phase B, 2026-10-26)
- Serveur : `server/Wowlheim/ValheimSkills.h/.cpp` (`WLSkillMgr`), accroches dans `TreeMgr::AdjustMelee` (arbres, roches, et combat avec un outil Valheim), `TreeMgr::OnKill` (mort d'un joueur), `TreeMgr::Update` (écriture des accumulateurs toutes les 30 s), `BuildingMgr::PlaceFromSpell` / `OnPieceUse` (pose, démolition, réparation), `.build craft` (Fabrication +1 à une station), `.build api skills`.
- Décision (a) : Haches réduit l'endurance de la hache et monte en frappant des créatures (+1,5 par coup qui touche ; un raté, une esquive ou une parade ne compte pas).
- Choix propres à WoW : endurance de combat avec un outil Valheim refusée = coup transformé en raté ; outil Valheim cassé (durabilité 0) = ni coup sur un arbre ni coût (Valheim refuse de l'équiper, `Humanoid.EquipItem` IL 79–106) ; régénération non suspendue pendant l'attaque automatique ; coûts d'endurance des outils codés dans `WLSkillMgr::ToolStamina` (prefabs) en attendant une colonne de `wowlheim_tool`.
- Noms affichés : Bûcheronnage (Valheim FR : « Couper du bois »), Pioches, Fabrication, Haches.
