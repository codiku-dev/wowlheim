# Wowlheim — Faisabilité côté client (phase 5)

Client analysé : WoW 1.12.1 build 5875 (`C:\Users\rlebh.RLEBHAR.000\Desktop\WoW Vanilla`), **en lecture seule** (aucun fichier du client modifié).
Méthode : lecture des MPQ (mpyq), analyse statique de `WoW.exe` (chaînes + désassemblage capstone, **sans exécution**), lecture des fichiers d'interface extraits.

Légende des conclusions : **[VÉRIFIÉ]** (preuve citée), **[INFÉRÉ]** (déduit d'indices, non confirmé par exécution), **[NON VÉRIFIÉ]** (hypothèse ou souvenir, aucune preuve ici).

> **Limite générale — aucun test en jeu.** Aucun pilotage de la GUI du client n'était possible : rien de ce qui suit n'a été exécuté dans WoW.exe. Tout ce qui dépend du comportement réel du client à l'exécution (chargement d'un patch, réception d'un événement, rendu) reste au mieux [INFÉRÉ].

> **Artefacts extraits.** `tools/client/extracted/` contient des fichiers issus du client légitime (FrameXML, DBC, quelques modèles). Ce sont des artefacts **locaux, à ne jamais publier ni distribuer** (voir `tools/client/extracted/README_NE_PAS_DISTRIBUER.txt`). Aucun asset WoW/Valheim n'est réutilisé hors de ce client.

---

## H1 — Addons : Lua 5.0, canal d'addon, retours serveur, masquage

**Verdict : hypothèse partiellement FAUSSE.** Lua 5.0 : vrai. `SendAddonMessage` : **il existe** (contrairement au cahier), mais restreint. `ChatFrame_AddMessageEventFilter` : absent comme prévu ; l'alternative `ChatFrame_OnEvent` est réelle.

### H1.1 Lua 5.0 — [VÉRIFIÉ]
- `WoW.exe` contient la chaîne `Lua 5.0 Copyright (C) 1994-2003 Tecgraf, PUC-Rio` (va 0x811b2e) et `Lua 5.0` (va 0x87163c).
- Le code Blizzard utilise la syntaxe 5.0 : itération sans `pairs`, `arg.n`, globales de handlers.
  ```lua
  -- Interface\FrameXML\ChatFrame.lua:1168-1172
  function ChatFrame_RegisterForMessages(...)
      for i=1, arg.n do  messageGroup = ChatTypeGroup[arg[i]]; ...
  -- ChatFrame.lua:1160
  for index, value in ChatTypeInfo do
  ```
- Absents de `WoW.exe` (recherche de la chaîne exacte) : `select`, `strsplit`, `gmatch`, `match`, `hooksecurefunc` → cohérent avec 5.0 (pas de `select`, pas de `string.match`). Présents : `getn`, `gfind`, `unpack`, `loadstring`, `getglobal`, `setglobal`, `mod`.
- Conséquences pour l'écriture d'addon : pas d'opérateur `#` ni `%` arithmétique, pas de `...` en table (variable implicite `arg`), handlers `function() … end` qui lisent les **globales** `this`, `event`, `arg1`…`arg9`.

### H1.2 `SendChatMessage` / `SendAddonMessage` — [VÉRIFIÉ] (existence), [INFÉRÉ] (usage serveur)
Script `tools/client/func_table.py` : cherche la chaîne du nom puis un dword qui la référence, immédiatement suivi d'un pointeur dans `.text` (table d'enregistrement Lua nom → fonction C) :
```
SendChatMessage:  table va=0x843618 -> fonction 0x49f1e0
SendAddonMessage: table va=0x843620 -> fonction 0x49f920
GetPlayerMapPosition -> 0x4a8610 ; UnitExists -> 0x515fb0   (témoins)
```
Messages d'usage dans le client : `Usage: SendAddonMessage("prefix", "message" [,"type"])` (va 0x844b64). `SendAddonMessage` était déjà utilisable en 1.12.

