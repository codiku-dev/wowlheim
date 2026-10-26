# Wowlheim — Patch client au cœur (jalon technique phase 5)

Portée de ce document : `tools/client/dll/`, `tools/client/re/`, cette page. Le client analysé est
`C:\Users\rlebh.RLEBHAR.000\Desktop\WoW Vanilla\WoW.exe` (lu, jamais modifié) ; tout travail d'exécution a
eu lieu sur une copie à `C:\Wowlheim\client_test\` (créée pour ce jalon). `docs/CLIENT_FEASIBILITY.md` couvre
déjà addons/MPQ/M2 et n'est pas refait ici.

Légende : **[VÉRIFIÉ]** (preuve citée, souvent avec exécution réelle), **[INFÉRÉ]** (déduit du désassemblage,
non exécuté), **[NON VÉRIFIÉ]** (hypothèse, pas de preuve ici).

---

## 1. Outil d'analyse statique — Ghidra installé et branché à REA

**[VÉRIFIÉ]** Aucun fournisseur natif (Ghidra/Hopper/IDA) n'était installé. J'ai installé :

- **Ghidra 12.1.4** (`Ghidra_12.1.4_build`, tag GitHub `Ghidra_12.1.4_build`), dépôt officiel
  `NationalSecurityAgency/ghidra`. Archive `ghidra_12.1.4_PUBLIC_20260921.zip`, taille **569 649 598 octets**
  (≈ 543 Mio), URL :
  `https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/ghidra_12.1.4_PUBLIC_20260921.zip`.
  Somme SHA-256 publiée dans les notes de release GitHub : `ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db`.
  Vérifiée après téléchargement : **identique** (`sha256sum` local = valeur publiée). Installé dans
  `C:\Wowlheim\tools\ghidra`.
- **Microsoft OpenJDK 21.0.12** (JDK 21 complet, 64 bits — requis par Ghidra 12.1.x ; le poste n'avait que
  JDK 17). Archive zip officielle Microsoft `microsoft-jdk-21.0.12.1-windows-x64.zip`, taille **191 756 288
  octets** (≈ 183 Mio), URL `https://aka.ms/download-jdk/microsoft-jdk-21.0.12.1-windows-x64.zip`. Somme
  SHA-256 publiée par Microsoft (fichier `.sha256sum.txt` attenant) : `192441a9d27da813bada974bb88b4cf64d37a9589ed37f204374d411ca5ce07f`,
  vérifiée identique après téléchargement. Installé dans `C:\Wowlheim\tools\jdk21`
  (`winget install Microsoft.OpenJDK.21` proposait un `.msi` ; j'ai préféré le zip officiel Microsoft, même
  binaire, pour rester dans `C:\Wowlheim\tools` sans toucher au système).
- Variables d'environnement : `GHIDRA_INSTALL_DIR=C:\Wowlheim\tools\ghidra`,
  `JAVA_HOME=C:\Wowlheim\tools\jdk21`, `REA_ANALYSIS_PROVIDER=ghidra`.
- `npx --yes rea-agents@latest doctor --json` : tous les contrôles `ghidra-*` passent à `healthy`
  (installation, version 12.1.4, `analyzeHeadless.bat`, décompilateur natif `win_x86_64` reconnaissant
  `pe x86_64`, JDK 21 64 bits accepté, autorité native Windows vérifiée). **[VÉRIFIÉ]**

Rien n'a été exposé au réseau (pas de service, pas de port ouvert) ; seuls des fichiers locaux ont été écrits
sous `C:\Wowlheim\tools`.

### Méthode d'analyse effectivement utilisée

