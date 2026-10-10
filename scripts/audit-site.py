#!/usr/bin/env python3
"""audit-site.py — audit "senior" et GÉNÉRAL de n'importe quel site -> rapport Markdown (ou JSON).

Zéro dépendance (bibliothèque standard uniquement). Fonctionne sous Windows, macOS, Linux.
Crawle une page et des pages clés du même domaine, et extrait :
  - meta/OG/Twitter, langue, canonical, générateur (techno)
  - structure par SECTIONS (titre H1-H4 + texte qui suit)
  - boutons / CTA, liens (internes vs externes)
  - lignes tarifaires détectées (€, FCFA, $, /mois, /an…)
  - images (nombre + exemples d'alt), formulaires (champs)
  - volume de texte

Exemples :
  python audit-site.py https://kaizenjob.cv
  python audit-site.py exemple.com --max-pages 12 --format json -o rapport.json
  python audit-site.py https://site.com --same-domain 0   (autorise le suivi hors domaine)
"""
import sys, re, json, time, argparse, urllib.request, urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
PRICE_RE = re.compile(r"(\d[\d .,]*)\s*(€|£|\$|FCFA|XOF|USD|EUR|GBP)|\b(/\s?mois|/\s?an|par mois|par an|per month|per year|gratuit|free)\b", re.I)
KEY_HINTS = ("tarif", "pric", "plan", "fonction", "feature", "faq", "produit", "product",
             "app", "solution", "recrut", "about", "propos", "demo", "comment")