Désassemblage de `0x49f920` (`tools/client/disasm_range.py`) :
- le type passe par la table de noms de `0x49f7a0` : SAY=0, PARTY=1, RAID=2, GUILD=3, OFFICER=4, YELL=5, WHISPER=6, EMOTE=8, CHANNEL=0x0E, AFK=0x14, DND=0x15, RAID_WARNING=0x58, BATTLEGROUND=0x5C ;
- `SendAddonMessage` n'accepte ensuite que les codes 1, 2, 3, 0x5C (**PARTY, RAID, GUILD, BATTLEGROUND**), sinon erreur `Unknown addon chat type` (va 0x844b44) — **pas de WHISPER ni CHANNEL** [VÉRIFIÉ par lecture du code] ;
- le texte (préfixe + message, assemblés via le format `0x844b5c`) est contrôlé pour les codes d'échappement `|` (`Invalid escape code in chat message`) puis envoyé via un paquet d'opcode `0x95` (= CMSG_MESSAGECHAT [INFÉRÉ]) avec langue `-1` (= LANG_ADDON [INFÉRÉ]) ;
- le type PARTY n'est envoyé que si deux globales (0xbc6f48 | 0xbc6f4c, probablement l'identité du groupe) sont non nulles [INFÉRÉ] ; GUILD/BATTLEGROUND n'ont pas ce test dans le code lu.

Usage « dot-command » : le champ de saisie envoie le texte tel quel, sans filtre côté Lua.
```lua
-- ChatFrame.lua:1950-1954 (ChatEdit_SendText)
SendChatMessage(text, type, editBox.language);
```
Donc `SendChatMessage(".build place 12", "SAY")` transmet ce texte au serveur ; son interprétation comme commande est du ressort du serveur [NON VÉRIFIÉ — serveur Wowlheim non testé].

Recommandation : canal principal = `SendChatMessage(".build …")` (aucune contrainte de groupe/guilde). `SendAddonMessage` (GUILD ou BATTLEGROUND) est une alternative **à valider** : le serveur doit intercepter les messages LANG_ADDON ; non testé.

### H1.3 Événements pour lire les retours — partiellement [VÉRIFIÉ]
Chaînes d'événements présentes dans `WoW.exe` (références dans le code, va) : `CHAT_MSG_SYSTEM` (0x852fe8), `CHAT_MSG_WHISPER` (0x853034), `CHAT_MSG_WHISPER_INFORM` (0x85301c), `CHAT_MSG_ADDON` (0x8530ac), `CHAT_MSG_PARTY/RAID/GUILD/CHANNEL`.
- `ChatFrame.lua:116-117` : `ChatTypeGroup["SYSTEM"] = { "CHAT_MSG_SYSTEM", … }` ; `:138-139` : WHISPER. Pour ces événements `arg1` = texte du message (`ChatFrame.lua` : `this:AddMessage(arg1, …)` pour SYSTEM).
- `CHAT_MSG_ADDON` : **aucune occurrence** dans le FrameXML ni les `Blizzard_*` extraits ⇒ aucune fenêtre de chat n'est enregistrée dessus, les messages d'addon n'apparaissent jamais dans le chat [INFÉRÉ de l'absence]. L'ordre des arguments (`arg1`=préfixe, `arg2`=texte, `arg3`=type, `arg4`=émetteur) n'a **pas** été vérifié dans le client [NON VÉRIFIÉ].
- Les retours d'une dot-command du serveur arrivent normalement en `CHAT_MSG_SYSTEM` [INFÉRÉ ; dépend du serveur].

