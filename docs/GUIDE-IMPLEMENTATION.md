# NexMove — Guide d'implémentation (déploiement de A à Z)

Ce guide couvre l'installation complète sur un VPS Linux, de zéro jusqu'à la production, puis les mises à
jour et le dépannage. Temps estimé : ~45 min la première fois.

---

## 0. Vue d'ensemble

```
Telegram ──▶ n8n (WF1 transport) ──▶ FastAPI (forge-nex-api:8000) ──▶ Telegram (envoi direct)
                                          ├─ SQLite (./data, persistant)
                                          ├─ Tavily · LLM (Cerebras/Groq/Gemini) · Embeddings
n8n WF0 (cron 24 h) ──▶ /api/collect → /api/score → /api/notify
ngrok (domaine statique) ──▶ expose n8n + webhooks à Internet
```

- **FastAPI** contient 100 % de la logique. **n8n** ne fait que le transport Telegram + le cron veille.
- Tout tourne en **Docker** sur le VPS. Le dossier `./data` (volume) conserve la base SQLite.

---

## 1. Prérequis

### 1.1 Serveur
- Un VPS Linux (Ubuntu/Debian), 1–2 vCPU, 2 Go RAM min (l'OCR + PDF aiment la RAM).
- **Docker** + **Docker Compose** installés :
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER   # puis se reconnecter
  docker compose version
  ```

### 1.2 Comptes & clés API (gratuits)
| Service | Clé | Où l'obtenir | Obligatoire ? |
|---|---|---|---|
| **Telegram** | `TELEGRAM_TOKEN` | @BotFather → /newbot | ✅ oui |
| **Groq** | `GROQ_API_KEY` | console.groq.com | ✅ (au moins un LLM) |
| **Cerebras** | `CEREBRAS_API_KEY` | cloud.cerebras.ai | ➕ fallback |
| **Gemini** | `GEMINI_API_KEY` | aistudio.google.com/apikey | ➕ fallback **+ embeddings** |
| **Tavily** | `TAVILY_API_KEY` | tavily.com | ✅ (grounding web) |
| **Adzuna** | `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` | developer.adzuna.com | ➕ emplois |
| **ngrok** | (domaine statique) | ngrok.com → Domains | ✅ (URL fixe) |

> 💡 Gemini sert **à la fois** de fallback LLM et d'**embeddings** (matching sémantique). Fortement recommandé.

---

## 2. Arborescence sur le VPS

```
~/infra/
├── forge-nex-api/          # l'API NexMove
│   ├── main.py             # le code (fourni)
│   ├── requirements.txt    # dépendances Python (fourni)
│   ├── Dockerfile          # image (fourni)
│   ├── docker-compose.yml  # orchestration (fourni)
│   ├── .env                # TES clés (jamais committer)
│   └── data/               # base SQLite (créé au 1er run, persistant)
└── n8n/                    # n8n (transport Telegram + cron)
    └── docker-compose.yml
```

Créer le dossier :
```bash
mkdir -p ~/infra/forge-nex-api && cd ~/infra/forge-nex-api
```

---

## 3. Les fichiers

Copie depuis le dépôt (dossier `api/`) : `main.py`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`.
Soit par `git clone`/`git pull`, soit par `scp` depuis ta machine :
```bash
scp api/main.py api/requirements.txt api/Dockerfile api/docker-compose.yml \
    UTILISATEUR@IP_VPS:~/infra/forge-nex-api/
```

### 3.1 `.env` (à créer, avec TES valeurs)
```bash
cp .env.example .env
nano .env
```
Contenu minimal fonctionnel :
```bash
# --- LLM (au moins un) ---
GROQ_API_KEY=gsk_...
CEREBRAS_API_KEY=
GEMINI_API_KEY=AIza...          # recommandé (fallback + embeddings sémantiques)

# --- Sécurité API ---
FORGE_NEX_API_KEY=forge_nex_secret_2026   # header X-Forge-Nex-Key

# --- Telegram (token ACTUEL du bot) ---
TELEGRAM_TOKEN=123456:AA...

# --- Grounding web ---
TAVILY_API_KEY=tvly-...

GENERIC_TIMEZONE=Africa/Porto-Novo

# --- Emplois (optionnel) ---
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
ADZUNA_COUNTRY=fr,ca,be

# --- Embeddings / veille (valeurs par défaut OK) ---
EMBED_MODELS=gemini-embedding-001,text-embedding-004,embedding-001
COLLECT_OSINT_PER_USER=0
```
> ⚠️ **TELEGRAM_TOKEN doit être le token ACTUEL** (après toute révocation), sinon l'envoi des PDF échoue.

---

## 4. Build & lancement

```bash
cd ~/infra/forge-nex-api
docker compose up -d --build
```
La 1ʳᵉ build installe tesseract (OCR) + les libs PDF : compter 2–3 min.

### Vérifier
```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```
Attendu : `"version": "2.20.1"`, `"telegram_configured": true`, `"tavily_configured": true`,
`"llm_providers": [...]`, `"semantic_matching": true` (si clé Gemini valide).

---

## 5. URL publique fixe (ngrok)

Telegram et les webhooks ont besoin d'une **URL stable**. Utilise un **domaine statique ngrok** (gratuit) —
jamais un tunnel éphémère (c'était la cause du bug « Provided secret is not valid »).

1. Récupère ton domaine sur ngrok.com → **Domains** (ex. `creation-hydrant-dimple.ngrok-free.dev`).
2. Configure ngrok pour exposer **n8n** (port 5678) derrière ce domaine (dans le compose n8n ou un service
   ngrok dédié). L'API (8000) est jointe par n8n en interne via `host.docker.internal:8000`.

---

## 6. n8n : les deux workflows

### WF1 — Transport Telegram (obligatoire)
- **Telegram Trigger** écoute `message` **et** `callback_query`.
- Un **Code node** normalise le message (texte / document / bouton).
- Route :
  - document (CV/PDF) → télécharge → `POST http://host.docker.internal:8000/api/chat-cv` (multipart :
    `file`, `user_id`, `chat_id`, `username`) ;
  - texte / bouton → `POST http://host.docker.internal:8000/api/chat` (JSON : `user_id`, `chat_id`,
    `username`, `text`, `message_type`, `callback_data`, `callback_id`, `message_id`).
- **Pas de node d'envoi** : c'est FastAPI qui répond directement à Telegram.
- Header sur chaque requête : `X-Forge-Nex-Key: forge_nex_secret_2026`.
- Le JSON du workflow est dans `workflows/WF1_Onboarding_Telegram.json`.

> Règle d'or : **un seul** workflow avec Telegram Trigger actif (WF1). Ne jamais relancer `setWebhook` à la
> main. Si un autre workflow (ex. WF5) capte le webhook, désactive-le puis réactive WF1.

### WF0 — Veille 24 h (recommandé)
Un **Schedule Trigger** (toutes les 24 h) qui enchaîne, avec le header API :
```
POST http://host.docker.internal:8000/api/collect
POST http://host.docker.internal:8000/api/score
POST http://host.docker.internal:8000/api/notify
```
→ ingère les sources, score par profil, envoie le digest + rappels de deadline.

---

## 7. Tests de bout en bout

```bash
# API vivante
curl -s http://localhost:8000/health | python3 -m json.tool | grep version

# Bot : sur Telegram, /start → envoyer un CV PDF → répondre Oui → voir le bilan + 3 pistes
# Veille manuelle
curl -s -X POST http://localhost:8000/api/collect -H "X-Forge-Nex-Key: forge_nex_secret_2026" | python3 -m json.tool

# Embeddings actifs ?
docker exec forge-nex-api python -c "import asyncio,main; print('vecteur' if asyncio.run(main.embed_text('test')) else 'lexical')"
```

---

## 8. Mises à jour

En général, **seul `main.py` change** :
```bash
scp api/main.py UTILISATEUR@IP_VPS:~/infra/forge-nex-api/
cd ~/infra/forge-nex-api && docker compose up -d --build
curl -s http://localhost:8000/health | python3 -m json.tool | grep version
```
Si `requirements.txt`/`Dockerfile` changent (nouvelle dépendance système comme l'OCR), copie-les **aussi**
avant le `--build`. Le volume `./data` (sessions, dossiers) est **conservé** à chaque rebuild.

---

## 9. Dépannage (cas réels rencontrés)

| Symptôme | Cause | Solution |
|---|---|---|
| `Provided secret is not valid` | URL webhook éphémère (trycloudflare) | Domaine **statique ngrok**, un seul WF1 actif |
| `/postuler` : envoi Telegram échoué | `TELEGRAM_TOKEN` périmé dans `.env` | Mettre le token actuel + `up -d --build` |
| `/health` renvoie une vieille version | main.py pas copié avant build | Re-scp `main.py` puis `--build` |
| `429` / `503 Service IA surchargé` en veille | osint LLM par utilisateur | `COLLECT_OSINT_PER_USER=0` (défaut) |
| `[embed] 404 ... not found` | modèle d'embeddings refusé par la clé | déjà géré (essaie plusieurs modèles) ; sinon lexical |
| `ocr_configured: false` | tesseract pas installé | Dockerfile à jour + `--build` |
| Menu qui se répète à chaque message | ancienne version | déployer ≥ 2.10.1 |
| Le bot « Bonjour »/vouvoie/redemande le CV | ancienne conversation | déployer ≥ 2.20.1 |
| `no space left on device` | disque plein | supprimer images/volumes inutilisés : `docker system prune -af` |

Logs utiles :
```bash
docker logs forge-nex-api --tail 50
docker logs forge-nex-api --tail 80 | grep -Ei 'error|429|embed|euraxess|llm'
```

---

## 10. Sauvegarde & sécurité

- **Sauvegarde** : archiver `~/infra/forge-nex-api/data/` (contient `sessions.db`).
  ```bash
  tar czf nexmove-data-$(date +%F).tgz -C ~/infra/forge-nex-api data
  ```
- **Secrets** : ne jamais committer `.env`. `/supprimer` = droit à l'effacement (RGPD).
- **Auth API** : header `X-Forge-Nex-Key` sur tous les endpoints sauf `/health` et les webhooks.

---

## 11. Checklist de mise en production

- [ ] Docker + Compose installés
- [ ] `main.py`, `requirements.txt`, `Dockerfile`, `docker-compose.yml` en place
- [ ] `.env` renseigné (Telegram, un LLM, Tavily, Gemini pour embeddings)
- [ ] `docker compose up -d --build` OK, `/health` = bonne version
- [ ] Domaine ngrok statique actif, un seul WF1 (Telegram Trigger) actif
- [ ] WF0 planifié (veille 24 h)
- [ ] Test Telegram : /start → CV → bilan + 3 pistes → /veille → /compresser
- [ ] `data/` sauvegardé régulièrement

---

_Voir aussi : `docs/FONCTIONNALITES.md` (référence des commandes) · `docs/SPECIFICATIONS.md` (specs) ·
`docs/CHANGELOG.md` (historique) · `docs/guide-test.html` (protocole testeurs)._
