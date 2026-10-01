# NexMove — Identité de marque & kit publicitaire (v1)

> Complète `LANCEMENT-PRODUCTION.md` (§3 à §7). Décisions validées : baseline, direction de palette,
> personas de la première vague. Éléments marqués **[proposition]** = point de départ à faire valider
> par le designer ou à tester.

---

## 1. Identité verrouillée

| Élément | Décision |
|---|---|
| **Nom** | NexMove (*Nex* = next, *Move* = mobilité / prochain pas) |
| **Éditeur** | « Un produit blvckUnlimited » — mention discrète, jamais dans le logo |
| **Baseline (validée)** | **Études, emploi, ici ou ailleurs : l'assistant pour ton prochain move.** |
| **Ligne descriptive [proposition]** | Assistant IA sur Telegram et WhatsApp — CV, opportunités, dossiers, entretiens. |
| **Promesse** | Un conseiller d'emploi et de mobilité par IA, en français, abordable, dans la messagerie. |
| **Ton** | Tutoiement, chaleureux, direct, concret, honnête ; fier d'être africain et tourné vers le monde. |

Règle d'usage : la baseline complète sert de signature (bannières, vitrine, bio). En publicité courte, on
utilise les accroches par persona (§4) et la baseline seulement en carte finale.

## 2. Palette (bleu électrique) **[proposition]**

| Rôle | HEX | Usage |
|---|---|---|
| Bleu principal | `#2F5BFF` | Logo, boutons, liens, fonds d'accroche |
| Bleu nuit | `#0B1B4D` | Titres, fonds sombres, cartes finales |
| Ambre (accent) | `#FFB020` | CTA « Démarrer », mise en valeur d'un mot par visuel |
| Fond clair | `#F7F9FC` | Fonds de pages et de visuels |
| Texte | `#0F172A` | Corps de texte |

Contrastes WCAG calculés (ratio de luminance relative) :

- Blanc sur `#2F5BFF` : **5,17:1** (AA texte normal ≥ 4,5:1 ✅)
- Blanc sur `#0B1B4D` : **16,43:1** ✅
- `#0F172A` sur ambre `#FFB020` : **9,76:1** ✅ — *jamais de blanc sur ambre (1,83:1 ❌)*
- `#2F5BFF` sur `#F7F9FC` : **4,90:1** ✅ (limite basse : pas pour du très petit texte)

Règle : 1 couleur dominante (bleu) + 1 accent (ambre) par visuel. Pas de dégradé indispensable au logo.

## 3. Typographie & style visuel **[proposition]**

- Titres : sans-serif géométrique (Inter ou Poppins, licences libres). Corps : police système.
- Visuels : photos ou illustrations de jeunes réels / contextes ouest-africains crédibles ; éviter les
  visuels de stock génériques et le jargon RH occidental.
- Captures d'écran du bot en mode clair, cadrées sur une seule fonctionnalité par visuel.

## 4. Logo — brief pour le designer

