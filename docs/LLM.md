# LLM local pour le chat des bots (phase 6, optionnelle)

Objectif : permettre aux bots proches d'un joueur de répondre en chat avec une réplique générée par un LLM local.
Jamais dans la boucle de combat, jamais bloquant pour le serveur, tout reste sur la machine (projet privé).

Fichiers : `tools/llm/bot_chat.py` (client), `tools/llm/test_bot_chat.py` (tests).

## État constaté (2026-10-26)

| Élément | État | Source |
|---|---|---|
| LM Studio installé | Oui (`%LOCALAPPDATA%\Programs\LM Studio`, CLI `%USERPROFILE%\.lmstudio\bin\lms.exe`) | constaté |
| Serveur local `127.0.0.1:1234` | Tourne déjà (lancé par l'utilisateur, pas par nous) | constaté |
| Modèle `nvidia-nemotron-3.5-bolt-e4b-4gb` | Listé par `/v1/models` ET chargé (`lms ps` : IDLE, 6,18 Go, contexte 40192, parallel 4) | constaté |
| Latence mesurée | voir ci-dessous | mesuré |

Aucun téléchargement de modèle, aucune installation, aucun démarrage de serveur n'ont été faits.

### Point de sécurité à corriger côté LM Studio

`netstat` montre le port 1234 en écoute sur `0.0.0.0` : le serveur LM Studio est **joignable depuis le réseau local**, pas seulement depuis la boucle locale.
Le client refuse de parler à autre chose que 127.0.0.1/localhost, mais le serveur reste exposé. Dans LM Studio (onglet Developer / Server Settings), désactiver « Serve on Local Network » pour n'écouter que sur 127.0.0.1. Non modifié par nous (réglage de l'utilisateur).

### Latence mesurée (client réel, 3 scénarios x 3 passages, machine de dev)

- Réplique complète : environ 2,0 à 4,0 s dans la grande majorité des cas (médiane ~2,4 s) ; quelques passages à 0,2 à 0,5 s quand le modèle pense très peu.
- Le modèle est un modèle à raisonnement : il produit ~250 à 350 tokens de `reasoning_content` avant les ~15 tokens de réponse utile. Avec `max_tokens=300`, environ 1 appel sur 3 retournait un contenu vide (raisonnement tronqué) ; le client utilise donc `max_tokens=600`.
- Essayés sans effet : `reasoning_effort: low`, `chat_template_kwargs.enable_thinking=false`, préfixe `/no_think`. Le raisonnement ne se désactive pas via l'API ici.
- Mesures indicatives (n petit, une seule machine, GPU/charge non contrôlés), pas un benchmark.

## Lancer

Prérequis : LM Studio avec le serveur local démarré et le modèle chargé. Python 3, stdlib seulement.

```
python -I tools/llm/bot_chat.py --demo
python -I tools/llm/bot_chat.py --persona perso.json --zone "Elwynn" --place "Auberge" --player "Salut !"
python -I tools/llm/test_bot_chat.py        # tests unitaires, faux serveur sur 127.0.0.1
```

Personnalité (JSON, clés françaises) : `{"nom": "...", "archetype": "...", "objectifs": ["..."], "zones_preferees": ["..."], "ton": "..."}`.

API Python : `generate_reply(persona, context, model=..., base_url=..., timeout=8.0)` renvoie une `str` (une ligne, <= 200 caractères) ou `None`.
Contexte : `{"zone": ..., "lieu": ..., "joueur": "ce que dit le joueur"}`.

Comportement :
- URL : seuls `http://127.0.0.1` et `http://localhost` sont acceptés (sinon `ValueError`, erreur de configuration volontairement bruyante). Pas de proxy système, pas d'identifiants dans l'URL.
- Serveur absent, timeout, HTTP 5xx, JSON invalide, réponse vide : `None`, aucune exception.
- Filtre de sortie : retire `<think>...</think>` (y compris balise non fermée ou ouverture perdue), retours à la ligne, caractères non imprimables, markdown (`* _ # > ~`), guillemets (l'apostrophe est conservée : « l'auberge »), coupe à 200 caractères au dernier mot, **refuse** (renvoie `None`) toute réponse contenant un lien ou un code de lien WoW (`|H`).

## Ce qui est testé et ce qui est supposé

