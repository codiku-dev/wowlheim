# Addon Wowlheim : menu de construction du marteau

Addon client WoW 1.12.1 (Lua 5.0) qui reproduit le menu du marteau de Valheim. **Jamais chargé en jeu à ce jour** : seuls la syntaxe et le comportement dans une API WoW simulée sont vérifiés (voir « Tests »).

## Installation

Copier le dossier `tools/client/addon/Wowlheim/` (avec `WowlheimData.lua`, `WowlheimCore.lua`, `Wowlheim.lua`, `Wowlheim.toc`, `Bindings.xml`) dans :

```
C:\Wowlheim\client_test\Interface\AddOns\Wowlheim\
```

Les icônes `Interface\Icons\WL_*` viennent du patch client (MPQ) ; sans lui, les icônes s'affichent vides ou vertes.

## Utilisation

- Équiper le **Marteau** (objet 9201100, main droite) ouvre le panneau ; le déséquiper le ferme. Échap le ferme aussi.
- Raccourcis (Menu > Raccourcis, section **Wowlheim**, aucune touche par défaut) : « menu du marteau », « tourner à gauche », « tourner à droite ». `/wl` ouvre/ferme ; `/wl debug` laisse les lignes `[WL]` du serveur visibles dans le chat.
- Onglets : Divers, Fabrication, Construction (par défaut), Construction lourde, Meuble.
- **Clic gauche sur une icône** : la pièce est choisie, puis le ciblage au sol du marteau s'active ; cliquer au sol pour la poser. Après une pose réussie, le ciblage se relance tout seul (pose continue), jusqu'à **clic droit sur le panneau** ou **Échap**.
- **Molette** sur le panneau : rotation par pas de 22,5° ; **Maj + molette** : défilement de la grille. Maj + glisser : déplacer le panneau.
- Divers commence par **Réparer** et **Démolir** : clic droit en jeu sur une construction posée pour la réparer ou la démolir. Choisir une pièce rétablit le mode construction.
- Icône grisée et rougeâtre = ressources insuffisantes (comptées dans les sacs) ; l'encadré affiche « possédé/requis » en rouge s'il en manque, et l'établi requis.

## Commandes envoyées au serveur (`SendChatMessage(..., "SAY")`)

- `.build api select <pieceId> <rot>` (rot 0..15, pas de 22,5°)
- `.build api mode build|remove|repair`
- puis `UseInventoryItem(16)` (sort à cible au sol du marteau) pour la pose.

Réponses lues : messages système `[WL]M|…` (zone de message du panneau), `[WL]E|…` (en rouge dans `UIErrorsFrame`), `[WL]D|<cmd>|0/1` ; une pose est réussie sur `D|place|1` ou un `M|` contenant « posée ». Ces lignes sont masquées du chat.

## Tests (hors jeu)

```
tools/client/.venv/Scripts/python.exe tools/client/addon/test_core.py
tools/client/.venv/Scripts/python.exe tools/client/luacheck_syntax.py tools/client/addon/Wowlheim/Wowlheim.lua
```

`test_core.py` teste `WowlheimCore.lua`, la forme de `WowlheimData.lua` (généré : ne pas éditer), puis charge `Wowlheim.lua` dans une API WoW simulée (clics, molette, pose continue, sacs, marteau). Cela ne garantit pas le comportement du vrai client 1.12.

## Points non vérifiés en jeu

- `Texture:SetTexture` renvoie nil pour un fichier absent (utilisé pour l'icône de secours de « Réparer »).
- `EnableMouseWheel` / `OnMouseWheel` sur des cadres créés en Lua.
- `UseInventoryItem(16)` relancé depuis un `OnUpdate` (sans clic matériel) pour la pose continue.
- Masquage des lignes `[WL]` par la surcharge de `ChatFrame_OnEvent`.
