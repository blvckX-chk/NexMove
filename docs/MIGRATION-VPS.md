# NexMove — Migration vers ton propre VPS (avec droits root)

Objectif : déplacer le bot vers un VPS où tu es **root**, **sans perdre de données** et **sans changer les
webhooks** (l'URL `api.nexmove.blvckunlimited.space` reste identique grâce au tunnel nommé).

> 🔑 Idée clé : tout l'état tient dans **un seul dossier `data/`** (SQLite : profils, sessions, codes
> premium, parrainages, quotas, sources) + le fichier **`.env`** (secrets). Sauvegarde ces deux-là et tu as
> tout. La vitrine (Cloudflare Pages) et le domaine (Cloudflare) ne bougent pas : ils sont hors VPS.

---

## 0. Avant de commencer
- Note l'emplacement actuel : `~/infra/forge-nex-api/` (contient `.env` + `data/`), source git dans
  `~/infra/nexmove-src/`.
- Le nouveau VPS : Ubuntu/Debian récent recommandé. Tu auras **root** → on utilisera **systemd** (plus
  fiable que le `nohup`/cron actuel).
- ⚠️ **Ne lance pas** le tunnel sur le nouveau VPS tant que l'ancien tourne encore : deux tunnels du même
  nom se disputent le trafic. On bascule à l'étape 6.

---

## 1. Nouveau VPS — installer les dépendances (root)
```bash
# Docker + plugin compose
curl -fsSL https://get.docker.com | sh
# cloudflared (tunnel)
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
  -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
cloudflared --version && docker --version
```
> (Optionnel mais recommandé) créer un utilisateur non-root pour faire tourner le projet, et l'ajouter au
> groupe `docker` : `adduser nexmove && usermod -aG docker nexmove`. La suite peut se faire sous cet
> utilisateur ; systemd ci-dessous est en root.

## 2. Ancien VPS — sauvegarder l'état
```bash
cd ~/infra/forge-nex-api
# Fige la base proprement : on arrête le conteneur le temps du tar (évite une copie WAL à chaud)
docker compose down
tar czf ~/nexmove-backup-$(date +%F).tgz .env data/
ls -lh ~/nexmove-backup-*.tgz
```
> Si tu préfères ne pas couper tout de suite, tu peux `tar` à chaud puis refaire un `tar` final juste avant
> la bascule — mais la copie à l'arrêt est la plus sûre.

