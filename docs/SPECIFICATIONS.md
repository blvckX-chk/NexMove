# NexMove — Spécifications techniques (v2.7)

Agent IA de **mobilité internationale** (études, emploi, bourses, fellowships) sur messageries,
avec grounding web réel, scoring LLM, génération de documents et veille proactive.

---

## 1. Vision produit
Aider un candidat (cible : francophones d'Afrique de l'Ouest, ex. Bénin) à préparer son **prochain départ** :
1. analyser son profil (CV), 2. trouver de **vraies** opportunités adaptées, 3. préparer les **dossiers**
(documents + CV + lettre/projet d'études), 4. suivre ses candidatures et **ne jamais rater une deadline**.

## 2. Architecture

```
Utilisateur ──(Telegram / WhatsApp / Messenger)──▶ Webhook ──▶ FastAPI (toute la logique)
                                                                 ├─ SQLite (sessions, offres, candidatures, cache)
                                                                 ├─ Tavily (recherche web réelle = grounding)
                                                                 ├─ Groq LLM (llama-3.3-70b : analyse, scoring, rédaction)
                                                                 └─ Envoi direct au canal (texte, menus, PDF)
n8n : WF1 (transport Telegram) · WF0 (orchestrateur veille 24 h)
```

- **FastAPI** (`api/main.py`, port 8000) contient **100 % de la logique** et **envoie lui-même** les messages.
- **n8n** ne sert que de transport Telegram (WF1) + planificateur de veille (WF0).
- **Couche canal** : `session["channel"]` ∈ {telegram, whatsapp, messenger} ; `deliver_text/deliver_menu/deliver_file`
  routent vers l'adaptateur du canal. Menus définis une seule fois (`get_menu`) et rendus par canal
  (Telegram = inline keyboard ; WhatsApp = interactive buttons/list ; Messenger = quick replies).

## 3. Canaux

| Canal | État | Menus | CV PDF entrant | Docs sortants | Notifs proactives |
|---|---|---|---|---|---|
| **Telegram** | ✅ en production | boutons inline | ✅ | ✅ | ✅ illimité |
| **WhatsApp Cloud API** | 🟡 code prêt, config Meta à faire | buttons/list | ✅ | ✅ | ⚠️ hors 24 h = templates payants |
| **Messenger** | 🟡 code prêt, config Meta à faire | quick replies | ✅ | ✅ | ⚠️ fenêtre 24 h |

Webhooks : `GET/POST /webhook/whatsapp`, `GET/POST /webhook/messenger` (verify token = `nexmove_verify` par défaut).
Contrainte Meta : App Review + Business Verification pour le grand public ; sinon testeurs/admins uniquement.

## 4. Parcours & commandes

**Onboarding déterministe** (machine à états, pas de boucle LLM) :
`WELCOME → ATTENTE_CV → CV_RECU → PREFERENCES → CONFIRMATION → ACTIF`.
En PREFERENCES, 8 critères d'éligibilité collectés un par un : `objectif, nationalite, pays_cibles,
financement, certifs_langue, langues_opportunite, niveau, mots_cles`.

| Commande | Rôle |
|---|---|
| `/start` | (re)démarrer + envoyer le CV (PDF) |
| `/tuto`, `/aide` | guide / hub groupé par objectif |
| `/veille` | chercher des opportunités maintenant (stockées, dédup) |
| `/mobilite <pays/domaine>` | recherche mobilité ciblée |
| `/campusfrance` | procédure « Études en France » (grounded) |
| `/parcours`, `/etape` | suivi Campus France en 8 étapes jusqu'au départ |
| `/dossier <cible>` | liste des documents requis + CV + projet d'études (PDF) + suivi |
| `/postuler <cible>` | CV adapté + lettre de motivation (PDF) |
| `/formations <domaine>` | formations/certifs pour se distinguer (gratuites d'abord) |
| `/rappels on\|off`, `/digest quotidien\|hebdo <jour>` | notifications proactives programmables |
| `/profil`, `/status`, `/supprimer` | profil · dossiers/veille · effacement RGPD |

Menu à boutons (tous canaux) : Trouver · Procédures · Candidater · Formations · Mon espace · Aide.
Le sous-menu « Procédures » liste Campus France + les candidatures en cours (dynamique).

## 5. Qualité des recommandations (points durs)
- **Grounding Tavily** (`search_depth: advanced`, cache SQLite 6 h) : le LLM ne fait que **sélectionner/scorer**
  parmi de vrais résultats web.
- **Intégrité des liens** : sélection **par index** de résultat → l'URL/titre viennent de la source (jamais inventés).
- **Profil complet** : la pertinence se base sur résumé + formations + **expériences** et cible le **domaine
  actuel/visé** (respecte les reconversions), pas seulement les diplômes.
- **Anti-offres expirées** : date du jour injectée + filtre déterministe des `deadline_iso` passées.
- **Types explicites** : 📚 FORMATION · 💼 EMPLOI · 🎓 BOURSE · 🔬 FELLOWSHIP + confiance 🟢🟡🔴.

## 6. Veille automatique (WF0, 24 h)
`/api/collect` → `/api/score` → `/api/notify` :
- **collect** : ingère des **flux RSS de bourses réels** (scholars4dev, OpportunityDesk,
  OpportunitiesForAfricans) dans `sources_offres`, puis pour chaque utilisateur actif : grounding + matching
  (parallélisé, `asyncio.gather`) → stocke les **nouvelles** offres (dédup par URL).
- **notify** : digest Telegram/canal des offres score ≥ 60 non notifiées (marquées `notified`) + **rappels de
  deadline** J-14 / J-7 / J-3 / J-1 sur les dossiers.

## 7. Endpoints API (`X-Forge-Nex-Key` requis sauf webhooks/health)
`POST /api/chat` · `POST /api/chat-cv` · `POST /api/parse-cv` · `POST /api/generate-documents` ·
`POST /api/osint` · `POST /api/collect` · `POST /api/score` · `POST /api/notify` ·
`GET /api/session/{user_id}` · `GET /health` · `GET /` ·
`GET|POST /webhook/whatsapp` · `GET|POST /webhook/messenger`.

## 8. Modèle de données (SQLite, `data/sessions.db`)
- **sessions** (user_id PK, data JSON) — état complet par utilisateur (channel, chat_id, etape, profil,
  historique, cf_stage, pref_index, onboarding_complete…).
- **offres** (id, user_id, titre, url, type, score, deadline, statut, notified…) — offres par utilisateur.
- **candidatures** (id, user_id, cible, deadline, deadline_iso, reminders_sent, statut) — dossiers suivis.
- **sources_offres** (id, titre, url, resume, date) — pool global RSS.
- **cache** (k, v, expires) — cache TTL (Tavily 6 h).

## 9. Déploiement
- `api/docker-compose.yml` : build de l'image (main.py **embarqué**), `env_file .env`, **volume `./data`**
  (persistance). Déploiement : `docker compose up -d --build`.
- **URL publique fixe** : ngrok domaine statique (`creation-hydrant-dimple.ngrok-free.dev`) — indispensable pour
  les webhooks. n8n derrière le même tunnel (Telegram Trigger).
- `/health` renvoie `version` + flags `*_configured` = témoin de déploiement.

### Variables d'environnement
`GROQ_API_KEY`, `FORGE_NEX_API_KEY` (= header X-Forge-Nex-Key), `TELEGRAM_TOKEN`, `GOOGLE_SHEET_ID`,
`TAVILY_API_KEY`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_VERIFY_TOKEN`, `MESSENGER_TOKEN`,
`MESSENGER_VERIFY_TOKEN`, `CEREBRAS_API_KEY`, `GEMINI_API_KEY` (repli LLM), `OCR_LANG`/`OCR_MAX_PAGES`/`OCR_ZOOM` (OCR, optionnels).

## 10. Sécurité / RGPD
- Auth API par header custom. Secrets en `.env` (à terme : hors image).
- `/supprimer` = droit à l'effacement. Historique borné (30 messages). Rate-limit par utilisateur.

## 11. Roadmap / reste à faire
- **WhatsApp & Messenger** : obtenir tokens permanents (System User WhatsApp), config webhooks Meta, App Review.
  Puis **templates** pour les notifs proactives hors 24 h.
- ~~**OCR** (CV scannés) : `tesseract-ocr` + `pytesseract`~~ ✅ **fait (v2.9)** — repli OCR automatique
  dans `extract_text_pdf` quand le PDF n'a pas de texte sélectionnable.
- ~~**DOCX** : export modifiable (`python-docx`).~~ ✅ **fait (v2.12)** — CV + lettre en Word.
- ~~**Sources structurées +** : API emploi (Adzuna free)~~ ✅ **fait (v2.13)** — arbeitnow + Adzuna.
  Reste : EURAXESS, RSS additionnels.
- ~~**Matching sémantique** (embeddings)~~ ✅ **fait (v2.12)** · ~~**routing de modèle**~~ ✅ **fait (v2.13)**.
- ~~Rappels programmables · feedback 👍/👎~~ ✅ **fait (v2.13)**.
- **Boutons inline avancés / sous-menus** enrichis, multilingue (EN).
- **Sécurité** : sortir `.env` de l'image (env runtime uniquement).

## 12. Historique
Voir `docs/CHANGELOG.md` (journal des évolutions) et l'historique Git (branche
`claude/nexmove-webhook-url-fix-07sjec`, PR #1).
