# NexMove — Domaine, tunnel nommé & déploiement web

Objectif : une **URL fixe** pour l'API (webhooks Telegram + WhatsApp qui ne cassent plus) et la
**vitrine** en ligne, le tout sous le domaine parapluie **blvckunlimited.space**.

## Schéma retenu (sous-domaines de l'ombrelle)

| Usage | Sous-domaine | Sert |
|---|---|---|
| **Vitrine** (site statique) | `nexmove.blvckunlimited.space` | Cloudflare Pages (dossier `web/`) |
| **API / webhooks** (bot) | `api.nexmove.blvckunlimited.space` | Tunnel nommé Cloudflare → VPS `127.0.0.1:8000` |

> ✅ Un **sous-domaine de blvckunlimited.space suffit** — pas besoin d'un domaine séparé pour NexMove.
> Le domaine est chez **Namecheap** : il faut le **rattacher à Cloudflare** (changer les nameservers), voir §0.

---

## Partie 0 — Rattacher blvckunlimited.space (Namecheap) à Cloudflare

Ton domaine est acheté chez **Namecheap**, mais pour utiliser le tunnel nommé et Cloudflare Pages, la
**zone DNS doit être gérée par Cloudflare**. Ça se fait une fois (~10 min + propagation).

1. **Cloudflare** (compte gratuit) → **Add a site** → saisis `blvckunlimited.space` → plan **Free**.
2. Cloudflare scanne tes DNS existants et t'affiche **2 nameservers** du type
   `xxx.ns.cloudflare.com` et `yyy.ns.cloudflare.com`. **Note-les.**
3. **Namecheap** → *Domain List* → `blvckunlimited.space` → **Manage** → section **Nameservers** →
   choisis **Custom DNS** → colle les **2 nameservers Cloudflare** → **enregistre** (la coche verte).
4. Reviens sur Cloudflare et clique **Done, check nameservers**. La propagation prend de quelques minutes
   à quelques heures ; tu reçois un mail « blvckunlimited.space is now active on Cloudflare ».

> ⚠️ Une fois sur Cloudflare, gère **tous** tes DNS depuis Cloudflare (plus depuis Namecheap).
> Si tu as déjà des enregistrements (mail, etc.), recopie-les dans Cloudflare avant de basculer.

### Les sous-domaines : tu n'as (presque) rien à créer à la main
- `api.nexmove.blvckunlimited.space` → **créé automatiquement** par la commande
  `cloudflared tunnel route dns` (Partie A, étape 4). Ne le crée pas toi-même.
- `nexmove.blvckunlimited.space` → **créé automatiquement** quand tu ajoutes le *Custom domain* dans
  Cloudflare Pages (Partie C, étape 5).

Autrement dit : rattache le domaine (Partie 0), puis les sous-domaines apparaissent tout seuls aux
Parties A et C. Un sous-domaine Cloudflare = un simple enregistrement **CNAME** (tu peux aussi en créer
manuellement dans **DNS → Records → Add record** si besoin).

---

## Partie A — Tunnel nommé (URL fixe pour le bot)

À faire **sur le VPS**, avec ton compte non-sudo. `cloudflared` doit être installé (binaire dans `~/bin` si besoin).

### 1. Authentifier cloudflared (une fois)
```bash
cloudflared tunnel login
```
Ça ouvre un lien : connecte-toi à Cloudflare et **choisis la zone `blvckunlimited.space`**.
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
  - hostname: api.nexmove.blvckunlimited.space
    service: http://localhost:8000
  - service: http_status:404
```
(remplace `TON_USER` et `<TUNNEL_ID>`).

### 4. Router le DNS (une fois)
```bash
cloudflared tunnel route dns nexmove api.nexmove.blvckunlimited.space
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
curl -s https://api.nexmove.blvckunlimited.space/health
# doit renvoyer le JSON de version de l'API
```

> Le tunnel nommé garde **toujours la même URL**. On abandonne l'ancien `scripts/nexmove-tunnel.sh`
> (tunnel rapide `*.trycloudflare.com` qui changeait à chaque redémarrage).

---

## Partie B — Enregistrer les webhooks (UNE seule fois)

Comme l'URL est fixe, ces commandes ne sont à passer **qu'une fois**.

### Telegram
Depuis le bot en admin : `/setwebhook https://api.nexmove.blvckunlimited.space/webhook/telegram`
(ou en curl) :
```bash
source ~/infra/forge-nex-api/.env
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook" \
  -d url="https://api.nexmove.blvckunlimited.space/webhook/telegram" \
  -d secret_token="${TELEGRAM_WEBHOOK_SECRET}" \
  -d allowed_updates='["message","edited_message","callback_query"]'
```

### WhatsApp
Se fait côté **Meta** (voir docs/GUIDE-WHATSAPP.md §6) :
- Callback URL : `https://api.nexmove.blvckunlimited.space/webhook/whatsapp`
- Verify token : la valeur de `WHATSAPP_VERIFY_TOKEN` (défaut `nexmove_verify`)
- Cocher le champ **messages**.

---

## Partie C — Vitrine sur Cloudflare Pages

1. Cloudflare Dashboard → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**.
2. Choisis le dépôt `blvckx-chk/nexmove`, branche `main` (ou celle de prod).
3. **Build settings** : Framework preset = *None*, Build command = *(vide)*, **Build output directory = `web`**.
4. Deploy. Tu obtiens une URL `*.pages.dev`.
5. **Custom domain** → ajoute `nexmove.blvckunlimited.space` (Cloudflare crée le DNS tout seul).

La vitrine pointe déjà vers le bot (`t.me/nex_move_bot`) et vers les pages légales
(`/cgu.html`, `/confidentialite.html`, `/mentions.html`).

> Alternative : héberger la vitrine sur le VPS. Déconseillé — Cloudflare Pages est gratuit, rapide,
> et **reste en ligne même si le bot est en maintenance** (les pages légales restent accessibles).

---

## Récap de l'ordre à suivre
0. Partie 0 → rattacher `blvckunlimited.space` (Namecheap) à Cloudflare (changer les nameservers).
1. Partie A (tunnel nommé) → `api.nexmove.blvckunlimited.space` répond.
2. Partie B Telegram → le bot est stable.
3. Partie C (Pages) → `nexmove.blvckunlimited.space` en ligne.
4. Meta WhatsApp (GUIDE-WHATSAPP.md) → webhook + numéro.
