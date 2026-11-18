"""Orientation professionnelle : détection d'intention, situation scolaire/pro, mini-test d'intérêts.

Module PUR (aucun réseau, aucun LLM) : tout est déterministe et testable.
Le câblage session / LLM est dans main.py (/orientation, /testorientation).
"""
from __future__ import annotations

import re
import unicodedata


def _fold(s: str) -> str:
    """minuscules sans accents, apostrophes normalisées."""
    s = (s or "").lower().replace("’", "'")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


# ── 1. Détection d'une demande d'ORIENTATION (≠ recherche d'offres) ──────────────────────────────
# Une question d'orientation porte sur le CHOIX (quoi faire, quelle voie, est-ce que ça vaut le coup),
# pas sur la RECHERCHE d'une opportunité précise (« trouve-moi un stage »).
_DOM = r"(metiers?|filieres?|series?|etudes|formations?|voies?|orientation|domaines?|parcours|masters?|licences?|bts|specialites?|carrieres?|secteurs?|branches?)"
_ORIENT_PATTERNS = [
    # « quel métier choisir / me correspond / est fait pour moi »
    rf"\bquel(le)?s?\s+{_DOM}\b[^.?!]{{0,45}}\b(choisir|faire|prendre|suivre|me\s+correspond\w*|me\s+convien\w*|pour\s+moi|fait\s+pour\s+moi|me\s+va|m'?irai\w*|adapte\w*)",
    rf"\b(choisir|trouver)\s+(mon|ma|mes|un|une|le|la)\s+{_DOM}\b",
    r"\b(hesite\w*|choisir|trancher)\s+entre\b",
    # « je ne sais pas quoi faire / vers quoi aller »
    r"\b(je\s+(ne\s+)?sais\s+(pas|plus)|j'?sais\s+pas|aucune\s+idee|je\s+vois\s+pas)\b[^.?!]{0,35}\b(quoi\s+faire|quoi\s+etudier|vers\s+quoi|dans\s+quoi|quel\s+metier|quelle\s+filiere|ce\s+que\s+je\s+veux|ou\s+aller|quoi\s+choisir|faire\s+quoi|ma\s+voie)",
    r"\b(perdu|perdue|bloque|bloquee|desoriente\w*|paume\w*)\b[^.?!]{0,30}\b(carriere|etudes|orientation|avenir|vie\s+pro\w*|parcours|metier)",
    r"\b(trouver|chercher)\s+ma\s+voie\b",
    # « comment devenir X », « quelles études pour devenir X »
    r"\b(comment|quoi\s+faire\s+pour|que\s+faire\s+pour)\s+devenir\b",
    rf"\bquel(le)?s?\s+{_DOM}\b[^.?!]{{0,25}}\bpour\s+(devenir|etre|faire|travailler)\b",
    r"\b(etudes|parcours|diplome)\s+(pour|necessaires?\s+pour)\s+(devenir|etre)\b",
    # débouchés, avenir d'un métier, ce qui recrute
    r"\bdebouche\w*\b",
    r"\b(a|ont)\s+(de\s+l'?|un\s+)avenir\b",
    r"\bquel(le)?s?\s+(metiers?|secteurs?|domaines?|filieres?)\s+(recrute\w*|embauche\w*|marche\w*|pai\w*|rapporte\w*|ont\s+de\s+l'?avenir)",
    # bilan / test / conseil d'orientation, réorientation, reconversion
    r"\b(bilan\s+de\s+competences?|conseill?\w*\s+d'?orientation|orientation\s+pro\w*|m'?orienter|me\s+reorienter|reorientation|projet\s+professionnel|projet\s+pro)\b",
    r"\b(me\s+)?reconvert\w*\b|\breconversion\b|\bchanger\s+de\s+(metier|carriere|voie|domaine|filiere)\b",
    # arbitrages typiques
    r"\b(faut[- ]il|vaut[- ]il\s+mieux|vaut\s+mieux|mieux\s+vaut|est[- ]ce\s+mieux|c'?est\s+mieux)\b[^.?!]{0,50}\b(master|licence|bts|doctorat|etudes|travailler|formation|universite|fac|ecole|concours|apprentissage)\b",
    r"\b(master|licence|bts|etudes|universite|fac)\b[^.?!]{0,30}\bou\b[^.?!]{0,30}\b(travailler|bosser|master|licence|bts|formation|apprentissage|entreprendre)\b[^.?!]*\?",
    # après un diplôme / examen
    r"\bapres\s+(le|mon|un|son|l')\s*(bac|bepc|cep|bts|dut|licence|master|cap|brevet)\b[^.?!]{0,40}\b(quoi|faire|choisir|filiere|etudes|orientation|ensuite)\b",
    # forces / goûts exprimés pour se situer
    r"\bje\s+suis\s+(bon|bonne|fort|forte|nul|nulle|doue\w*)\s+en\b[^.?!]{0,60}\b(j'?aime|j'?adore|metier|faire\s+quoi|quoi\s+faire|me\s+conseilles?|filiere)",
    r"\bj'?(aime|adore)\s+(bien\s+)?(le|la|les|l')\s*\w+[^.?!]{0,40}\b(metier|filiere|faire\s+quoi|quoi\s+faire|travailler\s+dans|en\s+faire\s+mon)",
    # pression familiale
    r"\b(mes\s+parents|mon\s+pere|ma\s+mere|ma\s+famille|mon\s+oncle|ma\s+tante)\s+(veu\w+|me\s+pousse\w*|m'?oblige\w*|insiste\w*)\b[^.?!]{0,30}\b(que\s+je\s+(fasse|devienne|etudie|choisisse|sois|prenne|aille\s+en)|etudier|devenir|faire\s+des\s+etudes)",
    # échec / décrochage
    r"\bj'?ai\s+(rate|echoue|loupe|abandonne|arrete)\b[^.?!]{0,30}\b(concours|bac|bepc|examen|annee|l1|l2|l3|fac|universite|etudes|ecole|licence|master)",
    # rapport négatif à l'école / voie pro
    r"\b(l'?ecole|les\s+etudes|la\s+fac|l'?universite)\s+(c'?est\s+pas|ce\s+n'?est\s+pas|n'?est\s+pas)\s+(pour\s+moi|mon\s+truc)",
    r"\bmetier\s+manuel\b|\bvoie\s+pro(fessionnelle)?\b|\bapprendre\s+un\s+metier\b",
    # attentes sur un métier : rémunération, stabilité
    r"\bmetier\s+qui\s+(pai\w*|rapporte\w*|recrute\w*|embauche\w*|a\s+de\s+l'?avenir)",
    r"\b(salaire|revenu|combien\s+(gagne|touche|paie|paye))\s+(d'?un|d'?une|un|une|les|des)\s+\w+",
    # expérience vécue qui fait douter
    r"\b(stage|job|travail|filiere|formation|metier|boulot)\b[^.?!]{0,40}\b(m'?a\s+pas\s+plu|ne\s+m'?a\s+pas\s+plu|me\s+plait\s+(pas|plus)|m'?ennuie|j'?aime\s+pas|je\s+n'?aime\s+pas)",
    # entrepreneuriat comme voie
    r"\b(je\s+veux|j'?aimerais|je\s+voudrais|envie\s+d')\s*(entreprendre|creer\s+(mon|ma|une)\s+(entreprise|boite|business|startup)|me\s+lancer\s+a\s+mon\s+compte|lancer\s+mon\s+(business|activite))",
    # contrainte financière sur les études
    r"\bpas\s+(les\s+)?moyens\b[^.?!]{0,40}\b(etudes|universite|fac|ecole|formation|etudier)",
]
_ORIENT_RE = re.compile("|".join(f"(?:{p})" for p in _ORIENT_PATTERNS))

