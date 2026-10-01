# NexMove

**Conseiller IA d'orientation & d'opportunités sur messageries** — études, emploi, bourses, fellowships,
**en local comme à l'international**. On lui parle **en langage naturel** (pas besoin de connaître les
commandes) : il lit le CV, dresse un bilan, trouve de vraies opportunités adaptées, accompagne les
procédures pas à pas et prépare les documents. Grounding web réel (Tavily), matching sémantique, génération
de documents (PDF + Word) et veille proactive. Multi-canal : **Telegram** (en production), **WhatsApp** &
**Messenger** (code prêt).

## Architecture (v2.7)

```
Utilisateur ─(Telegram / WhatsApp / Messenger)─▶ FastAPI (toute la logique)
                                                   ├─ SQLite (sessions, offres, candidatures, cache)
                                                   ├─ Tavily (recherche web réelle)
                                                   └─ Groq LLM (analyse, scoring, rédaction)
n8n : WF1 (transport Telegram) · WF0 (veille 24 h)
```

Toute la logique vit dans `api/main.py` ; une **couche canal** (`deliver_text/menu/file`) route vers
Telegram / WhatsApp / Messenger. Les canaux sont **indépendants** et partagent les mêmes fonctions.

## Commandes

`/start` · `/tuto` · `/veille` · `/mobilite <pays/domaine>` · `/campusfrance` · `/parcours` · `/etape` ·
`/ecoles <domaine>` · `/logement <ville>` · `/entretien` · `/canada` · `/procedure <pays>` · `/budget <ville>` · `/eligibilite <cible>` ·
`/dossier <cible>` · `/postuler <cible>` · `/formations <domaine>` ·
`/compresser` · `/fusionner` · `/enpdf` · `/decouper <pages>` · `/traduire <texte>` ·
`/rappels` · `/digest` · `/profil` · `/status` · `/supprimer`
(menu à boutons : Trouver · Procédures · Candidater · Formations · Mon espace · Aide).

## Fonctionnalités clés
- Onboarding déterministe (CV + 8 critères d'éligibilité).
- **Veille** : offres réelles (RSS + Tavily), scoring, notifications proactives, rappels de deadline J-14/7/3/1.
- **Campus France** : procédure + suivi en 8 étapes jusqu'au départ.
- **Dossiers** : documents requis + CV adapté + lettre/projet d'études (PDF), avec suivi.
- Qualité : liens fiables (par index), profil complet (reconversions), anti-offres expirées, formations gratuites d'abord.

## Déploiement
```bash
cd api/          # sur le VPS : ~/infra/forge-nex-api/
cp .env.example .env   # GROQ_API_KEY, TELEGRAM_TOKEN, TAVILY_API_KEY, GOOGLE_SHEET_ID, WHATSAPP_*/MESSENGER_*...
docker compose up -d --build
curl -s http://localhost:8000/health   # affiche version + flags *_configured
```
URL publique fixe via ngrok (webhooks + Telegram). Voir `README-webhook-fix.md`.

## Documentation
- **[docs/SPECIFICATIONS.md](docs/SPECIFICATIONS.md)** — spécifications complètes (archi, canaux, données, endpoints, roadmap).
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — journal des évolutions.
- [docs/roadmap-mobilite.md](docs/roadmap-mobilite.md) — analyse experte & roadmap mobilité.
- [README-webhook-fix.md](README-webhook-fix.md) — URL fixe & correctif webhook.
