# NexMove — Analyse technique senior (v2.22)

Audit d'ingénierie du système, dans l'esprit d'une revue staff/principal. Objectif : dire honnêtement où on
en est, ce qui tient, ce qui casse à l'échelle, et par quoi commencer.

---

## 0. Verdict global

**Produit riche et cohérent, ingénierie de bon niveau sur les détails, mais fondations fragiles pour
l'échelle.** NexMove fait *beaucoup* de choses bien (dégradation gracieuse partout, fallback multi-LLM,
grounding, sémantique, langage naturel, outils). Le risque n'est pas la qualité des features — c'est que le
tout repose sur : **un fichier monolithique de ~3 200 lignes, aucun test, aucune CI, SQLite mono-fichier, et
un rate-limit/état en mémoire par worker.** Ça tient très bien pour 10–100 testeurs ; ça devient risqué
au-delà et à chaque déploiement.

**Maturité** : bon prototype avancé / pré-production. Il manque le **filet de sécurité** (tests, CI,
observabilité) et le **socle de scalabilité** (Postgres/Redis) pour passer sereinement à 1 000+.

---

## 1. Points forts (à préserver)

- **Dégradation gracieuse systématique** : embeddings → lexical, OCR absent → message clair, DOCX absent →
  PDF seul, EURAXESS/RSS en échec → `[]`, LLM en panne → fallback fournisseur puis texte brut. C'est un vrai
  réflexe senior, rare à ce stade.
- **Routeur LLM multi-fournisseurs** (Cerebras → Groq → Gemini) avec bascule sur quota/erreur.
- **Grounding par index** : les URLs viennent des résultats web, jamais inventées.
- **Client HTTP partagé** (pool) + **CPU bloquant hors event-loop** (`asyncio.to_thread` pour OCR/PDF).
- **Anti-message-perdu Telegram** (repli texte brut sur Markdown cassé).
- **Onboarding déterministe** (pas de boucle LLM) + validation de cohérence + boutons.
- **Boucle de feedback** 👍/👎 réinjectée dans le score — vraie personnalisation.
- **Config par variables d'env** partout (endpoints, modèles, pays, feeds) — pas de valeurs en dur.

---

## 2. Risques & dette technique (par sévérité)

### 🔴 Bloquants pour l'échelle / la fiabilité

1. **Aucun test, aucune CI.** Chaque évolution = `scp main.py` + rebuild, sans filet. Sur 3 200 lignes très
   couplées, une régression passe inaperçue jusqu'en prod (on l'a déjà vu : embeddings 404, conversation
   qui vouvoie…). **C'est le risque n°1.**
2. **Monolithe unique de ~3 200 lignes.** Tout est dans `main.py` (modèles, DB, LLM, canaux, outils, 17
   endpoints, ~112 fonctions). Difficile à faire évoluer sans effets de bord, impossible à tester unité par
   unité, onboarding d'un dev long.
3. **SQLite mono-fichier, connexion par opération, écritures sérialisées.** WAL aide les lecteurs, mais les
   écritures se bloquent mutuellement ; avec 2 workers uvicorn + montée en charge, risque de
   *« database is locked »*. Chaque message lit **et réécrit** tout le blob session JSON.
4. **État en mémoire par worker** : le rate-limit (`_rate_store`), `_euraxess_working`, `_embed_model_ok`
   vivent dans chaque process → incohérents entre les 2 workers, remis à zéro à chaque redémarrage. Le
   rate-limit est donc contournable et non fiable.

### 🟠 Importants

5. **Secrets dans l'image Docker** (`.env` copié). Quiconque a l'image a les clés. À sortir en env runtime /
   secrets Docker.
6. **Coût LLM par message.** Depuis le langage naturel, *chaque* message libre non-mot-clé = 1 appel LLM ;
   + auto-veille au profil validé + chaque `/mobilite`. Pas de cache de réponses LLM, pas de file d'attente.
   Sous pic simultané, retour possible des 429 (déjà mitigé côté veille, pas côté conversation).
7. **Observabilité quasi nulle.** Logs JSON utiles mais pas de `/metrics`, pas d'ID de corrélation par
   requête, pas de suivi latence/taux de fallback/cache-hit. En cas d'incident, on débogue à l'aveugle.
8. **67 `except Exception` larges.** Beaucoup avalent l'erreur (`return []`, `msg = "réessaie"`). Pratique
   pour la robustesse, mais masque des bugs et complique le diagnostic. À resserrer + logguer le contexte.
9. **Fichiers temporaires orphelins.** Le tampon `data/tmp/<uid>/` (fusion/img→PDF) n'est nettoyé qu'au
   `/terminer` ou `/annuler`. Un utilisateur qui abandonne laisse des fichiers → fuite disque lente.
