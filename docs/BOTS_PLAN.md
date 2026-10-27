# Bots joueurs (playerbots + LLM) : plan et état

> **Décision de Robin (2026-10-26, soir)** : le test de recette final passe de 1 h à **30 min** (« oui réduis »).

## TEST FINAL DE 30 MIN : RÉUSSI (2026-10-26 23:44 → 2026-10-27 00:14)

Serveur principal fusionné (Valheim + playerbots + pont LLM Gemma 4 12B), `WL_TARGET=main python -I bots/tests/soak_bots.py --minutes 30` : **30,1 min, serveur vivant, 0 plantage** ; 100 bots en ligne du début à la fin, **100/100 ont joué** (niveau, XP, argent, position) ; 2 joueurs connectés tout du long (WLTEST /dire à Comté-de-l'Or, WLTEST2 chuchotements) ; tick moyen **50,1 ms**, max 55 ms ; RAM 1,97 → 2,45 Go ; **0 objet Valheim chez les bots** aux 3 relevés ; pont : 10 réponses `ok` (chuchotements 6/6, /dire 4/6 — les 2 autres repris par un autre bot ou hors portée, anti-spam `deja_pris` ×3). Exemples reçus : « bof peu d'xp ici », « oui c'est top le paladin est super solide », « Je suis niveau 3 :/ ». Résumé : `C:\Wowlheim\bots\state\soak_resume.json`.

## Serveur unique (Valheim + bots), 2026-10-26 nuit

- Fusion : serveur principal `C:\Wowlheim\run` (ports 3724/8085, bases principales) = cœur Wowlheim + playerbots + `bots/playerbots.patch`, intégré par `bots/server/integrate_main.py` (étapes module, cmake, sql, conf, deploy, shortcut ; rejouable) ; essai isolé préalable vert (`.build api list` 162/162, pièce posée, hêtre abattu, 100 bots, réponse du pont).
- Les bots n'ont aucun objet Valheim (≥ 9 000 000) : butin laissé aux joueurs, aucune autre source, filet toutes les 30 s, retrait à la création, SQL `bots/sql/remove_bot_valheim_items.sql` ; 468 objets laissés au butin en 10 min, 0 chez les bots.
- Plantage 1 (23:14, test 30 min) : `ItemUsageValue::QueryItemUsageForEquip`, mon test « objet Valheim » lisait `itemProto->ItemId` avant le contrôle de nullité ; trouvé par désassemblage (instruction `cmp [rdi], 0x895440` = 9 000 000), corrigé.
- Plantage 2 (23:40, instance en double lancée par un script résiduel) : `PlayerbotAI::GetMaxPreferedGuildSize` (amont playerbots) déréférençait un membre de guilde absent ; corrigé, ainsi que 3 autres accès identiques (GuildManagementActions ×2, Talentspec). Binaire principal désormais compilé avec symboles (`mangosd.pdb` dans `run`).
- `integrate_main.py` : les SQL monde du module sont rejoués avec `--force` (clé en double dans `ai_playerbot_travel_nodes.sql` amont).

## État au 2026-10-26, 20:45 (le plus récent) — après les retours de Robin en jeu

Retours de Robin : bots qui ne s'arrêtent pas quand on leur parle, réponses lentes (10–20 s) ou absentes, phrases toutes faites d'assistant, annonces absurdes dans Général, personne autour de lui, bots qui se téléportent. Corrigé et mesuré (session « joueur » `bots/tests/playtest.py`, sonde `bots/tests/converse_probe.py`, population `bots/tests/near_player.py`) :

| Point | Avant | Après |
|---|---|---|
| Réponse aux chuchotements | 1/9 répondus dans la session de base ; ailleurs 5/10, médiane 7,2 s, max 13,5 s | 10/10, médiane 0,9 s ; sessions : 9/9 à 0,9 s (Herna, Leanderolo) |
| /dire à côté d'un bot | 1/3 réponse, le bot continue sa route (85 m), dos au joueur | 0 m parcouru, face au joueur, réponses en 0,9–1,5 s, reprise de l'activité 26 s après |
| Message reçu en combat | jeté | mis de côté, réponse à la fin du combat (3,1 s, 9,4 s) |
| À qui s'adresse un /dire | seulement si le nom est cité | + bot ciblé par le joueur, + bot le plus proche à moins de 8 m |
| Ce qu'il fait / sa quête | invente (« quêtes de l'abbaye » sans quête) | quêtes réelles avec progression ; lien cliquable en jeu « [Beer Basted Boar Ribs] pour des côtes de sanglier. » ; sans quête : « Je n'en ai aucune. » |
| Textes prédéfinis de playerbots | annonces de butin, « mes poches sont vides », inventaire chuchoté, salutations d'assistant | tous coupés (`WowlheimNoCannedChat`, config, SQL) ; 0 message non sollicité en 3 × 45 s d'écoute |
| Ton | « je peux t'aider pour les premières quêtes » à un inconnu | sobre, réagit seulement à ce qu'on dit, 47 caractères en moyenne |
| Téléportation vers le joueur | « tu me rejoins » → téléportation | jamais : le bot vient à pied (non vérifié en jeu) |
| Population autour de Gogo (niv. 1, Comté-du-Nord) | 1 bot à < 300 m, 0 dans sa zone, 5 bots de niveau ≤ 9 | 7 à < 300 m, 15 dans sa zone, 40 de niveau ≤ 9 (100 bots, niveaux calés sur les joueurs) |