# Recherche CONCRÈTE d'opportunités : ce n'est pas de l'orientation, c'est /mobilite.
_SEARCH_RE = re.compile(r"\b(cherche[sz]?[- ]moi|trouve[sz]?[- ]moi|envoie[sz]?[- ]moi\s+des|des\s+offres|offres?\s+d'?emploi|"
                        r"je\s+(cherche|recherche)\s+(un|une|des)\s+(stage|emploi|job|boulot|bourse|alternance|poste|travail))\b")

_TEST_RE = re.compile(r"\b(test|quiz|questionnaire)\s+(d'?orientation|de\s+personnalite|d'?interets?|riasec|holland|metier)"
                      r"|\b(riasec|holland)\b"
                      r"|\b(test|quiz)\b[^.?!]{0,40}\b(savoir|trouver|decouvrir)\b[^.?!]{0,30}\b(ce\s+qui\s+me\s+(va|correspond|convient)|quel\s+metier|ma\s+voie|pour\s+moi)")


def is_orientation_query(text: str) -> bool:
    low = _fold(text)
    if not low or _SEARCH_RE.search(low):
        return False
    return bool(_ORIENT_RE.search(low))


def is_test_request(text: str) -> bool:
    return bool(_TEST_RE.search(_fold(text)))


# ── 2. Situation de la personne (déterministe, prudente) ──────────────────────────────────────────
_SERIES_BJ = {"a1", "a2", "b", "c", "d", "e", "f1", "f2", "f3", "f4", "g1", "g2", "g3", "s", "l", "es"}