`rea analyze`/`function`/`decompile` passant par le fournisseur Ghidra fonctionnent (testé, `analyze` a
produit une Evidence JSON en ~2 min), mais pour l'exploration itérative (dizaines de requêtes
adresse → pseudocode / xrefs / chaînes) j'ai utilisé directement **Ghidra headless** via un petit script
Java de requêtes (`tools/client/re/ghidra_scripts/Q.java`, lecture seule — `-readOnly`, aucune modification
du projet Ghidra n'est conservée) piloté par `tools/client/re/pe.py` et `tools/client/re/callers.py`
(recherche de call-sites par motif `E8/E9 rel32` dans la section `.text`) pour localiser rapidement les
appelants. C'est un usage direct de l'installation Ghidra faite pour REA, pas un outil concurrent.

---

## 2. Table adresse → rôle (WoW.exe build 5875, ImageBase fixe `0x400000`, pas d'ASLR, ICF_x86)

Toutes les adresses sont des VA (virtual address) du binaire ; le fichier n'a pas de relogement, donc ce
sont aussi les adresses en mémoire au runtime **[VÉRIFIÉ]** (répertoire d'import à l'entrée PE, section
`.text` à VA `0x401000`, taille `0x3fddac`, lecture de l'en-tête PE).

| Adresse | Rôle | Preuve | Niveau |
|---|---|---|---|
| `0x843618` (table nom→fonction Lua, 50 entrées, `0x843618`–`0x8437a0`) | Table d'enregistrement des fonctions Lua natives (nom C puis pointeur de fonction) | `tools/client/re/pe.py` : motif `"NomDeFonction\0"` suivi d'un dword pointant une autre VA, elle-même suivie d'un pointeur dans `.text` ; 50 entrées contiguës de 8 octets, dont `SendChatMessage→0x49f1e0`, `SendAddonMessage→0x49f920` (voir `tools/client/func_table.py` dans `docs/CLIENT_FEASIBILITY.md`) | **[VÉRIFIÉ]** |
| `0x4a1a10` / `0x4a1a40` | Boucle qui appelle `lua_register` (`0x704120`/`0x704160`) sur chacune des 50 entrées de la table ci-dessus | Désassemblage : `MOV EDX,[ESI+0x84361c]; MOV ECX,[ESI+0x843618]; CALL 0x704120` en boucle `0..0x190` pas 8 → 50 itérations | **[VÉRIFIÉ]** |
| `0x704120` | **`lua_register`-like** : `__fastcall(nom, fonction)` — enregistre une fonction C comme API Lua globale (table `0x843618`→API « classique ») | Désassemblage de `0x704120` (5 appels internes Lua : push name/table/newcfunction/settable) ; même routine utilisée pour les 50 API connues (`SendChatMessage`, etc.) et pour `0x490250` (946 autres API, boucle `0x490276`) | **[VÉRIFIÉ]** |
| `0x704160` | Variante de `lua_register` pour un second groupe (préfixe différent) | Même structure, table source différente (`0x83de68` au lieu de `0x843618`) | **[INFÉRÉ]** |
| `0x490250` | **Table de 946 API Lua** (point d'enregistrement en masse, appelée au boot et au chaque reload d'UI) | Décompilation : boucle `uVar1<0x6c0` (946×8) appelant `0x704120` sur une table `0x83de68`; puis ~50 `CALL` directs vers des fonctions C (`FUN_004b82c0`, etc. — handlers additionnels) | **[VÉRIFIÉ]** |
| `0x48fe9c` | Site d'appel `CALL 0x490250` dans `FUN_0048fbf0` (init FrameXML, UI load) | `callers.py 490250` → `0x48fe9c` ; désassemblage confirme `CALL 0x00490250` | **[VÉRIFIÉ]** |
| `0x7039e0` | **`FrameScript_Initialize`** : crée un nouvel état Lua (`lua_open`+libs), initialise le VM et écrit son pointeur dans la globale `0x00ceef74` (lu par `0x7040d0 → MOV EAX,[0xceef74]`, utilisé par *tous* les accesseurs Lua C `lua_pushstring`/`lua_tostring`/etc.) | Désassemblage complet ; `DAT_00ceef74 = FUN_006f6d20()` en première instruction ; confirmé à l'exécution (voir §3 : journal donne `lua_State global [0xceef74]=0xB9...`) | **[VÉRIFIÉ]** |
| `0x402aee` | Site d'appel `CALL 0x7039e0` dans l'init moteur (`FUN_00402ad0`, lui-même appelé depuis le point d'entrée `0x401000`→…→`0x4029ea`) — **1er point d'accroche candidat : démarrage** | `callers.py 7039e0` → `0x402aee` ; chaîne d'appel `entrypoint 0x401000 → 0x4098c0 (CRT) → … → 0x402a00 → 0x402ad0 → 0x7039e0` | **[VÉRIFIÉ]** |
| `0x703b8e` | Site d'appel (en fait un `JMP` de fin de fonction, octet `0xE9`, pas `0xE8`) `0x7039e0` dans `FUN_00703b80`, lui-même appelé par `FUN_00402ad0` et rappelé par le code de **ReloadUI / changement de personnage** (reset de l'état Lua) — **2e point d'accroche : chaque (re)chargement de l'UI** | Désassemblage `0x703b80` : `if (DAT_00ceef74 != 0) { FUN_00703ba0(); JMP FUN_007039e0 }` (tail-call) | **[VÉRIFIÉ]** |
| `0x6f3690` | `lua_tostring`-like : `__fastcall(L, idx) -> const char*` | Utilisé par toutes les fonctions C de `SendChatMessage`/`SendAddonMessage` pour lire un argument Lua ; signature confirmée par l'usage dans la DLL (§3) | **[VÉRIFIÉ] (usage), [INFÉRÉ] (nom Lua standard)** |
| `0x6f3890` | `lua_pushstring`-like : `__fastcall(L, const char*)` | Même méthode | **[INFÉRÉ]** |
| `0x49f1e0` | **`SendChatMessage(text, type, language, target)`** — construit et envoie un paquet client→serveur, opcode **`0x95`** (poussé via `FUN_00418190(0x95)`) avec langue `-1` pour `.commande` normale, type résolu via `0x49f7a0` | Désassemblage complet (voir `docs/CLIENT_FEASIBILITY.md` §H1.2, repris et confirmé ici) ; `.build place 12` passe tel quel au serveur via ce chemin | **[VÉRIFIÉ]** |
| `0x49f920` | **`SendAddonMessage(prefix, msg, type)`** — même opcode `0x95`, langue `LANG_ADDON=-1`, type restreint à PARTY/RAID/GUILD/BATTLEGROUND (`1,2,3,0x5c`) | idem | **[VÉRIFIÉ]** |
| `0x51ab30` | Remplit la table globale « type d'événement Lua → nom de chaîne » (`CHAT_MSG_SYSTEM`, `CHAT_MSG_ADDON`, etc., ~70 entrées) | Décompilation (table d'assignations `_DAT_00beXXXX = s_CHAT_MSG_…`) ; `CHAT_MSG_SYSTEM` à VA chaîne `0x852fe8`, seule xref dans `0x51ab30` | **[VÉRIFIÉ]** |
| (réception) | **Pas de fonction unique « réception SMSG_MESSAGECHAT »** : les paquets réseau sont démultiplexés ailleurs (hors du périmètre exploré ici) puis le client appelle l'un des handlers Lua ci-dessus en poussant les arguments sur la pile Lua et en déclenchant l'événement `CHAT_MSG_SYSTEM`/`CHAT_MSG_WHISPER`/etc. (table `0x51ab30`) via le moteur de scripts (`FrameScript_SignalEvent`, non localisé précisément) | L'événement arrive côté Lua en `arg1`=texte (confirmé dans `ChatFrame.lua` extrait, §H1.3 de `CLIENT_FEASIBILITY.md`) ; le code natif correspondant (décodage du paquet entrant côté opcode réseau) n'a pas été isolé dans ce jalon | **[NON VÉRIFIÉ]** pour l'adresse précise de réception réseau ; **[VÉRIFIÉ]** pour l'arrivée côté Lua |

### (b) Rendu scène / aperçu fantôme — ce qui existe pour le « ground target »

> **Mise à jour (jalon aperçu fantôme) — voir `docs/GHOST_PREVIEW.md`, qui remplace ce tableau.** Analyse
> statique plus poussée : le client a un **aperçu fantôme natif** (modèle du gameobject sous le curseur
> pendant le ciblage au sol d'un sort d'invocation d'objet, globale `0xceca8c`), et la DLL l'utilise
> désormais pour l'API `WowlheimGhost*`. Corrections : `0x481790` est `CGWorldFrame::OnLayerUpdate` (par
> image), pas un gestionnaire de clic ; `0x480a50` est le test d'intersection avec les objets (le terrain/WMO
> passe par `0x672170`) ; `0x672190`/`0x672b60`/`0x6aa160` ne sont pas sur ce chemin ; l'entrée pour placer
> un modèle dans le monde est `0x6707c0` (et non `0x70ea00` directement). Le tableau ci-dessous est conservé
> pour l'historique.

