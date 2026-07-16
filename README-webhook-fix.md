# NexMove — Correctif « Provided secret is not valid » (webhook Telegram ↔ n8n)

Ce dossier corrige la boucle qui empêche NexMove de recevoir les messages Telegram,
et fournit les workflows corrigés.

---

## 1. Cause racine (établie)

Flux : **Telegram → n8n (webhook) → FastAPI → n8n → Telegram**, Google Sheets en persistance.

Les workflows WF1 (onboarding) et WF5 (OSINT) utilisent des nœuds **Telegram Trigger**.
À l'activation, n8n enregistre lui-même le webhook côté Telegram via `setWebhook`, avec :

- `url = {WEBHOOK_URL}/webhook/{webhookId}`
- un **`secret_token` généré et stocké par n8n** (dans le volume `/home/node/.n8n`).

Telegram renvoie ensuite ce secret dans l'en-tête `X-Telegram-Bot-Api-Secret-Token`
sur **chaque** update. n8n le compare à celui qu'il a stocké. S'ils diffèrent →
`{"message":"Provided secret is not valid"}`.

### La boucle

1. `WEBHOOK_URL` / `N8N_HOST` pointent vers un tunnel **`trycloudflare` « quick »**, dont
   l'URL **change à chaque redémarrage de `cloudflared`** (limite de conception : un quick
   tunnel gratuit ne peut pas avoir d'URL fixe).
2. L'URL change → l'URL enregistrée côté Telegram devient morte → n8n ne reçoit plus rien.
3. On « rattrape » avec un `setWebhook` **manuel** vers la nouvelle URL. Mais cet appel
   manuel **n'a pas le `secret_token`** que n8n a stocké (ou en met un autre).
4. Telegram envoie désormais un secret que n8n ne reconnaît pas →
   **`Provided secret is not valid`**.

> Le secret cassé est un **symptôme** des `setWebhook` manuels, eux-mêmes **imposés** par
> l'URL qui bouge. Deux fausses pistes déjà écartées : la persistance du volume n8n (OK,
> bind mount rw) et la recréation du conteneur. Le problème est **l'URL publique éphémère**.

---

## 2. Le correctif (principe)

Deux règles suffisent à casser la boucle :

1. **Une URL publique FIXE.** n8n enregistre son webhook une fois pour toutes.
2. **Ne plus JAMAIS appeler `setWebhook` à la main.** C'est n8n qui possède
   l'enregistrement (URL **et** secret). Pour forcer un ré-enregistrement propre, on
   **désactive puis réactive** le workflow dans l'UI n8n — n8n fait alors `deleteWebhook`
   puis `setWebhook` avec **son** secret et l'URL courante.

---

## 3. Obtenir une URL fixe — 3 options

| Option | Quand la choisir | Ce qu'il faut |
|---|---|---|
| **A. Tunnel Cloudflare nommé** (recommandé) | Tu contrôles un domaine sur Cloudflare | Domaine (gratuit sur Cloudflare), aucun port ouvert, TLS auto, hostname stable |
| **B. ngrok domaine statique** | Tu n'as **pas** de domaine | Compte ngrok (1 domaine statique gratuit) |
| **C. Reverse proxy VPS + domaine** | Tu as déjà domaine + ports 80/443 ouverts sur le VPS | Caddy/nginx + Let's Encrypt |

Dans **tous les cas**, le hostname obtenu devient `N8N_PUBLIC_HOST` et alimente les
4 variables n8n ci-dessous.

### Variables n8n communes (indispensables)

```
N8N_HOST=<hostname-fixe>
N8N_PROTOCOL=https
WEBHOOK_URL=https://<hostname-fixe>/
N8N_EDITOR_BASE_URL=https://<hostname-fixe>/
```

> Les 4 doivent pointer vers **le même** hostname stable. `WEBHOOK_URL` est celle qui
> détermine l'URL envoyée à Telegram.

### Option A — Cloudflare nommé (fichiers fournis)

1. Cloudflare **Zero Trust → Networks → Tunnels → Create a tunnel** (type *Cloudflared*).
2. Copier le **token** du tunnel → `.env` (`CLOUDFLARE_TUNNEL_TOKEN`).
3. Ajouter un **Public hostname** : `n8n.mondomaine.com` → **Service** `http://n8n:5678`.
4. `.env` : `N8N_PUBLIC_HOST=n8n.mondomaine.com`, `TELEGRAM_BOT_TOKEN=...`.
5. `docker compose -f infra/docker-compose.n8n.yml --env-file infra/.env up -d`.

