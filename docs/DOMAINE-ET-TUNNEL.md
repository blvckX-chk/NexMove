# NexMove — Domaine, tunnel nommé & déploiement web

Objectif : une **URL fixe** pour l'API (webhooks Telegram + WhatsApp qui ne cassent plus) et la
**vitrine** en ligne, le tout sous le domaine parapluie **blackunlimited.online**.

## Schéma retenu (sous-domaines de l'ombrelle)

| Usage | Sous-domaine | Sert |
|---|---|---|
| **Vitrine** (site statique) | `nexmove.blackunlimited.online` | Cloudflare Pages (dossier `web/`) |
| **API / webhooks** (bot) | `api.nexmove.blackunlimited.online` | Tunnel nommé Cloudflare → VPS `127.0.0.1:8000` |

> ✅ Oui, un **sous-domaine de blackunlimited.online suffit** — pas besoin d'acheter `nexmove.online`.
> La zone `blackunlimited.online` doit juste être **active dans ton compte Cloudflare** (Websites → Add a site).

---

## Partie A — Tunnel nommé (URL fixe pour le bot)

À faire **sur le VPS**, avec ton compte non-sudo. `cloudflared` doit être installé (binaire dans `~/bin` si besoin).

### 1. Authentifier cloudflared (une fois)
```bash
cloudflared tunnel login
```
Ça ouvre un lien : connecte-toi à Cloudflare et **choisis la zone `blackunlimited.online`**.
Un certificat est écrit dans `~/.cloudflared/cert.pem`.

### 2. Créer le tunnel (une fois)
```bash
cloudflared tunnel create nexmove
```
Ça crée un identifiant `<TUNNEL_ID>` + un fichier de credentials `~/.cloudflared/<TUNNEL_ID>.json`.

### 3. Configurer l'ingress
Crée `~/.cloudflared/config.yml` :
```yaml
tunnel: nexmove
credentials-file: /home/TON_USER/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: api.nexmove.blackunlimited.online
    service: http://localhost:8000
  - service: http_status:404
```
(remplace `TON_USER` et `<TUNNEL_ID>`).

### 4. Router le DNS (une fois)
```bash
cloudflared tunnel route dns nexmove api.nexmove.blackunlimited.online
```
Ça crée automatiquement l'enregistrement DNS (CNAME proxifié) dans Cloudflare.

### 5. Lancer en continu (auto-restart, non-sudo)
```bash
setsid nohup ~/infra/nexmove-src/scripts/nexmove-named-tunnel.sh >/tmp/nexmove-tunnel.log 2>&1 &
# et au démarrage du VPS :
(crontab -l 2>/dev/null; echo "@reboot ~/infra/nexmove-src/scripts/nexmove-named-tunnel.sh >/tmp/nexmove-tunnel.log 2>&1") | crontab -
```

### 6. Vérifier
```bash
curl -s https://api.nexmove.blackunlimited.online/health
# doit renvoyer le JSON de version de l'API
```

> Le tunnel nommé garde **toujours la même URL**. On abandonne l'ancien `scripts/nexmove-tunnel.sh`
> (tunnel rapide `*.trycloudflare.com` qui changeait à chaque redémarrage).

---

## Partie B — Enregistrer les webhooks (UNE seule fois)

Comme l'URL est fixe, ces commandes ne sont à passer **qu'une fois**.

### Telegram
Depuis le bot en admin : `/setwebhook https://api.nexmove.blackunlimited.online/webhook/telegram`
(ou en curl) :
```bash
source ~/infra/forge-nex-api/.env
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook" \
  -d url="https://api.nexmove.blackunlimited.online/webhook/telegram" \
  -d secret_token="${TELEGRAM_WEBHOOK_SECRET}" \
  -d allowed_updates='["message","edited_message","callback_query"]'
```

### WhatsApp
Se fait côté **Meta** (voir docs/GUIDE-WHATSAPP.md §6) :
- Callback URL : `https://api.nexmove.blackunlimited.online/webhook/whatsapp`
- Verify token : la valeur de `WHATSAPP_VERIFY_TOKEN` (défaut `nexmove_verify`)
- Cocher le champ **messages**.

---

## Partie C — Vitrine sur Cloudflare Pages

1. Cloudflare Dashboard → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**.
2. Choisis le dépôt `blvckx-chk/nexmove`, branche `main` (ou celle de prod).
3. **Build settings** : Framework preset = *None*, Build command = *(vide)*, **Build output directory = `web`**.
4. Deploy. Tu obtiens une URL `*.pages.dev`.
5. **Custom domain** → ajoute `nexmove.blackunlimited.online` (Cloudflare crée le DNS tout seul).

La vitrine pointe déjà vers le bot (`t.me/nex_move_bot`) et vers les pages légales
(`/cgu.html`, `/confidentialite.html`, `/mentions.html`).

> Alternative : héberger la vitrine sur le VPS. Déconseillé — Cloudflare Pages est gratuit, rapide,
> et **reste en ligne même si le bot est en maintenance** (les pages légales restent accessibles).

---

## Récap de l'ordre à suivre
1. Zone `blackunlimited.online` active dans Cloudflare.
2. Partie A (tunnel nommé) → `api.nexmove.blackunlimited.online` répond.
3. Partie B Telegram → le bot est stable.
4. Partie C (Pages) → `nexmove.blackunlimited.online` en ligne.
5. Meta WhatsApp (GUIDE-WHATSAPP.md) → webhook + numéro.
