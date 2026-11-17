"""Icônes de la vitrine à partir de la marque officielle (brand/assets/mark.svg + out/icon-1000.png)."""
import re, pathlib
from PIL import Image
B = pathlib.Path(__file__).resolve().parent.parent           # brand/
W = B.parent / "web"
svg = (B / "assets/mark.svg").read_text()
vb = re.search(r'viewBox="([^"]+)"', svg).group(1)
paths = "".join(re.findall(r"<path[^>]*/>", svg))
(W / "favicon.svg").write_text((B / "templates/icon.svg.tpl").read_text().replace("__VB__", vb).replace("__PATHS__", paths))
big = Image.open(B / "out/icon-1000.png").convert("RGBA")
big.save(W / "logo-nexmove.png")
big.resize((180, 180), Image.LANCZOS).save(W / "apple-touch-icon.png")
big.resize((32, 32), Image.LANCZOS).save(W / "favicon.png")
big.resize((48, 48), Image.LANCZOS).save(W / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
print("icônes : favicon.svg/png/ico, apple-touch-icon.png, logo-nexmove.png")
