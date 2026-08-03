# NexMove — Journal des évolutions

Récapitulatif lisible de tout ce qui a été fait (le détail exact est dans l'historique Git).

## v2.14 — EURAXESS + RSS élargis & correctifs testeurs (rapport Carmelle)
- **Sources élargies** : 4 flux RSS supplémentaires (afterschoolafrica, opportunitiesforyouth, youthop,
  mladiinfo) + **EURAXESS** (recherche/PhD/postdoc EU) via `EURAXESS_RSS`, + `SOURCE_FEEDS_EXTRA` pour
  ajouter des flux sans toucher au code. `/health` : `euraxess_configured`, `rss_feeds`.
- **Correctifs retours testeurs :**
  - *Diplôme principal* : le profil retient désormais le diplôme le **plus élevé/récent** (master avant
    licence) — tri déterministe par niveau + année.
  - *Objectif « travailler »* : nouvelle question **type de poste** (temps plein / partiel / télétravail /
    alternance), injectée dans la recherche d'offres.
  - *Doublons /mobilite* : anti-doublons entre deux `/mobilite` successifs (mémoire des URLs déjà vues).
  - *Mots-clés multiples* : la recherche couvre désormais **tous** les mots-clés (requête OR + consigne de
    diversité) au lieu d'un seul.
  - *Faux assistant de dossier* : le mode conversationnel **ne simule plus** de formulaire multi-étapes ni
    ne prétend créer un dossier — il renvoie vers la commande unique `/dossier <cible>` / `/postuler <cible>`.

## v2.13 — Routing de modèle · sources emploi · rappels programmables · feedback 👍/👎
- **Routing de modèle** : les tâches simples (conversation libre en mode actif) partent sur un **petit
  modèle rapide** (llama-3.1-8b / gemini-flash) ; l'analyse CV, la sélection d'offres et la rédaction de
  documents gardent le **70B**. Moins de latence, quotas mieux préservés. (`call_groq(..., tier="fast")`).
- **Sources d'emploi structurées** : ingestion d'**arbeitnow** (sans clé) et **Adzuna** (clés gratuites
  optionnelles) dans le pool d'offres, en plus des flux RSS bourses. Les offres portent leur vrai **type**
  (emploi/bourse) et passent par le scoring sémantique par profil.
- **Rappels & digest programmables** : `/rappels on|off` et `/digest quotidien | hebdo <jour>`. La veille
  proactive respecte le choix de chaque utilisateur (fréquence, jour). Les rappels de deadline des dossiers
  restent toujours actifs.
- **Feedback 👍/👎 sur les offres** : boutons sous les résultats `/mobilite` et `/veille`. Les votes sont
  **appris par signature d'offre** (type + domaine) et **réinjectés dans le score** (±25) — le bot propose
  moins ce que l'utilisateur rejette, plus ce qu'il valide. `/health` : `adzuna_configured`.

## v2.12 — Export Word & matching sémantique
- **Export Word (.docx)** : `/postuler` et `/dossier` envoient désormais, en plus des PDF, des versions
  **Word modifiables** du CV et de la lettre/projet (demande des testeurs : « pouvoir modifier direct »).
  `python-docx` (pur Python, zéro dépendance système). Le type MIME des envois est déduit de l'extension
  (Telegram/WhatsApp/Messenger).
- **Matching sémantique des offres (embeddings)** : la pertinence ne repose plus seulement sur les mots-clés.
  On calcule la **similarité de sens** entre le profil et chaque offre (embeddings `text-embedding-004`,
  multilingue, via la clé Gemini déjà en place). Utilisé pour (a) re-trier les résultats web avant sélection
  LLM dans `/mobilite`, (b) mélanger score LLM + similarité (60/40), (c) filtrer/scorer les sources RSS de la
  veille (fini le score fixe à 62). Vecteurs mis en cache 7 j (quotas préservés). **Repli gracieux** : sans
  clé Gemini, on garde le classement mots-clés + LLM. `/health` expose `docx_configured` et
  `semantic_matching`.

## v2.11 — Performance & robustesse (passe senior)
- **Client HTTP partagé** : un seul `httpx.AsyncClient` avec pool keep-alive pour *tous* les appels
  sortants (LLM, Tavily, Telegram, WhatsApp, Messenger) au lieu d'un nouveau client (handshake TCP/TLS) à
  chaque requête. Gain de latence et de sockets sous forte charge (100+ testeurs), fermé proprement au
  shutdown.
- **Travail bloquant hors boucle asyncio** : l'OCR (tesseract), l'extraction PDF et la génération des PDF
  (reportlab) passent par `asyncio.to_thread`. Un CV scanné lourd ne gèle plus les autres utilisateurs du
  worker pendant plusieurs secondes.
- **Anti-message perdu (Telegram)** : si un `*`/`_`/`[` déséquilibré (texte LLM ou utilisateur) fait
  échouer l'envoi Markdown (400 « can't parse entities »), on renvoie automatiquement en texte brut — le
  message arrive toujours.