def detect_situation(text: str) -> dict:
    """Extrait ce que la personne dit d'elle-même : niveau scolaire/pro, série du bac, années d'expérience.
    Ne renvoie que ce qui est dit explicitement (jamais de déduction hasardeuse)."""
    low = _fold(text)
    out: dict = {}
    m = (re.search(r"\bbac(?:calaureat)?\s*(?:serie\s*)?([a-g]\d?|s|l|es)\b", low)
         or re.search(r"\b(?:terminale|tle|premiere|1ere)\s+(?:serie\s+)?([a-g]\d?)\b", low))
    if m and m.group(1) in _SERIES_BJ:
        out["serie"] = m.group(1).upper()
    if re.search(r"\b(en\s+)?(3e|3eme|troisieme)\b|\bbepc\b|\bbrevet\b|\bcollege\b|\bcollegien\w*", low):
        out["niveau"] = "collège / BEPC"
    if re.search(r"\b(en\s+)?(seconde|2nde|premiere|1ere|terminale|tle)\b|\blyce\w+", low):
        out["niveau"] = "lycée"
    if re.search(r"\bj'?ai\s+(eu|obtenu|decroche|valide)\s+(mon|le)\s+bac\b|\bnouveau\s+bachelier|\bnouvelle\s+bacheliere|\bbachelier\w*", low):
        out["niveau"] = "bachelier"
    m = re.search(r"\b(en|je\s+suis\s+en)\s+(l[123]|m[12]|licence\s*[123]?|master\s*[12]?|bts\s*[12]?|dut|doctorat|1ere\s+annee|2e\s+annee|3e\s+annee)\b", low)
    if m or re.search(r"\b(etudiant|etudiante)\b", low):
        out["niveau"] = "étudiant" + (f" ({m.group(2).upper()})" if m else "")
    if re.search(r"\bj'?ai\s+(abandonne|arrete|quitte)\s+(en\s+\w+|l'?ecole|les\s+etudes|la\s+fac|l'?universite)", low):
        out["niveau"] = "études interrompues"
    if re.search(r"\b(diplome|diplomee)\b[^.?!]{0,30}\b(sans\s+emploi|au\s+chomage|je\s+cherche)|\bfraichement\s+diplome", low):
        out["niveau"] = "diplômé(e) en recherche"
    m = re.search(r"\bje\s+suis\s+([a-z\- ]{3,30}?)\s+depuis\s+(\d{1,2})\s+ans\b", low)
    if m:
        out["niveau"] = "en poste"
        out["poste"] = m.group(1).strip()
        out["experience_ans"] = int(m.group(2))
    elif re.search(r"\b(\d{1,2})\s+ans\s+d'?experience\b", low):
        out["niveau"] = "en poste"
        out["experience_ans"] = int(re.search(r"\b(\d{1,2})\s+ans\s+d'?experience", low).group(1))
    return out


