# Instructions de travail — projet NexMove

Ce fichier est lu **automatiquement** au début de chaque session Claude Code dans ce dépôt.
C'est l'équivalent des instructions d'un projet sur claude.ai. Il n'a pas besoin d'être
mentionné : il s'applique.

Les règles ci-dessous ne sont pas des principes généraux. Chacune vient d'un **incident réel
de ce projet**, daté, qui a coûté quelque chose.

---

## 1. Ce qui ne se fait jamais

**Aucun secret dans le dépôt.** Il est **public**. Le `.env` ne se commite pas, même vide
d'exemple. *Incident : la clé `FORGE_NEX_API_KEY` a été publiée et l'API refuse désormais
cette valeur en dur.*

**Aucun nom de personne réelle, nulle part.** Ni dans un exemple montré à l'utilisateur, ni
dans un test, ni dans un commentaire, ni dans le journal des évolutions. Un exemple n'a jamais
besoin d'un nom : « ton nom exact » dit la même chose. Placeholder admis : *Marie Dupont*.
*Incident (v3.59 → v4.15) : le bot affichait à tous ses utilisateurs le nom d'une vraie
utilisatrice, pendant six mois, dans un dépôt public. Le test `test_vie_privee_exemples.py`
l'interdit maintenant.*

**Aucune donnée personnelle hors du serveur.** Pas de nom, d'e-mail, de numéro ni de contenu
de CV dans un commit, une PR, un fichier Drive ou une requête vers un service tiers.

**Rien d'inventé.** Jamais un chiffre, une URL, une date limite, un nom d'école, de bourse ou
d'entreprise produit de mémoire. Si la donnée vient du web, elle est vérifiée contre la source ;
sinon elle ne part pas. *Incident : le modèle renvoyait des liens plausibles mais morts à des
gens qui cherchent une bourse. Corrigé par `_lien_verifie` en v4.06.*

**Ne jamais affirmer l'état de la production.** Elle n'est pas joignable depuis une session de
développement. Ce qui tourne est **rapporté par le Propriétaire**. Écrire « déployé » sans
confirmation est un mensonge.

---

## 2. Comment on décide

**Mesurer avant d'optimiser.** Un chiffre avant, un chiffre après, dans un test qui reste.
*Le routage du langage naturel a tourné des mois avec 218 mots-clés sans qu'aucune mesure
existe : première mesure, 55 %.*

**Un jeu d'évaluation écrit par celui qui code ne mesure rien.** Il mesure sa mémoire. Seules
les lignes marquées `"source": "terrain"` dans `tests/jeu_routage.jsonl` comptent. *Mesuré :
100 % sur le lot que j'avais corrigé, 70 % sur un lot écrit juste après.*

**Un fait produit se tranche dans le code, jamais par le modèle.** Version, prix, quota,
existence d'une commande, lien, danger : si la réponse est connue, elle est déterministe.
Une consigne dans une invite **n'est pas un garde-fou**. *Incidents : le vouvoiement, les liens
inventés, les commandes inconnues — l'invite le demandait déjà à chaque fois.*

**Les deux erreurs ne coûtent jamais pareil.** Avant de choisir un seuil, dire laquelle fait le
plus de dégâts. *Prendre une question de suite pour une nouvelle recherche donne des résultats
hors sujet présentés comme une réponse ; l'inverse laisse simplement l'orchestrateur trancher.*

**Préférer un refus propre à une conversion approximative.** `_tutoie` rend le texte d'origine
si une seule forme résiste : un ton formel se pardonne, une conjugaison cassée non.

---

## 3. Le processus, qui a déjà sauvé la production deux fois

**La CI verte avant toute fusion.** Les quatre contrôles — `test`, `docker-smoke`,
`deploy-path`, `audit` — et **aucun job encore en cours**. Compter « 4 terminés » ne suffit
pas : les jobs tournent parfois en double. *Incident : une PR fusionnée sur un `docker-smoke`
en échec a cassé la production (v3.96). Et le 25/11 la règle a bloqué une fusion que je
croyais prête.*

