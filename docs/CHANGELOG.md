# NexMove — Journal des évolutions

Récapitulatif lisible de tout ce qui a été fait (le détail exact est dans l'historique Git).

## v2.31 — Profils persistés par identifiant (code de récupération) (PR-D3)
- **`ProfileStore`** (`db.py`) : chaque profil validé reçoit un **code de récupération stable** `NEX-XXXXX`.
  Le profil est archivé en **versions** ; on ne restaure QUE la **plus complète** (`profile_quality`) — donc
  « on garde les meilleures données » même si l'utilisateur change d'appareil ou de canal.
- **`/moncode`** : affiche (et crée au besoin) le code de récupération.
- **`/moi <code>`** : restaure le meilleur profil sur le compte courant → **portage Telegram ↔ WhatsApp**
  et récupération après changement d'appareil. Le code est aussi affiché à la fin de l'onboarding.
- **+8 tests** (code stable, restauration inter-utilisateurs, conservation de la meilleure version,
  `profile_quality`, code inconnu, commandes `/moi`/`/moncode`). **85/85 verts**.

## v2.30 — Onboarding ADAPTATIF + nom de secours + intention mémorisée (PR-D1)
- **Onboarding adaptatif** : les questions s'adaptent aux réponses. Un **stage/job LOCAL** (objectif
  « travailler » + son propre pays) ne demande plus la **nationalité/passeport**, ni le **financement
  d'études**, ni les **certifs de langue** — ces questions restent réservées à la mobilité internationale
  et aux parcours d'études/bourses. Plan de questions recalculé à chaque étape (`_build_pref_plan`).
  → Corrige le retour testeur : « demander la nationalité pour un stage local, ce n'est pas logique ».
- **Nom de secours depuis le fichier** : quand l'OCR/LLM ne détecte pas le nom sur le CV, on le devine
  depuis le **nom du fichier** (`CV_Judicael.pdf` → « Judicael », `cv-jean-dupont.pdf` → « Jean Dupont »)
  au lieu d'afficher « N/A ». Le nom deviné est persisté (utile pour lettres/dossiers).
- **Intention mémorisée** : une demande forte tapée **avant la fin de l'onboarding** (ex. « je cherche une
  bourse de master au Canada ») n'est plus perdue — elle est mémorisée puis **relancée** à la fin du profil
  (message + bouton « ▶️ … »).