# ── 3. Mini-test d'intérêts (modèle RIASEC de Holland, 6 questions équilibrées) ──────────────────
# Chaque lettre apparaît exactement 4 fois sur 24 options (aucun biais de construction).
RIASEC = {
    "R": ("Concret", "tu aimes faire de tes mains, voir un résultat tangible, le terrain"),
    "I": ("Investigateur", "tu aimes comprendre, analyser, résoudre des problèmes"),
    "A": ("Artistique", "tu aimes créer, imaginer, t'exprimer"),
    "S": ("Social", "tu aimes aider, expliquer, prendre soin des autres"),
    "E": ("Entreprenant", "tu aimes convaincre, décider, lancer des projets"),
    "C": ("Organisé", "tu aimes l'ordre, la précision, les chiffres et les procédures"),
}

# Familles de métiers par dominante : générales et vérifiables, adaptées au marché ouest-africain
# (pas d'école, de salaire ni d'employeur cités).
METIERS = {
    "R": ["technicien(ne) BTP / génie civil", "électricien(ne), froid & climatisation", "mécanique auto / engins",
          "agronomie, élevage, transformation agroalimentaire", "géomètre-topographe", "maintenance industrielle"],
    "I": ["santé (médecine, pharmacie, biologie médicale)", "ingénierie (informatique, réseaux, énergie)",
          "data / statistiques", "recherche et laboratoire", "cybersécurité", "environnement & eau"],
    "A": ["design graphique, UI/UX", "architecture, décoration d'intérieur", "journalisme, rédaction, communication",
          "audiovisuel, photo, montage", "mode & stylisme", "métiers d'art et artisanat"],
    "S": ["enseignement, formation", "soins infirmiers, sage-femme", "travail social, ONG, humanitaire",
          "ressources humaines", "psychologie, orientation", "santé communautaire"],
    "E": ["commerce, vente, négociation", "création d'entreprise", "marketing, communication commerciale",
          "droit des affaires, juriste", "gestion de projet", "transit, import-export"],
    "C": ["comptabilité, audit, contrôle de gestion", "banque, microfinance, assurance", "logistique, gestion des stocks",
          "assistanat de direction, administration", "secrétariat juridique, fiscalité", "gestion des ressources (paie, achats)"],
}

TEST_QUESTIONS = [
    ("Un samedi libre, tu préfères…",
     [("R", "réparer ou bricoler quelque chose"), ("A", "dessiner, écrire ou faire de la musique"),
      ("S", "aider quelqu'un de ta famille ou du quartier"), ("E", "organiser une sortie ou vendre un truc")]),
    ("À l'école, ce que tu préférais…",
     [("I", "les sciences : comprendre comment ça marche"), ("C", "les exercices bien rangés, les tableaux"),
      ("A", "le dessin, la rédaction, les langues"), ("R", "les travaux pratiques, l'atelier, le terrain")]),
    ("Dans un travail de groupe, tu es plutôt celui ou celle qui…",
     [("E", "prend la tête et convainc les autres"), ("S", "fait que tout le monde s'entende"),
      ("C", "tient le planning et les comptes"), ("I", "cherche les infos et analyse")]),
    ("Ton lieu de travail idéal…",
     [("R", "dehors : chantier, champ, atelier"), ("C", "un bureau bien organisé"),
      ("S", "au contact des gens"), ("A", "un studio ou un lieu créatif")]),
    ("Ce qui te rendrait le plus fier ou fière…",
     [("I", "résoudre un problème que personne n'arrivait à régler"), ("E", "créer ta propre entreprise"),
      ("A", "créer une œuvre ou un design reconnu"), ("S", "avoir aidé quelqu'un à s'en sortir")]),
    ("Tu préfères travailler avec…",
     [("R", "des outils et des machines"), ("I", "des données et des expériences"),
      ("C", "des dossiers et des chiffres"), ("E", "des clients et des négociations")]),
]
assert all(sum(1 for _q, opts in TEST_QUESTIONS for l, _ in opts if l == L) == 4 for L in RIASEC)

