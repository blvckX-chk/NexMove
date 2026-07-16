# NexMove

Agent IA d'automatisation de recherche d'emploi, de bourses et de mobilité
internationale, piloté via **Telegram**, avec scoring LLM des opportunités et
génération automatique de documents.

## Architecture (v4)

n8n sert de **couche de transport** ; toute la logique métier vit dans **FastAPI**.

```
Telegram → n8n (webhook) → FastAPI → n8n → Telegram
                                  └── Google Sheets (persistance)
```

- **FastAPI** (port 8000) — endpoints `/api/chat`, `/api/chat-cv`, `/api/parse-cv`,
  `/api/generate-documents`, `/api/osint`, `/api/session/{id}`, `/health`.
  Auth par header custom `X-Forge-Nex-Key`.
- **n8n** — WF0 (orchestrateur, scheduler 24 h), WF1 (onboarding Telegram),
  WF5 (OSINT mobilité). Voir `workflows/`.
- **Google Sheets** — classeur « NexMove Database » (Users, Sessions, Offres, …).

## Correctif webhook Telegram

Le problème `{"message":"Provided secret is not valid"}` (URL publique éphémère du
tunnel + `setWebhook` manuels qui cassent le secret) est traité dans
**[README-webhook-fix.md](./README-webhook-fix.md)** :

- cause racine et procédure de récupération ;
- kit URL fixe (`infra/` : tunnel Cloudflare nommé, variables n8n) ;
- workflows corrigés (`workflows/`).
