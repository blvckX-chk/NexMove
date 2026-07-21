# NexMove — Analyse experte mobilité & roadmap d'amélioration

Revue du système par cas d'application, avec regard « expert mobilité internationale »
(emploi, bourses, fellowships, immigration). Priorités : 🟢 quick win · 🟡 moyen · 🔴 gros chantier.

Architecture : Telegram → n8n (transport) → FastAPI (logique) → n8n → Telegram, Google Sheets en persistance.
Composants : WF0 (orchestrateur 24 h), WF1 (onboarding), WF5 (OSINT). FastAPI `forge-nex-api` (Groq llama-3.3-70b),
`SessionManager` (SQLite, partagé entre workers).

---

## 1. Profil & Onboarding (WF1 · `/api/chat-cv`, `/api/chat`)

**Aujourd'hui :** parsing CV → profil JSON, préférences (objectif, zone, langue, niveau, mots-clés).

**Manque (éligibilité dure) :** un profil de mobilité exige les critères qui décident de tout.

| Champ | Pourquoi décisif |
|---|---|
| Nationalité / passeport | Visa, frais, éligibilité bourses (nationalité-dépendantes) |
| Financement (bourse requise / auto-financé) | Fully-funded vs tuition-only : critique pour un profil ouest-africain |
| Certifs de langue (IELTS/TOEFL/TCF/DELF + scores) | Barrière d'entrée n°1 des masters anglophones |
| Âge / année de naissance | Limites d'âge fréquentes (Chevening, Mastercard Foundation < 35) |
| Pays cibles + disponibilité | Précision du ciblage + timing rentrée |

**Reco :** 🟢 étendre `profil.preferences` (nationalite, financement, certifs_langue, pays_cibles, disponibilite) ;
🟢 pré-remplir depuis le CV et ne demander que le manquant ; 🟡 gérer l'équivalence des diplômes (LMD).

---

## 2. Collecte d'opportunités (WF0 · `/api/collect`)

**Aujourd'hui :** collecte planifiée, dédup via `OffresDejaVues`.

**Reco :**
- 🟡 Schéma « Opportunité » normalisé avec champs mobilité : `type`, `deadline`, `financement`, `eligibilite`
  (nationalités, niveau, domaine), `langue_requise`, `pays`, `lien`, `source`.
- 🟡 Adaptateurs par catégorie plutôt qu'un scraping générique :
  - Bourses/fellowships : DAAD, Campus France, Erasmus Mundus, Chevening, Commonwealth, AUF,
    Mastercard Foundation, Fulbright (souvent des flux RSS/pages listables, plus fiables).
  - Emploi tech : connecteurs MCP **Dice** et **ZipRecruiter**, EURES, remote boards.
- 🟢 Dédup par URL canonique (pas seulement le titre).

---

## 3. Scoring / Matching (`/api/score`)

**Limite :** un LLM seul hallucine sur les règles dures (deadline passée, nationalité inéligible).

**Reco — architecture 2 étages :**
- 🔴 Étage 1 (déterministe, code) : deadline non expirée, nationalité éligible, niveau requis, langue OK.
- 🟡 Étage 2 (LLM) : fit nuancé + classement, score multi-dimensions
  (fit profil · financement · faisabilité visa/langue/timing · urgence deadline).
- 🟢 Stocker détail du score + justification dans `MatchingsAValider`.

---

## 4. Notification & recommandations (`/api/notify`)

**Reco :**
- 🟢 Carte Telegram riche : titre · financement · deadline **J-xx** · fit % · pourquoi · docs manquants · bouton Postuler.
- 🟢 Boutons inline Sauver / Ignorer / Postuler → alimente `Candidatures` et affine les préférences.
- 🟡 Rappels de deadline (J-14, J-3) — valeur ajoutée mobilité majeure.
- 🟢 Digest cadencé (quotidien/hebdo).

---

## 5. OSINT mobilité (WF5 · `/api/osint`, actuellement `active:false`)

**Reco :** 🟡 sortie structurée par pays cible : voie d'immigration, droit au travail post-études
(France APS/Passeport Talent, Canada PGWP, Allemagne 18 mois), reconnaissance du diplôme, marché du domaine,
coût de vie, langue. 🟢 Toujours citer les sources.

---

## 6. Génération de documents (`/api/generate-documents`)

**Aujourd'hui :** adaptation CV (ATS) via LLM + PDF reportlab. Lettre de motivation : à renforcer/cibler.

**Reco :**
- 🟡 Templates par type de cible :
  - Emploi : CV ATS + lettre de motivation ciblée (+ Europass pour l'UE).
  - Bourse : Statement of Purpose / lettre alignée sur les critères du programme (leadership Chevening,
    excellence + plan d'étude DAAD…), plan d'étude, modèle de demande de recommandation.
- 🟢 Injecter les critères de sélection spécifiques du programme dans le prompt (pas de lettre générique).
- 🟡 Sortie PDF + DOCX (les commissions demandent souvent du modifiable).

---

## 7. Candidature & suivi (feuille `Candidatures`)

**Reco :** 🟡 tracker (statut `à préparer → en cours → soumise → relance → résultat`, checklist docs, deadline,
prochaine action) ; 🟢 commande `/status` (pipeline + prochaines deadlines).

---

## 8. Transverse — fiabilité, coût, conformité

- 🟡 Source de vérité : SQLite/Postgres pour Sessions/Offres, Sheets en miroir reporting.
- 🟢 Robustesse LLM : JSON mode + validation schéma + fallback + cache (coûts Groq).
- 🟢 RGPD : stockage CV minimal, commande `/supprimer` (droit à l'effacement), rétention limitée.
- 🟢 Observabilité : métriques (offres collectées, matchings, taux notif, deadlines ratées = 0).
- 🟡 **OCR CV scannés** : `extract_text_pdf` (PyMuPDF) n'extrait que le texte intégré → PDF scanné = vide.
  Ajouter `tesseract-ocr` (+ langues fra/eng) au Dockerfile + `pytesseract` + rendu page via fitz. Nécessite rebuild.
- 🟡 Durabilité : les correctifs appliqués par `docker cp` sont perdus à la recréation du conteneur.
  Passer `forge-nex-api` sous docker-compose (rebuild image + volume pour `data/sessions.db`) et versionner le code.

---

## Roadmap (ordre de valeur)

| # | Chantier | Effort | Méthode |
|---|---|---|---|
| 1 | Profil enrichi (nationalité, financement, langue certifiée, pays cibles) + deep-merge préférences | 🟢 | `docker cp` |
| 2 | Scoring éligibilité-d'abord (filtre dur + fit LLM + justification) | 🔴/🟡 | `docker cp` |
| 3 | Notifs actionnables + rappels de deadline | 🟢/🟡 | `docker cp` + WF |
| 4 | Documents par cible (CV/LM emploi vs SOP/plan d'étude bourse) + DOCX | 🟡 | rebuild |
| 5 | OCR CV scannés | 🟡 | rebuild (Dockerfile) |
| 6 | Tracker candidatures + `/status` | 🟡 | `docker cp` + WF |
| 7 | Sources structurées (RSS bourses + MCP Dice/ZipRecruiter) | 🟡 | WF + code |
| 8 | Durabilité : compose + volume + repo + rebuild (regroupe 4 & 5) | 🟡 | compose |

**Séquencement :** d'abord les patchs « code pur » (1→3, 6) par `docker cp` ; puis un unique **rebuild** regroupant
documents (4), OCR (5) et la mise sous compose durable (8).