- **+11 tests** (`_build_pref_plan`, `_vise_international`, `_name_from_filename`, flux d'onboarding local
  bout en bout, capture d'intention). **77/77 verts**.

## v2.29 — WhatsApp : photos directes + rejet poli audio/vidéo + guide de mise en service
- **Photos WhatsApp directement** : le parseur gère maintenant `type: "image"` (JPG/PNG) — l'image part
  vers **vision Gemini** comme pour Telegram. Fini l'obligation d'envoyer en « Document ».
- **Rejet poli** des audios, vocaux, vidéos, stickers : « Écris-moi en texte ou envoie ton CV en
  PDF/Word/image » au lieu du silence.
- **`docs/GUIDE-WHATSAPP.md`** (nouveau) : procédure complète (Meta Business, App WhatsApp, tokens, webhook
  ngrok, whitelist testeurs, coûts, dépannage). ~30 min de config côté Meta, le code est déjà prêt.
- **`tests/test_whatsapp_incoming.py`** (+10 tests) : texte, document PDF, image JPG/PNG, boutons
  interactive (button_reply / list_reply / template button), rejets audio/vidéo/sticker. **66/66 verts**.

## v2.28 — Refactor PR-C : `channels.py` extrait + smoke test Docker en CI
- **`api/channels.py`** (nouveau, ~200 lignes) : Telegram (`send_message`, `edit_message`, `answer_callback`,
  `_send_telegram_document`, `_tg_keyboard`), WhatsApp Cloud API (`wa_text/menu/document/get_media`),
  Messenger (`fb_text/menu/document`), + helper `_mime_for`. Comportement identique.
- **~180 lignes retirées** de `main.py` (3 064 → 2 891).
- **`tests/test_channels.py`** (+10 tests) : MIME, clavier inline, garde-fous sans token. **56/56 verts**.
- **🛡️ Smoke test Docker en CI** : nouveau job `docker-smoke` qui build l'image, lance le container, et
  vérifie que `/health` répond. **Aurait attrapé le bug v2.27.1** (`ModuleNotFoundError: http_client`)
  avant qu'il n'arrive en prod.
- Étape suivante prévue (PR-D) : extraire `tools.py` (PDF ops, compression, DOCX, vision).

## v2.27.2 — Fix Dockerfile : les nouveaux modules manquaient dans l'image
- `COPY main.py .` → `COPY main.py db.py llm.py http_client.py .` — sans ça, `ModuleNotFoundError` au
  démarrage du container (PR-A/B cassées en prod). Le smoke test Docker (v2.28) verrouille cette classe de bugs.

## v2.27.1 — Fix test CI trop strict
- `test_compress_pdf_valid_output` : `kb == 0` est légitime pour un mini-PDF. On vérifie signature `%PDF-`
  + taille en octets > 200. CI durcie : ruff/compile couvrent tout `api/` (pas juste `main.py`).

## v2.27 — Refactor PR-B : `llm.py` + `http_client.py` extraits (IA isolée)
- **`api/http_client.py`** (nouveau) : le pool `httpx.AsyncClient` partagé sort du monolithe. Utilisable
  par tout module (`from http_client import http`).
- **`api/llm.py`** (nouveau, ~230 lignes) : routeur multi-fournisseurs (Cerebras→Groq→Gemini), embeddings
  (multi-modèles, cache 7 j via `db.cache`), vision Gemini pour l'analyse d'un CV image. Comportement
  identique — mêmes défauts de modèles, même bascule, même parseur JSON tolérant.
- **~210 lignes retirées** de `main.py` (3 260 → 3 064).
- **`tests/test_llm.py`** (+10 tests) : parseur JSON (fences ```/```json), cosine, structure des providers,
  garde-fous sans clé. **46/46 verts** (36 + 10). Zéro régression.
- Étape suivante prévue (PR-C) : extraire `channels/` (Telegram/WhatsApp/Messenger).

## v2.26 — Refactor PR-A : `db.py` extrait (persistance isolée)
- **`api/db.py`** (nouveau) : les 3 stores SQLite (`SessionManager`, `OppStore`, `Cache`) sortis du monolithe,
  comportement identique (méthodes, signatures, DDL, chemins). Chemin de base configurable via
  `NEXMOVE_DB_PATH`. `main.py` ne fait plus qu'un `from db import …`.
- **~230 lignes retirées** de `main.py` (fichier passe de ~3 490 à ~3 260 lignes).
- **`tests/test_db.py`** (8 tests) : session roundtrip, dédup offres, user_stats, candidatures + rappels,
  feedback borné à ±25, journal /contact, cache TTL. **36/36 verts en local et en CI.**
- Étape suivante prévue (PR-B) : extraire `llm.py` (routeur multi-fournisseurs + embeddings).

## v2.25 — Photos Telegram, journal /contact, tests + CI
- **Photos Telegram directes** : WF1 parse désormais `message.photo` (prend la plus grande taille) et route
  vers `/api/chat-cv` ; `process_cv` détecte l'image (`.jpg`) et l'analyse par **vision Gemini** (repli OCR).
  Fini l'obligation d'envoyer en « Fichier ».
- **Journal `/contact` en base** : chaque message est logué (table `contacts`), même si le forward Telegram
  échoue. Nouvelle commande **`/contacts_log`** (réservée à `ADMIN_CHAT_ID`) : les 20 derniers messages.
- **Filet de sécurité (risque n°1 de l'audit)** : ajout de `tests/test_units.py` (**28 tests unitaires**,
  fonctions pures : validation onboarding, tri diplômes, routeur d'intention, nationalité→pays, feedback,
  pages PDF, RSS tolérant, PDF ops, extraction DOCX, MIME…) + workflow **GitHub Actions** `ci.yml` (ruff
  errors-only + compile + pytest à chaque push/PR). Régression = build rouge, plus jamais en prod.

## v2.24 — Contact & version
- **`/version`** (alias `/about`) — affiche la version du bot, les IA actives, les modules (OCR, Word, Vision,
  Sémantique, Adzuna) et le nombre de sources. Utile pour le support et pour que tu voies l'état en un coup d'œil.
- **`/contact <message>`** (alias `/support`, `/rencontrer`, `/rdv`) — transmet directement le message au chat
  admin (Telegram) si `ADMIN_CHAT_ID` est configuré ; sinon affiche les canaux (WhatsApp, email, calendrier).
  Route aussi les intentions en langage naturel (« parler à quelqu'un », « prendre rdv », « contacter »…).
- Boutons `💬 Nous contacter` et `ℹ️ Version` dans le menu « Mon espace ». Env vars : `ADMIN_CHAT_ID`,
  `CONTACT_EMAIL`, `CONTACT_WHATSAPP`, `CONTACT_CALENDAR`.

## v2.23 — CV multi-formats & procédures françaises parallèles
- **CV en tous formats** : PDF texte + PDF scanné (OCR) ✅ déjà, **+ DOCX** (python-docx) **+ image** (JPG/PNG/WEBP/HEIC).
  Images analysées d'abord par **vision Gemini** (robuste sur photos), repli **OCR tesseract**. Endpoint et
  process_cv routent par extension/MIME. Messages d'erreur adaptés au format.
- **Procédures françaises parallèles à Campus France** (le gros gap face aux prestataires payants) :
  `/parcoursup`, `/monmaster`, `/ecandidat`, `/dap` (L1 hors UE), `/visa` (phase consulaire Capago/VFS),
  `/recours` (refus CF ou refus de visa). Grounded, adaptés au profil.
- Menu **Procédures & accompagnement** enrichi. Routeur d'intention en langage naturel étendu (« parcoursup »,
  « monmaster », « visa », « capago », « recours », « refus »…).

## v2.22.1 — 🔴 Correctif critique : modèles LLM dépréciés (bot bloqué)
- **Bug bloquant en prod** : les 3 modèles LLM renvoyaient 404 (Gemini `gemini-2.0-flash` **déprécié**,
  Groq/Cerebras 70B « no access ») → `call_groq` échouait → **les CV n'étaient plus analysés** (`/api/chat-cv`
  503), personne ne pouvait s'onboarder.
