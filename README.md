# NexMove

**Conseiller IA d'orientation & d'opportunités sur messageries** — orientation scolaire et
professionnelle, emploi, études, bourses, fellowships, **en local comme à l'international**.
On lui parle **en langage naturel** (pas besoin de connaître les commandes) : il lit le CV,
dresse un bilan, aide à choisir une voie, trouve de vraies opportunités adaptées, accompagne
les procédures pas à pas et prépare les documents.

Multi-canal : **Telegram**, **WhatsApp** et **Messenger**.

> 📍 **[docs/ETAT-ACTUEL.md](docs/ETAT-ACTUEL.md) décrit le système tel qu'il est aujourd'hui.**
> C'est la référence à lire en premier — et la seule à suivre en cas de contradiction avec un
> autre document.

## Architecture

```
Telegram ─┐
WhatsApp ─┼─► webhooks ─► Cloudflare (tunnel nommé) ─► API FastAPI (127.0.0.1:8000, Docker)
Messenger ┘                                              │
                                                         ├─► SQLite (WAL, un fichier)
                                                         ├─► IA en cascade (Cerebras → Groq →
                                                         │   Gemini → OpenRouter → Tchavi)
                                                         └─► recherche web (opportunités réelles)

Vitrine  nexmove.blvckunlimited.space  ─► Cloudflare Workers (dossier web/)
API      api-nexmove.blvckunlimited.space
```

Le code vit dans `api/` (6 modules). Une **couche canal** (`deliver_text / menu / file`) route
vers Telegram, WhatsApp ou Messenger : les canaux sont indépendants et partagent la même
logique. Telegram passe par un **webhook natif** — n8n n'est plus sur le chemin critique.

## Quelques commandes

Orientation : `/orientation <ta question>` · `/testorientation`
Opportunités : `/veille` · `/mobilite <pays ou domaine>` · `/formations <domaine>` · `/ecoles <domaine>`
Démarches : `/campusfrance` · `/parcours` · `/canada` · `/procedure <pays>` · `/visa` · `/budget <ville>`
Candidater : `/dossier <cible>` · `/postuler <cible>` · `/creercv` · `/simulation` · `/chances <cible>`
Outils & compte : `/outils` · `/traduire <texte>` · `/profil` · `/status` · `/supprimer`
Testeurs : `/mission` (les 5 choses à essayer)

`/aide` affiche le menu complet. Le langage naturel fonctionne aussi bien que les commandes —
y compris pour dire que quelque chose ne va pas : « ça marche pas », « j'ai pas compris »
sont entendus comme des retours, pas comme des demandes.

Le test d'orientation se fait aussi **sans ouvrir le bot**, sur
[nexmove.blvckunlimited.space/orientation.html](https://nexmove.blvckunlimited.space/orientation.html)
(6 questions, sans inscription, rien d'enregistré).

### Côté administrateur
`/admin` donne le sommaire. L'essentiel :

| Commande | À quoi ça sert |
|---|---|
| `/rapport` · `/rapport semaine` | rapport terrain en fichier `.md` (compréhension, ratés, retours) |
| `/misses` | taux de compréhension + messages sans route |
| `/misses jeu` | ces messages au format de `tests/jeu_routage.jsonl`, prêts à coller |
| `/misses reset` | repartir d'une fenêtre de mesure propre |
| `/codes` · `/codes valides` | les codes générés, et ceux encore libres |
| `/gencodes testeur 60 10` | créer des accès testeur |
| `/stats` · `/ia` · `/retours` | traction · cascade IA · retours reçus |

Les tâches automatiques (rapport du soir, relance des testeurs) se posent en crontab :
voir l'en-tête de `scripts/nex-cron.sh`.

## Développement

```bash
pip install -r api/requirements.txt
python3 -m pytest tests -q          # 762 tests, ~10 s
```

La CI exécute trois contrôles obligatoires avant toute fusion sur `main` : les tests,
le démarrage de l'image Docker, et le **chemin de déploiement réel**.

## Déploiement

```bash
cd ~/infra/nexmove-src && git pull && ./scripts/deploy.sh
```

La vitrine se publie seule à chaque fusion sur `main`. Les secrets vivent dans le `.env` du
dossier de déploiement et **ne sont jamais dans le dépôt**.

## Documentation
- ⭐ **[docs/ETAT-ACTUEL.md](docs/ETAT-ACTUEL.md)** — l'état réel du système (référence).
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — journal des évolutions.
- [docs/SECURITE.md](docs/SECURITE.md) — ce qui est public, ce qui ne doit pas l'être, rotation des clés.
- [docs/SAUVEGARDE.md](docs/SAUVEGARDE.md) — sauvegarde chiffrée et restauration.
- [docs/RUNBOOK.md](docs/RUNBOOK.md) — que faire quand ça casse (pannes, accès de secours).
- [docs/INSTALLATION.md](docs/INSTALLATION.md) — installer, mettre à jour, exploiter sur un VPS.

Également dans `docs/` : [DOMAINE-ET-TUNNEL.md](docs/DOMAINE-ET-TUNNEL.md) (domaine et tunnel
Cloudflare), [GUIDE-WHATSAPP.md](docs/GUIDE-WHATSAPP.md) et
[GUIDE-MESSENGER.md](docs/GUIDE-MESSENGER.md) (activer ces canaux).

`docs/` ne contient que de la documentation **opérationnelle** — ce qu'il faut pour faire tourner
et reconstruire le système. Les documents de stratégie (monétisation, lancement, campagne,
identité) vivent hors du dépôt : celui-ci est public.
