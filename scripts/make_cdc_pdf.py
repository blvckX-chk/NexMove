#!/usr/bin/env python3
"""Génère le Cahier des charges NexMove en PDF, branding blvkunlimited, depuis le .md."""
import re, sys, html, os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                Preformatted, HRFlowable, PageBreak, KeepTogether)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_ROOT, "docs", "CAHIER-DES-CHARGES.md")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_ROOT, "docs", "NexMove-Cahier-des-charges.pdf")

# ---- Palette blvkunlimited : noir profond + accent or ----
NOIR   = HexColor("#0E0E10")
NOIR2  = HexColor("#1A1A1E")
OR     = HexColor("#C9A227")
OR_CL  = HexColor("#E7CE7A")
GRIS   = HexColor("#6B7280")
GRIS_L = HexColor("#EDEDF0")
BLANC  = HexColor("#FFFFFF")
ENCRE  = HexColor("#17171B")

TITRE_DOC = "Cahier des charges"
PRODUIT   = "NexMove"
SOUS      = "Assistant IA de mobilité & d'orientation"
VERSION   = "v2.39.0"
DATE      = "9 septembre 2026"
MARQUE    = "blvkunlimited"

styles = {
    "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=19,
                         textColor=NOIR, spaceBefore=16, spaceAfter=2),
    "h1n": ParagraphStyle("h1n", fontName="Helvetica-Bold", fontSize=9, leading=11,
                          textColor=OR, spaceBefore=16, spaceAfter=1),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15,
                         textColor=ENCRE, spaceBefore=10, spaceAfter=3),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=14,
                          textColor=ENCRE, spaceAfter=4),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9.5, leading=13.5,
                            textColor=ENCRE, leftIndent=14, bulletIndent=4, spaceAfter=2),
    "cap": ParagraphStyle("cap", fontName="Helvetica-Oblique", fontSize=8.5, leading=12,
                         textColor=GRIS, spaceAfter=4),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.7, leading=11.5, textColor=ENCRE),
    "cellh": ParagraphStyle("cellh", fontName="Helvetica-Bold", fontSize=8.7, leading=11.5, textColor=BLANC),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=6.4, leading=7.6, textColor=HexColor("#E7CE7A")),
}


_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF"
    "\U0001F1E6-\U0001F1FF\U0000FE00-\U0000FE0F\U000020E3\U000025A0-\U000025FF]",
    flags=re.UNICODE)


def _deemoji(text: str) -> str:
    text = text.replace("👍", "+").replace("👎", "-")
    text = _EMOJI.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def inline(text: str) -> str:
    """Markdown inline -> balisage reportlab (gras, code, italique), en préservant les _ du code."""
    text = _deemoji(text)
    codes = []
    def stash(m):
        codes.append(m.group(1))
        return f"\x00{len(codes)-1}\x00"
    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w/])_([^_]+?)_(?![\w/])", r"<i>\1</i>", text)
    def restore(m):
        return ('<font face="Courier" size="8" color="#8A6D1B">'
                + html.escape(codes[int(m.group(1))], quote=False) + "</font>")
    text = re.sub(r"\x00(\d+)\x00", restore, text)
    return text


def make_table(rows):
    header, body = rows[0], rows[1:]
    data = [[Paragraph(inline(c), styles["cellh"]) for c in header]]
    for r in body:
        data.append([Paragraph(inline(c), styles["cell"]) for c in r])
    ncol = len(header)
    avail = A4[0] - 3.6 * cm
    # 1re colonne un peu plus large
    w0 = avail * (0.34 if ncol <= 2 else 0.22)
    rest = (avail - w0) / max(ncol - 1, 1)
    widths = [w0] + [rest] * (ncol - 1)
    t = Table(data, colWidths=widths, repeatRows=1)
    ts = [("BACKGROUND", (0, 0), (-1, 0), NOIR),
          ("TEXTCOLOR", (0, 0), (-1, 0), BLANC),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, HexColor("#D9D9DE")),
          ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#CFCFD6"))]
    for i in range(1, len(data)):
        if i % 2 == 0:
            ts.append(("BACKGROUND", (0, i), (-1, i), HexColor("#F7F5EF")))
    t.setStyle(TableStyle(ts))
    return t


def parse(md: str):
    story, i = [], 0
    lines = md.split("\n")
    buf = []

    def flush():
        if not buf:
            return
        text = " ".join(x.strip() for x in buf).strip()
        buf.clear()
        if not text:
            return
        if text.startswith("_") and text.endswith("_") and len(text) > 2:
            story.append(Paragraph(inline(text[1:-1].strip()), styles["cap"]))
        else:
            story.append(Paragraph(inline(text), styles["body"]))

    while i < len(lines):
        ln = lines[i].rstrip("\n")
        s = ln.strip()
        # ignorer le titre H1 (déjà en couverture)
        if s.startswith("# "):
            flush(); i += 1
            continue
        if s.startswith("```"):
            flush()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i]); i += 1
            i += 1
            code = "\n".join(block)
            tbl = Table([[Preformatted(code, styles["code"])]], colWidths=[A4[0] - 3.6 * cm])
            tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NOIR),
                                     ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                     ("BOX", (0, 0), (-1, -1), 0.5, OR)]))
            story.append(Spacer(1, 4)); story.append(tbl); story.append(Spacer(1, 6))
            continue
        if s.startswith("## "):
            flush()
            num_title = s[3:].strip()
            m = re.match(r"^(\d+)\.\s*(.*)$", num_title)
            if m:
                story.append(Paragraph(f"SECTION {m.group(1)}", styles["h1n"]))
                story.append(Paragraph(inline(m.group(2)), styles["h1"]))
            else:
                story.append(Paragraph(inline(num_title), styles["h1"]))
            story.append(HRFlowable(width="100%", thickness=1.2, color=OR, spaceBefore=3, spaceAfter=7))
            i += 1
            continue
        if s.startswith("### "):
            flush()
            story.append(Paragraph(inline(s[4:].strip()), styles["h2"]))
            i += 1
            continue
        if s.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not re.match(r"^-{2,}$", cells[0].replace(":", "").replace(" ", "") or "x"):
                    if not all(re.match(r"^:?-{2,}:?$", c.strip()) for c in cells):
                        rows.append(cells)
                i += 1
            if rows:
                story.append(Spacer(1, 2)); story.append(make_table(rows)); story.append(Spacer(1, 6))
            continue
        if s.startswith("- "):
            flush()
            story.append(Paragraph(inline(s[2:].strip()), styles["bullet"], bulletText="•"))
            i += 1
            continue
        if s == "" or s == "---":
            flush()
            i += 1
            continue
        buf.append(s)
        i += 1
    flush()
    return story