Testé (réellement exécuté) :
- 13 tests unitaires avec faux serveur HTTP local : filtre, validation d'URL (hôtes distants, `0.0.0.0`, `user@host`, `localhost.evil.com`, https refusés), repli sur 500 / JSON invalide / timeout / serveur absent, charge utile envoyée (modèle configurable).
- 3 scénarios réels contre LM Studio avec le modèle chargé : réponses en français, courtes, une ligne, cohérentes avec le personnage (qualité subjective, petit échantillon).

Supposé / non testé :
- Tout le lien avec CMaNGOS / playerbots (section suivante) : rien n'est implémenté ni testé.
- Charge concurrente (plusieurs bots), comportement sur longues sessions, consommation GPU/VRAM pendant que le serveur de jeu et le client WoW tournent.
- Rendu des accents dans le client WoW 1.12 selon la locale (non vérifié ; à tester, sinon translittérer en ASCII).
- Tenue du personnage et absence de dérives sur de nombreux échanges ; pas d'historique de conversation dans le client actuel (un tour = un appel).
- Sécurité contre le prompt injection : le texte du joueur est mis dans le message utilisateur, le filtre limite les dégâts (pas de lien, longueur bornée), mais aucune garantie de contenu.

## Limites

- Latence de 2 à 4 s : acceptable pour du chat, inutilisable pour le gameplay.
- Modèle à raisonnement : coût en tokens élevé pour une réplique de ~15 tokens ; un modèle sans raisonnement serait plus rapide (autre modèle déjà listé dans LM Studio possible, à comparer, non fait).
- Le serveur LM Studio doit être lancé à la main ; sans lui, les bots se taisent (repli `None`), ce qui est le comportement voulu.
- `parallel 4` côté LM Studio, mais nous recommandons un seul appel à la fois (voir ci-dessous).

## Proposition d'architecture (non implémentée)

Principe : le serveur de jeu ne doit jamais attendre le LLM.

```
CMaNGOS (module playerbots)            Pont LLM (processus Python séparé, local)
  |  joueur parle près d'un bot   --->   file d'entrée (bornée, ex. 8)
  |  (événement chat + contexte)         |  1 worker, 1 appel LLM à la fois
  |                                      |  bot_chat.generate_reply(...)
  |  <--- réplique prête (ou rien) ---   file de sortie
  v  le bot dit la ligne au prochain tick
```

Règles :
1. **Asynchrone** : le module C++ pousse une requête (bot, contexte) et continue. Il lit les réponses au tick suivant, sans attente. Transport simple : fichier/dossier de spool, socket Unix/TCP en boucle locale, ou table SQL locale ; au choix, tout en 127.0.0.1.
2. **Un seul appel à la fois** (un worker) : évite d'écraser GPU/CPU pendant que le serveur tourne. File bornée : si pleine, on jette la plus ancienne ou la nouvelle ; le bot ne répond pas, ou utilise une réplique prédéfinie.
3. **Plafond de fréquence par bot** (ex. 1 réponse / 20 s par bot, 1 réponse globale / 3 s) et ne répondre qu'aux bots à portée de chat (/dire, ~25 m) ou en groupe avec le joueur ; tirer au sort quel bot répond pour éviter que tous parlent.
4. **Jamais en combat** : refuser la requête côté serveur de jeu si le bot ou le joueur est en combat, mort, en vol ou en cinématique ; jeter aussi la réponse si l'état a changé pendant les 2 à 4 s de génération (réponse périmée, TTL ~10 s).
5. **Repli propre** : réponse `None`, timeout ou serveur LLM absent donnent le silence ou une réplique prédéfinie ; aucun effet sur le gameplay. Interrupteur global (config) pour tout désactiver.
6. **Aucune action de jeu pilotée par le LLM** : il ne produit que du texte de chat, filtré (une ligne, <= 200 caractères, sans lien).
7. **Local uniquement** : bind sur 127.0.0.1, client limité à 127.0.0.1/localhost, pas d'appel sortant sur Internet.
8. Étapes suggérées : (a) pont Python seul avec un faux joueur en ligne de commande ; (b) intégration lecture seule (journaliser les requêtes sans répondre) ; (c) réponse réelle limitée à un bot de test ; (d) mesurer l'impact sur la latence du serveur de jeu avant d'élargir.
