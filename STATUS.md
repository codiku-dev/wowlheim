# Wowlheim — état (mis à jour le 2026-10-26, fin de nuit)

## Résumé pour Robin
| Phase | Critère du cahier | État |
|---|---|---|
| 0 Préparation | résultats d'analyse avec preuves | **fait** : REA + Valheim analysés, règles prouvées dans `docs/VALHEIM_RULES.md` |
| 1 Serveur de base | 2 joueurs normaux, 50 bots, stable 1 h | **partiel** : serveur, cartes, bases OK ; connexion/jeu vérifiés avec un client de protocole ; **stable 1 h avec 2 joueurs-bots : vérifié** ; **50 bots : non fait (repoussé sur ta demande)** ; **connexion avec le vrai client graphique : non vérifiée** (écran de licence) |
| 2 Construction minimale | 100 pièces survivent au redémarrage | **vérifié** |
| 3 Règles Valheim | effondrement, dégradation sous la pluie | **vérifié** (constantes et formules lues dans le CIL) |
| 4 Ressources et zones | maison construite avec du butin, impossible en ville | **vérifié** (`house_test.py`) |
| 5 Client patché | un joueur construit/fabrique depuis l'interface | **partiel** : DLL injectée + API Lua prouvées ; canal `[WL]` serveur vérifié ; addon écrit et testé hors jeu ; **interface jamais vue en jeu** |
| 6 Bots bâtisseurs | — | non commencé (repoussé) |

Suite de tests complète : `python tools/run_all.py` → **9/9 OK** (dernier passage : fin de nuit). Mode d'emploi et arborescence : `README.md`.

**Décisions qui t'attendent** (rien n'a été décidé à ta place) :
1. **Licence Blizzard** : accepter l'EULA/TOS sur la copie `C:\Wowlheim\client_test` pour débloquer les tests avec interface (rendu des pièces, addon, aperçu fantôme).
2. **LM Studio** écoute sur 0.0.0.0:1234 (réseau local) : désactiver « Serve on Local Network ».
3. **Couverture** Horde × Royaumes de l'Est × palier 1 : 2 zones au lieu de 3 (voir « Nœuds de production »).
4. **Conception** : remboursement (sac/courrier, complet), coûts des pièces et des extensions, niveaux de recettes (fer 2, argent 3, métal noir 4), plafonds de pièces (2 000 par joueur, 20 000 au total).
5. Ouvertes du cahier : rapidité de la dégradation sous la pluie, effet « mouillé », droits sur les pièces d'autrui, OS du serveur final, sauvegardes (`tools/backup.py` existe, pas planifié).

Avertissements : mmaps **générées** (34 cartes, 1 695 fichiers, `C:\Wowlheim\data\mmaps`) et **activées** (`mmap.enabled = 1`) ; `zone_test`, `harvest_test` et `level_test` repassent avec ; le correctif local de `GridMap.cpp` (garde `IsEnabled()`) reste en place ; MySQL `root` sans mot de passe sur 127.0.0.1 ; compte `mangos`/`mangos` par défaut du projet.


