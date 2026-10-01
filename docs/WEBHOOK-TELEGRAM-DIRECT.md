# NexMove — Passer au webhook Telegram natif (retirer n8n)

Objectif : **Telegram parle directement à l'API** (`/webhook/telegram`), sans n8n. Ça supprime la cause
n°1 des coupures (workflow n8n désactivé, webhook effacé, bug « undefined » du nœud fichier).

Il reste **une seule** chose à avoir : une **URL publique stable** qui pointe sur l'API (port 8000).

---

## Étape 1 — Une URL publique stable pour l'API

Choisis **une** option :

### Option A (recommandée, gratuite, définitive) : Cloudflare Tunnel
URL fixe, HTTPS, pas de changement au redémarrage (contrairement à ngrok gratuit).
```bash
# installe cloudflared (une fois)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
# tunnel rapide vers l'API (URL en *.trycloudflare.com, stable tant que le process tourne)
cloudflared tunnel --url http://localhost:8000
```
Pour une URL **permanente** avec ton propre domaine : `cloudflared tunnel login` puis crée un tunnel nommé
(doc Cloudflare). Lance-le en service systemd pour qu'il survive aux reboots.

### Option B : ton ngrok actuel, mais pointé sur l'API (port 8000)
Si tu gardes ngrok, fais-le pointer sur `8000` (l'API) au lieu du port n8n. Idéalement un **domaine réservé**
ngrok (payant) pour une URL fixe.

> Note ton URL publique, ex. `https://nexmove.exemple.com` ou `https://xxxx.trycloudflare.com`.

## Étape 2 — (Recommandé) un secret de webhook

Dans `~/infra/forge-nex-api/.env` :
```bash
TELEGRAM_WEBHOOK_SECRET=un_secret_long_au_hasard
```
L'API n'acceptera que les requêtes Telegram portant ce secret (protège contre les faux updates).
Puis `docker compose up -d --build`.

## Étape 3 — Pointer Telegram sur l'API

Le plus simple, **depuis le bot en tant qu'admin** :
```
/setwebhook https://TON-URL-PUBLIQUE
```
→ le bot appelle Telegram `setWebhook` sur `https://TON-URL-PUBLIQUE/webhook/telegram` (avec le secret si
configuré) et retire les updates en attente.

Vérifie :
```
/webhookinfo
```
→ `url` doit afficher `…/webhook/telegram`, `dernière erreur : aucune`.

(Équivalent en ligne de commande si tu préfères :
```bash
TOKEN=$(grep -E '^TELEGRAM_TOKEN=' .env | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
curl -s "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  -d url="https://TON-URL-PUBLIQUE/webhook/telegram" \
  -d secret_token="$(grep -E '^TELEGRAM_WEBHOOK_SECRET=' .env | cut -d= -f2-)" \
  -d drop_pending_updates=true
```)

## Étape 4 — Tester puis débrancher n8n

1. Envoie un **message texte** → réponse OK.
2. Envoie un **CV PDF** → tu reçois l'analyse (le bug « chat not found » disparaît : l'API lit elle-même le
   `chat.id`).
3. Teste un **bouton** (menu) et une **photo**.

Quand tout marche, tu peux **désactiver le workflow n8n forge-nex-wf1** (il ne sert plus au Telegram). n8n
peut rester pour d'autres usages (planificateur de veille WF0), mais **le bot n'en dépend plus**.

---

## Revenir en arrière (si besoin)
Réactive le workflow n8n et refais son `setWebhook` (ou via l'interface n8n en réactivant le workflow).
Rien n'est perdu : l'endpoint natif et le chemin n8n peuvent coexister.

## Pourquoi c'est plus robuste
- **Moins de pièces** : Telegram → (tunnel stable) → API. Plus de n8n entre les deux.
- **Réponse immédiate** : l'API répond 200 à Telegram tout de suite et traite en tâche de fond (pas de
  timeout/retry sur les appels LLM/CV).
- **Alertes** : combiné à `/api/selfcheck` (cron) + le ping de démarrage, tu es prévenu si quoi que ce soit
  tombe.
