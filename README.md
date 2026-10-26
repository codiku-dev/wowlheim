# Wowlheim

Serveur privé WoW classic 1.12.1 (CMaNGOS-classic) auquel on ajoute les mécaniques de construction de Valheim. Projet privé, tout se passe en local sur ce poste Windows. Référence : [CAHIER_DES_CHARGES.md](CAHIER_DES_CHARGES.md) ; état d'avancement détaillé et décisions en attente : [STATUS.md](STATUS.md).

## Organisation du dépôt

| Chemin | Contenu |
|---|---|
| `CAHIER_DES_CHARGES.md`, `STATUS.md` | spécification, avancement, écarts, décisions à prendre |
| `docs/VALHEIM_RULES.md` | règles de Valheim extraites du CIL de `assembly_valheim.dll` par REA, avec preuves (offsets IL) |
| `docs/RESOURCES.md` | matériaux, outils, nœuds, butin (généré par script), audit et limites |
| `docs/CLIENT_FEASIBILITY.md`, `docs/CLIENT_PATCH.md`, `docs/GUI_TEST.md` | faisabilité addons/MPQ/modèles, patch du client `Wow.exe` (DLL injectée, API Lua), test avec interface |
| `docs/LLM.md` | client LM Studio local pour le chat des bots (optionnel, plus tard) |
| `server/Wowlheim/` | code C++ du module de construction (copié dans l'arbre CMaNGOS par `tools/sync_server.ps1`) |
| `server/core.patch` | modifications du cœur CMaNGOS (diff généré) |
| `server/sql/` | schémas et données SQL de Wowlheim (world et characters) |
| `tools/` | outils et tests (bot de protocole `wlclient.py`, tests d'acceptation, génération SQL, client LLM, patch client) |
| `analysis/` | désassemblages REA de Valheim (artefacts locaux, non distribuables) |

## Emplacements hors dépôt (ce poste)

- Sources CMaNGOS-classic : `C:\Wowlheim\src\mangos-classic` ; build : `C:\Wowlheim\build` ; exécution : `C:\Wowlheim\run` ; données extraites du client : `C:\Wowlheim\data` ; sauvegardes SQL : `C:\Wowlheim\backup`.
- Client 1.12.1.5875 d'origine : `C:\Users\rlebh.RLEBHAR.000\Desktop\WoW Vanilla` (jamais modifié, sauf `realmlist.wtf` pointé sur 127.0.0.1, original en `.orig`) ; copie de test : `C:\Wowlheim\client_test`.
- MySQL 8.4.9 : lancé à la main, `C:\Wowlheim\mysql\my.ini`, 127.0.0.1:3306 uniquement.
- Comptes de test et mots de passe : `C:\Wowlheim\run\test_account*.txt` (hors dépôt).

## Lancer (local)

```powershell
# base de données
& "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe" --defaults-file=C:\Wowlheim\mysql\my.ini --console
# serveurs (deux terminaux)
cd C:\Wowlheim\run; .\realmd.exe -c realmd.conf
cd C:\Wowlheim\run; .\mangosd.exe -c mangosd.conf     # la console mangosd exige un stdin ouvert
```

Reconstruire après modification de `server/` : `powershell -File tools\sync_server.ps1 -Build` ; appliquer le SQL : `python tools\apply_sql.py --backup`.

## Tests d'acceptation (client de protocole, sans interface graphique)

Tout lancer d'un coup (redémarre mangosd et remet les pièces à zéro avant chaque test) : `python tools/run_all.py` (9 tests, ~15 minutes). Sauvegarde des bases : `python tools/backup.py`.

`python tools/<script>.py <compte> <mot_de_passe>` avec le serveur lancé et un compte de test GM :

| Script | Vérifie |
|---|---|
| `login_test.py` | connexion SRP6, royaume, authentification monde |
| `phase3_acceptance.py` | effondrement (colonne, pièce flottante, cascade), usure sous la pluie, pièce couverte épargnée |
| `station_test.py` | établi utilisable seulement à l'abri (toit + couverture ≥ 70 %) |
| `zone_test.py` | construction interdite en ville et près des villages |
| `cost_test.py` | coûts, consommation, remboursement |
| `harvest_test.py` | nœuds : outil du bon type requis, butin ouvert avec le bon outil |
| `craft_test.py` | fabrication à l'établi abrité, refus à l'établi exposé |
| `loot_test.py` | matériaux lâchés par les mobs (comptage) |
| `house_test.py` | critère phase 4 : maison construite uniquement avec du butin, impossible en ville |
| `prod_node_test.py` | nœuds de production : charge (tick) et récolte |
| `level_test.py` | niveaux de station : forge niveau 1 + extensions, niveau de recette requis |
| `api_test.py` | canal `[WL]` : `.build api …` répond par des lignes structurées lisibles par l'addon (Python du venv `tools/client/.venv` pour lupa) |
| `soak_test.py` | stabilité : deux joueurs-bots pendant N minutes (téléports, butin, poses/démolitions) |
| `stress_test.py`, `stress2.py` | stabilité sous poses/démolitions répétées |

## Règles du projet

- Ne jamais réutiliser d'assets de Valheim ni de WoW hors du client légitime ; tout fichier extrait ou désassemblé est un artefact local.
- Rien n'est poussé sur un dépôt distant ; aucun service exposé au réseau (realmd, mangosd et MySQL écoutent sur 127.0.0.1).
- Une hypothèse n'est jamais déclarée vraie sans preuve : voir les légendes [PROUVÉ] / [INFÉRÉ] / [NON EXTRAIT] et les journaux de test.
