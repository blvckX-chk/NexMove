"""Extraction fidèle de la marque NexMove depuis l'affiche : masques couleur (blanc / ambre),
PNG transparent + SVG par tracé de contours (pas de redessin)."""
import sys, numpy as np, cv2
from PIL import Image
src, out_png, out_svg = sys.argv[1], sys.argv[2], sys.argv[3]
S = 4                                                     # sur-échantillonnage pour des bords lisses
im = Image.open(src).convert("RGB")
im = im.resize((im.width * S, im.height * S), Image.LANCZOS)
a = np.asarray(im).astype(np.float32)
R, G, B = a[..., 0], a[..., 1], a[..., 2]
amber = (R - B > 80) & (R > 120) & (G > 90)
a_amber = np.clip((R - 90) / 110, 0, 1) * amber
a_white = np.clip((np.minimum(R, G) - 80) / 140, 0, 1) * ~amber
AMBRE, BLANC = (224, 160, 32), (255, 255, 255)
h, w = R.shape
rgba = np.zeros((h, w, 4), np.uint8)
rgba[..., :3] = BLANC
rgba[amber, :3] = AMBRE
alpha = np.maximum(a_white, a_amber)
rgba[..., 3] = (alpha * 255).astype(np.uint8)
ys, xs = np.where(alpha > 0.5)
pad = 8 * S
y0, y1, x0, x1 = max(ys.min() - pad, 0), min(ys.max() + pad, h), max(xs.min() - pad, 0), min(xs.max() + pad, w)
Image.fromarray(rgba[y0:y1, x0:x1], "RGBA").save(out_png)
print("png", (x1 - x0, y1 - y0))

def paths(mask, eps):
    m = (mask[y0:y1, x0:x1] > 0.5).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    d = []
    for c in cnts:
        if cv2.contourArea(c) < 400 * S:
            continue
        p = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
        d.append("M" + " L".join(f"{x:.0f},{y:.0f}" for x, y in p) + " Z")
    return " ".join(d)
W, H = x1 - x0, y1 - y0
d_w = paths(a_white, 1.6 * S)
d_a = paths(a_amber, 1.6 * S)
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W//S}" height="{H//S}">'
       f'<title>NexMove — symbole</title>'
       f'<path fill="#FFFFFF" fill-rule="evenodd" d="{d_w}"/>'
       f'<path fill="#E0A020" fill-rule="evenodd" d="{d_a}"/></svg>')
open(out_svg, "w").write(svg)
print("svg points:", d_w.count("L") + d_a.count("L"))
