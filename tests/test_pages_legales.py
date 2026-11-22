"""Cohérence des pages légales (CGU + politique de confidentialité).

Ces pages sont des engagements publics : une section mal numérotée ou un renvoi « §7 » qui
pointe dans le vide décrédibilise tout le reste. En ajoutant la section « Qui peut utiliser
NexMove » aux CGU, la numérotation s'est effectivement cassée — d'où ces contrôles.
"""
import re, pathlib
import pytest

WEB = pathlib.Path(__file__).resolve().parent.parent / "web"
PAGES = ["cgu.html", "confidentialite.html"]


def _html(nom):
    return (WEB / nom).read_text(encoding="utf-8")


def _sections(contenu):
    return [(int(n), titre) for n, titre in re.findall(r"<h2>(\d+)\.\s*([^<]+)</h2>", contenu)]


@pytest.mark.parametrize("page", PAGES)
def test_numerotation_continue(page):
    nums = [n for n, _ in _sections(_html(page))]
    assert nums, f"{page} : aucune section numérotée trouvée"
    assert nums == list(range(1, len(nums) + 1)), f"{page} : numérotation cassée -> {nums}"


@pytest.mark.parametrize("page", PAGES)
def test_renvois_internes_valides(page):
    """Un « §N » doit désigner une section qui existe (dans cette page ou celle visée par le lien)."""
    contenu = _html(page)
    maxi = max(n for n, _ in _sections(contenu))
    maxi_autre = max(n for n, _ in _sections(_html(
        "confidentialite.html" if page == "cgu.html" else "cgu.html")))
    for ref in re.findall(r"§\s*(\d+)", contenu):
        assert int(ref) <= max(maxi, maxi_autre), f"{page} : renvoi §{ref} vers une section inexistante"


@pytest.mark.parametrize("page", PAGES)
def test_balises_bien_fermees(page):
    from html.parser import HTMLParser

    class P(HTMLParser):
        VIDES = {"meta", "link", "br", "img", "hr", "input"}

        def __init__(self):
            super().__init__(); self.pile = []; self.erreurs = []

        def handle_starttag(self, t, a):
            if t not in self.VIDES:
                self.pile.append(t)

        def handle_endtag(self, t):
            if self.pile and self.pile[-1] == t:
                self.pile.pop()
            elif t in self.pile:
                self.erreurs.append(f"<{t}> mal imbriquée")

    p = P(); p.feed(_html(page))
    assert not p.erreurs and not p.pile, f"{page} : {p.erreurs or p.pile}"


def test_le_public_scolaire_est_assume_partout():
    """N-02 : la politique ne doit plus dire « réservé aux majeurs » pendant que le bot
    conseille des lycéens. Les deux pages doivent porter le même message."""
    conf = _html("confidentialite.html")
    cgu = _html("cgu.html")
    assert "s'adresse à des personnes majeures" not in conf, \
        "l'ancienne formulation contredit le module d'orientation"
    for mot in ("lycéen", "collégien", "16 ans"):
        assert mot in conf.lower() or mot in conf, f"politique : « {mot} » attendu en §9"
    assert "16 ans" in cgu and "confidentialite.html" in cgu, \
        "les CGU doivent cadrer le public et renvoyer à la politique"


def test_la_promesse_de_suppression_reste_precise():
    """Garde-fou v3.97 : ne pas re-promettre « tout est supprimé » de façon vague."""
    conf = _html("confidentialite.html")
    assert "/supprimer" in conf
    assert "profil portable" in conf, "la politique doit nommer ce qui est réellement supprimé"
    assert "sans ton identifiant" in conf, "la conservation anonymisée doit rester documentée"
