# NexMove — état actuel du système

> **Statut : À JOUR** · version applicative **v4.21.0** · 26 novembre 2026
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
         /comment-ca-marche.html = trois conversations montrées de bout en bout
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
| Base de données | SQLite, un fichier, mode WAL — 21 tables |
| Fournisseurs IA | Cerebras → Groq → Gemini → OpenRouter → Tchavi, **en cascade** : si l'un tombe, le suivant prend le relais |

## Qualité
| | |
|---|---|
| Tests | **1080**, exécutés en ~21 s (`python3 -m pytest tests -q`) |
| Fichiers de test | 26, par domaine (unités, scénarios, orientation, test web, admin, routage, suite de conversation, testeurs, cas réels, vie privée, sources locales, apprentissage, bandeau daté, bannières multi-pays, page de présentation, offre de lancement, RGPD, sauvegarde, déploiement, pages légales…) |
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
| Piloter les bannières | `/banniere` (file + état) · `/banniere valider <id>` · `/banniere rafraichir` (cherche maintenant et dit ce qui a été cherché) · `/banniere ajouter Pays \| Titre \| URL \| AAAA-MM-JJ [\| ouverture]` · `/banniere retirer <id>`. Alimentation automatique : `scripts/nex-cron.sh banniere`, à valider avant publication. |
| Recruter des testeurs | `/gencodes testeur 60 10` · le testeur tape `/mission` pour savoir quoi essayer |
| En cas de panne | [RUNBOOK.md](RUNBOOK.md) |

## Sources d'opportunités
18 sources dans `SOURCE_CATALOG` (`api/main.py`), plus Adzuna, Himalayas, The Muse, Arbeitnow,
RemoteOK, Remotive, Jobicy et EURAXESS en API. Chaque entrée porte un `scope` — `local`,
`intl` ou `both` — et `_sources_for_profile` écarte les sources 100 % internationales quand
l'objectif déclaré est purement local.

**Deux formats sont lus** : les flux RSS (`fetch_rss`) et, depuis la v4.16, les **pages de
liste rendues par le serveur** (`fetch_html_listing`), parce que la plupart des sites d'emploi
ouest-africains n'ont pas de flux. Une source HTML déclare `"kind": "html"` et un `"motif"`
d'URL d'offre ; un test échoue si le motif manque.

**Ce qu'on ne peut pas lire, et pourquoi** : les sites dont la liste est construite en
JavaScript (`emploisbenin.bj`, `jobbenin.com` — vérifiés le 26/11/2026) n'exposent aucun lien
d'offre dans leur HTML. Aucun lecteur côté serveur ne les voit. Ils ne sont **pas** déclarés :
une source muette est pire qu'une source absente. Ils restent atteignables par la recherche web.

## Dates : ne jamais servir une information périmée
Une information datée qui ne porte pas sa date devient fausse toute seule, sans erreur, sans
log, sans que personne ne s'en aperçoive. Trois endroits où ça se jouait, corrigés le
26/11/2026 (v4.18) :

| Où | Avant | Maintenant |
|---|---|---|
| **Recherches web** (`/parcours`, `/visa`, `/canada`, `/logement`, `/ecoles`, `/recours`…) | « 2026 » écrit en dur dans 15 requêtes. Le 2 janvier, elles seraient allées chercher le calendrier de l'année passée. | `_annee_courante()` pour ce qui se renouvelle par année civile (frais, barèmes, rondes) et `_annee_scolaire()` pour les calendriers universitaires, qui rend « 2026 2027 » comme les sources officielles l'écrivent. |
| **Prompts du modèle** | Aucun ne disait quel jour on était : le modèle raisonnait sur la date de son entraînement et parlait au présent d'éditions closes. | `llm.bloc_date()` est préfixé à **tous** les prompts système dans `call_groq` — le seul passage obligé des 28 appels. Recalculé à chaque appel, jamais à l'import. |
| **Bandeau de la vitrine** | Texte figé, aucune date : il invitait depuis des semaines à préparer un dossier Campus France sans que rien ne sache si la campagne était ouverte. | Liste `CAMPAGNES` datée dans `web/index.html`. Parmi les fenêtres ouvertes aujourd'hui, celle dont l'échéance est la plus proche s'affiche ; quand aucune ne correspond, **il n'y a pas de bandeau**. |

**Pourquoi « la plus proche » et non « la première »** : les fenêtres se chevauchent (entretiens
Campus France jusqu'au 15 mars, vœux Parcoursup jusqu'au 11), et un classement par ordre
d'écriture aurait caché la date couperet derrière la période qui dure.

**Comment on apprend que la liste s'épuise** : `tests/test_banniere.py` échoue quand il reste
moins de 21 jours de campagnes. Un mécanisme qui se tait quand il n'a plus rien à dire est un
mécanisme qu'on oublie ; ici c'est la CI qui prévient, avec trois semaines d'avance. Les dates
se relèvent sur **benin.campusfrance.org** — et seulement là : en novembre 2026 les
agrégateurs tiers annonçaient le 15 et le 20 novembre, la page officielle disait le 1er
décembre.

## Bannières de la vitrine (v4.21)
Le bandeau est la première chose qu'un visiteur lit. Il **fait défiler** les programmes ouverts
et à venir, de pays différents : chaque programme reste dans la rotation jusqu'à sa date limite,
puis en sort seul (règle du Propriétaire du 26/11/2026), et les programmes qui arrivent sont
annoncés pour qu'on se prépare tôt (demande du 27/11/2026).

