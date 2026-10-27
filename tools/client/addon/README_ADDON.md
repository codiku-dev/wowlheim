# Addon Wowlheim : marteau, fabrication, fonderie

Addon client WoW 1.12.1 (Lua 5.0) qui reproduit le menu du marteau de Valheim, le panneau de fabrication (onglet Fabrication de l'inventaire) et l'interaction avec la fonderie / le four à charbon. **Jamais chargé en jeu à ce jour** : seuls la syntaxe et le comportement dans une API WoW simulée sont vérifiés (voir « Tests »).

## Installation

Copier le dossier `tools/client/addon/Wowlheim/` (avec `WowlheimData.lua`, `WowlheimCore.lua`, `Wowlheim.lua`, `WowlheimCraft.lua`, `Wowlheim.toc`, `Bindings.xml`) dans :

```
C:\Wowlheim\client_test\Interface\AddOns\Wowlheim\
```

Les icônes `Interface\Icons\WL_*` viennent du patch client (MPQ) ; sans lui, les icônes s'affichent vides ou vertes.

## Utilisation

- Équiper le **Marteau** (objet 9201100, main droite) ouvre le panneau ; le déséquiper le ferme. Échap le ferme aussi.
- Raccourcis : voir « Touches et disposition des panneaux » ci-dessous (**Y** menu, **I** fabrication, **J** fonderie, **Alt+A / Alt+E** ou **Ctrl + molette** : tourner). `/wl` ouvre/ferme ; `/wl reset` remet les panneaux à leur place par défaut ; `/wl debug` laisse les lignes `[WL]` du serveur visibles dans le chat.
- Onglets : Divers, Fabrication, Construction (par défaut), Construction lourde, Meuble.
- **Clic gauche sur une icône** : la pièce est choisie, **le menu se masque** (comme dans Valheim, pour dégager le sol) et le ciblage au sol du marteau s'active ; cliquer au sol pour la poser. Pendant la pose, « `Mur  -  Rotation : 22,5°` » est rappelé en petit en haut de l'écran. Après chaque pose (réussie **ou refusée**, ou ratée côté client : `SPELLCAST_FAILED`), le ciblage se relance tout seul : **la pièce reste choisie** (pose continue), jusqu'à **Échap**, clic droit (menu) ou rangement du marteau.
- **Contrôles de Valheim en mode construction** (marteau équipé, mode construction ; `docs/BUILD_CONTROLS.md`) — on n'est plus « en combat » :
  - **clic gauche** au sol : poser, puis enchaîner (sans rouvrir ni fermer le menu) ;
  - **clic droit** : ouvre le menu de construction. Le client annule le ciblage au sol ; l'addon détecte « ciblage terminé sans pose » (ni `SPELLCAST_START/STOP/FAILED`, ni ligne `D|place|…`, ni Échap dans les 0,3 s ; ou `IsMouseButtonDown("RightButton")` s'il existe) et ouvre le menu **sans relancer le ciblage** ; la pièce reste choisie, choisir une pièce relance. `TurnOrActionStart/Stop` (protégées) ne sont **pas** touchées ;
  - **clic milieu** : démolit la pièce **sous la souris** (DLL : `WowlheimGetMouseoverObject()` → `.build api removeguid <guidHex>` ; « Rien à démolir. » si ce n'est pas une pièce ; sans DLL : `.build api remove`, pièce la plus proche à 6 m). Le ciblage et la pose continue restent actifs ;
  - **molette** : tourne la pièce (22,5° par cran ; ne zoome plus pendant la construction) ;
  - option **`/wl qe on`** (`/wl qe off` pour revenir) : Q / E tournent aussi la pièce (sinon pas latéraux de WoW).
- **Liaisons temporaires** : `BUTTON3` → `WOWLHEIM_REMOVE`, `MOUSEWHEELUP` / `MOUSEWHEELDOWN` → `WOWLHEIM_ROTATE_RIGHT` / `LEFT` (et Q / E avec l'option) par `SetBinding` **sans `SaveBindings`** ; l'ancienne valeur (`GetBindingAction`) est mémorisée (aussi dans `WowlheimDB.tempBinds`) et **rétablie** au rangement du marteau, en mode Démolir / Réparer, à `PLAYER_LEAVING_WORLD` / `PLAYER_LOGOUT` (déconnexion, `/reload`) et par `/wl reset`. À l'entrée en jeu, une liaison temporaire restée active (plantage) est rétablie d'après `WowlheimDB.tempBinds`, et une liaison temporaire enregistrée par erreur (menu Raccourcis validé pendant la construction) est remise à la valeur d'origine du client. Une touche reliée par le joueur entre-temps n'est jamais écrasée.
- **Rouvrir le menu** : clic droit pendant la pose, touche de bascule (la pose en cours est conservée) ou rééquiper le marteau. Fermer soi-même le menu (Échap, bascule) arrête la pose. Menu masqué, la rotation se fait à la molette ou avec les touches « tourner à gauche / à droite ».
- **Molette** sur le panneau : rotation par pas de 22,5° ; **Maj + molette** : défilement de la grille. Maj + glisser : déplacer le panneau (position mémorisée). Bouton « x » en haut à droite : fermer (comme Échap).
- Divers commence par **Réparer** et **Démolir** (le menu se masque aussi) : clic droit en jeu sur une construction posée pour la réparer ou la démolir (liaisons d'origine de la souris dans ces modes). Le mode reste actif quand on ferme le menu (Échap, clic droit, fermeture) : on peut démolir / réparer menu fermé, et « Mode : Démolir » / « Mode : Réparer » est rappelé en haut de l'écran tant que le marteau est équipé. Seul le choix d'une pièce rétablit le mode construction.
- Icône grisée et rougeâtre = ressources insuffisantes (comptées dans les sacs) ; l'encadré affiche « possédé/requis » en rouge s'il en manque, et l'établi requis.
- **Recherche** : champ « Rechercher une pièce... » sous les onglets. Cliquer dedans pour taper (tant qu'il a le focus, les touches vont au texte : Y, I, J, Alt+A… ne déclenchent rien) ; **Entrée** ou **Échap** rend le clavier au jeu. Filtre sur le nom **et** la description, sans tenir compte des accents ni de la casse (« ecorce » trouve « Écorce ancienne » ; plusieurs mots = tous requis). Pendant une recherche, résultats de **toutes les catégories** et onglets désélectionnés (comme Valheim) ; cliquer un onglet efface la recherche.
- **Pièces connues (progression Valheim)** : une pièce n'apparaît que si **tous** ses matériaux sont connus (déjà possédés au moins une fois) et sa station connue ; sinon elle est **cachée** (pas grisée). Les pièces connues mais trop chères restent en rouge. Voir « Objets connus » ci-dessous.

## Objets connus (`.build api known`)

- Interrogé silencieusement à l'ouverture du menu du marteau et du panneau de fabrication, puis après `BAG_UPDATE` (au plus une fois par seconde, panneau ouvert, une seule interrogation en attente).
- Réponse : `K|item:<id>,<id>,…` (objets déjà possédés), `KS|<kind>:<niveau>,…` (stations connues), `KP|<pièce>,…` (pièces connues, règle Valheim appliquée par le serveur), `KR|<recette>,…` (recettes connues : station connue au niveau requis + ingrédients connus), puis `D|known|1`. Les listes longues arrivent en plusieurs lignes au même préfixe (concaténées) ; tout n'est remplacé qu'à `D|known|1`.
- **KP / KR font foi** pour le menu du marteau / le panneau de fabrication. Union locale en plus : une pièce / recette dont tous les matériaux sont connus **ou dans les sacs** et la station connue (au niveau requis pour une recette) ou à portée (`S|`, cercles `ST|`) est aussi affichée, sans attendre la réponse suivante.
- `KN|item|<id>` / `KN|station|<kind>|<niveau>` (spontanés, connaissance acquise) : ajoutés tout de suite, puis `known` est relancé discrètement (même panneaux fermés, au plus une fois par seconde). Annonces avec les textes de Valheim (`MessageHud.QueueUnlockMsg`) : `KN|item` → « Nouveau matériau : Bois » / « Nouvel objet : Marteau », `KN|station` → « Nouvel établi : Table de fabrication » / « Établi mis à niveau : … niveau 2 » ; pièces / recettes apparues depuis la réponse précédente → « Nouvelle pièce de construction : Mur en bois (+2) » (zone de message du menu, sinon `UIErrorsFrame`), « Nouvelle recette : Marteau » (panneau de fabrication, sinon `UIErrorsFrame`). Les noms des recettes viennent de `WowlheimData.recipes` (généré) : `KR|` ne donne que des identifiants. Un même texte n'est affiché qu'une fois par seconde au centre de l'écran (`WowlheimCore.DedupPass`).
- Compatibilité : tant qu'aucune réponse n'est arrivée, ou avec un ancien serveur (`E|commande inconnue` + `D|known|0`, rattachés à la commande et non affichés), **tout est affiché** ; après `D|known|0` sans liste, plus d'interrogation sur `BAG_UPDATE`.
- Même règle pour les recettes du panneau de fabrication (ingrédients + station de la recette).

## Touches et disposition des panneaux

Touches par défaut (`WowlheimCore.DEFAULT_KEYS`), toutes **libres** dans les liaisons d'origine du client 1.12.1 (`WTF\DefaultBindings.wtf` de `patch.MPQ`, extrait avec `mpq_layers.py ... extract tools/client/extracted "WTF\DefaultBindings.wtf"` ; vérifié par `test_core.py` si le fichier est extrait) :

| Action | Touche | Pourquoi |
|---|---|---|
| Menu du marteau | **Y** | libre ; main gauche, au-dessus de T / G. B (sacs), C, P, N, O, L, M, U, H, K, V, Z, X, T, G, F, R sont pris. |
| Fabrication | **I** | libre (seul Maj+I est pris : grimoire du familier) ; « inventaire », comme Tab dans Valheim (Tab = cibler un ennemi dans WoW). |
| Fonderie / four à charbon | **J** | libre ; le panneau s'ouvre aussi tout seul au clic sur la station. |
| Compétences | **Maj+K** | libre (K = compétences de WoW). Posée une fois à la mise à jour (liaisons version 2, `since = 2`), seulement si libre ; une touche retirée auparavant n'est pas reposée. |
| Tourner à gauche / à droite | **Alt+A / Alt+E** | A = tourner à gauche, E = pas latéral droit dans WoW ; Alt+A / Alt+E sont libres. En AZERTY, A et E encadrent Z (avancer) comme Q / E dans Valheim (Q et E seuls sont des déplacements : NON). |
| Tourner (molette) | **Ctrl + molette** (haut = droite, bas = gauche) | la molette seule zoome la caméra, Maj + molette change de barre d'action ; Ctrl + molette est libre. Sur le menu, la molette seule tourne toujours. **Molette seule en mode construction** : liaison temporaire (voir « Utilisation »). |
| Démolir la pièce visée | **clic milieu** en mode construction | liaison temporaire `BUTTON3` → `WOWLHEIM_REMOVE` (d'origine `MOVEANDSTEER`), rétablie à la sortie du mode. |

Ni ZQSD / WASD, ni flèches, ni chiffres / -, = (barre d'action), ni Échap, Entrée, Espace, Tab. Les touches par défaut d'un addon 1.12 ne s'appliquent pas seules : à la première entrée en jeu, `Wowlheim.ApplyDefaultBindings` fait `SetBinding(touche, action)` **seulement si** `GetBindingAction(touche)` est vide **et** si l'action n'a pas déjà une touche (choix du joueur), puis `SaveBindings(GetCurrentBindingSet())`. C'est fait **une seule fois** (`WowlheimDB.bindingsDone`) : une touche retirée ou changée par le joueur dans Menu > Raccourcis (section **Wowlheim**) n'est jamais reposée.

Disposition par défaut (`WowlheimCore.PanelDefaultPos`, unités de l'interface, 768 de haut) : le centre de l'écran (personnage, sol devant lui) reste libre dès le 16:9, les panneaux ne se superposent pas et ne couvrent pas le bandeau « Mode : … » / le rappel de pose (haut, centre) ; vérifié en 1024×768, 1365×768 et 1835×768 (3440×1440 de Robin) :

- menu du marteau (échelle 0,85) : **en bas à droite**, au-dessus des barres d'action (96) et à gauche des barres verticales (100) ;
- fabrication (échelle 0,8) : **en haut à gauche**, sous les cadres joueur / cible ;
- fonderie (échelle 0,85) : en haut, **à droite de la fabrication**.

Les trois se déplacent en glissant (Maj + glisser pour le menu du marteau, dont le clic gauche choisit une pièce) ; la position est mémorisée dans `WowlheimDB.pos` (ramenée dans l'écran si la résolution change). `/wl reset` : positions par défaut. Fermeture : bouton « x » ou Échap (`UISpecialFrames`).

## Panneau de fabrication (`WowlheimCraft.lua`)

- Ouverture : `/wlcraft` ou la touche **I** (« Wowlheim : fabrication »). Échap ou « x » ferme.
- **Clic droit sur une table de fabrication / forge / tailleur de pierre / table d'artisan** en jeu : le serveur envoie d'abord les lignes `S|guid|utilisable|couverture|niveau|kind` des stations à portée, puis `OPEN|craft|<guid>|<kind>` (déclencheur) ; ces `S|` deviennent la station du panneau et le panneau s'ouvre (s'il est déjà ouvert, il reste ouvert et se met à jour, sans bascule). La fonderie / le four à charbon gardent leur ouverture sur `SM|`.
- **Recherche** : champ « Rechercher une recette... » au-dessus de la liste (même fonctionnement que dans le menu du marteau : nom + description de l'objet produit, sans accents ni casse, Entrée / Échap pour sortir). Pendant une recherche, les recettes de **toutes les stations** sont cherchées. Recettes inconnues cachées (voir « Objets connus »).
- **Réparer** (bouton marteau en bas à droite, comme Valheim) : `.build api repairable [guid de la station du panneau]` (silencieux, à l'ouverture et toutes les 5 s) → `RS|guid|kind|niveau`, `RI|item|durabilité|max` par objet usé réparable, `D|repairable` ; le bouton affiche « Réparer (n) » et n'est actif que s'il y a des objets abîmés réparables à cette station (`D|repairable|0` : liste vidée). Clic : `.build api repairitems <guid RS>` → `R|item,…`, `M|Réparé : …` (ou `E|…`) dans la zone de message du panneau, `D|repairitems`, puis nouvelle liste. Une recette dont l'objet produit est abîmé et réparable ici a un petit marteau à droite de sa ligne, et la fiche affiche « Abîmé (40 %) : réparable ici ». Ancien serveur (`E|commande inconnue` + `D|repairable|0`) : bouton inactif, plus d'interrogation.
- À gauche, les recettes disponibles : celles **sans station** (fabrication à la main : marteau, hache en pierre…) sont toujours là, plus celles de la **station à portée**. Réalisables d'abord, puis les autres (grisées). Molette : défilement. Le bouton en haut à droite bascule « Station à portée » / « Toutes les stations ».
- À droite : objet produit (icône, nom, quantité, description), station requise et niveau requis / actuel (en rouge si insuffisant), ressources requises avec icône et « possédé/requis » (rouge s'il en manque), bouton **Fabriquer** (inactif si la recette n'est pas réalisable ou pendant une fabrication).
- Limite serveur : `.build api station` ne signale que l'**établi** (`workbench`). Les recettes de forge, tailleur de pierre, table d'artisan, four à charbon n'apparaissent donc qu'avec « Toutes les stations » ; leur bouton reste actif si les ressources suffisent et le serveur vérifie la station et son niveau à la fabrication.
- Rafraîchissements : station + recettes à l'ouverture, station toutes les 5 s, inventaire sur `BAG_UPDATE`.

## Panneau de fonderie / four à charbon

- Ouverture : `/wlsmelt` ou la touche **J** (« Wowlheim : fonderie / four à charbon », station la plus proche à 5 m), et **automatiquement** quand le serveur envoie une ligne `SM|` non sollicitée (clic sur la station en jeu).
- Affiche : nom et état (En marche, Vide, Plus de combustible, Nécessite un toit, Fumée bloquée), minerai en file / max (barre), combustible / max (barre ; absent du four à charbon), progression de la cuisson (s), produits prêts (icônes + nombres).
- Boutons : **Ajouter minerai** (« Ajouter du bois » au four à charbon), **Ajouter charbon**, **Récupérer** ; inactifs si la station est pleine, si rien de transformable / pas de combustible dans les sacs, ou s'il n'y a rien à récupérer. Clic = 1 unité (interrupteur de Valheim) ; **Maj + clic** = remplir (maintien de l'interrupteur).
- Rafraîchi toutes les 2 s (`status <guid>`) tant que le panneau est ouvert ; fermé automatiquement si la station n'est plus à portée (`E|trop loin` / `E|aucune station`).

## Commandes envoyées au serveur (`SendChatMessage(..., "SAY")`)

- `.build api select <pieceId> <rot>` (rot 0..15, pas de 22,5°)
- `.build api mode build|remove|repair`
- `.build api removeguid <guidHex>` (clic milieu : pièce sous la souris, GUID 64 bits du gameobject en 16 chiffres hexadécimaux) → `M|<nom> démolie.` + `D|removeguid|1`, ou `E|<raison>` (`Rien à démolir.`, `Trop loin.` au-delà de 5 m, `Cette pièce ne vous appartient pas.`, station requise absente, `Vous êtes trop fatigué.`, `Équipez le marteau.`) + `D|removeguid|0`. Mêmes règles que le clic en mode Démolir (`BuildingMgr::TryRemoveByPlayer` : remboursement, endurance, usure du marteau, compétence) ; le mode du marteau ne change pas.
- `.build api models` (silencieux, à l'équipement du marteau si la DLL fournit `WowlheimPreloadModel`) → `MD|id:prefab,…` (lignes concaténées) + `D|models|1` : les modèles `World\Wowlheim\<prefab>.m2` des pièces connues sont préchargés par `WowlheimPreloadModel`, 10 par image (repris à chaque entrée dans le monde : la DLL les libère au changement de carte). `WowlheimSetInstantFade(9110000, 9119999, 9300000, 9300099)` est appelé à l'entrée en jeu (apparition sans fondu).
- puis `UseInventoryItem(16)` (sort à cible au sol du marteau) pour la pose.
- Fabrication : `.build api station`, `.build api recipes`, `.build api craft <recetteId>`, `.build api repairable`, `.build api repairitems`.
- Objets connus : `.build api known` (silencieux).
- Fonderie : `.build api smelter status [guid]`, `.build api smelter add ore|fuel <n> [guid]`, `.build api smelter take [guid]`.
- Cercles de portée des stations (marteau équipé, mode construction) : `.build api stations` silencieux toutes les 1,5 s ;
  réponse `ST|guid|kind|x|y|z|portée|dedans|n` + `SG|guid|premier|x,y,z,o;…` (contour au sol), segments posés par la DLL
  (`WowlheimMarkerShow`, vert dans la zone / rouge hors zone) ; « Hors de portée de la table de fabrication » dans le bandeau
  de pose. Détails : `docs/GHOST_PREVIEW.md` §2bis.

Réponses lues : messages système `[WL]M|…` (zone de message du panneau), `[WL]E|…` (en rouge) ; un message n'est affiché qu'une fois (panneau ouvert, sinon `UIErrorsFrame`), et les refus déjà notifiés par le serveur (refus de pose `M|Pose refusée…` + `D|place|0`, refus de démolition / réparation `E|`) ne sont pas recopiés dans `UIErrorsFrame`, `[WL]D|<cmd>|0/1` ; une pose est réussie sur `D|place|1` ou un `M|` contenant « posée ». Ces lignes sont masquées du chat.

Lignes des panneaux (format exact, analysé par `WowlheimCore.ParseLine`) :

- `C|id|nom|station|sortieItem:qte|item:qte,item:qte|niveauMin` (station vide = à la main) ;
- `S|guid|utilisable 0/1|couverture %|niveau` (établi seulement ; sans `S|` avant `D|station`, pas d'établi à portée) ;
- `SM|guid|kind|nom|file|maxMinerai|combustible|maxCombustible|objetCombustible|cuisson s|s par produit|actif 0/1|raison|file item:n,…|produits item:n,…` (`server/Wowlheim/Smelter.cpp`, `SmelterMgr::StatusLine` ; raison : ok, noore, nofuel, off, roof, smoke) ;
- `A|n` (unités ajoutées par `smelter add`) ;
- `K|item:id,…`, `KS|kind:niveau,…`, `KP|pièce,…`, `KR|recette,…` (`known`) ; `KN|item|id`, `KN|station|kind|niveau` (spontanés) ; `OPEN|craft|guid|kind` (clic sur une station de fabrication, après ses `S|`) ;
- `RS|guid|kind|niveau`, `RI|item|durabilité|max` (`repairable`), `R|item,…` (`repairitems`) ;
- `MD|id:prefab,…` (`models`).

Le serveur répond aux commandes d'une session dans l'ordre et termine chacune par `D|<cmd>|…` : l'addon garde la file des commandes envoyées (`WowlheimCore.ChannelRoute`, oubli après 6 s sans réponse) pour savoir à quelle commande appartient chaque ligne. Les rafraîchissements automatiques sont « silencieux » (leurs `M|` ne s'affichent pas) ; les `M|`/`E|` de fabrication et de fonderie s'affichent dans la zone de message du panneau concerné.

## Tests (hors jeu)

```
tools/client/.venv/Scripts/python.exe tools/client/addon/test_core.py
tools/client/.venv/Scripts/python.exe tools/client/luacheck_syntax.py tools/client/addon/Wowlheim/Wowlheim.lua
```

`test_core.py` teste `WowlheimCore.lua` (dont l'analyse des lignes C/S/SM, le canal, possédé/requis, station/niveau, l'état des boutons), la forme de `WowlheimData.lua` (généré par `tools/valheim/gen_server_sql.py`, fonction `write_lua` : ne pas éditer ; il contient aussi les objets produits par les recettes, leurs descriptions et `WowlheimData.smelters`), puis charge `Wowlheim.lua` et `WowlheimCraft.lua` dans une API WoW simulée (clics, molette, pose continue, sacs, marteau, panneaux de fabrication et de fonderie). Cela ne garantit pas le comportement du vrai client 1.12.

## Points non vérifiés en jeu

- `Texture:SetTexture` renvoie nil pour un fichier absent (utilisé pour l'icône de secours de « Réparer »).
- `EnableMouseWheel` / `OnMouseWheel` sur des cadres créés en Lua.
- `UseInventoryItem(16)` relancé depuis un `OnUpdate` (sans clic matériel) pour la pose continue.
- Clic droit pendant le ciblage = annulation du ciblage par le client (`docs/BUILD_CONTROLS.md` §2), détectée par `SpellIsTargeting()` vrai → faux sans `SPELLCAST_*` ni `D|place` dans les 0,3 s ; `IsMouseButtonDown` en 1.12 ; ordre réel des événements `SPELLCAST_*` et de la fin du ciblage. Échap : surcharge de `ToggleGameMenu` (fin de la pose si un ciblage est en cours ou vient d'être annulé).
- Liaisons temporaires : `SetBinding(touche)` sans action pour délier ; liaison d'addon déclenchée par `BUTTON3` et la molette **pendant** un ciblage au sol ; liaisons gardées ou non en mémoire au `/reload` (les deux cas sont gérés par `WowlheimDB.tempBinds`) ; `PLAYER_LEAVING_WORLD` / `PLAYER_LOGOUT` reçus avant l'écriture des variables sauvegardées.
- DLL non lancée en jeu : `WowlheimGetMouseoverObject()` pendant le ciblage, `WowlheimPreloadModel` (chemin `.m2` alors que la DBC donne `.mdx`), `WowlheimSetInstantFade` (`docs/BUILD_CONTROLS.md` §7).
- Masquage des lignes `[WL]` par la surcharge de `ChatFrame_OnEvent`.
- Touches par défaut : `SetBinding` / `SaveBindings` à `PLAYER_ENTERING_WORLD` (liaisons du personnage déjà chargées ?), noms `ALT-A` / `CTRL-MOUSEWHEELUP`, et lettre produite par un clavier AZERTY (A et E supposés être les touches marquées A et E). Positions : `SetScale` + `GetLeft()` × `GetScale()` = unités de UIParent ; `SetClampedToScreen`.
- Panneaux de fabrication et de fonderie : disposition, `StatusBar` (`SetStatusBarTexture`, `SetMinMaxValues`), `FontString:SetFontObject`, `Button:Disable()` sur des boutons créés en Lua, `arg1` = temps écoulé dans `OnUpdate`.
- Réponses du serveur réel aux commandes `recipes` / `station` / `craft` / `smelter` (seul leur format a été lu dans le code C++).
- Champs de recherche : `CreateFrame("EditBox")` créé en Lua (`SetAutoFocus(false)`, `SetFontObject`, `SetTextInsets`, scripts `OnTextChanged` / `OnEscapePressed` / `OnEnterPressed` / `OnEditFocusGained` / `OnEditFocusLost`) ; repli des accents par `string.gsub` sur des séquences UTF-8 (textes du client supposés en UTF-8).
- Réponses `known`, `repairable`, `repairitems` et lignes `KN|` / `OPEN|craft` : formats communiqués par l'agent serveur, non relus dans le code C++ ni testés contre le serveur réel.
- Un `M|` non sollicité (ex. « posée » après une pose au sol) qui arrive pendant un rafraîchissement silencieux est masqué (affichage seulement : la pose continue n'est pas affectée).

## Endurance et compétences (`WowlheimSkills.lua`)

- Serveur : `EN|cur×10|max×10|délai_ms|clignote`, `SK|id|niveau|pourcentage`, `SKU|id|niveau`, `SKL|pourcentage` ; demande `.build api skills` à l'entrée en jeu et à l'ouverture du panneau (silencieuse).
- Barre d'endurance jaune (200 × 8) en haut au centre, juste au-dessus du bandeau « Mode : … » / rappel de pose ; affichée seulement avec un marteau, une hache ou une pioche Valheim en main, ou pendant la régénération (simulée entre deux `EN|` avec la formule de Valheim) ; clignote (rouge) quand le serveur refuse un coup faute d'endurance.
- Panneau Compétences (Maj+K, `/wl skills`, en bas à gauche, déplaçable, Échap) : Haches, Pioches, Couper du bois, Fabrication avec niveau et barre de progression.
- Montée de niveau : « Compétence améliorée » / « Couper du bois niveau 2 » au centre de l'écran (3 s) ; perte à la mort : « Compétences abaissées (-5 %) ».