- **Fix** : modèles **configurables par env** (`GROQ_MODEL`, `GROQ_MODEL_FAST`, `CEREBRAS_MODEL`,
  `CEREBRAS_MODEL_FAST`, `GEMINI_MODEL`, `GEMINI_MODEL_FAST`) → on corrige un modèle déprécié sans toucher au
  code. Défaut Gemini passé à **`gemini-2.5-flash`**. URL Gemini construite depuis `GEMINI_MODEL`.
- **Robustesse** : `process_cv` n'échoue plus **en silence** — si le service IA est indisponible, l'utilisateur
  reçoit un message clair (« renvoie ton CV dans une minute »).

## v2.22 — Langage 100 % naturel & offres locales
- **Parler normalement suffit** : n'importe quelle phrase est comprise. Mots-clés en priorité (instantané),
  sinon le LLM décide en **un seul appel** s'il faut lancer une **action** (n'importe quelle commande, avec
  son argument) ou **répondre en conversation**. Les commandes restent utilisables. Repli mots-clés si le
  LLM est indisponible (pas de régression).
- **Champ élargi au LOCAL** : le système ne cherche plus seulement à l'étranger. Si les pays visés sont
  vides / « tous » / le propre pays de l'utilisateur, la veille inclut les opportunités **locales** (emplois,
  formations comme l'ASIN, bourses nationales). Détection nationalité→pays, prompts et requêtes adaptés.
  Question d'onboarding « pays visés » mentionne désormais le local.

