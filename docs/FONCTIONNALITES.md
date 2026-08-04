# NexMove — Fonctionnalités & avancées (v2.20)

**NexMove** est un agent IA de **mobilité internationale** (études, emploi, bourses, fellowships) sur
messageries, qui se comporte comme un **conseiller d'orientation senior** : il lit le CV, dresse un bilan,
trouve de **vraies** opportunités, accompagne les procédures pas à pas et prépare les documents.

Cible : francophones d'Afrique de l'Ouest (ex. Bénin). Canal en production : **Telegram**
(`@nex_move_bot`). WhatsApp & Messenger : code prêt, config Meta à faire.

---

## 1. Principe d'architecture

```
Utilisateur ─(Telegram / WhatsApp / Messenger)─▶ FastAPI (100 % de la logique)
                                                   ├─ SQLite (sessions, offres, candidatures, feedback, cache)
                                                   ├─ Tavily (recherche web réelle = grounding)
                                                   ├─ LLM multi-fournisseurs (Cerebras → Groq → Gemini)
                                                   ├─ Embeddings Gemini (matching sémantique)
                                                   └─ Envoi direct au canal (texte, menus, PDF/DOCX)
n8n : WF1 (transport Telegram) · WF0 (veille 24 h : collect → score → notify)
```

- **n8n = transport uniquement.** Toute la logique et **l'envoi des messages** vivent dans `api/main.py`.
- **Couche canal** : `deliver_text / deliver_menu / deliver_file` routent vers Telegram / WhatsApp /
  Messenger. Menus définis une fois (`get_menu`), rendus par canal.
- **URL publique fixe** : ngrok domaine statique (indispensable pour les webhooks).

---

## 2. Commandes (toutes)

### Démarrage & aide
| Commande | Rôle |
|---|---|
| `/start` | (Re)démarrer, envoyer le CV en PDF |
| `/tuto` | Guide pas à pas |
| `/aide`, `/menu` | Ouvre le menu à boutons (à la demande) |

### 🔎 Trouver des opportunités
| Commande | Rôle |
|---|---|
| `/veille` | Chercher des opportunités maintenant (stockées, dédupliquées) |
| `/mobilite <pays/domaine>` | Recherche ciblée (grounded + matching sémantique) |
| `/formations <domaine>` | Formations/certifs pour se distinguer (gratuites d'abord) |

### 🇫🇷 Études en France (accompagnement pas à pas)
| Commande | Rôle |
|---|---|
| `/campusfrance` | Procédure « Études en France » (étapes, bourses, documents, calendrier) |
| `/parcours` | Suivi en 8 étapes jusqu'au départ, avec l'action concrète de l'étape en cours |
| `/etape` | Valider l'étape en cours |
| `/ecoles <domaine>` | Trouver des écoles/programmes adaptés au profil |
| `/logement <ville>` | Se loger sans arnaque (CROUS, résidences, garant Visale, budget) |
| `/entretien [type]` | Préparer l'entretien Campus France / Institut Français / visa (Capago-VFS) |

### 🌍 Autres destinations
| Commande | Rôle |
|---|---|
| `/canada` | Voies d'immigration Canada routées par profil (permis d'études, PGWP, Entrée express, PEQ/Arrima Québec) |
| `/procedure <pays>` | Procédure officielle générique (Belgique, Allemagne, Suisse, Luxembourg, Pays-Bas…) routée par profil |
| `/budget <ville>` | Coût de la vie + montant de ressources à justifier (visa) |
| `/eligibilite <cible>` | Compare **honnêtement** le profil aux exigences (éligible / limite / non + ce qui manque) |

### 📄 Candidater
| Commande | Rôle |
|---|---|
| `/dossier <cible>` | Documents requis + CV + projet d'études (PDF **et** Word) + suivi |
| `/postuler <cible>` | CV adapté + lettre de motivation (PDF **et** Word) |

