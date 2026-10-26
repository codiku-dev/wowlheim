# Wowlheim — Cahier des charges

Version du 26 oct. 2026, d'après le document partagé de Robin Lebhar (lien donné en session). Copie de travail du dépôt : en cas de divergence, le document partagé fait foi. L'état d'avancement et les écarts constatés sont dans `STATUS.md`.

Wowlheim est un serveur privé WoW classic 1.12.1 auquel on greffe la construction, la fabrication et la survie de Valheim, avec 2 joueurs et 50 bots qui vivent dans le monde.

## Vision et périmètre

Le jeu reste du WoW classic intact. On ajoute la construction par pièces, la fabrication d'outils à des stations, la pluie et l'abri, avec des ressources obtenues en tuant des mobs cohérents avec leur zone. Principe directeur : rester logique.

| Dans le périmètre | Hors périmètre |
|---|---|
| Serveur CMaNGOS-classic + playerbots | Modification du relief (les cartes sont compilées dans le client) |
| Client 1.12.1 patché via REA | Physique réelle, vent, abattage libre des arbres du décor |
| Construction, intégrité, destruction, pluie, abri | Client Classic Era 1.14+ et Warden |
| Outils et stations façon Valheim | 2000 bots, distribution publique |
| 2 joueurs, 50 bots habitants | Bots bâtisseurs (reportés) |

## Socle technique

CMaNGOS-classic avec le module playerbots, client 1.12.1 (build 5875), développement sur Windows puis déploiement sur le VPS.

| Élément | Choix | Statut |
|---|---|---|
| Serveur | CMaNGOS-classic + playerbots (ike3) | Décidé |
| Client | 1.12.1, build 5875, 32 bits | Décidé |
| Repérage de la logique Valheim | REA sur `assembly_valheim.dll` (Unity Mono) | Décidé |
| Repérage du client | REA sur `Wow.exe` (Ghidra, Hopper ou IDA) | Décidé |
| Hébergement | Hostinger KVM 8 (8 vCPU, 32 Go, vCPU mutualisés) | Décidé |
| OS du serveur final | Linux conseillé | À décider |
| LLM local (personnalités, chat) | Modèle ~9B ou plus petit, jamais en combat (modèle de test retenu en session : `nvidia-nemotron-3.5-bolt-e4b-4gb` via LM Studio) | Décidé |

Pourquoi pas VMaNGOS : plus fidèle au vanilla, mais aucun module de bots trouvé (non prouvé). Pourquoi pas un serveur officiel : Blizzard ne le distribue pas, et le client ne contient pas la logique de jeu.

Chemins sur la machine Windows : REA dans `C:\Users\rlebh.RLEBHAR.000\Documents\GitHub\rea`, Valheim dans `C:\Program Files (x86)\Steam\steamapps\common\Valheim`.

## Mécaniques de jeu

Chaque mécanique reprend les règles exactes de Valheim, extraites par REA et non devinées.

- **Construction :** catalogue de pièces en base (sol, mur, toit, porte, coffre, station...), posées comme GameObjects avec snap sur grille, persistées en base et recréées au démarrage.
- **Intégrité structurelle :** graphe de supports recalculé à chaque pose ou destruction. Une pièce sans support suffisant s'effondre.
- **Destruction :** les pièces ont des PV et peuvent être détruites ; la cascade d'effondrement suit l'intégrité. Base technique à vérifier : objets destructibles en 1.12.
- **Pluie et humidité :** la météo est lue par zone côté serveur. Une pièce sans toit au-dessus perd des PV sous la pluie, une pièce couverte est épargnée.
- **Abri :** une station ne fonctionne que si un toit la couvre.
- **Zones :** construction interdite en ville, autorisée ailleurs avec un plafond de pièces par joueur et par zone (à fixer).

## Outils, stations et progression

Le combat reste 100 % équipement WoW classique. Les outils ne donnent aucune stat : ils servent à récolter, et ils s'améliorent uniquement par les stations.

- **Outils :** objets à nous (hache de bûcheron, pic...) fabriqués à l'établi, jamais en butin. Les haches WoW normales ne récoltent rien. Un outil est une arme à faibles dégâts : on rééquipe son arme de combat pour se battre.
- **Amélioration :** un nouvel objet par palier (pierre, bronze, fer), avec une vitesse de récolte plus élevée. Durabilité : celle de WoW.
- **Stations :** établi, forge et marteau de construction. Le niveau d'une station dépend des extensions posées à proximité. Valeurs exactes à extraire de Valheim.
- **Nœuds de ressources :** les arbres du décor WoW ne sont pas interactifs, on pose donc des nœuds de bois et de pierre (GameObjects récoltables qui réapparaissent). Le minage de Valheim est indépendant des métiers WoW : pic fabriqué et nœuds de minerai à nous, sans niveau de compétence ni emplacement de métier. Les filons, le dépeçage et les métiers WoW restent un système séparé.