## v2.10.1 — Menu à la demande (moins de bruit)
- Le **menu à boutons ne se ré-affiche plus à chaque réponse** (onboarding comme mode actif). Il apparaît
  seulement quand c'est utile : **une fois** à la validation du profil, et sur demande via **`/menu`**
  (ou `/aide`). Discussions plus courtes et lisibles.

## v2.10 — Corrections retours testeurs
- **Rejet des fichiers non-CV** : à l'analyse, le LLM juge d'abord si le document est bien un CV
  (`est_cv`) ; sinon (facture, article, capture, texte quelconque) il est refusé au lieu de valider un
  profil vide. Double garde-fou heuristique (nom + formation/expérience/compétences présents).
- **Onboarding cohérent** : chaque réponse est validée (`valider_pref`). Les commandes tapées par erreur
  (`/hej`…) et les réponses incohérentes (ex. « Taf » comme certification de langue) sont refusées avec un
  indice, sans avancer — fini les profils validés avec une syntaxe fausse.
- **Documents PDF** : en-tête du CV corrigé (nom + titre plus aérés, interlignage explicite, échappement
  XML) — plus de chevauchement en haut. Génération CV/lettre **ancrée sur les expériences et formations
  réelles** du candidat, avec interdiction explicite des tournures d'IA et clichés (« je suis convaincu
  que », « correspond parfaitement »…).