## Crossover Valheim → WoW : vrais assets et vraies mécaniques (2026-10-26, après-midi)
Demande de Robin : intégrer les **vrais modèles et mécaniques de Valheim** (marteau, menu, coupe à la hache), pas des substituts WoW. Ressources animales/mobs : butin WoW normal (inchangé) ; construction et récolte d'arbres : iso Valheim.
Assets de Valheim lus dans l'installation Steam de Robin (usage privé, non distribué — cahier, Droits) ; artefacts dans `C:\Wowlheim\valheim_extract` et `C:\Wowlheim\wl_assets` (hors dépôt). Outils : `tools/valheim/`.
- **Données réelles** (`vh_dump_all.py`, UnityPy + typetrees des bundles) : table du marteau `_HammerPieceTable` (398 pièces, catégories Divers/Fabrication/Construction/Construction lourde/Meuble), `Piece.m_resources` (coûts), `WearNTear` (PV, matériau), points d'accroche `$hud_snappoint`, `TreeBase`/`TreeLog` (PV, `m_minToolTier`, bûches, butin), outils (`m_damages.m_chop`, `m_toolTier`), 481 recettes, localisation française du jeu. Formule de compétence lue dans le CIL : `Skills.GetRandomSkillRange` (centre `Lerp(0,4;1;compétence)` ± 0,15).
- **Modèles** (`build_assets.py`, `wowfmt.py`) : exporteur Unity → M2 v256 (format vérifié en relisant des M2 d'origine du client), BLP2, collisions ; 112 modèles (pièces, stations, arbres avec animations chute/couché/secousse, bûches, outils tenus en main), 457 icônes Valheim (`build_icons.py`). Contrôle hors jeu : `m2_preview.py` (rendu logiciel). `gen_client_patch.py` → DBC (GameObjectDisplayInfo 20000+, CreatureModelData 3000+, CreatureDisplayInfo 25000+, ItemDisplayInfo 70000+, Spell 40001 « Construire », SpellIcon 3000) et `C:\Wowlheim\wl_assets\patch-3.MPQ` (les mêmes DBC sont copiés dans `C:\Wowlheim\data\dbc`, originaux dans `dbc_orig`). **Pas encore installé dans le client ni vu en jeu.**
- **Serveur** (`gen_server_sql.py` → `012_valheim_content.sql`) : 83 pièces Valheim (noms, coûts, PV, matériau, station, extensions, points d'accroche) ; objets aux icônes/modèles Valheim ; recettes d'outils de Valheim ; 7 matériaux ajoutés (Charbon, Chaîne, Clous de bronze/fer, Plumes, Pierre à aiguiser, Goudron — **sources : recettes uniquement pour une partie ; Plumes et Goudron sans source**).
- **Abattage** (`server/Wowlheim/TreeMgr.*`, accroches dans `Unit.cpp`) : arbres et bûches = créatures au modèle Valheim (1 481 arbres à la place des nœuds de bois, essences par biome), frappés en mêlée ; seuls les dégâts de coupe de la hache comptent, palier d'outil requis ; arbre → chute → tronc → 2 bûches → Bois (butin de Valheim). **VÉRIFIÉ** par `tools/tree_test.py` (serveur réel, client de protocole) : marteau 0 dégât + message, hache en pierre 5–11 par coup (11 coups pour un hêtre), tronc, 2 bûches, 20 Bois, bouleau « Trop dur ». Compétence de bûcheronnage non suivie (niveau 0).
- **Minage** (même module) : roches et filons de Valheim (`MineRock_Stone`, `Rock_4`, `MineRock_Copper`, `MineRock_Tin`, `MineRock_Iron`, `MineRock_Obsidian`) en créatures frappées au pic (dégâts `m_pickaxe`, palier de Valheim + 1 = paliers des pics du serveur), animation d'éclatement, butin tiré selon la DropTable de Valheim et ramassé par le mineur ; 2 124 nœuds de pierre/minerai convertis. **Adaptations** : un MineRock regroupe ses 24 zones (PV et butin × 24) et l'on suppose 3 zones touchées par coup (`m_multiHit`, [INFÉRÉ]) ; le minerai donne directement le métal (pas encore de fonderie). Test : partie minage de `tools/tree_test.py`.
- **Marteau** (`BuildPlacement.cpp`) : `.build api select|mode|placeat`, pose au point visé avec l'accroche de Valheim (0,5 m ; adaptation : 1 m à l'horizontale jusqu'à 4 m au-dessus tant qu'il n'y a pas de fantôme visible), démolition/réparation par clic droit sur la pièce selon le mode ; sort 40001 lancé par l'utilisation du marteau (cercle de ciblage au sol). Test : `tools/hammer_test.py`.
- **Addon** (agent) : menu du marteau façon Valheim (`tools/client/addon/Wowlheim`, données générées `WowlheimData.lua`), 69 tests hors jeu OK, **jamais chargé en jeu**.
- **VÉRIFIÉ EN JEU** (client de test `C:\Wowlheim\client_test` + DLL, captures `tools/client/gui/shots/v14.png`–`v42.png`) :
  - le client charge `patch-3.MPQ` ; mur, plancher, établi et hêtre de Valheim s'affichent avec leurs textures (`v15`) ; objets aux noms de Valheim ; hache en pierre de Valheim tenue en main (`v25`) ; collision du mur (le personnage bute dessus, `v42`) ;
  - équiper le marteau ouvre le menu façon Valheim : onglets Divers/Fabrication/Construction/Construction lourde/Meuble, icônes Valheim, encadré coût « possédé/requis » et station requise (`v17`, `v19`) ;
  - pose à la souris : la pièce choisie apparaît en fantôme natif sous le curseur (`v23`), un clic la pose au point visé, le serveur répond « Pièce Plancher 2x2 posée » (`v24`).
  - Défauts trouvés et corrigés en jeu : `boneCountMax` des 4 vues M2 doit décroître (256, 75, 53, 21) sinon le modèle est invisible ; texture palette sans alpha mal lue → plan alpha 8 bits toujours écrit ; délai de 30 s après équipement du marteau (« Item is not ready yet ») → `spelltrigger_1 = 5` (corrigé dans le générateur, **pas encore appliqué/re-testé**).
  - **Non vu en jeu** : abattage (attaque lancée sur le hêtre mais aucun coup : personnage bloqué par le mur, tronc hors de portée ; la mécanique est vérifiée par `tree_test.py` côté serveur), animation de chute, fantôme teinté (il est sombre), démolition au clic, icônes d'objets dans les sacs.
- **Fantôme** (agent, `docs/GHOST_PREVIEW.md`) : le client affiche nativement le GameObject d'un sort d'invocation sous le curseur ; la DLL change l'objet du sort 40001 en mémoire (`WowlheimSetPlaceObject`) et l'orientation ; compilé, adresses vérifiées statiquement, **non testé en jeu**.

---

# Wowlheim — Phase 0 : état (2026-10-25, mis à jour)

Cadre : tout en local sur le Windows de Robin (pas de VPS pour l'instant).

## Poste (vérifié)
| Élément | État |
|---|---|
| Git 2.49, CMake 4.4.3, Python, .NET SDK, Java 17 | OK |
| Node.js | 24.22.1 installé via nvm et actif (REA exigeait ^22.23.4 / ^24.22.1). 22.15.1 et 20.20.2 restent installés. |
| Visual Studio (C++) | Build Tools 2022 + charge C++ installés (`C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools`), vérifié par vswhere |
| MySQL | 8.4.9 (winget). Pas de service Windows : lancé à la main, `C:\Wowlheim\mysql\my.ini`, données `C:\Wowlheim\mysql\data`. Vérifié : écoute 127.0.0.1:3306 uniquement. `root` **sans mot de passe** (local seulement) ; `mysql_native_password=ON` activé. Démarrage : `mysqld.exe --defaults-file=C:\Wowlheim\mysql\my.ini`. |
| Ghidra / Hopper / IDA | aucun — inutile pour Valheim (.NET), utile phase 5 (Wow.exe) |

## Client WoW 1.12.1 — **VÉRIFIÉ** (2026-10-26)
`C:\Users\rlebh.RLEBHAR.000\Desktop\WoW Vanilla` : `WoW.exe` FileVersion = 1, 12, 1, 5875 (32 bits, 4 775 986 o), Data\*.MPQ complets. Remarque : `patch.MPQ` fait 2 Go (inhabituel, probablement une installation reconditionnée ; à garder en tête pour l'extraction des cartes).

## (ancien) Client — état avant fourniture
- `C:\Program Files (x86)\World of Warcraft` : Classic Era 1.15.8 et Anniversary 2.5.6. Pas 1.12.1.
- `C:\Ascension` : launcher d'un serveur privé, pas un client 1.12.1 vanilla.
- [À DÉCIDER] Robin doit fournir une copie légitime du client build 5875.

## REA
- Version 6.8.0, utilisée via `npx rea-agents@latest <commande>` (CLI).
- **Enregistrement MCP dans Claude Code NON appliqué** : `setup --yes` refuse sans approbation interactive (le plan à blanc modifierait `~/.claude.json` avec sauvegarde, et installerait le skill `reverse-engineer-anything`). À lancer par Robin dans un terminal : `npx rea-agents setup --client claude_code`. Inutile pour la suite : la CLI suffit.
- Analyse .NET : aucun fournisseur natif requis (provider `rea-dotnet-static`).

## Valheim — assembly_valheim.dll (vérifié par REA)
- SHA-256 `94998885b103d6e5f5480123eaee0a093e82af2ddeeee37536c15bf555f24f3a`, 2 575 360 o, .NET IL-only, 1313 types, 11 373 méthodes.
- Sorties brutes (non versionnées, dérivées du jeu, ne pas distribuer) : `analysis/valheim/` (`artifact.json`, `members_<Type>.json`). Script de synthèse : `analysis/insp.cjs`.

| Type du cahier | Trouvé ? | Détail |
|---|---|---|
| `WearNTear` | oui | 106 champs, 55 méthodes. Intégrité/usure : `UpdateSupport`, `GetSupport`, `FindSupportPoint`, `HaveSupport`, `GetMaxSupport`, `GetMinSupport`, `GetMaterialProperties`, `ClearCachedSupport`. Abri/pluie : `UpdateCover`, `HaveRoof`, `RoofCheck`, `IsWet`, `m_noRoofWear`, `m_noSupportWear`, `m_roofCheckOffset`, `c_RainDamage`, `c_RainDamageTime`, `c_RainDamageMax`. Dégâts/destruction : `Damage`, `ApplyDamage`, `Destroy`, `Remove`, `UpdateWear`. |
| `Piece` | oui | 65 champs, 24 méthodes |
| `Player` | oui (2 types, dont un imbriqué) | 263 champs, 348 méthodes |
| `EnvMan` | oui | 101 champs, 76 méthodes |
| `Cover` | **non** (0 type) | Le nom supposé est faux : la logique de toit est dans `WearNTear.RoofCheck/HaveRoof/UpdateCover`. L'abri joueur reste à localiser dans `Player`/`EnvMan` (phase 3). |

**Non encore fait** : lecture des corps CIL (valeurs numériques exactes, formules). Les noms ci-dessus prouvent seulement l'existence des membres, pas les règles. Les valeurs des constantes (`c_RainDamage`, etc.) et la formule de support seront extraites en phase 3 avec preuve.

## Hypothèses du cahier : statut
Aucune hypothèse technique (addons, M2, SuperWoW, DESTRUCTIBLE_BUILDING, coût CPU bots) n'est vérifiée à ce stade.

## Critère phase 0
Partiel : outils de base OK, REA opérationnel en CLI, Valheim analysable et classes ciblées localisées. **Manquent : client 1.12.1, Visual Studio C++, MySQL.**

## Décisions utilisateur
- LLM pour le chat des bots (cahier §7.3, phase 6, optionnel) : `nvidia-nemotron-3.5-bolt-e4b-4gb` (modèle de test, remplace underdog-saluki-27b) servi par LM Studio en local. Jamais dans la boucle de combat. [À vérifier : API LM Studio locale, latence]

## Phase 1 — état (2026-10-26)
- CMaNGOS-classic (commit ff53dfc, 2026-10-22) compilé en Release, **sans playerbots** (décision : bots repoussés). Sources : `C:\Wowlheim\src\mangos-classic`, build `C:\Wowlheim\build`, exécution `C:\Wowlheim\run`. Boost/OpenSSL via vcpkg local (`C:\Wowlheim\vcpkg`).
- Extraction client : DBC (158), maps (2429), Cameras, vmaps (6077 fichiers) dans `C:\Wowlheim\data`. mmaps : non générées à ce moment-là (générées et activées depuis, voir le résumé en tête).
- Patch local au source : `src/game/Maps/GridMap.cpp:1299` garde le chargement mmap par `IsEnabled()` (sinon assertion fatale au démarrage quand les mmaps sont absentes). À refaire/retirer quand les mmaps existent.
- Bases importées dans MySQL local : classicmangos (Full_DB z2815 + updates core jusqu'à z2837 + updates contenu), classiccharacters, classicrealmd, classiclogs. Utilisateur `mangos`/`mangos` (défaut du projet, localhost uniquement). Les updates characters/realmd >base n'ont **pas** été appliqués (pas de table db_version à comparer) : à vérifier.
- realmd et mangosd configurés en BindIP 127.0.0.1 ; realmd écoute 127.0.0.1:3724 (vérifié). mangosd : "World initialized" vu dans le log (pas encore testé avec un client).
- Client : `realmlist.wtf` passé à `set realmlist 127.0.0.1` (original sauvegardé en `realmlist.wtf.orig`).
- Console mangosd lancée dans l'onglet Terminal « mangosd » (stdin nécessaire).
- Non vérifié : connexion client réelle, stabilité 1 h.

### Phase 1 — test de connexion (2026-10-26, nuit)
- Compte de test `WLTEST` (gmlevel 3) créé via la console mangosd ; mot de passe généré dans `C:\Wowlheim\run\test_account.txt` (hors dépôt). Comptes par défaut (ADMINISTRATOR, GAMEMASTER, MODERATOR, PLAYER, mot de passe = nom) **supprimés**.
- `tools/login_test.py` (client de protocole 1.12.1, local) : **VÉRIFIÉ** — logon SRP6 OK, realmlist 1 royaume, AUTH_SESSION → AUTH_RESPONSE 0x0C (OK), CHAR_ENUM reçu (0 personnage).
- **Non vérifié** : lancement réel de `WoW.exe` + création de personnage + déplacement en jeu (pas de pilotage GUI possible). Critère « jeu normal / stable 1 h » : non évalué.
- mangosd est lancé via `tail -f cmd.in | mangosd.exe` (Bash) pour garder un stdin ; envoyer des commandes GM : `echo "<cmd>" >> C:/Wowlheim/run/cmd.in`.

## Phase 2 — construction minimale (2026-10-26) : critère VÉRIFIÉ
- Code serveur : `server/Wowlheim/` (BuildingMgr, BuildCommands, StructureSim), SQL `server/sql/{world,characters}/`, patch du cœur `server/core.patch` (Chat.h/.cpp, World.cpp, Weather.h, GridMap.cpp). Synchro/compilation : `tools/sync_server.ps1 -Build`.
- Les pièces sont des GameObjects (`gameobject_template` 9100001+, modèles de substitution du client) spawnés via la table `gameobject` du cœur : persistance native ; métadonnées dans `wowlheim_piece` (characters) ; catalogue `wowlheim_piece_template` (world).
- Commandes : `.build list|place <pièce> [avant] [droite] [haut]|remove|count|support`, GM : `.build near|bulk|perf|rain|grace|dump|stats`.
- Test sans GUI : `tools/wlclient.py` (client de protocole : crée un personnage, entre dans le monde, envoie du chat, lit les réponses système).
- **Critère « poser 100 pièces, redémarrer, elles sont toujours là » : VÉRIFIÉ** (`.build bulk Plancher 98` + 1 → 100 en base et 100 GameObjects chargés ; après redémarrage de mangosd : 100 pièces rechargées, 100 GameObjects chargés).
- Mesure du tick : diff moyen **50 ms (plancher du tick, serveur au repos)** avec 100, 1 100 et 2 000 pièces → aucun coût mesurable de pièces statiques au repos. **Non mesuré** : coût sous charge (joueurs, combats, bots), plafonds MAX 20 000 total / 2 000 par joueur choisis arbitrairement.
- Piège rencontré : `Map::GetHeight` inclut les modèles des GameObjects dynamiques ; pour le sol il faut `TerrainInfo::GetHeightStatic` (sinon les pièces empilées s'ancrent les unes aux autres).

## Phase 3 — règles Valheim (2026-10-26) : critère VÉRIFIÉ, avec réserves
- Règles extraites : `docs/VALHEIM_RULES.md` (preuves IL). Implémentation : `server/Wowlheim/StructureSim.cpp`.
- `tools/phase3_acceptance.py` : colonne de 10 poteaux → 8 survivants, supports 100, 73.8, 54.4, 40.1, 29.6, 21.8, 16.1, 11.9 (identiques au calcul à la main avec les constantes Valheim bois) ; pièce flottante effondrée ; démolition de la base → toute la colonne tombe ; sous la pluie les pièces exposées perdent 5 % de PV max par période et s'arrêtent à 50 % ; pièce couverte épargnée. **Résultat : TOUT OK** (7 contrôles).
- Écarts assumés avec Valheim (adaptations, non des règles Valheim) : voisinage par distance (3 m) au lieu de colliders ; ancrage = base à ≤ 0,75 m au-dessus ou ≤ 3 m sous le terrain statique ; toit = n'importe quelle pièce au-dessus dans un rayon de 1,2 m (Valheim : tout collider sauf tags non résolus) ; effondrement par vagues d'1 s (en cascade instantanée par vague) ; matériau unique (bois, index 0) dans le catalogue ; pluie = météo RAIN de la zone (la simulation ne tourne que sur une carte où un joueur est présent).
- Paramètres de test accélérés par commande GM (`.build grace`, `.build rain`) ; valeurs Valheim par défaut : grâce 30 s, période de pluie 60 s.
- **BUG CORRIGÉ** (crash serveur sous poses répétées) : cause prouvée par capture d'exception dans le thread de mise à jour des cartes = `std::logic_error: invalid node overlap` levée par `BIH::subdivide` (arbre des objets dynamiques du cœur, reconstruit avec nos GameObjects de substitution). Correctif : les pièces (entrées 9100000+) ne sont plus insérées dans l'arbre dynamique (`GameObject::UpdateModel`), et une pose à moins de 0,5 m d'une pièce identique est refusée. Vérifié : 150 poses, 80 cycles pose/démolition, stress initial 150 cycles, critères phase 3 → aucun crash. Conséquence : nos pièces n'ont plus de collision côté serveur (ni ligne de vue, ni hauteur dynamique) ; la collision client dépend du modèle.

## Résultats des agents parallèles
- `docs/LLM.md`, `tools/llm/` : client LM Studio local pour le chat des bots (modèle `nvidia-nemotron-3.5-bolt-e4b-4gb`) : fonctionne, latence 2–4 s mesurée, 13 tests unitaires OK. **Alerte** : LM Studio écoute sur 0.0.0.0:1234 (joignable sur le réseau local) — à régler dans LM Studio (désactiver « Serve on Local Network »).
- `docs/CLIENT_FEASIBILITY.md`, `tools/client/` : H1 partiellement fausse (`SendAddonMessage` existe, limité à PARTY/RAID/GUILD/BATTLEGROUND ; pas de filtre de chat → surcharge de `ChatFrame_OnEvent`) ; H2 : le client utilise des `.m2` (pas `.mdx`), les `patch-?.MPQ` sont chargés ; aucun test en jeu du client réel. Venv local `tools/client/.venv` (mpyq, capstone, lupa).
- Extraction REA complémentaire : terminée, `docs/VALHEIM_RULES.md` complété (cadence, cascade, remboursement, réparation, placement). **Erreur trouvée et corrigée dans mon premier jet** : les valeurs Stone/Iron/HardWood étaient mal associées (table de sauts du switch) ; le code serveur utilise désormais la table corrigée. Autre correction : une pièce posée par un joueur est évaluée immédiatement (pas de grâce de 30 s) — le défaut serveur est maintenant 0.


## Cahier des charges mis à jour (2026-10-26) — changements pris en compte
Source : doc partagé « Wowlheim — Cahier des charges » (lien donné par Robin). Points nouveaux ou changés :
- **Client patché au cœur, sans repli** : analyse REA de `Wow.exe` (32 bits) pour injecter une DLL ou patcher le binaire : aperçu fantôme, panneaux de construction/établi, canal propre client-serveur. (SuperWoW n'est plus mentionné.)
- **Outils et stations** : outils à nous fabriqués à l'établi (jamais en butin), amélioration par palier, stations établi/forge/marteau de construction (niveau = extensions à proximité), nœuds de ressources (bois, pierre, minerai) en GameObjects récoltables, indépendants des métiers WoW ; catégorie d'objets « Wowlheim » ; noms de matériaux de Valheim.
- **Ressources** : 5 paliers (Prairie 1–15, Forêt noire 15–28, Marais 28–40, Montagne 40–52, Plaines 52–60), règles anti-blocage (3 sources minimum, 3 zones par continent, règles par famille de créature × tranche de niveau, taux 30–60 %), validation par audit de la base puis matrice générée en SQL.
- **Phases** : 0 à 5 ; bots bâtisseurs reportés après la phase 5 ; LLM : modèle de test `nvidia-nemotron-3.5-bolt-e4b-4gb` (le doc dit « ~9B ou plus petit »).
- Questions ouvertes inchangées (pluie/réparation/« mouillé », droits sur les pièces d'autrui, remboursement, plafonds, OS final, sauvegardes, LLM).
- Écart à noter : le doc place les 50 bots dans la phase 1 mais « bots bâtisseurs » après la 5 ; Robin a demandé de repousser tous les bots → phase 1 validée **sans bots**.

## Phase 4 — ressources et zones (2026-10-26)
Contenu SQL intégré dans `classicmangos` (sauvegarde préalable `C:\Wowlheimackup\*_20261026_025454.sql`) via `tools/apply_sql.py` : 39 objets (29 matériaux 9200001+, 10 outils 9201011+), 23 modèles de nœuds (9101001+) + 118 nœuds de validation (Elwynn/Dun Morogh/Durotar), 75 références de butin (8300000+, pas 9300000+ : `mincountOrRef` est un MEDIUMINT signé) et 2 292 lignes de butin de mobs, 159 lignes de vendeurs (source de secours), 16 recettes (10 outils + 6 conversions), pièces/coûts/zones. Détails, audit et limites : `docs/RESOURCES.md` (agent ressources ; ses contrôles automatiques : `tools/resources/check.py`).

**Vérifié sur le serveur réel avec le bot de protocole** (aucun `.additem` pour les matériaux dans le test de maison) :
- **Butin de mobs** (`loot_test.py`) : 20 Kobold Workers → Bois 9, Pierre 20, Silex 3, Résine 2, Chutes de cuir 17 (catégorie humanoïde, palier 1).
- **Récolte** (`harvest_test.py`) : sans outil → refus avec message ; pic sur un arbre → refus (« il faut une hache ») ; pic sur un rocher → butin (Pierre, Silex) ; hache sur un arbre → Bois. L'outil doit être équipé en main droite (hook dans `GameObject::Use`). Le butin du nœud est ouvert directement par ce hook : les coffres sans serrure ne s'ouvrent pas d'eux-mêmes dans ce cœur (le rapport de l'agent ressources disait le contraire : **corrigé**).
- **Fabrication** (`craft_test.py`) : à l'établi abrité (toit + couverture ≥ 70 %) → hache en silex fabriquée, ingrédients consommés ; sans ingrédients → refus ; établi sans toit → refus (« exposé »).
- **Coûts** (`cost_test.py`) : refus avec décompte, consommation 2 Bois par plancher, remboursement complet à la démolition volontaire, établi à 10 Bois.
- **Zones** (`zone_test.py`) : capitales/villes par drapeaux de zone, villages/camps par points d'exclusion (104, rayon 70 m, générés depuis les aubergistes et maîtres de vol : `tools/gen_nobuild.py`) ; Stormwind, Orgrimmar, Ironforge, Goldshire, Razor Hill, Kharanos, Anvilmar refusés ; Western Plaguelands et Westfall autorisés.
- **Critère de la phase** (`house_test.py`) : 60 à 80 kobolds tués → 22+ Bois lootés → plancher + 4 murs + toit + établi posés avec les coûts normaux, l'établi est utilisable (94–100 % de couverture) ; en ville (Stormwind, Orgrimmar) la pose est refusée avec les ressources en poche. Version finale du test (personnage neuf au sac vide, ne ramassant que les matériaux Wowlheim) : 110 morts de kobolds → 22 Bois ; maison de 7 pièces posée avec les coûts normaux (16 → 23 pièces, aucune effondrée après 5 s) ; établi utilisable à 100 % de couverture ; Stormwind et Orgrimmar refusés ; **RÉSULTAT : OK** (journal `C:\Wowlheim\house_run.log`). Deux essais précédents avaient échoué pour des causes de mon script : un emplacement déjà occupé par une maison d'un test précédent, et un sac plein de butin ordinaire.

Non vérifié / limites : taux de butin réels sur de gros échantillons et par famille autre qu'humanoïde ; équilibrage des coûts et des taux ; les vendeurs de secours ne couvrent pas toutes les zones des paliers 4–5 (voir RESOURCES.md §10) ; bronze sans source de butin (conversion à la forge uniquement, donc forge → cuivre → pic palier 1 → ok mais jamais testé en chaîne) ; pas de nœuds de production pour les paliers 2–5 (seulement les 118 nœuds de validation) ; z des nœuds issu d'une créature (non contrôlé sur le terrain) ; rendu en jeu des modèles de substitution non vu (le test avec interface graphique est bloqué sur l'écran de contrat de licence du client).

**Décision en attente de Robin (je ne la prends pas à sa place)** : accepter l'EULA / les conditions d'utilisation de Blizzard sur la copie de test du client (`C:\Wowlheim\client_test`) pour pouvoir lancer le test avec l'interface graphique ; l'agent chargé du test s'est arrêté sur cet écran. Rien n'a été écrit dans `Config.wtf` à ce sujet.

[À DÉCIDER] Remboursement : Valheim fait tomber les ressources au sol ; j'ai mis sac (démolition volontaire) / courrier (effondrement). Recommandation : garder ainsi, plein remboursement dans les deux cas (comme Valheim).
[À DÉCIDER] Coûts des pièces (prefab Unity non lisible dans le DLL) : plancher 2 Bois, mur 2, toit 2, poteau 1, feu de camp 5, établi 10 ; forge 20 Pierre + 5 Cuivre.

## Phase 5 — client patché : jalons atteints (2026-10-26)
- **DLL injectée dans `Wow.exe`** : vérifiée sur la copie `C:\Wowlheim\client_test` (hook posé, API Lua `WowlheimPing` enregistrée via un trampoline dans une cave de padding `.text`, appelée depuis du Lua exécuté par le client ; aucun GUI). Ghidra 12.1.4 + JDK 21 installés dans `C:\Wowlheim\tools` et branchés à REA. Adresses : `docs/CLIENT_PATCH.md`. **Non vérifié** : tout ce qui demande un rendu en jeu (aperçu fantôme, stabilité sur une longue session).
- **Canal client ↔ serveur — VÉRIFIÉ côté serveur** (`tools/api_test.py` : 8 contrôles OK, lignes analysées par le même code Lua que l'addon via lupa) : `.build api <commande>` répond par des lignes `[WL]<type>|champs` (P = pièce du catalogue, I = matériaux, C = recette, S = établi, M = message, E = erreur, D = fin de réponse avec drapeau de succès). Une commande normale n'émet aucune ligne `[WL]`.
- **Addon `tools/client/addon/Wowlheim/`** (Lua 5.0, panneau de construction : liste des pièces avec coûts, pose avec décalages/rotation, démolition, réparation, état de l'établi, sac) : `WowlheimCore.lua` (protocole) **testé hors jeu** avec lupa (`tools/client/addon/test_core.py`, 13 contrôles OK, la syntaxe de l'UI compile) ; l'interface elle-même (`Wowlheim.lua`) **n'a jamais été chargée par le client** : à tester dès que l'écran de licence aura été accepté (décision de Robin).
- **Test de stabilité (critère de la phase 1, sans bots) : VÉRIFIÉ pour 60 minutes** (`tools/soak_test.py`, journal `C:\Wowlheim\soak.log`) : deux joueurs-bots connectés en continu ; l'un relevait le diff et téléportait entre Westfall, les Barrens et les Western Plaguelands (16 téléports : chargements de grilles), l'autre faisait apparaître/tuer/piller un kobold, poser et démolir des pièces (510 cycles). Résultat : les deux bots terminent sans erreur, le serveur n'a pas planté, aucun fichier de crash nouveau, diff moyen 50 ms (plancher du tick) ; **deux pics isolés à 255 ms** (04:07 et 04:10, probablement le premier chargement d'une nouvelle carte après téléport). **Limites** : 2 joueurs-bots dans des zones différentes, pas de combat réel ni de bots compagnons ; le cahier demande 2 joueurs + 50 bots pendant 1 h : la partie « 50 bots » n'est pas faite (bots repoussés sur ta demande).

## Suite d'acceptation (2026-10-26, nuit)
`python tools/run_all.py` : phase3_acceptance, station_test, zone_test, cost_test, harvest_test, craft_test, api_test → **RÉSULTAT GLOBAL : OK** (7/7, binaire avec l'API `.build api`, journal `C:\Wowlheim\run_all.log`). Les tests utilisent des personnages dédiés (`Wlphase`, `Wlstation`, `Wlcost`, `Wlcraft`, `Wlharvest`, `Wlzone`) pour ne pas dépendre de l'état des autres ; `wlclient.goto_test_spot` place le personnage en mode GM sur un terrain libre de Coldridge Valley.
Sauvegardes : `tools/backup.py` (characters + realmd + logs, rotation 14) ; sauvegarde complète de la base du monde avant intégration du contenu : `C:\Wowlheim\backup\classicmangos_20261026_025454.sql`. **mmaps** : générées puis activées (voir résumé en tête).

## Stations : niveaux et extensions (2026-10-26) — implémenté et vérifié
Formule **prouvée dans le CIL** (agent d'extraction, `docs/VALHEIM_RULES.md` §8) : `niveau(station) = 1 + nombre d'extensions comptées` ; une extension compte si sa distance 3D à la station est < son `m_maxStationDistance` (5 par défaut du constructeur), si elle vise cette station, et si son type n'est pas déjà compté (sauf `m_stack`) ; niveau requis d'une recette = `max(1, m_minStationLevel) + qualité − 1`. Implémentation : `BuildingMgr::StationLevel`, pièces `kind = extension` (Billot de bûcheron, Étendoir à peaux → établi ; Soufflet, Enclume, Étau → forge), pose d'une extension refusée sans station compatible à moins de 5 m, `.build craft` refuse si le niveau est insuffisant. `tools/level_test.py` : forge niveau 1 → hache de fer (niveau 2) refusée ; extension loin de toute forge refusée ; soufflet posé → niveau 2 → fabriquée ; second soufflet (même type) non compté → hache en argent (niveau 3) refusée ; enclume (autre type) → niveau 3 → fabriquée. **RÉSULTAT : OK** (8 tests dans `run_all.py`).
**Non extractible du DLL** (données de prefabs Unity) : `m_extraRangePerLevel`, la liste des extensions de chaque station, les recettes et leurs niveaux. **Les niveaux de recettes (fer 2, argent 3, métal noir 4, bronze 1) et les coûts des extensions sont donc ma proposition de conception, à valider par Robin.** Je n'ai pas implémenté l'extension de portée de construction par niveau (valeur inconnue) ni le cache de 2 s des extensions.

## Nœuds de production (2026-10-26) — intégrés et testés
Agent de génération : `server/sql/world/008_node_spawns_production.sql`, **4 664 nœuds** (guid 9510001–9514664, plafond fixé à 6 000) sur les cartes 0 et 1, positions/z/orientation repris de créatures non élites de la base (jamais inventés), aucun nœud à moins de 100 m d'un point d'exclusion, ni dans une aire de ville/intérieure, espacement ≥ 12 m, +9,8 % de GameObjects (au plus 45 nœuds/km²). Détails et limites : `docs/RESOURCES_NODES.md`, contrôles `tools/resources/check_nodes.py` (0 erreur de forme).
Intégration : appliqué avec `tools/apply_sql.py` (sauvegarde `C:\Wowlheim\backup\classicmangos_20261026_060026.sql`) ; **j'ai borné le `DELETE` de `005_node_spawns.sql` aux nœuds** (sinon son rejeu effaçait les pièces de construction, qui reçoivent des guid dans la même plage 95xxxxx) ; `GuidReserveSize.GameObject` passé à 100 000 dans `mangosd.conf` (10 000 par exécution du serveur était une limite cachée sur le nombre de pièces posées).
**Vérifié** (`tools/prod_node_test.py`, 9ᵉ test de `run_all.py`) : 4 782 nœuds en base, démarrage du serveur toujours en 2 s, diff moyen 50 ms avec tous les nœuds, un arbre et un rocher de production récoltés avec l'outil.
**Limites (agent + moi)** : un nœud est à une position de créature (camps de monstres, rien dans les grandes zones vides, aucun filon en mine) ; z comparé au terrain statique seulement (jamais vu en jeu) ; palier d'un nœud = niveau médian des créatures voisines ; classification des factions de zone faite à la main.
**Écart de couverture à trancher (Robin)** : Horde × Royaumes de l'Est × palier 1 n'a que 2 zones (Tirisfal Glades, Silverpine Forest) au lieu des 3 exigées par le cahier ; aucune zone contestée de ce continent n'a assez de créatures de palier 1. Options : reclasser une zone (p. ex. Hillsbrad en zone Horde de palier 1) ou assouplir la règle à 2 zones pour ce cas. `check_nodes.py` renvoie le code 3 tant que ce n'est pas réglé.