| Palier | Matériau | Source |
|---|---|---|
| 1 | Bois | Tréants, ents, nœuds de bois |
| 2 | Pierre | Élémentaires de terre, golems, nœuds de pierre |
| 3 | Cuir, corde | Bêtes (butin direct, sans dépeçage) |
| 4 | Métal | Nœuds de minerai à nous, mobs de mines |
| 5 | Rares | Dragons, démons, géants |

Un mob ne lâche que les ressources du palier de sa zone. L'équilibrage se fait par calcul (objectif de farm par construction type), avec les bots comptés dans la consommation.

## Ressources : conception détaillée

Objectif : ne jamais être bloqué plus de quelques minutes par une ressource introuvable, tout en gardant la progression par paliers de Valheim. Les tranches de niveaux et les noms ci-dessous sont des propositions, à corriger après l'audit de la base (étape 1 de la validation).

### Règles anti-blocage

1. **Trois sources minimum par ressource :** un butin de famille de mobs, un nœud récoltable, et une source de secours (vendeur à prix élevé ou conversion à l'établi).
2. **Disponible partout :** chaque ressource se trouve dans au moins 3 zones par continent (Kalimdor et Royaumes de l'Est) et pour les deux factions.
3. **Règles par famille, pas par mob :** le butin se définit par famille de créature × tranche de niveau, via des tables de référence partagées. Un mob de plus hérite des règles sans retouche.
4. **Taux généreux :** 30 à 60 % de chance avec des quantités variables pour les matériaux de base. Aucun matériau nécessaire à 1 %.
5. **Pas de goulot unique :** le matériau qui ouvre le palier suivant (l'équivalent des boss de Valheim) vient d'au moins deux sources répétables, jamais d'un seul boss ni d'un seul mob.
6. **Retour en arrière possible :** les mobs d'un palier lâchent aussi les matériaux du palier d'avant, à taux réduit.
7. **Nœuds denses :** beaucoup de nœuds de bois et de pierre, réapparition courte, pour que 2 joueurs et 50 bots ne vident pas une zone.

### Matériaux par type de créature

| Famille | Matériaux |
|---|---|
| Bêtes | Peaux, os, viande, griffes |
| Humanoïdes | Tissu, cordage, ferraille, clous |
| Élémentaires | Pierre, minerai brut, cristaux |
| Morts-vivants | Os, poussière d'os, fil |
| Dragonkin, démons, géants | Matériaux rares, matériau de passage |
| Tréants et plantes | Bois, résine (famille à vérifier dans la base) |

### Paliers

Tous les matériaux de construction sont des objets à nous, avec les noms de Valheim, sans aucun lien avec les métiers WoW (minage, dépeçage, travail du cuir, forge). Les joueurs gardent leurs deux métiers WoW pour eux : récolter pour Wowlheim ne demande ni métier ni niveau de compétence, seulement l'outil fabriqué. Pour ne jamais confondre les deux systèmes : une catégorie d'objet dédiée, une ligne d'infobulle « Wowlheim », et aucune recette WoW n'utilise ces matériaux. Les paliers suivent l'ordre des biomes de Valheim ; les noms et la répartition sont à confirmer dans les fichiers du jeu avec REA (donnés de mémoire dans le document d'origine).

| Palier | Niveaux | Biome Valheim | Matériaux |
|---|---|---|---|
| 1 | 1 – 15 | Prairie | Bois, Pierre, Silex, Résine, Peau de cerf, Chutes de cuir |
| 2 | 15 – 28 | Forêt noire | Bois fin, Bois de cœur, Cuivre, Étain (bronze), Peau de troll |
| 3 | 28 – 40 | Marais | Fer, Écorce ancienne, Fragments d'os, Entrailles |
| 4 | 40 – 52 | Montagne | Argent, Obsidienne, Fourrure de loup, Cristal |
| 5 | 52 – 60 | Plaines | Métal noir, Lin, Fil de lin, Peau de lox |

Chaque palier a aussi un **matériau de passage** (à définir) venant d'au moins deux sources répétables. Les recettes d'un palier consomment au moins deux familles de matériaux, pour qu'aucune ressource ne soit inutile : pièces de construction par matériau (bois, pierre, métal), outils, extensions de station.

### Méthode de validation

1. **Auditer la base :** compter, par famille de créature et par tranche de niveau, les mobs et les zones disponibles par continent et par faction (type, famille et niveaux de `creature_template`, noms des champs à vérifier).
2. **Construire la matrice** ressources × (famille, tranche) avec les taux, puis la générer en SQL par script, jamais à la main.
3. **Contrôler automatiquement :** chaque ressource a au moins 3 sources, chaque ingrédient de recette est atteignable au palier de la recette, chaque palier couvre au moins 3 zones par continent.
4. **Simuler le temps de farm** avec des objectifs à calibrer (par exemple : outil de base environ 10 min, abri de base environ 30 min, station suivante environ 1 h de chasse).
5. **Tester en jeu** avec 2 joueurs et 50 bots, puis ajuster les taux.

## Client patché et interface

On modifie le client au cœur, sans version de repli : l'analyse REA de `Wow.exe` (32 bits) sert à injecter une DLL ou patcher le binaire pour ajouter ce que le jeu ne sait pas faire.

- **Fonctions ajoutées :** aperçu fantôme d'une pièce avant la pose, panneau de construction, panneau d'établi, canal propre entre client et serveur.
- **Interface :** fidèle à Valheim en fonctionnement et en disposition (liste de recettes, ressources requises, aperçu), avec des assets propres. Le rendu pixel-identique n'est pas garanti, l'interface Unity ne se transplante pas dans le client WoW.
- **Modèles :** chaîne d'import des modèles Valheim (arbres, pièces) : extraction des maillages et textures Unity, simplification et conversion en M2, empaquetage MPQ avec entrées DBC, référence côté serveur. On valide d'abord avec un seul arbre.
- **Droits :** les assets de Valheim restent pour un usage privé non distribué. Si le projet sort de ce cadre, il faudra les remplacer. (Règle donnée en consigne de session : ne réutiliser aucun asset de Valheim ni de WoW hors du client légitime.)

## Plan de livraison

Six phases (0 à 5), dans l'ordre. Chacune a un critère de réussite à vérifier avant de passer à la suivante.

| Phase | Contenu | Critère de réussite |
|---|---|---|
| 0. Préparation | Outils Windows, REA, analyse de `assembly_valheim.dll` | Résultats d'analyse avec preuves |
| 1. Serveur de base | CMaNGOS compilé, cartes extraites, bases importées, 50 bots | 2 joueurs jouent normalement, serveur stable 1 h |
| 2. Construction minimale | Table de pièces, pose, persistance, mesure du diff tick | 100 pièces posées survivent à un redémarrage |
| 3. Règles Valheim | Intégrité, destruction, pluie, abri, stations | Une structure sans support s'effondre, une pièce sans toit se dégrade |
| 4. Ressources et zones | Loot par palier, outils, zones interdites en ville | Une maison complète construite avec du butin, impossible en ville |
| 5. Client patché | Aperçu, panneaux, modèles, outils fabriqués | Un joueur construit et fabrique depuis l'interface |

Les bots bâtisseurs sont reportés après la phase 5. Le client 1.12.1 intact est requis dès la phase 1 (extraction des cartes) et pour la phase 5.

## Risques et points à vérifier

| Risque ou hypothèse | Impact | Parade |
|---|---|---|
| Client 1.12.1 introuvable ou modifié | Élevé | Discord CMaNGOS, vérifier build 5875, tester l'extraction des cartes |
| Patch du client sans repli | Élevé | Analyse REA dès la phase 0, tests de plantage fréquents |
| Objets destructibles en 1.12 | Moyen | Test dès la phase 2 |
| Limites M2 et modèles custom | Moyen | Un seul arbre pour valider la chaîne |
| Charge due aux GameObjects sur vCPU mutualisés | Moyen | Mesure du diff tick, plafond de pièces |
| Génération auto des nœuds de bois | Moyen | Pose manuelle sur 1 ou 2 zones d'abord |
| Aspect légal | Faible | Projet privé, aucune distribution ni publicité |

## Questions ouvertes et définition de terminé

Le projet est terminé quand 2 joueurs et 50 bots jouent 1 h sans crash, qu'un joueur construit une maison hors ville avec du butin, la voit s'effondrer si elle est mal soutenue et se dégrader sous la pluie sans toit, et que tout survit à un redémarrage.

- Durée et vitesse de la dégradation sous la pluie, réparation, effet « mouillé » sur les joueurs
- Droits des autres joueurs et des bots sur les pièces d'autrui
- Remboursement lors d'une démolition volontaire
- Plafond de pièces par joueur et par zone
- OS du serveur final, fréquence et lieu des sauvegardes
- Modèle LLM local retenu (français, vitesse sur la carte graphique)