## v2.21 — Boutons de confirmation & choix cliquables (rapport testeur, point 3)
- **Validation du CV** avec boutons : `✅ C'est correct` / `🔄 Recommencer` (au lieu de taper « Oui »).
- **Questions d'onboarding fermées** en boutons cliquables : objectif, financement, langue, niveau, type de
  poste — plus besoin de taper, et fini les réponses incohérentes sur ces champs.
- **Récapitulatif** validé par boutons : `✅ Oui, c'est bon` / `🔄 Recommencer`.
- Mécanique : clavier par tour (`_kb_options`) attaché au message, callbacks `onb:`/`pref:` rejoués comme une
  réponse tapée (la saisie texte reste possible). `deliver_text(..., options=…)` sur les 3 canaux.

## v2.20.2 — Affichage des formations (rapport testeur)
- Le message d'analyse du CV affiche désormais **toutes les formations** (jusqu'à 3, diplôme le plus élevé
  en tête, + « +N autres ») au lieu d'une seule — les données étaient déjà complètes, seul l'affichage
  induisait en erreur.
- **CV sans section Formation** : message explicite « Aucune formation détectée » (l'analyse continue, pas
  de blocage).

## v2.20.1 — Conversation libre corrigée (retour prod)
- **Avant onboarding** : un message libre reçoit une réponse *déterministe* (« envoie ton CV ») au lieu d'un
  LLM bavard qui disait « Bonjour », vouvoyait et redemandait le CV.
- **Utilisateur actif** : les messages libres sont *routés vers la vraie commande* selon l'intention
  (formations, école, logement, budget, Campus France, Canada, opportunités) — ex. « formations proposées
  par l'ASIN » lance une vraie recherche au lieu d'une réponse approximative.
- **Conversation** repassée sur le modèle 70B (le 8B ignorait le tutoiement / ne-pas-resaluer), consignes
  durcies (jamais « Bonjour »/« vous », ne jamais redemander le CV).

## v2.20 — Boîte à outils & procédures multi-pays
- **Outils PDF** : `/fusionner` (assembler des PDF), `/enpdf` (images→PDF, images envoyées en fichier),
  `/decouper <pages>` (extraire des pages), en plus de `/compresser`. Tampon de fichiers sur disque
  (volume persistant), `/terminer` / `/annuler`. Le endpoint accepte les images en mode img2pdf.
- **Outils conseil** : `/budget <ville>` (coût de la vie + preuve de ressources), `/eligibilite <cible>`
  (compare honnêtement le profil aux exigences), `/traduire <texte>` (traduction informative + rappel :
  dossier officiel = traducteur assermenté).
- **Procédures multi-pays** : `/procedure <pays>` générique (Belgique, Allemagne, Suisse, Luxembourg,
  Pays-Bas… routé par profil), en plus de `/campusfrance` (France) et `/canada`. Menu enrichi.
- **Fix** : f-string sans placeholder.

## v2.19 — Motivation & outils
- **Première veille automatique** dès le profil validé : 3 pistes tout de suite (valeur immédiate) + promesse
  d'un digest quotidien lié au profil.
- **Gamification** : `/status` affiche la progression (opportunités trouvées, +N cette semaine, dossiers,
  barre Campus France ▓▓▓░░). Digest quotidien enrichi (preuve sociale : « N nouvelles cette semaine »).
- **Outil compression PDF** : `/compresser [Ko]` puis envoi d'un PDF → version allégée pour les soumissions
  en ligne (Campus France, visa…). Reconstruction lossless puis, si besoin, ré-encodage image à DPI
  décroissant (testé : 20 Mo → <200 Ko). Bouton « 🗜️ Compresser un PDF » dans *Mon espace*.
