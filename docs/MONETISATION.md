# NexMove — Stratégie de monétisation & business plan

> Document de travail (projet blvckUnlimited). Contenu markdown volontairement neutre : le design/PDF sera
> réalisé séparément. Les chiffres de marché et d'unit economics sont des **hypothèses de travail à valider**,
> pas des données arrêtées.
>
> Repère de conversion : **1 € ≈ 656 FCFA (XOF)**. Prix pensés « valeur du résultat ».

---

## 1. Résumé exécutif

NexMove est un **assistant d'emploi, d'orientation et de mobilité augmenté par l'IA**, livré là où sa cible
est déjà : **la messagerie** (Telegram aujourd'hui, WhatsApp demain). Il couvre toute la chaîne de valeur
d'un candidat — **comprendre son profil → trouver de vraies opportunités (locales et internationales) →
préparer ses dossiers → réussir ses entretiens et ses démarches (Campus France, visa, immigration)** — sans
application à installer, en français, avec paiement mobile.

**Thèse d'investissement :** en Afrique de l'Ouest francophone, l'accompagnement à l'emploi et à la mobilité
est soit **cher et humain** (agences, consultants à 100 000–1 000 000 FCFA), soit **gratuit mais générique
et fragmenté** (portails officiels, groupes WhatsApp). NexMove occupe le **milieu manquant** : un
accompagnement **personnalisé, instantané, abordable et scalable** grâce à l'IA. Le modèle est un
**freemium** (déjà en place techniquement via les quotas) qui convertit vers un **abonnement récurrent** et
des **packs à résultat**, distribués via **Chariow** (Mobile Money).

**Objectif 18 mois :** devenir la **référence de l'emploi et de la mobilité par IA en Afrique francophone**,
puis s'étendre au marché anglophone et au **B2B** (écoles, agences, ONG, institutions).

---

## 2. Le marché

### 2.1 Cible primaire
- **Étudiants et jeunes diplômés** francophones (Bénin, puis UEMOA + Cameroun) : orientation, bourses,
  études à l'étranger.
- **Chercheurs d'emploi/stage** (local et diaspora) : CV, veille, candidatures.
- **Candidats à la mobilité** : Campus France, Canada (Entrée express), visas.
- **Segment sous-servi clé** : ceux **sans CV** ni méthode — NexMove leur en crée un.

### 2.2 Taille (hypothèses à valider — TAM / SAM / SOM)
- **TAM** : jeunes 18–35 ans connectés en Afrique de l'Ouest francophone + Cameroun ≈ **plusieurs dizaines
  de millions**.
- **SAM** : ceux activement en recherche d'emploi/études/mobilité et prêts à payer un service digital ≈
  **quelques millions**.
- **SOM 12–18 mois** (réaliste, Bénin + 1–2 pays) : **50 000–150 000 utilisateurs** touchés, dont
  **3–7 % payants**.
> Action : valider ces bornes avec des données réelles (Campus France, INSAE Bénin, opérateurs mobiles).

### 2.3 Tendances porteuses
- **Chômage des jeunes élevé** + forte **envie de mobilité** (études/emploi à l'étranger).
- **Adoption massive de WhatsApp/Telegram** et du **Mobile Money** (MTN, Moov, Orange, Wave).
- **Vague IA générative** : attente d'outils « qui font à ta place », mais **peu d'offres localisées** en
  français pour cette cible.

---

## 3. Analyse concurrentielle (honnête) & différenciation

Il **existe** de la concurrence — la prétendre inexistante serait une erreur stratégique. Mais **personne ne
combine** tout ce que fait NexMove pour **cette cible précise**. Le vide, c'est **l'intégration + la
localisation + le canal messagerie + le prix**.

| Catégorie | Exemples | Leur limite pour ta cible |
|---|---|---|
| Portails officiels | Campus France, MonMaster, IRCC | Gratuits mais **génériques, non personnalisés**, aucun accompagnement |
| Agences / consultants | agences de placement, consultants visa | **Chers** (100k–1M FCFA), non scalables, qualité variable |
| CV/interview builders | Zety, Enhancv, Final Round AI, Google Interview Warmup | **Anglophones**, orientés Occident, **paiement carte**, pas de mobilité africaine |
| Agrégateurs de bourses | Opportunity Desk, Scholars4dev | **Info brute**, pas de matching ni de dossier |
| Job boards | LinkedIn, Jobberman, Novojob, Emploi.bj | **Offres seules**, ni CV ni coaching ni mobilité |
| Groupes WhatsApp/Telegram | canaux d'entraide | **Bruit, non fiable**, non personnalisé |

### 3.1 Le moat (avantage défendable) de NexMove
1. **Intégration bout‑en‑bout** : orientation → opportunités → dossier → entretien → visa, **en un seul fil
   de discussion**. Personne d'autre ne fait la chaîne complète.
2. **Localisation profonde** : français, réalités béninoises/UEMOA, Campus France, **Mobile Money**,
   opportunités **locales ET internationales**.
3. **Canal natif** : **zéro app à installer**, ça vit dans WhatsApp/Telegram — friction minimale.
4. **IA augmentée + données propriétaires** : chaque interaction enrichit les **profils persistants** et le
   **feedback appris** → matching qui **s'améliore avec l'usage** (effet de données).
5. **Prix disruptif** : 1/20 à 1/100 du prix d'une agence, pour un service disponible 24/7.
6. **Vitesse** : instantané vs jours/semaines côté agences.

> **Positionnement (proposition, à valider par blvckUnlimited) :** *« Ton conseiller d'emploi et de mobilité,
> dans ta poche — de ton CV à ton visa, en français, à prix juste. »*

---

## 4. Modèle économique (multi-revenus)

1. **Freemium → Abonnement (récurrent)** — le cœur : ARPU stable, LTV élevée.
2. **Packs one-shot à résultat** (Chariow) — panier moyen élevé, conversion émotionnelle.
3. **Services premium done-for-you** (VIP conciergerie) — forte marge, preuve/témoignages.
4. **B2B / institutionnel** — écoles, agences, ONG, gouvernements (licences/volume) — **le vrai scale**.
5. **Affiliation / partenariats** — écoles, assurances étudiantes, banques, opérateurs télécom, tests de
   langue (commission d'apport).

---

## 5. Architecture d'offre (3 étages + B2B)

| Étage | Rôle stratégique |
|---|---|
| **Gratuit** (aimant) | Acquisition + preuve de valeur (1 CV, bilan, aperçu veille) |
| **Premium / Pro** (abonnement) | **Revenu récurrent** — quotas illimités, veille quotidienne, alertes, simulation |
| **Packs & VIP** (one-shot) | Panier élevé sur un **résultat daté** (dossier, bourse, entretien) |
| **B2B** (licences) | Volume — établissements & institutions déploient NexMove pour leurs publics |

---

## 6. Catalogue de produits — Chariow (B2C)

Chaque produit = **une promesse + une échéance + une preuve**. Livraison : **code d'activation** (le bot
débloque le contenu/le tier) — voir §11.

| # | Produit | Promesse (résultat) | Contenu livré | Prix FCFA | € |
|---|---|---|---|---|---|
| 1 | **Guide « Réussir Campus France 2026 »** (tripwire) | Comprendre toute la procédure | eBook PDF + checklist + 7 j Premium | **2 000** | ~3 |
| 2 | **Pack CV + Lettre qui décrochent** | Un CV + LM pro ciblés | Génération illimitée 7 j (PDF+Word) + 3 modèles | **6 500** | ~10 |
| 3 | **Pack Dossier Campus France complet** | Dossier prêt à déposer | CV + projet d'études + liste docs + suivi 8 étapes + relecture | **19 900** | ~30 |
| 4 | **Pack Chasseur de bourses (90 j)** | Ne rater aucune bourse | Veille quotidienne + alertes ciblées 3 mois | **14 900** | ~23 |
| 5 | **Pack Prépa entretien** | Réussir l'entretien (Campus France/visa/emploi) | /simulation illimité + grille de score + bilan écrit | **9 900** | ~15 |
| 6 | **Pack Cap Canada** | Savoir si/comment partir au Canada | Analyse Entrée express + feuille de route + docs | **12 900** | ~20 |
| 7 | **Pack Décrocher un emploi/stage (60 j)** | Trouver + candidater efficacement | Veille + CV/LM illimités + coaching candidature | **12 900** | ~20 |
| 8 | 👑 **VIP Conciergerie** (done-for-you) | On monte ton dossier avec toi | Accompagnement humain + tout inclus + priorité | **75 000–150 000** | 115–230 |

**Offre d'ancrage — Bundle « Tout-en-un Mobilité »** : tous les packs 1–7 + 3 mois Premium →
**39 900 FCFA (~60 €)**. Elle rend chaque pack « pas cher » par comparaison.

---

## 7. Abonnements (récurrent — priorité n°1)

| | **Gratuit** | **Premium** | **Pro** |
|---|---|---|---|
| Prix mensuel | 0 | **3 500 FCFA** (~5 €) | **8 900 FCFA** (~13 €) |
| Trimestre (−15 %) | — | 8 900 | 22 500 |
| Annuel (−30 %) | — | 29 400 | 74 700 |
| CV analysés | 1 / jour | illimité | illimité |
| Création de CV guidée | 1 | illimité | illimité |
| Veille opportunités | à la demande | **quotidienne auto** | quotidienne + **sources premium** |
| Alertes mots-clés | 1 | 10 | illimité |
| /guide (captures) | 3 / jour | illimité | illimité |
| /simulation entretien | 1 | illimité | illimité + **bilan écrit** |
| CV + lettre | — | illimité | illimité + **relecture humaine** |
| Support | communautaire | prioritaire | prioritaire + conseiller |

**Logique de prix :** Premium calé sur « le prix d'un ou deux repas/mois » pour un service quotidien →
faible friction, forte perception d'usage. Pro pour les candidats « sérieux » en pleine démarche.

---

## 8. Order bumps, upsells, bundles (augmentent le panier de 20–40 %)

- **Order bump** (case à cocher au paiement du Pack CV, +2 000 FCFA) : « Traduction pro du CV en anglais ».
- **Upsell post-achat** (tout pack) : « Passe en Premium à **−50 % le 1er mois** ».
- **Down-sell** (abandon panier) : le **Guide à 2 000 FCFA** (tripwire).
- **Cross-sell** : après Dossier Campus France → **Prépa entretien** ; après veille → **Pack candidature**.
- **Parrainage** : « Invite 2 amis → 1 mois Premium offert » (boucle virale).

---

## 9. Tunnel de vente (funnel) & acquisition

**Aimant gratuit** (bot + eBook) → **Tripwire 2 000 F** → **Offre cœur** (Dossier / Premium) →
**Récurrent** (abonnement) → **Fort ticket** (VIP / B2B).

### Canaux d'acquisition (par ordre de ROI attendu)
1. **Contenu court vidéo** (TikTok, Reels, YouTube Shorts) : témoignages « admis à… / bourse obtenue »,
   démos du bot, mini-tutos Campus France/visa. **Le canal n°1** pour cette cible.
2. **Groupes WhatsApp/Telegram étudiants** + statuts WhatsApp.
3. **Partenariats écoles, universités, cybercafés, associations étudiantes** (co-branding, commission).
4. **Ambassadeurs campus** (étudiants rémunérés en % ou en Premium).
5. **Bouche-à-oreille / parrainage** intégré au produit.
6. **SEO/notoriété** : articles « procédure Campus France Bénin 2026 », etc.

---

## 10. Rétention & récurrence (le nerf de la guerre)

L'abonnement ne vaut que si les gens **restent**. Leviers :
- **Valeur récurrente réelle** : la **veille quotidienne** et les **alertes** donnent une raison de revenir
  chaque jour (habitude).
- **Gamification** (déjà en place : progression, feuille de route /timeline) → sentiment d'avancer.
- **Relances intelligentes** : rappels de deadlines de dossiers, « 3 nouvelles bourses pour toi ».
- **Onboarding qui délivre vite** une 1re victoire (CV généré, 1re offre pertinente).
- **Cible churn < 8 %/mois** au départ, à améliorer vers 4–5 %.

---

## 11. Le pont technique Chariow ↔ bot (indispensable — à coder)

Chariow encaisse (Mobile Money/carte) et **délivre un contenu** après paiement. Pour vendre du premium, il
faut relier l'achat au déblocage dans le bot :

- Table **`premium_codes`** (code, tier, durée, statut, acheteur, date).
- Commande **`/premium <CODE>`** : valide le code → passe l'utilisateur en **Premium/Pro** jusqu'à
  l'échéance (saute les quotas, active les fonctions payantes).
- **Génération de lots de codes** (export CSV) → tu les charges sur Chariow comme « produit numérique »
  (livraison auto d'un code unique par vente).
- Commande **`/monabo`** : statut, tier, date d'expiration ; relance J‑3 avant échéance (réabonnement).
- Un flag **`tier`** par session (free/premium/pro/vip) réutilise l'infra **quotas + admin** déjà en place.

> **Effort estimé : ~1 journée de dev.** C'est le déclencheur qui transforme le bot en machine à vendre.

---

## 12. B2B / institutionnel (le vrai levier de scale)

Au-delà du B2C, le volume vient des **organisations qui ont déjà l'audience** :
- **Écoles & universités** : licence pour accompagner leurs étudiants (orientation, stages, mobilité).
- **Agences de placement / cabinets** : NexMove en marque blanche ou en outil interne.
- **ONG, programmes jeunesse, coopération** (emploi des jeunes) : déploiement subventionné.
- **Institutions publiques** (agences emploi, ministères) : accès de masse.
- **Modèle** : licence annuelle par volume d'utilisateurs, ou par siège conseiller, + setup.
> Un seul contrat institutionnel peut peser plus que des milliers d'abonnés B2C.

---

## 13. Unit economics & métriques (cibles à instrumenter)

| Indicateur | Définition | Cible de départ |
|---|---|---|
| **Conversion free → payant** | % d'utilisateurs qui paient | 3–7 % |
| **ARPU** | revenu moyen / utilisateur payant / mois | ~3 500–5 000 FCFA |
| **CAC** | coût d'acquisition d'un client | < 1 mois d'abonnement (via organique/parrainage) |
| **LTV** | valeur vie client | ≥ 3× CAC |
| **Churn mensuel** | % d'abonnés perdus / mois | < 8 % (→ 4–5 %) |
| **MRR** | revenu récurrent mensuel | à suivre chaque semaine |

**Illustration (hypothèse) :** 5 000 abonnés Premium à 3 500 FCFA → **17,5 M FCFA/mois** (~26 700 €) de MRR,
hors packs et B2B. À instrumenter dès le lancement.

---

## 14. Roadmap de lancement (90 jours)

- **Jours 0–15** : coder le **système de codes premium** + `/monabo` ; créer la boutique Chariow ; définir
  la grille de prix de lancement (−40 % early).
- **Jours 15–30** : produire l'**eBook tripwire** + 10 vidéos courtes ; recruter 3–5 **ambassadeurs campus**.
- **Jours 30–60** : lancement public ; activer **parrainage** ; premiers **témoignages** (admis/boursiers).
- **Jours 60–90** : optimiser le funnel (A/B prix), ouvrir **1 partenariat école**, préparer WhatsApp pour
  élargir l'acquisition.
- **KPIs de lancement** : nb d'utilisateurs, conversion free→payant, MRR, CAC, taux de complétion onboarding.

---

## 15. Risques & mitigations

| Risque | Mitigation |
|---|---|
| Faible pouvoir d'achat | Prix bas + Mobile Money + paiement fractionné/packs d'entrée |
| Dépendance à un canal (Telegram/WhatsApp/Meta) | Multi-canal + collecte d'e-mails/numéros propriétaires |
| Qualité IA / hallucinations | Grounding web réel + garde-fous + relecture humaine sur le premium |
| Concurrence / copie | Vitesse d'exécution + effet de données (profils/feedback) + marque + B2B |
| Confiance (arnaques fréquentes) | Preuves sociales, garantie « admissible ou remboursé », transparence |
| Coûts LLM | Router multi-fournisseurs + quotas + modèles configurables (déjà en place) |

---

## 16. Vision — « la meilleure startup d'emploi du 21e siècle, augmentée par l'IA »

De l'outil d'accompagnement vers une **plateforme d'emploi et de mobilité intelligente** :
1. **Aujourd'hui** : assistant personnel (candidat) — orientation, opportunités, dossiers, entretiens.
2. **Demain (marketplace 2 faces)** : côté **candidats** ET côté **recruteurs/écoles** — matching IA
   candidat ↔ poste/programme, candidature assistée, vérification de profils.
3. **Après-demain (infrastructure)** : la **couche IA de l'emploi et de la mobilité en Afrique
   francophone** — données propriétaires, API partenaires, agents autonomes qui candidatent et négocient
   pour l'utilisateur.

**Ce qui rend la vision crédible :** le produit délivre déjà de la valeur, l'infra (freemium/quotas/profils
persistants/feedback appris) est posée, et le canal (messagerie + Mobile Money) est le bon pour la cible.
Le facteur décisif sera l'**exécution** : rapidité, preuves, distribution.

---

## 17. Prochaine étape recommandée

1. **Coder le système de codes premium** (`/premium`, tiers, `/monabo`) → vendre dès la semaine prochaine.
2. **Monter la boutique Chariow** (3 produits pour démarrer : Guide 2 000, Pack Dossier 19 900, Premium
   mensuel 3 500) et tester la conversion avant d'élargir.
3. **Instrumenter les métriques** (conversion, MRR, churn) dès le jour 1.
