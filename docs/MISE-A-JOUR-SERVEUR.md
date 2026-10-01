# NexMove — Mettre à jour le serveur (VPS)

Tout le code est sur GitHub. Pour déployer une nouvelle version, on **récupère depuis GitHub** et on
**reconstruit le conteneur** — aucun fichier à copier à la main.

Branche de travail actuelle : `claude/nexmove-webhook-url-fix-07sjec` (version applicative **v2.38.0**).

---

## 1. Se connecter au VPS et aller dans le dossier de déploiement

```bash
ssh <ton-user>@<ton-serveur>
cd ~/infra/forge-nex-api
```

## 2. Récupérer la dernière version depuis GitHub

```bash
# Voir sur quelle branche pointe le déploiement
git branch --show-current
git status

# Récupérer les nouveautés
git fetch origin
git checkout claude/nexmove-webhook-url-fix-07sjec   # si pas déjà dessus
git pull origin claude/nexmove-webhook-url-fix-07sjec
```

> Si `git status` montre des fichiers modifiés localement qui bloquent le pull (ex. `.env` — normalement
> ignoré), mets-les de côté : `git stash`, fais le pull, puis `git stash pop` si besoin. Ne touche jamais
> au `.env` (il contient tes clés) — il n'est pas versionné.

## 3. Reconstruire et relancer le conteneur

```bash
docker compose up -d --build
```

## 4. Vérifier que la nouvelle version tourne

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

Tu dois voir :

```json
{
  "status": "ok",
  "version": "2.38.0",
  ...
}
```

Et dans un chat Telegram, la commande `/version` doit afficher **2.38.0**.

## 5. Vérifier les logs (optionnel)

```bash
docker logs forge-nex-api --tail 30
```

Pas d'erreur `ModuleNotFoundError` ni de trace au démarrage = tout va bien.

---

## Nouveautés à tester après cette mise à jour (Telegram)

| Commande | Ce que ça fait |
|---|---|
| Onboarding | Ne demande **plus la nationalité** pour un stage/job **local** (objectif « travailler » + ton pays) |
| `/moncode` · `/moi <code>` | Sauvegarde / restauration du profil par code (portage inter-appareils/canaux) |
| `/guide` | Envoie une **capture d'écran** d'une plateforme → guidage étape par étape (vision) |
| `/canada` | Affiche les **dernières rondes Entrée express IRCC en temps réel** |
| `/simulation` | Entretien blanc interactif (campus france / visa / emploi) |
| `/alerte <mot>` | Alertes mots-clés — les offres qui matchent remontent en tête (🔔) |
| `/timeline` | **Feuille de route en image PNG** (étapes Campus France + échéances) |

## Variables d'environnement optionnelles (`.env`)

Tout a un défaut raisonnable ; à ajuster seulement si besoin :

```bash
# Quotas gratuits (l'admin ADMIN_CHAT_ID est illimité)
FREE_CV_DAILY=8            # analyses de CV / jour / utilisateur gratuit
FREE_GUIDE_DAILY=12        # captures /guide / jour / utilisateur gratuit
SIM_MAX_QUESTIONS=5        # questions par /simulation

# Sources de veille
ENABLE_RELIEFWEB=1         # active la source ReliefWeb (ONG/humanitaire)
SOURCE_FEEDS_EXTRA=https://exemple.com/feed/,https://autre.com/rss   # flux RSS en plus

# IRCC (par défaut = open data officiel, à ne changer que si l'URL évolue)
IRCC_ROUNDS_URL=https://www.canada.ca/content/dam/ircc/documents/json/ee_rounds_123_en.json
```

Après modification du `.env` : `docker compose up -d --build` pour recharger.

---

## Rappel : mettre à jour ≠ pousser

- **Toi (serveur)** : tu fais `git pull` pour **récupérer** le code (lecture seule).
- **Moi (Claude)** : je fais `git push` pour **publier** le code sur GitHub.

Donc à chaque fois que je te dis « c'est poussé », il te suffit de refaire les étapes **2 → 4** ci-dessus.
