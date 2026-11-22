# NexMove — Installation et exploitation

> 📘 **Guide de tâche** · révisé le 22 novembre 2026 · **à jour**.
> Vue d'ensemble du système : [ETAT-ACTUEL.md](ETAT-ACTUEL.md).
>
> **C'est le seul document d'installation.** Il renvoie, sans les réécrire, vers :
> [DOMAINE-ET-TUNNEL.md](DOMAINE-ET-TUNNEL.md) (domaine et tunnel Cloudflare),
> [GUIDE-WHATSAPP.md](GUIDE-WHATSAPP.md) et [GUIDE-MESSENGER.md](GUIDE-MESSENGER.md) (activer ces canaux),
> [SAUVEGARDE.md](SAUVEGARDE.md) (sauvegarder, restaurer, **changer de serveur**),
> [SECURITE.md](SECURITE.md) (secrets et rotation des clés).

Ce guide couvre l'installation complète sur un VPS Linux, de zéro jusqu'à la production, puis les mises à
jour et le dépannage. Temps estimé : ~45 min la première fois.

---

## 0. Vue d'ensemble

```
Telegram / WhatsApp / Messenger ──▶ webhooks
            │
  tunnel nommé Cloudflare ──▶ FastAPI (forge-nex-api, 127.0.0.1:8000)
                                   ├─ SQLite (./data, persistant, mode WAL)
                                   └─ recherche web · IA en cascade (Cerebras/Groq/Gemini/…)
cron système ──▶ scripts/nex-cron.sh ──▶ /api/collect → /api/score → /api/notify
```

- **FastAPI** contient 100 % de la logique, y compris le **webhook Telegram natif**
  (`/webhook/telegram`) : n8n n'est plus sur le chemin critique.
- L'API n'est **pas** exposée directement : elle écoute sur `127.0.0.1`, derrière le tunnel.
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
| **Cloudflare** | (tunnel nommé + DNS) | dash.cloudflare.com | ✅ (URL fixe) |

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

Clone le dépôt **une fois** sur le VPS ; ensuite, `scripts/deploy.sh` synchronise tout seul
le code vers le dossier de déploiement (il ne touche jamais à `.env` ni à `data/`) :
```bash
git clone https://github.com/blvckX-chk/NexMove.git ~/infra/nexmove-src
```
> Ne copie plus les fichiers à la main : un module oublié = API morte au démarrage. C'est
> arrivé en v3.96, et c'est pour ça que la CI teste désormais ce chemin exact.

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
FORGE_NEX_API_KEY=<clé aléatoire, 32+ caractères>   # header X-Forge-Nex-Key

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

## 5. URL publique fixe (tunnel nommé Cloudflare)

Les webhooks ont besoin d'une **URL stable**. On utilise un **tunnel nommé Cloudflare**, qui publie
`api-nexmove.blvckunlimited.space` vers l'API locale. Jamais un tunnel éphémère
(`trycloudflare`) : c'était la cause du bug « Provided secret is not valid ».

> ⚠️ Les anciennes versions de ce guide décrivaient **ngrok + n8n**. Ce n'est plus l'architecture
> en service. Procédure détaillée : **[DOMAINE-ET-TUNNEL.md](DOMAINE-ET-TUNNEL.md)**.

1. Crée le tunnel nommé et son enregistrement DNS (voir le guide ci-dessus).
2. Lance-le au démarrage : `scripts/nexmove-named-tunnel.sh` (ligne `@reboot` dans la crontab).
3. Déclare le webhook Telegram vers `https://TON-DOMAINE/webhook/telegram` (commande admin `/setwebhook`).

---

## 6. n8n — non requis

Le bot fonctionne **sans n8n** : le transport Telegram est natif (`/webhook/telegram`) et la veille
passe par le cron système (`scripts/nex-cron.sh`). Les fichiers de `workflows/` sont conservés pour
mémoire ; l'historique de l'ancienne chaîne est dans l'historique Git.

---

## 7. Tests de bout en bout

```bash
# API vivante
curl -s http://localhost:8000/health | python3 -m json.tool | grep version

# Bot : sur Telegram, /start → envoyer un CV PDF → répondre Oui → voir le bilan + 3 pistes
# Veille manuelle
curl -s -X POST http://localhost:8000/api/collect -H "X-Forge-Nex-Key: $FORGE_NEX_API_KEY" | python3 -m json.tool

# Embeddings actifs ?
docker exec forge-nex-api python -c "import asyncio,main; print('vecteur' if asyncio.run(main.embed_text('test')) else 'lexical')"
```

---

## 8. Mises à jour

```bash
cd ~/infra/nexmove-src && git pull && ./scripts/deploy.sh
```

Le script met le dépôt à jour, synchronise **tous** les modules, reconstruit l'image, redémarre le
conteneur et vérifie `/health`. Le volume `./data` (sessions, dossiers) est conservé à chaque rebuild.
Tu reçois un message Telegram au démarrage, avec une alerte si un secret manque.

---

## 9. Dépannage (cas réels rencontrés)

| Symptôme | Cause | Solution |
|---|---|---|
| `Provided secret is not valid` | URL webhook éphémère (trycloudflare) | Utiliser le **tunnel nommé** Cloudflare, puis refaire `/setwebhook` |
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

## 10. Sauvegarde, sécurité, changement de serveur

- **Sauvegarder / restaurer / migrer vers un autre VPS** : [SAUVEGARDE.md](SAUVEGARDE.md).
  L'archive chiffrée contient la base **et** le `.env` : restaurer sur une machine neuve suffit à
  remonter le service. N'archive plus `data/` à la main.
- **Secrets, rotation des clés, ce qui est public** : [SECURITE.md](SECURITE.md).
- **Authentification de l'API** : header `X-Forge-Nex-Key` sur tous les endpoints, sauf `/health`
  et les webhooks (eux sont authentifiés par signature).

---

## 11. Checklist de mise en production

- [ ] Docker + Compose installés
- [ ] `main.py`, `requirements.txt`, `Dockerfile`, `docker-compose.yml` en place
- [ ] `.env` renseigné (Telegram, un LLM, Tavily, Gemini pour embeddings)
- [ ] `docker compose up -d --build` OK, `/health` = bonne version
- [ ] Tunnel nommé Cloudflare actif (`scripts/nexmove-named-tunnel.sh`, relancé au boot)
- [ ] WF0 planifié (veille 24 h)
- [ ] Test Telegram : /start → CV → bilan + 3 pistes → /veille → /compresser
- [ ] `data/` sauvegardé régulièrement

---

_Voir aussi : `docs/FONCTIONNALITES.md` (référence des commandes) · `docs/SPECIFICATIONS.md` (specs) ·
`docs/CHANGELOG.md` (historique) · `docs/guide-test.html` (protocole testeurs)._