Variante par fichier de config (sans dashboard) : voir `infra/cloudflared/config.yml.example`.

### Option B — ngrok statique

```
ngrok config add-authtoken <TOKEN>
ngrok http 5688 --domain=<ton-domaine>.ngrok-free.app   # domaine réservé, stable
```
Puis `N8N_PUBLIC_HOST=<ton-domaine>.ngrok-free.app` et les 4 variables ci-dessus.

### Option C — Reverse proxy (Caddy)

`Caddyfile` :
```
n8n.mondomaine.com {
    reverse_proxy n8n:5678
}
```
DNS `n8n.mondomaine.com` → IP du VPS, ports 80/443 ouverts. Puis les 4 variables.

---

## 4. Procédure de récupération (à faire UNE fois)

Après avoir mis en place l'URL fixe :

```bash
# 1) Repartir d'un état propre côté Telegram (retire tout webhook manuel + son secret)
curl -s "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"

# 2) Redémarrer n8n avec les nouvelles variables (URL fixe)
docker compose -f infra/docker-compose.n8n.yml --env-file infra/.env up -d

# 3) Dans l'UI n8n : DÉSACTIVER puis RÉACTIVER WF1 (et WF5).
#    n8n ré-enregistre alors le webhook avec SON secret vers l'URL FIXE.

# 4) Vérifier : l'URL doit être le hostname fixe, has_custom_certificate=false,
#    last_error_message vide.
curl -s "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

À partir de là : **ne plus jamais** lancer `setWebhook` à la main. Si un jour il faut
re-synchroniser, on passe **uniquement** par le toggle désactiver/réactiver dans n8n.

---

## 5. Workflows corrigés (`workflows/`)

Repris des exports v4, avec corrections :

**WF1 — Onboarding Telegram**
- 🐛 **Bug bloquant corrigé** : le nœud `📤 Envoyer Telegram` référençait
  `$('Parser Message')` alors que le nœud s'appelle `🔍 Parser Message` (avec emoji).
  n8n résout les nœuds par nom exact → *« Referenced node doesn't exist »* à chaque
  message. Corrigé en `$('🔍 Parser Message')`.
- 🔐 **Secret retiré du JSON** : le **token du bot Telegram était codé en dur** dans les
  URLs `getFile` / `Download CV`. Remplacé par `{{ $env.TELEGRAM_BOT_TOKEN }}`
  (fourni via l'environnement n8n — voir `.env.example` et le compose). Le token qui
  figurait dans l'export doit être considéré comme **compromis** : le **révoquer via
  @BotFather** (`/revoke`) et mettre le nouveau dans `TELEGRAM_BOT_TOKEN`.
  > Nécessite `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` (déjà dans le compose).

**WF0 / WF5** : inchangés fonctionnellement (aucun token en dur, pas de bug de
référence). Fournis pour garder l'ensemble cohérent et versionné.

### Point de vigilance (non modifié — à confirmer côté FastAPI)

Dans WF1, `💾 Sauvegarder Session` lit `$json.session_row.*`. Or il est placé **après**
`📤 Envoyer Telegram`, dont la sortie est la réponse de l'API Telegram (pas `session_row`).
Selon la forme réelle des réponses de `/api/chat` et `/api/chat-cv`, `session_row` peut être
`undefined` à ce stade. Si la persistance des sessions échoue, il faudra référencer le nœud
FastAPI en amont (`$('🤖 Forge NEX Chat')` / `$('🤖 Forge NEX Chat-CV')`) plutôt que `$json`.
Je ne l'ai pas modifié faute d'accès au code FastAPI pour confirmer le schéma de réponse.

---

## 6. Checklist de validation

- [ ] `getWebhookInfo` montre le **hostname fixe** (pas une URL trycloudflare).
- [ ] `last_error_message` vide, `pending_update_count` qui décroît.
- [ ] Un message Telegram simple déclenche WF1 sans `Provided secret is not valid`.
- [ ] Un envoi de CV (PDF) traverse `getFile` → `download` → `/api/chat-cv` → réponse Telegram.
- [ ] Après un redémarrage de la stack, l'URL **n'a pas changé** et tout refonctionne
      **sans** intervention manuelle.
- [ ] Ancien token Telegram **révoqué**, nouveau token uniquement dans `.env`.
