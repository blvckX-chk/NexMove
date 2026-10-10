#!/usr/bin/env python3
"""audit-site.py — audit "senior" d'un site (concurrent, inspiration UI, veille).

Zéro dépendance (bibliothèque standard uniquement). Crawle une page et quelques pages du même
domaine, puis produit un rapport Markdown structuré : titre, meta/OG, hiérarchie des titres (H1-H3),
navigation, boutons/CTA, blocs de tarifs détectés, liens, et un extrait du texte visible par page.

Usage :
    python3 audit-site.py https://kaizenjob.cv
    python3 audit-site.py https://kaizenjob.cv -o rapport.md --max-pages 8

Puis envoie le fichier rapport.md (par défaut: <domaine>-audit.md).
"""
import sys, re, argparse, urllib.request, urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PRICE_RE = re.compile(r"(\d[\d .,]*)\s*(€|FCFA|XOF|\$|USD|EUR)|\b(gratuit|free|/mois|/an|per month|par mois)\b", re.I)


class Extract(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""; self.meta = {}; self.headings = []; self.links = []
        self.buttons = []; self.text = []
        self._skip = 0; self._cur = None; self._buf = []; self._in_title = False
        self._a_href = None; self._a_buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            if name in ("description", "og:title", "og:description", "keywords") and a.get("content"):
                self.meta[name] = a["content"].strip()
        elif tag in ("h1", "h2", "h3"):
            self._cur = tag; self._buf = []
        elif tag == "a":
            self._a_href = a.get("href"); self._a_buf = []
            cls = (a.get("class") or "").lower()
            if "btn" in cls or "button" in cls or "cta" in cls:
                self._a_is_btn = True
            else:
                self._a_is_btn = False
        elif tag == "button":
            self._cur = "button"; self._buf = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in ("h1", "h2", "h3") and self._cur == tag:
            txt = " ".join("".join(self._buf).split())
            if txt:
                self.headings.append((tag, txt))
            self._cur = None
        elif tag == "button" and self._cur == "button":
            txt = " ".join("".join(self._buf).split())
            if txt:
                self.buttons.append(txt)
            self._cur = None
        elif tag == "a":
            txt = " ".join("".join(self._a_buf).split())
            if self._a_href:
                self.links.append((txt, self._a_href))
            if txt and getattr(self, "_a_is_btn", False):
                self.buttons.append(txt)
            self._a_href = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        if self._cur:
            self._buf.append(data)
        if self._a_href is not None:
            self._a_buf.append(data)
        s = data.strip()
        if s and len(s) > 1:
            self.text.append(s)


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        charset = r.headers.get_content_charset() or "utf-8"
        return r.read().decode(charset, "replace"), r.geturl()


def audit_page(url):
    html, final = fetch(url)
    p = Extract(); p.feed(html)
    txt = " ".join(p.text)
    # lignes qui ressemblent à des tarifs
    prices = []
    for seg in re.split(r"(?<=[.!?])\s+|\n", txt):
        seg = seg.strip()
        if 2 < len(seg) < 160 and PRICE_RE.search(seg):
            prices.append(seg)
    return {"url": final, "title": " ".join(p.title.split()), "meta": p.meta,
            "headings": p.headings, "links": p.links, "buttons": p.buttons,
            "text": txt, "prices": prices[:40]}


def same_site(base, href):
    try:
        u = urlparse(urljoin(base, href))
        return u.scheme in ("http", "https") and u.netloc == urlparse(base).netloc
    except Exception:
        return False


def report(start, max_pages):
    base = start
    seen, queue, pages = set(), [start], []
    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        key = url.split("#")[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        try:
            d = audit_page(url)
        except Exception as e:
            pages.append({"url": url, "error": str(e)}); continue
        pages.append(d)
        for _, href in d["links"]:
            full = urljoin(d["url"], href).split("#")[0]
            if same_site(base, full) and full.rstrip("/") not in seen and len(seen) + len(queue) < max_pages * 3:
                # priorise les pages clés
                if any(k in full.lower() for k in ("tarif", "pric", "fonction", "feature", "faq", "produit", "app", "recrut")):
                    queue.insert(0, full)
                else:
                    queue.append(full)
    out = [f"# Audit de site — {urlparse(base).netloc}",
           f"_Généré le {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} · {len(pages)} page(s)_\n",
           "> Rapport brut à transmettre pour analyse UI/positionnement/tarifs.\n"]
    for d in pages:
        out.append("\n---\n")
        if d.get("error"):
            out.append(f"## ❌ {d['url']}\nErreur : {d['error']}\n"); continue
        out.append(f"## {d['title'] or '(sans titre)'}\n`{d['url']}`\n")
        if d["meta"]:
            out.append("**Meta :**")
            for k, v in d["meta"].items():
                out.append(f"- `{k}` : {v}")
            out.append("")
        if d["headings"]:
            out.append("**Structure (titres) :**")
            for tag, txt in d["headings"][:60]:
                out.append(("  " * (int(tag[1]) - 1)) + f"- {tag.upper()}: {txt}")
            out.append("")
        if d["buttons"]:
            uniq = list(dict.fromkeys(d["buttons"]))[:25]
            out.append("**Boutons / CTA :** " + " · ".join(f"`{b}`" for b in uniq) + "\n")
        if d["prices"]:
            out.append("**Lignes tarifaires détectées :**")
            for pr in d["prices"]:
                out.append(f"- {pr}")
            out.append("")
        nav = list(dict.fromkeys(t for t, _ in d["links"] if t and len(t) < 30))[:20]
        if nav:
            out.append("**Liens (libellés) :** " + " · ".join(nav) + "\n")
        body = d["text"]
        out.append("**Extrait de texte (début) :**\n")
        out.append("> " + (body[:1600].replace("\n", " ")) + ("…" if len(body) > 1600 else "") + "\n")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Audit senior d'un site -> rapport Markdown.")
    ap.add_argument("url")
    ap.add_argument("-o", "--out", default="")
    ap.add_argument("--max-pages", type=int, default=8)
    a = ap.parse_args()
    url = a.url if "://" in a.url else "https://" + a.url
    out = a.out or (urlparse(url).netloc.replace(".", "_") + "-audit.md")
    try:
        md = report(url, max(1, a.max_pages))
    except urllib.error.URLError as e:
        print(f"Impossible de joindre {url} : {e}", file=sys.stderr); sys.exit(1)
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"✅ Rapport écrit : {out}  ({len(md)} caractères)")
    print("→ Envoie ce fichier pour analyse.")


if __name__ == "__main__":
    main()