## 3. Transférer la sauvegarde vers le nouveau VPS
Depuis l'ancien VPS (remplace `IP_NOUVEAU_VPS` et l'utilisateur) :
```bash
scp ~/nexmove-backup-*.tgz root@IP_NOUVEAU_VPS:/root/
```
*(ou `rsync -avz`, ou passe par un stockage intermédiaire si le scp direct n'est pas possible).*

## 4. Nouveau VPS — restaurer le projet
```bash
mkdir -p ~/infra && cd ~/infra
git clone https://github.com/blvckx-chk/nexmove nexmove-src
cd nexmove-src && git checkout claude/nexmove-webhook-url-fix-07sjec   # (ou main après la PR)
# Prépare le dossier de déploiement comme sur l'ancien VPS
mkdir -p ~/infra/forge-nex-api && cd ~/infra/forge-nex-api
cp ~/infra/nexmove-src/api/Dockerfile ~/infra/nexmove-src/api/docker-compose.yml .
cp ~/infra/nexmove-src/api/*.py .          # main.py, db.py, llm.py, http_client.py, channels.py
cp ~/infra/nexmove-src/api/requirements.txt .
# Restaure .env + data/ depuis la sauvegarde
tar xzf ~/nexmove-backup-*.tgz -C .
ls -la   # tu dois voir .env et data/ (avec sessions.db)
docker compose up -d --build
curl -s http://localhost:8000/health   # JSON de version -> l'app tourne avec tes anciennes données
```
> 💡 Ton script de déploiement habituel copie déjà ces fichiers depuis `nexmove-src`. L'essentiel ici est
> de **restaurer `.env` + `data/` par-dessus** avant le premier `up`.

## 5. Nouveau VPS — tunnel nommé en service systemd
Comme tu es root, on installe le tunnel proprement.
```bash
# 1) Authentifier + réutiliser le MÊME tunnel "nexmove"
cloudflared tunnel login            # choisis la zone blvckunlimited.space
```
Deux cas :
- **Tu réutilises le tunnel existant** : copie son fichier credentials de l'ancien VPS
  (`~/.cloudflared/<TUNNEL_ID>.json`) vers `/root/.cloudflared/` sur le nouveau. L'ID et la route DNS
  restent valables.
- **Tu recrées le tunnel** : `cloudflared tunnel create nexmove` puis
  `cloudflared tunnel route dns nexmove api.nexmove.blvckunlimited.space` (si l'ancienne route gêne,
  supprime-la d'abord côté Cloudflare DNS).

Crée `/root/.cloudflared/config.yml` :
```yaml
tunnel: nexmove
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json
ingress:
  - hostname: api.nexmove.blvckunlimited.space
    service: http://localhost:8000
  - service: http_status:404
```
Installe le service systemd :
```bash
cloudflared service install
systemctl enable --now cloudflared
systemctl status cloudflared --no-pager
```

## 6. Bascule (cutover) — sans double tunnel
1. Sur le **nouveau** VPS : `docker compose up -d` OK + `curl localhost:8000/health` OK.
2. Sur l'**ancien** VPS : **arrête tout** → `docker compose down` et stoppe le tunnel
   (`pkill -f cloudflared` ou le cron/systemd correspondant).
3. Sur le **nouveau** VPS : démarre le tunnel (`systemctl start cloudflared`).
4. Vérifie l'URL publique : `curl -s https://api.nexmove.blvckunlimited.space/health`.

## 7. Webhooks (URL inchangée → quasi rien à faire)
- **Telegram** : re-enregistre une fois pour être sûr (le secret reste le même) :
  ```bash
  source ~/infra/forge-nex-api/.env
  curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook" \
    -d url="https://api.nexmove.blvckunlimited.space/webhook/telegram" \
    -d secret_token="${TELEGRAM_WEBHOOK_SECRET}" \
    -d allowed_updates='["message","edited_message","callback_query"]'
  ```
- **WhatsApp / Messenger** : **rien à changer** côté Meta tant que l'URL reste
  `api.nexmove.blvckunlimited.space/webhook/whatsapp`.

## 8. Vérification finale
- Envoie un message au bot sur Telegram → il répond.
- `/version` → bonne version. `/moncode` d'un ancien utilisateur → son profil est bien là (données migrées).
- `docker logs forge-nex-api --tail 30` → pas d'erreur.

## 9. Sécurité (maintenant que tu es root)
- **Pare-feu** : n'ouvre que le SSH. L'API reste bindée sur `127.0.0.1:8000` (jamais exposée) ; le tunnel
  sort tout seul. Exemple UFW :
  ```bash
  ufw default deny incoming && ufw default allow outgoing
  ufw allow OpenSSH && ufw enable
  ```
- **SSH** : désactive le login root par mot de passe, passe en clés ; installe `fail2ban`.
- **Mises à jour auto** : `unattended-upgrades`.
- `META_APP_SECRET` et `TELEGRAM_WEBHOOK_SECRET` bien renseignés dans `.env` (déjà requis).
- Sauvegarde régulière du dossier `data/` (ex. cron quotidien qui tar `data/` hors VPS).

## 10. Repli (rollback)
Tant que tu n'as pas supprimé l'ancien VPS : si quelque chose cloche, ré-active l'ancien
(`docker compose up -d` + son tunnel) — l'URL publique repointe dessus. Garde l'ancien **48 h** après la
bascule avant de le résilier.

---

_Liés : `docs/DOMAINE-ET-TUNNEL.md` (tunnel & Pages), `docs/MISE-A-JOUR-SERVEUR.md` (déploiement courant),
`docs/GUIDE-WHATSAPP.md` (Meta)._