10. **Dépendances de transport = SPOF.** n8n (WF1) et **ngrok gratuit** (limites de débit/sessions) sont sur
    le chemin critique de *chaque* message Telegram. Une coupure ngrok = bot muet.
11. **CPU lourd sur petit VPS.** OCR (tesseract) + compression/rendu PDF sont gourmands ; `to_thread` évite
    de bloquer l'event-loop, mais le threadpool par défaut est petit — 2–3 gros PDF simultanés peuvent
    saturer les 2 workers.

### 🟡 À surveiller

12. **Qualité factuelle IA.** Le grounding réduit les hallucinations, mais le LLM *sélectionne/résume* :
    montants, dates, conditions peuvent être faux. Pas de vérification factuelle systématique (c'est
    d'ailleurs l'objet du protocole de test). Les disclaimers aident mais ne corrigent pas.
13. **Routeur d'intention LLM** : peut mal router une phrase ambiguë (pas de confirmation). Impact faible
    (l'utilisateur retape), mais à monitorer.
14. **WhatsApp/Messenger non éprouvés en prod** (tokens permanents, App Review, templates hors 24 h).
15. **RGPD / données perso.** `/supprimer` existe (bien), mais l'historique de conversation et le profil
    (données perso) sont stockés en clair dans SQLite, et potentiellement dans les logs. Pas de politique de
    rétention/chiffrement au repos.

---

## 3. Scalabilité — le chemin vers 1 000+ utilisateurs

| Aujourd'hui | Cible | Pourquoi |
|---|---|---|
| SQLite mono-fichier | **PostgreSQL** | écritures concurrentes, pas de lock global |
| État en mémoire/worker | **Redis** | rate-limit distribué, cache LLM/Tavily partagé, verrous |
| Collecte inline dans l'API | **worker/queue dédié** (RQ/Celery) | isoler la charge veille des requêtes utilisateur |
| 2 workers uvicorn | **scaler horizontalement** (stateless) | nécessite Postgres+Redis d'abord |
| ngrok gratuit + n8n | **reverse-proxy stable** (Caddy/Traefik) + domaine | enlever le SPOF |
| Logs seuls | **/metrics (Prometheus) + traces** | piloter la charge, alerter |

Bonne nouvelle : l'API est **presque stateless** (tout l'état est en base) — la migration Postgres+Redis
débloque le scaling horizontal sans réécriture profonde.

---

## 4. Recommandations priorisées

### Quick wins (jours, fort ROI)
1. **Filet de tests + CI GitHub Actions** : commencer par des tests unitaires sur les fonctions pures déjà
   isolables (`valider_pref`, `_sort_formations`, `_free_text_to_command`, `compress_pdf`, `merge/split`,
   `_offer_signal`, `_pays_from_nat`, parsers RSS/EURAXESS) + un lint (ruff) + `python -m compileall`. Ça
   coupe 80 % des régressions pour peu d'effort.
2. **Nettoyage TTL du tampon `data/tmp`** (supprimer les dossiers > 1 h au démarrage/collecte).
3. **Secrets hors image** : `.env` en `env_file` runtime uniquement, retirer le `COPY .env` du Dockerfile.
4. **`/metrics` minimal** (compteurs : appels LLM par fournisseur, taux de fallback, erreurs, latence p50/p95).

### Structurant (semaines)
5. **Découper le monolithe** en modules (`db.py`, `llm.py`, `channels/`, `tools.py`, `procedures.py`,
   `onboarding.py`, `sources.py`, `main.py`) — sans changer le comportement, pour tester et faire évoluer.
6. **Rate-limit + cache LLM dans Redis**, puis **collecte en worker dédié**.
7. **Migration PostgreSQL** (SQLAlchemy ou requêtes directes), une seule couche `store`.

### Produit / qualité
8. **Garde-fou factuel** : marquer explicitement montants/dates comme « à vérifier » et, quand c'est
   critique (frais, ressources visa), renvoyer systématiquement vers la source officielle (déjà partiel).
9. **Embeddings locaux optionnels** (`fastembed`) pour s'affranchir du quota Gemini.
10. **Finaliser un seul canal secondaire** (WhatsApp) proprement avant d'ouvrir large.

---

## 5. En une phrase

> Le produit est en avance sur son socle : **investir maintenant dans les tests/CI et la migration
> Postgres+Redis** (avant d'ajouter encore des features) est ce qui sécurisera le passage de « 100 testeurs »
> à « service fiable ».

_Voir `docs/FONCTIONNALITES.md` (features), `docs/GUIDE-IMPLEMENTATION.md` (déploiement),
`docs/CHANGELOG.md` (historique)._
