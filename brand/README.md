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
Le symbole officiel (N maison + flèche ambre) va dans **`assets/mark.png`** (fond transparent).
Sans ce fichier, les gabarits affichent un emplacement « MARQUE N » au lieu d'un faux logo.

## Générer le set
```bash
brand/tools/render.sh
```
Produit dans `brand/out/` : `HERO_v2.png` (1080×1080), `og.png` (1200×630, copié dans
`web/og.png` si le logo est présent) et les posts `POST_0x_*.png` (1080×1350, format 4:5).

Nouveau post : ajouter une ligne `post …` dans `tools/render.sh`
(`*mot*` = accent ambre, `|` = saut de ligne dans le titre).
