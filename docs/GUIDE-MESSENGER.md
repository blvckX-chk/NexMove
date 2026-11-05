# Guide — activer NexMove sur Facebook Messenger

Le code Messenger est **déjà prêt** (endpoints `/webhook/messenger`, signature Meta,
envoi texte/menu/documents). Il n'y a **rien à coder** : il suffit de configurer
l'app Meta et de mettre le token dans `.env`.

Valeurs propres à NexMove :
- **Callback URL (webhook)** : `https://api-nexmove.blvckunlimited.space/webhook/messenger`
- **Verify token** : `nexmove_verify`  _(= `MESSENGER_VERIFY_TOKEN`, défaut)_

---

## Prérequis
1. Une **Page Facebook** (en créer une si besoin : facebook.com/pages/create).
2. L'app Meta **« NexMove »** (déjà créée pour WhatsApp, App ID 1590553112520815)
   sur https://developers.facebook.com → *Mes apps*.

## Étapes (dans developers.facebook.com → ton app)

### 1. Ajouter le produit Messenger
*Add products to your app* → **Messenger** → *Set up*.

### 2. Lier ta Page et générer le token
Messenger → **Settings / Paramètres** → section *Access Tokens* :
- *Add/Connect a Page* → choisis ta Page → autorise.
- **Génère le Page Access Token** → **c'est la valeur de `MESSENGER_TOKEN`**.
  (⚠️ c'est un token de PAGE, pas un token utilisateur.)

### 3. Configurer le webhook
Messenger → Settings → *Webhooks* → **Add Callback URL** :
- Callback URL : `https://api-nexmove.blvckunlimited.space/webhook/messenger`
- Verify Token : `nexmove_verify`
- Clique *Verify and Save* (ça appelle le GET du serveur → doit réussir).

### 4. Abonner la Page aux événements
Toujours dans *Webhooks* → *Add subscriptions* pour **ta Page** → coche au minimum :
- **messages**
- **messaging_postbacks**

### 5. Renseigner le serveur (`.env`)
Dans le dossier de déploiement (`~/infra/forge-nex-api/.env` ou équivalent) :
```
MESSENGER_TOKEN=<le Page Access Token de l'étape 2>
MESSENGER_VERIFY_TOKEN=nexmove_verify
META_APP_SECRET=<App Secret de l'app Meta>   # recommandé : vérifie la signature des webhooks
```
> `META_APP_SECRET` est le même pour WhatsApp et Messenger (c'est l'app secret de l'app Meta,
> dans *Paramètres → De base*). Sans lui, le webhook accepte tout (OK en test, à mettre en prod).

### 6. Redéployer et vérifier
```
cd ~/infra/nexmove-src && ./scripts/deploy.sh
```
Vérifie : `/api/admin/health` (clé admin) doit montrer `"messenger_configured": true`.

### 7. Tester
Depuis un compte **admin ou testeur de l'app**, envoie un message à ta Page Facebook.
Le bot doit répondre. (En mode *Développement*, seuls les rôles de l'app peuvent écrire.)

---

## Passage au public (tous les utilisateurs)
En mode *Développement*, seuls les **admins/testeurs** de l'app peuvent parler au bot.
Pour ouvrir à tout le monde :
- Mets l'app en **Live / Production**.
- Demande l'**App Review** pour la permission **`pages_messaging`** (Meta te demande une
  vidéo de démo + description de l'usage). Tant que ce n'est pas approuvé, seuls les rôles
  de l'app peuvent écrire.

## Dépannage
- **La vérif du webhook échoue** → l'URL n'est pas joignable en HTTPS, ou le verify token
  ne correspond pas à `MESSENGER_VERIFY_TOKEN`. Teste : ouvre l'URL `/health` dans un navigateur.
- **Le bot ne répond pas** → (a) la Page n'est pas abonnée au champ `messages` ;
  (b) `MESSENGER_TOKEN` absent/erroné ; (c) tu écris depuis un compte sans rôle sur l'app (mode dev) ;
  (d) `META_APP_SECRET` erroné → signatures rejetées (regarde les logs : « signature invalide »).
- **Logs** : `cd <dossier-deploiement> && docker compose logs --tail=50`.

### ⭐ Test décisif : « les logs montrent GET mais jamais POST »
C'est LE symptôme « Meta ne livre rien ». Dans 9 cas sur 10 : **la Page n'est pas abonnée à l'app**.
Attention, il y a DEUX abonnements différents, et il faut **les deux** :
1. **App → Webhooks** : s'abonner aux *champs* `messages` + `messaging_postbacks` (puis cliquer **Confirmer**).
2. **App → Messenger → Paramètres API** : *abonner la PAGE à l'app* (bouton **Ajouter des abonnements** / **Subscribe** à côté du nom de la Page). ← **l'étape le plus souvent oubliée.**

Vérifie l'abonnement de la Page en une commande (remplace `PAGE_TOKEN`) :
```bash
curl -s "https://graph.facebook.com/v21.0/me/subscribed_apps?access_token=PAGE_TOKEN"
```
- Réponse `{"data": []}` → la Page **n'est pas abonnée** : abonne-la (bouton ci-dessus) ou en API :
```bash
curl -s -X POST "https://graph.facebook.com/v21.0/me/subscribed_apps" \
  -d "subscribed_fields=messages,messaging_postbacks" -d "access_token=PAGE_TOKEN"
# attendu : {"success": true}
```
- Réponse avec ton app et `messages` dans `subscribed_fields` → l'abonnement est bon ; regarde alors
  le **mode dev** : en *Développement*, seul un compte **admin/dev/testeur** de l'app peut écrire à la Page.

### Vérifier que le token de Page est le bon
```bash
curl -s "https://graph.facebook.com/v21.0/me?access_token=PAGE_TOKEN"
# doit renvoyer l'ID + le NOM de ta Page NexMove (pas une erreur de token).
```