### 🛠️ Outils PDF & documents
| Commande | Rôle |
|---|---|
| `/compresser [Ko]` | Alléger un PDF sous une taille cible (pour les soumissions en ligne) |
| `/fusionner` | Assembler plusieurs PDF en un seul (→ envoyer les PDF puis `/terminer`) |
| `/enpdf` | Transformer des images en PDF (images **en Fichier**, puis `/terminer`) |
| `/decouper <pages>` | Extraire certaines pages (ex. `1-3,5`) |
| `/terminer`, `/annuler` | Finaliser / annuler une opération outil |
| `/traduire <texte>` | Traduction **informative** (+ rappel : dossier officiel = traducteur assermenté) |

### 📊 Mon espace
| Commande | Rôle |
|---|---|
| `/profil` | Voir le profil extrait |
| `/status` | Suivi gamifié : opportunités trouvées, +N cette semaine, dossiers, barre Campus France |
| `/rappels on\|off` | Activer/couper les notifications proactives |
| `/digest quotidien\|hebdo <jour>` | Fréquence des notifications |
| `/supprimer` | Effacement RGPD |

---

## 3. Parcours d'onboarding (déterministe)

Machine à états (pas de boucle LLM) :
`WELCOME → ATTENTE_CV → CV_RECU → PREFERENCES → [PREF_TYPE_EMPLOI] → CONFIRMATION → ACTIF`.

- **Analyse du CV** → extraction + **bilan d'orientation** (atouts, axes à renforcer, 2-3 pistes réalistes).
- **Rejet des non-CV** (facture, capture, texte quelconque) au lieu de valider un profil vide.
- **Diplôme principal** = le plus élevé/récent (master avant licence).
- **8 critères** collectés un par un, avec **validation de cohérence** (refuse « Taf » comme certif, `/hej`…).
- Si objectif = **travailler** → question conditionnelle **type de poste** (temps plein / partiel / télétravail).
- **Profil validé → première veille automatique** (3 pistes immédiates) : valeur dès la fin de l'onboarding.

---

## 4. Qualité des recommandations

