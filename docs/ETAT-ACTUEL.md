# NexMove — état actuel du système

> **Statut : À JOUR** · version applicative **v4.03.0** · 22 novembre 2026
>
> **C'est le seul document de référence sur ce qu'est le système aujourd'hui.** Les autres
> fichiers de `docs/` sont soit des guides d'une tâche précise, soit des **documents
> historiques** conservés pour mémoire — ils portent un bandeau qui le dit. En cas de
> contradiction, **c'est cette page qui fait foi**, et le code tranche en dernier ressort.

## En une phrase
Un conseiller IA (emploi, études, bourses, orientation) accessible depuis Telegram, WhatsApp
et Messenger, servi par une API FastAPI sur un VPS, avec une vitrine statique.

## Architecture réelle

```
Telegram ─┐
WhatsApp ─┼─► webhooks ─► Cloudflare (tunnel nommé) ─► API FastAPI (127.0.0.1:8000, Docker)
Messenger ┘                                              │
                                                         ├─► SQLite (WAL, un fichier)
                                                         ├─► fournisseurs IA (repli en cascade)
                                                         └─► recherche web (opportunités réelles)

Vitrine  nexmove.blvckunlimited.space  ─► Cloudflare Workers (assets statiques, dossier web/)
API      api-nexmove.blvckunlimited.space
```

**Points à ne pas confondre avec les anciens documents :**
- **Telegram passe par un webhook natif** (`/webhook/telegram`), pas par n8n.
- **Le tunnel est un tunnel nommé Cloudflare**, pas ngrok. ngrok n'est plus utilisé nulle part.
- **n8n n'est plus sur le chemin critique.** Les fichiers de `workflows/` sont conservés pour
  mémoire ; le bot fonctionne sans eux.
- L'API n'est **pas** exposée directement : elle écoute sur `127.0.0.1`, derrière le tunnel.

## Code
| | |
|---|---|
| Modules Python | 6 dans `api/` : `main.py`, `db.py`, `llm.py`, `channels.py`, `http_client.py`, `orientation.py` |
| Taille | ~14 000 lignes au total, dont **~11 700 dans `main.py`** (monolithe assumé, extraction progressive) |
| Base de données | SQLite, un fichier, mode WAL — 19 tables |
| Fournisseurs IA | Cerebras → Groq → Gemini → OpenRouter → Tchavi, **en cascade** : si l'un tombe, le suivant prend le relais |

## Qualité
| | |
|---|---|
| Tests | **724**, exécutés en ~10 s (`python3 -m pytest tests -q`) |
| Fichiers de test | 11, par domaine (unités, scénarios, orientation, RGPD, sauvegarde, déploiement, pages légales…) |
| CI (`.github/workflows/ci.yml`) | 4 jobs : **`test`**, **`docker-smoke`** (l'image démarre), **`deploy-path`** (le chemin de déploiement réel fonctionne), **`audit`** (failles connues des dépendances) |
| Protection de `main` | Les jobs `test`, `docker-smoke` et `deploy-path` sont **obligatoires** : une PR en échec ne peut pas être fusionnée. Suppression de branche et force-push bloqués. |
| Vitrine | `deploy-vitrine.yml` = publication de **secours** manuelle ; la publication normale est faite par le build Cloudflare sur `main`. |

## Exploitation
| Quoi | Comment |
|---|---|
| Déployer l'API | `cd ~/infra/nexmove-src && git pull && ./scripts/deploy.sh` |
| Déployer la vitrine | Automatique (Cloudflare) à chaque fusion sur `main` |
| Sauvegarder | `./scripts/backup.sh` — voir [SAUVEGARDE.md](SAUVEGARDE.md) |
| Restaurer | `./scripts/restore.sh` |
| Secrets | `.env` du dossier de déploiement, **jamais dans le dépôt** — voir [SECURITE.md](SECURITE.md) |
| Surveiller | Message Telegram à chaque démarrage, avec alerte si un secret manque |

## Ce qui est connu et non réglé
- `main.py` reste un monolithe de ~11 700 lignes : extraction progressive vers des modules purs
  et testés (modèle : `orientation.py`), au fil des zones qu'on touche. Pas de réécriture globale.
- Quotas et verrous par utilisateur vivent **en mémoire de chaque worker** (il y en a 2) : la
  limite réelle est donc le double de l'annoncée. Sans volume, c'est théorique.
- La politique de confidentialité nomme les catégories de sous-traitants IA, pas chaque
  fournisseur, ni les durées de conservation chez eux.

## Documents de `docs/`
`docs/` ne contient **que** de la documentation opérationnelle : de quoi faire tourner, mettre à
jour et reconstruire le système. Huit fichiers, aucun doublon, chacun avec un rôle unique.

| Fichier | Rôle |
|---|---|
| **ETAT-ACTUEL.md** | ⭐ cette page — la référence sur ce qu'est le système |
| CHANGELOG.md | l'historique détaillé des versions |
| INSTALLATION.md | installer, mettre à jour, exploiter sur un VPS |
| DOMAINE-ET-TUNNEL.md | domaine, tunnel nommé Cloudflare, vitrine |
| GUIDE-WHATSAPP.md · GUIDE-MESSENGER.md | activer ces deux canaux (côté Meta) |
| SECURITE.md | ce qui est public, les secrets, la rotation des clés |
| SAUVEGARDE.md | sauvegarde chiffrée, restauration, changement de serveur |

Les documents de **stratégie** (monétisation, plan de lancement, kit de campagne, identité de
marque) ont été sortis du dépôt : il est public. Les anciennes analyses techniques et
spécifications ont été supprimées — elles décrivaient une architecture qui n'existe plus ; leur
contenu reste consultable dans l'historique Git.

## Entretenir cette page
Les chiffres ci-dessus (version, nombre de tests, modules, jobs CI) sont **vérifiés
automatiquement** par `tests/test_docs.py`. Si tu changes le système sans mettre cette page à
jour, la CI échoue — c'est volontaire : c'est ce qui empêche la documentation de redevenir
fausse en silence.