Rappel de la décision de campagne, souvent mal résumée : la campagne démarre à sa date de
décembre, mais **on ne communique pas sur l'échéance Campus France** tant que l'outil n'a pas été
présenté. Ce n'est pas une campagne « passive » — une première rédaction de cette page le disait,
à tort.

| Pièce | Rôle |
|---|---|
| `CAMPAGNES` dans `web/index.html` | relevé officiel intégré à la vitrine, affiché tout de suite, sans attendre le réseau |
| Table `bannieres` | la file côté serveur : pays, phrase, URL source, fenêtre, date d'ouverture, statut |
| `GET /api/banniere` | public : `items` (la rotation) + le premier programme à la racine, pour la vitrine v4.20 |
| `POST /api/banniere/refresh` | cron (`nex-cron.sh banniere`) : cherche dans des pays **absents** de la file |
| `/banniere` (admin) | voir, `valider`, `retirer`, `ajouter` (avec date d'ouverture facultative), `rafraichir` |

**Trois types d'entrées sur la vitrine** : *ouvert* (compte à rebours sous dix jours), *bientôt*
(date d'ouverture **officielle** connue ; l'annonce s'arrête la veille de l'ouverture), *à
surveiller* (appel attendu mais pas publié — ces entrées n'affichent **aucune date**, un test le
vérifie, et expirent à une date de révision au lieu de devenir fausses).

**Ordre** : l'échéance ouverte la plus proche d'abord, puis les annonces, puis ce qui est à
surveiller ; les pays alternent sans casser la tête de liste. Si l'API répond pendant
l'affichage, la rotation repart en tête ; plus tard, elle reprend là où en était le visiteur.

**Quatre règles non négociables**, dans cet ordre :

1. **Le modèle n'écrit jamais la phrase affichée.** Il extrait des champs ; la phrase est
   assemblée par `_banniere_phrase()`. La date montrée est donc celle qui est en base.
2. **Une URL absente des résultats de recherche est rejetée.**
3. **Pas de date limite lisible, pas de bannière.** Échéance à moins de dix jours : écartée.
4. **Ce que trouve le cron n'est pas public avant validation humaine** (`/banniere valider`).
   Les règles 1 à 3 garantissent qu'une date vient d'une vraie page, pas que cette page dit vrai :
   le 27/11/2026, les agrégateurs donnaient la première soumission Campus France au 15 et au
   20 novembre, la page officielle disait le 1er décembre. Désactivable (`BANNIERE_VALIDATION=0`),
   mais ce serait parier sur les agrégateurs.

**Pourquoi peu de pays pour l'instant.** Au 27/11/2026, aucun programme hors France n'a pu être
vérifié sur une source officielle comme ouvert aux candidats béninois avec au moins dix jours
devant lui : appels 2027 clos (MEXT, Fulbright), pas encore publiés (Türkiye Bursları, Stipendium
Hungaricum), derrière une agence nationale aux dates non publiques (Maurice), ou site officiel
injoignable (E-JUST). La variété viendra à mesure que les appels sortent — `/banniere rafraichir`
dit ce qui a été cherché, y compris quand rien n'est trouvé.

**Accessibilité** : pause au survol et au focus, bouton « suivant » de 44 px, aucune rotation
automatique si le visiteur a demandé moins de mouvement, rotation non annoncée aux lecteurs
d'écran sauf quand la personne demande la suite. Le texte de l'API entre par `textContent`.

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

## Offre de lancement : tout est gratuit jusqu'au 1er mars 2027
Les formules et les packs de crédits **restent affichés avec leurs prix** — le modèle
économique n'est pas effacé, c'est la gratuité qui est datée. Pendant le lancement, qui
accepte d'être testeur (`/testeur`, ou « je veux être testeur ») obtient l'accès complet
sans quota jusqu'au `LANCEMENT_FIN`.

Ce que la gratuité achète n'est pas du volume, c'est du retour de terrain : la seule chose
qui ait jamais trouvé un défaut dans ce produit.

**L'offre s'arrête d'elle-même.** L'échéance est une date (`LANCEMENT_FIN`, surchargeable par
variable d'environnement), et le statut testeur expire par le mécanisme d'abonnement qui
existait déjà — `premium_until`. Le 2 mars, `/offres` redevient une page de tarifs et les
quotas ci-dessous reprennent, sans qu'une ligne de code change. Une promotion qui ne sait pas
s'arrêter devient un produit gratuit par oubli.

Deux pièges verrouillés par `tests/test_lancement.py` : un abonnement payant plus long que
l'offre n'est **jamais** dégradé en « testeur jusqu'au 1er mars » ; et « je veux être testeur
de logiciels » est une question de métier, pas une adhésion — la première version de la règle
de langage changeait le statut de qui parlait de sa carrière.

## Quotas gratuits (par jour)
Divisés par deux le 26/11/2026. Chacun est surchargeable par variable d'environnement.
Ils ne s'appliquent pas aux testeurs, donc en pratique pas avant le 2 mars 2027.

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
- La politique de confidentialité ne connaît pas les **durées de conservation** chez les
  fournisseurs d'IA, et le dit plutôt que de les inventer. Le reste est désormais nommé :
  chaque fournisseur figure au tableau, et le lieu de stockage est renseigné — serveur loué
  chez Contabo, **dans l'Union européenne** (relevé sur le panneau Contabo le 26/11/2026).
  Le stockage est européen, le traitement par les modèles est américain et ne reçoit jamais
  l'identité de la personne.

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
