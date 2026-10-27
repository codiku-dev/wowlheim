# Wowlheim — Contrôles du mode construction (Valheim → WoW 1.12.1)

Portée : conception des contrôles « marteau en main » (addon + serveur) et partie DLL correspondante
(`tools/client/dll/wowlheim_client.cpp`). L'addon (`tools/client/addon/*`) et le serveur (`server/Wowlheim/*`) ne sont
**pas** modifiés ici : ce document dit ce qu'ils doivent faire et dans quel ordre.

Légende comme `docs/GHOST_PREVIEW.md` : **[VÉRIFIÉ-S]** vérifié statiquement (désassemblage Ghidra 12.1.4 du projet
`C:\Wowlheim\tools\ghidra_proj`, requêtes et sorties dans `C:\Wowlheim\tools\re_work\mouseover\c*.txt` / `o*.txt`),
**[INFÉRÉ]** déduit du code, **[NON VÉRIFIÉ]** comportement en jeu. WoW.exe n'a pas été lancé pour ce travail.

---

## 1. Demande de Robin et contrôles de Valheim

Marteau équipé, on n'est plus « en combat » : les boutons de la souris servent à construire.

| Geste | Valheim (PC, défaut) | Preuve |
|---|---|---|
| Poser | clic gauche, bouton `Attack` ; maintenu : nouvelle pose toutes les `m_placeDelay` s ; **la pièce reste choisie** | `Player.UpdatePlacement` IL 841–934 (`ZInput.GetButtonDown("Attack")`, `m_placePressedTime`, `m_placeDelay`) puis `TryPlacePiece` IL 1112, `BuildUi.AddRecentPiece` IL 1138 |
| Détruire la pièce visée | **clic milieu**, bouton `Remove` (appui puis relâché) | IL 204–314 (`GetButtonDown("Remove")` … `GetButtonUp("Remove")`), `Player.RemovePiece()` IL 627 / 1059 |
| Menu de construction | **clic droit** (`BuildMenu`, géré par le HUD) | lecture de `Hud` (chaînes `$hud_nothingtobuild`…) ; non extrait du CIL ici |
| Tourner la pièce | **molette** (`ZInput.GetMouseScrollWheel`, IL 1583 → `m_placeRotation` ± 1, pas de 22,5°) ; manette : `JoyRotate` | IL 1583–1944 |
| Réparer | outil « Réparer » choisi dans le menu, puis clic gauche | `Player.Repair` IL 1036 |

`RemovePiece` (docs/VALHEIM_RULES.md) : rayon depuis la caméra, point touché à **< `m_maxPlaceDistance` = 5 m de l'œil**,
`Piece.m_canBeRemoved`, zone privée, `CheckCanRemovePiece` (station requise à portée), `CanBeRemoved()` (conteneur vide),
puis `WearNTear.Remove` avec **remboursement**.

---

## 2. Correspondance dans WoW 1.12 (sans action protégée)

Contrainte constatée en jeu : le clic droit du monde est **protégé** — remplacer `TurnOrActionStart` / `TurnOrActionStop`
(liaison `BUTTON2 TURNORACTION`) ne marche pas. Liaisons d'origine (`tools/client/extracted/WTF/DefaultBindings.wtf`) :
`BUTTON1 CAMERAORSELECTORMOVE`, `BUTTON2 TURNORACTION`, **`BUTTON3 MOVEANDSTEER`** (le clic milieu n'est **pas** libre :
il fait avancer en dirigeant), `BUTTON4 TOGGLEAUTORUN`, `MOUSEWHEELUP/DOWN CAMERAZOOMIN/OUT`,
`SHIFT-MOUSEWHEELUP/DOWN` page de barre d'action.

Principe : **en mode construction, le ciblage au sol du sort de pose 40001 est actif en continu.** Tout le reste en découle.