### H1.4 Masquer des messages — [VÉRIFIÉ] (absence + mécanisme), non testé en jeu
- `ChatFrame_AddMessageEventFilter` : **absent** (0 occurrence dans tout `extracted/`, absent aussi de la table de fonctions). `hooksecurefunc` absent de `WoW.exe` également.
- Mécanisme réel : le modèle XML des fenêtres de chat route tous les événements vers une **globale résolue à l'exécution** :
  ```xml
  <!-- ChatFrame.xml:9-11 -->
  <OnEvent>
      ChatFrame_OnEvent(event);
  </OnEvent>
  ```
  Remplacer la globale `ChatFrame_OnEvent` par un wrapper qui `return` sans appeler l'original pour les messages ciblés les masque. `ChatFrame_OnEvent(event)` utilise `this`, `arg1`… ; le wrapper doit donc laisser ces globales intactes et appeler l'original avec `event`. Implémenté dans l'addon d'exemple.
- Alternative : ne pas masquer mais préfixer les retours serveur (`[WL] …`) et les rediriger vers `UIErrorsFrame:AddMessage` (utilisé par Blizzard, ex. `ContainerFrame.lua:753`).
- Risque : le client journalise `FrameXML is modified or corrupt` / `has corrupt signature` / `missing signature` (va 0x842f20…, `Logs\FrameXML.log`) → il existe une vérification de signatures (`FRAMEXML.TOC.SIG`, `BLIZZARD_*.TOC.SIG` dans les MPQ). Ça concerne les **fichiers** Blizzard ; surcharger une fonction à l'exécution depuis un addon ne modifie aucun fichier. Effet exact d'une signature invalide : [NON VÉRIFIÉ]. **Ne pas patcher le FrameXML dans un MPQ ; passer par un addon.**

### H1.5 Addon d'exemple
`tools/client/addon_example/Wowlheim/` (`Wowlheim.toc` avec `## Interface: 11200`, `Wowlheim.lua`). **Non installé dans le client.**
- `/wlbuild <id>` → `SendChatMessage(".build place <id>", "SAY")` ; `/wlbuilda <id>` → variante expérimentale `SendAddonMessage("WL", …, "GUILD")` ; `/wldebug` bascule l'affichage des retours masqués.
- Retours : événements `CHAT_MSG_SYSTEM`/`CHAT_MSG_WHISPER` dont le texte commence par `[WL]` (convention proposée au serveur) → `UIErrorsFrame`, masqués du chat via le wrapper de `ChatFrame_OnEvent`.
- Vérifications faites : syntaxe contrôlée avec Lua 5.1 (lupa, `tools/client/luacheck_syntax.py`) : OK, aucune construction interdite en 5.0 détectée par le script. **Pas** de Lua 5.0 disponible ⇒ la compatibilité 5.0 reste [INFÉRÉE] ; comportement en jeu [NON VÉRIFIÉ].
- Installation (à faire par l'utilisateur, plus tard) : copier le dossier dans `Interface\AddOns\` du client.

Risques H1 : sémantique des retours serveur à définir côté serveur ; `CHAT_MSG_ADDON` non testé ; un addon tiers qui surcharge aussi `ChatFrame_OnEvent` (chaînage possible, ordre de chargement).

---

## H2 — Patch MPQ : modèles, WMO, DBC

**Verdict : réalisable sur le principe, avec deux corrections au cahier** : (1) le format de modèle de ce client est **M2 version 256 stocké en `.m2`** (pas des fichiers `.mdx` dans les archives) ; (2) les `patch-<lettre>.MPQ` **sont** bien chargés. L'écriture de MPQ n'a **pas** de solution PyPI fiable ; un écrivain Python minimal a été développé et vérifié par relecture indépendante, mais **jamais chargé par le vrai client**.

### H2.1 Format des modèles — [VÉRIFIÉ]
- `DBFilesClient\GameObjectDisplayInfo.dbc` (extrait ; fournisseur effectif : `patch.MPQ`, 180 844 octets) : `WDBC`, **1638 enregistrements, 12 champs, taille d'enregistrement 48** (`tools/client/dbc_dump.py`). Champs (typage déduit, le DBC n'embarque pas son schéma) : `0 ID`, `1 ModelName` (offset de chaîne), `2..11` dix entiers « Sound » (213 enregistrements ont une valeur non nulle ; pas de boîte englobante en 1.12). IDs 1…6914.
  ```
  ['1', 'World\\Generic\\ActiveDoodads\\Chest02\\Chest02.mdx', '0', '1277', '0', …]
  extensions des chaînes: {'mdx': 1574, 'mdl': 31, 'wmo': 17}
  ```