## v2.9 — OCR des CV scannés
- **OCR automatique** (`tesseract-ocr` + `pytesseract`) : quand un PDF ne contient pas de texte
  sélectionnable (CV scanné / photographié), `extract_text_pdf` bascule sur un rendu image page par page
  (`fitz` pixmap, zoom ≈216 dpi) puis reconnaissance `image_to_string` en **fra+eng**. Garde-fous
  `OCR_MAX_PAGES` / `OCR_ZOOM`. Import **tolérant** : sans le binaire tesseract, l'app démarre quand même
  (OCR désactivé, message d'erreur adapté). `/health` expose `ocr_configured`.
- Ajout de `api/requirements.txt` et `api/Dockerfile` au dépôt (paquets système
  `tesseract-ocr-fra`/`tesseract-ocr-eng` + `pytesseract`/`Pillow`).

## v2.8 — Résilience LLM multi-fournisseurs
- Routeur de repli **Cerebras → Groq → Gemini** (mêmes appels, bascule auto sur quota/erreur) pour tenir
  la charge de 100+ testeurs sur quotas gratuits. `/health` expose `llm_providers`.

## Infrastructure & fiabilité
- **Webhook Telegram stabilisé** : URL publique fixe via **ngrok domaine statique** (fin de la boucle
  `{"message":"Provided secret is not valid"}` causée par le tunnel trycloudflare éphémère). Règle d'or :
  un seul workflow avec Telegram Trigger actif (WF1), et on ne relance jamais `setWebhook` à la main.
- **Déploiement durable** : `forge-nex-api` sous **docker-compose** (image qui embarque `main.py`,
  `.env`, **volume `./data`** pour `sessions.db`). Fin des `docker cp` fragiles.
- **Attribution retirée** : plus de « This message was sent automatically with n8n ».

## Backend FastAPI (`api/main.py`)
- **Bug `Form(...)`** corrigé : `/api/chat-cv` lit enfin `user_id`/`chat_id` du multipart (avant : sauvés
  sous « unknown »).
- **Sessions persistantes** : `SessionManager` → **SQLite** (partagé entre les 2 workers uvicorn, survit
  aux redémarrages). Correctif du bug `/health` (`_cache` supprimé).
- **Onboarding déterministe** : machine à états en code (plus de boucle LLM). 8 critères d'éligibilité
  collectés : objectif, nationalité, pays cibles, financement, certifs de langue, langue, niveau, mots-clés.
- **Token Telegram** : lu depuis l'env (`TELEGRAM_TOKEN`/`TELEGRAM_BOT_TOKEN`), repli fichier.

## Fonctionnalités bot (commandes)
- `/start` (réinitialise + tutoriel), `/tuto` (guide pas à pas), `/aide`.
- `/mobilite <pays/domaine>` — analyse mobilité.
- `/veille` — recherche d'opportunités à la demande (stockées, dédoublonnées).
- `/campusfrance` — procédure « Études en France » (étapes, bourses, documents), **grounded** via Tavily.
- `/postuler <cible>` — génère **CV adapté + lettre de motivation** (ou SOP académique pour une bourse),
  envoyés en PDF dans Telegram.
- `/profil`, `/status`, `/supprimer` (RGPD).
- Menu de commandes Telegram (`setMyCommands`).

## Qualité des résultats
- **Grounding web (Tavily)** : `/mobilite`, `/veille`, `/campusfrance` cherchent de **vraies annonces**
  et Groq ne fait que **sélectionner/scorer** parmi les résultats réels (URL exactes, pas d'invention).
  Repli « pistes IA durcies » si la clé Tavily est absente.
- **Types explicites** dans les résultats : 📚 FORMATION · 💼 EMPLOI · 🎓 BOURSE · 🔬 FELLOWSHIP.
- Niveau de **confiance** (🟢🟡🔴), portail/lien, deadline, bandeau « à vérifier ».

## Veille automatique (WF0 — orchestrateur 24 h)
- `/api/collect` — pour chaque utilisateur actif : recherche + scoring → stocke les **nouvelles** offres
  (table SQLite `offres`, dédup par URL).
- `/api/score` — résumé des offres en attente.
- `/api/notify` — envoie un **digest Telegram proactif** (offres score ≥ 60 non encore notifiées) puis les
  marque `notified` (pas de spam).

## Branding
- **Forge NEX → NexMove** partout dans l'expérience utilisateur (« ton prochain départ » : études, emploi,
  bourses, mobilité).

## v2.3 → v2.5 (efficience & pré-lancement)
- `/health` versionné (VERSION dynamique) — vrai témoin de déploiement.
- **Anti-offres expirées** : date du jour dans les prompts + filtre déterministe des deadlines passées.
- **Sprint efficience** : veille parallélisée (`asyncio.gather`), cache Tavily (TTL 6 h), `search_depth: advanced`.
- **Sources structurées** : ingestion de flux RSS de bourses réels (scholars4dev, OpportunityDesk,
  OpportunitiesForAfricans) → table `sources_offres`, matchées au profil dans la veille.
- **`/formations <domaine>`** : recommandations de formations/certifications (grounded) pour se distinguer.
- **Suivi Campus France par étapes** : `/parcours` (roadmap EEF jusqu'au départ) + `/etape` (valider l'étape courante).

## Reste à faire (optionnel)
- OCR (CV scannés) + export **DOCX** (nouvelles dépendances → `requirements.txt`).
- Sources structurées supplémentaires (RSS bourses, API emploi) en plus de Tavily.
- Tracker de candidatures détaillé + `/status` enrichi.
- Montée en charge : paralléliser `/api/collect` (actuellement séquentiel).