**Avant chaque commit** : `python3 -m pytest tests -q` **et**
`python3 -m ruff check api/ --select=E9,F63,F7,F82,F821`. *Ruff a attrapé une variable
d'exception hors portée que ma relecture avait manquée.*

**Une PR = un sujet.** Branche `claude/<sujet>`, jamais de commit direct sur `main` (la règle
le refuse de toute façon).

**Tout changement visible monte la version** (`api/main.py`), et met à jour `docs/CHANGELOG.md`
et `docs/ETAT-ACTUEL.md`. Le garde-fou vérifie le numéro, les commandes documentées et les
quotas — mais pas le reste : la vigilance reste nécessaire.

---

## 4. Ce qu'on écrit

**Du français, tutoiement, voix active.** Le bot tutoie partout, sans exception.

**Les commentaires disent *pourquoi*, pas *quoi*.** Un commentaire utile explique la décision
ou nomme l'incident qui l'a causée. Le code dit déjà ce qu'il fait.

**Pas de tics d'écriture.** Pas de tiret long en pause dramatique, pas d'énumération en trois
temps systématique, pas de « X ne fait pas A, il fait B » répété. *Le Propriétaire les a
repérés le 25/11 : ils étaient partout dans ma copie.*

**Dire ce qui ne marche pas.** Un rapport qui n'annonce que des succès ne sert à rien. Les
limites, les hypothèses non vérifiées et les erreurs se disent en premier.

---

## 5. Le domaine, et ce qu'il impose

NexMove conseille des jeunes d'Afrique de l'Ouest sur les études, l'emploi et le départ à
l'étranger. Trois conséquences qui ne se négocient pas :

**Le public inclut des mineurs.** Le module d'orientation détecte « collège » et « lycée ».
La politique de confidentialité l'assume (§9) : elle doit le rester.

**L'arnaque à l'avance de frais est endémique.** « Paie et je te garantis le visa » ruine des
familles. La détection est déterministe (`orientation.py`), prioritaire sur tous les flux, et
couvre les voies illégales. Les frais légitimes (Campus France, TLS/VFS, scolarité, loyer) ne
déclenchent rien : crier au loup les rendrait suspects.

**Les gens vont parfois très mal.** La détection de détresse sort de tout questionnaire et
oriente vers un humain. Le bot n'est pas thérapeute et le dit.

**Le contexte compte autant que la compétence.** Budget serré, décision familiale, voie courte,
auto-emploi : ce sont de vrais choix, pas des solutions de repli. Un conseil qui suppose de
l'argent disponible ne sert à personne ici.

---

## 6. Repères techniques

- `api/` : 6 modules. `main.py` est un monolithe de ~12 000 lignes, **assumé** — extraction
  progressive vers des modules purs (modèle : `orientation.py`), au fil des zones touchées.
  Pas de réécriture globale sans déclencheur mesuré.
- **VPS : 2 Go de RAM, 1–2 vCPU, 2 workers uvicorn.** Cette contrainte tranche beaucoup de
  débats d'architecture : un modèle d'embeddings local n'y tient pas à côté de PyMuPDF,
  Pillow et tesseract.
- Tout état en mémoire est **par worker** : il y en a deux. Un compteur en mémoire ne voit que
  la moitié du trafic. *Incident v4.12.*
- `docs/ETAT-ACTUEL.md` est la **seule référence** sur ce qu'est le système. En cas de
  contradiction avec un autre document, c'est elle qui fait foi, et le code tranche en dernier.
- Le test d'orientation a **une seule source** : `api/orientation.py`. `web/orientation-data.js`
  est généré par `scripts/gen-orientation-web.py`, et la CI compare les deux implémentations.

---

## 7. Quand demander

Demander avant : de toucher à l'infrastructure, de changer un prix ou un quota, de publier
quelque chose à l'extérieur, de modifier la politique de confidentialité ou les CGU.

Ne pas demander pour : corriger un défaut mesuré, ajouter un test, mettre la documentation à
jour. Ce sont des réparations, pas des décisions.
