# NexMove — Guide de mise en service WhatsApp Cloud API

Le **code est prêt** (channels.py + endpoints webhook + parseur photos/documents/boutons). Il ne reste
qu'à faire la **config côté Meta** — ~30 min. Suis les étapes dans l'ordre.

---

## 0. Ce qui est déjà fait côté NexMove

- ✅ Envoi de messages texte, boutons, PDF/DOCX/images (`wa_text`, `wa_menu`, `wa_document`)
- ✅ Réception : texte, boutons (button_reply / list_reply), documents PDF/Word, **photos** (analyse
  vision Gemini), rejet poli audio/vidéo/sticker
- ✅ Endpoints webhook : `GET /webhook/whatsapp` (verify) et `POST /webhook/whatsapp` (messages)
- ✅ Menus, /commands, procédures, outils, tout fonctionne — c'est le même code métier que Telegram

---

## 1. Créer un compte Meta Developers (5 min)

1. Va sur **https://developers.facebook.com/** → connecte-toi avec ton compte Facebook.
2. Complète ton profil dev (nom, email pro, pays).
3. Accepte les conditions.

---

## 2. Créer une App WhatsApp Business (5 min)

1. Sur **My Apps** → **Create App** → choisis **Business** comme type.
2. Nom de l'app : `NexMove` (ou ce que tu veux). Email de contact.
3. Après création, sur le tableau de l'app → **Add Products** → **WhatsApp** → **Set Up**.
4. Meta te demande de créer/lier un **Meta Business Portfolio** (portefeuille pro) — accepte, remplis ton
   entreprise (peut être un nom perso pour débuter).

---

## 3. Récupérer tes clés (2 min)

Dans le menu gauche → **WhatsApp** → **API Setup**. Tu vois :

- **Access token (temporaire)** — long jeton `EAAxxxxxxxxx...` valable **24 h**. Copie-le → ce sera ton
  `WHATSAPP_TOKEN` pour les tests.
- **Phone number ID** (sous « From ») — un nombre à ~15 chiffres. C'est ton `WHATSAPP_PHONE_ID`.
- **Test number** (colonne « From ») : Meta te fournit un numéro de test gratuit. Ne pas s'en servir pour le
  grand public.

> 🔒 **Pour la production (plus tard)** : il faut un **System User** dans le Business Portfolio → génère
> un **token permanent** avec les permissions `whatsapp_business_messaging` + `whatsapp_business_management`.
> Sans ça, tu devras régénérer le token toutes les 24 h.

---

## 4. Configurer NexMove (2 min)

Sur ton VPS, édite `.env` :

```bash
cd ~/infra/forge-nex-api
nano .env
```

Ajoute (ou remplace) :

```bash
WHATSAPP_TOKEN=EAAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx     # le jeton copié à l'étape 3
WHATSAPP_PHONE_ID=123456789012345                        # le Phone number ID
WHATSAPP_VERIFY_TOKEN=nexmove_verify                     # secret partagé avec Meta (au choix)
```

Puis :

```bash
docker compose up -d --build
curl -s http://localhost:8000/health | python3 -m json.tool | grep whatsapp
# doit afficher : "whatsapp_configured": true
```

---

## 5. Ajouter un testeur (2 min)

Meta bride le numéro de test : seuls les numéros **ajoutés à la whitelist** reçoivent les messages du bot.

- Toujours dans **API Setup** → section **Recipient phone numbers** → **Add phone number**.
- Ajoute ton numéro perso (format international, ex. `+229...`). Meta t'envoie un code par WhatsApp, tu le
  saisis dans l'interface pour confirmer.

---

## 6. Brancher le webhook (5 min) — le point le plus délicat

Meta va **appeler ton API** à chaque message reçu. Il faut lui donner ton URL publique **ngrok** (la même
que pour Telegram).

- Menu gauche → **WhatsApp** → **Configuration** → **Webhook** → **Edit**.
- **Callback URL** : `https://TON-DOMAINE-NGROK/webhook/whatsapp`
  (ex. `https://creation-hydrant-dimple.ngrok-free.dev/webhook/whatsapp`)
- **Verify token** : `nexmove_verify` (exactement la même valeur que `WHATSAPP_VERIFY_TOKEN` dans `.env`)
- Clique **Verify and save**.

Si tu vois « Verified ✓ » → parfait. Sinon → **check `docker logs forge-nex-api | tail`** et vérifie que
ton domaine ngrok est bien joignable de l'extérieur.

Puis, juste en dessous, **Webhook fields** → clique **Manage** et **coche** :
- `messages` ✅ (obligatoire — c'est là que passent les vrais messages)

Optionnels (à ignorer au début) : `message_template_status_update`, `account_update`.

---

## 7. Premier test (1 min)

Depuis ton **compte perso WhatsApp** (le numéro ajouté à l'étape 5) → envoie **« bonjour »** au **numéro
de test** fourni par Meta.

Résultat attendu : le bot te répond avec le message d'accueil (« envoie ton CV… »).

Vérifs :

```bash
docker logs forge-nex-api --tail 20
# tu dois voir "[chat] wa user=..." et pas d'erreur
```

**Teste ensuite** :
- Envoie un PDF (📎 → Document) → analyse OK
- **Envoie une photo de CV** (directement 📸) → analyse via vision Gemini ✅
- Envoie un vocal → réponse polie « je ne traite pas encore les audios »
- Tape `/version` → doit afficher la version

---

## 8. Passer en production (plus tard)

Quand tu es prêt à ouvrir à tout le monde :

1. **Business Verification** (Meta) — vérifie ton entreprise avec des documents.
2. **Numéro WhatsApp perso** → dédié à ton bot (pas le numéro de test).
3. **Token permanent** via System User (voir note § 3).
4. **App Review** — nécessaire pour toucher > 250 users. Meta relit ton flow et valide.
5. **Templates de notifications** — obligatoires pour envoyer un message > 24 h après la dernière interaction
   utilisateur (contrainte Meta). À créer dans **Message Templates**.

---

## Dépannage rapide

| Symptôme | Cause probable | Fix |
|---|---|---|
| Webhook « Verify failed » | `WHATSAPP_VERIFY_TOKEN` ≠ celui saisi sur Meta | Aligner les deux, `docker compose up -d --build` |
| Bot ne répond pas | Numéro pas dans la whitelist (étape 5) | Ajouter le numéro |
| `whatsapp_configured: false` sur `/health` | `.env` pas rechargé | Rebuild : `docker compose up -d --build` |
| Erreur 401 dans les logs | Token expiré (>24 h avec token temp) | Régénérer le token dans API Setup, ou passer au token permanent |
| Erreur 190 | Token invalide/révoqué | Idem — régénérer |
| Photo/CV en photo ignoré | Code < v2.29.0 | Déployer v2.29+ |

---

## Coûts

- **Conversations initiées par l'utilisateur** (les 24 h qui suivent son 1er message) : **gratuites** en
  quantité illimitée sur le tier gratuit Meta.
- **Notifications proactives** (>24 h) : payantes via templates, ~0,01–0,05 € par message selon le pays.
  1 000 premières conversations d'entreprise/mois **gratuites** (tier Meta 2024+).
- Pour tes tests : **0 €** tant que tu restes sur le numéro de test avec ta whitelist.

Voir : https://developers.facebook.com/docs/whatsapp/pricing