_LETTER_IDX = {"a": 0, "b": 1, "c": 2, "d": 3, "1": 0, "2": 1, "3": 2, "4": 3}


def parse_test_answer(text: str, qi: int):
    """Réponse à la question qi : '1'..'4', 'a'..'d', ou un mot du libellé. Renvoie la lettre RIASEC ou None."""
    low = _fold(text).strip(" .!)")
    if not low or not (0 <= qi < len(TEST_QUESTIONS)):
        return None
    opts = TEST_QUESTIONS[qi][1]
    m = re.fullmatch(r"(?:reponse\s+|choix\s+|option\s+)?([1-4a-d])", low)
    if m:
        return opts[_LETTER_IDX[m.group(1)]][0]
    words = [w for w in re.findall(r"[a-z]{4,}", low) if w not in ("plutot", "prefere", "choisis", "celle", "celui")]
    if not words or len(low) > 80:
        return None
    best, score = None, 0
    for letter, label in opts:
        lab = _fold(label)
        s = sum(1 for w in words if w in lab)
        if s > score:
            best, score = letter, s
        elif s == score and s > 0:
            best = None if best != letter else best   # égalité entre deux options -> ambigu
    return best if score > 0 else None


def score_test(answers: list) -> str:
    """Code à 2 lettres (dominantes). Égalité départagée par l'ordre des réponses (la 1re citée gagne)."""
    counts: dict = {}
    first: dict = {}
    for i, l in enumerate(answers):
        if l in RIASEC:
            counts[l] = counts.get(l, 0) + 1
            first.setdefault(l, i)
    ranked = sorted(counts, key=lambda l: (-counts[l], first[l]))
    return "".join(ranked[:2])


def format_question(qi: int) -> tuple:
    """(texte, options[(libellé bouton, callback)])"""
    q, opts = TEST_QUESTIONS[qi]
    lignes = [f"*{qi + 1}/{len(TEST_QUESTIONS)} · {q}*", ""]
    for n, (_l, label) in enumerate(opts, 1):
        lignes.append(f"{n}. {label}")
    lignes.append("")
    lignes.append("_Réponds 1, 2, 3 ou 4 · ce qui te ressemble le plus, pas ce qui « fait bien »._")
    kb = [(f"{n}. {label}"[:40], f"ori:{qi}:{n}") for n, (_l, label) in enumerate(opts, 1)]
    return "\n".join(lignes), kb


def format_result(code: str) -> str:
    if not code:
        return ""
    noms = " – ".join(RIASEC[l][0] for l in code)
    lignes = [f"🧭 *Ton profil d'intérêts : {noms}*", ""]
    for l in code:
        lignes.append(f"• *{RIASEC[l][0]}* : {RIASEC[l][1]}.")
    lignes.append("")
    lignes.append("*Familles de métiers qui vont souvent avec :*")
    vus = []
    for l in code:
        for m in METIERS[l][:3]:
            if m not in vus:
                vus.append(m)
    lignes += [f"• {m}" for m in vus]
    lignes.append("")
    lignes.append("_Un test donne des pistes, il ne décide pas à ta place : tes résultats scolaires, ton budget "
                  "et ce que tu as envie de vivre comptent autant._")
    return "\n".join(lignes)