class Parser(HTMLParser):
    """Produit un flux d'évènements pour reconstruire des sections, + collecte liens/images/forms."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""; self.meta = {}; self.lang = ""; self.canonical = ""
        self.events = []        # ("h", level, text) | ("p", text)
        self.links = []; self.buttons = []; self.images = []; self.forms = []
        self._skip = 0; self._cap = None; self._buf = []; self._in_title = False
        self._a_href = None; self._a_buf = []; self._a_btn = False
        self._form = None

    def _flush_p(self):
        if self._buf:
            txt = " ".join("".join(self._buf).split())
            if len(txt) > 1:
                self.events.append(("p", txt))
            self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg", "template"):
            self._skip += 1; return
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"]
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            val = a.get("content", "").strip()
            if name and val and (name in ("description", "keywords", "generator", "author", "robots")
                                 or name.startswith("og:") or name.startswith("twitter:")):
                self.meta[name] = val
        elif tag == "link" and (a.get("rel") or "").lower() == "canonical":
            self.canonical = a.get("href", "")
        elif tag in ("h1", "h2", "h3", "h4"):
            self._flush_p(); self._cap = ("h", int(tag[1])); self._buf = []
        elif tag == "a":
            self._a_href = a.get("href"); self._a_buf = []
            cls = (a.get("class") or "").lower()
            self._a_btn = any(k in cls for k in ("btn", "button", "cta"))
        elif tag == "button":
            self._cap = ("btn", 0); self._buf = []
        elif tag == "img":
            self.images.append({"src": a.get("src", ""), "alt": (a.get("alt", "") or "").strip()})
        elif tag == "form":
            self._form = {"action": a.get("action", ""), "method": (a.get("method", "get")).lower(), "fields": []}
        elif tag in ("input", "textarea", "select") and self._form is not None:
            n = a.get("name") or a.get("placeholder") or a.get("type") or tag
            if n:
                self._form["fields"].append(n)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "template"):
            self._skip = max(0, self._skip - 1); return
        if tag == "title":
            self._in_title = False
        elif tag in ("h1", "h2", "h3", "h4") and self._cap and self._cap[0] == "h":
            txt = " ".join("".join(self._buf).split())
            if txt:
                self.events.append(("h", self._cap[1], txt))
            self._cap = None; self._buf = []
        elif tag == "button" and self._cap and self._cap[0] == "btn":
            txt = " ".join("".join(self._buf).split())
            if txt:
                self.buttons.append(txt)
            self._cap = None; self._buf = []
        elif tag == "a":
            txt = " ".join("".join(self._a_buf).split())
            if self._a_href:
                self.links.append((txt, self._a_href))
                if txt and self._a_btn:
                    self.buttons.append(txt)
            if txt:
                self._buf.append(" " + txt + " ")
            self._a_href = None
        elif tag in ("p", "li", "section", "div", "header", "footer") :
            self._flush_p()
        elif tag == "form" and self._form is not None:
            self.forms.append(self._form); self._form = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        if self._a_href is not None:
            self._a_buf.append(data); return
        if self._cap:
            self._buf.append(data)
        else:
            s = data.strip()
            if s:
                self._buf.append(data)


def fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr,en;q=0.8",
                                               "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ct = (r.headers.get_content_type() or "")
        if "html" not in ct and "xml" not in ct:
            raise ValueError(f"type non-HTML ({ct})")
        cs = r.headers.get_content_charset() or "utf-8"
        return r.read().decode(cs, "replace"), r.geturl()


def audit_page(url, timeout):
    html, final = fetch(url, timeout)
    p = Parser(); p.feed(html); p._flush_p()
    # sections : chaque titre + le texte qui suit jusqu'au prochain titre
    sections, cur = [], None
    full_text = []
    for ev in p.events:
        if ev[0] == "h":
            if cur:
                sections.append(cur)
            cur = {"level": ev[1], "title": ev[2], "text": []}
        else:
            full_text.append(ev[1])
            if cur:
                cur["text"].append(ev[1])
    if cur:
        sections.append(cur)
    body = " ".join(full_text)
    prices = []
    for seg in re.split(r"(?<=[.!?])\s+|[\n•|]| {3,}", body):
        seg = seg.strip()
        if 2 < len(seg) < 140 and PRICE_RE.search(seg):
            prices.append(seg)
    host = urlparse(final).netloc
    internal, external = [], []
    for txt, href in p.links:
        full = urljoin(final, href)
        (internal if urlparse(full).netloc == host else external).append((txt, full))
    return {
        "url": final, "lang": p.lang, "title": " ".join(p.title.split()),
        "canonical": p.canonical, "meta": p.meta,
        "sections": [{"level": s["level"], "title": s["title"],
                      "text": " ".join(" ".join(s["text"]).split())[:1400]} for s in sections],
        "buttons": list(dict.fromkeys(p.buttons))[:30],
        "prices": list(dict.fromkeys(prices))[:50],
        "images_count": len(p.images), "images_alt": [i["alt"] for i in p.images if i["alt"]][:15],
        "forms": p.forms[:8],
        "links_internal": len(internal), "links_external": len(external),
        "nav_labels": list(dict.fromkeys(t for t, _ in p.links if t and len(t) < 28))[:24],
        "word_count": len(body.split()),
        "_internal_urls": [u for _, u in internal],
    }


def crawl(start, max_pages, same_domain, delay, timeout):
    base = urlparse(start).netloc
    seen, queue, pages = set(), [start], []
    while queue and len(pages) < max_pages:
        url = queue.pop(0).split("#")[0]
        key = url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        try:
            d = audit_page(url, timeout)
        except Exception as e:
            pages.append({"url": url, "error": str(e)}); continue
        pages.append(d)
        if delay:
            time.sleep(delay)
        for u in d.get("_internal_urls", []):
            u2 = u.split("#")[0]
            if u2.rstrip("/") in seen:
                continue
            if same_domain and urlparse(u2).netloc != base:
                continue
            (queue.insert(0, u2) if any(k in u2.lower() for k in KEY_HINTS) else queue.append(u2))
    for d in pages:
        d.pop("_internal_urls", None)
    return pages


def to_md(base, pages):
    out = [f"# Audit de site — {urlparse(base).netloc}",
           f"_Généré le {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} · {len(pages)} page(s) · outil: audit-site.py_\n",
           "> Rapport brut à transmettre pour analyse UI / positionnement / tarifs.\n"]
    for d in pages:
        out.append("\n---\n")
        if d.get("error"):
            out.append(f"## ❌ {d['url']}\n{d['error']}\n"); continue
        out.append(f"## {d['title'] or '(sans titre)'}")
        out.append(f"`{d['url']}` · lang=`{d.get('lang') or '?'}` · {d['word_count']} mots · "
                   f"{d['links_internal']} liens internes / {d['links_external']} externes · {d['images_count']} images\n")
        if d["meta"]:
            out.append("**Meta / OG :**")
            for k, v in list(d["meta"].items())[:12]:
                out.append(f"- `{k}` : {v}")
            out.append("")
        if d["nav_labels"]:
            out.append("**Navigation / liens :** " + " · ".join(d["nav_labels"]) + "\n")
        if d["buttons"]:
            out.append("**Boutons / CTA :** " + " · ".join(f"`{b}`" for b in d["buttons"]) + "\n")
        if d["prices"]:
            out.append("**Tarifs détectés :**")
            out += [f"- {p}" for p in d["prices"]]
            out.append("")
        if d["forms"]:
            out.append("**Formulaires :**")
            for f in d["forms"]:
                out.append(f"- {f['method'].upper()} {f['action'] or '(même page)'} — champs: {', '.join(f['fields'][:12]) or '—'}")
            out.append("")
        if d["images_alt"]:
            out.append("**Images (alt) :** " + " · ".join(d["images_alt"]) + "\n")
        if d["sections"]:
            out.append("**Contenu par section :**\n")
            for s in d["sections"][:40]:
                out.append(("#" * min(6, s["level"] + 2)) + " " + s["title"])
                if s["text"]:
                    out.append("> " + s["text"] + "\n")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Audit senior et général d'un site -> Markdown/JSON.")
    ap.add_argument("url")
    ap.add_argument("-o", "--out", default="")
    ap.add_argument("--max-pages", type=int, default=10)
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--same-domain", type=int, default=1, help="1=rester sur le domaine (défaut), 0=suivre tout")
    ap.add_argument("--delay", type=float, default=0.4, help="pause entre pages (s), politesse")
    ap.add_argument("--timeout", type=float, default=25)
    a = ap.parse_args()
    url = a.url if "://" in a.url else "https://" + a.url
    try:
        pages = crawl(url, max(1, a.max_pages), bool(a.same_domain), a.delay, a.timeout)
    except urllib.error.URLError as e:
        print(f"Impossible de joindre {url} : {e}", file=sys.stderr); sys.exit(1)
    ext = "json" if a.format == "json" else "md"
    out = a.out or (urlparse(url).netloc.replace(".", "_") + f"-audit.{ext}")
    data = json.dumps(pages, ensure_ascii=False, indent=2) if a.format == "json" else to_md(url, pages)
    with open(out, "w", encoding="utf-8") as f:
        f.write(data)
    print(f"OK -> {out}  ({len(data)} caracteres, {len(pages)} page(s))")
    print("Envoie ce fichier (ou copie-colle son contenu) pour analyse.")


if __name__ == "__main__":
    main()