**Contraintes :** lisible à 40 px ; version 1 couleur ; fonctionne en cercle (Telegram/WhatsApp recadrent
l'avatar en rond → garder le symbole dans la zone centrale, ~80 % du diamètre) ; favicon 32/180/512 px.

**Trois pistes à faire dessiner puis comparer :**

- **A. « N » à flèche intégrée** : le trait du N se prolonge en flèche montante (progression).
- **B. « M » en chevrons** : deux chevrons qui forment un M (mouvement, direction).
- **C. Bulle de messagerie à flèche** : la queue de la bulle devient une flèche (canal = messagerie,
  promesse = avancer). Plus distinctive, mais plus détaillée à petite taille : à tester en favicon.

**Livrables :** symbole seul · logo horizontal (symbole + « NexMove ») · version monochrome (bleu nuit et
blanc) · version sur fond bleu · avatar rond bot Telegram/WhatsApp · favicon.

## 5. Kit publicitaire — vague 1 (2 personas)

### Persona 1 — Étudiant visant Campus France

- **Accroche (hook 3 s) :** « Tu veux étudier en France mais tu ne sais pas par où commencer ? »
- **Bénéfice :** dossier guidé étape par étape, évaluation de tes chances (`/chances`), guide avec
  captures (`/guide`), simulation d'entretien (`/simulation`).
- **CTA :** « Démarre gratuitement sur Telegram ».

### Persona 2 — Jeune diplômé en recherche d'emploi

- **Accroche :** « Ton CV ne passe pas ? Envoie-le, on te dit pourquoi. »
- **Bénéfice :** analyse de CV (PDF/Word/photo), opportunités locales et internationales (`/veille`),
  score de compatibilité par compétence (`/compatibilite`), même sans CV (`/creercv`), même à la voix.
- **CTA :** « Démarre gratuitement sur Telegram ».

### Formats

- Vidéo verticale 9:16, 30–60 s : hook (0–3 s) → problème → démo écran du bot → résultat → CTA + baseline
  en carte finale. Sous-titres obligatoires (lecture sans son).
- Visuels statiques : carré 1:1 et vertical 4:5 / 9:16 (5 visuels, cf. LANCEMENT-PRODUCTION §7).

### Règles de conformité des messages

- **Ne pas promettre** visa, admission, bourse ou emploi : NexMove accompagne, la décision revient aux
  organismes et employeurs. Formulations : « augmente tes chances », « prépare ton dossier ».
- **« Admissible ou remboursé »** : ne pas l'utiliser en publicité tant que les conditions précises
  (ce qui déclenche le remboursement) ne sont pas rédigées et publiées dans les CGU.
- **Témoignages** : uniquement réels, avec accord écrit ; pas de faux avant/après.
- **Logos / marques tierces** (Campus France, IRCC, ambassades) : ne pas les utiliser comme si NexMove
  était affilié ; mentionner « NexMove n'est pas affilié à… » sur la vitrine.
- **Mention IA** : dire clairement qu'il s'agit d'un assistant IA.

## 6. Mesure des angles — liens `?start=` (Telegram)

Principe : chaque lien de pub ouvre le bot avec un paramètre `start`. Le bot le reçoit dans `/start <code>`
et il suffit de l'enregistrer une fois, à la création du profil.

- Format : `https://t.me/<BOT_USERNAME>?start=<code>`
- Contraintes Telegram du paramètre : **1 à 64 caractères, uniquement `A-Z a-z 0-9 _ -`**.

**Convention de codes :** `src_<persona>_<canal>`

| Segment | Valeurs |
|---|---|
| persona | `etu` (étudiant), `dip` (diplômé) |
| canal | `tt` TikTok · `ig` Instagram · `yt` YouTube · `wa` statuts/groupes WhatsApp · `eco` école · `amb` ambassadeur |

Exemples : `src_etu_tt`, `src_dip_wa`, `src_etu_amb`.
Pour un ambassadeur précis : `src_etu_amb_<prenom>` (reste très en dessous de 64 caractères).

**Côté bot (à faire faire à Claude Code) :**
1. Dans le handler `/start`, si le paramètre commence par `src_`, l'écrire dans un champ `source` du profil,
   **uniquement s'il est vide** (on garde la première source).
2. **À vérifier dans le code :** le format déjà utilisé par le parrainage, pour que les deux codes ne
   entrent pas en collision (le préfixe `src_` sert à les distinguer).
3. Vue simple : nombre d'utilisateurs par `source`, taux d'onboarding complété par `source`,
   conversion free → payant par `source`.

**Sans coût de développement, en complément :** demander en fin d'onboarding « Comment nous as-tu connus ? »
(boutons). Déclaratif, donc moins fiable que le lien, mais utile pour les canaux où l'on ne contrôle pas le
lien (bouche-à-oreille).

Côté WhatsApp (plus tard) : les liens `wa.me/<numéro>?text=<message prérempli>` jouent le même rôle, avec un
message prérempli différent par persona.