| Geste | Mécanisme WoW | Détail |
|---|---|---|
| **Poser (clic gauche)** | natif : clic gauche pendant le ciblage → `Spell_C_HandleTerrainClick` `0x6e60f0` → sort 40001 avec destination | Le fantôme natif suit déjà la souris (GHOST_PREVIEW §1). Après la pose (`D|place|1` ou `SPELLCAST_*`), l'addon relance `UseInventoryItem(16)` : **la pièce reste choisie** (déjà fait : « pose continue »). |
| **Menu (clic droit)** | natif : un clic droit pendant le ciblage **annule** le ciblage (`0x492c20`, bouton 4 → annulation ; seul l'effet 81 « maison » tourne de π/2 à la place, `0x6e69e0`). L'addon **détecte « ciblage terminé sans pose »** et rouvre le menu. | Détection (OnUpdate) : `SpellIsTargeting()` passe de vrai à faux ; si dans les ~0,3 s suivantes ni `SPELLCAST_START/STOP/FAILED` ni ligne `D|place|…` n'arrive, et qu'Échap n'a pas été pressé (surcharge existante de `ToggleGameMenu`), c'est un clic droit ⇒ **ouvrir le menu, garder la pièce choisie, ne pas relancer le ciblage**. Choisir une pièce dans le menu relance le ciblage. Aide optionnelle : `IsMouseButtonDown("RightButton")` au moment de la transition [NON VÉRIFIÉ en 1.12]. Aucune surcharge de `TurnOrAction*`. |
| **Détruire (clic milieu)** | liaison **`BUTTON3` → action d'addon `WOWLHEIM_REMOVE`** posée **seulement marteau équipé** (`SetBinding` sans `SaveBindings`, valeur précédente mémorisée par `GetBindingAction("BUTTON3")` et remise au déséquipement / à la sortie du mode construction / à `PLAYER_LEAVING_WORLD`). | Le gestionnaire appelle `WowlheimGetMouseoverObject()` (§3) ; si `entrée` ∈ 9110000–9119999 il envoie `.build api removeguid <guidHex>` ; sinon message « Rien à démolir ». Le ciblage au sol reste actif (pas besoin de l'annuler : l'API refait elle-même le lancer de rayon avec les gameobjects). Sans DLL : repli sur `.build api remove` (pièce la plus proche à 6 m, existant). |
| **Tourner (molette)** | liaisons temporaires `MOUSEWHEELUP` / `MOUSEWHEELDOWN` → `WOWLHEIM_ROTATE_RIGHT/LEFT` marteau équipé (comme Valheim : la molette ne zoome plus pendant la construction), restaurées au déséquipement ; `CTRL-MOUSEWHEEL*` reste lié (existant). | Rotation : `WowlheimSetPlaceFacing(r)` (fantôme natif) + `.build api select <id> <rot>` (serveur). Les liaisons s'appliquent même pendant le ciblage [NON VÉRIFIÉ pour la molette sur le WorldFrame en ciblage]. |
| **Tourner (Q / E)** | **option** (désactivée par défaut) : liaisons temporaires `Q`/`E` → rotation. En WoW, Q/E (QWERTY) sont les pas latéraux ; en AZERTY la touche A tourne. Les garder par défaut : Alt+A / Alt+E (existant). | `/wl qe on` pour l'activer (proposé). |
| **Réparer / Démolir (outils du menu)** | inchangé (mode serveur `remove`/`repair`, clic droit sur la pièce = utilisation du gameobject). | En mode Démolir/Réparer le ciblage au sol n'est pas actif : le clic droit garde son sens WoW. |
| **Sortie du mode** | Échap (surcharge `ToggleGameMenu`), déséquiper le marteau. | Restaure BUTTON3 / molette / Q-E. |

Pourquoi c'est sûr côté « actions protégées » : on n'appelle aucune fonction protégée ; on **change des liaisons** de
touches (autorisé hors combat en 1.12, `SetBinding`) et on **réagit** à l'annulation native du ciblage. Le relancement de
`UseInventoryItem(16)` depuis un `OnUpdate` (sans événement matériel) est déjà utilisé par la pose continue et reste
[NON VÉRIFIÉ] en jeu (README_ADDON).

---

## 3. DLL : `WowlheimGetMouseoverObject()`

```
guidHex, entree, guidLo, guidHi, x, y, z = WowlheimGetMouseoverObject()
-- guidHex : 16 chiffres hexadécimaux majuscules "HHHHHHHHLLLLLLLL" (GUID 64 bits du gameobject)
-- entree  : OBJECT_FIELD_ENTRY (9110000+ pour une pièce)
-- x, y, z : point touché sur le modèle
-- nil si aucun gameobject sous le curseur, souris hors du monde, ou API inactive
```

### 3.1 Où le client calcule l'objet sous la souris [VÉRIFIÉ-S]

| Adresse | Rôle | Preuve |
|---|---|---|
| `0x481790` `CGWorldFrame::OnLayerUpdate` | par image : `r = 0x481190(x, y, &hit)` ; `r==1` → `0x4820f0` (sol) ; `r==2` → **`0x4828d0(&hit)`** (objet) ; sinon `0x482090(0,0)` | décompilation (`o1.txt`) |
| `0x481190` lancer de rayon | `__thiscall(worldFrame, x, y, hit*)`, `RET 0xc` ; masque = **`0x481050()`** (appel en **`0x4812c1`**) ; écrit `hit+0x18` début et `hit+0x24` fin du rayon ; `r = 0x480df0(début, fin, masque, hit)` ; si `r ≥ 2` **`[wf+0x348..0x34c] = GUID`**, sinon `0x480990(wf+0x320)` et `[wf+0x348]=0` | décompilation + désassemblage `0x4812c1..0x48136f` (`o2/o5`) |
| `0x480df0` | `0x672170` (TraceLine terrain/WMO) puis, si `masque & 0x7c`, `0x480a50` (objets) ; l'objet gagne s'il est **plus proche que le terrain** ; renvoie 2 avec **`hit+0` = GUID (64 bits)**, `hit+8` point, `hit+0x14` distance | décompilation |
| `0x480a50` | parcourt la liste des `AUCModelRecord` de `wf+0x31c` (GUID en `+0x18`), filtre par **`0x480780(rec, masque)`**, ajoute chaque modèle au test (`0x480d90` → `0x713cb0(1,…)`), puis `0x7089c0` = intersection rayon / **triangles affichés** du M2 ; renvoie le GUID (`RET 0x14`) | décompilation `o1/o4`, fin `0x480c83 MOV EAX,[ECX+0x18]; MOV EDX,[ECX+0x1c]; RET 0x14` |
| `0x480780` filtre | type `[[obj+8]+8]` : `9` unité (masque & 8), `0x19` joueur (& 0x10), **`0x21` gameobject (& 4)**, `0x81` cadavre (& 0x40) ; **gameobject pendant un ciblage : accepté seulement si `0x6e62e0` (`[0xcecac0] & 0x4800`, sort qui vise un objet)** | décompilation (`o2.txt`) |
| `0x481050` masque | hors ciblage : `0x5c` (+1/3 selon l'état) → **gameobjects inclus** ; **pendant un ciblage** : `3` si `[0xcecac0] & 0x60` (destination au sol), `|4` seulement si `& 0x4800` ⇒ **pour le sort 40001 (`Targets = 0x40`) aucun objet n'est testé** | décompilation (`o3.txt`), `0x6e6320`, `0x6e62d0` |
| `0x4828d0` (cas objet) | joueur absent / `vtable+0x54` nul ⇒ `0x482090(0,0)` ; sinon curseur selon le type (`0x21` → `0x4826e0`, curseur d'interaction `0x5f8760`) ; puis **`0x482090(guid)` → `[wf+0x340..0x344]` = objet survolé** (change → `0x492e70`) | décompilation |
| `0xb4b2bc` | **`CGWorldFrame*`** : écrit par le constructeur `0x481960` (qui initialise aussi `+0x31c`), remis à 0 par `0x481d30` (destructeur) ; lu par `0x514810` → `0x481f00`, qui **appelle `0x481190` hors de l'image** (`hit` en `wf+0x358`) | xrefs (`o19.txt`, `o6.txt`) |
| `0x464870` | `ClntObjMgrObjectPtr(guidLo, guidHi)` `__stdcall`, `RET 8` → `CGObject_C*` (table de hachage `[0xb41414]`, `0x464890`) | octets `558bec8b45088b4d0c…c20800` |
| descripteurs | `obj+8` → `+0` GUID, `+8` `OBJECT_FIELD_TYPE` (0x21 = gameobject), `+0xc` `OBJECT_FIELD_ENTRY` | utilisés par `0x480780`, `0x482200`, `0x5f7c40` (`puVar1[3]` = entrée pour la requête du cache `0x558560`) |

**Réponses aux questions :**

- *Où est stocké l'objet touché ?* `hit+0` (GUID) dans le tampon passé au rayon, recopié dans **`[[0xb4b2bc]+0x348]`**
  (dernier objet touché par le rayon) ; l'**objet survolé « officiel »** (curseur, info-bulle) est **`[[0xb4b2bc]+0x340]`**,
  mis à jour seulement si l'objet est interactif (`vtable+0x54`) — une pièce non utilisable n'y apparaît pas.
- *Les GameObjects sans collision ?* Le test objet n'utilise **pas** la collision : `0x7089c0` (mode 1, posé par
  `0x480d90`) teste les **triangles affichés** du M2 (lots de la vue, os appliqués), en sautant les lots invisibles
  (drapeau `& 8`, alpha 0). Un `.m2` sans maillage de collision est donc sélectionnable [VÉRIFIÉ-S]. Sont exclus : un modèle
  pas encore chargé ou hors de la liste `wf+0x31c` (objets rendus, alimentée par `0x481540` → `0x4815d0`) [INFÉRÉ] et un
  objet caché par le terrain/WMO (comparaison de distance dans `0x480df0`).
- *Le vrai obstacle* : **pendant le ciblage au sol, le client ne teste aucun gameobject** (masque `0x481050` + filtre
  `0x480780`). Le mouseover natif est donc vide en mode construction.

### 3.2 Implémentation

- Le hook par image existant (`0x48184a` → `Hook_WorldRaycast`) mémorise les `x, y` déjà convertis passés à `0x481190`.
- Nouveau hook **`0x4812c1`** (`CALL 0x481050` → `Hook_PickMask`) : renvoie le masque d'origine, sauf pendant notre
  appel où il renvoie **4** (gameobjects seulement ; sans le bit 1 le terrain sert uniquement à l'occultation).
- `WowlheimGetMouseoverObject()` : `wf = [0xb4b2bc]` ; sauvegarde de `[0xcecac0]`, mise à 0 (le filtre `0x480780` accepte
  alors les gameobjects), masque forcé à 4, **appel de `0x481190(wf, x, y, hit)`** (comme `0x481f00`), restauration
  immédiate ; si `r == 2` : GUID = `hit+0`, objet = `0x464870(GUID)`, type `0x21` exigé, entrée = `desc+0xc`.
  Effets de bord identiques à une image native sans objet / avec objet (`wf+0x348`, `0x480990`), recalculés à l'image suivante.
- Garde-fous : groupe de signatures 3 (`0x4812c1`, `0x481050`, `0x6e48a0`, `0x464870`) + groupe 1 (rayon, Lua) ;
  `__try/__except` (désactivation au lieu d'un plantage).

---

## 4. DLL : apparition instantanée des pièces et préchargement (délai ressenti à la pose)

Le serveur envoie la création en 29–70 ms ; le retard vient du client.

### 4.1 Le fondu d'apparition [VÉRIFIÉ-S]

| Adresse | Rôle |
|---|---|
| `0x614f80` `CGObject_C::SetAlphaTarget(cible, durée_ms)` | `+0xec` = début (`0x42b790`, ms), `+0xf0` = durée, `+0xf8` = départ (= courant), `+0xfc` = cible ; durée 0 ⇒ `+0xf4` (courant) = cible |
| `0x613af0` (init., `RET 0xc`) et `0x614640` (réapparition) | **durée = `vtable+0x68()` ? 2000 : 0** (`AND EAX,0x7d0` en `0x613b0d` / `0x614677`), cible = `vtable+0x6c(durée)` |
| `0x614a90` (mise à jour par image, vtable) | si `+0xf0` ≠ 0 : `t = écoulé / durée`, **courant = départ + (cible − départ) · t³** ; alpha du modèle = `+0x100 × courant` (`0x710cb0`) |
| appelants | `0x5f7c40` **CGGameObject_C** (appel en `0x5f7c6b`, appelé par la création d'objet `0x465c50`), `0x5fb880` CGUnit_C (`0x5fb956`), `0x5f7e80` GO (`0x5f7e83`) et `0x5fbd60` unité (`0x5fbd67`) pour la réapparition |

Courbe t³ sur 2 s : 1,6 % d'opacité à 0,5 s, 12,5 % à 1 s, 42 % à 1,5 s ⇒ la pièce **paraît apparaître ~1 s après**.

**Option DLL** : les 4 `CALL` sont redirigés vers `Hook_ObjInitFade` / `Hook_ObjReshowFade` qui appellent l'original puis,
si l'objet est un gameobject (type `0x21`) d'entrée **9110000–9119999** ou une unité (type `0x09`) d'entrée
**9300000–9300099**, terminent le fondu (`+0xf0 = 0`, `+0xf4 = +0xfc`, état de `SetAlphaTarget(cible, 0)`). Actif par
défaut ; `WowlheimSetInstantFade(goMin, goMax [, unitMin, unitMax])` change les plages, `WowlheimSetInstantFade(0)` le coupe,
`WowlheimSetInstantFade()` renvoie `1, goMin, goMax, unitMin, unitMax` (ou `nil` si inactif).

La **disparition** utilise un autre mécanisme (fondu du modèle détaché, 2000 ms) : traitée au §4.3. Les ramassables de
Valheim (gameobjects **9130000–9139999**) sont couverts aussi (5ᵉ/6ᵉ arguments, défaut 9130000–9139999).

### 4.2 Chargement du modèle et préchargement

- La création du modèle d'un gameobject attend le **cache gameobject** (`0x558560` dans `0x5f7c40` : requête
  `CMSG_GAMEOBJECT_QUERY` si l'entrée est inconnue, modèle créé dans le rappel). En mode construction ce cache est déjà
  rempli par le ciblage du sort 40001 (le fantôme natif interroge la même entrée, GHOST_PREVIEW §1) [INFÉRÉ].
- Fichier M2 : `0x707350` `CM2Scene::CreateModel(chemin, drapeaux)` (`__thiscall`, `RET 8`) → `0x706a50` cherche le
  `CM2Shared` dans une table de hachage par nom (`scene+4`, 0x3fd seaux) et ne lit le fichier que s'il est absent ;
  le modèle se charge ensuite (`CM2Model+0x10` ≠ 0 quand prêt). `0x71d480` : à la dernière référence, le `CM2Shared`
  part dans une liste « récents » datée au lieu d'être détruit.
- Scène M2 du monde : **`[0xc7b298]`** (créée au démarrage par `0x66f6c0`, détruite à l'arrêt par `0x66fb00` **après**
  `0x6920c0`, donc après notre hook `0x6920cc`) ; `0x695100` l'utilise ainsi : `MOV ECX,[0xc7b298]; CALL 0x707350`.
- **`WowlheimPreloadModel(chemin)`** crée un `CM2Model` (`0x707350` sur `[0xc7b298]`, drapeaux 0, jamais affiché) et le
  garde : le `CM2Shared` reste chargé, la pose suivante n'attend plus le disque. Doublons ignorés (512 max).
  `WowlheimPreloadModel()` libère tout (`0x7103a0` `CM2Model::Release`) ; libération automatique au déchargement de la
  carte (hooks `0x697ac0`). L'addon appelle le préchargement à l'équipement du marteau (après `PLAYER_ENTERING_WORLD`) pour
  les modèles du catalogue (`WowlheimData`), par lots de ~10 par image pour ne pas figer l'écran.

### 4.3 Disparition instantanée (pièce démolie, ramassable ramassé, arbre abattu) [VÉRIFIÉ-S]

Valheim : `WearNTear.Destroy` / `Pickable` → `ZNetScene.Destroy` ; l'objet disparaît à l'image suivante (avec l'effet de
destruction `m_destroyedEffect`). Dans le client 1.12 la pièce s'effaçait en ~2 s :

| Adresse | Rôle |
|---|---|
| `0x4674a0` | gestionnaire de `SMSG_DESTROY_OBJECT` (`0xaa`, enregistré en `0x46518c` par `0x537a60`) → `0x464920` (« Forgetting game object… ») → **`vtable+4` = Disappear** de l'objet, puis libération de l'objet |
| `0x6145e0` `CGObject_C::Disappear` (vtable `0x803640`+4) | `PUSH ESI ; MOV ESI,ECX` ; si `[obj+0xe0]` (def du modèle du monde) : `vtable+0x3c(0)`, puis **`0x672df0(def, alpha courant [obj+0xf4])`** (`CALL` en **`0x614603`**), `[obj+0xe0] = 0`, alpha = 0, drapeau `+0xe4 \|= 1` ; `CGGameObject_C` `0x5f7e40` y saute (`JMP` en `0x5f7e5b` / `0x5f7e7a`) |
| `0x5fbe80` (CGUnit_C, appelé en `0x5fbc8b`) | même chose pour les créatures : `0x672df0([obj+0xe0], [obj+0xfc])` (`CALL` en **`0x5fbf30`**), sinon `0x671ac0` direct |
| `0x672df0` `ModelFadeout(def, alpha)` (`__thiscall`, `RET 4`) | si le `CM2Model` (`def+0x88`) est chargé et **alpha ≥ 0.01** (`FCOMP [0x8029d0]` en `0x672e1e`) : alloue un « `SWModelFadeout` » {def, début, alpha} accroché à la liste `[0xc7b2d4]/[0xc7b2d8]` ; **sinon `0x671ac0(def)` = libération immédiate** |
| `0x672ef0` (chaque image) | pour chaque entrée : écoulé > **2000 ms** (`CMP EAX,0x7d0` en `0x672f36`) → `0x671ac0` ; sinon alpha = a₀·(1−t) lissé, `0x710cb0` |

**Option DLL** (`Stub_ModelFadeout` / `Hook_ModelFadeout`, groupe de signatures 6) : les deux `CALL 0x672df0` (`0x614603`,
`0x5fbf30`) appellent un relais `naked` qui recopie `ESI` (= l'objet : `MOV ESI,ECX` en tête des deux fonctions, ESI
préservé jusqu'au `CALL`) puis saute dans `Hook_ModelFadeout(def, edx, alpha)` : pour un objet des plages Wowlheim
(mêmes plages que l'apparition : pièces 9110000–9119999, ramassables 9130000–9139999, créatures 9300000–9300099),
**alpha = 0** → `0x672df0` prend sa propre branche « déjà invisible » et libère le modèle tout de suite (`0x671ac0`),
exactement comme pour un objet transparent. Aucun autre objet n'est touché. Journal : `disparition instantanee :
gameobject entree …`. `WowlheimSetInstantFade()` renvoie maintenant `1, goMin, goMax, unitMin, unitMax, pickMin, pickMax,
disparition(1/nil)` ; `WowlheimSetInstantFade(0)` coupe apparition et disparition.

Non fait : l'**effet de destruction** de Valheim (particules + son `sfx_*_destroyed`) — il faudrait un sort/visuel ou un
son du patch client joué par le serveur à la démolition (`TryRemoveByPlayer`).

---

## 5. Serveur : `.build api removeguid <guidHex>`

À ajouter dans `server/Wowlheim/BuildCommands.cpp` (même table que `.build api mode`), par un agent serveur :

1. Analyse : 16 chiffres hexadécimaux → `uint64` → `ObjectGuid`. Refus si ce n'est pas un gameobject
   (`HIGHGUID_GAMEOBJECT`) ou si `GetEntry()` ∉ 9110000–9119999. La pièce = `GetCounter()` dans `sBuildingMgr.Pieces()`
   (même guid que `WLPiece::guid`) ; vérifier que son entrée correspond (pas de pièce d'un autre type au même compteur).
2. Même carte (`piece.map == player->GetMapId()`) et **distance** : `DistToPiece2D(piece, x, y) ≤ 8 m` (Valheim
   `m_maxPlaceDistance` = 5 m de l'œil au point visé) et écart vertical ≤ 8 m ; sinon `E|Trop loin.`.
   **Portée 8 m** au lieu des 5 m de Valheim : la caméra de WoW est plus loin derrière le personnage. La même portée vaut pour la pose (`PlaceFromSpell` : `E|Trop loin.`).
3. **Mêmes contrôles que le clic en mode Démolir** (`BuildingMgr::OnPieceUse`, branche `remove`) : propriétaire (sauf MJ),
   `CheckStation` (Player.CheckCanRemovePiece), puis `Remove(guid, map, err, false, refund ? player : nullptr)` avec
   remboursement. Le mieux : extraire cette branche en `BuildingMgr::TryRemoveByPlayer(player, guid, err)` partagée par
   `OnPieceUse` et `removeguid`.
4. Réponses : `M|<nom> démolie.` + `D|removeguid|1`, ou `E|<raison>` + `D|removeguid|0`. Le mode du marteau n'est pas
   changé (on reste en construction).

---

## 6. Ordre d'implémentation dans l'addon

1. **Ciblage continu** : marteau équipé + mode construction + pièce choisie ⇒ ciblage relancé après chaque pose
   (existe) et à la fermeture du menu par choix d'une pièce.
2. **Clic droit = menu** : détection « ciblage terminé sans pose » (§2) ; supprimer la surcharge de
   `TurnOrActionStart/Stop` (inefficace) ; le menu s'ouvre sans relancer le ciblage ; choisir une pièce relance.
3. **Liaisons temporaires** : à l'entrée en mode construction mémoriser `GetBindingAction` de `BUTTON3`,
   `MOUSEWHEELUP`, `MOUSEWHEELDOWN` (et `Q`/`E` si l'option est active), poser `WOWLHEIM_REMOVE` /
   `WOWLHEIM_ROTATE_RIGHT/LEFT` par `SetBinding` **sans `SaveBindings`** ; restaurer à la sortie (déséquipement, mode
   Démolir/Réparer, `PLAYER_LEAVING_WORLD`, `/wl` reset). Déclarer les actions dans `Bindings.xml`.
4. **Clic milieu** : `WOWLHEIM_REMOVE` → `WowlheimGetMouseoverObject()` → `.build api removeguid <guidHex>` (file
   `ChannelRoute`, réponse `D|removeguid|…`) ; sans DLL, repli `.build api remove`.
5. **Molette** : rotation (`WowlheimSetPlaceFacing` + `select <id> <rot>`), molette sur le menu inchangée.
6. **Préchargement** : `WowlheimPreloadModel` sur les modèles du catalogue à l'équipement du marteau ;
   `WowlheimSetInstantFade` n'a rien à faire (actif par défaut).
7. Tests `test_core.py` : simuler la transition `SpellIsTargeting` vrai→faux sans `D|place` (menu), avec (`pose
   continue`), Échap (fin), les liaisons posées / restaurées, et `WowlheimGetMouseoverObject` simulé.

---

## 7. Vérifié / non vérifié

**Vérifié statiquement** : toutes les adresses des §3–4 (sorties `C:\Wowlheim\tools\re_work\mouseover\o1..o19.txt`) ;
`python tools/client/dll/verify_addrs.py` : 41 motifs (dont les nouveaux groupes survol / fondu / préchargement) et 12 sites
`CALL/JMP rel32` (dont `0x4812c1`, `0x5f7c6b`, `0x5fb956`, `0x5f7e83`, `0x5fbd67`) correspondent dans
`C:\Wowlheim\client_test\WoW.exe` ; compilation `build.bat` sans avertissement (aussi en `/W4`), `wowlheim_client.dll`
130 560 octets ; code généré : `Hook_ObjInitFade` `ret 12`, `Hook_ObjReshowFade` et `Hook_PickMask` `ret 0`.
14 trampolines : les deux caves sont pleines (une nouvelle API Lua demandera une 3ᵉ cave).

**Non vérifié (aucune exécution)** : que l'appel de `0x481190` depuis un gestionnaire de liaison renvoie bien la pièce
sous la souris pendant le ciblage (mise à 0 temporaire de `[0xcecac0]`) ; que BUTTON3 déclenche une liaison d'addon
pendant un ciblage au sol ; que le clic droit annule bien le ciblage de l'effet 76 ; que l'apparition soit visuellement
instantanée (le modèle peut encore attendre son chargement) ; que le `CM2Model` préchargé hors monde ne soit jamais rendu
et ne gêne pas la scène ; Warden : 5 nouveaux sites de `CALL` modifiés (même analyse de risque que CLIENT_PATCH §4).

Test en jeu proposé : `/script print(WowlheimGetMouseoverObject())` souris sur une pièce, avec puis sans ciblage du marteau ;
`/script print(WowlheimSetInstantFade())` ; poser une pièce (apparition immédiate ; journal `apparition instantanee …`) ;
`/script print(WowlheimPreloadModel("World\\Wowlheim\\woodwall.m2"))` (journal `modele precharge`), puis `.tele` vers
un autre continent (journal `… modele(s) precharge(s) libere(s)`), pas de plantage.

---

## 8. Implémentation (2026-10-26)

- **Serveur** : `.build api removeguid <guidHex>` (`server/Wowlheim/BuildCommands.cpp`, `Wowlheim_RemoveGuidCommand`) ; la
  branche « démolir » de `OnPieceUse` est extraite en `BuildingMgr::TryRemoveByPlayer` (endurance, propriétaire, station,
  remboursement, dette de démolition, usure du marteau), partagée par les deux. Distance : horizontale au bord de la pièce
  ≤ 8 m et écart vertical entre la boîte de la pièce et le personnage (pieds … +2 m) ≤ 8 m ; marteau en main exigé.
  `.build api models` → `MD|id:prefab,…` : chemins des modèles pour le préchargement (WowlheimData n'a pas les prefabs).
  Test protocole : `tools/hammer_test.py`.
- **Addon** : comme §2 / §6 (`WowlheimCore` : `TempBind*`, `TargetWatch*`, `RemoveCommand`, `ModelsOnMessage`,
  `PreloadList` ; `Wowlheim.lua` : `WatchTargeting`, `UpdateBuildKeys`, `RemoveUnderMouse`, `QueuePreload`). Écarts :
  un refus de pose (`D|place|0`, `E|`) ou `SPELLCAST_FAILED` relance aussi le ciblage (sinon, sans ciblage, le clic droit
  redeviendrait la caméra) ; la molette n'appelle pas `WowlheimSetPlaceFacing` (orientation absolue : il faudrait
  l'orientation du joueur, absente de l'API Lua 1.12). Tests : `tools/client/addon/test_core.py`.
- **Pose en chaîne sans état mort (2026-10-26, captures p2/112-118)** : un `UseInventoryItem(16)` de relance qui ne
  donnait pas de ciblage était abandonné en silence après 1 s (`TargetWatchUpdate`) : bandeau « Pièce - Rotation » affiché,
  aucun fantôme, clic gauche sans effet, info-bulle de survol, Échap ouvrant le menu du jeu. Désormais : nouvelle tentative
  après `ARM_TIMEOUT` (0,5 s), menu (pièce gardée) après `ARM_RETRIES` (3) échecs de suite ; une pose vue
  (`SPELLCAST_*`) sans réponse du serveur relance après `PLACE_WAIT` (2 s) ; le verdict `canplace` est oublié à chaque
  relance (`GhostCheckReset`). Échap en mode pose (pièce choisie, pose continue) quitte toujours la pose, même entre deux
  ciblages, sans menu du jeu (menu du marteau ouvert : il est fermé). Survol (surbrillance, info-bulle) seulement si
  `GetMouseFocus()` est `WorldFrame` (ou nil). `/wl debug` affiche chaque relance / retour au menu décidé par la surveillance.

---

## 9. Surbrillance de la pièce visée (Valheim `WearNTear.Highlight`)

**Valheim** (CIL extrait, `analysis/valheim`) : `Player.UpdateWearNTearHover` (en mode construction, tous outils) lance un
rayon depuis la caméra (50 m, `m_removeRayMask`), garde la pièce si le point est à moins de `m_maxPlaceDistance` de l'œil
et appelle `WearNTear.Highlight()` : couleur = `GetSupportColorValue()` (support normalisé 0..1, **−1 si le support est
complet** → bleu clair `(0.6, 0.8, 1)`), sinon `Lerp(rouge, vert, v)` puis HSV avec saturation `Lerp(1, 0.5, v)` et
valeur `Lerp(1.2, 0.9, v)` ; `_Color` = couleur, `_EmissionColor` = couleur × 0.4 ; remis à l'origine 0,2 s après le
dernier appel (`Invoke("ResetHighlight", 0.2)`). Le HUD affiche le nom de la pièce près du viseur.

**Client 1.12** [VÉRIFIÉ-S] : le `CM2Model` d'un objet est `[obj+0xdc]`, sinon `[obj+0xd8]` (même choix que `0x614a90`,
`0x6144f0`) ; `+0x184` = couleur diffuse multipliée (`0x710cf0`), `+0x190` = couleur émissive ajoutée (`0x710d40`). Pour un
gameobject, le client n'écrit ces champs que dans `CGObject_C::SetHighlight(bit)` `0x614550` / `ClearHighlight(bit)`
`0x6144f0` (masque `[obj+0xb8]` : survol natif `0x4945ec`, cible `0x493701` ; vide ⇒ émissif remis à 0).

**DLL** (groupe de signatures 7, exige le survol du groupe 3) : `WowlheimHighlightObject(guidHex, r, g, b [, lueur=0.4])`
→ `1` / `nil` ; `WowlheimHighlightObject()` retire. L'objet est retrouvé à chaque appel par son GUID
(`ClntObjMgrObjectPtr 0x464870`), diffuse = (r,g,b), émissif = (r,g,b) × lueur ; les valeurs d'origine sont gardées à la
première application et remises quand la souris quitte la pièce (émissif 0 si le masque natif est vide), au
rechargement de l'interface (`Hook_InitLua`) ; rien n'est remis au déchargement de la carte ni si l'objet a été détruit
ou son modèle remplacé. Nouvelle API ⇒ 15ᵉ trampoline : `MakeTrampoline` parcourt maintenant 5 caves (`0x75d401`,
`0x75f048`, puis **`0x755d16`, `0x755dd6`, `0x755e96`** : 40 octets `0xCC` chacune entre deux fonctions, après un `RET`),
soit 29 places.

**Addon** (`WowlheimCore` : `HoverWanted`, `HoverTipWanted`, `HighlightColor` (formule Valheim), `HoverTip`, `RGBToHSV`,
`HSVToRGB` ; `Wowlheim.lua` : `WL.UpdateHover` à chaque image, `WL.HoverClear`, `WL.ShowHoverTip`) : marteau équipé, dans
les trois modes, la pièce Wowlheim sous la souris (`WowlheimGetMouseoverObject`) est mise en surbrillance bleu clair
(réappliquée à chaque image, retirée dès que la souris la quitte) ; en modes **Démolir / Réparer**, info-bulle
`WowlheimHoverTip` à côté du curseur : nom de la pièce + « Clic droit : démolir » (rouge) / « Clic droit : réparer »
(vert). En pose (mode construction) pas d'info-bulle : le bandeau de pose suffit.

Écarts / reste à faire :
- **État de la pièce** (fait, 2026-10-26) : `.build api pieceinfo <guidHex>` → `PI|guid|pv|pvmax|support|nom`
  (`support` = `BuildingMgr::SupportColorValue`, copie de `WearNTear.GetSupportColorValue` IL 0–51 : −1 si support ≥ max du
  matériau, sinon `Clamp01((support − min) / (max × 0,5 − min))`), interrogée en silence au changement de pièce visée puis
  toutes les 2 s (`Core.PieceInfoCommand`, une seule en attente). Surbrillance `Core.HighlightColor(support)` (bleu clair tant
  que l'état n'est pas connu) ; info-bulle dans les **trois** modes : nom, « Santé : 75 % » (jaune ≤ 60 %, rouge ≤ 25 %),
  « Support : complet / solide / moyen / faible / critique » dans la couleur de la surbrillance, puis l'action du clic droit
  en Démolir / Réparer. Ancien serveur (`E|commande inconnue`) : plus d'interrogation, bleu clair.
- **Son de démolition** : sur `M|<pièce> démolie.` (clic milieu ou clic en mode Démolir), `PlaySoundFile` d'un son du
  client selon la matière principale (coût le plus élevé) : bois `Sound\Doodad\DeadmineDoor01Destroy.wav`, pierre
  `Sound\Doodad\G_CaveinClosed.wav`, métal `Sound\Doodad\BlackRockDoorSingleDestroy.wav` (`SoundEntries.dbc` 3079,
  4634, 6533 ; non écoutés).
- Distance : Valheim ne surligne qu'à portée de pose (5 m de l'œil) ; ici toute pièce sous la souris (le rayon du client).
- Le survol natif de WoW (`SetHighlight` bit 1, info-bulle du gameobject en bas à droite) reste actif hors ciblage.

**Non vérifié en jeu** : rendu réel de la diffuse / de l'émissif sur les M2 de pièces (intensité de la lueur 0.4) ; que
la surbrillance ne « colle » pas après démolition (l'objet est détruit : rien à remettre) ; disparition instantanée
visuelle (`disparition instantanee` dans le journal) ; arbres abattus (créatures `0x5fbe80`).
Test proposé : `/script print(WowlheimSetInstantFade())` (8 valeurs, la dernière = 1) ; démolir une pièce (clic droit en
mode Démolir ou clic milieu) : disparition à l'image suivante ; ramasser un ramassable ; en mode Démolir, survoler des
pièces : bleu clair + info-bulle, rien sur les autres objets ; `/reload` en survolant une pièce : couleur d'origine.
