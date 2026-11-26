# NexMove — état actuel du système

> **Statut : À JOUR** · version applicative **v4.15.0** · 26 novembre 2026
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
         /orientation.html  = test d'intérêts jouable sur la page, 100 % local
         (aucune IA, aucun stockage, aucun appel à l'API ; renvoie vers le bot
          avec le résultat dans le lien : /start ori_SA)
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
| Tests | **922**, exécutés en ~13 s (`python3 -m pytest tests -q`) |
| Fichiers de test | 19, par domaine (unités, scénarios, orientation, test web, admin, routage, suite de conversation, testeurs, cas réels, vie privée, RGPD, sauvegarde, déploiement, pages légales…) |
| CI (`.github/workflows/ci.yml`) | 4 jobs : **`test`**, **`docker-smoke`** (l'image démarre), **`deploy-path`** (le chemin de déploiement réel fonctionne), **`audit`** (failles connues des dépendances) |
| Protection de `main` | Les jobs `test`, `docker-smoke` et `deploy-path` sont **obligatoires** : une PR en échec ne peut pas être fusionnée. Suppression de branche et force-push bloqués. |
| Vitrine | `deploy-vitrine.yml` = publication de **secours** manuelle ; la publication normale est faite par le build Cloudflare sur `main`. |

## Exploitation
| Quoi | Comment |
|---|---|
| Déployer l'API | `cd ~/infra/nexmove-src && git pull && ./scripts/deploy.sh` |
| Déployer la vitrine | Automatique (Cloudflare) à chaque fusion sur `main` |
| Modifier le test d'orientation | Éditer **`api/orientation.py`** uniquement, puis `python3 scripts/gen-orientation-web.py`. `web/orientation-data.js` est **généré** : la page web et le bot doivent poser le même test, et la CI échoue sinon. |
| Sauvegarder | `./scripts/backup.sh` — voir [SAUVEGARDE.md](SAUVEGARDE.md) |
| Restaurer | `./scripts/restore.sh` |
| Secrets | `.env` du dossier de déploiement, **jamais dans le dépôt** — voir [SECURITE.md](SECURITE.md) |
| Surveiller | Message Telegram au démarrage (alerte si un secret manque) · `/ia` en admin et `/api/admin/llm` : qui répond, latence, bascules |
| Mesurer la compréhension | `/misses` (taux + messages sans route) · `/misses jeu` (au format du jeu d'évaluation) · `/misses reset` (fenêtre propre) |
| Suivre le terrain | `/rapport` ou `/rapport semaine` → fichier `.md` envoyé sur Telegram. Automatique via `scripts/nex-cron.sh rapport` (crontab, voir l'en-tête du script). |
| Recruter des testeurs | `/gencodes testeur 60 10` · le testeur tape `/mission` pour savoir quoi essayer |
| En cas de panne | [RUNBOOK.md](RUNBOOK.md) |

## Garde-fous déterministes (jamais confiés au modèle)
Trois situations où une réponse improvisée coûterait trop cher. Toutes détectées par
expression régulière dans `api/orientation.py`, testées, et placées **avant** tous les flux
guidés — un questionnaire en cours ne retient jamais quelqu'un dans l'une de ces situations.

| Situation | Ce que fait le bot |
|---|---|
| **Arnaque** (« paie et je te garantis le visa », voie illégale) | Énonce la règle : un vrai employeur, une vraie école, une vraie ambassade ne demandent **jamais** d'argent. Nomme les guichets officiels, puis propose la voie légale. |
| **Détresse** (souffrance profonde) | Accueille, dit qu'il n'est pas la bonne personne, oriente vers un humain de confiance, et reste disponible. |
| **Refus de visa ou d'admission** | Part sur `/recours`, pas sur l'information générale — le pire moment pour réexpliquer comment déposer. |

Les frais légitimes (Campus France, TLS/VFS/Capago, scolarité, loyer, caution) ne déclenchent
rien : crier au loup les rendrait suspects.

## Programme testeurs
Le palier **testeur** n'est ni gratuit ni payant : même confort que le Premium (pas de quota,
pas de filigrane), mais surtout **le bot sait qu'il parle à un testeur** et peut lui demander
un retour au bon moment.

Un retour n'a pas besoin de commande : « ça marche pas », « j'ai pas compris », « c'est bizarre »
sont enregistrés, transmis à l'admin **avec la réponse qui précédait**, et comptés dans `/rapport`.
C'est la correction d'un défaut constaté : les meilleurs retours arrivaient dans le WhatsApp
personnel du propriétaire et n'entraient jamais dans le produit.

## Quotas gratuits (par jour)
Divisés par deux le 26/11/2026. Chacun est surchargeable par variable d'environnement.

| Action | Gratuit | Variable |
|---|---|---|
| Analyse de CV | 4 | `FREE_CV_DAILY` |
| Recherches `/veille` + `/mobilite` | 3 | `FREE_VEILLE_DAILY` |
| Captures guidées (vision) | 6 | `FREE_GUIDE_DAILY` |
| Messages vocaux | 10 | `FREE_VOICE_DAILY` |
| Audit d'un lien | 2 | `FREE_LINK_DAILY` |
| `/chances` | 1 | `FREE_SCORE_DAILY` |
| `/commentpostuler` | 1 | `FREE_APPLY_DAILY` |
| Simulation d'entretien | 1 | `FREE_SIM_DAILY` |

Admin, testeurs et abonnés : aucun quota. Au-delà de la limite gratuite, un **crédit** peut
être consommé à la place.

## Ce qui est connu et non réglé
- `main.py` reste un monolithe de ~11 700 lignes : extraction progressive vers des modules purs
  et testés (modèle : `orientation.py`), au fil des zones qu'on touche. Pas de réécriture globale.
- Quotas et verrous par utilisateur vivent **en mémoire de chaque worker** (il y en a 2) : la
  limite réelle est donc le double de l'annoncée. Sans volume, c'est théorique.
- La politique de confidentialité nomme les catégories de sous-traitants IA, pas chaque
  fournisseur, ni les durées de conservation chez eux.

## Documents de `docs/`
`docs/` ne contient **que** de la documentation opérationnelle : de quoi faire tourner, mettre à
jour et reconstruire le système. Neuf fichiers, aucun doublon, chacun avec un rôle unique.

| Fichier | Rôle |
|---|---|
| **ETAT-ACTUEL.md** | ⭐ cette page — la référence sur ce qu'est le système |
| CHANGELOG.md | l'historique détaillé des versions |
| INSTALLATION.md | installer, mettre à jour, exploiter sur un VPS |
| DOMAINE-ET-TUNNEL.md | domaine, tunnel nommé Cloudflare, vitrine |
| GUIDE-WHATSAPP.md · GUIDE-MESSENGER.md | activer ces deux canaux (côté Meta) |
| SECURITE.md | ce qui est public, les secrets, la rotation des clés |
| SAUVEGARDE.md | sauvegarde chiffrée, restauration, changement de serveur |
| RUNBOOK.md | que faire quand ça casse — écrit pour quelqu'un d'autre que le constructeur |

Les documents de **stratégie** (monétisation, plan de lancement, kit de campagne, identité de
marque) ont été sortis du dépôt : il est public. Les anciennes analyses techniques et
spécifications ont été supprimées — elles décrivaient une architecture qui n'existe plus ; leur
contenu reste consultable dans l'historique Git.

## Entretenir cette page
Les chiffres ci-dessus (version, nombre de tests, modules, jobs CI) sont **vérifiés
automatiquement** par `tests/test_docs.py`. Si tu changes le système sans mettre cette page à
jour, la CI échoue — c'est volontaire : c'est ce qui empêche la documentation de redevenir
fausse en silence.