- **Mais** les archives ne contiennent aucun `.mdx` : `mpq_layers.py find "\.mdx$"` → 0 ; `\.m2$` → 17 570 (model.MPQ 7816, patch.MPQ 9716, interface.MPQ 30, patch-2.MPQ 8). `World\Generic\ActiveDoodads\Chest02\Chest02.mdx` → introuvable ; `…\Chest02.m2` → présent (patch.MPQ), contenu `MD20`, **version 256**.
- Pont entre les deux, trouvé dans `WoW.exe` (fonction `0x706a50`, chaînes `Model2: Invalid file extension: %s` / `Model2: File not found: %s`, va ~0x873100) : recherche du dernier `.` du chemin ; si l'extension vaut `.mdl` ou `.mdx` elle est **réécrite en `.m2`** ; si elle vaut déjà `.m2` elle est acceptée ; sinon erreur. [VÉRIFIÉ par lecture du code ; non exécuté]. ⇒ Dans un patch il faut stocker les modèles sous leur nom `.m2` ; le DBC peut citer `.mdx` (convention du client) ou `.m2`.
- WMO : `wmo.MPQ`, ex. `World\wmo\Azeroth\Buildings\Big_Keep\Big_Keep.wmo` : fichier de chunks, premier chunk `MVER` (octets `REVM`), **version 17**. 8767 WMO dans les listfiles ; 17 référencés par `GameObjectDisplayInfo`.
- Les **outils d'édition de modèles/WMO** (création de M2 v256 / WMO v17 originaux) ne sont pas couverts ici : aucun outil open source fiable n'a été identifié ou testé [NON VÉRIFIÉ]. Hors périmètre de cette étude.

