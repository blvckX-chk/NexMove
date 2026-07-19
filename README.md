# NexMove

**Agent IA de mobilité internationale sur Telegram** — ton prochain départ : études, emploi, bourses et fellowships.
Scoring LLM des opportunités (grounding web réel) et génération automatique de documents (CV + lettre de motivation).

## Architecture (v2.1)

n8n sert de **couche de transport** ; toute la logique vit dans **FastAPI**.

```
Telegram → n8n (WF1) → FastAPI → n8n → Telegram
                          ├── SQLite (sessions + offres)
                          ├── Tavily (grounding web réel)
                          └── Groq LLM (analyse & scoring)
WF0 (24h) → /api/collect → /api/score → /api/notify   (veille proactive)
```

- **FastAPI** (`api/main.py`, port 8000) — endpoints `/api/chat`, `/api/chat-cv`, `/api/parse-cv`,
  `/api/generate-documents`, `/api/osint`, `/api/collect`, `/api/score`, `/api/notify`, `/api/session`, `/health`.
- **n8n** — WF1 (onboarding + toutes les commandes), WF0 (orchestrateur 24 h). *(WF5 déprécié : `/mobilite` est
  géré dans FastAPI.)*
- **Déploiement** — `api/docker-compose.yml` (image + `.env` + volume `./data`).

## Commandes du bot

| Commande | Rôle |
|---|---|
| `/start` | Démarrer / recommencer + créer le profil (envoi du CV) |
| `/tuto` | Guide d'utilisation pas à pas |
| `/veille` | Chercher de nouvelles opportunités maintenant |
| `/campusfrance` | Procédure « Études en France » (étapes, bourses, documents) |
| `/postuler <cible>` | Générer CV adapté + lettre de motivation (PDF) |
| `/mobilite <pays/domaine>` | Analyse mobilité ciblée |
| `/profil` · `/status` · `/supprimer` | Profil · veille · effacement (RGPD) |

## Déploiement

```bash
cd api/            # (sur le VPS : ~/infra/forge-nex-api/)
cp .env.example .env   # renseigner GROQ_API_KEY, TELEGRAM_TOKEN, TAVILY_API_KEY, GOOGLE_SHEET_ID...
docker compose up -d --build
curl -s http://localhost:8000/health
```

## Documentation
- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) — journal des évolutions.
- [`docs/roadmap-mobilite.md`](docs/roadmap-mobilite.md) — analyse experte & roadmap.
- [`README-webhook-fix.md`](README-webhook-fix.md) — correctif webhook + URL fixe.