def cover(canv, doc):
    canv.saveState()
    W, H = A4
    canv.setFillColor(NOIR); canv.rect(0, 0, W, H, fill=1, stroke=0)
    canv.setFillColor(NOIR2); canv.rect(0, H - 5.2 * cm, W, 5.2 * cm, fill=1, stroke=0)
    canv.setStrokeColor(OR); canv.setLineWidth(2)
    canv.line(2.2 * cm, H - 3.05 * cm, W - 2.2 * cm, H - 3.05 * cm)
    canv.setFillColor(OR); canv.setFont("Helvetica-Bold", 22)
    canv.drawString(2.2 * cm, H - 2.7 * cm, "blvk")
    tw = canv.stringWidth("blvk", "Helvetica-Bold", 22)
    canv.setFillColor(BLANC); canv.drawString(2.2 * cm + tw, H - 2.7 * cm, "unlimited")
    canv.setFillColor(GRIS); canv.setFont("Helvetica", 9)
    canv.drawRightString(W - 2.2 * cm, H - 2.65 * cm, "STUDIO PRODUIT & IA")
    # Bloc titre centré
    canv.setFillColor(OR); canv.setFont("Helvetica-Bold", 12)
    canv.drawCentredString(W / 2, H / 2 + 2.7 * cm, "PROJET " + PRODUIT.upper())
    canv.setFillColor(BLANC); canv.setFont("Helvetica-Bold", 40)
    canv.drawCentredString(W / 2, H / 2 + 1.1 * cm, TITRE_DOC)
    canv.setStrokeColor(OR); canv.setLineWidth(1.4)
    canv.line(W / 2 - 3 * cm, H / 2 + 0.3 * cm, W / 2 + 3 * cm, H / 2 + 0.3 * cm)
    canv.setFillColor(OR_CL); canv.setFont("Helvetica-Oblique", 12.5)
    canv.drawCentredString(W / 2, H / 2 - 0.6 * cm, SOUS)
    canv.setFillColor(GRIS); canv.setFont("Helvetica", 10.5)
    canv.drawCentredString(W / 2, H / 2 - 1.7 * cm,
                           "Études · Emploi · Bourses · Fellowships — local & international")
    # Bas de couverture
    canv.setStrokeColor(HexColor("#33333A")); canv.setLineWidth(0.8)
    canv.line(2.2 * cm, 3.4 * cm, W - 2.2 * cm, 3.4 * cm)
    canv.setFillColor(BLANC); canv.setFont("Helvetica-Bold", 10)
    canv.drawString(2.2 * cm, 2.75 * cm, f"Version  {VERSION}")
    canv.drawString(2.2 * cm, 2.25 * cm, f"Date       {DATE}")
    canv.setFillColor(GRIS); canv.setFont("Helvetica", 9)
    canv.drawRightString(W - 2.2 * cm, 2.75 * cm, "Document interne")
    canv.drawRightString(W - 2.2 * cm, 2.25 * cm, "Confidentiel — blvkunlimited")
    canv.restoreState()


def later(canv, doc):
    canv.saveState()
    W, H = A4
    canv.setFillColor(NOIR); canv.setFont("Helvetica-Bold", 8.5)
    canv.drawString(2 * cm, H - 1.15 * cm, "blvk")
    tw = canv.stringWidth("blvk", "Helvetica-Bold", 8.5)
    canv.setFillColor(GRIS); canv.drawString(2 * cm + tw, H - 1.15 * cm, "unlimited")
    canv.drawRightString(W - 2 * cm, H - 1.15 * cm, f"{PRODUIT} — {TITRE_DOC}")
    canv.setStrokeColor(HexColor("#E2E0D8")); canv.setLineWidth(0.6)
    canv.line(2 * cm, H - 1.35 * cm, W - 2 * cm, H - 1.35 * cm)
    canv.line(2 * cm, 1.35 * cm, W - 2 * cm, 1.35 * cm)
    canv.setFillColor(GRIS); canv.setFont("Helvetica", 8)
    canv.drawString(2 * cm, 1.0 * cm, f"{MARQUE} · {VERSION}")
    canv.drawRightString(W - 2 * cm, 1.0 * cm, f"Page {doc.page - 1}")
    canv.restoreState()


md = open(SRC, encoding="utf-8").read()
story = [PageBreak()] + parse(md)
doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                        topMargin=1.9 * cm, bottomMargin=1.7 * cm,
                        title="NexMove — Cahier des charges", author="blvkunlimited")
doc.build(story, onFirstPage=cover, onLaterPages=later)
print("OK ->", OUT)