- **Fix** : Pillow importé indépendamment de tesseract (l'OCR manquant ne désactive plus la compression).

## v2.18 — Mode « conseiller d'orientation senior » & accompagnement des procédures
- **Bilan d'orientation au CV** : à l'analyse, le bot rend un mini-bilan personnalisé (atouts, axes à
  renforcer, 2-3 pistes réalistes de destinations/programmes) — l'onboarding devient un vrai conseil, pas
  une simple extraction. Persona `CONSEILLER_PERSONA` partagée (aussi appliquée à la conversation libre).
- **Campus France vraiment accompagné** : `/campusfrance` présente la procédure + oriente vers l'aide ;
  `/parcours` affiche, pour l'étape en cours, l'action concrète + la commande qui aide.
- **Nouvelles commandes d'accompagnement** (ancrées web, adaptées au profil) :
  `/ecoles <domaine>` (trouver les bonnes écoles), `/logement <ville>` (se loger sans arnaque : CROUS,
  Visale…), `/entretien [type]` (prépa entretien Campus France / Institut Français / visa Capago-VFS avec
  questions types + pistes de réponse), `/canada` (voies d'immigration routées par profil : permis d'études,
  PGWP, Entrée express, PEQ/Arrima Québec).
- Menu **Procédures & accompagnement** enrichi (Campus France · Parcours · École · Logement · Entretien ·
  Canada). Helper réutilisable `conseil_grounded`.

## v2.17.2 — RSS tolérant (feeds mal formés)
- `fetch_rss` : si le XML strict échoue (afterschoolafrica, youthop… : `&` nus, CDATA), repli sur une
  extraction **régex tolérante** (gère CDATA + entités) ; page HTML → `[]` en silence. Log en warning au
  lieu d'error.

## v2.17.1 — EURAXESS opérationnel + RSS anti-bot
- **User-Agent navigateur** pour EURAXESS, les flux RSS et arbeitnow : certains sites (EURAXESS,
  afterschoolafrica, youthop) renvoyaient une page de blocage aux bots → plus d'offres/flux récupérés.
- **Extraction EURAXESS fiabilisée** : offres = liens `/jobs/<id>` ; comme une carte lie l'offre deux fois
  (image + titre), on garde l'intitulé le plus long (le vrai titre) au lieu de rater l'offre.

## v2.17 — Correctifs quotas & embeddings (logs de prod)
- **Embeddings réparés** : `text-embedding-004` était refusé (404) par la clé → le matching sémantique
  était KO. On essaie maintenant plusieurs modèles (`gemini-embedding-001`, `text-embedding-004`,
  `embedding-001`) et on retient le premier disponible ; si aucun, repli lexical **sans spam de logs**.
- **Fin des 429 en cascade sur la veille** : la collecte ne lance plus un appel LLM (osint Tavily) **par
  utilisateur** (16 users = 16 appels simultanés → quotas explosés). Le digest s'appuie sur le **pool de
  sources** (RSS + Adzuna + EURAXESS + arbeitnow) matché par profil ; l'osint complet reste à la demande via
  `/mobilite`. Réactivable avec `COLLECT_OSINT_PER_USER=1`. Concurrence collecte réduite (5→3).

## v2.16 — Fetcher EURAXESS (API adaptative)
- **EURAXESS par API** au lieu du RSS : `fetch_euraxess(query)` interroge EURAXESS avec les **mots-clés
  réels des utilisateurs** (comme Adzuna). Endpoint **auto-sondé** parmi des candidats, ou fixé via
  `EURAXESS_API` (`{q}` = requête). Parseur **générique** (JSON de formes variées : results/hits/_embedded…,
  ou XML/RSS) → titre/url/description quels que soient les noms de champs. Découverte à la 1ʳᵉ requête puis
  arrêt si l'endpoint ne répond pas (pas de requêtes inutiles). Échec **silencieux et sûr** (n'ajoute rien,
  ne casse pas la veille). Offres taguées `fellowship`. Le flux `EURAXESS_RSS` reste possible en complément.

## v2.15 — Adzuna adaptatif & multi-pays
- **Requêtes Adzuna adaptatives** : au lieu d'une liste figée, les requêtes sont construites à partir des
  **mots-clés réels des utilisateurs actifs** (les plus fréquents d'abord) + compétences ; repli sur
  `ADZUNA_QUERIES` si aucun. Les offres collectées collent donc à ce que les testeurs recherchent vraiment.
- **Multi-pays** : `ADZUNA_COUNTRY` accepte plusieurs pays (ex. `fr,ca,be`). `/health` : `adzuna_countries`.

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