Reste / limites : les répliques restent sobres, parfois plates (Jev « écrit par un humain » ≈ 0,6) ; le bot qui court hors de portée de dire (~25 m) n'entend pas ; venir à pied et entrer seul en instance non vérifiés en jeu ; `LogFileLevel = 2` (traces de diagnostic, ~2 Mo/min de journal) ; test d'1 h à refaire.

## État au 2026-10-26, 18:55

**Objectif de Robin** : en jeu, avoir l'impression de jouer avec des joueurs humains qui réagissent, comprennent et vivent.

| Sujet | État | Preuve |
|---|---|---|
| Modèle LLM | **Gemma 4 12B QAT, sans raisonnement** (`reasoning_effort: none`) ; un seul modèle chargé | Banc de 14 dialogues multi-tours (`bots/tests/eval_chat.py`), notés par TypeSafe Jev (`bots/tests/jev_judge.py`, probabilité « écrit par un humain » et scores sur 4). Nemotron : 0,52 humain / 2,37 compréhension / 2,6 s ; Gemma 12B : 0,62 / 3,48 / 0,56 s ; Saluki 27B : 0,58 / 3,31 / 0,59 s ; Gemma 26B Uncensored : meilleur sur 5 dialogues (0,66 / 3,70) mais 18 Go, 3,5 Go de RAM libres ; LFM 2.5 24B : inutilisable (18/25 réponses vides). Fichiers `C:\Wowlheim\bots\state\eval\*_jev.json`. |
| Qualité du chat (prompt) | **Amélioré, mesuré** | Gemma 12B, dernière version (v6) : 0,63 humain, compréhension 3,67, naturel 3,28, personnage 3,09. Gains : questions perso (3,23 → 3,85), mémoire (2,24 → 3,71 : « tu m'as dit que tu t'appelais robin »), connaissances du jeu (druide : forme de voyage niveau 30 chez l'entraîneur, ours à Reflet-de-Lune). Faiblesse restante : « t'es un bot ? » donne des réponses neutres pour les profils timides. |
| État de jeu dans le chat | **Fait** | `gamestate.py` : or, quêtes en cours, groupe avec l'interlocuteur, heure ; zones en VF (`zones_fr.py`, 99 noms). |
| Base de connaissances vanilla | **Fait** | `knowledge.py` + `knowledge_vanilla.json` (168 faits vérifiés : entraîneurs, quêtes de classe, montures, donjons, zones, métiers, raids) injectés seulement si la question les concerne ; 24 tests. |
| Ordres en français libre | **Vérifié en jeu** | « tu viens on va aux mortemines ? » → intention `aller_donjon` (confiance 1,0) → `follow` ; le bavardage reste `discussion` sans action (`intent_log.jsonl`, `quick_check`). Phrases exactes (« suis-moi », « reste là »…) traduites sans réseau (`WowlheimFrenchCommands.h`, 88 cas testés). |
| Suivi du chef au loin / en instance | **Vérifié en jeu, sans « summon »** | Charo (niv. 16) à 2 614 m : arrive seul à l'entrée des Mortemines (1,8 m), puis dans l'instance (carte 36, 1,9 m) — `group_probe.py`. Le combat du bot ne remet plus le délai à zéro (non vérifié en jeu). |
| Silence en combat | **Vérifié en jeu** | Charo en combat (paquets SMSG_ATTACKERSTATEUPDATE) : aucune réponse en /groupe ni en chuchotement, aucune requête au pont ; hors combat, réponse en 15 s. |
| Textes en français | **Vérifié en jeu** (tables) ; 80 réponses codées en dur traduites | « Coucou ! », « Je te suis », « Je reste là »… ; restent en anglais : noms de quêtes, d'objets, de factions (aucune donnée FR disponible). |
| Bots qui parlent d'eux-mêmes en groupe | **En cours** | Route `/spontaneous` du pont faite et testée (silence, montée de niveau, mort, élite, zone, donjon ; 4 min par bot) : « enfin le niveau 19 mdr on y est presque ». Branchement C++ en cours. |
| Stabilité | **30 min sans plantage** avec 45 bots + 2 joueurs (test d'endurance coupé à 30 min à la demande de Robin pour avancer) | `C:\Wowlheim\bots\state\soak.log` : tick 50 ms, 47–54 bots. Le test d'1 h reste à faire en fin de développement. |

## État au 2026-10-26, 17:30

| Sujet | État | Preuve |
|---|---|---|
| 45 bots qui jouent | **Vérifié** | 50 bots en ligne (45 aléatoires + chefs de guilde), tous actifs (`botActiveAlone = 100`). Entre 16:52 et 17:08 : **50/50 ont changé** (XP jusqu'à +4 150, quêtes prises, zones, argent) — `bot_activity.py diff activity_165219.json activity_1708*.json`. Tick moyen 50 ms (plancher), 2,7 Go, ~17 % d'un cœur. |
| /dire au milieu des bots | **Vérifié** | à Comte-de-l'Or, un seul bot répond (Gengeanvi), le second est bloqué par l'anti-spam (`deja_pris`) — `test_pass.py`. |
| Canal Général | **Vérifié** | message qui nomme Valando : réponse « juste quetes ok » en 5,3 s ; Gengeanvi se tait (`adresse_a_un_autre`). Sans nom, silence voulu à 65 % (`hasard`). |
| Chuchotement à un bot éloigné | **Vérifié** (corrigé) | Kedries, en Sombrivage : « bien le bonjour qu'Elune te guide à Darkshore Mist's Edge » en 13,6 s. |
| Groupe + donjon | **Vérifié, avec « summon »** | `bots/tests/group_probe.py` (compte WLTEST2) : invitation acceptée (`SMSG_GROUP_LIST`, table `group_member`), réponse en /groupe via le LLM (« mortemines ok mais faut trouver une arme dabord »), bot sur la carte 36 (Mortemines) après le chuchotement « summon ». Sans « summon », le bot ne prend pas le portail. `NonGmFreeSummon = 1` pour que Robin (non MJ) puisse le faire. |
| Textes prédéfinis en français | **Appliqué, pas encore observé en jeu** | 1 943 textes traduits (colonne `text` + `text_loc2`, base `classicmangos_bots` seulement ; sauvegarde `C:\Wowlheim\bots\backup_ai_playerbot_texts.sql`) ; `bots/sql/check_texts_fr.py` : 0 ligne sans FR, 0 placeholder cassé. playerbots ne choisit pas la langue par config : la colonne `text` est remplacée. |
| Personnalités | **Fait, tests OK** | `persona.py` réécrit : 41 styles distincts sur 45 bots, 2/45 profils à smileys, 6/45 en RP léger ; `test_persona.py` (11 tests) et `test_bridge.py` (12 tests) OK ; relecture et répliques réelles dans `docs/BOTS_PERSONAS.md`. Pont : consignes de forme, smileys retirés si `smileys = jamais`, mots méta (vanilla, serveur privé…) bloqués, `max_tokens` 800. |
| Silence en combat | **Codé, pas vérifié en jeu** | patch playerbots : en combat, ni LLM ni réponse toute faite (`SayAction.cpp`, dans `bots/playerbots.patch`). |
| Ordres en phrase libre (« tu viens on va aux mortemines ? ») | **Codé, compilé, pas vérifié en jeu** | chuchotement ou /groupe d'un vrai joueur (maître, groupe ; inconnu = invitation seulement) sans ordre FR exact → `POST /intent` du pont en asynchrone → TypeSafe Jev (`choice`, seuil 0,8) → commande playerbots (`follow`, `stay`, `attack`, `summon`, `invite`, `leave`, `trade`, `loot`, `give leader`) exécutée sur le thread du bot ; donjon et quête ensemble = `follow` (ou `invite` hors groupe). `bots/llm_bridge/intent.py`, `test_intent.py` ; journal `intent_log.jsonl` ; coupure : `--no-intent` ou fichier `C:\Wowlheim\bots\state\intent_off`. |

Reste : bot qui suit seul son chef en instance (aujourd'hui « summon ») ; bot resté dans l'instance après dissolution du groupe (non vérifié) ; vérifier en jeu le silence en combat et les textes FR ; arrêt propre par le fichier `stop` qui n'aboutit pas toujours en 90 s (arrêt forcé utilisé) ; soak 1 h avec 2 joueurs (jalon 6) ; intégration au serveur principal (jalon 5). Latence du pont : médiane 6,4 s sur ce passage (contre 2–4 s avant `max_tokens` 800, à surveiller).

## État au 2026-10-26, 16:45 (historique)

| Jalon | État | Preuve |
|---|---|---|
| 1. playerbots compilés, bots connectés qui jouent seuls (serveur de test) | **Fait, vérifié** | `mangosd_bots.exe` (CMaNGOS ff53dfc + playerbots c6288bf) compilé sans erreur ; 10 bots en ligne (`chat_probe.py --online`) ; entre 16:05 et 16:45, **9 bots sur 10 ont changé** : zones, argent ramassé, XP (Isona 0 → 90), déplacements de 200 m à 18 km (`bot_activity.py diff`, fichiers `C:\Wowlheim\bots\state\activity_*.json`). Tick moyen 50 ms (plancher), 1,6 Go de RAM. |
| 2. Un bot répond en chat via le LLM avec sa personnalité | **Fait, vérifié** (/dire et /chuchoter) | Journal `C:\Wowlheim\bots\state\bridge_log.jsonl`, joueur de test Wlbuilder (compte WLTEST) via `chat_probe.py` : /dire « salut Bimlink, ça va ? » → « va bien merci toi aussi » (14,8 s en jeu, 11,7 s de LLM au premier appel) ; chuchotement « tu joues depuis longtemps ? » → « je découvre juste jveux economiser pour les sorts » (2,4 s de LLM, 11,8 s en jeu avec le délai de frappe) ; « tu sais construire une maison avec le marteau ? genre .build » → « je ne sais pas ce que c est je joue juste a wow vanilla » ; « t es un bot ? » → « non je suis juste un gnome mage qui aime economiser ». Les réponses suivent la fiche générée de Bimlink (minuscules sans ponctuation, débutant, objectif : sorts). 12 tests unitaires du pont OK. |
| 3 à 6 | Non commencés | voir §4 |

**Pas vérifié** : canaux Groupe, Général, Commerce ; anti-spam avec plusieurs bots autour d'un même /dire ; rendu des accents dans le vrai client graphique (testé seulement avec le client de protocole) ; tenue sur la durée ; 50 bots ; le serveur principal.

**Limites constatées** :
- Un bot ne lit le chat que s'il est « actif » (`AllowActivity()` de playerbots) : un chuchotement à un bot éloigné de tout joueur reste **sans réponse** (vérifié : 90 s de silence, puis réponse en 12 s une fois à côté). À régler au jalon 3 (réglages d'activité de playerbots ou exception pour les chuchotements de joueurs réels).
- Phrase un peu méta (« je joue juste a wow vanilla ») : la consigne cite « WoW vanilla » ; à reformuler au jalon 4.
- Les textes prédéfinis de playerbots sont en anglais (1 943 textes, 500 traduits en `text_loc2`).
- Premier démarrage du serveur de test : **72 min** (construction unique des caches playerbots en base) ; ensuite 1 min 36 s.

**Pièges rencontrés et corrigés** (dans `bots/server/setup_run.py` et `bots/playerbots.patch`) :
1. `tools/run_all.py` (autre session) fait `taskkill /F /IM mangosd.exe` : il a tué le serveur de test. Binaires renommés `mangosd_bots.exe` / `realmd_bots.exe`. Le cache de téléportation interrompu était resté partiel en base (niveaux 1 à 10) : vidé et reconstruit.
2. playerbots parcourait tous les ids d'objets jusqu'à 9 201 101 (objets Wowlheim) pour chaque classe × niveau × emplacement : patch qui ne parcourt que les objets existants et **exclut les objets Wowlheim (ids ≥ 9 000 000) des caches d'équipement des bots** ; insertions du cache d'équipement groupées par transaction.
3. `anticheat.conf.dist` active l'anticheat, qui crée Warden même avec `Warden.Enable = 0` ; sans modules Warden, la première connexion d'un joueur fait planter mangosd (3 plantages, piles symbolisées dans `C:\Wowlheim\bots\run\Crashes`). Anticheat coupé (`Enable = 0`), comme sur le serveur principal qui n'a pas d'`anticheat.conf`.
4. Sans `ahbot.conf`, l'AhBot de playerbots tourne avec un intervalle de 0 s et sature la base personnages (connexion des joueurs bloquée). `ahbot.conf` écrit avec `AhBot.Enabled = 0`.

**Reste** : jalons 3 à 6 (§4) ; points ouverts (§5). Rien n'est commité ni poussé.

**Pour relancer** : MySQL et LM Studio démarrés, puis `python -I bots/server/run_server.py` (en arrière-plan) et `python -I bots/llm_bridge/bridge.py`. Serveur de test et pont laissés **en marche** à 16:45.

## 1. Objectif

Des bots qui passent pour de vrais joueurs sur le serveur WoW classic 1.12.1 (CMaNGOS-classic) :

- ils parlent (/dire, /chuchoter, groupe, canaux), chacun avec sa personnalité (style d'écriture, caractère, vie du joueur derrière l'écran), cohérente avec sa race, sa classe et son niveau ;
- on peut les inviter en groupe et en donjon ; ils font des quêtes, montent de niveau, se baladent, commercent ;
- ils ne savent **rien** de la partie Valheim (construction, marteau, arbres, minage, `.build`) : ils jouent à WoW vanilla.

Cible du cahier des charges : **50 bots + 2 joueurs, serveur stable 1 h**.

## 2. Choix technique

### Moteur de jeu des bots : playerbots (ike3, dépôt `cmangos/playerbots`)

Décidé dans le cahier des charges, et confirmé par l'examen du code :

| Besoin | playerbots | Preuve |
|---|---|---|
| Bots autonomes (quêtes, niveaux, voyages, commerce, hôtel des ventes, métiers) | « random bots » : comptes `RNDBOT*`, connexion automatique, stratégies `rpg`, `travel`, `quest`, `grind` | `aiplayerbot.conf.dist`, `RandomPlayerbotMgr.cpp` |
| Groupe, donjon, commandes par chuchotement (`follow`, `stay`, `attack`...) | oui, invitation acceptée par les bots, IA de combat par classe | `strategy/`, liste `noReplyMsgs` dans `SayAction.cpp` |
| Intégré au cœur CMaNGOS-classic | option CMake `BUILD_PLAYERBOTS`, crochets `#ifdef ENABLE_PLAYERBOTS` déjà présents dans 19 fichiers du cœur au commit ff53dfc | `src/CMakeLists.txt`, grep |
| **Chat par LLM** | **déjà présent** : stratégie hors combat `ai chat`, appel HTTP dans un thread à part (`std::async`), contexte de conversation par canal, fichier de personnalités par nom de bot | `PlayerbotLLMInterface.cpp`, `SayAction.cpp` (`ChatReplyDo`) |

Alternatives écartées :
- **Ancien « Playerbot » (`BUILD_DEPRECATED_PLAYERBOT`)** : bots compagnons seulement, pas de population autonome, plus maintenu.
- **mod-playerbots (AzerothCore)** : WotLK uniquement, autre cœur ; incompatible avec CMaNGOS-classic et le travail Valheim déjà fait.
- **Bots maison pilotés par client de protocole (`tools/wlclient.py`)** : il faudrait réécrire déplacements, combat, quêtes ; des mois de travail pour un résultat inférieur.
- **VMaNGOS** : pas de module de bots (déjà noté dans le cahier).

Version retenue : cœur CMaNGOS-classic **ff53dfc** (celui du serveur principal) + playerbots **c6288bf** (2026-10-25), compilés ensemble sans erreur (voir état).

### Pont LLM : on garde l'appel intégré de playerbots, on met un pont local devant LM Studio

L'appel LLM de playerbots est déjà asynchrone : le thread du monde n'attend jamais. Mais il envoie un seul prompt brut, sans personnalité riche, sans mémoire des réponses du bot, sans file d'attente, et notre modèle à raisonnement (`nvidia-nemotron-3.5-bolt-e4b-4gb`) a besoin d'environ 600 jetons pour produire une réplique (voir `docs/LLM.md`). On intercale donc un **pont Python local** (`bots/llm_bridge/bridge.py`, stdlib seulement) :

```
joueur parle (chuchote / dit / groupe / canal)
  -> mangosd : playerbots ChatReplyDo (stratégie « ai chat », hors combat)
       remplit LLMApiJson : bot, race, classe, niveau, zone, interlocuteur, canal, message
       std::async -> POST http://127.0.0.1:5005/api/v1/generate     (thread à part)
  -> pont : garde-fous anti-spam -> personnalité + mémoire -> 1 appel LM Studio à la fois
       -> filtre de sortie -> {"results":[{"text":"..."}]}   ("" = silence)
  -> playerbots : envoie la ligne dans le même canal, avec un délai de frappe (200 ms/caractère)
```

- **Jamais dans la boucle de combat** : le LLM ne produit que du texte de chat ; aucune action de jeu n'en dépend. Les décisions (combat, déplacement, quêtes, accepter un groupe) restent celles de playerbots. Latence mesurée 2 à 4 s (8 s pour le premier appel à froid), sans effet sur le tick.
- **Commandes** : les ordres aux bots (`follow`, `attack`, `stay`...) sont filtrés par playerbots avant le LLM (liste `noReplyMsgs`), ils restent instantanés.
- Tout reste en **127.0.0.1** : le pont refuse d'écouter ailleurs, et le client LM Studio (`tools/llm/bot_chat.py`) refuse toute URL non locale.

### Mémoire de conversation

- Le pont garde, par paire (bot, interlocuteur), les 6 derniers échanges **des deux côtés** (le module C++ ne garde que les messages du joueur), avec une durée de vie de 3 h, enregistrés dans `C:\Wowlheim\bots\state\memory.json` (survit au redémarrage du pont).
- Contexte C++ de playerbots borné à 2 000 caractères (`LLMContextLength`) ; il n'est pas envoyé au pont (champ inutile, la mémoire du pont le remplace).
- À faire (jalon 4) : faits durables par bot (« a groupé avec Robin aux Mortemines ») résumés hors ligne.

### Génération des personnalités (`bots/llm_bridge/persona.py`)

- Une personnalité décrit **le joueur derrière le bot** : style d'écriture (minuscules sans ponctuation, abréviations, poli, laconique, roleplay léger...), deux traits de caractère, sa vie (étudiant le soir, parent, ancien de 2005...), ses objectifs en jeu selon niveau et classe (Mortemines à 18, monture à 40, Coeur du Magma à 60...).
- Déterministe : graine = nom du bot, donc stable d'une session à l'autre ; race, classe, niveau et zone viennent du personnage réel créé par playerbots, donc toujours cohérents.
- Fiches générées dans `C:\Wowlheim\bots\state\personas\` ; une fiche écrite à la main dans `bots/personas/<Nom>.json` (dépôt) a priorité (champ optionnel `histoire`).
- À faire (jalon 4) : enrichissement hors ligne par le LLM (une courte histoire par bot), généré une fois et relu, jamais pendant le jeu.

### Garde-fous

| Risque | Parade (dans le pont sauf mention) |
|---|---|
| Réponse trop longue, multi-lignes, markdown, lien | Filtre : une ligne, 160 caractères max, pas de lien ni de code `|H`, pas de guillemets |
| Le bot avoue être une IA, parle de Valheim/Wowlheim/.build | Consigne système + filtre de sortie (mots interdits) : la réponse est jetée, le bot se tait |
| Sujets hors jeu (politique, religion, argent réel, infos perso) | Consigne : ramener vers le jeu ; pas de promesse d'or ou d'objets |
| Spam : dix bots répondent au même /dire | Un seul bot répond à un même message (fenêtre 15 s) ; si le message nomme un autre bot, les autres se taisent ; probabilité de réponse par canal (chuchotement et groupe 100 %, Général 35 %, Commerce 25 %...) |
| Un bot bavard | Recharge de 6 s par bot ; plafond global de 30 réponses par minute |
| Bots qui se parlent entre eux en boucle | `LLMBotToBotChatChance = 0`, `LLMRpgAIChatChance = 0` |
| GPU saturé pendant le jeu | Un seul appel LLM à la fois, file bornée à 4, attente max 15 s, sinon silence |
| LM Studio absent ou en panne | Silence (réponse vide) ; le reste du jeu est inchangé |
| Combat | Stratégie `ai chat` dans le moteur hors combat (`LLMEnabled = 2`) ; et même déclenché, l'appel n'est que du texte dans un autre thread |
| Prompt injection par le joueur | Le texte du joueur n'est qu'un message utilisateur, la sortie est filtrée et ne déclenche aucune action |
| Accents dans le client 1.12 | Pont en UTF-8 brut ; option `--ascii` si le client les affiche mal (non vérifié en client graphique) |
| Journal | `C:\Wowlheim\bots\state\bridge_log.jsonl` : message, réponse, raison du silence, latence (rotation à 5 Mo) |

### Les bots ne savent rien de Valheim

- Le cœur des bots ne connaît pas `.build` ni les systèmes Wowlheim ; le LLM a pour consigne que la construction « n'existe pas » et le filtre jette toute réponse qui en parle.
- Déjà fait : les objets Wowlheim (ids ≥ 9 000 000) sont exclus des caches d'équipement et d'objets aléatoires des bots (`bots/playerbots.patch`).
- **Point à traiter à l'intégration (jalon 5)** : sur le serveur principal, le contenu Wowlheim est dans la base (nœuds 9101001+, butin des mobs). playerbots pourrait ramasser ces nœuds, garder ou vendre le butin Wowlheim, ou le mettre à l'hôtel des ventes. À vérifier puis bloquer (liste d'exclusion de GameObjects et d'objets dans le module), sans toucher aux règles Valheim.

## 3. Serveur de test séparé

| Élément | Serveur principal (autre session) | Serveur de test des bots |
|---|---|---|
| Sources | `C:\Wowlheim\src\mangos-classic` (avec patchs Wowlheim) | `C:\Wowlheim\bots\src\mangos-classic` (clone propre ff53dfc) + `src\modules\PlayerBots` (c6288bf) |
| Build | `C:\Wowlheim\build` | `C:\Wowlheim\bots\build` (`BUILD_PLAYERBOTS=ON`) |
| Dépendances | `C:\Wowlheim\vcpkg\installed` | racine séparée `C:\Wowlheim\bots\vcpkg_installed` (+ `boost-bimap` requis par playerbots) |
| Exécution | `C:\Wowlheim\run`, `mangosd.exe` | `C:\Wowlheim\bots\run`, **`mangosd_bots.exe` / `realmd_bots.exe`** |
| Ports | realmd 3724, monde 8085 | realmd **3725**, monde **8086** (127.0.0.1) |
| Bases | classicmangos, classiccharacters, classicrealmd, classiclogs | copies `*_bots` + tables playerbots (pas de base playerbots à part : le module range ses tables dans les bases monde et personnages) |
| Données client | `C:\Wowlheim\data` (lecture seule, partagées) | idem |

Les binaires sont renommés parce que `tools/run_all.py` fait `taskkill /F /IM mangosd.exe` : le 2026-10-26 à 14:27, cela a tué le premier serveur de test.

Commandes (depuis la racine du dépôt) :

```
python -I bots/server/setup_run.py --bots 5 --accounts 5   # copie binaires + configs
python -I bots/server/run_server.py                        # realmd + mangosd (stdin tenu)
python -I bots/llm_bridge/bridge.py                        # pont LLM sur 127.0.0.1:5005
python -I bots/tests/chat_probe.py --online                # bots en ligne
python -I bots/tests/chat_probe.py --whisper "salut, tu fais quoi ?"
python -I bots/llm_bridge/test_bridge.py                   # tests unitaires du pont
```

Console du serveur de test : écrire une commande dans `C:\Wowlheim\bots\run\console.in` ; arrêt propre : créer `C:\Wowlheim\bots\run\stop`.

Pour se connecter avec le vrai client : `set realmlist 127.0.0.1:3725` dans une copie du client (pas `client_test`, utilisé par l'autre session), comptes WLTEST/WLTEST2 (mêmes mots de passe, base copiée).

## 4. Jalons et critères de réussite

| # | Jalon | Critère vérifiable |
|---|---|---|
| 1 | playerbots compilés, quelques bots connectés qui jouent seuls (serveur de test) | `mangosd_bots.exe` démarre ; `chat_probe.py --online` liste ≥ 5 bots ; après 15 min, niveau, position ou XP d'au moins un bot ont changé (requête SQL avant/après) |
| 2 | Un bot répond en chat via le LLM avec sa personnalité | Un joueur de test chuchote, le bot répond en < 15 s, réponse visible dans `bridge_log.jsonl` avec raison `ok` ; un message sur la construction ne produit aucune mention de construction |
| 3 | Tous les canaux et anti-spam en conditions réelles | /dire au milieu de 5 bots → 1 seule réponse ; groupe → réponse en /groupe ; Général → ≤ 1 réponse ; 0 réponse en combat (journal) |
| 4 | Personnalités et mémoire de qualité | 10 bots, grille de relecture (style distinct, cohérence race/classe/niveau, aucun aveu d'IA) sur 50 échanges ; histoires générées hors ligne et relues ; un bot se souvient d'un échange après redémarrage du pont |
| 5 | Intégration au serveur principal | patch Wowlheim + playerbots compilés ensemble, bots exclus du contenu Valheim (objets, nœuds, `.build`), accord de l'autre session pour le redémarrage |
| 6 | **Cible : 50 bots + 2 joueurs, stable 1 h** | soak 60 min (style `tools/soak_test.py`) : pas de crash, diff moyen et pics de tick relevés, VRAM/CPU relevés, ≤ 30 réponses LLM/min, 2 joueurs groupés avec des bots en donjon au moins une fois |

## 5. Points ouverts

- Textes prédéfinis de playerbots (`ai_playerbot_texts`, salutations, annonces de groupe) en **anglais** : traduire en français (colonne `text_loc2` = frFR) ou les désactiver, sinon les bots mélangent les langues.
- Noms des bots générés par playerbots (`ai_playerbot_names`) : vérifier qu'ils ont l'air de pseudos de joueurs.
- Impact CPU de 50 bots sur la machine de dev puis sur le VPS (vCPU mutualisés) : à mesurer au jalon 6.
- Le patch `bots/playerbots.patch` (boucles d'objets, exclusion des ids ≥ 9 000 000, transactions) doit suivre si on met à jour playerbots ; à proposer en amont pour la partie performance.
- Activité des bots : seuls les bots proches d'un joueur réel lisent le chat (`AllowActivity`) ; pour 50 bots, régler les paramètres d'activité (`AiPlayerbot.*Activity*`, à étudier) sans faire exploser le CPU.
- Un modèle sans raisonnement serait 5 à 10 fois moins coûteux par réplique : comparer avec les autres modèles déjà listés dans LM Studio (non fait).
- LM Studio écoute encore sur 0.0.0.0:1234 (alerte de `docs/LLM.md`).
