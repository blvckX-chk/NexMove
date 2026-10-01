# NexMove — Cahier des charges

> Projet **blvckUnlimited**. Document markdown neutre (le design/PDF sera réalisé séparément). Version
> applicative de référence : **v2.39.0**. Ce document décrit le système actuel **et** la feuille de route
> produit — y compris les ajouts essentiels et innovants prévus pour en faire une plateforme d'emploi et de
> mobilité de référence, augmentée par l'IA.

---

## 1. Vision & ambition

NexMove est un **assistant d'emploi, d'orientation et de mobilité augmenté par l'IA**, délivré par
messagerie (Telegram, bientôt WhatsApp), destiné en priorité aux **francophones d'Afrique de l'Ouest**
(Bénin en tête). Il couvre **toute la chaîne** d'un candidat :

1. comprendre son profil (analyse de CV + bilan d'orientation, ou création de CV s'il n'en a pas) ;
2. trouver de **vraies** opportunités adaptées (emplois, stages, bourses, fellowships — **locales ET
   internationales**) ;
3. préparer ses **dossiers** (CV, lettre, projet d'études) ;
4. être **accompagné pas à pas** (Campus France, Canada, visa…) et **ne jamais rater une deadline** ;
5. **réussir ses entretiens et démarches** (coaching, guidage par capture d'écran).

**Ambition :** devenir la **couche IA de l'emploi et de la mobilité en Afrique francophone** — d'abord un
assistant candidat, puis une **marketplace deux faces** (candidats ↔ recruteurs/écoles), puis une
**infrastructure** (données, API, agents autonomes). Principe directeur : on **parle en langage naturel** ;
les commandes ne sont qu'un raccourci.

## 2. Public cible

- Étudiants et jeunes diplômés francophones (Bénin, UEMOA, Cameroun).
- Chercheurs d'emploi/stage, **local** comme diaspora.
- Candidats à la mobilité (Campus France, Canada, visas).
- **Segment clé sous-servi** : personnes **sans CV** ni méthode (le bot leur en crée un).

## 3. Périmètre fonctionnel (existant)

### 3.1 Canaux
| Canal | État |
|---|---|
| **Telegram** | En production (via n8n WF1 comme transport) |
| **WhatsApp Cloud API** | Code prêt — config Meta en cours |
| **Messenger** | Code prêt — config Meta non entamée |

Couche canal unifiée : `deliver_text` / `deliver_menu` / `deliver_file` selon `session["channel"]`.

### 3.2 Onboarding
- Machine à états déterministe : `WELCOME → ATTENTE_CV → CV_RECU → PREFERENCES → CONFIRMATION → ACTIF`.
- **Accueil non rigide** : répond aux questions d'ouverture avant de réclamer le CV.
- **Analyse de CV multi-format** : PDF (texte + OCR), DOCX, image/photo (vision).
- **Sans CV** : création guidée en 5 questions → profil structuré + **CV PDF généré**.
- **Questions adaptatives** : le plan dépend des réponses (pas de nationalité/financement d'études pour un
  job local).
- **Repli du nom** depuis le nom de fichier si l'IA ne le détecte pas.

### 3.3 Recherche d'opportunités
- `/veille`, `/mobilite <pays/domaine>` ; grounding web (Tavily) + matching sémantique + feedback appris.
- **Sources structurées** (type + scope local/intl) + **filtrage adaptatif** ; **alertes mots-clés** ;
  **digest** quotidien/hebdo.

### 3.4 Accompagnement & procédures
- Campus France + suivi 8 étapes ; 6 procédures FR (Parcoursup, MonMaster, eCandidat, DAP, Visa, Recours).
- `/canada` avec **rondes Entrée express IRCC en temps réel** ; `/procedure <pays>`, `/eligibilite`.
- **`/guide`** (guidage par capture d'écran, vision) ; **`/simulation`** (entretien blanc + bilan).

### 3.5 Documents & outils
- `/dossier`, `/postuler` (CV + lettre + projet, PDF **et** Word) ; outils PDF ; **`/timeline`** (feuille de
  route en image PNG).

### 3.6 Espace personnel & données
- `/profil`, `/status`, **`/moncode` + `/moi <code>`** (profil persistant, portable), `/supprimer` (RGPD),
  `/contact`, `/version`.

### 3.7 Quotas & rôles
- Quotas journaliers pour les gratuits sur les options coûteuses ; **admin illimité**. Socle prêt pour un
  **tier premium** payant (voir §6).

## 4. Architecture technique

```
Utilisateur ─(Telegram/WhatsApp/Messenger)→ Webhook → n8n WF1 (transport) → FastAPI (TOUTE la logique)
                                                                              ├─ SQLite (sessions, offres,
                                                                              │   candidatures, profils,
                                                                              │   usage, cache, sources)
                                                                              ├─ Tavily (grounding web)
                                                                              ├─ LLM multi-fournisseurs
                                                                              │   (Cerebras → Groq → Gemini,
                                                                              │    fallback auto ; vision +
                                                                              │    embeddings)
                                                                              └─ Envoi direct au canal
n8n : WF1 (transport Telegram), WF0 (planificateur veille /api/collect)
```

- **FastAPI** (`api/main.py`) = 100 % de la logique + envoi des messages.
- Modules : `db.py` (persistance), `llm.py` (IA/vision/embeddings), `http_client.py`, `channels.py`.
- Déploiement VPS : Docker, conteneur `forge-nex-api`, port 8000, volume `./data` (SQLite).

## 5. Modèle de données (SQLite)

`sessions`, `offres`, `candidatures`, `sources_offres` (+ scope), `feedback`, `contacts`, `profiles` +
`profile_versions` + `profile_user_map`, `usage` (quotas), `cache`.
**À venir** : `premium_codes`, `tiers` (abonnements), `recruteurs`/`offres_partenaires` (marketplace),
`skills`/`badges` (évaluation), `events` (analytics).

## 6. Exigences non-fonctionnelles

- **Fiabilité IA** : router multi-fournisseurs, bascule automatique, modèles configurables par env.
- **Robustesse** : garde-fous sur chaque entrée ; replis (OCR, banque de questions, profil manuel) ; aucun
  crash au démarrage (imports tolérants).
- **Qualité** : **127 tests**, CI GitHub Actions (lint, compile, pytest, smoke Docker).
- **Langue & ton** : 100 % français, tutoiement, chaleureux et concret.
- **Confidentialité** : `.env` non versionné ; `/supprimer` (RGPD) ; profils portables par code.
- **Scalabilité** (cible) : passer de SQLite mono-fichier à une base gérée (Postgres) quand le volume
  l'exige ; observabilité (logs, métriques, erreurs).

---

## 7. État d'avancement (synthèse)

- **Fait / déployé** : onboarding (CV multi-format, adaptatif, accueil non rigide, création de CV sans CV),
  recherche (veille, sources structurées + filtrage, alertes, digest, feedback appris, matching sémantique),
  accompagnement complet (Campus France + 8 étapes, 6 procédures FR, Canada temps réel, guide par capture,
  simulation), documents (CV/lettre/projet, outils PDF, timeline PNG), espace perso (profil persistant,
  status/gamification, contact, RGPD), quotas + admin. **Telegram en production.**
- **Priorités en cours (déjà décidées)** :
  1. **Enrichir & améliorer les sources d'offres** (surtout locales Bénin/UEMOA) ;
  2. **Optimiser la conversation** (réponses libres encore plus naturelles).
- **En cours (infra)** : **WhatsApp** (config compte Meta).

---

## 8. Feuille de route & innovations futures

_Priorités : **P0** = en cours · **P1** = prochain socle · **P2** = différenciation forte · **P3** = vision.
Les deux priorités déjà actées (sources, conversation) ne sont pas répétées ici._

### 8.1 P1 — Monétisation & socle de croissance (essentiel)
- **Système premium & paiement** : codes d'activation (`/premium <code>`), tiers **Free/Premium/Pro/VIP**,
  `/monabo` (statut/échéance), génération de lots de codes, intégration **Chariow / Mobile Money**.
  Réutilise l'infra quotas + admin. *(Détails business : `MONETISATION.md`.)*
- **Notes vocales (audio in/out)** : comprendre un message **vocal** (transcription) et répondre en vocal —
  **accessibilité majeure** pour une cible qui préfère souvent parler qu'écrire.
- **Rappels de deadline fins** (J‑30 / J‑7 / J‑1) par dossier ; relances de réabonnement.
- **Tableau de bord / analytics** (candidat + interne) : suivi de progression, métriques d'usage.
- **Migration base** (Postgres) et **observabilité** quand le volume l'impose.

### 8.2 P2 — IA augmentée & différenciation
- **Score prédictif d'admissibilité / de chances** : estimer les chances (admission, visa, bourse, poste) et
  expliquer **quoi améliorer** pour les augmenter.
- **Candidature assistée / auto-apply** : l'agent **pré-remplit et propose** des candidatures (avec
  validation de l'utilisateur), suit les réponses, relance.
- **Évaluation & badges de compétences** : mini-tests IA → **compétences vérifiées** valorisables auprès des
  recruteurs (données propriétaires).
- **Coach de carrière longitudinal** : plan de **montée en compétences** personnalisé (formations,
  certifications) et suivi dans le temps.
- **Préparation aux tests de langue** (TCF/TEF/IELTS) : entraînement IA + estimation de niveau.
- **Générateur de portfolio / mini-site** personnel à partir du profil.
- **Vérification de documents/diplômes** (authenticité, cohérence) pour la confiance côté recruteurs.

### 8.3 P2 — Marketplace deux faces (candidats ↔ recruteurs/écoles)
- **Espace recruteurs/écoles** : publier des offres/programmes ; **matching IA** candidat ↔ opportunité.
- **Sourcing inversé** : proposer aux recruteurs des candidats pertinents (avec consentement).
- **B2B / marque blanche** : déploiement pour écoles, agences, ONG, institutions (licences volume).

### 8.4 P3 — Élargissement & vision
- **Multilingue** : anglais (ouvre l'Afrique anglophone), puis **langues locales** (fon, yoruba…) pour
  l'inclusion.
- **Agents autonomes** : veille + candidature + négociation semi-autonomes, sous contrôle de l'utilisateur.
- **Communauté & mentorat** : mise en relation pairs/alumni/mentors.
- **Intégrations** : dépôt assisté sur portails officiels, calendrier, e-mail, API partenaires (écoles,
  assurances étudiantes, banques, opérateurs).
- **Effet de données** : chaque interaction améliore le matching → **avantage cumulatif** difficile à copier.

### 8.5 Table de priorisation
| Priorité | Chantier | Valeur | Effort | Dépendance |
|---|---|---|---|---|
| P0 | Sources d'offres (local) + conversation | Rétention/valeur | Moyen | — |
| P1 | Premium & paiement (Chariow) | **Revenu** | Faible | — |
| P1 | Notes vocales (audio) | Accessibilité/portée | Moyen | STT/TTS |
| P1 | Rappels fins + analytics | Rétention | Faible | — |
| P2 | Score d'admissibilité | Différenciation | Moyen | Données |
| P2 | Auto-apply assisté | Différenciation forte | Élevé | Intégrations |
| P2 | Badges de compétences | Données propriétaires | Moyen | Éval IA |
| P2 | Marketplace recruteurs | **Scale/B2B** | Élevé | Base recruteurs |
| P3 | Multilingue / agents / communauté | Vision | Élevé | Socle mûr |

## 9. Facteurs clés de succès & risques

- **Succès** : exécution rapide, premières **preuves** (admis/boursiers/embauchés), distribution (contenu +
  partenariats), **récurrence** (habitude via veille/alertes), **effet de données**.
- **Risques** : dépendance canal (Meta/Telegram/n8n) → multi-canal + données propriétaires ; qualité IA →
  grounding + garde-fous + relecture humaine premium ; pouvoir d'achat → prix bas + Mobile Money ;
  concurrence/copie → vitesse + marque + B2B + données ; coûts LLM → router + quotas (déjà en place).

---

_Documents liés : `MONETISATION.md` (business), `SPECIFICATIONS.md` / `ANALYSE-TECHNIQUE.md` (détail
technique), `GUIDE-WHATSAPP.md`, `MISE-A-JOUR-SERVEUR.md`._
