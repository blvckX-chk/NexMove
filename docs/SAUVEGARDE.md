# Sauvegarde et restauration

Sans sauvegarde, un disque perdu = **toutes les données utilisateurs perdues définitivement**
(profils, CV analysés, candidatures, abonnements). C'est le seul incident dont on ne peut pas
se remettre. Ces scripts existent pour ça.

## Mise en place (une seule fois, sur le serveur)

```bash
cd ~/infra/nexmove-src

# 1. Phrase secrète de chiffrement
python3 -c "import secrets; print(secrets.token_urlsafe(24))" > ~/.nexmove-backup-pass
chmod 600 ~/.nexmove-backup-pass
cat ~/.nexmove-backup-pass      # ⚠️ NOTE-LA dans ton gestionnaire de mots de passe
```

> ⚠️ **Sans cette phrase, les sauvegardes sont irrécupérables.** Elle ne doit pas exister
> *uniquement* sur le serveur : si tu perds le serveur, tu perds aussi la phrase, donc tout.

```bash
# 2. Première sauvegarde
./scripts/backup.sh
```

```bash
# 3. Automatiser (tous les jours à 3h17)
(crontab -l 2>/dev/null; echo "17 3 * * * cd ~/infra/nexmove-src && ./scripts/backup.sh >> ~/backup.log 2>&1") | crontab -
```

## Ce que contient l'archive
`sessions.db` (toutes les données), `.env` (**tous les secrets de production**) et
`docker-compose.yml`. Chiffrée en AES-256, droits `600`.

Volontairement **exclus** : les fichiers déposés par les utilisateurs (volumineux, et
reconstituables — ils peuvent renvoyer leur CV).

## La règle qui compte : sortir l'archive du serveur
Une sauvegarde qui dort à côté de la base ne protège **que** d'une bêtise logicielle, pas de la
perte du serveur. Copie-la ailleurs — depuis ton PC :

```bash
scp root@TON_SERVEUR:~/nexmove-backups/nexmove-*.tar.gz.gpg ~/sauvegardes-nexmove/
```

## Restaurer

```bash
# 1. Regarder ce que contient la dernière sauvegarde (n'écrit RIEN)
./scripts/restore.sh

# 2. Restaurer pour de vrai
cd ~/infra/forge-nex-api && docker compose down
cd ~/infra/nexmove-src && ./scripts/restore.sh --oui
cd ~/infra/forge-nex-api && docker compose up -d
```

Garde-fous : l'archive est vérifiée avant d'écrire, le conteneur doit être arrêté (restaurer
sous une base ouverte la corromprait), et l'état actuel est copié dans
`avant-restauration-<date>/` avant tout écrasement — on peut toujours revenir en arrière.

## Vérifications
- La sauvegarde **se teste elle-même** : elle rouvre l'archive, contrôle l'intégrité SQLite et
  compte les sessions. Elle échoue plutôt que de laisser une archive douteuse.
- `tests/test_backup.py` rejoue en CI le cycle complet : sauvegarde → base détruite →
  restauration → données vérifiées.
- À faire une fois par trimestre, à la main : restaurer dans un dossier de test
  (`NEXMOVE_DEPLOY_DIR=/tmp/essai ./scripts/restore.sh --oui`) pour confirmer que **ta** phrase
  secrète fonctionne toujours.

## En cas d'incident
1. Ne pas réinstaller par-dessus : d'abord `./scripts/restore.sh` (inspection seule).
2. Arrêter le conteneur, restaurer, redémarrer.
3. Vérifier : `curl -s https://api-nexmove.blvckunlimited.space/health`
