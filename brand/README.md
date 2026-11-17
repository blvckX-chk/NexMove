# Identité visuelle NexMove

Source de vérité versionnée de la marque (gabarits + outil de rendu). Les fichiers produits
vont dans `out/` (non versionné) ; l'image de partage de la vitrine est copiée dans `web/og.png`.

## Système « Mobilité éditoriale »

| Élément | Règle |
|---|---|
| Titres | **Big Shoulders** 800, condensé, fer à gauche, interlignage serré |
| Texte | **Instrument Sans** 400 / 700 |
| Labels, URL, kickers, folios | **Geist Mono** 700, capitales espacées |
| Fond | un seul : nuit `#0B1326` (+ texture losanges adinkra à 6 %) |
| Encre | crème `#F4F1EA` · secondaire `#9FAAC6` |
| Accent | **un seul accent saturé : ambre `#E0A020`**, avec parcimonie (1 mot, 1 filet, 1 ruban) |
| Bleu | `#1B52B0` / `#2f6ad6` en secondaire (le « Move » du wordmark) |
| Signature | wordmark texte « Nex**Move** » en haut à gauche + filet ambre + folio mono ; marque N en ancrage |

### Ce qu'on s'interdit (réflexes « IA »)
- lueurs, halos, orbes décoratives derrière le logo ;
- dégradés de fond, semis de points décoratifs ;
- logo en double (wordmark texte **ou** lockup image, jamais les deux côte à côte) ;
- chiffres, témoignages ou logos clients inventés ;
- redessiner le logo : on utilise **toujours le fichier officiel**.

## Logo
- `assets/mark.png` : symbole (N maison + flèche ambre) détouré, fond transparent.
- `assets/mark.svg` : le même en **vectoriel**, obtenu par **tracé des contours** de l'affiche (pas un redessin).
- `assets/source/affiche-base.png` : l'affiche d'origine dont il est extrait.

⚠️ **Version provisoire** extraite d'une capture de l'affiche (Canva) : fidèle et nette jusqu'à ~1500 px,
mais deux angles du SVG sont très légèrement biseautés. Dès que le fichier source final existe, le
déposer ici (mêmes noms) puis relancer `brand/tools/render.sh` : tout le set et la vitrine se mettent à jour.
Réextraction depuis une nouvelle affiche : `python3 brand/tools/extract_mark.py <recadrage.png> mark.png mark.svg`.

Sans `mark.png`, les gabarits affichent un emplacement « MARQUE N » au lieu d'un faux logo.
**Règle** : le logo n'est jamais coupé par le bord, jamais redessiné, jamais accompagné d'une lueur.

## Générer le set
```bash
brand/tools/render.sh
```
Produit dans `brand/out/` : `HERO_v2.png` (1080×1080), `og.png` (1200×630) et les posts `POST_0x_*.png`
(1080×1350, format 4:5). Avec le logo présent, met aussi à jour la vitrine : `web/og.png`, `favicon.svg/.png/.ico`,
`apple-touch-icon.png` et `logo-nexmove.png`.

Nouveau post : ajouter une ligne `post …` dans `tools/render.sh`
(`*mot*` = accent ambre, `|` = saut de ligne dans le titre).

## Supports imprimés
| Fichier | Format | Usage |
|---|---|---|
| `exports/print/affiche-a4.pdf` | A4 + 3 mm de fond perdu (216×303 mm) | affiche / flyer de découverte, 2 QR (WhatsApp, Telegram) |
| `exports/print/carte-visite.pdf` | 85×55 mm + 3 mm de fond perdu, recto-verso | carte produit, QR WhatsApp |

PDF vectoriels (texte et QR nets à toute taille), polices incorporées, en RVB : demander à
l'imprimeur s'il accepte le RVB, sinon conversion CMJN avec son profil (vérifier le bleu).
Le trait de coupe est à 3 mm du bord du fichier ; tout le texte est dans la zone de sécurité.
**Coordonnées** (numéro du bot, site) : une seule source, `contact.json`, puis `tools/render.sh`.
Ambre sur fond clair : `#B57A00` (variante foncée de l'ambre, pour rester lisible).

## Canva (modifiable)
`exports/canva/*.pdf` : HERO, posts et og en PDF à texte vectoriel. Dans Canva : *Créer un design
→ Importer un fichier* → choisir le PDF : il devient un design dont les textes sont modifiables.