### H2.2 Ordre de priorité et chargement de `patch-<lettre>.MPQ` — [VÉRIFIÉ] (code lu) / [INFÉRÉ] (sens du tri, jamais exécuté)
Analyse de `WoW.exe` (`tools/client/exe_strings.py`, `xrefs.py`, `disasm_range.py`), fonction d'ouverture des archives à `0x403740` (source Blizzard citée dans une chaîne : `…\WowServices/PatchFiles.h`) :
- Chaînes : `patch.MPQ` (va 0x82edb0), **`patch-?.MPQ`** (va 0x82edbc), `Data\%s`, `Failed to open archive %s`. Le motif `?` est passé à une énumération de répertoire `Data\` : **toute lettre/chiffre unique** (`patch-2`, `patch-A`, … `patch-Z`) est trouvée.
- Les noms sont triés (comparateur `0x403ae0` = comparaison de chaînes **négée** ⇒ ordre décroissant [INFÉRÉ]), `patch.MPQ` est ajouté en fin de vecteur, puis le vecteur est parcouru **à l'envers** en ouvrant chaque archive avec une priorité croissante à partir de **0x40** (`call 0x648dd0(nom, priorité, 0, &handle)`, signature type `SFileOpenArchive`). Donc, du plus faible au plus fort : `patch.MPQ` (0x40) < `patch-2` (0x41) < … < `patch-Z` [INFÉRÉ].
- Archives de base (tableau va 0x82e12c, 10 entrées) ouvertes avant, priorités décroissantes **à partir de 0x3F** : `model` (0x3F) > `texture` > `terrain` > `wmo` > `sound` > `misc` > `interface` > `fonts` > `speech` > `dbc` (0x36). `base.MPQ` (chaîne `Data\base.MPQ`, va 0x85d484) : priorité non déterminée [NON VÉRIFIÉ]. `backup.MPQ` (présent dans `Data\`) n'est référencé par **aucune** chaîne de `WoW.exe` ⇒ non chargé [INFÉRÉ].
- Conséquence robuste quel que soit le sens exact du tri : **tout `patch-?.MPQ` a une priorité supérieure à `patch.MPQ` et aux archives de base** (patch.MPQ est toujours ouvert le premier des patchs). Pour surcharger `GameObjectDisplayInfo.dbc` (fourni par `dbc.MPQ` puis `patch.MPQ`, **pas** par `patch-2`), n'importe quel `patch-<x>.MPQ` suffit. Éviter de réutiliser `patch-2` et ne pas viser un nom qui dépend du sens du tri en cas de conflit entre deux de nos propres patchs.
- Les en-têtes bruts (`tools/client/mpq_headers.py`) : les archives de base sont en **format 0 (en-tête 0x20)** ; `patch.MPQ` (2 055 856 542 octets), `patch-2.MPQ` et `backup.MPQ` ont un **en-tête 0x2C (format 1)**. Le client livré lit donc des deux formes [INFÉRÉ : les patchs officiels sont là]. Pour nos archives, on utilise le **format 0**, celui des archives de base.
- Les **marqueurs de suppression** existent : `patch.MPQ` masque des fichiers des archives basses (flags de bloc `0x82000000`, ex. `Interface\FrameXML\AuctionFrame.lua`, 31 fichiers d'interface concernés) ; `mpq_layers.py` en tient compte (un fichier supprimé est signalé `SUPPRIME/ABSENT`). Un patch peut donc aussi retirer des fichiers.
- Simulation (hors client) : avec `WL_EXTRA_MPQ=extracted\out\patch-Z_zlib.mpq`, `mpq_layers.py` résout `GameObjectDisplayInfo.dbc` dans notre archive (1639 enregistrements) au lieu de `patch.MPQ` (1638). Ce n'est **pas** une preuve du comportement réel du client.

### H2.3 Outils MPQ — recherche faite, pas de solution d'écriture fiable
| Outil | Rôle | Statut |
|---|---|---|
| `mpyq` 0.2.5 (PyPI, pur Python) | lecture | **Installé** dans `tools/client/.venv`. Lit les 14 archives du client, y compris les en-têtes 0x2C. Limites : compression PKWARE/Huffman non gérée, suppose toujours une table de secteurs, ne gère pas `/` comme `\`. |
| `mpq` 1.1.1 (PyPI) | liaisons StormLib | **Non installé** : lecture seule (« Writing MPQs is not supported »), compile du C++ (`stormmodule.cc`) sans fournir StormLib. |
| `pystormlib` 0.1 (PyPI) | ctypes + `stormlib_x86.dll` embarquée | **Non installé** : DLL binaire 32 bits d'origine non vérifiable, inutilisable avec Python 64 bits, paquet abandonné (2015). Téléchargé uniquement dans le dossier temporaire de session pour inspection de ses métadonnées. |
| `stormlib` / `pystorm` (PyPI) | — | `stormlib` n'existe pas sur PyPI ; `pystorm` est un autre produit (Storm/Twitter). |
| StormLib (C++, MIT) / Ladik's MPQ Editor / `mpqcli` | écriture de référence | **Non téléchargés** (hors règles : seuls des paquets PyPI sont autorisés). Cités de mémoire : [NON VÉRIFIÉ]. StormLib reste la référence pour écrire des MPQ conformes ; à construire/télécharger plus tard avec l'accord de l'utilisateur. |
| `capstone` 5.0.9, `lupa` 2.8 (PyPI) | désassemblage / contrôle syntaxe Lua | Installés dans le venv (voir `requirements.txt`). |

**Écrivain maison** `tools/client/mpq_write.py` (spécification publique du format : table de chiffrement, hash de noms, tables hash/block chiffrées, fichiers compressés zlib par secteurs) :
- Test `mpq_roundtrip_test.py` (`roundtrip_test.log`) : crée `extracted/out/patch-Z_zlib.mpq` (GameObjectDisplayInfo.dbc modifié + un enregistrement ID 7000 ajouté par `dbc_append.py`, plus un fichier texte), puis **relit avec mpyq** (code indépendant du mien) : contenus identiques octet pour octet, `(listfile)` correct, recherche insensible à la casse. Résultat : OK. [VÉRIFIÉ : conforme à ce que lit mpyq]
- **Non vérifié** : acceptation par le vrai `WoW.exe`/Storm 5875. Le mode « fichiers bruts » (`compress=False`) est conforme à la spec mais illisible par mpyq : non validé, déconseillé tant qu'on n'a pas StormLib pour valider.
- Verdict outils : **lecture fiable (mpyq), écriture = pas de solution PyPI fiable ; piste de repli = StormLib/MPQ Editor, à valider en jeu.**

### H2.4 Risques H2
- Aucun test dans le client : un MPQ valide pour mpyq peut être refusé par Storm 1.12 (détail de table, `block size`, flags).
- Warden : des chaînes `WardenClient.cpp` / `WardenCachedModule` sont présentes dans `WoW.exe` ⇒ le client sait répondre à Warden. Un serveur qui l'active pourrait rejeter des MPQ modifiés [NON VÉRIFIÉ ; dépend du serveur].
- Distribution : un patch contenant des modèles ne peut contenir que des **assets créés par nous** (les assets Blizzard ne se redistribuent pas). Les DBC modifiés sont des dérivés de fichiers Blizzard : à générer localement chez chaque joueur (script) plutôt qu'à distribuer.
- Cohérence serveur/client : `gameobject_template.displayId` côté serveur doit correspondre aux IDs ajoutés au DBC ; les DBC du serveur (collision/vmaps) sont un chantier distinct.

---

## H3 — Prévisualisation « fantôme »

**Verdict : non faisable avec le client vanilla sans mod ; à traiter côté serveur. Évaluation uniquement (rien exécuté, rien téléchargé).**

Preuves (`func_table.py`, table de fonctions de `WoW.exe`) :
- **Présents** : `GetPlayerMapPosition` (0x4a8610), `SetMapToCurrentZone`, `GetCurrentMapZone`, `GetMapInfo`, `SetMapZoom`, `GetCursorPosition` (position **écran** du curseur), `GetMouseFocus`. Usage Blizzard : `local playerX, playerY = GetPlayerMapPosition("player");` (`WorldMapFrame.lua:334`, `Blizzard_BattlefieldMinimap.lua:203`).
- **Absents** (chaîne introuvable dans `WoW.exe`) : **`UnitPosition`**, **`GetPlayerFacing`**.
- Constat [VÉRIFIÉ pour la présence/absence ; sémantique INFÉRÉE] : l'API vanilla ne donne que la position **normalisée sur la carte** (x,y ∈ [0,1], sans altitude, sans orientation ; dépend de la carte affichée, d'où `SetMapToCurrentZone`) — insuffisante pour placer un fantôme précis ; aucune API de point visé au sol.
- Rendu : les widgets `Model`/`PlayerModel`/`DressUpModel` existent (`SetModel` 0x76d950, `SetFacing`, `SetPosition`, `SetCamera`, `SetModelScale`, `SetLight`). Ce sont des **cadres 2D à l'écran**, pas des objets 3D dans le monde : on pourrait, au mieux, afficher un aperçu du modèle dans une fenêtre (ex. choix de pièce), pas un fantôme aligné sur le terrain [INFÉRÉ].
- **SuperWoW** (de mémoire, NON TÉLÉCHARGÉ, NON VÉRIFIÉ) : mod de client (DLL chargée par/avec l'exécutable) qui étend l'API Lua (positions d'unités, GUID, etc.). Ce qu'il faudrait : modifier ou lancer le client d'une façon non standard (chargeur/DLL), fournir cette DLL à chaque joueur, vérifier précisément quelles fonctions de position/curseur-monde elle expose, et accepter le risque Warden/anti-triche et de maintenance. À évaluer seulement si la phase 5 l'exige ; **ne pas en faire une dépendance** du projet.
- Alternative réaliste [INFÉRÉ] : fantôme **côté serveur** (objet temporaire visible uniquement du joueur / créature d'aide) ou aperçu « snap » par commande ; pas d'API client à développer.

---

## Scripts et artefacts (`tools/client/`)
| Fichier | Rôle |
|---|---|
| `mpq_layers.py` | lecture seule des MPQ avec l'ordre de priorité déduit de `WoW.exe`, marqueurs de suppression, `order`/`find`/`extract`/`extract-re` |
| `mpq_headers.py`, `probe_mpq.py` | en-têtes bruts / sonde d'ouverture des MPQ |
| `exe_strings.py`, `func_table.py`, `xrefs.py`, `disasm_range.py` | analyse statique de `WoW.exe` (chaînes, table de fonctions Lua, références croisées, désassemblage capstone) |
| `dbc_dump.py`, `dbc_append.py` | lecture d'un DBC (typage deviné) / ajout d'un enregistrement GameObjectDisplayInfo |
| `mpq_write.py`, `mpq_roundtrip_test.py`, `roundtrip_test.log` | écrivain MPQ v1 minimal et test d'aller-retour via mpyq |
| `luacheck_syntax.py` | contrôle syntaxe Lua 5.1 + constructions interdites en 5.0 |
| `addon_example/Wowlheim/` | addon d'exemple (non installé) |
| `extracted/` | artefacts locaux du client (**ne pas distribuer**) ; `extracted/out/` = sorties de test |
| `extract_ui.log`, `extract_dbc.log` | journaux d'extraction |
| `.venv/`, `requirements.txt` | venv local : `mpyq==0.2.5`, `capstone==5.0.9`, `lupa==2.8` (PyPI, installés dans le venv uniquement) |

Installations : `python -m venv tools/client/.venv`, puis `pip install mpyq capstone lupa` **dans ce venv seulement**. Aucune installation globale, aucun service réseau, aucune modification du client ni de `C:\Wowlheim`. `pip download mpq pystormlib` : archives placées dans le dossier temporaire de session, jamais installées ni exécutées (inspection du contenu par lecture de l'archive).

---

## Synthèse et prochaines étapes (phase 5)
Vérifié : Lua 5.0 ; `SendChatMessage` et **`SendAddonMessage` existent** (types PARTY/RAID/GUILD/BATTLEGROUND seulement) ; événements `CHAT_MSG_SYSTEM`/`WHISPER`/`ADDON` présents ; pas de `ChatFrame_AddMessageEventFilter`, surcharge de `ChatFrame_OnEvent` possible d'après le XML ; modèles = `.m2` (MD20 v256) avec réécriture `.mdx/.mdl → .m2` dans le client ; WMO v17 ; `patch-?.MPQ` énumérés par le client ; `UnitPosition`/`GetPlayerFacing` absents.
Non vérifié : tout comportement en jeu (addon, masquage, `CHAT_MSG_ADDON`, chargement d'un patch par Storm, Warden côté serveur), sens exact du tri des patchs, priorité de `base.MPQ`, SuperWoW, outillage de création de M2/WMO.

À faire :
1. Test manuel par l'utilisateur : copier l'addon d'exemple dans `Interface\AddOns\`, vérifier `/wlbuild`, la réception `[WL]` et le masquage (ou ajuster).
2. Définir le protocole serveur : préfixe `[WL]` en `CHAT_MSG_SYSTEM`, ou interception LANG_ADDON (GUILD/BATTLEGROUND) ; décider si `SendAddonMessage` vaut le coup.
3. Obtenir StormLib (build local, validation par l'utilisateur) pour écrire un `patch-X.MPQ` de référence ; comparer à la sortie de `mpq_write.py` ; test réel du DBC modifié en jeu.
4. Pipeline de génération locale du DBC (ID ≥ 7000) + modèles originaux `.m2` (outil de création à choisir) ; accorder `displayId` serveur.
5. Fantôme : prototyper côté serveur ; ne considérer SuperWoW qu'en dernier recours.
