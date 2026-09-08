# NexMove — Cahier des charges

_Version applicative de référence : **v2.39.0**. Ce document décrit le système tel qu'il est aujourd'hui
et ce qui reste à faire. Il fait foi comme spécification produit ; le détail technique vit dans le code et
dans `SPECIFICATIONS.md` / `ANALYSE-TECHNIQUE.md`._

---

## 1. Vision & objectif

NexMove est un **assistant IA de mobilité et d'orientation** délivré par messagerie, destiné en priorité aux
**francophones d'Afrique de l'Ouest** (Bénin en tête). Il aide chaque utilisateur à **saisir sa prochaine
opportunité — chez lui ou à l'étranger** :

1. comprendre son profil (analyse de CV + bilan d'orientation) ;
2. trouver de **vraies** opportunités adaptées (emplois, stages, bourses, fellowships — **locales ET
   internationales**) ;
3. préparer ses **dossiers** (CV, lettre de motivation, projet d'études) ;
4. être **accompagné pas à pas** (Campus France, Canada, visa…) et **ne jamais rater une deadline**.

Principe directeur : on **parle en langage naturel** ; les commandes ne sont qu'un raccourci.

## 2. Public cible

- Étudiants et jeunes diplômés francophones (Bénin, Afrique de l'Ouest).
- Personnes en recherche d'emploi/stage **local** comme à l'international.
- Candidats à la mobilité (études en France via Campus France, immigration Canada, etc.).
- Utilisateurs **sans CV** (le bot leur en crée un).

## 3. Périmètre fonctionnel

### 3.1 Canaux
| Canal | État |
|---|---|
| **Telegram** | ✅ En production (via n8n WF1 comme transport) |
| **WhatsApp Cloud API** | 🟡 Code prêt — config côté Meta en cours (bloqué à la création du compte dev) |
| **Messenger** | 🟡 Code prêt — config Meta non entamée |

Couche canal unifiée : `deliver_text` / `deliver_menu` / `deliver_file` routent selon `session["channel"]`.

### 3.2 Onboarding
- Machine à états déterministe : `WELCOME → ATTENTE_CV → CV_RECU → PREFERENCES → CONFIRMATION → ACTIF`.
- **Accueil non rigide** : répond aux questions d'ouverture (« à quoi tu sers », salutations) avant de
  réclamer le CV.
- **Analyse de CV multi-format** : PDF (texte + OCR), DOCX, image/photo (vision Gemini).
- **Sans CV** : création guidée en 5 questions → profil structuré + **CV PDF généré**.
- **Questions adaptatives** : le plan de questions dépend des réponses (ex. pas de nationalité/passeport ni
  financement d'études pour un stage/job local).
- **Repli du nom** depuis le nom de fichier si l'IA ne le détecte pas.

### 3.3 Recherche d'opportunités
- `/veille` (opportunités adaptées au profil), `/mobilite <pays/domaine>` (recherche ciblée).
- Grounding web réel (Tavily) + matching sémantique (embeddings Gemini) + feedback appris 👍/👎.
- **Sources structurées** : catalogue taggé (type bourse/emploi/fellowship/ONG ; scope local/intl/both),
  activable par flag d'env ; **filtrage adaptatif** au profil (le local n'est pas noyé sous l'international).
- APIs emploi : Arbeitnow, Adzuna (si clés) ; flux RSS bourses/jeunesse ; EURAXESS/ReliefWeb optionnels.
- **Alertes mots-clés** (`/alerte`) : les offres qui matchent remontent en tête (🔔).
- **Digest proactif** quotidien/hebdo (`/rappels`, `/digest`).

### 3.4 Accompagnement & procédures
- 🇫🇷 `/campusfrance`, `/parcours` + `/etape` (suivi Campus France en 8 étapes), `/ecoles`, `/logement`,
  `/entretien`, `/budget`.
- Procédures FR parallèles : `/parcoursup`, `/monmaster`, `/ecandidat`, `/dap`, `/visa`, `/recours`.
- 🇨🇦 `/canada` avec **rondes Entrée express IRCC en temps réel** (open data, cache 6 h).
- `/procedure <pays>` (Belgique, Allemagne, Suisse, Luxembourg, Pays-Bas…), `/eligibilite <cible>`.
- 🧭 **`/guide`** : l'utilisateur envoie une capture d'écran d'une plateforme → guidage étape par étape (vision).
- 🎤 **`/simulation`** : entretien blanc interactif (Campus France / visa / emploi) avec bilan.

### 3.5 Génération de documents & outils
- `/dossier <cible>` (documents requis + CV + projet d'études), `/postuler <cible>` (CV + lettre) — PDF **et** Word.
- Outils PDF : `/compresser`, `/fusionner`, `/enpdf`, `/decouper`, `/traduire`.
- 🗺️ **`/timeline`** : feuille de route visuelle **en image PNG** (étapes + échéances).

### 3.6 Espace personnel & données
- `/profil`, `/status` (progression, gamification), `/moncode` + `/moi <code>` (profil persistant par
  identifiant, portage inter-appareils/canaux), `/supprimer` (RGPD), `/contact` (joindre un conseiller),
  `/version`.

### 3.7 Quotas & rôles
- **Quotas journaliers** pour les utilisateurs gratuits sur les options coûteuses (analyse CV, `/guide`).
- **Admin** (`ADMIN_CHAT_ID`) illimité et jamais décompté.

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
                                                                              │    embeddings Gemini)
                                                                              └─ Envoi direct au canal
n8n : WF1 (transport Telegram), WF0 (planificateur veille /api/collect)
```

- **FastAPI** (`api/main.py`) = 100 % de la logique + envoi des messages.
- Modules extraits : `db.py` (persistance), `llm.py` (IA/vision/embeddings), `http_client.py` (pool HTTP),
  `channels.py` (adaptateurs Telegram/WhatsApp/Messenger).
- Déploiement VPS : Docker (`api/`), conteneur `forge-nex-api`, port 8000, volume `./data` (SQLite).

## 5. Modèle de données (SQLite)

`sessions`, `offres`, `candidatures`, `sources_offres` (+ scope), `feedback`, `contacts`, `profiles` +
`profile_versions` + `profile_user_map` (persistance par code), `usage` (quotas), `cache` (TTL).

## 6. Exigences non-fonctionnelles

- **Fiabilité IA** : router multi-fournisseurs avec bascule automatique ; modèles **configurables par env**.
- **Robustesse** : garde-fous sur chaque entrée (fichiers, quotas, formats) ; replis (OCR, banque de
  questions, profil manuel) ; aucun crash au démarrage (imports tolérants).
- **Qualité** : suite de tests (**127 tests**), CI GitHub Actions (lint erreurs, compile, pytest,
  smoke Docker).
- **Langue** : 100 % français, tutoiement, ton chaleureux et concret.
- **Confidentialité** : `.env` jamais versionné ; `/supprimer` efface les données ; profils portables par code.

## 7. État d'avancement

### ✅ Fait (en production ou déployé)
- Onboarding (analyse CV multi-format, adaptatif, accueil non rigide, création de CV sans CV).
- Recherche d'opportunités (veille, mobilité, sources structurées + filtrage adaptatif, alertes mots-clés,
  digest, feedback appris, matching sémantique).
- Accompagnement complet (Campus France + 8 étapes, 6 procédures FR, Canada temps réel IRCC, guide par
  capture, simulation d'entretien).
- Documents (CV/lettre/projet PDF+Word, outils PDF, timeline PNG).
- Espace perso (profil persistant par code, status/gamification, contact, RGPD), quotas + admin illimité.
- Telegram en production ; qualité (tests + CI + smoke Docker) ; refactor modulaire (db/llm/http/channels).

### 🟡 En cours
- **WhatsApp** : code prêt, **configuration du compte Meta Developers en cours** (blocage actuel : réception
  du code SMS / étape 3 du guide `GUIDE-WHATSAPP.md`).

### 🔭 Prévu / idées (non implémenté)
- **Messenger** : activer la config Meta (même socle que WhatsApp).
- **Optimisation conversation** : réponses libres encore plus naturelles hors onboarding (déjà amorcé).
- **Enrichir les sources locales** (Bénin/Afrique de l'Ouest) : intégrer davantage de portails d'emploi
  nationaux et régionaux quand des flux fiables existent.
- **Rappels de deadline plus fins** (J-30 / J-7 / J-1 par dossier).
- **Export PDF du profil complet** ; **comparateur d'écoles** ; **notifications proactives WhatsApp**
  (templates hors fenêtre 24 h).
- **Passage éventuel à un token permanent Meta** + App Review pour ouvrir WhatsApp au grand public.

## 8. Risques & dépendances

- **Dépendance Meta** (WhatsApp/Messenger) : compte + vérification obligatoires, SMS parfois non délivrés
  vers le Bénin → contournement = mobile d'un autre opérateur/pays pour créer le compte.
- **Dépendance n8n** (transport Telegram) : si le workflow WF1 n'est pas actif → Telegram renvoie 404.
- **Quotas des fournisseurs LLM** : atténués par le router multi-fournisseurs et les modèles configurables.
- **ngrok** (dev) : l'URL change au redémarrage → réenregistrer le webhook.
