"""Supports imprimés NexMove : QR codes (vectoriels) + remplissage des gabarits depuis contact.json.

Une seule source pour les coordonnées : changer le numéro du bot dans brand/contact.json,
puis relancer brand/tools/render.sh. Produit templates/affiche-a4.html et templates/carte-visite.html.
"""
import json
import pathlib
import qrcode
import qrcode.image.svg

B = pathlib.Path(__file__).resolve().parent.parent          # brand/
c = json.loads((B / "contact.json").read_text(encoding="utf-8"))

wa = c["whatsapp"]
wa_aff = "+{} {}".format(wa[:3], " ".join(wa[3 + i:5 + i] for i in range(0, len(wa) - 3, 2)))
links = {
    "telegram": f"https://t.me/{c['telegram']}",
    "whatsapp": f"https://wa.me/{wa}",
    "site": f"https://{c['site']}",
}


def qr_svg(url: str, out: pathlib.Path) -> None:
    # Correction M (15 %) + marge de 4 modules (quiet zone) : lisible imprimé à partir de 2 cm.
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, box_size=10)
    q.add_data(url)
    q.make(fit=True)
    img = q.make_image(image_factory=qrcode.image.svg.SvgPathImage, fill_color="#0B1326", back_color="#F4F1EA")
    out.write_bytes(img.to_string())


for k in ("telegram", "whatsapp", "site"):
    qr_svg(links[k], B / "assets" / f"qr-{k}.svg")

vals = {"{{TELEGRAM}}": "@" + c["telegram"], "{{WHATSAPP}}": wa_aff, "{{SITE}}": c["site"]}
for tpl in ("affiche-a4", "carte-visite"):
    s = (B / "templates" / f"{tpl}.html.tpl").read_text(encoding="utf-8")
    for k, v in vals.items():
        s = s.replace(k, v)
    (B / "templates" / f"{tpl}.html").write_text(s, encoding="utf-8")
print("QR + gabarits imprimés :", vals)
