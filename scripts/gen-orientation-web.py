#!/usr/bin/env python3
"""Génère web/orientation-data.js à partir de api/orientation.py.

Pourquoi un générateur plutôt qu'une recopie : le test existe maintenant à deux endroits
(le bot et le web). Deux copies manuelles divergent toujours — quelqu'un corrige une
formulation d'un côté et oublie l'autre, et deux personnes obtiennent deux résultats
différents au même test. Ici, `api/orientation.py` est la seule source ; le fichier web en
est dérivé, et `tests/test_orientation_web.py` échoue si les deux ne correspondent plus.

Usage : python3 scripts/gen-orientation-web.py [--verifier]
        --verifier : ne réécrit rien, sort en erreur si le fichier est périmé (utilisé en CI).
"""
import json
import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "api"))
import orientation as ori  # noqa: E402

CIBLE = RACINE / "web" / "orientation-data.js"


def construire() -> str:
    data = {
        "riasec": {l: {"nom": n, "desc": d} for l, (n, d) in ori.RIASEC.items()},
        "metiers": {l: list(m) for l, m in ori.METIERS.items()},
        "questions": [{"q": q, "opts": [[l, lib] for l, lib in opts]} for q, opts in ori.TEST_COMPLET],
        "court": ori.TEST_COURT,
    }
    corps = json.dumps(data, ensure_ascii=False, indent=2)
    return (
        "/* Fichier GÉNÉRÉ — ne pas modifier à la main.\n"
        "   Source : api/orientation.py · Régénérer : python3 scripts/gen-orientation-web.py\n"
        "   Le bot et le web doivent poser exactement le même test. */\n"
        f"window.ORIENTATION = {corps};\n"
    )


def main() -> int:
    attendu = construire()
    verifier = "--verifier" in sys.argv
    actuel = CIBLE.read_text(encoding="utf-8") if CIBLE.exists() else ""
    if attendu == actuel:
        print(f"✅ {CIBLE.relative_to(RACINE)} est à jour "
              f"({len(ori.TEST_COMPLET)} questions, {ori.TEST_COURT} en version courte)")
        return 0
    if verifier:
        print(f"❌ {CIBLE.relative_to(RACINE)} ne correspond plus à api/orientation.py.\n"
              "   Lance : python3 scripts/gen-orientation-web.py", file=sys.stderr)
        return 1
    CIBLE.write_text(attendu, encoding="utf-8")
    print(f"✍️  {CIBLE.relative_to(RACINE)} régénéré "
          f"({len(ori.TEST_COMPLET)} questions, {ori.TEST_COURT} en version courte)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
