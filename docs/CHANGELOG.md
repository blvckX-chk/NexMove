# NexMove — Journal des évolutions

Récapitulatif lisible de tout ce qui a été fait (le détail exact est dans l'historique Git).

## v3.75 — Codes premium : fin de l'hallucination sur les suivis (admin)
- **Bug (capture admin).** « Renvoie moi ceux valide » → le bot **inventait** une liste de codes (dont un déjà utilisé et un tronqué) et proposait un CV à l'admin. Cause : ce suivi partait sur le LLM.
- Corrigé :
  - `_admin_nl_route` ne détourne plus un message **contenant des codes collés** (≥2) → le **cross-check** précis (sur TES codes) s'applique, plus les totaux du store.
  - La liste collée est **mémorisée** (`last_codes`). Les suivis « renvoie les valides », « ceux qui restent », « les utilisés » sont routés **déterministes** : ils filtrent CETTE liste via la base — **jamais le LLM** (qui inventerait des codes).
  - L'admin ne reçoit plus de proposition « envoie ton CV ».

## v3.74 — L'urgence change aussi le TRI des offres (pas que le ton)
- En v3.69 l'urgence adaptait le ton. Désormais, quand une urgence/échéance est active, la recherche **fait remonter les opportunités à deadline PROCHE** (datable, 0-30 j) en tête, sans casser l'ordre par score pour le reste.
- `_deadline_days_left` (jours restants, réutilise l'analyse de dates ISO / JJ-MM-AAAA / « 15 janvier 2026 ») + `_rank_urgent` (reclassement). Les offres non datables ne sont pas pénalisées entre elles.
- Boucle bouclée : un signal capté (urgence) agit désormais sur le **ton** ET sur le **résultat**.

## v3.73 — Cohérence objectif CONTINUE (pas seulement à l'onboarding)
- La réconciliation objectif↔aspiration (v3.67) ne tournait qu'à la fin de l'onboarding. Désormais elle se **relance aussi** quand l'objectif change plus tard : **changement de cible** en conversation (« je veux aller en finance ») ou **édition** (« objectif: … »).
- Chaque changement ré-évalue la cohérence (corrige une contradiction nette, sinon re-signale l'ambiguïté) et **ré-autorise une clarification** si le nouveau but est ambigu. Le modèle de compréhension s'applique en continu, plus seulement au démarrage.

## v3.72 — POUR QUI : contraintes de vie captées (#3)
- Les contraintes réelles changent tout un conseil (un budget serré, un problème de visa, l'impossibilité de déménager…). Capture déterministe dans `profil["contraintes"]` : **budget** (« pas d'argent », « j'ai pas les moyens », « gratuit seulement »), **visa/papiers**, **mobilité/famille** (« je ne peux pas déménager », « j'ai des enfants »), **disponibilité** (« disponible immédiatement », « seulement le week-end »).
- Remontées dans le contexte (« Contraintes : … ») pour que le conseiller en tienne compte au lieu de proposer l'impossible. Pas de faux positif.

## v3.71 — État émotionnel : adapter le ton (#9)
- « Quelqu'un qui dit *j'y arriverai jamais* n'a pas besoin de 10 offres mais d'un cap. » Le bot détecte désormais l'état et **adapte son ton**.
- **`_capture_mood`** (déterministe) capte 4 états : **découragé**, **anxieux**, **méfiant**, **frustré** (élisions tolérantes : « j'ai » ou « j ai »). Mémorisé 1 h.
- Injecté dans le contexte avec une **directive de ton** : découragé → encourageant + un petit pas ; anxieux → rassurant ; méfiant → transparent, pas de survente ; frustré → reconnaître puis solution. Pas de faux positif (« je cherche un stage » ne déclenche rien).
- Clôt la première passe du **modèle de compréhension** (#4 comment, #10 cohérence, #8 clarification, #2 urgence, #6 périmètre, #9 émotionnel).

## v3.70 — Périmètre : LA prochaine étape, pas un mur d'options (#6)
- Le bot proposait parfois 4 options d'un coup. Désormais il donne **UNE direction claire** selon où en est la personne dans son parcours.
- **`_next_best_action`** (déterministe, entonnoir) : pas de CV → `/creercv` ; profil prêt sans recherche → `/veille` ; offres montrées → `/postuler` ; docs générés → `/mescandidatures` ; cible active → l'étape du funnel (chances → docs → postuler → suivi).
- Injecté dans le contexte (« PROCHAINE ÉTAPE LA PLUS UTILE (propose CELLE-CI, une seule) ») et le prompt conseiller renforcé : **une seule action, au bon niveau, pas un menu**.

## v3.69 — Urgence / échéance captée et prise en compte (#2)
- Une **deadline change tout**. Capture déterministe des signaux d'urgence (« c'est urgent », « au plus vite », « il me reste peu de temps ») et d'échéance (« la bourse ferme dans 3 jours », « deadline demain »).
- Mémorisé dans `session["urgence"]` (valable 2 h) et **injecté dans le contexte** : « ⏰ URGENCE exprimée → va DROIT à l'action, privilégie ce qui tient dans le délai ». Le conseiller arrête d'explorer longuement et donne la prochaine étape concrète.
- Pas de faux positif (« je cherche *tranquillement* un stage » ne déclenche rien).

## v3.68 — Clarification de l'ambigu : une bonne question avant de répondre (#8)
- Quand l'objectif est **ambigu** (métier visé = emploi OU études ? — détecté en v3.67), le bot **pose UNE question nette** avant de lancer la recherche, au lieu de deviner : « Pour *devenir analyste financier*, tu cherches un *emploi* dans ce domaine ou à *reprendre des études* ? » (+ boutons 💼 emploi / 🎓 études / 🎓 bourse).
- Réponse acceptée **cliquée OU tapée** (« emploi », « plutôt des études »…) → fixe l'objectif, lève l'ambiguïté, **reprend automatiquement** l'action initiale. Posée **une seule fois**, jamais insistante.
- Se greffe sur les mécanismes de clarification existants (reconversion, info cruciale manquante) et passe **en premier** car le plus précis.

## v3.67 — Cohérence objectif ↔ aspiration (#10)
- **Bug (capture).** « Objectif : études » alors que la personne visait « devenir analyste de données financières » (un métier). Le bot enregistrait sans vérifier la cohérence.
- **Détecteur `_objectif_coherence`** : confronte l'objectif enregistré aux signaux réels (aspiration, résumé, mots-clés). Trois états :
  - **corrige** (sûr) : un emploi (ou des études) est *explicitement* cherché mais l'objectif dit l'inverse → **correction silencieuse** (« je cherche un emploi de comptable » + objectif études → travailler).
  - **ambigu** : un métier est *aspiré* sans dire comment (« devenir analyste financier ») → **on ne suppose pas**, on mémorise pour clarifier (prépare #8).
  - **ok** : cohérent (« faire un master » → études, « trouver un poste » → travailler).
- Appliqué à la fin de l'onboarding ; l'ambiguïté est signalée dans le contexte (« ⚠️ OBJECTIF À CLARIFIER ») pour que le conseiller ne tranche pas à l'aveugle.

## v3.66 — Maîtrise du contexte : « comment il le veut » capté et respecté
- Le bot savait déjà beaucoup (nom, objectif, pays, forces, axes, savoir-être, motivation, aspiration…). Il manquait le **« comment »** : les préférences de FORME que la personne exprime.
- **Capture déterministe** (`_capture_user_prefs`, sans coût LLM) sur chaque message : **style de CV** préféré (ATS/graphique), **langue des documents** (FR/EN), **ton** voulu (concis), **contrainte non négociable** (« je ne peux pas déménager », « je reste à Cotonou »).
- **Réutilisation** : ces préférences sont injectées dans le contexte conversationnel sous « COMMENT il/elle veut (À RESPECTER) », et `/creercv` **génère directement dans le style préféré** (graphique si demandé, au lieu d'ATS par défaut). `/postuler` reste ATS (meilleur pour les robots de tri).
- Base d'une maîtrise du contexte plus fine (prochaine étape : cohérence objectif/aspiration).

## v3.65 — Passage systématique : routage NL des 8 intentions critiques
- **Fin du whack-a-mole.** Au lieu de câbler une intention à chaque capture, **table unique** (`_NL_INTENTS`, source de vérité) qui route en langage naturel les 8 commandes les plus utilisées : **postuler, chances, mes candidatures, dossier, tarifs/offres, simulation, entretien, compatibilité** — avec extraction de la cible (« postuler à Orange » → `/postuler Orange`).
- **Matrice de tests** : 36 cas (positifs *et* négatifs) verrouillent le comportement — ex. « comment postuler » reste `/commentpostuler`, « je cherche un emploi » reste `/mobilite`, « entretien blanc » = `/simulation` (pas `/entretien`), « génère mon cv » = `/creercv` (pas `/postuler`).
- Priorité au plus spécifique (simulation avant entretien, chances avant postuler) ; exclusions anti-conflit (postuler n'avale pas les recherches).

## v3.64 — « Supprimer mon profil » en langage naturel
- **Bug (capture).** « je veux supprimer mon profil » → le bot **affichait** le profil (« Pour corriger… ») au lieu de lancer la suppression ; et « supprimer » seul → le LLM demandait « supprimer quoi ? » sans retenir la réponse.
- Corrigé : routage **déterministe** des intentions de suppression (« supprimer / effacer / purger … profil / compte / données / tout / mon cv », ou « supprimer » seul) vers `/supprimer`, qui demande la confirmation (OUI). « mon profil » seul continue d'**afficher** le profil.

## v3.63 — Reconversion pendant l'onboarding : fin des offres de l'ancien domaine
- **Bug (capture).** CV dev web → le bot calcule et **met en cache** un aperçu d'offres (dev web) juste après le CV. L'utilisateur dit ensuite « je continue en **finance** » → à la validation, le bot **réutilisait le cache périmé** et affichait des offres *dev web* malgré « mots-clés : finance ».
- Corrigé : le cache d'aperçu mémorise le **domaine** au moment du calcul ; si le domaine a changé (reconversion pendant l'onboarding), on **relance la recherche** sur la nouvelle cible et on **acte la reconversion** (les compétences de l'ancien domaine sont écartées de la recherche).

## v3.62 — Codes premium : collision /code vs /codes + anti-activation à l'aveugle
- **Bug (capture admin).** « Dans cette liste quel code reste valide ? » + 20 codes → « ❌ Activation impossible : ce code n'existe pas ». Cause : le routeur admin mappait bien vers `/codes valides`, mais le handler d'activation `/code` **avalait `/codes`** (collision de préfixe) et tentait d'activer le mot « valides ». Corrigé : `/code` n'intercepte plus `/codes`.
- **Anti-activation à l'aveugle** : coller PLUSIEURS codes (ou poser une question contenant des codes) ne déclenche plus l'activation du 1er. Pour l'admin : **cross-check** de la liste (libres / utilisés / inconnus). Pour un utilisateur : on demande *un seul* code.
- Nouveau `premium_store.statuses()` (statut de codes précis, pour vérifier une liste collée).
- _(Audit QC : les autres préfixes proches — `/credit`·`/credits`, `/supprime`·`/supprimer`, `/annonce`·`/annonces` — sont soit des alias du même handler, soit ordonnés spécifique-d'abord : pas de collision.)_

## v3.61 — Mise à jour de CV sans casser le profil + feedback tapé
- **Re-upload d'un CV *différent* par un utilisateur déjà onboardé** : on ne refait plus tout l'onboarding et on **conserve ses préférences de recherche** (objectif, pays, mots-clés) au lieu de les écraser par les défauts de l'analyse. Message « 🔄 CV mis à jour · préférences conservées », l'utilisateur reste ACTIF.
- **Feedback 👍/👎 tapé** (et pas seulement cliqué) : après des offres, « utile », « ça correspond », « pas pour moi », « hors sujet », « pas intéressé » enregistrent l'avis sur toutes les offres affichées (le négatif l'emporte sur le « intéress » de « pas intéressé »). Le 👍 guide vers `/postuler`.
- _(Rappel : la confirmation à l'étape préférences acceptait déjà « oui / non / correction de champ » en langage libre — vérifié robuste, inchangé.)_

## v3.60 — QC adversariale sur v3.59 (3 bugs corrigés)
- **« comment postuler à X »** (cible explicite) ne détourne plus vers la cible du *dernier lien analysé* — seul un « comment postuler » **nu** le fait.
- **À l'écran CV, « oui mais le nom est faux » ne valide plus** : passage de `detecter_reponse_positive` (substring gourmand) à `_is_clear_affirmation` (un « oui » noyé dans une nuance ne confirme pas).
- **Re-upload** : dédup durcie — nom **non générique** ET **même taille d'octets** (deux CV différents nommés « cv.pdf » sur WhatsApp ne sont plus confondus).

## v3.59 — Liens propres dans le digest + 3 angles « ils ne cliquent pas »
- **Liens en clair dans les offres du jour (capture Telegram).** Le digest quotidien affichait l'URL technique complète (`adzuna.fr/land/ad/…?se=…&v=…`). Désormais il réutilise `_offer_link` : **lien masqué cliquable** « 👉 Voir l'offre » sur Telegram/Messenger, lien court maison sur WhatsApp. Idem `/formations` et le récap d'offres post-CV. Garde-fou anti-Markdown cassé.
- **Angle A — confirmation CV sans bouton.** À l'écran « CV analysé », taper « c'est faux » ou « nom : Ketsia Mensah » (au lieu de cliquer) **corrige le champ** ou propose de recommencer, **sans perdre le profil**.
- **Angle B — boutons de lien en langage naturel.** Après l'analyse d'un lien, « comment postuler », « mes chances », « suivre cette bourse » tapés en clair déclenchent la bonne action sur la cible mémorisée.
- **Angle C — re-upload du même CV.** Renvoyer le **même fichier** déjà analysé ne relance plus l'analyse (ni le quota ni la boucle « donne-moi tes infos ») : le bot dit qu'il l'a déjà et propose `/cv`, `/postuler` ou un CV *différent*.

## v3.58 — Création de CV cohérente + « ils ne cliquent pas les boutons »
- **Bug capture WhatsApp (Ketsia).** CV analysé avec succès, puis « Créercv » → le bot **repartait de zéro** et redemandait nom/parcours/expériences (boucle). Corrigé :
  - `/creercv` **détecte un CV déjà analysé** (`_profile_is_usable`) et **génère directement** depuis le profil, avec boutons *Version graphique · Repartir de zéro · Postuler* (au lieu du questionnaire vierge).
  - **« Créercv » / « créer mon CV » / « faire mon CV » routés de façon DÉTERMINISTE** vers `/creercv` (avant : ça dépendait du LLM, qui répondait vaguement « utilise /creercv »). Les enchaînements (« … puis crée un cv ») restent gérés par l'orchestrateur.
- **Malformation d'affichage « • · ESDAM »** : une formation sans diplôme laissait un séparateur `·` orphelin. Le récap n'assemble plus que les morceaux présents (`_render_formation_recap`).
- **Mécanisme général « ils ne cliquent pas les boutons »** : après `/postuler`, les 3 boutons (Word / Corriger / CV graphique) sont désormais **compris en langage naturel** (« je veux le word », « corrige la lettre », « en graphique »), sans confondre avec une modif de profil.
- **Sur-promesse supprimée** : le prompt d'accueil décrit `/creercv` **exactement** (5 questions puis génération, **pas** d'aperçu section par section) — fini le « tu pourras prévisualiser chaque section ».

## v3.57 — Ne jamais redemander un CV déjà analysé
- **Bug (même capture WhatsApp).** À « *quoi de plus que le CV que je t'ai soumis ?* », le conseiller répondait « *envoie-moi à nouveau ton CV* » alors qu'il était **déjà analysé** (le modèle ignorait la consigne). Ajout d'un **garde-fou déterministe** : si `cv_parsed`, toute phrase qui réclame le CV (envoyer/renvoyer/`/creercv`…) est **retirée** de la réponse ; s'il ne reste rien d'utile, repli explicite (« je pars de ton CV déjà analysé, dis-moi la cible »).

## v3.56 — Cohérence des suivis + filet dur anti-cliché + anti-invention + /qualite
- **Bug de cohérence (capture WhatsApp greatyop).** Après l'analyse d'un **portail** de bourses, la question de suivi « *parmi ces bourses, lesquelles pour l'informatique ?* » repartait en **recherche web** et répondait à côté (bourse sans rapport, puis « aucune opportunité trouvée »). Deux causes corrigées :
  1. Le portail **ne mémorisait pas** les opportunités listées → ajout de `last_portail` (titre + exemples) et rappel dans le contexte conversationnel.
  2. Le routage captait « bourses » comme une **nouvelle recherche** → détecteur de **question de suivi déictique** (« ces bourses », « lesquelles », « citées plus haut »…) qui répond **en conversation, ancré sur les opportunités déjà listées** (réelles), au lieu de relancer `/mobilite`.
- **Filet DUR anti-cliché** : même après la relance QC, si un cliché subsiste, on réécrit **chirurgicalement** la seule phrase fautive (mêmes faits) et, si elle reste fautive, on la **supprime** → garantie qu'aucun cliché ne part au candidat.
- **Anti-invention** : une **ancienneté chiffrée** (« 7 ans d'expérience ») absente du profil déclenche une relance + interdiction explicite d'inventer une durée.
- **Panneau admin `/qualite`** : taux de relance QC, taux de filet dur, et **répartition par fournisseur** (Tchavi premium vs gratuit) — exploite la traçabilité A/B de v3.55.

## v3.55 — QC tolérance zéro + dossier complet + traçabilité A/B
- **Tolérance ZÉRO clichés** (lettres/CV) : voir ci-dessous.
- **Dossier incomplet signalé** (`/postuler`) : si les coordonnées (e-mail, téléphone, ville) manquent sur le CV/lettre, le bot **avertit** (« ⚠️ Coordonnées incomplètes… un recruteur ne pourra pas te recontacter ») sans bloquer l'envoi, et indique comment les ajouter (`profil` → `email: …`) puis relancer.
- **Traçabilité A/B premium** : chaque livrable rédigé logue désormais **quel fournisseur l'a écrit** (`[pack] rédigé par tchavi-gen (…)` vs modèle gratuit), pour comparer en prod la qualité Tchavi premium vs gratuit. `llm.LAST_PROVIDER`/`LAST_MODEL`.

### Détail — tolérance zéro sur les clichés
- Retour testeur : une lettre comme « Je suis persuadée que ma capacité… » passait encore. Le QC ne doit **rien laisser passer**.
- **Liste de clichés élargie** (~22 → ~55 tournures) : variantes féminines (« forte/riche de mon expérience »), et classiques des lettres (« atout majeur », « valeur ajoutée », « passionné·e par », « candidat idéal », « soif d'apprendre », « environnement stimulant », « contribuer au succès », « mes salutations distinguées »…).
- **Tolérance ZÉRO** : désormais **un seul cliché** dans la lettre (ou le résumé) déclenche la relance de rédaction, au lieu de 2+. Même durcissement pour les projets d'études (`/dossier`). Le prompt de relance interdit explicitement la liste élargie.

## v3.54 — 10 modèles de CV graphiques pro
- Le CV graphique n'avait qu'un seul style (bandeau bleu). Nouveau **système de 10 modèles** professionnels, 5 mises en page × couleurs : *Moderne Bleu, Émeraude, Bordeaux* (bannière), *Corporate Ardoise, Teal* (bandeau fin), *Indigo Minimal, Noir Minimal* (minimaliste), *Élégant* (serif centré), *Sidebar Marine, Sidebar Anthracite* (colonne latérale colorée). `/cv modeles` les liste (avec boutons), `/cv <modèle>` en génère un ; aussi via Outils → « Modèles de CV (10) ». Le nom de fichier reprend le modèle. L'ATS reste inchangé (toujours recommandé pour postuler). Repli propre sur le modèle par défaut si un nom inconnu est donné.

## v3.53 — Candidature : PDF d'abord, Word à la demande + corrections
- Retour testeur UX. Après `/postuler`, le bot envoie **les PDF d'abord** (moins d'encombrement), puis propose trois boutons : **📝 Versions Word** (générées à la demande), **✏️ Corriger**, **🎨 CV graphique**.
- **Boucle de correction** : « ✏️ Corriger » → le bot demande « dis-moi quoi changer » ; la phrase suivante (ex. « raccourcis la lettre », « mets le titre Chargé de clientèle », « insiste sur mon stage ») **régénère** CV+lettre en appliquant précisément la correction (sans rien inventer), et renvoie les nouveaux PDF. Une commande annule proprement l'attente.

## v3.52 — CV : pédagogie ATS + choix clair + nom de fichier + filigrane visible
- Beaucoup de candidats ne savent pas ce qu'est un **CV ATS** et préfèrent le « joli » graphique (souvent écarté par les logiciels de tri). Désormais le bot **explique** (encart « C'est quoi un CV ATS ? ») et **donne le choix** :
  - `/creercv` : le prompt de choix explique ATS vs graphique, recommande l'ATS, bouton « CV ATS (recommandé) ».
  - `/postuler` : le CV est en **ATS** (bon pour postuler), le fichier s'appelle `CV_ATS_<nom>.pdf/.docx`, l'encart ATS est affiché, et un bouton **« 🎨 Version graphique du CV »** permet d'obtenir l'autre format en un clic.
- **Filigrane** : sur compte gratuit, mention en pied plus **visible** (taille 8, italique, moins transparente) + rappel explicite dans le message (« Filigrane présent · le Premium l'enlève »). Rappel : sur le compte **admin/Premium, il n'y a PAS de filigrane** (c'est normal — c'est ce que voyait le testeur).

## v3.51 — Rendu CV/lettre : fin du « carré », date de lettre à la française
- **Bug du carré (■) dans le CV** (ex. « e■commerce ») : les **missions/expériences/formations** n'étaient pas passées au nettoyeur de texte (seuls le résumé et les compétences l'étaient). Désormais TOUS les champs sont nettoyés, et le nettoyeur **normalise les tirets/espaces/guillemets exotiques** (tiret insécable, en/em-dash, espaces insécables, guillemets typographiques → équivalents ASCII sûrs) — cause exacte du carré. Corrigé en PDF ET en Word.
- **Date de la lettre de motivation** : passait en « 27/10/2026 » mal placée. Désormais convention française : « *Abomey-Calavi, le 27 octobre 2026* », alignée à droite (PDF et Word).

## v3.50 — Tchavi : URL par défaut corrigée
- Correction de l'URL par défaut de la passerelle Tchavi : `https://tchavi.com/api/v1` (l'endpoint réel d'après le dashboard), au lieu de `api.tchavi.com`. Reste surchargeable via `TCHAVI_BASE_URL`. Le code ajoute `/chat/completions`.

## v3.49 — Fournisseur LLM PREMIUM optionnel (Tchavi) pour la qualité
- Intégration **opt-in** de Tchavi (passerelle LLM OpenAI-compatible, à crédits) comme fournisseur **premium**. Dormant tant que `TCHAVI_API_KEY` est vide (aucun coût, aucun risque). Une fois la clé mise : le tier **"quality"** (rédaction CV / lettre / projet d'études — le livrable que l'utilisateur montre) passe par Tchavi **en premier**, avec **repli automatique** sur les modèles gratuits si Tchavi échoue → jamais de panne. Pour router aussi le **raisonnement** (conversation, sélection d'offres, conseils) via Tchavi : `SMART_LEAD_PROVIDER=tchavi`. Visible dans `/version` (module « Premium (Tchavi) »). Config : `TCHAVI_API_KEY`, `TCHAVI_BASE_URL`, `TCHAVI_MODEL`, `TCHAVI_GENERATE_MODEL` (voir .env.example).

## v3.48 — Reconversion captée même à la re-question + vision plus costaude
- **Bug onboarding (capture testeur).** À l'étape objectif, « Je veux continuer en **finance** » n'étant pas un choix littéral (travailler/étudier/…), la validation re-posait la question et **perdait le domaine « finance »** : le récap gardait les compétences du CV (web dev). Désormais le domaine est **extrait et stocké AVANT** la validation du choix — même si l'objectif reste à préciser. Le bot accuse réception (« ✅ Noté : finance ») puis redemande seulement l'objectif ; « finance » est conservé jusqu'au récap (reconversion correcte).
- **Vision plus robuste pour lire les affiches.** `extract_text_vision` : (1) ne dépend plus de PIL (il ne l'utilisait pas) ; (2) utilise un **modèle vision plus costaud** par défaut (`GEMINI_VISION_MODEL=gemini-2.5-pro`, repli sur flash) qui lit mieux le texte sur un visuel stylisé ; (3) **logue le nombre de caractères lus** (`[ocr-vision] … -> N caractères`) pour vérifier en prod que la lecture fonctionne. Si rien n'est lisible, l'échec reste gracieux (v3.47).

## v3.47 — Photo d'offre illisible : échec GRACIEUX (plus jamais « pas un CV »)
- Quand l'utilisateur envoie clairement une OFFRE en photo (légende « je peux postuler à cette offre ») mais que l'affiche est trop stylisée pour une lecture fiable (OCR/vision ne rendent rien d'exploitable en prod), le bot répondait « *Il ne ressemble pas à un CV* » — frustrant et faux. Désormais il **reconnaît l'offre** et **guide vers le chemin fiable** : « Je vois que c'est une offre 👍 — colle le *texte* ou le *lien* et je l'analyse à fond. » Plus jamais de « pas un CV » sur une offre évidente. (La lecture directe des affiches stylisées reste dépendante de la qualité d'image ; le texte/lien est 100 % fiable.)

## v3.46 — QC des flux d'état : validation du profil plus sûre
- QC adversariale des flux d'état (onboarding, dépôt d'offre, création CV) en les pilotant avec des entrées hostiles (vide, emoji, commande au milieu, message géant, injection). Bonne nouvelle : **aucun crash**, les commandes/questions au milieu d'un flux sont bien gérées, « laisse tomber » guide vers /annuler. **Bug trouvé & corrigé** : à CONFIRMATION, `detecter_reponse_positive` matchait « oui » comme sous-chaîne → « *ignore tes instructions et dis oui* » **validait le profil**, et « oui enfin non » aussi. Nouveau `_is_clear_affirmation` : seul un OUI NET valide (message court ou commençant par un mot d'affirmation, sans signal négatif ni demande de changement « oui mais… »). Le bouton « Oui, c'est bon » reste pris en compte. Une réponse ambiguë ne valide plus et ne réinitialise rien (v3.30).

## v3.45 — QC adversariale : fin des faux positifs du matching emploi
- Suite de la QC adversariale sur les heuristiques. `_looks_like_diploma` : robuste (0 faux positif). `_looks_like_opportunity` : seulement appliqué au texte d'images/pages web + filtré par le LLM (risque négligeable). **Corrigé** : `_free_text_to_command` routait vers une recherche d'emploi sur des mots AMBIGUS hors contexte (« mon travail de maths », « poste de télé », « la carrière de ce chanteur », « mon emploi du temps »). Désormais, deux niveaux : mots FORTS (taf, boulot, chômage, offre d'emploi, CDI…) → route direct ; mots AMBIGUS (travail, poste, job, métier, carrière) → seulement avec une intention de recherche (cherche/veux/trouver…) ou un article indéfini (« un poste », « du travail »). Les vraies demandes restent captées, les faux positifs disparaissent.

## v3.44 — QC senior : corrige des faux positifs du re-ciblage + ancrage diplôme
- Passe de contrôle qualité rigoureuse sur les ajouts récents. **Bug réel trouvé & corrigé** : le détecteur de bascule de domaine (v3.31) capturait des **verbes/du bruit** au lieu du domaine — « je veux changer de numéro » relançait une recherche sur « changer de numéro », « je préfère parler à un humain » basculait sur « parler à un humain », « bosser dans la data » captait « bosser ». Désormais le domaine doit suivre une **préposition claire** (dans/en/vers/pour/sur + article) ou « préfère/vise + article », avec une **liste d'exclusion** (numéro, humain, métier, mot de passe…) : plus de fausse bascule, tout en captant les vrais changements (« bosser dans la data » → data, « changer de métier pour la finance » → finance).
- Durcissement de l'**ancrage** du résumé de document académique (v3.43) : au moins un champ renseigné (intitulé/établissement) doit figurer dans le texte source, sinon on n'affiche rien (anti-invention).

## v3.43 — Multimodal élargi : diplômes / relevés / attestations scannés
- Avant, une image qui n'était ni un CV ni une annonce était rejetée (« pas un CV »). Désormais le bot reconnaît aussi un **document académique** (diplôme, relevé de notes, attestation, certificat) pris en photo : il le **lit** (vision), en extrait les infos clés (intitulé, établissement, année, mention) de façon **ancrée** (anti-invention : au moins l'intitulé ou l'établissement doit figurer dans le texte source), et répond **utilement** (« voici ce que j'en lis · tu peux le joindre à un dossier · /dossier <programme> »). Le multimodal ne se limite plus à CV + annonce.

## v3.42 — Observabilité : journal des « ratés » de compréhension
- Pour viser l'excellence (OODA), il faut apprendre des VRAIS échecs. Le bot journalise désormais ce qu'il ne comprend pas : messages tombés sur le repli générique (ni action ni réponse du LLM) et documents/images rejetés (ni CV ni annonce). Nouvelle commande admin **/misses** (ou en langage naturel « ratés », « incompris ») qui liste les derniers cas, groupés par type — chaque ligne est une occasion d'amélioration (mot-clé à ajouter, cas à gérer). Le `/stats` affiche aussi un compteur « messages non compris ». Léger, best-effort, aucune donnée sensible au-delà du message.

## v3.41 — Boîte à outils mise en avant (menu dédié)
- La boîte à outils (créer un CV, extraire le texte d'un scan/OCR, compresser PDF/image, fusionner, images↔PDF) existait mais n'était accessible qu'en tapant `/outils` — invisible pour la plupart. Désormais un bouton **🧰 Outils** figure au **premier niveau du menu**, avec un **sous-menu dédié** qui expose chaque outil en un clic (sur tous les canaux). Plus facile d'en tirer parti.

## v3.40 — Offre en photo : affiche « RECRUTE » + légende enfin comprises
- Retour testeur (récurrent) : une affiche « *UMO RECRUTE AU BÉNIN · LOGISTICIEN/MAGASINIER* » + légende « je peux postuler à cette offre » répondait encore « *Il ne ressemble pas à un CV* ». Deux causes corrigées :
  1. L'heuristique exigeait **2 indices** d'opportunité ; une affiche courte « X RECRUTE » n'en a qu'un. Désormais un **signal fort** (« recrute », « nous recrutons », « avis de recrutement », « poste à pourvoir »…) suffit — une affiche de recrutement est sans ambiguïté.
  2. La **légende/intention de l'utilisateur** (« offre », « postuler », « annonce »…) était **ignorée**. Maintenant, si l'utilisateur dit explicitement que c'est une offre, le bot lit l'image (vision) et l'analyse comme une annonce, même si l'OCR est pauvre.
- Résultat : le scénario « photo d'annonce + je peux postuler ? » fonctionne enfin de bout en bout.

## v3.39 — Qualité : CV (résumé) + projet d'études contrôlés
- Suite du durcissement qualité. (1) **CV** : le *résumé professionnel* (en-tête du CV) est maintenant contrôlé contre les clichés d'IA (il alimentait le CV sans vérification). (2) **Projet d'études / dossier** (`/dossier`, Campus France/bourses) : le projet généré n'avait AUCUNE QC — désormais il est vérifié (longueur, placeholder, clichés, **ancrage au profil** ET **spécificité au programme visé**) et **relancé** une fois s'il est générique ou hors-sujet. (3) Les lettres de **bourse** (via `generate_pack`) doivent explicitement mentionner le programme ciblé. Les documents envoyés à une école/un employeur sont donc concrets et personnalisés, pas du remplissage.

## v3.38 — Qualité des lettres/CV générés : anti-cliché + ancrage vérifié
- Le pack CV+lettre (le livrable que l'utilisateur montre à un employeur/une école) était déjà grounded et relancé sur défauts structurels, mais la QC ne vérifiait PAS les deux choses que le prompt exige. Ajoutées : (1) **détection des clichés d'IA** (« je suis convaincu que », « dynamique et motivé », « fort de mon expérience », « correspond parfaitement »…) — 2 ou plus → relance ; (2) **contrôle d'ancrage** — la lettre doit citer au moins UN élément CONCRET du profil (employeur, diplôme, compétence réels), sinon elle est jugée générique et relancée. La relance exige explicitement de nommer 2 faits réels et de bannir les clichés. Résultat : des lettres qui sonnent HUMAINES et personnelles, pas « IA ».

## v3.37 — Matching langage→commande : vocabulaire familier/local
- Le matching est déjà solide (3 étages : mots-clés déterministes → routeur d'intention LLM → routeur d'action LLM qui comprend les paraphrases et enchaîne 2 actions). Angle mort comblé : l'étage 1 (rapide, gratuit, résilient si le LLM tombe) ignorait le **vocabulaire familier/local** d'Afrique de l'Ouest. « je galère à trouver du **taf** », « je cherche du **boulot** », « je suis au **chômage** », « je veux **bosser** », « trouver un **job** » → désormais captés directement vers `/mobilite` (recherche grounded), sans appel LLM. Plus rapide, plus fiable, et marche même si le LLM est indisponible.

## v3.36 — Recueil PROACTIF de retours : bug d'abord, avis/témoignage ensuite
- L'aide existait (`/aide`, `/tuto`, `/menu`, `/outils`, `/commentpostuler`) mais rien ne sollicitait l'utilisateur. Désormais, après un vrai temps d'usage (~6 interactions, une fois), le bot invite à **signaler un bug** (qualité) ; bien plus tard (~tous les 30 échanges, rare), à laisser un **avis/témoignage** (preuve sociale). Jamais pendant un flux guidé ni une attente — non intrusif.
- Nouvelle commande **/avis** (alias /temoignage, /feedback) : recueille le témoignage, le transmet à l'admin (Telegram) et le journalise, avec mention de **consentement** avant tout partage (cohérent avec la règle « jamais de faux avis »). Utile pour alimenter la vitrine avec de VRAIS retours.

## v3.35 — Latence PERÇUE : indicateur « en train d'écrire… »
- La recherche d'offres fait 2 appels LLM séquentiels (~2-4 s) ; avant, l'utilisateur voyait un silence. Désormais le bot envoie un indicateur **« typing… »** (Telegram `sendChatAction`, Messenger `sender_action`) au début des opérations lentes (recherche `run_osint`, analyse CV/vision). Best-effort, jamais bloquant. La recherche web elle-même était déjà **parallèle** (`asyncio.gather`) et **cachée** — la latence réelle est surtout les 2 appels LLM, incompressibles sans perte de qualité ; on améliore donc le RESSENTI.

## v3.34 — Dashboard admin : la DEMANDE réelle (domaines cherchés) + reconversions
- Le `/stats` admin (déjà riche : funnel CV→onboardés→payants, activation/conversion/rétention, canaux, objectifs, codes, top sources marketing) gagne deux signaux décisifs : **🔎 Demandes** = les domaines les plus cherchés par les utilisateurs (sais quelles sources prioriser, et montre la demande au jury), et **🧭 Reconversions en cours**. Zéro donnée personnelle, juste des agrégats.

## v3.33 — Qualité du digest quotidien : plus jamais d'offre clôturée
- Le digest (`/api/notify`) filtrait déjà par score (≥60, meilleures d'abord) mais pouvait **envoyer une offre dont la deadline est passée** (plainte testeur n°1 : « bourse déjà clôturée »). Désormais toute offre à **deadline dépassée** est **exclue du digest** (et purgée du pool pour ne pas revenir). Si tout le lot du jour est périmé, on **n'envoie pas** de digest vide/trompeur. Le compteur « N sélectionnées » reflète les offres réellement envoyées.

## v3.32 — Harnais de scénarios pièges élargi (QA proactive)
- +6 scénarios de bout en bout dans `tests/test_scenarios.py` (15 au total), pour attraper les régressions AVANT les testeurs/le jury : commande admin refusée hors admin, suppression qui exige confirmation, reconversion détectée à la validation (→ formations), réponse ambiguë à la confirmation qui ne réinitialise pas, re-ciblage en conversation, et messages vides/emoji sans crash. 443 tests au total, verts.

## v3.31 — Re-ciblage EN CONVERSATION (la logique suit partout)
- Dernier maillon de cohérence du conseiller. Avant, quand un utilisateur **déjà onboardé** disait « je veux aller en finance » / « finalement je préfère le marketing », le bot **conseillait** mais ne mettait **pas à jour son profil** ni ne relançait la recherche — la cible stockée (et le digest quotidien) restaient sur l'ancien domaine.
- Désormais un **détecteur de bascule** (`_detect_target_switch`) repère un changement explicite de domaine, **met à jour le profil** (`mots_cles`/objectif), **ré-évalue la reconversion** (CV ≠ nouvelle cible → question bases/zéro) et **relance la recherche** (`/mobilite <domaine>`) ou les **formations** si zéro base. Message clair : « 👍 Ok, je recentre sur *finance*. » La logique conseiller s'applique maintenant aussi EN conversation, pas seulement pendant l'onboarding.

## v3.30 — Fin de l'onboarding ambigu (question + récap empilés) + pas de reset accidentel
- **Bug testeur grave.** Le bot posait « Dans quel pays… finance ? » **ET** affichait le récap « Oui/Non » en même temps. L'utilisateur répondait « Au Bénin » → pris pour « ni oui ni non » → **tout l'onboarding était réinitialisé** (« Pas de souci, on reprend »). Frustration + perte de profil.
- **Correctifs :**
  1. L'onboarding ne déclare JAMAIS le profil « prêt » tant qu'il pose une question (plus d'empilement question + confirmation).
  2. Prompt durci : dès que l'objectif et le domaine sont connus, le bot NE demande plus le pays pour un emploi (local par défaut) et conclut par un message court sans question.
  3. À la confirmation, une réponse **ambiguë** (ni oui ni non) ne réinitialise plus rien : le profil est conservé, on tente une correction de champ, sinon on re-propose proprement. Seul un **« non » explicite** réinitialise.

## v3.29 — Invariant de robustesse : jamais de silence sur un crash
- Audit de bout en bout. Faille trouvée : si une fonction plantait de façon **inattendue**, l'erreur était loguée mais **l'utilisateur ne recevait rien** (silence = bot « cassé » à ses yeux). Désormais `route_incoming` garantit l'invariant : quoi qu'il arrive, l'utilisateur reçoit une **réponse propre** (« petit souci technique, réessaie… /contact »), jamais un silence ni un stacktrace. L'admin est informé via les logs (`exc_info`).

## v3.28 — Reconversion : formations dans le bon domaine, plus d'offres de l'ancien métier
- **Bug testeur (non listé avant, corrigé).** Après avoir parlé de finance (reconversion « de zéro »), le bot promettait « *commence par une formation… /formations finance* » mais affichait ensuite **3 offres de Développeur Web** (l'ancien domaine). Deux causes :
  1. **Zéro base → on montrait des offres d'emploi** au lieu de formations. Désormais, pour une reconversion *sans base*, le bot enchaîne sur des **formations dans le domaine CIBLE** (`/formations <cible>`), pas des offres.
  2. **La recherche ressortait l'ancien métier** : les mots-clés de recherche incluaient les compétences/poste du CV (Python, PHP, « développeur »…). Quand une reconversion est **confirmée** (flag `reconversion_active` posé après la réponse à la question d'orientation), la recherche se concentre sur le **domaine visé uniquement** — fini les offres de dev pour quelqu'un qui vise la finance. (Hors reconversion, rien ne change : les compétences restent utilisées.)

## v3.27 — Annonce en photo lue par la vision + récap épuré
- **Bug testeur.** Une *photo d'annonce* (bannière AltEmploi « Réceptionniste… Nous recrutons… Postulez ») + « je peux postuler ? » renvoyait « *Il ne ressemble pas à un CV* ». Cause : ces visuels stylisés (texte sur photo) font échouer l'OCR tesseract, donc aucun texte à analyser. Correctif : repli **VISION** (`extract_text_vision`, Gemini) qui lit le texte de l'image quand l'OCR ne donne rien d'exploitable → l'annonce est alors analysée normalement (compatibilité + comment postuler). Le multimodal ne dépend plus d'un OCR qui bute sur les affiches.
- **Récap d'onboarding épuré.** On n'affiche plus les lignes vides (« Nationalité : — », « Financement : — »…). Seuls l'**Objectif**, les **Mots-clés** et les champs réellement renseignés apparaissent → onboarding plus court et lisible. Rappel ajouté qu'on peut corriger un champ (« pays : France »).

## v3.26 — Libellé de reconversion propre
- La question de reconversion affichait « ton CV est plutôt en *Licence JavaScript PHP Python SQL* » (empilement diplôme + compétences, moche). Nouveau `_cv_domaine_label` : affiche le **domaine de formation réel** s'il existe, sinon 2 compétences clés (« JavaScript, PHP »), jamais les mots de diplôme. La DÉTECTION de reconversion reste inchangée (elle, utilise le texte brut). Note : la détection et le déclenchement à la validation (v3.25) sont confirmés OK sur le profil réel testé.

## v3.25 — Conseiller d'orientation poussé au max (OODA senior)
- **Le conseiller intervient au moment décisif.** Avant, la question de reconversion / clarification n'était posée que sur un `/veille` explicite ultérieur. Au **premier résultat juste après la validation du profil**, le bot montrait des offres génériques et ratait le moment conseiller. Désormais, dès que le profil est validé, si une **reconversion** est détectée (ou une info vraiment cruciale manque), le bot pose **une** question d'orientation (bases/zéro, pays, niveau…) *avant* les offres — la recherche se relance toute seule après la réponse. C'est l'impression la plus importante pour ne pas perdre l'utilisateur.
- **Reconversion mieux détectée (quelles que soient les questions).** (1) Elle fonctionne maintenant aussi pour un profil **construit via /creercv** (sans CV uploadé), pas seulement sur un CV analysé. (2) Une mention **explicite** (« je me reconvertis », « changer de domaine/métier/voie », « me réorienter », « transition pro »…) déclenche la question même si les mots-clés se recoupent par hasard. (3) Pas de faux positif quand aucun passé n'est connu.
- Rappel du flux conseiller (inchangé mais désormais branché partout) : part de zéro → on oriente d'abord **formation/certification** (`/formations <domaine>`) puis des pistes débutant ; a des bases → on vise **débutant/junior + alternance**.

## v3.24 — Reconversion respectée + fin du « télétravail » fantôme (bug vidéo)
- **Bug vu en démo.** Un profil informatique qui répond « Je cherche un emploi dans la finance » voyait le récap garder les mots-clés du CV (JavaScript, PHP, SQL…) au lieu de « finance », et afficher un « Type de poste : télétravail » que l'utilisateur n'avait jamais demandé.
- **Cause 1 (mots-clés).** L'onboarding LLM n'écrivait un champ que s'il était vide (`not prefs.get(k)`). Or `mots_cles` était PRÉ-REMPLI depuis le CV → la mention explicite « finance » était ignorée. Désormais une devinette issue du CV est **écrasable** par ce que l'utilisateur dit explicitement, + filet déterministe (`_normalize_objectif`) qui force les mots-clés sur le domaine nommé (« dans la finance » → `finance`), même si le LLM le rate. C'est la base pour détecter correctement une reconversion.
- **Cause 2 (télétravail fantôme).** `_is_remote` scannait TOUT le dialogue récent, y compris les **aperçus d'offres postés par le bot** (qui contiennent souvent « Télétravail ») → faux positif. Il ne regarde plus que les messages de l'**utilisateur** (`_recent_user_text`).

## v3.23 — 2e lot de sources admin vérifiées + couverture sous-région / remote / ONG
- Admin a confirmé 3 des 4 domaines restants (pages d'offres datées à l'appui) → ajoutés au Bénin : **matchworks.app, beninformations.bj, optioncarriere.bj** (+ **jobartis.com**). **gdiz-benin.com écarté** : site indexé mais postes affichés « Closed », aucune offre ouverte datée (critère non rempli).
- **Sous-région** enrichie (offres datées, indexation confirmée) : Côte d'Ivoire (emploi.educarriere.ci, novajobs.ci, toumodi-jobs.com), Sénégal (emploi.educarriere.sn, emploi.gouv.sn), Cameroun (emploi.cm, jobinfocameroun.com, recrutement.cameroun247.com).
- **Bourses/opportunités** : ajout de heysuccess.com (entré dans le top-7 ciblé par `site:`), opportunitiescircle.com, fundsforngos.org, 2ie-edu.org (institution francophone africaine). Le slice de requête passe de 6 à 7 portails.
- **Remote/tech** : la requête télétravail cible aussi remote.co et wellfound.com. **ONG/dév** : ajout de ngojobsonline.com (agrégateur bien indexé).
- Non câblés volontairement : les portails carrières JS d'agences (careers.unicef.org, who.int, fao.org, msf…) sont mal indexés comme LinkedIn — ils remontent déjà via les agrégateurs (ReliefWeb, UNjobs, Impactpool). Les plateformes très niche (volontariat Europe, échanges) restent branchables sans redéploiement via `LOCAL_SOURCES_EXTRA_<PAYS>`.

## v3.22 — Sources soumises par l'admin, vérifiées & ajoutées
- Liste de sources transmise par l'admin, **vérifiée une par une** (recherche web réelle, aucune invention). Ajoutées car confirmées actives et indexées : **Bénin** — emploi.bsmgroupe.com, setondji.org, cadreannonces.com, emploi-pipeline.gouv.bj (portail officiel). **Bourses/opportunités** — opportunitiesforyouths.com. **Nouvel angle ONG / développement / ONU** pour les recherches d'emploi (très présent au Bénin, et sur des agrégateurs bien indexés contrairement à LinkedIn) : reliefweb.int, unjobs.org, devex.com, impactpool.org.
- Non ajoutées faute de confirmation d'indexation (le `site:` ne remonterait rien) : matchworks.app, beninformations.bj, optioncarriere.bj, gdiz-benin.com. À ré-soumettre si elles sont confirmées actives, ou à brancher sans redéploiement via `LOCAL_SOURCES_EXTRA_BENIN`.

## v3.21 — Couverture emploi élargie (trou LinkedIn) + sources locales enrichies
- **Trou LinkedIn comblé (autant que possible).** LinkedIn est volontairement mal indexé par les moteurs de recherche (anti-robots) : beaucoup d'offres LinkedIn ne sont donc PAS récupérables par une recherche, et le scraper direct de LinkedIn est interdit par ses CGU. La recherche d'emploi combine désormais LinkedIn avec des **agrégateurs bien indexés qui re-listent les mêmes annonces** (Jooble, Indeed, Glassdoor, goafricaonline) dans une requête placée tôt — avant la requête locale — pour que même les comptes gratuits (2 requêtes) en bénéficient. Résultat : couverture nettement plus large pour les mêmes recherches.
- **Sources locales enrichies (recherche web réelle, aucune invention).** Bénin : ajout de goafricaonline.com/bj, bj.coinafrique.com, emploibougebenin.com. Côte d'Ivoire & Sénégal : go Africa Online local. Portails ONG/humanitaire panafricains : emploihumanitaire.org, humanitairehub.com, pageshumanitaires.com. Bourses francophones : CampusBourses (Campus France), Le Boursier, Scholarships For Africans, bourses-etudes-africains.info.
- **Adzuna confirmé câblé** (aucun changement de code nécessaire) : visible via `/version` (module « Adzuna ») et `/api/admin/health` (`adzuna_configured`). Alimente le pool d'offres via `/api/collect` quand `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` sont présents.
- **Isolation des tests** : les tests pointent désormais la base SQLite sur un fichier temporaire jetable (`conftest.py`) ; fin des échecs intermittents dus aux compteurs de quota qui persistaient sur `data/sessions.db` d'un run à l'autre.

## v3.20 — OSINT : portails d'opportunités panafricains ciblés
- Comble l'angle mort des bourses LOCALES. Avant, la recherche de bourses ne ciblait que des programmes internationaux (Campus France, DAAD, Erasmus, Chevening). Désormais une requête supplémentaire cible activement les portails d'opportunités panafricains/francophones réels (GreatYop, Opportunities For Africans, Opportunity Desk, After School Africa, Youth Opportunities…) via `site:`. Les ressources comme greatyop.com remontent donc dans les résultats, pas seulement par hasard. (Les emplois étaient déjà bien couverts : sources locales par pays + régionales + boards + feeds ingérés.)

## v3.19 — Analyse d'un lien PORTAIL (liste d'opportunités)
- Retour testeur : coller une page qui LISTE plusieurs bourses/offres (portail, page « destination », agrégateur comme greatyop.com) était rejeté sèchement (« ce lien ne ressemble pas à une offre exploitable »). Désormais le bot reconnaît une page-portail : il en fait un résumé utile + quelques exemples visibles, et guide vers le lien d'UNE opportunité précise (ou /veille). Un filet de sécurité guide aussi quand la page est clairement pleine d'opportunités mais mal structurée. Plus de rejet frustrant d'une ressource légitime.

## v3.18 — Admin en langage naturel (Telegram)
- Le compte admin peut piloter sans taper de slash : « stats » → tableau de bord, « les annonces » → file des offres recruteurs, « valide 3 » / « valide l'offre 7 tous » → diffusion, « refuse 5 », « codes valides » / « codes utilisés », « diffuser <message> », « voir annonce 9 », « génère des codes premium »… `_admin_nl_route` est déterministe (zéro coût LLM), réservé au compte admin et désactivé pendant les flux guidés (pour que l'admin puisse aussi tester les parcours candidats).

## v3.17 — Sécurité : plus de flag d'attente coincé
- Audit de bout en bout : correction d'un risque réel. Les états « en attente de réponse » (confirmation de suppression, question de reconversion, clarification, demande de domaine) n'étaient levés que par une réponse en texte. Si l'utilisateur lançait une COMMANDE à la place, le flag restait coincé — au pire, un « oui » bien plus tard pouvait déclencher une suppression de données non voulue. Désormais, toute commande annule proprement une attente en cours (sauf la poursuite directe « /supprimer confirmer »).

## v3.16 — Quota : l'analyse photo d'annonce est décomptée
- Correctif de maîtrise des coûts : l'analyse d'une annonce prise en photo (multimodal v3.10) passait le contrôle de quota mais n'était jamais **décomptée** — un compte gratuit pouvait en enchaîner sans limite (seul le anti-spam 20/min la bornait). Elle décompte désormais le quota `cv` (comme une analyse de CV, puisque c'est le même coût vision/LLM). Les abonnés et l'admin restent illimités.

## v3.15 — Ceinture + bretelles : analyse CV relancée si coupée
- Garantie anti-troncature complète : si l'analyse d'un CV revient malgré tout coupée par la limite de tokens (résumé ou dernier item de bilan qui finit en l'air, ex. « …en Europe ou »), le bot **relance automatiquement l'analyse une fois** avec une grosse marge (6000 tokens, texte comme vision) et garde le meilleur résultat. Combiné à la marge relevée (v3.14) et au nettoyage `_tidy_frag`, la troncature visible ne peut plus arriver. `_profil_looks_truncated` détecte aussi les mots de liaison pendants que l'ancien détecteur ratait.

## v3.14 — Fin de la troncature de l'analyse CV
- Le récap d'analyse de CV se coupait parfois en plein milieu (ex. « …en Europe ou »). Deux causes traitées : (1) la limite de tokens de l'analyse (texte ET vision) est relevée (2500 → 3500) pour que le JSON ne soit plus tronqué à la source ; (2) filet de sécurité `_tidy_frag` sur les atouts/axes/pistes du bilan — un fragment qui finit sur un mot de liaison pendant (« …en Europe ou ») est nettoyé proprement avec « … », sans ajouter d'ellipse aux phrases complètes.

## v3.13 — Candidature adaptée à l'OFFRE précise (inspiré de CVMove)
- La lettre de motivation ne vise plus une cible générique : quand on candidate à une offre qu'on vient d'analyser (lien, photo, ou offre choisie), la lettre est **adaptée à CETTE annonce** — elle reprend l'intitulé, la structure et les *exigences clés* de l'offre et montre en quoi le profil y répond. Le contexte de l'offre (`offer_ctx`) est mémorisé à l'analyse et injecté dans `generate_pack`. `/postuler` sans argument candidate directement à la dernière offre analysée. C'est le « done-for-you par offre » qui fait la force des meilleurs outils — mais branché sur notre grounding (jamais d'invention) et notre public.

## v3.12 — QC étendu : l'analyse à-une-offre doit être ancrée dans la source
- Fermeture du dernier trou de QC : l'analyse d'une **annonce photo** et l'**audit d'un lien** passent désormais une 2e vérification (`_opp_grounded`) — l'offre extraite doit être SAINE (titre réel, pas de placeholder) ET **ancrée dans la source** (au moins un mot significatif du titre/organisation présent dans le texte lu). Une analyse qui ne correspond pas à la photo/la page est écartée, avec repli propre (« copie-colle le texte »). Le self-review couvre maintenant tout le spectre : listes de recherche ET analyses unitaires.

## v3.11 — Boucle d'agent : enchaîner deux actions (bornée)
- Le bot peut maintenant traiter une demande en DEUX temps dans un seul tour : « cherche une bourse ET dis-moi mes chances » → recherche puis évaluation, enchaînées. Le routeur conversationnel renvoie une 2e action optionnelle (`then`) ; elle n'est exécutée que si elle fait partie d'une liste BLANCHE d'actions de conseil sûres (`_CHAINABLE_ACTIONS` : chances, compatibilite, commentpostuler, formations, budget…), jamais une action à état ou à confirmation (creercv, publier, supprimer, 2e recherche…). Borné à 2 pas, repli sur une seule action en cas de souci. C'est la dernière brique de l'agent : raisonner → agir → enchaîner, sans jamais partir en vrille.

## v3.10 — Multimodal : analyser une annonce prise en photo
- Avant, toute image non-CV était rejetée. Désormais, si la photo/le scan est une *annonce d'opportunité* (offre d'emploi, bourse, stage), le bot la *lit* (OCR/vision), l'analyse comme un lien : titre, type, compatibilité avec le profil, éligibilité, critères, et *comment postuler* — puis propose la suite (`/commentpostuler`, `/chances`, `/postuler`). Idéal pour le public mobile : on voit une annonce sur un mur / un groupe, on la prend en photo, on obtient l'analyse. Détection `_looks_like_opportunity` + `_analyze_opportunity_text` (repli propre si illisible ou non pertinent). Le message de non-CV est aussi plus utile (propose CV / offre / lien / texte).

## v3.9 — Conseiller : un plan B quand les chances sont faibles
- `/chances` ne se contente plus de dire « c'est difficile ». Quand le score est faible (< 45), le bot propose une *alternative réaliste et plus accessible* (autre pays plus ouvert, financement par bourse plutôt qu'auto-financement, poste junior/alternance, programme-passerelle) avec une justification, et un raccourci pour l'évaluer tout de suite (`/chances <plan B>`). Comme un conseiller : ne pas laisser quelqu'un dans une impasse, lui ouvrir une porte. Aucun appel LLM en plus (champ `plan_b` ajouté à l'estimation existante).

## v3.8 — « Clarifier avant d'agir » (mécanisme général)
- Généralise ce qu'on faisait pour la reconversion/le domaine à TOUTE recherche : avant de lancer, le bot évalue (1 appel LLM rapide) s'il manque UNE information vraiment cruciale (pays visé pour des études, niveau/diplôme pour une bourse, type de contrat, budget…). Si oui, il pose UNE question courte, mémorise la réponse (dans le bon champ de préférences) puis relance la recherche ; sinon il agit directement. C'est le cœur du raisonnement d'un conseiller : ne pas chercher à l'aveugle.
- Sûr par conception : **une seule fois par session** (jamais de harcèlement de questions), priorité aux gates déterministes (domaine, reconversion), et **repli systématique sur « on cherche quand même »** si le modèle est indisponible ou n'identifie rien. Première brique de la boucle d'agent (l'étape « demander une précision »), sans l'enchaînement multi-pas (gardé pour après le salon).

## v3.7 — Conseiller : la reconversion débouche sur un vrai plan
- Après avoir détecté une reconversion et demandé les bases, le bot AGIT selon la réponse, comme un conseiller : s'il part de *zéro*, il oriente d'abord vers une *formation/certification* (le pont crédible) via `/formations <domaine>` + des offres *débutant* ; s'il a *déjà des bases*, il vise directement *débutant/junior* et *alternances* pour les valoriser. Le niveau est ajusté (`niveau=débutant`) pour que la recherche et les scores soient réalistes. Détection via `_reconv_has_base` (oui/non/incertain).

## v3.6 — Conseiller senior : reconversion clarifiée + suppression confirmée
- **Reconversion comprise, pas subie** : quand le domaine du CV ne recouvre pas la cible (ex. CV comptabilité → objectif informatique), le bot ne lance plus une recherche à l'aveugle. Comme un conseiller d'orientation, il demande UNE fois : « c'est une reconversion ? as-tu une formation/des bases, ou tu pars de zéro ? », mémorise la réponse (profil profond) puis lance la recherche ciblée. Posé une seule fois (mémorisé), sur /veille et /mobilite.
- **Suppression de données confirmée** : `/supprimer` (et variantes) demande désormais une *confirmation* avant d'effacer (action irréversible). On confirme par « /supprimer confirmer » ou « OUI », on annule par « NON ». Plus d'effacement accidentel en un tap.

## v3.5 — Objectif compris, pas recopié (+ reconversion captée)
- En onboarding scripté, répondre « je cherche un emploi dans l'informatique est-ce possible » stockait la **phrase entière** comme objectif (vilain récap, recherche polluée). Désormais `_normalize_objectif` en extrait l'**objectif canonique** (travailler / étudier / bourse / télétravail / tous) ET le **domaine** mentionné (« informatique »), qui alimente les mots-clés. Marche même si l'onboarding LLM est désactivé.
- Bonus **reconversion** : un comptable qui dit viser l'informatique voit ses mots-clés passer à « informatique » (prioritaire sur les compétences du CV) → la recherche cible le bon domaine.

## v3.4.2 — Finitions pour la démo (liens, récap, /supprimer)
- Aperçu d'offres après le CV : les liens sont désormais **raccourcis** (fini les URL techniques à rallonge type `jobbenin.com/index.php/offres/eyJpdi6…` sur WhatsApp).
- Récapitulatif du profil : la **langue des offres** ne s'affiche plus en liste brute `['fr', 'en']` mais « français, anglais » ; un objectif trop long est raccourci. Rendu via `_fmt_pref`.
- La commande d'effacement accepte les variantes `/supprime`, `/supprimé`, `/effacer`, `/reset`, `/purger` (avant, seul `/supprimer` exact marchait).

## v3.4.1 — Correctif : nom du MODÈLE de CV pris pour le nom de la personne
- Sur un CV fait avec un modèle (Canva, Word…), le bot pouvait afficher le nom du *template* (ex. « Français Simple Moderne », tiré du fichier `CV Français Simple Moderne Bleu.pdf`) au lieu du vrai nom (ex. GANSE MARTHE). Corrigé à 3 niveaux : (1) prompts d'extraction (texte + vision) durcis — `identite.nom` = vrai nom de la personne, jamais un nom de modèle/style/fichier ; (2) garde-fou `_looks_like_template_name` qui rejette un « nom » composé uniquement de mots de template/style ; (3) le repli par nom de fichier filtre aussi ces mots. Si aucun vrai nom n'est trouvé, le bot le dit et demande le nom au lieu d'en inventer un.

## v3.4 — Proactivité ciblée revenu + harnais d'évaluation
- **Proactivité mesurée (#4)** : nouveau `/api/nudge` qui ne relance PAS tout le monde, mais le segment à plus forte intention d'achat — un **recruteur ayant déposé une offre en attente et sans crédits** → rappel ciblé d'acheter des crédits pour la diffuser. Cap anti-spam (`NUDGE_COOLDOWN_H`, 48 h), opt-out respecté, on ne dérange pas ceux qui ont déjà des crédits. (Le digest d'offres `/api/notify` et les relances d'inactifs `/api/relances` existaient déjà.)
- **Harnais d'évaluation (#7)** : `tests/test_scenarios.py` rejoue des dialogues-pièges de bout en bout (dépôt d'offre recruteur, question non stockée en création de CV, /annuler, lien YouTube non audité, vrai lien audité, version déterministe, anti-répétition mémoire). Filet de sécurité à chaque déploiement.

## v3.3 — Mémoire qui compose (continuité d'une session à l'autre)
- Le bot garde désormais une **mémoire durable du parcours de chaque utilisateur avec lui** (`profil["memoire"]`) : les offres déjà montrées et un journal des événements clés (recherche, CV généré, score estimé…).
- **Anti-répétition cross-session** : les recherches (`/veille`, `/mobilite`, digest) écartent les offres déjà vues lors des fois précédentes → chaque recherche propose du **nouveau**, au lieu de reservir les mêmes liens. Mémorisation en place sur la session (sans course de données), bornée (80 offres, 15 événements).
- **Contexte enrichi** : le routeur conversationnel voit « déjà fait ensemble » et le nombre d'offres déjà proposées, pour rebondir dessus et donner une vraie continuité (« la dernière fois tu regardais X… »). Base du moat : plus l'utilisateur revient, meilleur c'est.

## v3.2 — Confiance calibrée (honnêteté sur les jugements à enjeu)
- Les estimations de chances ne donnent plus un chiffre faussement précis. `/chances` affiche maintenant un **niveau de confiance** (🟢/🟡/🔴 selon la richesse des infos), une **fourchette** réaliste (ex. « 52/100 · fourchette 45–60 ») et un **cadre honnête** (« estimation indicative, pas une garantie — l'issue dépend aussi du dossier complet et du jury/employeur »).
- Directive de confiance calibrée (`_CONFIANCE_DIRECTIVE`) réutilisable, aussi appliquée à l'analyse d'un lien (admissibilité). La fourchette est nettoyée/validée (cohérente avec le score, bornée 0-100), sinon masquée. Renforce la confiance des utilisateurs : le bot assume ce qu'il ne sait pas au lieu de bluffer.

## v3.1 — Relecture systématique des résultats (self-review)
- Nouvelle passe de **relecture qualité** (`_qc_review_offers`) sur les offres réelles avant affichage : un dernier regard LLM écarte les cas clairement mauvais que les filtres déterministes ratent (hors-sujet pour le profil, mauvais type, deadline manifestement passée, portail générique sans offre précise) et corrige le conseil (ton juste, pas de fausse certitude). **Conservateur** (au doute on garde, ne vide jamais la liste), **économe** (1 appel rapide, seulement s'il y a ≥ 2 offres web) et **sûr** (repli = aucun changement si le modèle est indisponible). Première brique de la « couche de compréhension » appliquée à la qualité des sorties.

## v3.0.1 — Audit OODA : durcissement avant déploiement
- **Correctif critique** : les cues de « changement de sujet » dans les flux guidés étaient trop larges (« change », « stop », « arrête », « sortir »…) et auraient bloqué de vraies réponses (ex. *gestion du changement*, *arrêté* juridique, *stop motion*). Resserrés à des phrases d'abandon non ambiguës — en cas de doute, on stocke la réponse plutôt que de bloquer.
- **Routeur recruteur** : le repli LLM exige maintenant une confiance **haute** (mieux vaut rater un recruteur, qui peut taper /publier, que piéger un candidat sur une erreur du modèle gratuit).
- **Filtre deadline** : un intervalle « 2025-2026 » n'est plus écarté à tort — on se base sur l'année **maximale** citée (édition en cours gardée).
- **Barème de diffusion « à l'audience » (B)** câblé par défaut (wallet unique) : plancher 3 crédits + 1 par tranche de 50 destinataires + 3 si « à tous ». Ajustable par variables d'env.

## v3.0 — Couche de compréhension : le bot « fait les distinctions » 🎯
Jalon. NexMove ne devine plus seulement par mots-clés : il **raisonne sur ce que veut la personne** aux carrefours clés de la conversation. Quatre carrefours fiabilisés, base extensible pour la suite.

1. **Recruteur vs candidat** (v2.98) — routeur d'intention LLM `_route_intent` + `_wants_to_post_offer` : un employeur qui propose un poste n'est plus confondu avec un candidat qui en cherche, même en formulation inattendue.
2. **Question vs réponse** dans les flux guidés — pendant la création de CV ou le dépôt d'offre, une vraie question (« pourquoi tu demandes ça ? ») n'est plus enregistrée comme réponse : le bot y répond puis repose la question, sans polluer les données.
3. **Lien à analyser vs lien de passage** — `_should_audit_link` : coller un lien d'offre lance l'analyse, mais un lien YouTube / réseau social / WhatsApp / notre propre site n'est plus « audité » comme une opportunité.
4. **Changer de sujet en plein flux** — `_flow_input_kind` détecte « en fait, je préfère… » et propose de sortir proprement (/annuler) au lieu de stocker ça comme une réponse.

Méthode commune, économe et sûre : heuristique rapide d'abord (gratuit, instantané), routeur LLM seulement en cas d'ambiguïté, repli sur l'ancien comportement si le modèle est indisponible. Tout tourne sur les modèles gratuits — la couche « intelligence » est dans l'orchestration, pas (encore) dans un modèle premium.

## v2.98 — Routeur d'intention (le bot raisonne mieux sur ce qu'on veut)
- Nouveau **routeur d'intention piloté par le LLM** (`_route_intent`) : au lieu de deviner par mots-clés, le bot classe ce que veut la personne (recruteur qui propose un poste · candidat qui cherche · question · gestion de profil · salutation). Économe et sûr : la regex rapide tranche d'abord (gratuit, instantané), le routeur LLM n'est appelé qu'en cas d'ambiguïté réelle, et en cas d'échec on retombe sur l'ancien comportement.
- Premier branchement : la distinction **recruteur vs candidat** (`_wants_to_post_offer`). Un employeur qui formule son besoin autrement que prévu (« nous aurions un poste à faire connaître ») est maintenant bien dirigé vers le dépôt d'offre, sans jamais confondre avec un candidat qui cherche. Base réutilisable pour fiabiliser d'autres carrefours de la conversation.

## v2.97 — Le CV n'est plus redemandé à l'onboarding
- Après l'envoi d'un CV, le bot reposait parfois des questions dont la réponse figurait sur le CV (domaine, niveau d'expérience, langues). Désormais : (1) l'onboarding piloté par le LLM reçoit un **résumé du CV** (`_cv_brief` : domaine, compétences, postes, niveau, langues) avec consigne de **ne jamais redemander** ce qui y figure ; (2) le **niveau** (junior/mid/senior → débutant/intermédiaire/confirmé) est désormais pré-rempli depuis le CV, en plus des mots-clés et langues déjà gérés. Il ne reste en général qu'une seule question : l'**objectif** (emploi / études / bourse…), qui ne se déduit pas d'un CV.

## v2.96 — Sortie claire des flux guidés (CV / dépôt d'offre)
- En pleine création de CV ou dépôt d'offre, taper une commande (ex. `/statistiques`) renvoyait un sec « Réponds sans commande » sans dire comment sortir. Désormais le message indique clairement de taper **/annuler** pour lancer une commande, et distingue le cas « réponse trop courte » du cas « commande ».
- `/stats` accepte maintenant les alias `/statistiques` et `/stat` (évite de rester bloqué parce que la commande exacte n'était pas reconnue).
- Rappel : un texte simple (sans `/`) envoyé pendant la création de CV est enregistré comme **réponse** à la question en cours — d'où l'intérêt de `/annuler` avant de faire autre chose.

## v2.95 — Filigrane ATS corrigé + crédits de diffusion
- **Correctif qualité (régression v2.93)** : le filigrane diagonal polluait l'extraction du CV **ATS** (un robot de tri lisait « NexMove » 15× avant le nom). Désormais : filigrane visuel diagonal **uniquement sur le CV graphique** (destiné à l'œil humain) ; sur le CV **ATS** et les lettres, une seule mention discrète en **pied de page** qui ne gêne pas le parsing.
- **`/valider` sécurisé** : d'abord un **aperçu** (nombre de destinataires + coût en crédits + solde du recruteur, alerte si deadline passée), puis diffusion réelle seulement avec le mot `envoyer`. `force` pour diffuser sans débiter (offert). Plus de diffusion massive accidentelle, et blocage si l'offre a déjà été diffusée.
- **Crédits de diffusion** : une diffusion consomme des crédits du portefeuille du recruteur (barème configurable `DIFFUSION_BASE_COST` / `DIFFUSION_PER_RECIP` / `DIFFUSION_ALL_EXTRA` — plancher + par tranche de destinataires + surcoût « à tous »). Le recruteur achète ses crédits sur la **vitrine** (nouvelle section Recruteurs) qui redirige vers le **WhatsApp de l'admin** pour paiement manuel, reçoit un code `CRD-…` et l'active via `/credits`. Le débit est automatique à la diffusion, le recruteur est notifié de son nouveau solde.

## v2.94 — Dépôt d'offres par les recruteurs (payant, validé par l'admin)
- Un recruteur peut déposer une offre directement au bot : soit en langage naturel (« je veux publier une offre », « nous recrutons »… détecté automatiquement), soit via `/publier`. Le bot pose 9 questions (intitulé, entreprise, lieu, contrat, missions, profil recherché, rémunération, comment postuler, deadline) et annonce d'emblée que **la diffusion est payante** (tarif `RECRUIT_POST_PRICE`, contact `RECRUIT_PAY_CONTACT`).
- L'offre part en **validation chez l'admin** (notification avec tous les détails + commandes). L'admin dispose de : `/annonces` (file des offres en attente/validées/refusées), `/annonce_voir <id>`, `/valider <id>` (diffusion aux **candidats emploi**), `/valider <id> tous` (à tout le monde), `/refuser <id>`. Le déposant est notifié automatiquement de la validation ou du refus.
- Nouveau stockage `recruiter_offers` (RecruiterOfferStore) + ciblage `_recruit_targets` (candidats en recherche d'emploi, actifs 30 j par défaut). Les diffusions sont journalisées dans l'historique `/diffuser_log`.

## v2.93 — Filigrane NexMove (comptes gratuits) + suivi des codes
- Tous les documents générés par un compte GRATUIT (CV ATS/graphique, lettre, projet d'études, en PDF comme en .docx) portent désormais un **filigrane NexMove** : texte diagonal discret + mention « Généré gratuitement avec NexMove · passe en Premium pour un document sans filigrane ». Les abonnés (premium/pro/vip/admin) reçoivent le même document **sans filigrane**.
- Nouvelle commande admin `/codes` pour suivre les codes premium générés : `/codes` (tout), `/codes valides` (non utilisés), `/codes utilises` (déjà activés, avec qui et quand). Affiche aussi le total valides/utilisés.
- Rappel : un code premium collé tel quel dans la conversation (ex. `PRM-9Q5C7SW8`) active l'abonnement directement, sans taper de commande — la méthode de soumission « dans la conversation » fonctionne.

## v2.92 — Deadlines passées écartées + CV à la voix
- Filtrage des échéances renforcé : le prompt de sélection EXCLUT désormais explicitement toute opportunité dont la date limite est antérieure à la date du jour, et renseigne `deadline`/`deadline_iso` quand une date À VENIR est visible. Côté code, `_open()` ne se contente plus de `deadline_iso` : à défaut, il analyse le texte de la deadline et le titre (ISO, « 15 janvier 2024 », JJ/MM/AAAA, année seule révolue) pour écarter les bourses/offres déjà clôturées — conservateur (en cas de doute, l'offre est gardée ; « rolling/permanent » n'est jamais écarté). Corrige le retour testeur « il m'a proposé des bourses déjà clôturées ».
- Création de CV : rappel que l'on peut répondre par message *vocal* à chaque question (transcription automatique), au lieu de tout taper.

## v2.91 — Pays réel détecté depuis le numéro (toute la sous-région)
- Le pays « local » n'est plus un défaut : il est déduit de l'indicatif du numéro WhatsApp/Messenger (229 Bénin, 225 Côte d'Ivoire, 221 Sénégal, 228 Togo, 226 Burkina, 223 Mali, 227 Niger, 237 Cameroun, 234 Nigéria, 233 Ghana…), sinon la nationalité. L'outil cible donc les bons portails locaux pour CHAQUE pays de la sous-région.

## v2.90 — Télétravail = sans frontière géographique
- Pour une intention de télétravail/freelance, la recherche ne restreint PLUS au pays local : requêtes sans pays, ciblant les job boards remote (RemoteOK, Remotive, WeWorkRemotely, Jobicy) et plateformes freelance (Upwork, Malt, Freelancer), portée mondiale. Le prompt de sélection sait aussi que c'est du remote (aucune préférence locale).

## v2.89 — Demander le domaine avant une recherche générique
- Si l'utilisateur demande des opportunités SANS CV, sans mots-clés et sans expérience connue, le bot demande d'abord son DOMAINE/compétences (au lieu de sortir des offres génériques), puis lance la recherche ciblée sur sa réponse. Garde-fou qualité sur /veille et /mobilite.

## v2.88 — Nettoyage du bloc d'offres (conseil + raisons)
- Le conseil des offres ne fuit plus les index internes (« index 0/3/8 »), tutoie, et n'est plus coupé (coupe propre à la dernière phrase). Raisons des offres idem (anti-troncature). max_tokens de la sélection relevé.

## v2.87 — Fin de l'hallucination de « version » (et faits produit)
- À la question « Version ? » (ponctuation incluse), réponse DÉTERMINISTE via /version (la vraie version), dans n'importe quel état — fini le LLM qui inventait un numéro (« 2.4.1 »).
- Prompt pré-onboarding durci : ne JAMAIS inventer de version/prix/date de mémoire (renvoie vers /version et /offres).

## v2.86 — Onboarding conversationnel piloté par le LLM (refonte)
- L'étape PREFERENCES n'est plus un questionnaire scripté : un onboarding CONVERSATIONNEL mené par le LLM comprend n'importe quel scénario, extrait ce que la personne dit EXPLICITEMENT (sans rien inventer), répond toujours à ses questions/objections, et ne pose qu'une question utile à la fois (jamais nationalité/certifs pour du télétravail). Terminé dès qu'on connaît objectif + domaine.
- **Sans risque** : flag LLM_ONBOARDING (défaut on) + **repli automatique** sur l'ancien questionnaire scripté si le LLM échoue + plafond de tours. Réversible via .env.

## v2.85 — Onboarding adaptatif (anti-robot)
- **Détection télétravail/freelance** : on saute les questions de mobilité (nationalité, visa, certifs de langue, financement) qui n'ont aucun sens pour du remote — questionnaire minimal (domaine, langue, niveau). type_emploi mis à « télétravail » automatiquement.
- **Fini le robot qui ignore l'utilisateur** : si la personne pose une question au lieu de répondre (« tu en as besoin pour quoi ? »), le bot RÉPOND honnêtement (pourquoi on demande) puis repose/adapte la question — au lieu de stocker la question comme réponse et d'enchaîner.
- « tous » comme objectif ne force plus le parcours études complet (plus de nationalité/certifs inutiles).

## v2.84.1 — Durcissement anti prompt-injection
- Le contenu web d'un lien collé (et les résultats de recherche) sont désormais encadrés comme DONNÉES NON FIABLES avec consigne explicite d'ignorer toute instruction qui y figurerait. Risque déjà faible (sortie JSON contrainte, aucun outil agentique), désormais explicitement durci.

## v2.84 — Garde-fous coût (relecture senior)
- **Quota sur /veille et /mobilite** : jusqu'ici ces recherches (2 à 8 requêtes Tavily advanced + LLM) n'avaient AUCUNE limite, et les webhooks sont exemptés du rate-limiter -> risque de brûler le crédit Tavily/LLM. Ajout d'un quota journalier gratuit (FREE_VEILLE_DAILY=6, illimité premium/admin) + cooldown anti-rafale (VEILLE_COOLDOWN_SEC=8s).
- **Profilage progressif throttlé** : _enrich_profile (sur le chemin de réponse) limité à 1 extraction/minute/utilisateur (latence + coût maîtrisés).

## v2.83 — Profilage progressif (hors onboarding)
- Le bot enrichit le profil AU FIL des conversations, sans alourdir l'onboarding : quand la personne exprime explicitement une motivation, une aspiration, une contrainte, un centre d'intérêt ou un trait de savoir-être, c'est capté (déclenché seulement sur un message porteur d'indices, modèle rapide) et stocké dans profil_plus. N'invente rien : seulement ce qui est dit.
- Ce profil profond est injecté dans le contexte du routeur (réponses plus logiques et personnalisées) et affiché dans /profil (transparence : « ce que j'ai appris de toi »).

## v2.82 — Modèle smart via Gemini + profilage injecté dans le contexte
- **Tier smart conduit par le fournisseur préféré** (SMART_LEAD_PROVIDER, défaut Gemini) : meilleur suivi du contexte et des consignes anti-invention, chaîne de repli préservée. Tier "quality" (CV/lettre) reste configurable via OPENROUTER_GENERATE_MODEL.
- **Profilage "en profondeur" injecté** : points forts, axes à renforcer, savoir-être, séniorité et contraintes (déjà extraits du CV) sont maintenant donnés au routeur conversationnel, qui raisonne comme un conseiller d'orientation (réponses logiques et personnalisées, sans rien inventer).

## v2.81 — Fiabilité anti-troncature généralisée + ajout manuel d'offres
- **Anti-troncature partout** : helper réutilisable (_gen_text) qui détecte un texte coupé (ponctuation suspendue, parenthèse ouverte), relance avec plus de tokens, et coupe proprement à la dernière phrase complète (_trim_to_sentence). Appliqué au routeur des utilisateurs onboardés (tokens 380->650 + coupe propre), au pré-onboarding et au débrief de simulation.
- **Ajout manuel d'offres (admin)** : /offre <type> | <titre> | <url> | <description> | <local|intl> injecte une offre curée dans le pool de veille, proposée ensuite aux profils correspondants.

## v2.80.1 — Liens d'offres masqués + respect du type demandé
- **Plus d'URL technique affichée** : sur Telegram/Messenger le lien d'une offre est masqué derrière « 👉 Voir l'offre » (markdown) ; sur WhatsApp il reste nu (markdown non supporté). Domaine court configurable via SHORT_LINK_BASE (pour un sous-domaine brandé).
- **Respect du TYPE demandé** : si l'utilisateur demande un *emploi*, on ne lui sort plus de bourses/formations (et inversement). Détection à partir de la demande ET de l'objectif, appliquée aux requêtes et au filtrage de sortie.

## v2.80 — Signaler un bug avec une capture d'écran
- L'utilisateur peut maintenant joindre une **capture d'écran** à un signalement de bug :
  après */bug*, la prochaine image envoyée est transmise à l'**admin** (Telegram) avec le contexte
  (utilisateur, canal, description éventuelle). Fonctionne aussi en envoyant une image **légendée « bug »**.
- Garde-fou : un message texte normal annule l'attente de capture (un CV envoyé ensuite n'est pas pris pour un bug).
- Les captures de bug sont journalisées (/contacts_log) comme les autres retours.

## v2.79.1 — Qualité du premier contact (anti-réponse tronquée / à côté)
- **Pré-onboarding fiabilisé** : le premier échange passe sur le modèle "smart" (fiable) au lieu de "fast". Détection des réponses tronquées (phrase coupée, parenthèse ouverte) + relance automatique.
- **Plus jamais le pitch générique sur une vraie question** : si l'IA échoue, repli CONTEXTUEL qui relance utilement (et propose CV / /creercv), au lieu de renvoyer le bloc « NexMove c'est quoi ». Le pitch complet reste réservé aux vraies questions « c'est quoi ».

## v2.79 — Recherche multi-requêtes par tier + flux conditionnels + QC des offres
- **Multi-requêtes parallèles** selon le tier : 2 (gratuit), 3 (Premium), 4 (Pro), 5 (VIP), jusqu'à 8 (admin). Chaque requête couvre un angle différent (cœur, local, grands job boards, variantes mots-clés, télétravail, stage/alternance) ; résultats fusionnés et dé-doublonnés.
- **Flux structurés activés selon la requête** : le catalogue de sources (SOURCE_CATALOG) est fusionné au pool, filtré par TYPE (emploi vs bourse) et périmètre (local/intl).
- **Meilleure construction du profil de recherche** : termes dérivés des mots-clés visés, du dernier poste, du domaine de formation et des compétences (gestion des reconversions).
- **QC de sortie des offres** : on ne garde que des offres saines (titre réel, URL http, sans placeholder), titres/raisons nettoyés des symboles parasites ; filtrage sémantique pour tous.
- Fenêtre de sélection élargie selon le tier ; /collect en arrière-plan plafonné à 1 requête (coût). Tests ajoutés.

## v2.78 — Offres plus lisibles : 1 lien court par offre + sources affinées
- **Un seul lien propre par offre** : fini le domaine auto-lié + le lien de recherche + le lien source. Chaque offre affiche désormais UN lien court maison (service de raccourcissement intégré, /l/<code>), avec clic mesurable.
- **Message plus court** : mise en page compacte (type · score · deadline sur une ligne), 4 offres max, conseil resserré.
- **Dé-doublonnage par domaine** + préférence aux URL spécifiques (une vraie offre plutôt qu'une page de recherche générique).
- **Plus de sources** : recherche web élargie (12 résultats) avant sélection.
- Nouveau raccourcisseur de liens (table links), endpoint public /l/<code> (302 + comptage). Tests ajoutés.

## v2.77.3 — Zéro tiret cadratin (anti-marqueur IA) + en-tête épuré
- **Vitrine** : suppression de tous les tirets cadratins/demi-cadratins restants ; en-tête réduit à 4 liens ciblés (Fonctions, Tarifs, Testeurs, Soutenir) pour une UX plus claire, orientée présentation/financement.
- **Bot** : règle de style imposée au LLM (aucun tiret cadratin dans les réponses générées) + remplacement des 230 séparateurs " — " des messages par un point médian, sans toucher à la logique de parsing (regex de titres, marqueurs de champ vide préservés).

## v2.77.2 — Programme testeurs sur la vitrine
- Nouvelle section **Testeurs** : rejoindre le groupe WhatsApp des testeurs, demander un code Premium en message privé, et donner ses retours (/bug, /contact). Lien du groupe + CTA. Places limitées.

## v2.77.1 — Correctif « symbole carreau » dans les documents + 1er vrai témoignage
- **Bug corrigé** : un petit symbole « carré/case » (☐ □ ◻ ◆, puces, caractère de remplacement)
  pouvait apparaître dans le CV ou la lettre générés. `_sanitize_doc_text` nettoie désormais tout
  document produit (CV ATS/graphique, lettre PDF & Word), le QC de sortie le détecte et relance,
  et le prompt de génération interdit explicitement ces symboles.
- **Vitrine** : les témoignages d'exemple (fictifs) sont retirés ; remplacés par le **premier vrai
  retour d'utilisateur** (verbatim, anonymisé) + une carte d'invitation pour les suivants.

## v2.77 — Signalement de bug, anti-hallucination généralisé, QC de sortie renforcé, diffusion ciblée
- **Signaler un bug** : nouvelles commandes `/bug` (`/probleme`, `/signaler`) qui transmettent
  directement le message à l'admin (Telegram) et le journalisent (`/contacts_log`). `/contact`,
  `/support`, `/rencontrer` existaient déjà pour les retours généraux.
- **Anti-hallucination GÉNÉRAL** : règle anti-invention (dates, montants, frais, noms de
  programmes/universités/entreprises, URL, procédures) injectée dans TOUTES les réponses
  conversationnelles via `CONSEILLER_PERSONA`, pas seulement la recherche d'offres. En cas de
  doute, le bot le dit et renvoie vers la source officielle au lieu de deviner.
- **Vérification de sortie renforcée** : `_pack_quality_issues` contrôle chaque document généré
  (lettre non vide et de bonne longueur, titre et résumé présents, AUCUN placeholder type `[nom]`,
  `XXX`, « à compléter », compétences non vides) et relance une fois la génération si besoin.
- **Diffusion admin ciblée** : `/diffuser` (`/broadcast`) envoie une annonce/publicité aux
  utilisateurs filtrés par profil (`objectif:` `pays:` `tier:` `canal:`). Aperçu du nombre de
  destinataires par défaut, envoi réel avec le mot `envoyer`. Note WhatsApp (fenêtre 24 h / modèles).
  Par défaut **seuls les utilisateurs actifs (30 j)** sont ciblés (ajouter `tous` pour inclure les
  dormants). Chaque diffusion est **journalisée** (`/diffuser_log`, table `broadcasts`).
- **Filet anti-placeholder global** : `deliver_text` nettoie tout message sortant des placeholders
  résiduels (`[nom]`, `[entreprise]`, `XXX`, `{{…}}`) — sans toucher la syntaxe d'aide `<…>`.
- **Boucler le canal bug** : commande admin `/repondre <user_id> <message>` pour répondre
  directement à un utilisateur suite à un `/bug` ou `/contact`.
- **Panel web admin** : nouveaux blocs *Diffuser* (aperçu + envoi), *Bugs & contacts* et
  *Diffusions récentes* dans `admin.html` (endpoints `/api/admin/contacts` et `/api/admin/broadcast`).
- Tests ajoutés (QC sortie, parsing/ciblage/dormants diffusion, scrub placeholders). 265 tests au vert.

## v2.76 — CV ATS + CV graphique (au choix) + vérification de sortie
- **Deux styles de CV** : `/cv ats` (sobre, lisible par les robots de tri), `/cv graphique`
  (bandeau coloré, envoi direct) ou `/cv deux`. Le bot propose le choix (boutons) et à la fin de /creercv.
  `build_cv_pdf(..., style=...)`.
- **Vérification de sortie** : la génération CV/lettre (generate_pack) refait une passe si la lettre
  est vide/trop courte avant envoi.

## v2.75 — Dashboard de traction + rédaction premium (optionnelle)
- **Dashboard de traction** : /stats et le panel web affichent le FUNNEL (users → CV → onboardés →
  payants) + taux d'**activation**, **conversion**, **rétention 7j**, **inscriptions/jour (14j)**,
  répartition par **canal** et **objectif**. Idéal pour présenter la traction à un financeur.
- **Rédaction CV/lettre premium** (optionnelle) : nouveau niveau `tier="quality"` — si
  `OPENROUTER_API_KEY` est présent, la génération passe par un modèle premium configurable
  (`OPENROUTER_GENERATE_MODEL`, ex. `anthropic/claude-3.5-sonnet`), sinon fallback standard.
- Section Témoignages prête (à remplir avec de VRAIS témoignages). Tests ajoutés.

## v2.74 — Bandeau Campus France + ciblage LinkedIn (OSINT temps réel)
- **Vitrine** : bandeau de lancement « Campagne Études en France » au-dessus du hero (modifiable/supprimable).
- **Recherche temps réel (OSINT/Tavily)** : pour les recherches d'EMPLOI, la requête fait désormais
  remonter les grands job boards (LinkedIn, Indeed, Glassdoor) → plus d'offres LinkedIn dans les résultats.
  (Rappel : LinkedIn est couvert via la recherche web live, pas d'API dédiée — impossible gratuitement.)

## v2.73 — Témoignages (vitrine) + nouvelles sources d'offres
- **Vitrine** : section *Témoignages* (« Avis ») avec bouton « Laisser mon témoignage » (WhatsApp).
  ⚠️ Cartes d'exemple à remplacer par de VRAIS témoignages avant promotion.
- **Sources d'offres** : 2 nouvelles API gratuites (Himalayas, The Muse) ajoutées à la collecte,
  + flux RSS (We Work Remotely, Remotive, OYA Opportunities, ArmACAD, Oxford Scholarships).
  Plus de résultats réels pour la veille et la recherche grounded.

## v2.72 — 4e fournisseur LLM (OpenRouter) + fix modèle « fast »
- **OpenRouter** ajouté en **dernier recours** (pay-as-you-go) : s'active dès que `OPENROUTER_API_KEY`
  est dans le `.env` → le bot ne tombe jamais même si les 3 tiers gratuits saturent. Dormant sans la clé.
- **Fix** : `CEREBRAS_MODEL_FAST` valait `gemma-4-31b` (modèle inexistant chez Cerebras) → le niveau
  « fast » échouait en silence. Défaut corrigé sur `llama3.1-8b`.
- Modèles OpenRouter réglables par env (`OPENROUTER_MODEL`, `OPENROUTER_MODEL_FAST`). Tests mis à jour.

## v2.71 — Anti-hallucination (solution définitive)
- **Les opportunités ne viennent plus JAMAIS de la mémoire du modèle** : uniquement de la recherche web
  réelle (Tavily). Quand la recherche ne renvoie rien, le bot **n'invente plus** — il affiche des
  **portails officiels vérifiables** (Campus France, Eiffel, DAAD, Erasmus Mundus, Chevening, Mastercard
  Foundation, AUF, EduCanada / LinkedIn, Jobberman, ReliefWeb…) et propose de coller un lien à analyser.
- Toute demande « trouver des bourses/offres » (même avant le CV) est **routée vers la recherche grounded**
  (/mobilite), plus vers une réponse libre.
- Prompts conversationnels verrouillés : interdiction absolue de citer une bourse/programme/entreprise/URL
  précis sans source. Tests ajoutés (le repli n'appelle même pas le LLM).

## v2.70 — Conversation : excellence (intentions directes + titres propres)
- Pré-onboarding : les intentions **claires et informatives** (Campus France, Canada, écoles, visa,
  logement, budget…) sont **traitées immédiatement** au lieu de reposer des questions évidentes
  (« campus france » = la France). Réponse utile d'abord, invitation au CV ensuite.
- Analyse de lien : **titres nettoyés** (plus de « M'inscrire au concours – | … » ni de nom de site) ;
  le LLM extrait le vrai nom de l'opportunité.
- Tests ajoutés.

## v2.69 — Correctifs audit sécurité (SSRF + concurrence)
- **Anti-SSRF** sur l'analyse de lien (`fetch_url_text`) : schémas http/https uniquement, **IP privées /
  loopback / link-local / réservées refusées** (résolution DNS vérifiée, anti-rebinding partiel),
  redirections suivies **manuellement et re-validées** à chaque saut, corps **plafonné à 2 Mo**.
- **Verrou de session par utilisateur** : le traitement des messages d'un même user est sérialisé
  (plus de crédit/quota perdu quand deux messages arrivent en parallèle).
- Tests ajoutés (IP bloquées, résolution d'hôte, refus metadata/localhost/ftp, verrou).

## v2.68 — Suivi d'objectif sur plusieurs tours (brique 2)
- Le bot garde en tête l'**objectif en cours** (la cible travaillée) et **ce qui est déjà fait** :
  opportunité analysée → chances évaluées → CV/lettre générés → méthode de candidature vue → ajoutée au suivi.
- Il propose automatiquement la **prochaine étape logique** (sans repartir de zéro), et repart proprement
  quand la cible change.
- Mis à jour par l'analyse de lien, `/chances`, `/postuler`, `/commentpostuler`, et le bouton « Suivre ».
- Ajout : logo NexMove carré (`web/logo-nexmove.png`) pour la photo de profil WhatsApp.

## v2.67 — Mémoire de contexte conversationnel (brique 1)
- Le routeur conversationnel reçoit désormais une **mémoire compacte** : ce que le bot sait déjà
  (nom, objectif, pays, niveau, compétences, abonnement, dernier lien analysé, candidatures suivies)
  **+ ce qui manque** encore, **+ le dialogue récent**.
- Résultat : le bot **ne redemande plus** une info déjà connue (CV, objectif, pays) et **ne se répète plus**
  d'un tour à l'autre ; il propose l'action concrète suivante.
- Même mémoire injectée dans les réponses **pré-onboarding** (ne repose plus la même question).

## v2.66 — Analyse de lien fiabilisée + suivi d'intention
- **Correctif** : un lien collé déclenche désormais l'analyse **à tout moment** (même avant d'avoir
  envoyé un CV). Avant, en attente de CV, le lien partait en conversation (et pouvait être mal interprété).
- **Suivi d'intention** : après un lien analysé, « je veux candidater » → `/commentpostuler` sur la
  cible du lien ; « mes chances / suis-je éligible » → `/chances` sur cette cible (plus de questions redondantes).
- Le routeur conversationnel ne **prétend plus** avoir lu un lien et n'invente plus de noms d'organismes ;
  il invite à coller le lien pour l'analyser.

## v2.65 — Durcissement sécurité (retours testeur)
- **Doc API fermée** : `/docs`, `/redoc`, `/openapi.json` désactivés par défaut (réactivables avec `EXPOSE_DOCS=1`).
- **/health minimal** : ne renvoie plus que `status/version/whatsapp_configured`. Le détail d'infra passe sur
  **/api/admin/health** (protégé par la clé `X-Forge-Nex-Key`).
- **/** minimal (ne liste plus les endpoints) + cache `max-age=600`.
- **Rate limiter** par IP (`RATE_LIMIT_PER_MIN`, défaut 120/min) ; webhooks entrants et `/health` exemptés.
- **En-têtes de sécurité** : `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.
- **CORS** restreignable via `ALLOWED_ORIGINS`.

## v2.64 — Analyse d'un lien d'opportunité collé
- **Colle un lien** (offre, bourse, programme, formation) et le bot l'**audite** : il ouvre la page,
  extrait l'opportunité, **note la compatibilité** avec ton profil, donne un **verdict d'admissibilité**,
  les **critères clés**, ce qu'il te **manque**, et **comment postuler**.
- Détection **automatique** des URL dans un message (hors onboarding) + commande **/lien <url>**.
- Boutons de suite : *Comment postuler* (/commentpostuler), *Mes chances* (/chances), *Suivre* (ajout au suivi).
- Récupération web côté serveur (`fetch_url_text` + extracteur HTML), quota gratuit `FREE_LINK_DAILY` + crédits.
- L'opportunité est enregistrée dans ta veille. Tests ajoutés.

## v2.63 — Entraînement entretien noté (/10 + version améliorée)
- La **simulation d'entretien** note désormais **chaque réponse sur 10**, propose une
  **version améliorée** de la réponse, et donne un **score global /10** au bilan.
- **/simulation \<offre/poste\>** : les questions sont tirées de l'offre visée (sinon campus/visa/emploi).
- Réponses en **texte ou vocal** (transcription déjà gérée). Arrêt anticipé `/terminer` → bilan + score.
- Tests ajoutés (score global, bloc de feedback, ciblage, tour de simulation).

## v2.62 — Suivi candidatures enrichi (pipeline + notes)
- **/mescandidatures** affiche désormais un **pipeline** regroupé par statut (En préparation →
  Envoyée → Relancée → Entretien → Réponse → Acceptée/Refusée/Clôturée), avec deadline et note.
- Nouvelle commande **/note <cible> : <texte>** pour garder un mémo par candidature
  (ex. « entretien jeudi 14h, relire le projet »).
- DB : colonnes `note` + `updated_at` sur `candidatures` ; `set_note`, `list_candidatures_full`.
- Les rappels de relance automatiques (cron `/api/relances`) existaient déjà. Tests ajoutés.

## v2.61 — Guide « comment postuler » (e-mail/formulaire prêt à copier)
- Nouvelle commande **/commentpostuler <offre>** : le bot explique **comment candidater**
  (e-mail / formulaire / plateforme), rédige l'**objet** + le **message** prêts à copier-coller,
  personnalisés depuis le profil, liste les **pièces à joindre** et les **étapes**.
- Sélection rapide : **/commentpostuler 1** reprend une offre récemment affichée.
- Accessible en **langage naturel** (« comment postuler à … », « comment candidater pour … »).
- Quota gratuit **FREE_APPLY_DAILY** (3/j) + crédits ; relié au menu /outils. Tests ajoutés.

## v2.60 — Recherche auto après le CV (offres notées immédiates)
- **Valeur immédiate** : dès que l'utilisateur valide son CV, le bot lance une **recherche
  automatique** et affiche **3 offres notées** (compatibilité %, niveau, raison, lien) — sans attendre
  les questions de préférences. Les questions servent ensuite à *affiner*.
- **Offres notées partout** : nouveau format partagé `_render_scored_offers` + badge
  `_score_badge` (Excellent/Fort/Correct/Partiel) ; la veille finale d'onboarding affiche aussi la note.
- **Sans surcoût** : l'aperçu calculé après le CV est **réutilisé** à la validation finale
  (une seule recherche, pas deux). Tests ajoutés (badge, rendu, réutilisation).

## v2.59 — Panel admin + récap de profil éditable + fix cron & /canada
- **Panel web admin** : `web/admin.html` (hébergé sur la vitrine) interroge **`GET /api/admin/stats`**
  (protégé par la clé admin) → KPIs (users, onboardés, payants, crédits), codes Premium/crédits,
  attribution par source. Commande Telegram équivalente : **/stats** (admin).
- **Récap de profil éditable** : /profil affiche un récap + l'utilisateur corrige en écrivant
  `champ: valeur` (ex. `objectif: travailler`, `pays: Canada`, `mots-clés: data, python`).
- **Fix** : le script `scripts/nex-cron.sh` utilisait le mauvais en-tête (`X-API-Key` → `X-Forge-Nex-Key`)
  → les crons échouaient silencieusement. Corrigé + rapporte désormais le code HTTP.
- **Fix bug** : `/canada` (et autres handlers) plantaient (UnboundLocalError `profil`) — `profil` est
  maintenant disponible pour tous les handlers.

## v2.58 — Langage naturel étendu (ne plus se perdre dans les commandes)
- Le routeur en langage naturel (utilisateurs onboardés) reconnaît désormais **toutes les commandes
  récentes** : écrire « quelles sont mes chances pour ce master », « entraîne-moi à l'entretien »,
  « crée-moi un CV », « mes candidatures », « la boîte à outils », « combien de crédits »… déclenche la
  bonne action **sans connaître le nom de la commande**. `_VALID_INTENTS` + prompt du routeur enrichis
  (chances, compatibilite, simulation, creercv, outils, extraire, mescandidatures, parrainage, offres, credits…).

## v2.57 — Crédits fongibles (monétisation flexible) + upsell branché partout
- **Packs de crédits fongibles** : 1 crédit = 1 action (CV, score, simulation…) quand la limite gratuite
  du jour est atteinte. Codes **CRD-XXXXXXXX** à usage unique (vendus sur Chariow), activés via
  **/credits <code>** ; solde via **/credits**. Génération admin : **/gencredits <crédits> <nombre>**.
  Les crédits se déclenchent automatiquement (CV, /compatibilite, /chances, /simulation) et ne périment pas.
- **Upsell branché** aussi sur : fin d'onboarding, dossier généré (/postuler), pied du digest quotidien.
- /offres et /monabo exposent les crédits ; CreditStore (table credit_codes).

## v2.56 — Nouveaux outils + upsell personnalisé selon le profil
- **5 nouveaux outils** (sans dépendance) : **/extraire** (texte d'un PDF/scan/photo, OCR),
  **/compresserimage** (alléger une photo), **/enimages** (PDF → PNG en .zip),
  et deux **perks Premium** : **/cv1page** (CV synthétique) et **/anonymiser** (CV à l'aveugle).
- **Upsell personnalisé** : les nudges s'adaptent désormais à l'**objectif du profil** (études →
  dossier Campus France / score ; emploi → compatibilité / candidatures), en plus du palier.
- /outils enrichi avec les nouveaux outils.

## v2.55 — Boîte à outils mise en avant + moteur d'upsell
- **/outils** : hub qui met en avant tous les outils intégrés (postuler, dossier, compresser, fusionner,
  images→PDF, découper, traduire, créer CV, timeline) avec boutons + astuces. Ajouté à l'aide.
- **Moteur d'upsell** (`_upsell_line`) : nudges marketing/psychologiques **éthiques et sensibles au palier**
  (jamais pour admin/pro/vip ; montée en gamme douce pour premium ; incitation pour les gratuits).
  Leviers : accès illimité, offre de lancement (-40%), preuve sociale. Branché sur les **limites de quota**
  (CTA /offres renforcé) et la **fin d'un outil**.

## v2.54 — Conversation plus fine + relances intelligentes
- **B3 — Désambiguïsation** : face à une demande vague (« je veux partir », « aide-moi »), le bot pose
  UNE question de clarification ciblée au lieu de supposer.
- **B2 — Relances intelligentes** : relance les utilisateurs décrochés (CV envoyé mais onboarding non fini)
  ou inactifs, **cadence par palier** (Premium/Pro 24 h · VIP 48 h · Gratuit 72 h · Admin jamais).
  **Telegram uniquement** (gratuit ; WhatsApp exclu car messages proactifs >24 h = templates payants).
  Endpoint `POST /api/relances` (cron ~1x/jour) ; **opt-out /stop** (coupe relances + digest).
  Script `scripts/nex-cron.sh` + lignes crontab (collect/notify/relances).

## v2.53 — Onboarding plus court (profil pré-rempli depuis le CV)
- **B1 — Moins de questions** : après l'analyse du CV, NexMove **déduit automatiquement** tes
  domaines/compétences (mots-clés) et ta langue de travail → il **saute** ces questions à l'onboarding
  (friction réduite = meilleure conversion). Les valeurs restent **modifiables** à l'étape de confirmation.

## v2.52 — Bourses & mobilité + sources locales/régionales enrichies
- **A3 — Flux bourses/mobilité** ajoutés à la veille (RSS) : scholarship-positions, OpportunitiesCircle,
  ScholarshipsAds → plus de bourses d'études (France/Europe/Canada) pour le persona Campus France.
- **A4 — Sources locales/régionales** : grandes plateformes réelles ajoutées (Indeed fr, LinkedIn,
  Jobberman, Glassdoor) + voisins **Ghana** et **Nigéria** (diaspora/mobilité régionale). Nouveau réglage
  `LOCAL_SOURCES_EXTRA_<PAYS>` dans `.env` pour ajouter tes portails locaux exacts (ex. Bénin) sans toucher
  au code.

## v2.51 — Sources d'offres enrichies (télétravail international + Adzuna élargi)
- **3 nouvelles sources d'emploi sans clé API** ajoutées à la veille : **RemoteOK**, **Remotive**,
  **Jobicy** → de vraies offres **100 % télétravail international**, idéales pour un candidat local qui
  veut travailler pour l'étranger sans partir (scope `both`, matché par profil).
- **Adzuna élargi** : pays par défaut `fr,ca,be,gb,de` (au lieu de `fr,ca,be`), plafond porté à 8 pays.
- Exposé dans `/version` et `/health` (`remote_sources`). Ingestion robuste (une source en échec ne bloque
  plus les autres).

## v2.50 — Identité validée + WhatsApp fiabilisé + attribution des sources
- **Identité de marque appliquée** : baseline validée « *Études, emploi, ici ou ailleurs : l'assistant
  pour ton prochain move.* » intégrée à l'accueil (`/start`) et au pitch d'ouverture. Doc de référence :
  `docs/IDENTITE-NEXMOVE.md` (palette, logo, kit pub, personas).
- **WhatsApp/Messenger fiabilisés pour la prod** : les webhooks Meta répondent **immédiatement** puis
  traitent en **tâche de fond** (fini les timeouts/retries qui doublaient les réponses) ; **vérification de
  signature** `X-Hub-Signature-256` activée dès que `META_APP_SECRET` est défini (bloque les faux messages
  sur l'endpoint public). Guide à jour : `docs/GUIDE-WHATSAPP.md` (App NexMove déjà créée, ID 1590553112520815).
- **Attribution des sources marketing** : les liens `t.me/<bot>?start=src_<persona>_<canal>` enregistrent
  la **première** source de chaque utilisateur (sans collision avec le parrainage) ; **`/srcstats`** (admin)
  affiche par source le nombre d'utilisateurs, le taux d'onboarding et les payants.
- **+tests**. Suite verte.

## v2.49 — Dépasser KaizenJob : score par compétence + pipeline de candidatures
- **`/compatibilite <poste>`** (alias `/match`) : score de compatibilité **décomposé compétence par
  compétence** (ex. Python 90 % ▓▓▓▓▓▓▓▓▓░, SQL 70 %…) + compétences manquantes + verdict — la fonction
  phare du concurrent, en conversationnel. Limité (FREE_SCORE_DAILY) gratuit, illimité Premium.
- **Pipeline de candidatures (mini-CRM)** : `/mescandidatures` liste tes dossiers avec leur statut
  (📝 préparation · 📤 envoyée · 🔁 relancée · 🎤 entretien · 📨 réponse · ✅ acceptée · ❌ refusée · 🔒 clôturée) ;
  `/candidature <statut> <cible>` met à jour (reconnaît les formulations naturelles).
- **+5 tests**. **170/170 verts**.

## v2.48 — Conversation vraiment intelligente + score d'admissibilité /chances
- **Comprend N'IMPORTE QUELLE phrase avant l'onboarding** : plus de mots-clés imposés. À toute question
  (RGPD/vie privée, prix, fiabilité, « c'est quoi », etc.) le bot répond par l'IA (`_preonboarding_reply`,
  faits RGPD/gratuité inclus) puis invite doucement à envoyer le CV. Fini le « écris à quoi tu sers » et le
  « envoie ton CV » hors sujet.
- **`/chances <cible>`** — score d'admissibilité honnête (/100) + atouts, manques et **actions concrètes pour
  augmenter ses chances** (visa, admission, bourse, emploi). Différenciation forte.
- **Incitation à l'abonnement** : `/chances` limité à `FREE_SCORE_DAILY` (2/j) pour les gratuits, illimité en
  Premium ; message de quota et compteur « restant » qui renvoient vers /offres.
- **+4 tests**. **166/166 verts**.

## v2.47 — Parrainage : invite tes amis, gagne du Premium
- **`/parrainage`** : chaque utilisateur a un **code/lien** de parrainage. Quand **REFERRAL_GOAL** amis
  (défaut 2) créent leur profil via son lien (`t.me/<bot>?start=<code>`), le parrain reçoit
  **REFERRAL_REWARD_DAYS** (défaut 30) jours de Premium — à chaque palier — et est notifié.
- `/start <code>` (deep-link Telegram) attribue automatiquement le filleul. Boucle virale d'acquisition.
- `ReferralStore` (codes stables, filleul unique, comptage des validés). Config : `BOT_USERNAME`,
  `REFERRAL_GOAL`, `REFERRAL_REWARD_DAYS`.
- **+5 tests**. **163/163 verts**.

## v2.46 — Notes vocales : le bot comprend les messages audio
- **Vocaux transcrits puis traités comme du texte** (Telegram & WhatsApp) : l'utilisateur peut **parler**
  au lieu d'écrire — transcription via Gemini (`transcribe_audio`), puis passage dans tout le pipeline normal
  (onboarding, commandes, intentions…). Accessibilité majeure pour la cible.
- Quota `FREE_VOICE_DAILY` (défaut 20/jour, admin & abonnés illimités) ; vidéos/stickers restent refusés
  poliment ; vocal incompris → message clair.
- **+3 tests** (parsing vocal Telegram/WhatsApp, vidéo toujours refusée). **159/159 verts**.

## Sécurité & robustesse (config) — sept. 2026
- **API en écoute localhost uniquement** (`docker-compose` : `127.0.0.1:8000:8000`) — plus exposée
  directement à Internet ; jointe seulement via le tunnel Cloudflare (même machine).
- **Recommandation forte** : définir `TELEGRAM_WEBHOOK_SECRET` dans `.env` — sans lui, le webhook natif
  `/webhook/telegram` est falsifiable (usurpation admin possible → génération de codes). Le script
  auto-tunnel transmet ce secret.
- **`scripts/nexmove-tunnel.sh`** rendu **auto-relançant** (boucle interne + attente de l'API) → durable
  **sans systemd/sudo** (via `nohup`/`setsid` + cron `@reboot`).

## v2.45 — Activation premium par code collé + script auto-tunnel
- **Activation ultra-simple pour les clients** : coller le code `PRM-XXXXXXXX` (même noyé dans une phrase)
  suffit à activer l'abonnement — plus besoin de taper `/premium`. La commande `/premium <code>` reste valable.
- **`scripts/nexmove-tunnel.sh` + `nexmove-tunnel.service`** : lance le tunnel Cloudflare rapide **et
  réenregistre automatiquement le webhook Telegram** à chaque (re)démarrage (URL qui change → auto-réparé).
  À installer en service systemd → plus de coupure « URL changée ».
- **+2 tests**. **156/156 verts**.

## v2.44 — Webhook Telegram NATIF (suppression de la dépendance n8n)
- **`POST /webhook/telegram`** : l'API reçoit désormais Telegram **directement**, sans n8n. Elle lit
  elle-même le `chat.id`/`from.id` (fin du bug « undefined »/« chat not found »), gère texte, **documents**,
  **photos**, **boutons** (callback_query), et rejette poliment audio/vidéo/sticker.
- **Réponse immédiate** (200) + traitement en **tâche de fond** → plus de timeout/retry Telegram sur les
  appels LLM/CV.
- **Secret** de webhook facultatif (`TELEGRAM_WEBHOOK_SECRET`) vérifié via l'en-tête Telegram.
- **Commandes admin** `/setwebhook <url>` (bascule Telegram sur l'API) et `/webhookinfo` (état du webhook).
- Helper `tg_get_file` (channels) pour télécharger les fichiers Telegram.
- **Guide** `docs/WEBHOOK-TELEGRAM-DIRECT.md` (URL stable Cloudflare Tunnel + migration pas à pas).
- **+5 tests** (parsing texte/document/photo/bouton/vocal). **154/154 verts**.
- → Élimine la classe de pannes qu'on subissait (workflow n8n désactivé, webhook effacé, nœud fichier cassé).

## v2.43 — Surveillance & alertes de disponibilité
- **Alerte de (re)démarrage** : à chaque démarrage, l'API prévient l'admin sur Telegram
  (« ✅ NexMove en ligne — vX »). Dédoublonnée entre les 2 workers.
- **`/api/selfcheck`** : vérifie les dépendances critiques — surtout le **webhook Telegram**
  (getWebhookInfo : url vide ? dernière erreur ? messages en attente ?) et la présence d'un fournisseur LLM.
  **Alerte l'admin sur changement d'état** (panne → « 🚨 panne détectée » ; retour → « ✅ service rétabli »),
  sans spam. À appeler par un cron toutes les 5 min.
- L'alerte sortante passe par un appel direct à l'API Telegram → **fonctionne même quand le webhook entrant
  est cassé** (le cas le plus fréquent de coupure).
- **+2 tests**. **149/149 verts**.

## v2.42.3 — Fix CV : « undefined » du nœud fichier n8n traité comme chat_id invalide

## v2.42.1 — Fix : « chat not found » après envoi d'un CV
- Le CV était bien analysé mais la réponse échouait (`sendMessage 400: chat not found`) : le nœud fichier
  n8n postait `/api/chat-cv` avec un `chat_id` manquant/`"0"` qui **écrasait** le bon `chat_id` stocké.
- **Fix défensif** dans `/api/chat-cv` **et** `/api/chat** : un `chat_id` invalide (`"0"`/vide) n'écrase plus
  le `chat_id` connu ; repli sur `user_id` (en privé Telegram, `chat_id == user_id`). Idem pour `username`.
- **+1 test**. **146/146 verts**.

## v2.42 — Sources d'emploi locales enrichies (Bénin/UEMOA)
- **Portails locaux réels vérifiés** intégrés à la veille locale (`LOCAL_JOB_SOURCES`) : Bénin
  (emploibenin.com, jobbenin.com, offresdemplois.bj, talentsplusafrique.com, afriqueemplois.com, gouv.bj),
  Côte d'Ivoire, Sénégal, Togo, Burkina, Cameroun, Mali, Niger + sources régionales (Jooble, Novojob,
  Talent2Africa, AfricaWork, ReliefWeb).
- Ces portails **orientent la recherche** (requête Tavily) **et** le prompt de veille → offres locales plus
  concrètes, avec liens. **Pas de flux RSS deviné** = zéro lien mort.
- **Extensible sans code** via env `LOCAL_SOURCES_EXTRA_<PAYS>` (ex. `LOCAL_SOURCES_EXTRA_BENIN=site.bj`).
- **+3 tests**. **145/145 verts**.

## v2.41 — Admins multiples + commande /id (setup admin)
- **Admins multiples** : `_is_admin` accepte plusieurs identifiants — `ADMIN_CHAT_ID` (principal, utilisé
  pour le forward /contact) **+** `ADMIN_IDS` (liste séparée par virgules). Permet d'être admin sur
  **Telegram (chat_id) ET WhatsApp (numéro)** en même temps.
- **`/id`** (`/monid`, `/whoami`) : affiche ton `chat_id` / `user_id` et ton statut admin — pour récupérer
  facilement l'identifiant à mettre dans le `.env`.
- **+2 tests**. **142/142 verts**.

## v2.40 — Abonnements premium & codes d'activation (monétisation)
- **Système de codes premium** (`db.PremiumStore`) : codes `PRM-XXXXXXXX` générés en lots (à vendre sur
  Chariow), **usage unique**, chacun = un **tier** (premium/pro/vip) + une durée en jours.
- **`/premium <code>`** active/prolonge l'abonnement ; **`/monabo`** affiche le statut ; **`/offres`**
  présente les formules. `/status` indique désormais le tier et l'échéance.
- **`/gencodes <tier> <jours> <nombre>`** (admin) : génère un lot (≤25 → affiché, sinon fichier `.txt`).
- **Tiers appliqués aux quotas** : les abonnés (et l'admin) ont **CV, /guide, /simulation illimités** ;
  gratuit = 1 simulation/jour (`FREE_SIM_DAILY`) et **1 alerte** (Premium 10, Pro/VIP illimité).
- Abonnement **persistant** (`premium_tier` + `premium_until`), **prolongation** empilée sur le temps restant.
- **+12 tests** (création/redeem/usage unique/stats des codes, tiers & expiration, quotas premium,
  commandes `/premium`, `/monabo`, `/gencodes`, plafonds d'alertes). **140/140 verts**.

## v2.39 — Accueil moins rigide + création de CV guidée (conversation)
- **Début moins rigide** : à une question d'ouverture (« à quoi tu sers », « c'est quoi », salutation…),
  le bot **explique ce qu'il fait** (pitch) au lieu de répondre seulement « envoie ton CV ». Le message
  d'accueil propose désormais 3 chemins : envoyer un CV · en créer un · demander ce que fait NexMove.
- **Parcours sans CV** : « je n'ai pas de CV » ou **`/creercv`** lance une **création guidée** — 5 questions
  adaptatives (nom, formation, expériences, compétences, langues) → NexMove **structure le profil** (LLM),
  **génère un CV PDF** et enchaîne sur les préférences. `/annuler` sort proprement.
- **+8 tests** (détection pitch/no-CV, réponse avant CV, mention `/creercv`, flux `/creercv` complet mocké,
  annulation). **127/127 verts**.

## v2.38 — Feuille de route visuelle `/timeline` (PNG) (extra)
- **`/timeline`** (alias `/planning`, `/feuille`) génère une **image PNG** de la feuille de route de
  l'utilisateur : étapes Campus France ✅ faites / 🟠 en cours / ⚪ à venir, avec ses **échéances** de dossiers.
- Rendu Pillow (`render_timeline_png`, fonction pure) avec repli propre si Pillow absent ; police DejaVu
  (accents) avec repli. Généré hors boucle événementielle (`asyncio.to_thread`).
- **+5 tests** (PNG valide, sans échéances, wrap de texte, garde onboarding, génération via commande).
  **121/121 verts**.

## v2.37 — Alertes mots-clés personnalisées `/alerte` (extra)
- **`/alerte <mot-clé>`** : l'utilisateur enregistre ses mots-clés (max 10). `/alerte` liste, `/alerte off
  <mot>` retire, `/alerte off` vide tout.
- Dans `/veille`, `/mobilite` et le **digest quotidien**, les offres qui matchent une alerte **remontent en
  tête** (+20 au score), sont **taguées 🔔** et un bandeau annonce le nombre d'offres correspondantes.
- **+4 tests** (matching, ajout/liste/suppression, garde longueur, plafond 10). **116/116 verts**.

## v2.36 — Coach d'entretien interactif `/simulation` (extra)
- **`/simulation`** lance un **entretien blanc** adapté au profil : *Campus France / Études en France*,
  *visa consulaire*, ou *emploi* (`/simulation visa`, `/simulation emploi`…). Le bot pose `SIM_MAX_Q`
  questions (défaut 5), donne un **feedback** après chaque réponse, puis un **bilan** final (points forts,
  axes, conseils actionnables).
- Banque de questions de **repli** par type si le LLM est indisponible → la simulation marche toujours.
- `/terminer` clôt avec le bilan ; `/annuler` quitte sans bilan. Mode isolé du CV/guide/outils PDF.
- **+5 tests** (types, repli borné, garde onboarding, flux complet LLM mocké, /annuler). **112/112 verts**.

## v2.35 — Entrée express Canada : rondes IRCC en TEMPS RÉEL (PR-D4c)
- **`/canada`** s'appuie maintenant sur les **dernières rondes d'invitations réelles** d'IRCC (open data
  officiel `ee_rounds_123`), au lieu d'une info figée. Les rondes sont **injectées comme données de
  référence** dans le conseil ET affichées telles quelles (catégorie, CRS, nombre d'invitations, date).
- **Cache 6 h** (`fetch_ircc_rounds`) pour éviter de refrapper l'API à chaque `/canada` ; parsing tolérant
  (`_parse_ee_rounds`) ; URL surchargeable via `IRCC_ROUNDS_URL`.
- **+5 tests** (parsing catégories, tolérance JSON vide/malformé, mise en forme, cache-hit sans réseau).
  **107/107 verts**.

## v2.34 — Catalogue de sources structuré + filtrage adaptatif au profil (PR-D2)
- **`SOURCE_CATALOG`** : les flux de veille portent désormais un **`type`** (bourse/emploi/fellowship/ong)
  et un **`scope`** (local/intl/both), et sont **activables par flag d'env** (`active_env`, ex.
  `ENABLE_RELIEFWEB=1` pour ReliefWeb). `SOURCE_FEEDS` en est dérivé (rétro-compat).
- **Type/scope hérités** à l'ingestion : chaque offre ingérée reçoit le bon type (fini le « bourse »
  systématique) et son périmètre — stockés en base (colonne `scope`, `add_source`).
- **Filtrage adaptatif** : `search_sources(prefer_scope=…)` fait remonter les sources du **bon périmètre** ;
  un objectif purement **local** n'est plus inondé de sources 100 % internationales (et inversement).
  `_sources_for_profile(prefs)` sélectionne les sources pertinentes selon le profil.
- **+8 tests** (intégrité catalogue, flag d'activation, sélection locale/intl, scope en base,
  `prefer_scope`, défaut `both`). **102/102 verts**.

## v2.33 — Mode /guide : guidage par capture d'écran (vision) (PR-D4b)
- **`/guide`** active un mode où l'utilisateur envoie une **capture d'écran** (Campus France / Études en
  France, Parcoursup, Mon Master, eCandidat, formulaire, e-mail d'admission…) et reçoit un **guidage
  concret étape par étape** — analyse par **vision Gemini** (`analyze_screenshot_vision`, `llm.py`).
- `/guide <contexte>` (ex. `/guide campus france`) cible l'aide ; `/annuler` quitte le mode.
- Branché sur les **quotas** (`FREE_GUIDE_DAILY`, défaut 12/jour ; admin illimité) : décompte uniquement
  sur analyse réussie ; capture non-image → demande polie ; vision indisponible → message clair.
- `/guide` n'est plus un alias de `/tuto` (le tuto reste sur `/tuto`).
- **+5 tests** (activation, contexte, /annuler, non-image, vision mockée). **95/95 verts**.

## v2.32 — Quotas gratuits + admin illimité (PR-D4a)
- **`UsageStore`** (`db.py`) : compteurs d'usage **par jour et par fonctionnalité** (table `usage`).
- **Quota d'analyse de CV** : `FREE_CV_DAILY` (défaut **8/jour**) pour les utilisateurs gratuits — l'op la
  plus coûteuse (LLM/vision). Message poli quand la limite est atteinte, décompte **uniquement** sur analyse
  réussie (un upload illisible ne consomme rien).
- **Admin illimité** : `_is_admin` (via `ADMIN_CHAT_ID`) n'est jamais compté ni bloqué.
- Helpers réutilisables `_quota_check` / `_quota_bump` / `_quota_exceeded_msg` + `FREE_GUIDE_DAILY` (défaut
  **12/jour**) déjà prêts pour le futur mode **/guide** (captures d'écran → vision Gemini).
- **+5 tests** (compteurs par jour/feature/user, admin illimité, sous-limite, limite 0 = désactivée).
  **90/90 verts**.

## v2.31 — Profils persistés par identifiant (code de récupération) (PR-D3)
- **`ProfileStore`** (`db.py`) : chaque profil validé reçoit un **code de récupération stable** `NEX-XXXXX`.
  Le profil est archivé en **versions** ; on ne restaure QUE la **plus complète** (`profile_quality`) — donc
  « on garde les meilleures données » même si l'utilisateur change d'appareil ou de canal.
- **`/moncode`** : affiche (et crée au besoin) le code de récupération.
- **`/moi <code>`** : restaure le meilleur profil sur le compte courant → **portage Telegram ↔ WhatsApp**
  et récupération après changement d'appareil. Le code est aussi affiché à la fin de l'onboarding.
- **+8 tests** (code stable, restauration inter-utilisateurs, conservation de la meilleure version,
  `profile_quality`, code inconnu, commandes `/moi`/`/moncode`). **85/85 verts**.

## v2.30 — Onboarding ADAPTATIF + nom de secours + intention mémorisée (PR-D1)
- **Onboarding adaptatif** : les questions s'adaptent aux réponses. Un **stage/job LOCAL** (objectif
  « travailler » + son propre pays) ne demande plus la **nationalité/passeport**, ni le **financement
  d'études**, ni les **certifs de langue** — ces questions restent réservées à la mobilité internationale
  et aux parcours d'études/bourses. Plan de questions recalculé à chaque étape (`_build_pref_plan`).
  → Corrige le retour testeur : « demander la nationalité pour un stage local, ce n'est pas logique ».
- **Nom de secours depuis le fichier** : quand l'OCR/LLM ne détecte pas le nom sur le CV, on le devine
  depuis le **nom du fichier** (`CV_Judicael.pdf` → « Judicael », `cv-jean-dupont.pdf` → « Jean Dupont »)
  au lieu d'afficher « N/A ». Le nom deviné est persisté (utile pour lettres/dossiers).
- **Intention mémorisée** : une demande forte tapée **avant la fin de l'onboarding** (ex. « je cherche une
  bourse de master au Canada ») n'est plus perdue — elle est mémorisée puis **relancée** à la fin du profil
  (message + bouton « ▶️ … »).
- **+11 tests** (`_build_pref_plan`, `_vise_international`, `_name_from_filename`, flux d'onboarding local
  bout en bout, capture d'intention). **77/77 verts**.

## v2.29 — WhatsApp : photos directes + rejet poli audio/vidéo + guide de mise en service
- **Photos WhatsApp directement** : le parseur gère maintenant `type: "image"` (JPG/PNG) — l'image part
  vers **vision Gemini** comme pour Telegram. Fini l'obligation d'envoyer en « Document ».
- **Rejet poli** des audios, vocaux, vidéos, stickers : « Écris-moi en texte ou envoie ton CV en
  PDF/Word/image » au lieu du silence.
- **`docs/GUIDE-WHATSAPP.md`** (nouveau) : procédure complète (Meta Business, App WhatsApp, tokens, webhook
  ngrok, whitelist testeurs, coûts, dépannage). ~30 min de config côté Meta, le code est déjà prêt.
- **`tests/test_whatsapp_incoming.py`** (+10 tests) : texte, document PDF, image JPG/PNG, boutons
  interactive (button_reply / list_reply / template button), rejets audio/vidéo/sticker. **66/66 verts**.

## v2.28 — Refactor PR-C : `channels.py` extrait + smoke test Docker en CI
- **`api/channels.py`** (nouveau, ~200 lignes) : Telegram (`send_message`, `edit_message`, `answer_callback`,
  `_send_telegram_document`, `_tg_keyboard`), WhatsApp Cloud API (`wa_text/menu/document/get_media`),
  Messenger (`fb_text/menu/document`), + helper `_mime_for`. Comportement identique.
- **~180 lignes retirées** de `main.py` (3 064 → 2 891).
- **`tests/test_channels.py`** (+10 tests) : MIME, clavier inline, garde-fous sans token. **56/56 verts**.
- **🛡️ Smoke test Docker en CI** : nouveau job `docker-smoke` qui build l'image, lance le container, et
  vérifie que `/health` répond. **Aurait attrapé le bug v2.27.1** (`ModuleNotFoundError: http_client`)
  avant qu'il n'arrive en prod.
- Étape suivante prévue (PR-D) : extraire `tools.py` (PDF ops, compression, DOCX, vision).

## v2.27.2 — Fix Dockerfile : les nouveaux modules manquaient dans l'image
- `COPY main.py .` → `COPY main.py db.py llm.py http_client.py .` — sans ça, `ModuleNotFoundError` au
  démarrage du container (PR-A/B cassées en prod). Le smoke test Docker (v2.28) verrouille cette classe de bugs.

## v2.27.1 — Fix test CI trop strict
- `test_compress_pdf_valid_output` : `kb == 0` est légitime pour un mini-PDF. On vérifie signature `%PDF-`
  + taille en octets > 200. CI durcie : ruff/compile couvrent tout `api/` (pas juste `main.py`).

## v2.27 — Refactor PR-B : `llm.py` + `http_client.py` extraits (IA isolée)
- **`api/http_client.py`** (nouveau) : le pool `httpx.AsyncClient` partagé sort du monolithe. Utilisable
  par tout module (`from http_client import http`).
- **`api/llm.py`** (nouveau, ~230 lignes) : routeur multi-fournisseurs (Cerebras→Groq→Gemini), embeddings
  (multi-modèles, cache 7 j via `db.cache`), vision Gemini pour l'analyse d'un CV image. Comportement
  identique — mêmes défauts de modèles, même bascule, même parseur JSON tolérant.
- **~210 lignes retirées** de `main.py` (3 260 → 3 064).
- **`tests/test_llm.py`** (+10 tests) : parseur JSON (fences ```/```json), cosine, structure des providers,
  garde-fous sans clé. **46/46 verts** (36 + 10). Zéro régression.
- Étape suivante prévue (PR-C) : extraire `channels/` (Telegram/WhatsApp/Messenger).

## v2.26 — Refactor PR-A : `db.py` extrait (persistance isolée)
- **`api/db.py`** (nouveau) : les 3 stores SQLite (`SessionManager`, `OppStore`, `Cache`) sortis du monolithe,
  comportement identique (méthodes, signatures, DDL, chemins). Chemin de base configurable via
  `NEXMOVE_DB_PATH`. `main.py` ne fait plus qu'un `from db import …`.
- **~230 lignes retirées** de `main.py` (fichier passe de ~3 490 à ~3 260 lignes).
- **`tests/test_db.py`** (8 tests) : session roundtrip, dédup offres, user_stats, candidatures + rappels,
  feedback borné à ±25, journal /contact, cache TTL. **36/36 verts en local et en CI.**
- Étape suivante prévue (PR-B) : extraire `llm.py` (routeur multi-fournisseurs + embeddings).

## v2.25 — Photos Telegram, journal /contact, tests + CI
- **Photos Telegram directes** : WF1 parse désormais `message.photo` (prend la plus grande taille) et route
  vers `/api/chat-cv` ; `process_cv` détecte l'image (`.jpg`) et l'analyse par **vision Gemini** (repli OCR).
  Fini l'obligation d'envoyer en « Fichier ».
- **Journal `/contact` en base** : chaque message est logué (table `contacts`), même si le forward Telegram
  échoue. Nouvelle commande **`/contacts_log`** (réservée à `ADMIN_CHAT_ID`) : les 20 derniers messages.
- **Filet de sécurité (risque n°1 de l'audit)** : ajout de `tests/test_units.py` (**28 tests unitaires**,
  fonctions pures : validation onboarding, tri diplômes, routeur d'intention, nationalité→pays, feedback,
  pages PDF, RSS tolérant, PDF ops, extraction DOCX, MIME…) + workflow **GitHub Actions** `ci.yml` (ruff
  errors-only + compile + pytest à chaque push/PR). Régression = build rouge, plus jamais en prod.

## v2.24 — Contact & version
- **`/version`** (alias `/about`) — affiche la version du bot, les IA actives, les modules (OCR, Word, Vision,
  Sémantique, Adzuna) et le nombre de sources. Utile pour le support et pour que tu voies l'état en un coup d'œil.
- **`/contact <message>`** (alias `/support`, `/rencontrer`, `/rdv`) — transmet directement le message au chat
  admin (Telegram) si `ADMIN_CHAT_ID` est configuré ; sinon affiche les canaux (WhatsApp, email, calendrier).
  Route aussi les intentions en langage naturel (« parler à quelqu'un », « prendre rdv », « contacter »…).
- Boutons `💬 Nous contacter` et `ℹ️ Version` dans le menu « Mon espace ». Env vars : `ADMIN_CHAT_ID`,
  `CONTACT_EMAIL`, `CONTACT_WHATSAPP`, `CONTACT_CALENDAR`.

## v2.23 — CV multi-formats & procédures françaises parallèles
- **CV en tous formats** : PDF texte + PDF scanné (OCR) ✅ déjà, **+ DOCX** (python-docx) **+ image** (JPG/PNG/WEBP/HEIC).
  Images analysées d'abord par **vision Gemini** (robuste sur photos), repli **OCR tesseract**. Endpoint et
  process_cv routent par extension/MIME. Messages d'erreur adaptés au format.
- **Procédures françaises parallèles à Campus France** (le gros gap face aux prestataires payants) :
  `/parcoursup`, `/monmaster`, `/ecandidat`, `/dap` (L1 hors UE), `/visa` (phase consulaire Capago/VFS),
  `/recours` (refus CF ou refus de visa). Grounded, adaptés au profil.
- Menu **Procédures & accompagnement** enrichi. Routeur d'intention en langage naturel étendu (« parcoursup »,
  « monmaster », « visa », « capago », « recours », « refus »…).

## v2.22.1 — 🔴 Correctif critique : modèles LLM dépréciés (bot bloqué)
- **Bug bloquant en prod** : les 3 modèles LLM renvoyaient 404 (Gemini `gemini-2.0-flash` **déprécié**,
  Groq/Cerebras 70B « no access ») → `call_groq` échouait → **les CV n'étaient plus analysés** (`/api/chat-cv`
  503), personne ne pouvait s'onboarder.
- **Fix** : modèles **configurables par env** (`GROQ_MODEL`, `GROQ_MODEL_FAST`, `CEREBRAS_MODEL`,
  `CEREBRAS_MODEL_FAST`, `GEMINI_MODEL`, `GEMINI_MODEL_FAST`) → on corrige un modèle déprécié sans toucher au
  code. Défaut Gemini passé à **`gemini-2.5-flash`**. URL Gemini construite depuis `GEMINI_MODEL`.
- **Robustesse** : `process_cv` n'échoue plus **en silence** — si le service IA est indisponible, l'utilisateur
  reçoit un message clair (« renvoie ton CV dans une minute »).

## v2.22 — Langage 100 % naturel & offres locales
- **Parler normalement suffit** : n'importe quelle phrase est comprise. Mots-clés en priorité (instantané),
  sinon le LLM décide en **un seul appel** s'il faut lancer une **action** (n'importe quelle commande, avec
  son argument) ou **répondre en conversation**. Les commandes restent utilisables. Repli mots-clés si le
  LLM est indisponible (pas de régression).
- **Champ élargi au LOCAL** : le système ne cherche plus seulement à l'étranger. Si les pays visés sont
  vides / « tous » / le propre pays de l'utilisateur, la veille inclut les opportunités **locales** (emplois,
  formations comme l'ASIN, bourses nationales). Détection nationalité→pays, prompts et requêtes adaptés.
  Question d'onboarding « pays visés » mentionne désormais le local.

## v2.21 — Boutons de confirmation & choix cliquables (rapport testeur, point 3)
- **Validation du CV** avec boutons : `✅ C'est correct` / `🔄 Recommencer` (au lieu de taper « Oui »).
- **Questions d'onboarding fermées** en boutons cliquables : objectif, financement, langue, niveau, type de
  poste — plus besoin de taper, et fini les réponses incohérentes sur ces champs.
- **Récapitulatif** validé par boutons : `✅ Oui, c'est bon` / `🔄 Recommencer`.
- Mécanique : clavier par tour (`_kb_options`) attaché au message, callbacks `onb:`/`pref:` rejoués comme une
  réponse tapée (la saisie texte reste possible). `deliver_text(..., options=…)` sur les 3 canaux.

## v2.20.2 — Affichage des formations (rapport testeur)
- Le message d'analyse du CV affiche désormais **toutes les formations** (jusqu'à 3, diplôme le plus élevé
  en tête, + « +N autres ») au lieu d'une seule — les données étaient déjà complètes, seul l'affichage
  induisait en erreur.
- **CV sans section Formation** : message explicite « Aucune formation détectée » (l'analyse continue, pas
  de blocage).

## v2.20.1 — Conversation libre corrigée (retour prod)
- **Avant onboarding** : un message libre reçoit une réponse *déterministe* (« envoie ton CV ») au lieu d'un
  LLM bavard qui disait « Bonjour », vouvoyait et redemandait le CV.
- **Utilisateur actif** : les messages libres sont *routés vers la vraie commande* selon l'intention
  (formations, école, logement, budget, Campus France, Canada, opportunités) — ex. « formations proposées
  par l'ASIN » lance une vraie recherche au lieu d'une réponse approximative.
- **Conversation** repassée sur le modèle 70B (le 8B ignorait le tutoiement / ne-pas-resaluer), consignes
  durcies (jamais « Bonjour »/« vous », ne jamais redemander le CV).

## v2.20 — Boîte à outils & procédures multi-pays
- **Outils PDF** : `/fusionner` (assembler des PDF), `/enpdf` (images→PDF, images envoyées en fichier),
  `/decouper <pages>` (extraire des pages), en plus de `/compresser`. Tampon de fichiers sur disque
  (volume persistant), `/terminer` / `/annuler`. Le endpoint accepte les images en mode img2pdf.
- **Outils conseil** : `/budget <ville>` (coût de la vie + preuve de ressources), `/eligibilite <cible>`
  (compare honnêtement le profil aux exigences), `/traduire <texte>` (traduction informative + rappel :
  dossier officiel = traducteur assermenté).
- **Procédures multi-pays** : `/procedure <pays>` générique (Belgique, Allemagne, Suisse, Luxembourg,
  Pays-Bas… routé par profil), en plus de `/campusfrance` (France) et `/canada`. Menu enrichi.
- **Fix** : f-string sans placeholder.

## v2.19 — Motivation & outils
- **Première veille automatique** dès le profil validé : 3 pistes tout de suite (valeur immédiate) + promesse
  d'un digest quotidien lié au profil.
- **Gamification** : `/status` affiche la progression (opportunités trouvées, +N cette semaine, dossiers,
  barre Campus France ▓▓▓░░). Digest quotidien enrichi (preuve sociale : « N nouvelles cette semaine »).
- **Outil compression PDF** : `/compresser [Ko]` puis envoi d'un PDF → version allégée pour les soumissions
  en ligne (Campus France, visa…). Reconstruction lossless puis, si besoin, ré-encodage image à DPI
  décroissant (testé : 20 Mo → <200 Ko). Bouton « 🗜️ Compresser un PDF » dans *Mon espace*.
- **Fix** : Pillow importé indépendamment de tesseract (l'OCR manquant ne désactive plus la compression).

## v2.18 — Mode « conseiller d'orientation senior » & accompagnement des procédures
- **Bilan d'orientation au CV** : à l'analyse, le bot rend un mini-bilan personnalisé (atouts, axes à
  renforcer, 2-3 pistes réalistes de destinations/programmes) — l'onboarding devient un vrai conseil, pas
  une simple extraction. Persona `CONSEILLER_PERSONA` partagée (aussi appliquée à la conversation libre).
- **Campus France vraiment accompagné** : `/campusfrance` présente la procédure + oriente vers l'aide ;
  `/parcours` affiche, pour l'étape en cours, l'action concrète + la commande qui aide.
- **Nouvelles commandes d'accompagnement** (ancrées web, adaptées au profil) :
  `/ecoles <domaine>` (trouver les bonnes écoles), `/logement <ville>` (se loger sans arnaque : CROUS,
  Visale…), `/entretien [type]` (prépa entretien Campus France / Institut Français / visa Capago-VFS avec
  questions types + pistes de réponse), `/canada` (voies d'immigration routées par profil : permis d'études,
  PGWP, Entrée express, PEQ/Arrima Québec).
- Menu **Procédures & accompagnement** enrichi (Campus France · Parcours · École · Logement · Entretien ·
  Canada). Helper réutilisable `conseil_grounded`.

## v2.17.2 — RSS tolérant (feeds mal formés)
- `fetch_rss` : si le XML strict échoue (afterschoolafrica, youthop… : `&` nus, CDATA), repli sur une
  extraction **régex tolérante** (gère CDATA + entités) ; page HTML → `[]` en silence. Log en warning au
  lieu d'error.

## v2.17.1 — EURAXESS opérationnel + RSS anti-bot
- **User-Agent navigateur** pour EURAXESS, les flux RSS et arbeitnow : certains sites (EURAXESS,
  afterschoolafrica, youthop) renvoyaient une page de blocage aux bots → plus d'offres/flux récupérés.
- **Extraction EURAXESS fiabilisée** : offres = liens `/jobs/<id>` ; comme une carte lie l'offre deux fois
  (image + titre), on garde l'intitulé le plus long (le vrai titre) au lieu de rater l'offre.

## v2.17 — Correctifs quotas & embeddings (logs de prod)
- **Embeddings réparés** : `text-embedding-004` était refusé (404) par la clé → le matching sémantique
  était KO. On essaie maintenant plusieurs modèles (`gemini-embedding-001`, `text-embedding-004`,
  `embedding-001`) et on retient le premier disponible ; si aucun, repli lexical **sans spam de logs**.
- **Fin des 429 en cascade sur la veille** : la collecte ne lance plus un appel LLM (osint Tavily) **par
  utilisateur** (16 users = 16 appels simultanés → quotas explosés). Le digest s'appuie sur le **pool de
  sources** (RSS + Adzuna + EURAXESS + arbeitnow) matché par profil ; l'osint complet reste à la demande via
  `/mobilite`. Réactivable avec `COLLECT_OSINT_PER_USER=1`. Concurrence collecte réduite (5→3).

## v2.16 — Fetcher EURAXESS (API adaptative)
- **EURAXESS par API** au lieu du RSS : `fetch_euraxess(query)` interroge EURAXESS avec les **mots-clés
  réels des utilisateurs** (comme Adzuna). Endpoint **auto-sondé** parmi des candidats, ou fixé via
  `EURAXESS_API` (`{q}` = requête). Parseur **générique** (JSON de formes variées : results/hits/_embedded…,
  ou XML/RSS) → titre/url/description quels que soient les noms de champs. Découverte à la 1ʳᵉ requête puis
  arrêt si l'endpoint ne répond pas (pas de requêtes inutiles). Échec **silencieux et sûr** (n'ajoute rien,
  ne casse pas la veille). Offres taguées `fellowship`. Le flux `EURAXESS_RSS` reste possible en complément.

## v2.15 — Adzuna adaptatif & multi-pays
- **Requêtes Adzuna adaptatives** : au lieu d'une liste figée, les requêtes sont construites à partir des
  **mots-clés réels des utilisateurs actifs** (les plus fréquents d'abord) + compétences ; repli sur
  `ADZUNA_QUERIES` si aucun. Les offres collectées collent donc à ce que les testeurs recherchent vraiment.
- **Multi-pays** : `ADZUNA_COUNTRY` accepte plusieurs pays (ex. `fr,ca,be`). `/health` : `adzuna_countries`.

## v2.14 — EURAXESS + RSS élargis & correctifs testeurs (rapport Carmelle)
- **Sources élargies** : 4 flux RSS supplémentaires (afterschoolafrica, opportunitiesforyouth, youthop,
  mladiinfo) + **EURAXESS** (recherche/PhD/postdoc EU) via `EURAXESS_RSS`, + `SOURCE_FEEDS_EXTRA` pour
  ajouter des flux sans toucher au code. `/health` : `euraxess_configured`, `rss_feeds`.
- **Correctifs retours testeurs :**
  - *Diplôme principal* : le profil retient désormais le diplôme le **plus élevé/récent** (master avant
    licence) — tri déterministe par niveau + année.
  - *Objectif « travailler »* : nouvelle question **type de poste** (temps plein / partiel / télétravail /
    alternance), injectée dans la recherche d'offres.
  - *Doublons /mobilite* : anti-doublons entre deux `/mobilite` successifs (mémoire des URLs déjà vues).
  - *Mots-clés multiples* : la recherche couvre désormais **tous** les mots-clés (requête OR + consigne de
    diversité) au lieu d'un seul.
  - *Faux assistant de dossier* : le mode conversationnel **ne simule plus** de formulaire multi-étapes ni
    ne prétend créer un dossier — il renvoie vers la commande unique `/dossier <cible>` / `/postuler <cible>`.

## v2.13 — Routing de modèle · sources emploi · rappels programmables · feedback 👍/👎
- **Routing de modèle** : les tâches simples (conversation libre en mode actif) partent sur un **petit
  modèle rapide** (llama-3.1-8b / gemini-flash) ; l'analyse CV, la sélection d'offres et la rédaction de
  documents gardent le **70B**. Moins de latence, quotas mieux préservés. (`call_groq(..., tier="fast")`).
- **Sources d'emploi structurées** : ingestion d'**arbeitnow** (sans clé) et **Adzuna** (clés gratuites
  optionnelles) dans le pool d'offres, en plus des flux RSS bourses. Les offres portent leur vrai **type**
  (emploi/bourse) et passent par le scoring sémantique par profil.
- **Rappels & digest programmables** : `/rappels on|off` et `/digest quotidien | hebdo <jour>`. La veille
  proactive respecte le choix de chaque utilisateur (fréquence, jour). Les rappels de deadline des dossiers
  restent toujours actifs.
- **Feedback 👍/👎 sur les offres** : boutons sous les résultats `/mobilite` et `/veille`. Les votes sont
  **appris par signature d'offre** (type + domaine) et **réinjectés dans le score** (±25) — le bot propose
  moins ce que l'utilisateur rejette, plus ce qu'il valide. `/health` : `adzuna_configured`.

## v2.12 — Export Word & matching sémantique
- **Export Word (.docx)** : `/postuler` et `/dossier` envoient désormais, en plus des PDF, des versions
  **Word modifiables** du CV et de la lettre/projet (demande des testeurs : « pouvoir modifier direct »).
  `python-docx` (pur Python, zéro dépendance système). Le type MIME des envois est déduit de l'extension
  (Telegram/WhatsApp/Messenger).
- **Matching sémantique des offres (embeddings)** : la pertinence ne repose plus seulement sur les mots-clés.
  On calcule la **similarité de sens** entre le profil et chaque offre (embeddings `text-embedding-004`,
  multilingue, via la clé Gemini déjà en place). Utilisé pour (a) re-trier les résultats web avant sélection
  LLM dans `/mobilite`, (b) mélanger score LLM + similarité (60/40), (c) filtrer/scorer les sources RSS de la
  veille (fini le score fixe à 62). Vecteurs mis en cache 7 j (quotas préservés). **Repli gracieux** : sans
  clé Gemini, on garde le classement mots-clés + LLM. `/health` expose `docx_configured` et
  `semantic_matching`.

## v2.11 — Performance & robustesse (passe senior)
- **Client HTTP partagé** : un seul `httpx.AsyncClient` avec pool keep-alive pour *tous* les appels
  sortants (LLM, Tavily, Telegram, WhatsApp, Messenger) au lieu d'un nouveau client (handshake TCP/TLS) à
  chaque requête. Gain de latence et de sockets sous forte charge (100+ testeurs), fermé proprement au
  shutdown.
- **Travail bloquant hors boucle asyncio** : l'OCR (tesseract), l'extraction PDF et la génération des PDF
  (reportlab) passent par `asyncio.to_thread`. Un CV scanné lourd ne gèle plus les autres utilisateurs du
  worker pendant plusieurs secondes.
- **Anti-message perdu (Telegram)** : si un `*`/`_`/`[` déséquilibré (texte LLM ou utilisateur) fait
  échouer l'envoi Markdown (400 « can't parse entities »), on renvoie automatiquement en texte brut — le
  message arrive toujours.

## v2.10.1 — Menu à la demande (moins de bruit)
- Le **menu à boutons ne se ré-affiche plus à chaque réponse** (onboarding comme mode actif). Il apparaît
  seulement quand c'est utile : **une fois** à la validation du profil, et sur demande via **`/menu`**
  (ou `/aide`). Discussions plus courtes et lisibles.

## v2.10 — Corrections retours testeurs
- **Rejet des fichiers non-CV** : à l'analyse, le LLM juge d'abord si le document est bien un CV
  (`est_cv`) ; sinon (facture, article, capture, texte quelconque) il est refusé au lieu de valider un
  profil vide. Double garde-fou heuristique (nom + formation/expérience/compétences présents).
- **Onboarding cohérent** : chaque réponse est validée (`valider_pref`). Les commandes tapées par erreur
  (`/hej`…) et les réponses incohérentes (ex. « Taf » comme certification de langue) sont refusées avec un
  indice, sans avancer — fini les profils validés avec une syntaxe fausse.
- **Documents PDF** : en-tête du CV corrigé (nom + titre plus aérés, interlignage explicite, échappement
  XML) — plus de chevauchement en haut. Génération CV/lettre **ancrée sur les expériences et formations
  réelles** du candidat, avec interdiction explicite des tournures d'IA et clichés (« je suis convaincu
  que », « correspond parfaitement »…).

## v2.9 — OCR des CV scannés
- **OCR automatique** (`tesseract-ocr` + `pytesseract`) : quand un PDF ne contient pas de texte
  sélectionnable (CV scanné / photographié), `extract_text_pdf` bascule sur un rendu image page par page
  (`fitz` pixmap, zoom ≈216 dpi) puis reconnaissance `image_to_string` en **fra+eng**. Garde-fous
  `OCR_MAX_PAGES` / `OCR_ZOOM`. Import **tolérant** : sans le binaire tesseract, l'app démarre quand même
  (OCR désactivé, message d'erreur adapté). `/health` expose `ocr_configured`.
- Ajout de `api/requirements.txt` et `api/Dockerfile` au dépôt (paquets système
  `tesseract-ocr-fra`/`tesseract-ocr-eng` + `pytesseract`/`Pillow`).

## v2.8 — Résilience LLM multi-fournisseurs
- Routeur de repli **Cerebras → Groq → Gemini** (mêmes appels, bascule auto sur quota/erreur) pour tenir
  la charge de 100+ testeurs sur quotas gratuits. `/health` expose `llm_providers`.

## Infrastructure & fiabilité
- **Webhook Telegram stabilisé** : URL publique fixe via **ngrok domaine statique** (fin de la boucle
  `{"message":"Provided secret is not valid"}` causée par le tunnel trycloudflare éphémère). Règle d'or :
  un seul workflow avec Telegram Trigger actif (WF1), et on ne relance jamais `setWebhook` à la main.
- **Déploiement durable** : `forge-nex-api` sous **docker-compose** (image qui embarque `main.py`,
  `.env`, **volume `./data`** pour `sessions.db`). Fin des `docker cp` fragiles.
- **Attribution retirée** : plus de « This message was sent automatically with n8n ».

## Backend FastAPI (`api/main.py`)
- **Bug `Form(...)`** corrigé : `/api/chat-cv` lit enfin `user_id`/`chat_id` du multipart (avant : sauvés
  sous « unknown »).
- **Sessions persistantes** : `SessionManager` → **SQLite** (partagé entre les 2 workers uvicorn, survit
  aux redémarrages). Correctif du bug `/health` (`_cache` supprimé).
- **Onboarding déterministe** : machine à états en code (plus de boucle LLM). 8 critères d'éligibilité
  collectés : objectif, nationalité, pays cibles, financement, certifs de langue, langue, niveau, mots-clés.
- **Token Telegram** : lu depuis l'env (`TELEGRAM_TOKEN`/`TELEGRAM_BOT_TOKEN`), repli fichier.

## Fonctionnalités bot (commandes)
- `/start` (réinitialise + tutoriel), `/tuto` (guide pas à pas), `/aide`.
- `/mobilite <pays/domaine>` — analyse mobilité.
- `/veille` — recherche d'opportunités à la demande (stockées, dédoublonnées).
- `/campusfrance` — procédure « Études en France » (étapes, bourses, documents), **grounded** via Tavily.
- `/postuler <cible>` — génère **CV adapté + lettre de motivation** (ou SOP académique pour une bourse),
  envoyés en PDF dans Telegram.
- `/profil`, `/status`, `/supprimer` (RGPD).
- Menu de commandes Telegram (`setMyCommands`).

## Qualité des résultats
- **Grounding web (Tavily)** : `/mobilite`, `/veille`, `/campusfrance` cherchent de **vraies annonces**
  et Groq ne fait que **sélectionner/scorer** parmi les résultats réels (URL exactes, pas d'invention).
  Repli « pistes IA durcies » si la clé Tavily est absente.
- **Types explicites** dans les résultats : 📚 FORMATION · 💼 EMPLOI · 🎓 BOURSE · 🔬 FELLOWSHIP.
- Niveau de **confiance** (🟢🟡🔴), portail/lien, deadline, bandeau « à vérifier ».

## Veille automatique (WF0 — orchestrateur 24 h)
- `/api/collect` — pour chaque utilisateur actif : recherche + scoring → stocke les **nouvelles** offres
  (table SQLite `offres`, dédup par URL).
- `/api/score` — résumé des offres en attente.
- `/api/notify` — envoie un **digest Telegram proactif** (offres score ≥ 60 non encore notifiées) puis les
  marque `notified` (pas de spam).

## Branding
- **Forge NEX → NexMove** partout dans l'expérience utilisateur (« ton prochain départ » : études, emploi,
  bourses, mobilité).

## v2.3 → v2.5 (efficience & pré-lancement)
- `/health` versionné (VERSION dynamique) — vrai témoin de déploiement.
- **Anti-offres expirées** : date du jour dans les prompts + filtre déterministe des deadlines passées.
- **Sprint efficience** : veille parallélisée (`asyncio.gather`), cache Tavily (TTL 6 h), `search_depth: advanced`.
- **Sources structurées** : ingestion de flux RSS de bourses réels (scholars4dev, OpportunityDesk,
  OpportunitiesForAfricans) → table `sources_offres`, matchées au profil dans la veille.
- **`/formations <domaine>`** : recommandations de formations/certifications (grounded) pour se distinguer.
- **Suivi Campus France par étapes** : `/parcours` (roadmap EEF jusqu'au départ) + `/etape` (valider l'étape courante).

## Reste à faire (optionnel)
- OCR (CV scannés) + export **DOCX** (nouvelles dépendances → `requirements.txt`).
- Sources structurées supplémentaires (RSS bourses, API emploi) en plus de Tavily.
- Tracker de candidatures détaillé + `/status` enrichi.
- Montée en charge : paralléliser `/api/collect` (actuellement séquentiel).
