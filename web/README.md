# NexMove — Vitrine web (site statique)

Une page d'accueil + 3 pages légales, **sans dépendance ni build**. Objectif : confiance, SEO,
hébergement des pages légales, et un seul lien à partager qui renvoie vers le bot.

## Fichiers
- `index.html` — landing page (hero, fonctions, comment ça marche, prix, FAQ, CTA).
- `confidentialite.html` — politique de confidentialité / RGPD.
- `cgu.html` — conditions générales d'utilisation.
- `mentions.html` — mentions légales.
- `legal.css` — style commun aux pages légales.

Palette et typographie : identité validée (bleu `#2F5BFF`, bleu nuit `#0B1B4D`, ambre `#FFB020`,
police Inter). Compatible mode clair et sombre. Responsive (mobile d'abord).

## Avant de publier — 2 choses à faire
1. **Lien du bot** : dans `index.html`, remplace `TON_BOT` par le username de ton bot (sans `@`) :
   ```html
   <body data-bot="TON_BOT">   →   <body data-bot="NexMoveBot">
   ```
   Tous les boutons « Démarrer » pointeront automatiquement vers `https://t.me/<ton_bot>`.
2. **Champs légaux** : remplace toutes les mentions surlignées `[À COMPLÉTER]` dans les 3 pages
   légales (email de contact, adresse, immatriculation, hébergeur, directeur de publication, date,
   juridiction). Ce sont des modèles — fais-les relire si besoin, ce n'est pas un avis juridique.

## Publier gratuitement (au choix)
- **Cloudflare Pages** : connecte ce dépôt, dossier racine `web/`, aucune commande de build.
- **GitHub Pages** : Settings → Pages → publie le dossier `web/` (ou déplace-le à la racine d'un dépôt dédié).
- **Netlify** : glisse-dépose le dossier `web/`, ou connecte le dépôt (publish directory = `web`).

Puis pointe ton domaine (ex. `nexmove.app`) vers l'hébergement. Le même domaine peut servir de
tunnel nommé Cloudflare pour le bot (voir `docs/LANCEMENT-PRODUCTION.md`).

## À faire produire ensuite (hors code)
- Vrai logo + favicon (le SVG intégré est un placeholder « N/flèche » ; brief dans `docs/IDENTITE-NEXMOVE.md`).
- Captures d'écran réelles du bot pour illustrer les fonctions.
- Un ou deux vrais témoignages (avec accord écrit).