| Adresse | Rôle | Preuve | Niveau |
|---|---|---|---|
| `0x480a50` (`CGWorldFrame::…`, fichier source `WorldFrame.cpp` d'après la chaîne `0x83dc98`) | Calcule le point d'intersection écran→monde (ray-cast) pour une position écran donnée : construit un rayon depuis la caméra (`0x7bca80` normalise un vecteur) à travers deux points écran transformés, teste la portée et renvoie une structure de collision (position 3D touchée) | Décompilation complète ; appelée depuis `0x7e50a0` et `0x480df0` | **[VÉRIFIÉ]** |
| `0x480df0` | Fonction « *GetGroundTarget*-like » : prend une position caméra et une position de visée, teste collision M2/WMO (`0x480a50`), sinon projette une distance fixe (comportement classique d'un « ground target » de sort type Blizzard/Fléau de givre/zone au sol) ; renvoie un vecteur normalisé + point d'impact | Décompilation complète ; code appelant `0x481190`, lui-même appelé par `0x481790` (reçoit un clic souris — voir ligne suivante) | **[VÉRIFIÉ] (mécanisme)**, **[INFÉRÉ] (identification comme « ground target » au sens Blizzard — pas de nom de symbole, le PDB n'est pas présent)** |
| `0x481790` | Gestionnaire d'un événement (probablement clic/relâcher de souris sur le monde, `WorldFrame.cpp`) qui appelle `0x481190` → `0x480df0`, puis selon le résultat appelle `0x4820f0` (cas 1) ou `0x4828d0` (cas 2) | Décompilation ; writes dans `DAT_0083dc2c` (état de mode visée ?) | **[VÉRIFIÉ] (flux de code)**, **[NON VÉRIFIÉ] (sémantique exacte « clic gauche terrain »)** |
| `0x6aa160`/`0x672190`/`0x672b60` | Famille de fonctions utilisées pour les **curseurs de sort au sol existants** (filtrage par distance/LoS avec masques `0xf000ff`/`0xf00f0f`, renvoi d'une fraction `0..1` le long d'un segment caméra→cible) | Décompilation ; `0x672b60` construit un vecteur caméra→cible, appelle `0x672190`→`0x6aa160`, renvoie une fraction utilisée pour positionner un point le long du rayon | **[INFÉRÉ]** (structure cohérente avec un test de portée/LoS pour un sort ciblé au sol, mais aucune chaîne ni nom ne confirme « spell ground cursor ») |
| `0x707350` / `0x706a50` | **Chargeur de modèle M2 par chemin** (`FUN_00707350("Spells\ErrorCube.mdx", flags)` → cache par hash de nom `0x706a50`, résolution MPQ `0x6477c0`) ; `0x70ea00` initialise une instance affichable (scène, position, flags) | Décompilation ; chaîne de secours `"Spells\ErrorCube.mdx"` (VA `0x860c9c`) utilisée quand le modèle demandé est absent — signature typique d'un chargeur de modèles génériques du moteur (dossier source `Engine/Source/Model2/M2Scene.cpp`, `M2Model.cpp` d'après les chaînes `0x8731d4`, `0x873240`) | **[VÉRIFIÉ] (chargement/cache M2)**, **[INFÉRÉ] (que c'est la voie pour un fantôme de pièce)** |

**Conclusion pratique pour l'aperçu fantôme [INFÉRÉ, non testé en jeu] :** le moteur a déjà (i) une projection
écran→monde complète et robuste (`0x480a50`/`0x480df0`, avec test de collision M2/WMO et filtrage par
portée), (ii) un chargeur de modèle M2 générique indépendant de tout sort (`0x707350`/`0x70ea00`) capable
d'afficher n'importe quel `.m2`/`.mdx` à une position 3D donnée. Une DLL injectée pourrait en théorie
réutiliser ces deux briques (hooker le message souris existant ou créer son propre tick qui lit la position
souris → `0x480df0` → position 3D → instancier un M2 via `0x70ea00` à chaque frame, le détruire si annulé)
sans réinventer le ray-casting. C'est une hypothèse d'architecture, **pas vérifiée à l'exécution** : aucun
rendu n'a été déclenché dans ce jalon (consigne : pas d'interaction GUI).

### (c) Table d'enregistrement Lua — cible pour nos propres API

Voir ligne `0x843618`/`0x704120`/`0x490250` ci-dessus. **Conclusion [VÉRIFIÉ à l'exécution, §3] :**
`FrameScript_RegisterFunction` = `0x704120`, signature `__fastcall(const char* nom, void* fonction_C)`.
Hooker l'un des deux sites d'appel de `FrameScript_Initialize` (`0x402aee` démarrage, `0x703b8e` chaque
reload d'UI) et appeler `0x704120` juste après l'original suffit à ajouter une API Lua, **sans toucher à la
table de 946 entrées existante**. Confirmé par l'exécution : `WowlheimPing()` ajoutée et appelée avec succès
depuis un chunk Lua exécuté par le client lui-même (§3).

### (d) Points d'accroche pour une DLL injectée

| Point | Évaluation |
|---|---|
| Début de `WinMain`/CRT (`0x4098c0`) | Possible mais précoce : le moteur Lua n'existe pas encore, aucune utilité directe pour patcher le Lua ; utile seulement pour un hook plus bas niveau (fenêtre, D3D). Non utilisé ici. |
| `DllMain` à l'injection (`LoadLibrary` avant reprise du thread principal, process `CREATE_SUSPENDED`) | **[VÉRIFIÉ]** C'est le point utilisé : pose les hooks CALL sur `0x402aee` et `0x703b8e` avant toute exécution de code applicatif, donc avant la première init Lua. Robuste car les deux sites sont dans `.text`, non auto-modifiés par le jeu avant ce point. |
| Site d'appel de `FrameScript_Initialize` (`0x402aee`, `0x703b8e`) | **[VÉRIFIÉ]** Hook de type « patch de CALL/JMP rel32 » (remplacement des 5 octets d'opcode+relatif par un saut vers notre trampoline). Choisi car (i) s'exécute une seule fois par (re)initialisation Lua donc faible risque de concurrence, (ii) permet d'enregistrer notre API après que le VM Lua soit prêt mais avant que l'UI ne commence à s'exécuter. |

---

## 3. Preuve de concept d'injection — résultat de test [VÉRIFIÉ, exécuté]

Fichiers : `tools/client/dll/wowlheim_client.cpp` (DLL), `tools/client/dll/launch.cpp` (lanceur),
`tools/client/dll/build.bat` (compilation x86 via VS Build Tools 2022, `vcvars32.bat`).

**Exécuté sur la copie** `C:\Wowlheim\client_test\WoW.exe` (copie intégrale du client original, ~5,2 Go,
`sha256sum` identique à l'original avant tout patch ; jamais exécuté ni modifié dans le dossier Desktop
d'origine). `realmlist.wtf` pointe déjà vers `127.0.0.1`, mais **aucune tentative de connexion au serveur
n'a été faite** (aucune interaction GUI, consigne respectée) ; la DLL force la fermeture du processus après
quelques secondes, bien avant tout écran de connexion visible.

### Ce que fait la DLL
1. `DllMain(DLL_PROCESS_ATTACH)` : vérifie d'abord (lecture de deux chaînes connues à VA fixes) que le
   processus hôte est bien WoW 1.12.1 build 5875 — sinon elle ne touche à rien.
2. Pose deux hooks (patch de 5 octets `E8/E9 rel32`) sur les deux sites d'appel de `FrameScript_Initialize`
   identifiés en §2(d). Écrit une ligne de journal pour chaque hook posé, avec vérification préalable des
   octets attendus (si la cible ne correspond pas, la DLL **n'écrit rien** et journalise une erreur).
3. Dans le hook, après avoir laissé s'exécuter l'initialisation Lua d'origine, enregistre une API Lua de
   test `WowlheimPing(texte)` via `FrameScript_RegisterFunction` (`0x704120`), qui journalise l'appel et
   renvoie `"pong"`.
4. **Validation sans interface graphique** : juste après l'enregistrement, la DLL fait exécuter par le
   client lui-même (via `FrameScript_Execute`, `0x704cd0`) un petit script Lua qui appelle
   `WowlheimPing(...)` deux fois et journalise le retour — remplaçant l'« addon de test » prévu dans la
   consigne par un appel direct, plus simple et tout aussi probant pour ce jalon.

### Contrainte découverte et contournée : validation de pointeur de fonction Lua
Premier essai (hook sur `0x48fe9c`/`0x490250`, enregistrement direct de l'adresse de la fonction C dans la
DLL) : **échec reproductible**, crash immédiat du client avec
`ERROR #134 (0x85100086) Fatal Condition — Invalid function pointer: <adresse DLL>` (journal de crash
`Errors/*.txt` du client). Analyse (`0x42a320`/`0x42a380`, lecture seule) : WoW valide **chaque** pointeur
de fonction C passé à l'API Lua interne et exige qu'il tombe dans la section `.text` de `WoW.exe`
(`[0x401000, 0x7fedac)`) — un pointeur vers une DLL externe est toujours rejeté. **[VÉRIFIÉ, avec preuve
d'échec puis de correction]**

Contournement appliqué (robuste, minimal) : écriture d'un trampoline de 7 octets (`JMP rel32` vers la
fonction réelle dans la DLL) dans une **cave de padding `0xCC`** repérée dans `.text` (VA `0x75d401`, 63
octets de remplissage inutilisés entre deux fonctions, vérifiés `0xCC` avant écriture) ; c'est l'adresse du
trampoline (dans `.text`, donc valide pour le contrôle `0x42a320`) qui est enregistrée comme fonction Lua.
C'est un **patch mémoire minimal du binaire original** (aucune réécriture de code existant, seulement un
octet mort converti en saut), conforme à l'esprit « patcher le client au cœur ».

### Résultat du run final (`test_run3.log`, journal complet `wowlheim_client.log` reproduit) :
```
DllMain DLL_PROCESS_ATTACH  processus="C:\Wowlheim\client_test\WoW.exe"  dll="...\wowlheim_client.dll"
hook pose en 0x00402aee (CALL 0x007039e0 -> Hook_InitLua)
hook pose en 0x00703b8e (CALL 0x007039e0 -> Hook_InitLua)
FrameScript_Initialize termine (retour 1), lua_State global [0xceef74]=0xB9...
WowlheimPing enregistree (trampoline .text a 0x0075d401 -> DLL 0x6a2b1340)
Lua->DLL WowlheimPing #1 arg="hello from lua 2"
Lua->DLL WowlheimPing #2 arg="retour=pong"
auto-test Lua termine ; WowlheimPing appelee 2 fois
```
Le lanceur (`launch.exe`) a ensuite attendu, confirmé la présence de la ligne `DLL_PROCESS_ATTACH`, puis
**terminé** `WoW.exe` lui-même (`TerminateProcess`) sans jamais afficher ni piloter l'interface.
**[VÉRIFIÉ] : injection réussie, hook posé, API Lua enregistrée et exécutée avec succès depuis du Lua
exécuté par le client lui-même, sans aucune intervention GUI.**

Garde-fous du lanceur : refuse de s'exécuter si le chemin de `WoW.exe` ne contient pas `client_test` (donc
ne peut pas viser accidentellement le client original) ; vérifie l'existence de la DLL avant de lancer.

---

## 4. Risques — évaluation honnête

### Détection Warden côté serveur [lecture seule de `C:\Wowlheim\src\mangos-classic\src\game\Anticheat`]

**[VÉRIFIÉ]** Le serveur CMaNGOS-classic local a un module Warden complet et actif par défaut
(`Warden.Enable = 1` dans `anticheat.conf.dist.in`), avec au démarrage **89 scans** chargés depuis la table
SQL `warden_scans` (`sql/updates/mangos/z2778_01_mangos_anticheat.sql`) + 9 « scripted » depuis le module
anticheat (log serveur `run/mangosd.out` : « 89 Warden scans loaded from world database », « 9 scripted
Warden scans loaded »).

Les scans SQL observés sont de deux types pertinents ici :
- **`READ_MEMORY` (type 0)** : la majorité (ids 1–54+ observés) — lecture d'octets à une **adresse fixe du
  binaire client** (ex. id 8 : offset `8151666` = `0x7c69b2`, 4 octets attendus `D893FEC0`, commentaire
  « Jump gravity ») et comparaison à une valeur attendue. Ce sont des signatures de patchs de triche connus
  (vol/no-clip/fly hack/etc.), **à des adresses précises et des octets précis**, pas une vérification
  générique d'intégrité de tout `.text`. Aucune des adresses observées dans l'échantillon lu ne correspond
  à nos sites de hook (`0x402aee`, `0x703b8e`) ni à notre cave (`0x75d401`) — mais le serveur peut en
  ajouter à tout moment via la base de données, et c'est exactement le mécanisme qui **détecterait** notre
  patch si quelqu'un y ajoutait une entrée aux bonnes adresses. **Notre patch modifie des octets `.text` à
  des adresses non couvertes par les 89 scans actuels [VÉRIFIÉ pour l'échantillon lu], mais rien n'empêche
  structurellement d'en ajouter [INFÉRÉ sur l'architecture générale, confirmé par le code de `wardenscanmgr.cpp`].**
- **`FIND_MODULE_BY_NAME` (type 2)** : 3 scans observés (ids 5–7) recherchent par **nom de module exact**
  (haché HMAC-SHA1 avec seed, comparé côté client par le module Warden livré au client — voir
  `wardenscan.cpp::WindowsModuleScan`, utilise `GetModuleHandle`) des DLL connues d'outils de triche
  (« Cheat Engine dll », « WPE PRO dll », « rPE dll ») et, dans le code (`wardenwin.cpp:1002`), un scan
  codé en dur pour `prxdrvpe.dll`. **Notre DLL s'appelle `wowlheim_client.dll`, nom absent de tout scan
  existant** [VÉRIFIÉ pour les scans lus] — mais si l'opérateur du serveur Wowlheim ajoute volontairement
  une entrée `FIND_MODULE_BY_NAME` pour `wowlheim_client.dll` (ce qui est le but recherché une fois le
  projet officiel), Warden la détecterait **à coup sûr**, car ce scan cherche un nom de module chargé, peu
  importe ce qu'il fait. C'est cohérent avec l'objectif du projet : **c'est précisément le canal par lequel
  le serveur Wowlheim pourra plus tard *exiger* la présence de notre DLL (liste blanche) plutôt que la
  bannir**, à condition d'inverser la sémantique `wanted` (le scan `WindowsModuleScan` prend un booléen
  `wanted` — `true` = la DLL doit être présente, pas absente). **[INFÉRÉ sur l'usage futur, vérifié sur le
  mécanisme : `WindowsModuleScan(module, wanted, ...)`, la mécanique est symétrique]**.
- Les scans de hash de code (`FIND_CODE_BY_HASH`/`FIND_MEM_IMAGE_CODE_BY_HASH`) et `API_CHECK` existent dans
  le module mais aucune entrée SQL observée dans l'échantillon lu ne les utilise ; ils pourraient en théorie
  détecter un hook sur un site précis si une entrée était ajoutée pour l'adresse `0x402aee`/`0x703b8e`.
  **[NON VÉRIFIÉ]** (pas d'entrée actuelle, juste une capacité du module).

**Conclusion risque Warden [INFÉRÉ] :** avec la configuration serveur actuelle (89+9 scans ciblant des
patchs de triche connus et 3 DLL d'outils tiers connus), notre DLL et nos deux hooks ne seraient
**probablement pas détectés en l'état**. Mais Warden est conçu précisément pour ce cas d'usage (recherche de
module par nom, lecture mémoire à adresse fixe) : le jour où quelqu'un d'autre ajoute une règle ciblée
(nom de notre DLL, ou octets à `0x402aee`), la détection est immédiate et fiable côté serveur. Comme le
projet Wowlheim contrôle son propre serveur, la voie recommandée est d'**ajouter nous-mêmes** une entrée
`FIND_MODULE_BY_NAME(wowlheim_client.dll, wanted=true)` pour *exiger* la DLL plutôt que risquer qu'elle soit
un jour bannie par erreur.

### Solidité du patch [VÉRIFIÉ sur ce build précis, limites honnêtes]

- Toutes les adresses sont **codées en dur pour le build 5875 uniquement** ; elles cassent sur tout autre
  build/version du client (pas de résolution par signature de bytes/pattern-scan dans ce PoC — à ajouter
  avant un usage en production).
- Le garde-fou `LooksLikeWow5875()` vérifie deux chaînes de référence avant de patcher quoi que ce soit, ce
  qui évite un crash sur un exécutable différent, mais ne garantit pas que le *layout* interne n'ait pas
  légèrement varié entre sous-versions du même build (peu probable pour 5875, qui est figé depuis 2006,
  mais non prouvé formellement).
- Le hook patch 5 octets de code à deux endroits fixes (six depuis l'aperçu fantôme : `0x48184a`,
  `0x66fc45`, `0x6920cc`, `0x4821c5` en plus, voir `docs/GHOST_PREVIEW.md`) et des caves de padding `0xCC`
  (0x75d401, 63 octets, 7 trampolines de 8 octets ; 0x75f048, 56 octets, 2 trampolines) :
  fonctionnel mais fragile si plusieurs patchs veulent utiliser la même cave sans coordination. À
  terme, mieux vaut allouer la mémoire exécutable nécessaire via `VirtualAllocEx`/`VirtualAlloc` dans le
  process cible plutôt que de dépendre d'une cave de padding.
- Pas de gestion de **unload** propre de la DLL (les hooks ne sont jamais retirés ; `DLL_PROCESS_DETACH`
  se contente de journaliser).
- Le patch ne touche à aucun fichier sur disque (patch mémoire uniquement, posé à l'injection) : le binaire
  `WoW.exe` sur disque reste bit-à-bit identique à l'original, y compris dans `client_test` (vérifié
  `sha256sum` avant toute injection).

---

## Résumé final

**Vérifié avec preuve :**
- Ghidra 12.1.4 + JDK 21 installés et fonctionnels avec REA (`rea doctor` healthy sur tous les contrôles
  `ghidra-*`), sources/sommes de contrôle citées ci-dessus.
- Table d'enregistrement des API Lua localisée (`0x843618`, 50 entrées « classiques » + table de 946 à
  `0x83de68` via `0x490250`), fonction d'enregistrement `FrameScript_RegisterFunction = 0x704120`.
- `SendChatMessage`/`SendAddonMessage` et la table des types de chat (`0x49f1e0`, `0x49f920`, `0x49f7a0`)
  confirmés par désassemblage (reprend et confirme `docs/CLIENT_FEASIBILITY.md`).
- Deux points d'accroche DLL identifiés et exploités avec succès à l'exécution (`0x402aee`, `0x703b8e`,
  tous deux appelant `FrameScript_Initialize = 0x7039e0`).
- DLL d'injection fonctionnelle : hook posé, API Lua `WowlheimPing()` enregistrée **et appelée avec succès
  depuis du Lua exécuté par le client lui-même**, journal complet reproduit ci-dessus.
- Contrainte de validation de pointeur de fonction (`0x42a320`) découverte, comprise et contournée par un
  trampoline dans une cave de code.
- Mécanisme Warden serveur lu (lecture seule) : scans actuels ne couvrent ni nos adresses de hook ni notre
  nom de DLL ; le mécanisme `FIND_MODULE_BY_NAME` est symétrique et pourrait servir à *exiger* notre DLL.

**Non vérifié (hypothèses à tester plus tard, hors périmètre « pas d'interaction GUI ») :**
- Adresse précise de réception réseau de `SMSG_MESSAGECHAT` côté natif (seule l'arrivée côté Lua est
  confirmée).
- Identification formelle de `0x480df0`/`0x6aa160` comme étant le code du « ground target » de sort
  Blizzard (cohérent par structure, pas confirmé par nom/chaîne/test visuel).
- Comportement réel en jeu (rendu, connexion serveur, chat visible) — aucune interaction GUI n'a été faite,
  conformément à la consigne.
- Stabilité du patch sur une session de jeu complète (le test dure quelques secondes puis termine le
  processus).

**Étapes suivantes proposées :**
1. *(Fait statiquement, non testé en jeu — voir `docs/GHOST_PREVIEW.md` : API `WowlheimGhostShow/Rotate/Hide/
   GetPos/SetColor`, vérification `tools/client/dll/verify_addrs.py`.)* Texte d'origine : Aperçu fantôme : hooker l'event souris déjà utilisé par `0x481790` (ou créer un hook de tick qui lit la
   position souris + `0x480df0`) pour instancier un modèle M2 propre à Wowlheim (pas un asset Blizzard)
   via `0x70ea00`/`0x707350`, en mode « non collisionnable », détruit à chaque frame si annulé — nécessite
   des tests avec rendu actif, donc une étape GUI qui sort de ce jalon.
2. Canal client-serveur propre : soit (a) continuer sur `SendAddonMessage`/`CHAT_MSG_ADDON` en l'enregistrant
   explicitement côté serveur Wowlheim (CMaNGOS-classic doit écouter les paquets `LANG_ADDON`), soit (b) une
   fois l'API Lua interne confirmée exploitable (ce jalon le prouve), exposer directement depuis la DLL une
   paire d'API `WowlheimSend(table)`/callback `WowlheimOnMessage` qui parle un petit protocole binaire
   au-dessus du même opcode `0x95`, en coordination avec un handler ajouté côté serveur.
3. Remplacer les adresses codées en dur par une résolution par signature d'octets (pattern-scan), pour
   survivre à un éventuel changement mineur de build.
4. Ajouter côté serveur une entrée Warden `FIND_MODULE_BY_NAME(wowlheim_client.dll, wanted=true)` dès que
   la DLL est stabilisée, pour transformer Warden en vérification positive plutôt que risque de détection.
