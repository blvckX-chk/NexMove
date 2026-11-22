# Runbook — quand ça casse, et quand personne n'est là

> 📘 **Guide de tâche** · 22 novembre 2026 · **à jour**.
> Écrit pour être suivi **par quelqu'un d'autre que la personne qui a construit NexMove**, un
> jour où elle est injoignable. Vue d'ensemble : [ETAT-ACTUEL.md](ETAT-ACTUEL.md).

## 0. Les 3 choses à savoir avant tout

1. **Le bot est muet ?** → §2. **Le site est down ?** → §3. **Données perdues ?** → §4.
2. **Rien ne se répare en modifiant le code en urgence.** Presque toutes les pannes viennent
   d'un secret manquant, d'un tunnel arrêté ou d'un conteneur qui ne démarre pas.
3. **Ne jamais pousser directement sur `main`** : la CI est obligatoire, et elle existe parce
   qu'une fusion sans tests a déjà mis la production à terre (v3.96).

## 1. Où se trouve quoi

| Quoi | Où |
|---|---|
| Code source | `https://github.com/blvckX-chk/NexMove` (public) |
| Sur le serveur, dépôt | `~/infra/nexmove-src` |
| Sur le serveur, déploiement | `~/infra/forge-nex-api` — contient **`.env`** et **`data/`** |
| Base de données | `~/infra/forge-nex-api/data/sessions.db` |
| Sauvegardes chiffrées | `~/nexmove-backups/` |
| Phrase secrète des sauvegardes | `~/.nexmove-backup-pass` **et** le gestionnaire de mots de passe du propriétaire |
| Tunnel (URL publique) | `cloudflared`, lancé par `scripts/nexmove-named-tunnel.sh` (crontab `@reboot`) |

## 2. Le bot ne répond plus

Dans l'ordre, sans sauter d'étape :

```bash
# a) L'API répond-elle ?
curl -s https://api-nexmove.blvckunlimited.space/health
```
- **Réponse JSON avec une version** → l'API va bien, le problème est côté canal (voir e).
- **Pas de réponse** → continuer.

```bash
# b) Le conteneur tourne-t-il ?
docker ps --filter name=forge-nex-api
cd ~/infra/forge-nex-api && docker compose logs --tail=50
```
Les pannes déjà vues et leur cause :

| Dans les logs | Cause | Correction |
|---|---|---|
| `ModuleNotFoundError` | un fichier n'a pas été copié au déploiement | `cd ~/infra/nexmove-src && git pull && ./scripts/deploy.sh` |
| `Clé API non configurée` (503) | `FORGE_NEX_API_KEY` vide dans `.env` | voir [SECURITE.md](SECURITE.md) |
| le conteneur redémarre en boucle | erreur au démarrage | lire les 50 dernières lignes, c'est écrit dedans |

```bash
# c) Le tunnel est-il debout ? (API vivante en local mais injoignable de l'extérieur)
curl -s http://127.0.0.1:8000/health      # si ça répond ici mais pas dehors -> tunnel
pgrep -a cloudflared || ~/infra/nexmove-src/scripts/nexmove-named-tunnel.sh &
```

```bash
# d) Redémarrage complet (sans perte de données : data/ et .env ne sont pas touchés)
cd ~/infra/forge-nex-api && docker compose up -d --build
```

**e) L'API va bien mais le bot reste muet sur Telegram** → le webhook a sauté :
```bash
curl -s "https://api.telegram.org/bot<TELEGRAM_TOKEN>/getWebhookInfo"
```
S'il est vide ou pointe ailleurs, le redéclarer (commande admin `/setwebhook` dans le bot,
ou voir [INSTALLATION.md](INSTALLATION.md) §5).

## 3. La vitrine est inaccessible
Elle est servie par Cloudflare, indépendamment du serveur : **le bot peut très bien
fonctionner pendant que le site est down, et inversement.** Vérifier le build du projet
`nexmove` dans Cloudflare (Workers & Pages). Une nouvelle fusion sur `main` relance la
publication.

## 4. Données perdues ou base corrompue
→ [SAUVEGARDE.md](SAUVEGARDE.md). En résumé, **arrêter le conteneur avant de restaurer** :
```bash
cd ~/infra/forge-nex-api && docker compose down
cd ~/infra/nexmove-src && ./scripts/restore.sh          # inspection, n'écrit rien
cd ~/infra/nexmove-src && ./scripts/restore.sh --oui    # restauration réelle
cd ~/infra/forge-nex-api && docker compose up -d
```
L'état d'avant restauration est conservé dans `avant-restauration-<date>/`.

## 5. Le serveur est perdu (incendie, résiliation, disque mort)
1. Louer un VPS, installer Docker, créer un utilisateur.
2. `git clone https://github.com/blvckX-chk/NexMove.git ~/infra/nexmove-src`
3. Récupérer **une sauvegarde** (hors serveur) et la restaurer : elle contient la base **et**
   le `.env` complet. → [SAUVEGARDE.md](SAUVEGARDE.md)
4. Refaire le tunnel nommé → [DOMAINE-ET-TUNNEL.md](DOMAINE-ET-TUNNEL.md)
5. Redéclarer les webhooks (Telegram, et Meta si WhatsApp/Messenger sont actifs).
6. `./scripts/deploy.sh`, puis vérifier `/health`.

> Sans la **phrase secrète** des sauvegardes, l'étape 3 est impossible. C'est le point de
> défaillance unique du système : elle doit exister ailleurs que sur le serveur.

## 6. Accès de secours — à préparer AVANT d'en avoir besoin

C'est le point que personne ne traite à temps. Si le propriétaire est injoignable, il faut
qu'une **deuxième personne de confiance** puisse accéder à ces éléments :

| Accès | Pourquoi c'est bloquant |
|---|---|
| Compte GitHub (ou un collaborateur avec droits d'écriture) | sans lui, aucune correction ne peut être déployée |
| SSH du serveur | sans lui, aucune intervention |
| Compte Cloudflare | domaine, tunnel et vitrine en dépendent |
| **Phrase secrète des sauvegardes** | sans elle, les sauvegardes sont du bruit chiffré |
| Compte Telegram administrateur (`@BotFather`) | jeton du bot, alertes |
| Comptes des fournisseurs d'IA | renouvellement des clés |

**Moyen simple et suffisant** : un gestionnaire de mots de passe avec un contact de confiance
et un accès d'urgence (la plupart en proposent un, avec délai de carence). À défaut, une
enveloppe scellée chez une personne de confiance, mise à jour à chaque rotation de clé.

**À faire dès maintenant, dans l'ordre d'importance :**
1. La phrase secrète des sauvegardes est-elle ailleurs que sur le serveur ? Si non, c'est
   l'action la plus urgente du projet — plus urgente que n'importe quel correctif de code.
2. Une sauvegarde a-t-elle été copiée hors du serveur cette semaine ?
3. Une deuxième personne peut-elle accéder au serveur et à GitHub ?

## 7. Vérifier que tout va bien (2 minutes)
```bash
curl -s https://api-nexmove.blvckunlimited.space/health        # version attendue
curl -s -o /dev/null -w "%{http_code}\n" https://nexmove.blvckunlimited.space/
ls -lt ~/nexmove-backups/ | head -3                            # sauvegarde récente ?
```
Et dans Telegram : écrire `bonjour` au bot — c'est le seul test qui prouve que la chaîne
complète fonctionne.
