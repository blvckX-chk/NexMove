# Sécurité NexMove — ce qui est public, ce qui ne l'est pas

Le dépôt GitHub est **public**. Tout ce qui y est écrit doit être considéré comme connu de tous.

## Ce qui est volontairement public
| Élément | Risque |
|---|---|
| Vitrine `nexmove.blvckunlimited.space` (HTML statique) | aucun : pas de donnée utilisateur, pas de clé |
| Domaine de l'API `api-nexmove.blvckunlimited.space` | aucun seul : toutes les routes de données exigent une clé |
| `/health`, `/` de l'API | version et « WhatsApp configuré oui/non », rien d'autre |
| `admin.html` | une page vide sans la clé ; aucune clé ni donnée dans le fichier |
| Numéros du bot et de l'équipe, e-mail de contact | publiés exprès |

## Ce qui doit rester secret (jamais dans le dépôt)
`.env` de l'API et de l'infra : `FORGE_NEX_API_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`,
`WHATSAPP_TOKEN`, `MESSENGER_TOKEN`, `META_APP_SECRET`, clés des fournisseurs IA.
Un historique de 267 commits a été analysé (motifs de jetons Telegram, Meta, Google, OpenAI, Groq, etc.) : aucun secret réel trouvé.

## La clé API (`FORGE_NEX_API_KEY`)
Elle protège les sessions utilisateurs (`/api/session/…`), les statistiques, les contacts et le **broadcast**.
- L'ancienne valeur d'exemple `forge_nex_secret_2026` a été publiée dans le dépôt (docs, `.env.example`,
  workflows n8n). Depuis la v3.95, **l'API la refuse** (réponse 503) même si elle est configurée.
- Sans clé, l'API refuse aussi `/api/*` dès qu'un canal (Telegram, WhatsApp, Messenger) est configuré.
- Au démarrage, l'admin reçoit une alerte si la clé est absente, publique ou trop courte.

### Changer la clé (sur le serveur)
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"     # génère une clé
# la coller dans le .env de l'API : FORGE_NEX_API_KEY=...
# si n8n tourne encore : même valeur dans le .env de l'infra : FORGE_NEX_KEY=...
./scripts/deploy.sh
```
Puis, dans le panneau admin, saisir la nouvelle clé.

**Vérifier** que l'ancienne ne marche plus (doit afficher `503` ou `401`, jamais `200`) :
```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Forge-Nex-Key: forge_nex_secret_2026" \
  https://api-nexmove.blvckunlimited.space/api/admin/stats
```

## Dépendances
Les versions sont **figées** (reproductibilité) et **auditées à chaque PR** par le job CI
`audit` (`pip-audit`). Une faille connue dans une dépendance de production fait échouer la CI.
Dependabot propose une mise à jour groupée chaque semaine.

> Pourquoi ça compte ici : `Pillow` lit les **photos de CV envoyées par des inconnus**,
> `starlette` traite **chaque requête HTTP**, `python-multipart` analyse les **fichiers
> téléversés**. Au 22/11/2026, ces trois paquets cumulaient **68 failles connues** ; ils ont
> été mis à jour (Pillow 11→13, starlette 0.41→1.10, python-multipart 0.0.20→0.0.34).

Vérifier à la main :
```bash
pip install pip-audit && pip-audit -r api/requirements.txt
```

## Autres protections en place
- Webhooks Meta signés (`META_APP_SECRET`), webhook Telegram authentifié (`TELEGRAM_WEBHOOK_SECRET`).
- Droits admin désactivés sur WhatsApp/Messenger tant que `META_APP_SECRET` manque.
- Documentation interactive de l'API (`/docs`) désactivée par défaut.
- Panneau admin : toutes les valeurs venant des utilisateurs sont échappées ; la clé est gardée
  dans l'onglet seulement (oubliée à sa fermeture).
- Source marketing `/start src_…` réduite à `[A-Za-z0-9_-]`.
- Vitrine : en-têtes de sécurité (`web/_headers`) : HTTPS forcé (HSTS), pas d'intégration dans une
  autre page, CSP limitant scripts/connexions au site et à l'API, admin non indexé et non mis en cache.
- Verify tokens Meta : choisir un mot à soi (`WHATSAPP_VERIFY_TOKEN`, `MESSENGER_VERIFY_TOKEN`) plutôt que
  la valeur par défaut `nexmove_verify` (risque faible : ce jeton sert seulement à la poignée de main Meta).