- **Grounding Tavily** (`search_depth: advanced`, cache 6 h) : le LLM **sélectionne/score** parmi de vrais
  résultats web (jamais d'URL inventée — sélection **par index** de résultat).
- **Matching sémantique (embeddings)** : similarité de sens profil ↔ offre (`gemini-embedding-001`, repli
  `text-embedding-004`/`embedding-001`, puis repli lexical). Utilisé dans `/mobilite` (re-tri + blend
  score LLM/sim 60/40) et la veille RSS. Vecteurs en cache 7 j.
- **Feedback 👍/👎** : boutons sous les offres, votes appris par signature (type + domaine) et réinjectés
  dans le score (±25) — le bot propose moins ce qui est rejeté, plus ce qui est validé.
- **Anti-offres expirées** : date du jour injectée + filtre déterministe des deadlines passées.
- **Anti-doublons** : mémoire des URLs déjà vues entre deux `/mobilite`.
- **Profil complet** : pertinence basée sur résumé + formations + **expériences** (respecte les reconversions).
- **Types explicites** : 📚 FORMATION · 💼 EMPLOI · 🎓 BOURSE · 🔬 FELLOWSHIP + confiance 🟢🟡🔴.

---

## 5. Sources d'opportunités (veille 24 h)

`/api/collect` → `/api/score` → `/api/notify` (WF0, quotidien) :

- **Flux RSS bourses/mobilité** (7) : scholars4dev, OpportunityDesk, OpportunitiesForAfricans,
  afterschoolafrica, opportunitiesforyouth, youthop, mladiinfo (+ `SOURCE_FEEDS_EXTRA`). Parseur **tolérant**
  (CDATA, `&` nus), User-Agent navigateur.
- **arbeitnow** : emplois EU/tech, sans clé.
- **Adzuna** : emplois multi-pays (`fr,ca,be…`), **requêtes adaptées aux mots-clés réels des utilisateurs**.
- **EURAXESS** : recherche/PhD/postdoc, scraping HTML de la recherche par mot-clé (requêtes adaptées).
- **Matching par profil** (sémantique ou lexical) sur tout le pool, digest des offres score ≥ 60.
- **Digest programmable** (`/rappels`, `/digest`) + **rappels de deadline** J-14/7/3/1 sur les dossiers.
- **Anti-quotas** : la collecte n'appelle pas le LLM par utilisateur par défaut (`COLLECT_OSINT_PER_USER=0`)
  — l'analyse LLM complète reste à la demande (`/mobilite`).

---

## 6. Génération de documents

- **CV adapté** + **lettre de motivation / projet d'études**, en **PDF** (reportlab) **et Word .docx**
  (python-docx, modifiable).
- Rédaction **ancrée sur les expériences et formations réelles**, avec **interdiction des clichés d'IA**
  (« je suis convaincu que », « correspond parfaitement »…).
- En-tête CV aéré (plus de superposition nom/titre).
- Suivi : chaque dossier est ajouté au `/status` + rappels de deadline.

---

## 7. Robustesse & performance (ingénierie)

- **Client HTTP partagé** (pool keep-alive) pour tous les appels sortants.
- **Travail CPU bloquant hors boucle asyncio** (OCR, génération/compression PDF via `asyncio.to_thread`).
- **Anti-message perdu Telegram** : repli automatique en texte brut si le Markdown échoue (400).
- **Routeur LLM multi-fournisseurs** : Cerebras → Groq → Gemini (bascule auto sur quota/erreur).
- **Routing de modèle** : petit modèle rapide pour la conversation (`tier="fast"`), 70B pour l'analyse.
- **OCR** des CV scannés (tesseract, fra+eng).
- **Sessions persistantes** SQLite (partagées entre workers), rate-limit par utilisateur.

---

## 8. Multi-canal

| Canal | État | Menus | CV entrant | Docs sortants | Notifs |
|---|---|---|---|---|---|
| **Telegram** | ✅ production | boutons inline | ✅ (+ OCR) | PDF + DOCX | ✅ illimité |
| **WhatsApp Cloud API** | 🟡 code prêt | buttons/list | ✅ | ✅ | ⚠️ templates hors 24 h |
| **Messenger** | 🟡 code prêt | quick replies | ✅ | ✅ | ⚠️ fenêtre 24 h |

Webhooks : `GET/POST /webhook/whatsapp`, `GET/POST /webhook/messenger` (verify token `nexmove_verify`).

---

## 9. Modèle de données (SQLite `data/sessions.db`)

- **sessions** (user_id PK, data JSON) — état complet (channel, étape, profil, historique, cf_stage,
  notif, seen_urls, tool_mode…).
- **offres** (id, user_id, titre, url, type, score, deadline, statut, notified…).
- **candidatures** (id, user_id, cible, deadline, deadline_iso, reminders_sent, statut).
- **sources_offres** (id, titre, url, resume, type, date) — pool global.
- **feedback** (user_id, signal, score) — préférences apprises 👍/👎.
- **cache** (k, v, expires) — Tavily 6 h, embeddings 7 j.

---

## 10. Endpoints API (`X-Forge-Nex-Key` requis sauf webhooks/health)

`POST /api/chat` · `POST /api/chat-cv` · `POST /api/parse-cv` · `POST /api/generate-documents` ·
`POST /api/osint` · `POST /api/collect` · `POST /api/score` · `POST /api/notify` ·
`GET /api/session/{user_id}` · `GET /health` · `GET /` ·
`GET|POST /webhook/whatsapp` · `GET|POST /webhook/messenger`.

`/health` renvoie : `version`, `llm_providers`, `tavily/telegram/whatsapp/messenger_configured`,
`ocr_configured`, `docx_configured`, `semantic_matching`, `adzuna_configured`, `adzuna_countries`,
`euraxess_configured`, `rss_feeds`, `sessions_stored`.

---

## 11. Variables d'environnement

| Variable | Rôle |
|---|---|
| `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `GEMINI_API_KEY` | LLM (fallback) + embeddings (Gemini) |
| `FORGE_NEX_API_KEY` | Auth API (header `X-Forge-Nex-Key`) |
| `TELEGRAM_TOKEN` | Bot Telegram (envoi des messages/documents) |
| `TAVILY_API_KEY` | Grounding web |
| `GOOGLE_SHEET_ID`, `GENERIC_TIMEZONE` | Sheets / fuseau |
| `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_VERIFY_TOKEN` | WhatsApp Cloud API |
| `MESSENGER_TOKEN`, `MESSENGER_VERIFY_TOKEN` | Messenger |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `ADZUNA_COUNTRY` (liste), `ADZUNA_QUERIES` | Emplois Adzuna |
| `EURAXESS_API`, `EURAXESS_RSS`, `SOURCE_FEEDS_EXTRA` | Sources EURAXESS / RSS additionnels |
| `EMBED_MODELS` | Modèles d'embeddings candidats |
| `COLLECT_OSINT_PER_USER` | Osint LLM par utilisateur pendant la collecte (0 par défaut) |
| `OCR_LANG`, `OCR_MAX_PAGES`, `OCR_ZOOM` | OCR (CV scannés) |

---

## 12. Déploiement

```bash
cd api/                 # sur le VPS : ~/infra/forge-nex-api/
cp .env.example .env    # renseigner les clés
docker compose up -d --build
curl -s http://localhost:8000/health | python3 -m json.tool   # version + flags
```

- Image Docker : `python:3.11-slim` + `tesseract-ocr(-fra/-eng)` ; `requirements.txt` (fastapi, uvicorn,
  httpx, pydantic, PyMuPDF, reportlab, pytesseract, Pillow, python-docx).
- Volume `./data` : persistance (sessions.db + tampon outils).

---

## 13. Historique des avancées (résumé)

| Version | Apport |
|---|---|
| 2.7 | Base : onboarding déterministe, veille, Campus France, documents, multi-canal |
| 2.8 | Routeur LLM multi-fournisseurs (Cerebras → Groq → Gemini) |
| 2.9 | OCR des CV scannés |
| 2.10 | Rejet non-CV, onboarding cohérent, en-tête CV, anti-clichés |
| 2.10.1 | Menu à la demande (fin du spam de menu) |
| 2.11 | Perf : client HTTP partagé, CPU hors event-loop, anti-message perdu |
| 2.12 | Export Word (.docx) + matching sémantique (embeddings) |
| 2.13 | Routing de modèle, sources emploi (arbeitnow/Adzuna), rappels programmables, feedback 👍/👎 |
| 2.14 | EURAXESS + RSS élargis, correctifs testeurs (diplôme, type poste, doublons, mots-clés, faux wizard) |
| 2.15 | Adzuna adaptatif (mots-clés utilisateurs) + multi-pays |
| 2.16 | Fetcher EURAXESS (API/scraping HTML) |
| 2.17 | Fix embeddings (multi-modèles), fin des 429 sur la veille, RSS tolérant, anti-bot |
| 2.18 | Mode conseiller senior (bilan CV) + accompagnement procédures (/ecoles, /logement, /entretien, /canada) |
| 2.19 | Veille auto au profil validé, gamification /status, preuve sociale, outil /compresser |
| 2.20 | Boîte à outils PDF (/fusionner, /enpdf, /decouper), /budget, /eligibilite, /traduire, /procedure multi-pays |

---

## 14. Roadmap / pistes

- **Simulateur d'entretien interactif** (tour par tour, évaluation).
- **Relecteur CV/lettre** (`/relire` : correction + amélioration).
- **Épingler Belgique/Allemagne** dans le menu Procédures ; autres pays via `/procedure`.
- **Fusion → 1 dossier prêt à soumettre** (ZIP/PDF unique).
- **WhatsApp/Messenger** : tokens permanents, App Review, templates notifs.
- **Observabilité** : `/metrics` (latence LLM, taux de fallback, cache hit-rate).
- **Matching local/offline** (fastembed) en option, secrets hors image.

---

_Détail chronologique dans `docs/CHANGELOG.md` · spécifications dans `docs/SPECIFICATIONS.md` ·
guide de test dans `docs/guide-test.html`._
