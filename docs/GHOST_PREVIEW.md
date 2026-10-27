# Wowlheim — Aperçu fantôme de la pièce (client 1.12.1 build 5875)

Portée : `tools/client/dll/` (DLL injectée, voir `docs/CLIENT_PATCH.md`) et ce document. Tout ce qui suit a
été obtenu par **analyse statique uniquement** (Ghidra 12.1.4 headless sur le projet déjà analysé
`C:\Wowlheim\tools\ghidra_proj`, lecture seule ; scripts de requêtes dans `C:\Wowlheim\tools\re_work\ghost\`).
WoW.exe n'a **pas** été lancé pour ce travail. Les trois copies de WoW.exe (Bureau, `client_test`,
`re_work`) ont le même SHA-256 `b4756d38…2dc7`.

Légende : **[VÉRIFIÉ-S]** = vérifié statiquement (désassemblage/flux de données, octets contrôlés),
**[INFÉRÉ]** = déduit du code mais sémantique non confirmée, **[NON VÉRIFIÉ]** = rien ne l'établit
(comportement en jeu). Aucun point de ce document n'est vérifié en jeu.

---

## 1. Découverte principale : le client a déjà un aperçu fantôme natif

Pendant le ciblage au sol d'un sort dont un effet invoque un gameobject, le client 1.12.1 **affiche lui-même
le modèle du gameobject sous le curseur** et le déplace à chaque image. C'est exactement le mécanisme
« fantôme » voulu ; la DLL Wowlheim réutilise les mêmes fonctions pour un modèle arbitraire.

Chaîne native (preuves en §3) :

1. `0x6e4b60` (lancement d'un sort par le joueur, Spell_C_CastSpell-like) : si le sort passe en mode ciblage
   (`0x6e5250` échoue → `[0xcecac0]` = drapeaux de cible attendus), il parcourt les 3 effets du Spell.dbc
   (`rec[0x3d..0x3f]`) ; si l'un vaut **50, 76, 81, 104, 105, 106 ou 107** (TRANS_DOOR, SUMMON_OBJECT_WILD,
   CREATE_HOUSE, SUMMON_OBJECT_SLOT1..4), il lit `EffectMiscValue` (`rec[0x6a+i]`, = entrée gameobject),
   interroge le cache gameobject (`0x558560`, requête serveur + rappel `0x6e59c0` si absent), prend
   `displayId` (`goRec+4`), la ligne `GameObjectDisplayInfo` (`[0xc0dcec][displayId]`), puis le chemin de
   modèle (`displayRec+4`) et crée l'objet-modèle : `[0xceca8c] = 0x6707c0(chemin, posJoueur, 0,0,0,0,0)`,
   `0x670d40(obj, 0)`.
2. À chaque image, `CGWorldFrame::OnLayerUpdate` (`0x481790`) lance le rayon écran→monde (`0x481190`) ; si le
   rayon touche le sol (retour 1), `0x4820f0(hit)` copie le point (`hit+8`) dans `0xb4b3a0`, teste la portée
   (`0x6e6810` → `[0x83dc2c]` = 0 dans la portée / 1 hors portée) et, si `[0xceca8c]` existe, le déplace :
   `0x6709a0(obj, 0xb4b3a0, orientation, isHouse)`.
3. Orientation : `0x6e6980` = orientation du joueur (vtable+0x18), sauf effet 81 CREATE_HOUSE
   (`[0xceca90]=1`) où elle vaut le flottant `[0xcecad4]` (0 au départ) et où `0x698110` **aligne la position
   sur une grille** (arrondi `ROUND((x+C)*K-D)`).
4. Clic : `0x492580` → `Spell_C_HandleTerrainClick` (`0x6e60f0`, nom communautaire confirmé par le code) copie
   le point dans `0xceac84` (TARGET_FLAG_DEST_LOCATION `0x40`) ou `0xceac78` (SOURCE `0x20`) ; le sort part.
5. Annulation/fin (`0x6e4940`, `0x6e54f0`) : `0x670d50([0xceca8c])` puis `[0xceca8c]=0`.

**Conséquence pratique (sans DLL) [INFÉRÉ, très probable] :** un sort Wowlheim de pose dont l'effet 1 est
`SUMMON_OBJECT_WILD` (76), `EffectMiscValue` = entrée du gameobject de la pièce (son `displayId` 20000+
pointant `World\Wowlheim\<prefab>.m2`) et dont la cible implicite est une destination au sol, montrera
nativement le modèle de la pièce sous la souris pendant le ciblage. Il faut que **le Spell.dbc du client**
(patch MPQ) contienne ces valeurs — c'est la copie client qui pilote l'aperçu — et que le serveur réponde à
`CMSG_GAMEOBJECT_QUERY` pour l'entrée. Limites natives : pas de teinte, orientation = celle du joueur (ou
grille + `[0xcecad4]` avec l'effet 81). Hors de mon périmètre (Spell.dbc/MPQ/serveur appartiennent à d'autres
agents) : à transmettre.

### 1bis. Voie native retenue — sort 40001, choix de la pièce et orientation (DLL)

Décision du coordinateur : sort de pose **40001** (Spell.dbc du patch client), `Effect1 = 76`
(SUMMON_OBJECT_WILD), `Targets = 0x40`, `EffectImplicitTargetA1 = 28`, `EffectMiscValue1` = entrée
gameobject de la pièce (`9110000 + id`, displayId 20000+). Lancé par `UseInventoryItem(16)` (marteau).

**Table Spell du client en mémoire [VÉRIFIÉ-S]** — `WowClientDB<SpellRec>` statique en **`0xc0d780`** :

| Champ | Contenu | Preuve |
|---|---|---|
| `+0x00` (`0xc0d780`) | pointeur vers les enregistrements contigus (n × 0x2b4 octets, alloués sur le tas) | chargeur `0x54ffd0` : `*param_1 = alloc(n*0x2b4 + tailleChaînes)` |
| `+0x04` | nombre d'enregistrements (en-tête WDBC) | idem |
| `+0x08` (`0xc0d788`) | table d'index `[id] → SpellRec*` (taille `maxId+1`, entrées absentes = 0) | boucle finale de `0x54ffd0` : `index[rec->id] = rec` |
| `+0x0c` (`0xc0d78c`) | id maximal | idem (`max(rec->id)`) |
| `+0x10` | chargé (1) | idem |

- Chargement : `0x54073b MOV ECX,0xc0d780 ; CALL 0x54ffd0`, au milieu de la série d'initialisation des
  bases (`0xc0dce4` = GameObjectDisplayInfo, etc.) ; `0x54ffd0` ouvre le fichier dont le nom vient de
  `0x583720` (`"DBFilesClient\Spell.dbc"`, chaîne `0x859e30`), vérifie la signature `WDBC`, **173 colonnes
  (`CMP EAX,0xad` en `0x55007e`) et 692 octets par ligne (`CMP EAX,0x2b4` en `0x5500bb`)**, puis lit chaque
  ligne avec `0x583750` (lecture champ par champ ; erreur `"Error reading SpellRec"`).
- **Pas de fonction de recherche unique** : le lookup est en ligne partout (≈ 150 lectures de `0xc0d788`),
  toujours sous la forme `if (id < 0 || [0xc0d78c] < id) échec; rec = [[0xc0d788] + id*4]` (ex. `0x6e4b60`).
- Champs utilisés par le fantôme natif dans `0x6e4b60` : `Effect[i]` = `rec[0x3d+i]` (champ **61+i**, testé
  en `0x6e50e0..0x6e5103` contre 50/104/105/106/107/76/81) et `EffectMiscValue[i]` = `rec[0x6a+i]` (champ
  **106+i**, lu en `0x6e5140 MOV EAX,[ESI+EDI*4+0x1a8]`, passé au cache gameobject `0xc0e318` via `0x558560`).
  Confirme la numérotation du coordinateur (champ 106 = `EffectMiscValue1`).
- La valeur est lue **au moment où le sort entre en ciblage** : la changer pendant un ciblage en cours ne
  change pas le fantôme déjà créé (il faut relancer le sort). Si l'entrée n'est pas encore dans le cache
  gameobject du client, celui-ci envoie la requête au serveur et crée le fantôme dans le rappel `0x6e59c0`
  (seulement si le même sort est toujours en ciblage).
- Le **serveur** utilise ses propres données de sort : changer la valeur côté client ne change pas l'objet
  invoqué par le serveur. Le choix de la pièce doit aussi lui parvenir (canal addon), à charge du serveur.

**Orientation du fantôme natif [VÉRIFIÉ-S]** — `0x4820f0` appelle `0x6e6980` (site `0x4821c5`) et passe le
résultat à `0x6709a0`, qui l'applique (`0x698e20` → rotation Z `0x7bdd60`) :
- effet 76 (non « maison », `[0xceca90]=0`) : orientation = **celle du lanceur** (`obj->vtable[0x18]`),
  recalculée à **chaque image** et recopiée dans `0xcecad4` ⇒ écrire `0xcecad4` ne sert à rien ;
- effet 81 CREATE_HOUSE (`[0xceca90]=1`, posé en `0x6e511d`) : orientation = flottant **`0xcecad4`** (mis à 0 au
  lancement en `0x6e50cf`) ; un **clic droit** pendant le ciblage (`0x492c20`, bouton `4`) appelle `0x6e69e0`
  qui ajoute **π/2** (constante `0x808acc` = 1.5708, modulo `0x80295c` = 6.2832) au lieu d'annuler ; la
  position est en plus **alignée sur une grille** (`0x698110`). Champ réglable en mémoire, mais ce mode
  impose la grille et dépend d'un effet 81 que le serveur doit savoir traiter (non étudié côté serveur).

⇒ Pour l'effet 76, aucun champ mémoire ne suffit ; la DLL remplace donc le `CALL 0x6e6980` en `0x4821c5`
(l'original est toujours appelé, puis sa valeur est remplacée si l'addon a fixé une orientation).

**API Lua ajoutée** (trampolines 7 à 9 ; la cave 1 étant pleine, une 2ᵉ cave de padding `0xCC` est
utilisée : `0x75f048..0x75f07f`, 56 octets après le `RET 0xc` de `0x75f042`, aucune xref) :

| Fonction | Effet |
|---|---|
| `WowlheimSetPlaceObject(goEntry [, spellId=40001])` | Cherche le sort dans `0xc0d780` (bornes + `rec[0]==id`), prend le **premier effet d'invocation** (50/76/81/104–107) et écrit `goEntry` dans son `EffectMiscValue` (champ 106 pour l'effet 1). Renvoie l'ancienne valeur, ou `nil` si la table n'est pas chargée, le sort absent ou sans effet d'invocation (rien n'est écrit dans ce cas : protège les autres sorts). |
| `WowlheimGetPlaceObject([spellId=40001])` | Valeur actuelle, ou `nil`. |
| `WowlheimSetPlaceFacing(radians)` / `WowlheimSetPlaceFacing()` | Impose l'orientation absolue du fantôme natif (tous modes) / rend la main au client (orientation du joueur). Côté serveur, l'objet posé n'en tient pas compte : l'orientation doit être transmise par l'addon. |

Séquence addon prévue : choix dans le menu → `WowlheimSetPlaceObject(9110000 + id)` →
(`WowlheimSetPlaceFacing(r)` si rotation) → `UseInventoryItem(16)` → le client affiche la pièce sous le
curseur → clic gauche : le client envoie le sort avec la destination (`0x6e60f0`) ; `WowlheimGhostGetPos()`
reste disponible pour lire le point. Pour changer de pièce pendant le ciblage : `SpellStopTargeting()`, puis
nouveau `SetPlaceObject` et nouveau lancement.

Garde-fous : la voie native n'est activée que si les 6 motifs du groupe « natif » de `g_sigs` (chargeur
Spell, 173 colonnes, 692 octets, lecture `EffectMiscValue`, site `0x4821c5`, début de `0x6e6980`) **et** ceux
du groupe fantôme (dont les fonctions Lua utilisées) correspondent ; la cave 2 est contrôlée (`0xCC`) au
moment d'y écrire. Le hook `0x4821c5` est posé indépendamment des hooks de l'aperçu DLL (§2).

---

## 2. Implémentation DLL : API Lua de l'aperçu fantôme

Fichier : `tools/client/dll/wowlheim_client.cpp` (même mécanisme que `WowlheimPing` : enregistrement par
`FrameScript_RegisterFunction` 0x704120 via un trampoline de 8 octets dans une cave `.text` ; la cave
0x75d401 contient les 7 premiers — Ping + 5 API fantôme + `WowlheimSetPlaceObject` — et la cave 0x75f048 les
2 suivants, voir §1bis).

| Fonction Lua | Effet |
|---|---|
| `WowlheimGhostShow(chemin [, echelle])` | Demande l'affichage du modèle (`"World\\Wowlheim\\woodwall.m2"` ; `.mdx`/`.mdl` sont réécrits en `.m2` par le chargeur `0x706a50` ; fichier absent → `Spells\ErrorCube.mdx`, comportement du client). Échelle 0.01–100, défaut 1. Le modèle est créé à la première image où un point sous la souris est connu. Renvoie `1`, ou `nil` si l'API fantôme est désactivée ou l'argument invalide. Changer de chemin recrée le modèle. |
| `WowlheimGhostRotate(radians)` | Orientation absolue autour de Z (normalisée dans [0, 2π)). |
| `WowlheimGhostHide()` | Masque et libère le modèle (`0x670d50`). |
| `WowlheimGhostGetPos()` | `x, y, z, orientation, type` du dernier point sous la souris (`type` 1 = sol/WMO, 2 = objet), ou `nil` si aucun. Mis à jour à chaque image où la souris survole le monde (pas l'UI), que le fantôme soit visible ou non. |
| `WowlheimGhostSetColor(r, g, b [, a [, lueur]])` | Teinte 0..1 : `(r,g,b)` multiplie l'éclairage diffus du modèle, `a` = alpha, `lueur` = part de `(r,g,b)` ajoutée en couleur ambiante/émissive (défaut 0.25). Défauts : `0.4, 1, 0.4, 0.5`. Ex. valide `(0.4,1,0.4,0.5)`, invalide `(1,0.3,0.3,0.5)`. |

Le placement final reste fait par le serveur : l'addon lit `WowlheimGhostGetPos()` et envoie position +
orientation (canal addon existant).

Fonctionnement interne :

- **Hook par image** : le `CALL 0x481190` en `0x48184a` (dans `CGWorldFrame::OnLayerUpdate`) est redirigé vers
  `Hook_WorldRaycast` ; après l'original, si le retour est 1 ou 2, le point `hit+8` est mémorisé puis
  `Ghost_Tick()` crée / déplace (`0x6709a0`, exactement comme le fantôme natif en `0x4821d5`) / libère le modèle.
- **Création** : `0x6707c0(chemin, pos, orientation, 0, 0, 0, 0)` puis `0x670d40(def, 0)` — mêmes arguments que
  le client (`0x6e5a6e`, `0x6e518f`) ; GUID nul ⇒ l'objet n'est rattaché à aucun gameobject.
- **Échelle** (M2 seulement) : après le déplacement (qui remet la matrice à T·R et `def+0x30` à 1.0),
  `C44Matrix::Scale` (`0x7bdca0`) sur la matrice monde `def+0xcc`, `def+0x30 = échelle`, puis recalcul des
  bornes `0x6952a0` si le M2 est chargé.
- **Teinte/alpha** (M2 seulement) : écrits à chaque image dans le `CM2Model` (`def+0x88`) : `+0x180` alpha,
  `+0x184` couleur diffuse, `+0x190` couleur ajoutée. WMO : ni teinte ni échelle (non étudié).
- **Sécurité mémoire** : hooks des deux `CALL 0x697ac0` (`CMap::Unload`-like, sites `0x66fc45` et `0x6920cc`,
  seuls appelants — `callers.py`) : le fantôme est libéré **avant** que la carte ne libère ses objets, et
  l'affichage est annulé (l'addon doit rappeler `Show` après un changement de carte). À chaque
  réinitialisation Lua (ReloadUI, changement de personnage) le fantôme est aussi libéré. Les mises à jour sont
  protégées par `__try/__except` : une exception désactive l'aperçu au lieu de planter (journalisée).
- **Garde-fous** : avant de poser le moindre hook fantôme, la DLL vérifie les octets attendus de chaque site et
  de chaque fonction appelée (table `g_sigs`) ; un seul écart ⇒ API fantôme non enregistrée, `WowlheimPing`
  inchangé.

### 2bis. Marqueurs fixes : cercle de portée des stations (2026-10-26)

Valheim montre, marteau en main, le **marqueur de zone** de chaque station (`CraftingStation.m_areaMarker`, enfant
`AreaMarker` de `piece_workbench` : `CircleProjector` de 80 segments, `m_prefab` = `station_marker/Circle_section.prefab`,
un cube à l'échelle 0,15 × 0,10 × 1,0 en `Unlit/Color` gris 0,8 ; lu dans les bundles avec `tools/valheim/vh_lib.py`).

**Approche retenue : marqueurs côté client** (pas de GameObject serveur : il serait visible de tous et coûterait des
objets réseau). Trois éléments :

1. **Serveur** — `.build api stations [rayon=40]` (`server/Wowlheim/BuildCommands.cpp`, `Wowlheim_StationsCommand`) :
   au plus 6 stations (pièces dont le kind est exigé par une pièce du catalogue) à moins de 40 m, de la plus proche à la plus
   lointaine. Pour chacune `ST|guid|kind|x|y|z|portée|dedans|n` puis `SG|guid|premier|x,y,z,o;…` (6 points par ligne) :
   le **contour exact** de la zone que teste la pose — `BuildingMgr::STATION_RANGE` = **10 m mesurés depuis le bord** de la
   boîte de la station (`DistToPiece2D`, `CheckStation` sur la position du **joueur**), donc un rectangle arrondi (presque
   un cercle pour une station de 1–2 m). Points espacés de ~1,57 m comme Valheim (24 à 96 par station), `o` = tangente,
   `z` = sol sous le point (`Map::GetHeight`, terrain + WMO ; plancher posé s'il couvre le point) + 5 cm.
   `dedans` = joueur dans la zone (même test que la pose). N.B. : le prefab de Valheim a `m_rangeBuild = 20` (+4 m par
   extension, `m_extraRangePerLevel`) ; le serveur garde 10 m depuis le bord, c'est lui qui décide.
2. **Modèles** — `tools/valheim/build_markers.py` : `World\Wowlheim\wl_station_ring{,_in,_out}.m2` (pavé 1 m × 0,15 ×
   0,10, non éclairé, gris Valheim / vert / rouge, texture unie 8×8), écrits dans `C:\Wowlheim\wl_assets\mpq` puis mis
   dans `patch-3.MPQ` par `gen_client_patch.py` (DBC inchangés : ce sont des modèles affichés par la DLL, sans entrée DBC).
3. **DLL** — deux API (trampolines 10 et 11, cave 2) ; **aucune adresse nouvelle** : mêmes fonctions que le fantôme
   (`0x6707c0` création, `0x670d40`, `0x6709a0` placement, `0x670d50` libération, `0x7bdca0` échelle).

| Fonction Lua | Effet |
|---|---|
| `WowlheimMarkerShow(id, chemin, x, y, z [, orientation [, échelle]])` | `id` 0..255. Pose (ou déplace / change de modèle) le marqueur. Créé tout de suite dans l'appel Lua si une image du monde a été vue depuis le chargement de la carte (le fantôme natif est lui aussi créé depuis Lua, par le lancement du sort `0x6e4b60 → 0x6e518f`), sinon à la prochaine image. Rappeler avec les mêmes valeurs ne fait rien. Renvoie `1` ou `nil`. |
| `WowlheimMarkerHide(id)` / `WowlheimMarkerHide()` | Libère un marqueur / tous. |

Chaque image (hook du lancer de rayon), les marqueurs en attente sont créés et 16 marqueurs déjà posés sont replacés
(`0x6709a0`, comme le fantôme natif replacé à chaque image : rattachement aux chunks). Tous sont libérés avant le
déchargement de la carte (hooks `0x697ac0`) et à chaque réinitialisation Lua ; exceptions interceptées (aperçu désactivé).

**Addon** (`WowlheimCore.lua` : `RingsOnMessage`, `RingMarkers`, `StationRangeWarning` ; `Wowlheim.lua` : `UpdateRings`,
`ApplyRings`) : marteau équipé **et** mode construction ⇒ `.build api stations` silencieux toutes les 1,5 s (une seule
en attente), un segment par point, vert si le joueur est dans la zone, rouge sinon ; masqué dès que le marteau est rangé
ou en mode Démolir / Réparer. Le bandeau de pose ajoute « Hors de portée de la table de fabrication » (ou « Hors de
portée : Forge »…) quand la pièce choisie exige une station dont le joueur n'est dans aucune zone. Sans la DLL, seul
l'avertissement fonctionne. Les lignes `ST|`/`SG|` ne sont attribuées qu'à la commande `stations` : un `M|`/`E|` reçu
pendant l'interrogation va à la commande suivante ou à personne (`C.CHANNEL_STRUCTURED`).

**Non vérifié en jeu** : affichage des segments (couleur non éclairée, enfoncement sur les pentes), tenue des modèles
quand le joueur s'éloigne (chunks déchargés/rechargés — d'où le replacement tournant), coût de 250 modèles, retard de
couleur (≤ 1,5 s + latence).

### 2ter. Objet sous le curseur, apparition instantanée, préchargement (2026-10-26)

Trois API de plus (trampolines 12 à 14, cave 2 désormais pleine) : `WowlheimGetMouseoverObject()`,
`WowlheimSetInstantFade(...)`, `WowlheimPreloadModel([chemin])`, et 5 nouveaux sites de `CALL` (`0x4812c1`, `0x5f7c6b`,
`0x5fb956`, `0x5f7e83`, `0x5fbd67`). Preuves et conception des contrôles : **`docs/BUILD_CONTROLS.md`** §3–4.

### 2quater. Rotation et couleur du fantôme natif (2026-10-26)

Valheim : la molette tourne le fantôme par pas de 22,5° (`m_placeRotation`) et `SetPlacementGhostValid` le montre normal si
la pose est possible, rouge sinon. **Aucune API nouvelle** (les deux caves sont pleines, 14/14 trampolines) : les fonctions
existantes prennent des arguments de plus ; 2 motifs ajoutés au groupe « natif » de `g_sigs` (`verify_addrs.py` : tout passe).

| Ajout | Effet |
|---|---|
| `WowlheimSetPlaceFacing(radians, 1)` | **Décalage relatif** : `Hook_NativeFacing` renvoie `orientationNative + radians` (normalisée dans [0, 2π)) à chaque image. L'orientation native de l'effet 76 est celle du personnage, et le serveur pose avec `orientation du personnage + rot × π/8` (`BuildingMgr::PlaceOrientation`, utilisée par `PlaceFromSpell` et `canplace`) : l'addon passe `rot × π/8`, le fantôme montre donc l'orientation exacte de la pièce posée, y compris quand le personnage tourne pendant le ciblage. Sans 2ᵉ argument : orientation absolue (inchangé). |
| `WowlheimGhostSetColor(r, g, b, a, lueur, 1)` | Teinte le **fantôme natif** : à chaque image, dans `Hook_NativeFacing` (appelé par `0x4820f0` juste avant `0x6709a0`), la def `[0xceca8c]` (`0x6e6970` = `MOV EAX,[0xceca8c] ; RET`, résultat passé à `0x6709a0` via ESI) reçoit alpha / diffus / émissif dans son `CM2Model` (mêmes champs que §2). Défauts `a = 1`, `lueur = 0`. `cible = -1` : arrêt (une dernière écriture neutre 1,1,1 / 1 / 0). Remis à zéro à chaque réinitialisation Lua. |
| `WowlheimGhostGetPos()` → 6ᵉ et 7ᵉ valeurs | `[0x83dc2c]` (0 point de ciblage dans la portée du sort, 1 hors portée, 3 pas encore calculé ; écrit par `0x4820f0`, motif `0x482154 MOV [0x83dc2c],0`) et la dernière orientation donnée au fantôme natif (contrôle en jeu). |

**Serveur** — `.build api canplace <x> <y> <z> [rot]` (`BuildCommands.cpp`, `BuildingMgr::CanPlaceFromSpell`) : mêmes
contrôles que `PlaceFromSpell` (portée 8 m `InPlaceReach`, zone interdite, extension, station, ressources, accroche,
`CanPlaceAt` = plafonds + emplacement occupé + gameobject_template, extrait de `Place`) via `TryPlace(..., dryRun = true)`,
sans poser, sans consommer, sans l'endurance (Valheim ne colore pas selon l'endurance). Réponse `CP|1` ou `CP|0|raison`,
puis `D|canplace|1`.

**Addon** (`WowlheimCore.lua` : `PlaceFacingOffset`, `GhostCheckCommand`, `GhostCheckOnMessage`, `GhostValid`,
`GHOST_COLORS` ; `Wowlheim.lua` : `ApplyGhostFacing`, `UpdateGhost`) : décalage posé avant chaque ciblage et à chaque cran de
molette. Pendant le ciblage de la pose : `canplace` silencieux au plus toutes les **0,25 s** (une seule en attente), seulement
si le point visé bouge de plus de 0,1 m ou que la pièce / la rotation change, sinon une fois par seconde (4 commandes/s au
plus : l'anti-flood du chat, `ChatFlood.MessageCount = 10` messages dans la même seconde, reste loin). Couleur, dans l'ordre :
hors portée du sort (DLL) → rouge ; verdict du serveur de moins de 1,5 s pour la même pièce / rotation → il fait foi ; sinon
contrôles locaux immédiats (ressources des sacs vs coût, zone des stations des lignes `ST|`). Normal = `(1,1,1)` opaque ;
rouge = `(1, 0,25, 0,2)`, alpha 0,75, lueur 0,45. Hors ciblage : teinte retirée.

Limites : la distance joueur ↔ point (8 m) n'est vérifiée que par le serveur (Lua 1.12 ne donne pas la position monde du
joueur ; la DLL n'expose pas l'objet joueur) ; retard de couleur ≤ 0,25 s + latence. L'orientation suppose que le serveur
connaît l'orientation courante du personnage (paquets de mouvement : tourner au clavier envoie l'orientation à l'arrêt ; le
clic droit, qui tourne à la souris, annule le ciblage). Accroche : voir §2quinquies.

### 2quinquies. Fantôme accroché (2026-10-26)

**Valheim** : `Player.UpdatePlacementGhost` place le fantôme APRÈS `FindClosestSnapPoints` : la pièce saute sur le point
d'accroche voisin, verte ou rouge. **Choix retenu** : le fantôme natif ne peut pas être déplacé (sa position est calculée
par `0x4820f0` puis passée directement à `0x6709a0` ; seul l'appel d'orientation `0x6e6980` est accroché). Quand le serveur
a accroché la pièce, l'addon rend le fantôme natif **invisible** (`WowlheimGhostSetColor(1,1,1,0,0,1)`, alpha 0 — il sert
toujours au ciblage, le clic part toujours du point sous la souris) et montre le **fantôme DLL** (même modèle
`World\Wowlheim\<prefab>.m2`, lignes `MD|`) au point accroché ; sinon le fantôme natif teinté, comme avant.

| API (nouvelle, 16ᵉ trampoline) | |
|---|---|
| `WowlheimGhostPlace(x, y, z)` | Le fantôme DLL est posé à ce point au lieu du point sous la souris (créé même si la souris n'a pas encore touché le monde). `WowlheimGhostPlace()` : retour à la souris. Remis à zéro par `WowlheimGhostHide`, le déchargement de la carte et la réinitialisation Lua. `WowlheimGhostGetPos` renvoie toujours le point sous la souris. |

**Serveur** : `canplace` répond `CP|1|x|y|z|o|a` ou `CP|0|x|y|z|o|a|raison` (`x y z o` = position et orientation après
`BuildingMgr::Snap`, `a` = 1 si un point d'accroche a été pris ; `CanPlaceFromSpell(..., WLPlacePreview*)`, même `Snap` que la
pose, la position accrochée est calculée même si la pose est refusée). L'addon accepte encore l'ancien `CP|1` / `CP|0|raison`.

**Addon** (`Core.GhostSnapPos`, `WL.UpdateGhost`, `WL.SnapGhostReady`, `WL.HideSnapGhost`) : position accrochée du dernier
verdict (même pièce / rotation, moins de 1,5 s) tant que le point visé reste à moins de **0,75 m** du point interrogé ; au-delà
(ou `a = 0`), fantôme natif à la souris jusqu'au verdict suivant (≤ 0,25 s). Orientation : 7ᵉ valeur de `WowlheimGhostGetPos`
(orientation du fantôme natif, donc personnage + rotation, à jour à chaque image), sinon `o` du serveur. Modèles demandés
(`.build api models`) si l'addon ne les a pas encore. Sans `WowlheimGhostPlace` (ancienne DLL) ou sans modèle : comportement
précédent (fantôme natif au point visé).

**À vérifier en jeu** : alpha 0 cache bien le fantôme natif ; le fantôme DLL a la même échelle / hauteur que la pièce posée
(gameobject `size` 1) ; pas de clignotement natif ↔ DLL quand la souris glisse le long d'un point d'accroche.
**Non vérifié en jeu** : rendu de la teinte et de l'alpha sur le fantôme natif, valeur réelle de `[0x83dc2c]` pendant le
ciblage du sort 40001.

---

## 3. Adresses, preuves et confiance

Toutes les adresses sont des VA de WoW.exe 5875 (ImageBase 0x400000, pas de relocalisation).

### (a) Point du monde sous le curseur

| Adresse | Rôle | Preuve | Confiance |
|---|---|---|---|
| `0x481790` | `CGWorldFrame::OnLayerUpdate(float dt)` — exécuté à chaque image | seule xref = vtable `0x804420` ; appelle d'abord `0x76b2c0` (= `CSimpleFrame::OnLayerUpdate`, lance le script `OnUpdate` stocké en `+0x128` avec `dt`) ; ne calcule le rayon que si le cadre sous la souris (`[[this+0xa0]+0x7c]`) est le WorldFrame ; lit la position souris `[ui+0x1118/0x111c]` (mêmes champs que `GetCursorPosition` 0x48b820) | [VÉRIFIÉ-S] |
| `0x481190` | Lancer de rayon écran→monde : `__thiscall(worldFrame, x, y, hit*)`, `RET 0xc`, renvoie 0 rien / 1 sol-WMO / 2 objet | désassemblage du site `0x48184a` (`PUSH hit; PUSH ECX; PUSH EDX; MOV ECX,ESI; CALL`) et de `0x4813a4 RET 0xc` ; dispatch `DEC EAX; JZ` → `0x4820f0` (1) / `0x4828d0` (2) | [VÉRIFIÉ-S] |
| `0x480df0` | Cœur du test : `0x672170` (TraceLine monde, drapeaux `0x1000114`/`0x10f0114` → `0x69bff0`) puis `0x480a50` (intersection objets, renvoie le GUID) ; écrit `hit+0` GUID (cas 2), `hit+8` point touché (C3Vector), `hit+0x14` distance | décompilation | [VÉRIFIÉ-S] (mécanisme), [INFÉRÉ] (`0x672170` = TraceLine : correspond aussi à l'offset publié par la communauté, ex. UnitXP) |
| `hit+8` | **point monde sous la souris** | c'est ce que `0x4820f0` copie dans `0xb4b3a0` et passe à `0x6709a0` pour le fantôme natif | [VÉRIFIÉ-S] |
| `0xb4b3a0` | point sous la souris pendant un ciblage au sol (x,y,z float) | écrit seulement par `0x4820f0` (si `[0xcecac0] & 0x60`) et remis à 0 par `0x4805d0` | [VÉRIFIÉ-S] |
| `0x83dc2c` | état du curseur de ciblage : 0 dans la portée, 1 hors portée, 3 avant calcul | `0x4820f0` / `0x481840` | [VÉRIFIÉ-S] (valeurs), [INFÉRÉ] (couleur du curseur via `0xb4b344[idx]`) |
| `0x6e48a0` | `Spell_C_IsTargeting` : `word [0xcecac0] != 0` (utilisé par `SpellIsTargeting` 0x6e6cd0) | table Lua `0x86f950` → `0x6e6cd0` | [VÉRIFIÉ-S] |
| `0x6e60f0` | `Spell_C_HandleTerrainClick(C3Vector*)` : copie dans `0xceac84` (dest, drapeau 0x40) ou `0xceac78` (source, 0x20) | décompilation ; appelé par `0x492580` | [VÉRIFIÉ-S] |
| `0x6e6810` | test de portée du point de ciblage (min/max du sort `0x6e3480`) | décompilation | [VÉRIFIÉ-S] |

### (b) Affichage d'un modèle M2 arbitraire sans objet serveur

| Adresse | Rôle | Preuve | Confiance |
|---|---|---|---|
| `0x6707c0` | Création d'un objet-modèle du monde : `__fastcall(chemin, C3Vector* pos, [pile] orientation, chargerTout, grille, guidLo, guidHi)`, `RET 0x14` ; `.wmo` (chaîne `0x867aa4`) → def WMO `0x6953e0` (drapeau `+8 & 0x08`), sinon def M2 `0x694980` (`+8 & 0x40`, `+0x90 |= 0x2000`, GUID en `+0x180/+0x184`) ; `+0xe` compteur de références | désassemblage complet ; appelée par le fantôme natif (`0x6e518f`, `0x6e5a6e`) et par la création de modèle des gameobjects (`0x5f8076`, avec GUID) | [VÉRIFIÉ-S] |
| `0x694980` / `0x695100` | def M2 : position `+0x24`, échelle `+0x30`, bornes `+0x44..+0x68`, matrice monde `+0xcc` ; `0x695100` charge le M2 (`0x707350`) dans `+0x88` | décompilation | [VÉRIFIÉ-S] |
| `0x6709a0` | Déplacement : `__fastcall(def, C3Vector* pos, [pile] orientation, grille)`, `RET 8` → `0x698e20` (M2 : matrice = I·T(pos)·Rz(orientation), `+0x30 = 1`, bornes, rattachement aux chunks) ou `0x698f50` (WMO) ; `grille≠0` → `0x698110` | désassemblage ; appelé par `0x4821d5` (fantôme natif) et le déplacement des gameobjects (`0x5f52b8`, `0x5f603c`) | [VÉRIFIÉ-S] |
| `0x670d40` | `__fastcall(def, v)` : `v==0` → `[def+0xd] |= 1`, sinon `&= ~1` ; le client l'appelle avec 0 juste après la création | désassemblage | [VÉRIFIÉ-S] (effet mémoire), [INFÉRÉ] (sens du bit) |
| `0x670d50` | Libération : `--[def+0xe]`, puis `0x6a67a0` (M2) / `0x6a6870` (WMO) libère à 0 | désassemblage ; appelé à l'annulation du ciblage (`0x6e49e5`) | [VÉRIFIÉ-S] |
| `0x697ac0` | `CMap::Unload`-like : libère toutes les defs du monde (listes `0xc9e358`, `0xc962bc`) ; appelants uniques `0x66fc45`, `0x6920cc` | décompilation + recherche de tous les `E8 rel32` | [VÉRIFIÉ-S] |
| `0x7bdca0` | `C44Matrix::Scale(const C3Vector*)` (`__thiscall`, `RET 4`) | désassemblage | [VÉRIFIÉ-S] |
| `0x6952a0` | recalcul des bornes de la def (rayon × `+0x30`) | décompilation | [VÉRIFIÉ-S] |
| `CM2Model+0x180` | alpha (float) | `SetAlpha` `0x710cb0` ; fondu des gameobjects/unités `0x614a90` (`alpha = objAlpha * fondu`) ; fondu temporel `0x672ef0` ; lu par la mise à jour d'éclairage `0x714260` (`… * [m+0x180]`) | [VÉRIFIÉ-S] (flux), [NON VÉRIFIÉ] (transparence effective à l'écran) |
| `CM2Model+0x184` | couleur diffuse (C3Vector, défaut 1,1,1) | `0x710cf0` ; `0x714260` : `diffuse_scene * [m+0x184..0x18c]` | [VÉRIFIÉ-S] (flux), [NON VÉRIFIÉ] (rendu) |
| `CM2Model+0x190` | couleur ajoutée (C3Vector, défaut 0,0,0) | `0x710d40` ; `0x714260` : `ambiante + [m+0x190..0x198]` | [VÉRIFIÉ-S] (flux), [NON VÉRIFIÉ] (rendu) |
| `0xc0dcec` | enregistrements de `GameObjectDisplayInfo.dbc` (WowClientDB `0xc0dce4`, max `0xc0dcf0`) | `0x5404b1 MOV ECX,0xc0dce4; CALL 0x545d50` (chargeur qui référence `"DBFilesClient\GameObjectDisplayInfo.dbc"` via `0x579d80`) | [VÉRIFIÉ-S] |
| `0x706a50` | chargeur M2 : `.mdx`/`.mdl` → `.m2`, autre extension refusée, fichier absent → `ErrorCube` | décompilation | [VÉRIFIÉ-S] |
| `0xceca8c` / `0xceca90` / `0xcecad4` | fantôme natif / mode « maison » (effet 81) / orientation fixe du mode maison | xrefs listées en §1 | [VÉRIFIÉ-S] |

### Fonctions Lua internes utilisées (vérifiées par désassemblage)

`lua_tonumber` `0x6f3620` (`__fastcall(L, idx)`, double dans ST0), `lua_isnumber` `0x6f34d0`, `lua_isstring`
`0x6f3510`, `lua_pushnumber` `0x6f3810` (`__fastcall(L, double)`, `RET 8`), `lua_pushnil` `0x6f37f0` ; toutes
passent par `index2adr` `0x6f3410` (`ECX=L`, `EDX=idx`). `lua_tostring` `0x6f3690` / `lua_pushstring`
`0x6f3890` : déjà validés à l'exécution par `WowlheimPing`.

### Corrections de `CLIENT_PATCH.md` §2(b)

- `0x481790` n'est pas un gestionnaire de clic : c'est `CGWorldFrame::OnLayerUpdate` (par image).
- `0x480a50` est le test d'intersection avec les **objets** (renvoie un GUID) ; le test terrain/WMO est
  `0x672170` → `0x69bff0`.
- `0x672190`/`0x672b60`/`0x6aa160` ne sont pas sur le chemin du curseur de sort au sol.
- `0x70ea00` n'est pas l'API à appeler pour placer un modèle dans le monde : la bonne entrée est `0x6707c0`
  (qui finit par `0x707350` → `0x70ea00`).

---

## 4. Vérifié / non vérifié

**Vérifié statiquement :**
- Toutes les adresses de §3 par décompilation/désassemblage Ghidra (sorties dans `C:\Wowlheim\tools\re_work\ghost\o*.txt`).
- Conventions d'appel et nettoyage de pile des fonctions appelées et des sites hookés (`RET 0xc`, `RET 0x14`,
  `RET 8`, `RET 4`, `RET`), et du code compilé de la DLL (`Hook_WorldRaycast` : `ret 12` ; `Hook_MapUnload` :
  saut de queue vers `0x697ac0` avec ECX/EDX restaurés ; fonctions Lua `__fastcall(L)`).
- `python tools/client/dll/verify_addrs.py` : les 28 motifs d'octets de `g_sigs`, les 7 sites
  `CALL/JMP rel32` (6 hooks + l'appel du chargeur Spell) et les constantes 173/692 du chargeur Spell
  correspondent dans `C:\Wowlheim\client_test\WoW.exe` (« toutes les vérifications passent ») ; caves :
  0x75d401 (≥ 48 octets `0xCC`), 0x75f048 (56 octets `0xCC`).
- Compilation x86 (`build.bat`, VS Build Tools 2022) sans avertissement, y compris en `/W4` ;
  `wowlheim_client.dll` 121 344 octets, machine 0x14C. Code généré contrôlé : `Hook_NativeFacing` renvoie
  dans ST0 avec `ret 0` (comme `0x6e6980`).

**Non vérifié (aucune exécution) :**
- Tout le comportement en jeu : que le modèle apparaisse, suive la souris, soit orienté, mis à l'échelle,
  teinté, transparent ; que le monde ne plante pas.
- Que l'alpha < 1 rende réellement le M2 translucide (le moteur pourrait exiger un mode de mélange ou réécrire
  l'alpha au rendu des doodads).
- Que l'échelle appliquée à `def+0xcc` soit celle utilisée au rendu (déduit du fait que le fantôme natif suit
  la souris avec le seul `0x6709a0`).
- Que le rayon ne touche pas le fantôme lui-même (risque de « remontée » vers la caméra si le `.m2` Valheim a
  un maillage de collision ; le fantôme natif a le même statut, le drapeau `+0x90 & 0x2000` semble le placer
  dans une liste dynamique).
- Le sens du bit `[def+0xd] & 1` posé par `0x670d40(def,0)`.
- La voie native (§1) avec un vrai sort Wowlheim : dépend du Spell.dbc client et du serveur.
- Voie native : l'affichage réel du modèle sous le curseur avec le sort 40001 modifié, la prise en compte de
  `WowlheimSetPlaceObject` au lancement suivant, l'orientation imposée par `WowlheimSetPlaceFacing`, la
  sémantique du bouton `4` (= clic droit, convention Storm, non confirmée ici), et que la mémoire des
  enregistrements Spell soit bien inscriptible (tas alloué par `0x6462e0`, non protégé a priori).
- Le module Warden : nouveaux octets modifiés en `0x48184a`, `0x66fc45`, `0x6920cc`, `0x4821c5`, 48 octets
  supplémentaires dans la cave `0x75d409..0x75d438` et 16 dans `0x75f048..0x75f057` ; l'enregistrement du
  sort 40001 est aussi modifié en mémoire (tas, non lu par les scans `READ_MEMORY` à adresse fixe). Non
  couverts par les scans actuels lus pour `CLIENT_PATCH.md` §4 (même analyse de risque).

---

## 5. Procédure de test en jeu (à faire plus tard, par une personne devant la machine)

Pré-requis : copie `C:\Wowlheim\client_test`, DLL et patch MPQ des modèles en place, serveur local démarré.

1. `python tools\client\dll\verify_addrs.py` → doit afficher « toutes les vérifications passent ».
2. Copier `wowlheim_client.dll` dans `C:\Wowlheim\client_test\`, lancer via `launch.exe` (prévoir une
   durée d'attente longue, ex. `launch.exe C:\Wowlheim\client_test\WoW.exe C:\Wowlheim\client_test\wowlheim_client.dll 3600`,
   le lanceur termine WoW à la fin du délai).
3. Journal `wowlheim_client.log` attendu au démarrage : `hooks poses en 0x0066fc45 et 0x006920cc`,
   `hook pose en 0x0048184a`, six lignes `… enregistree (trampoline …)`, `ghost getpos=nil`.
4. En jeu, dans la fenêtre de discussion :
   - `/script WowlheimGhostShow("World\\Wowlheim\\woodwall.m2")` → le mur doit apparaître sous la souris et
     la suivre ; journal `fantome cree …`.
   - `/script WowlheimGhostRotate(1.57)` → quart de tour.
   - `/script WowlheimGhostSetColor(1,0.3,0.3,0.5)` puis `(0.4,1,0.4,0.5)` → rouge / vert, translucide.
   - `/script WowlheimGhostShow("World\\Wowlheim\\wood_floor.m2", 2)` → changement de modèle, échelle ×2.
   - `/script local x,y,z,o,k=WowlheimGhostGetPos() DEFAULT_CHAT_FRAME:AddMessage(x..' '..y..' '..z..' '..o..' '..k)`
     → comparer avec `.gps` du serveur.
   - Survoler un objet / son propre personnage : vérifier que le fantôme ne « remonte » pas vers la caméra.
   - `/script WowlheimGhostHide()` → disparition ; journal `fantome libere`.
   - Fantôme affiché, se téléporter (`.tele`) puis changer de continent → pas de plantage, journal
     `fantome libere (dechargement de la carte)` ; `ReloadUI()` → `fantome libere (reinitialisation Lua)`.
   - Fichier inexistant → `Spells\ErrorCube` attendu (comportement du client), pas de plantage.
5. Voie native (sort 40001 modifié dans le patch, gameobjects 9110000+ connus du serveur) :
   - journal au démarrage : `hook pose en 0x004821c5 (… Hook_NativeFacing)`, `place object=…` (souvent `nil`
     au tout premier démarrage si Spell.dbc n'est pas encore chargé, puis la valeur du DBC après ReloadUI) ;
   - `/script print(WowlheimGetPlaceObject())` → valeur du DBC ;
     `/script WowlheimSetPlaceObject(9110001)` → renvoie l'ancienne valeur, journal `EffectMiscValue … -> 9110001` ;
   - `/script UseInventoryItem(16)` → le modèle de la pièce 9110001 suit le curseur, orienté comme le
     personnage ; tourner le personnage → le fantôme tourne ;
   - `/script WowlheimSetPlaceFacing(0)` pendant le ciblage → orientation fixe ; `WowlheimSetPlaceFacing()` →
     retour à l'orientation du joueur ;
   - `SpellStopTargeting()`, `WowlheimSetPlaceObject(9110002)`, relancer → l'autre pièce ;
   - clic gauche → le serveur reçoit la destination (`.gps`/journal serveur) ;
   - `WowlheimSetPlaceObject(1, 133)` (sort sans invocation) → `nil`, rien d'écrit.
6. En cas de plantage : `Errors\*.txt` du client + `wowlheim_client.log` (dernière ligne avant l'arrêt).
