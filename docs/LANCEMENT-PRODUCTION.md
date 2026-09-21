# NexMove — Pack de mise en production & campagne de lancement

> Projet **blvckUnlimited**. Document markdown (design/PDF à réaliser séparément). Version applicative de
> référence : **v2.49.0**. Ce document réunit : l'état actuel, l'identité de marque (propositions à valider),
> le positionnement/messaging, les offres, le plan de lancement, les assets à produire, les pages légales,
> et la recommandation sur le web.
>
> ⚠️ Je n'ai pas ta charte graphique existante : les éléments d'identité ci-dessous sont des **propositions
> de départ à valider/ajuster**, pas des choix arrêtés.

---

## 1. État actuel du produit (prêt à lancer)

**Canal :** Telegram en production (webhook natif direct, sans n8n). WhatsApp & Messenger : code prêt,
config Meta à finaliser.

**Fonctionnalités livrées :**
- **Profil** : analyse de CV multi-format (PDF/Word/photo), création de CV guidée sans CV (`/creercv`),
  onboarding adaptatif, **notes vocales** (le bot comprend l'audio).
- **Conversation** : comprend n'importe quelle question (IA), pas de mots-clés imposés.
- **Opportunités** : `/veille`, `/mobilite`, sources locales Bénin/UEMOA + internationales, alertes mots-clés,
  digest, matching sémantique, feedback appris.
- **Évaluation** : `/chances` (admissibilité visa/bourse/admission), **`/compatibilite`** (score par
  compétence).
- **Accompagnement** : Campus France + 8 étapes, 6 procédures FR, Canada (rondes IRCC temps réel),
  `/guide` (captures d'écran), `/simulation` (entretien blanc).
- **Documents & suivi** : `/dossier`, `/postuler` (CV + lettre + projet, PDF & Word), outils PDF,
  `/timeline` (PNG), **pipeline de candidatures** (`/mescandidatures`).
- **Compte** : profil persistant (`/moncode`/`/moi`), `/supprimer` (RGPD), `/contact`.
- **Monétisation** : abonnements Premium/Pro + **codes d'activation** (`/premium`, `/gencodes`), **quotas**
  par tier, **parrainage** (`/parrainage`).
- **Exploitation** : alertes de disponibilité (`/api/selfcheck` + ping démarrage), tunnel auto-réparant,
  API en localhost (sécurité).

**Qualité :** 170 tests verts, CI (lint + compile + pytest + smoke Docker).

## 2. À finaliser AVANT le lancement (checklist technique)

- [ ] **Domaine** acheté + ajouté à Cloudflare → **tunnel nommé** (URL fixe) → `setWebhook` une fois.
- [ ] `.env` : **`TELEGRAM_WEBHOOK_SECRET`** (sécurité), **`BOT_USERNAME`** (liens de parrainage),
      `ADMIN_CHAT_ID`, clés LLM (Gemini/Groq — recharger/retirer Cerebras si hors crédit), `TAVILY_API_KEY`.
- [ ] **Boutique Chariow** : 3 produits pour démarrer (Guide 2 000 · Pack Dossier 19 900 · Premium 3 500/mois)
      + livraison des **codes** générés via `/gencodes`.
- [ ] **Pages légales** publiées (CGU, Confidentialité/RGPD, Mentions) — voir §8.
- [ ] **Mini-vitrine web** (une page) publiée — voir §9.
- [ ] Surveillance : cron `/api/selfcheck` (5 min) + moniteur externe (UptimeRobot) sur `/health`.
- [ ] Jeu de **codes premium de test** + parcours d'achat Chariow testé de bout en bout.

## 3. Identité de marque (propositions à valider)

- **Nom produit :** NexMove — *Nex* (next, ton prochain move) + *Move* (mobilité). Court, international,
  prononçable en français.
- **Éditeur :** blvckUnlimited (à afficher discrètement : « un produit blvckUnlimited »).
- **Baseline / tagline (choisir une)** :
  1. « *Ton prochain move commence ici.* »
  2. « *De ton CV à ton visa — dans ta poche.* »
  3. « *L'IA qui te fait avancer : études, emploi, mobilité.* »
- **Promesse :** un conseiller d'emploi et de mobilité par IA, en français, abordable, dans la messagerie.
- **Ton de voix :** chaleureux, direct, tutoiement, concret, honnête (jamais faussement vendeur), fier
  d'être africain et tourné vers le monde.
- **Palette (proposition)** : un **bleu/teal confiant** (mouvement, fiabilité) + un **accent chaud**
  (orange/ambre = énergie, opportunité) sur fond clair ; décliner une version sombre. *(À aligner avec
  blvckUnlimited si tu veux une continuité noir/or.)*
- **Typographie :** une sans-serif géométrique lisible (ex. Inter/Poppins) pour les titres, système pour le
  corps.
- **Logo :** direction « flèche/mouvement » intégrée au *N* ou au *M* (idée de progression), déclinable en
  favicon et en photo de profil du bot. *(À faire produire par un designer ; je peux te livrer une maquette
  de vitrine où tester des variantes.)*
- **À éviter :** jargon RH occidental, promesses de « job garanti », visuels génériques de stock.

## 4. Positionnement & messaging

- **Pitch (1 phrase) :** « NexMove est ton assistant IA de mobilité et d'emploi sur WhatsApp/Telegram :
  il analyse ton profil, trouve de vraies opportunités (locales et à l'étranger), prépare tes dossiers et
  t'accompagne jusqu'au départ — en français, à prix juste. »
- **Value props (3) :**
  1. *Tout au même endroit* — du CV à l'entretien au visa, sans app à installer.
  2. *Vraies opportunités, local ET international* — pas juste des offres génériques.
  3. *Abordable & accessible* — Mobile Money, même à la voix, même sans CV.
- **Différenciation (vs KaizenJob & agences)** : cf. `MONETISATION.md §3` et l'audit — intégration bout-en-bout,
  localisation francophone Afrique de l'Ouest, canal messagerie, mobilité (Campus France/Canada/visa),
  simulation d'entretien, notes vocales, prix disruptif.
- **Personas :** (a) étudiant qui veut partir étudier (Campus France) ; (b) jeune diplômé en recherche
  d'emploi local/diaspora ; (c) candidat mobilité Canada ; (d) personne sans CV ni méthode.
- **Messages par persona** : un accroche + un bénéfice concret + un CTA « Démarre gratuitement ».

## 5. Offres & prix (rappel, cf. MONETISATION.md)

- **Gratuit** (aimant) · **Premium 3 500 FCFA/mois** · **Pro 8 900 FCFA/mois** · **Packs one-shot**
  (Dossier Campus France 19 900, Chasseur de bourses 14 900, etc.) · **VIP conciergerie**.
- **Leviers de conversion :** quotas gratuits qui poussent au Premium, parrainage (essai gratuit du Premium),
  garantie « admissible ou remboursé » sur le pack Dossier, tarif de lancement −40 %.
- **À ajouter (roadmap, cf. audit) :** packs de **crédits fongibles** (pic d'usage sans abonnement).

## 6. Acquisition & calendrier de lancement (30 jours)

**Canaux (par ROI) :** TikTok/Reels/Shorts (témoignages « admis à… / bourse obtenue », démos du bot) ·
groupes & statuts WhatsApp étudiants · **partenariats écoles/cybercafés** · **ambassadeurs campus** (rémunérés
en % ou Premium) · parrainage intégré · SEO (articles « procédure Campus France Bénin 2026 »).

- **J-7 → J0 (pré-lancement)** : vitrine + légales en ligne, boutique Chariow prête, 10 vidéos courtes
  tournées, 3–5 ambassadeurs recrutés, liste d'attente (lien Telegram).
- **J0 (lancement)** : annonce multi-canal, tarif lancement −40 %, activation du parrainage.
- **J1 → J14** : 1 vidéo/jour, collecte des **premiers témoignages** (admis/boursiers/embauchés), A/B du prix.
- **J15 → J30** : 1 partenariat école signé, optimisation du tunnel de vente, préparation WhatsApp.
- **KPIs hebdo :** nouveaux utilisateurs, taux d'onboarding complété, conversion free→payant, MRR, CAC,
  parrainages activés.

## 7. Assets à produire (checklist)

- [ ] Logo (couleur + monochrome) + favicon + **photo de profil du bot** Telegram/WhatsApp.
- [ ] Bannière + 5 visuels réseaux (formats carré/vertical).
- [ ] **3–5 vidéos démo** (30–60 s) : « CV analysé », « trouver une bourse », « /simulation entretien »,
      « /chances », « /guide capture ».
- [ ] Captures d'écran propres (mode clair) pour la vitrine et Chariow.
- [ ] FAQ (10 questions) + 3 témoignages (même informels au début).
- [ ] Page de vente Chariow par produit (promesse + contenu + prix + garantie).
- [ ] Kit ambassadeur (1 page : quoi dire, lien de parrainage, visuels).

## 8. Pages légales (indispensable pour B2B, Meta/WhatsApp, confiance)

- [ ] **CGU** (conditions d'utilisation).
- [ ] **Politique de confidentialité / RGPD** : données collectées (CV, préférences), finalité
      (accompagnement), conservation, droit à l'effacement (`/supprimer`), pas de revente, sous-traitants
      (fournisseurs LLM). *NB : nécessaire aussi pour l'App Review WhatsApp.*
- [ ] **Mentions légales / éditeur** : blvckUnlimited + contact.
- [ ] Lien vers ces pages depuis la vitrine et depuis `/contact` du bot.
> Je peux te **rédiger des modèles** de ces 3 pages (adaptés au Bénin/UEMOA + RGPD) quand tu veux.

## 9. Faut-il un accès web ? — Recommandation

**Oui à une mini-vitrine. Non à un dashboard web complet.** Détail :

| Besoin | Décision | Pourquoi |
|---|---|---|
| **Landing page publique** (1 page : ce que fait le bot, prix, FAQ, témoignages, gros bouton « Démarrer sur Telegram/WhatsApp ») | ✅ **OUI** | Crédibilité/confiance (les gens vérifient avant de payer), SEO/découvrabilité, cible des pubs, **héberge les pages légales**, un seul lien à partager. Coût quasi nul (hébergement statique gratuit : Cloudflare Pages / GitHub Pages / Netlify). |
| **Pages légales** | ✅ OUI | Confiance + exigence Meta/B2B (cf. §8). |
| **Dashboard web / app SaaS** (comme KaizenJob) | ❌ **NON (pour l'instant)** | Diluerait ton avantage « zéro app, tout dans la messagerie + Mobile Money », coûte cher à construire/maintenir, et ta cible vit sur WhatsApp, pas sur un portail web. À reconsidérer seulement pour le **B2B** (espace écoles/recruteurs) plus tard. |

**En clair :** le web sert de **vitrine + point de confiance + porte d'entrée vers le bot**, pas de produit.
KaizenJob a un dashboard parce que son marché (Occident, carte bancaire) l'attend ; ton marché récompense la
simplicité messagerie. Fais la vitrine, garde le produit dans le chat.

> 💡 Je peux te **générer la mini-vitrine** (page HTML responsive, bilingue possible, bouton vers ton bot)
> prête à héberger — dis-moi le nom du bot et la tagline retenue.

## 10. Go / No-Go de lancement (résumé)

Prêt à lancer quand : domaine+tunnel nommé ✅ · secret webhook ✅ · Chariow (3 produits + codes) ✅ · pages
légales ✅ · vitrine ✅ · surveillance ✅ · parcours d'achat testé ✅ · 10 vidéos + 3 ambassadeurs ✅.

---

_Documents liés : `CAHIER-DES-CHARGES.md`, `MONETISATION.md`, `AUDIT-KAIZENJOB-VS-NEXMOVE.md`,
`WEBHOOK-TELEGRAM-DIRECT.md`, `MISE-A-JOUR-SERVEUR.md`, `GUIDE-WHATSAPP.md`._
