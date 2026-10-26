# Wowlheim - test GUI du client reel (etat : BLOQUE a l'ecran EULA)

Date : 2026-10-26. Client : copie `C:\Wowlheim\client_test` (jamais l'original). Captures dans `tools/client/gui/shots/` (artefacts locaux, non distribuables).

## Outils (tools/client/gui/) - verifies
- `wgui.py` (ctypes pur, aucun paquet) : recherche de la fenetre, capture BitBlt (et PrintWindow), clics et frappe SendInput par scancodes (disposition clavier courante).
- `screenshot.py <png> [--pw|--screen]`, `type.py --click X,Y --key enter --text ... --textfile F --shot f.png --sleep S`.
- `launch_wow.ps1 [-Dll]` (sans DLL : Start-Process ; avec DLL : `launch_play.exe`, variante de `dll/launch.cpp` qui ne tue plus le jeu quand le delai vaut 0 ; compilee, NON testee). `stop_wow.ps1` (WM_CLOSE puis taskkill).
- Addon de test cree : `client_test\Interface\AddOns\WowlheimTest\` (.toc 11200 + .lua affichant `WowlheimPing("x")` a PLAYER_ENTERING_WORLD) - non teste.

## Constats (preuves : captures)
- Capture : BitBlt et PrintWindow marchent sur le client D3D (`01_launch.png` : cinematique, `05_eula_prompt.png`). Le rendu n'est pas noir.
- Le client tourne en fenetre 1024x768 (le client a reecrit `WTF\Config.wtf`, `gxResolution "1024x768"`, `realmList "127.0.0.1"`). `realmlist.wtf` = 127.0.0.1 verifie.
- WoW.exe refuse l'acces a OpenProcess (erreur 5) depuis nos outils : chemin de l'exe illisible, `Stop-Process` d'apres le chemin ne marche pas ; la recherche de fenetre se rabat sur le nom via Toolhelp, l'arret se fait par `taskkill /PID`. Les entrees SendInput ont atteint la fenetre (Echap a saute la cinematique d'introduction).
- Des fenetres `WowError` restees ouvertes des essais DLL precedents (crash #134 historique, voir CLIENT_PATCH.md) ont ete fermees.

## BLOCAGE : contrat de licence (EULA)
Au premier vrai lancement, le client affiche « The End User License Agreement has changed ... Accept / Decline » (`shots/05_eula_prompt.png`). Accepter un contrat est une decision de l'utilisateur ; je ne l'ai PAS accepte (je n'ai pas non plus ecrit `readEULA`/`readTOS` dans Config.wtf). Une fois Robin d'accord, on clique Accept (l'ecran des CGU peut suivre), puis le scenario continue.

## Non fait (donc non verifie)
Connexion WLTEST2, liste des royaumes, creation du personnage, rendu du monde, `.build ...` en jeu et modeles de substitution, `.build remove`, DLL en session jouee, addon WowlheimPing, stabilite plusieurs minutes. Aucun crash nouveau n'est apparu (dossier Errors inchange).

## Prochaines etapes
1. Accord de Robin pour accepter l'EULA/TOS sur la copie de test. 2. Scenario : login (type.py --textfile pour le mot de passe, `C:\Wowlheim\run\test_account2.txt`), royaume, creation humain guerrier, entree dans le monde, `.build list/nocost on/place/remove`. 3. Meme scenario avec `launch_wow.ps1 -Dll`. 4. Apercu fantome / panneau : hooks decrits dans CLIENT_PATCH.md section 2(b).
