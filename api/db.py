"""Persistance NexMove — 3 stores SQLite + singletons.
Extrait de main.py sans changement de comportement (PR-A du plan de refactor).
Base : `data/sessions.db` (mono-fichier, WAL). Toutes les méthodes ouvrent leur
propre connexion (timeout 10s) et la referment ; c'est le pattern historique.
"""
from __future__ import annotations
import os, json, sqlite3, hashlib, time, secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

# Alphabet du code de récupération : sans caractères ambigus (0/O, 1/I/L).
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _new_recovery_code() -> str:
    return "NEX-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(5))


def profile_quality(data: dict) -> int:
    """Score de richesse d'un profil — sert à ne garder QUE la meilleure version enregistrée."""
    d = data or {}
    profil = d.get("profil", d) or {}
    prefs = profil.get("preferences") or {}
    q = 0
    nom = (profil.get("identite") or {}).get("nom") or ""
    if nom and nom not in ("—", "N/A", "NA"):
        q += 2
    q += min(len(profil.get("formation") or []), 3) * 2
    q += min(len(profil.get("experience") or []), 3) * 2
    comp = profil.get("competences") or {}
    q += min(sum(len(v or []) for v in comp.values()), 10)
    q += sum(1 for k in ("objectif", "pays_cibles", "nationalite", "financement", "niveau",
                         "mots_cles", "langues_opportunite", "certifs_langue") if prefs.get(k))
    if profil.get("bilan"):
        q += 2
    return q

DB_PATH = os.getenv("NEXMOVE_DB_PATH", "data/sessions.db")


class SessionManager:
    def __init__(self, path: str = DB_PATH):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._path = path
        con = sqlite3.connect(self._path)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE IF NOT EXISTS sessions (user_id TEXT PRIMARY KEY, data TEXT)")
        con.commit(); con.close()

    def get(self, user_id: str) -> Optional[dict]:
        con = sqlite3.connect(self._path, timeout=10)
        row = con.execute("SELECT data FROM sessions WHERE user_id=?", (str(user_id),)).fetchone()
        con.close()
        return json.loads(row[0]) if row else None

    def set(self, user_id: str, session: dict):
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("INSERT INTO sessions(user_id, data) VALUES(?, ?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
                    (str(user_id), json.dumps(session, ensure_ascii=False)))
        con.commit(); con.close()

    def count(self) -> int:
        con = sqlite3.connect(self._path, timeout=10)
        n = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        con.close()
        return int(n)

    def list_active(self) -> list:
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT data FROM sessions").fetchall()
        con.close()
        out = []
        for (d,) in rows:
            try:
                s = json.loads(d)
                if s.get("onboarding_complete"):
                    out.append(s)
            except Exception:
                pass
        return out

    def sources_stats(self) -> list:
        """Attribution marketing : par source (src_...), total d'utilisateurs, onboarding complété, payants."""
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT data FROM sessions").fetchall()
        con.close()
        agg = {}
        for (d,) in rows:
            try:
                s = json.loads(d)
            except Exception:
                continue
            src = s.get("source") or "(direct)"
            a = agg.setdefault(src, {"total": 0, "onboarded": 0, "paid": 0})
            a["total"] += 1
            if s.get("onboarding_complete"):
                a["onboarded"] += 1
            exp = s.get("premium_until")
            if exp and (s.get("premium_tier") or "free") in ("premium", "pro", "vip"):
                try:
                    if datetime.fromisoformat(exp) > datetime.now(timezone.utc):
                        a["paid"] += 1
                except Exception:
                    pass
        return sorted(({"source": k, **v} for k, v in agg.items()), key=lambda x: -x["total"])

    def list_all(self) -> list:
        """Toutes les sessions (y compris onboarding non terminé) — pour les relances."""
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT data FROM sessions").fetchall()
        con.close()
        out = []
        for (d,) in rows:
            try:
                out.append(json.loads(d))
            except Exception:
                pass
        return out

    def create_default(self, user_id: str, chat_id: str, username: str) -> dict:
        return {"user_id": str(user_id), "chat_id": str(chat_id), "username": username, "etape": "WELCOME",
                "profil": {}, "historique": [], "cv_parsed": False, "cv_file_id": None,
                "onboarding_complete": False, "created_at": datetime.now(timezone.utc).isoformat()}


class OppStore:
    def __init__(self, path: str = DB_PATH):
        self._path = path
        con = sqlite3.connect(self._path)
        con.execute("""CREATE TABLE IF NOT EXISTS offres (
            id TEXT PRIMARY KEY, user_id TEXT, titre TEXT, organisation TEXT, type TEXT,
            url TEXT, pays TEXT, financement TEXT, deadline TEXT, score INTEGER, raison TEXT,
            statut TEXT DEFAULT 'nouvelle', notified INTEGER DEFAULT 0, created_at TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS candidatures (
            id TEXT PRIMARY KEY, user_id TEXT, cible TEXT, deadline TEXT,
            statut TEXT DEFAULT 'en_preparation', created_at TEXT)""")
        for ddl in ("ALTER TABLE candidatures ADD COLUMN deadline_iso TEXT DEFAULT ''",
                    "ALTER TABLE candidatures ADD COLUMN reminders_sent TEXT DEFAULT ''",
                    "ALTER TABLE candidatures ADD COLUMN note TEXT DEFAULT ''",
                    "ALTER TABLE candidatures ADD COLUMN updated_at TEXT DEFAULT ''"):
            try:
                con.execute(ddl)
            except Exception:
                pass
        con.execute("""CREATE TABLE IF NOT EXISTS sources_offres (
            id TEXT PRIMARY KEY, titre TEXT, url TEXT, resume TEXT, date TEXT, created_at TEXT)""")
        for ddl in ("ALTER TABLE sources_offres ADD COLUMN type TEXT DEFAULT 'bourse'",
                    "ALTER TABLE sources_offres ADD COLUMN scope TEXT DEFAULT 'both'"):
            try:
                con.execute(ddl)
            except Exception:
                pass
        con.commit(); con.close()

    # ---- sources (pool global de veille) ----
    def add_source(self, it) -> bool:
        oid = hashlib.sha1(str(it.get("url", "")).encode("utf-8", "ignore")).hexdigest()
        con = sqlite3.connect(self._path, timeout=10)
        try:
            if con.execute("SELECT 1 FROM sources_offres WHERE id=?", (oid,)).fetchone():
                return False
            con.execute("INSERT INTO sources_offres(id,titre,url,resume,date,type,scope,created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (oid, it.get("titre", ""), it.get("url", ""), it.get("resume", ""), it.get("date", ""),
                         it.get("type", "bourse"), it.get("scope", "both"), datetime.now(timezone.utc).isoformat()))
            con.commit(); return True
        finally:
            con.close()

    def search_sources(self, keywords, limit=80, prefer_scope=None):
        """Recherche par mots-clés dans le pool de veille.
        `prefer_scope` ('local'/'intl') fait remonter les sources du bon périmètre (filtrage adaptatif)."""
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT titre,url,resume,type,scope FROM sources_offres ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        con.close()
        kws = [str(k).lower() for k in keywords if k and len(str(k)) > 2]
        scored = []
        for (titre, url, resume, typ, scope) in rows:
            txt = (str(titre) + " " + str(resume)).lower()
            sc = sum(1 for k in kws if k in txt)
            if sc <= 0:
                continue
            scope = scope or "both"
            # Bonus/malus adaptatif selon le périmètre visé par l'utilisateur.
            if prefer_scope and scope != "both":
                sc += 2 if scope == prefer_scope else -1
            scored.append((sc, {"titre": titre, "url": url, "resume": resume,
                                "type": typ or "bourse", "scope": scope}))
        scored.sort(key=lambda x: -x[0])
        return [d for sc, d in scored[:10] if sc > 0]

    # ---- candidatures (dossiers suivis) ----
    def add_candidature(self, user_id, cible, deadline="", deadline_iso=""):
        oid = hashlib.sha1(f"cand|{user_id}|{cible}".encode("utf-8", "ignore")).hexdigest()
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("""INSERT INTO candidatures(id,user_id,cible,deadline,deadline_iso,statut,created_at)
                       VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET deadline=excluded.deadline, deadline_iso=excluded.deadline_iso""",
                    (oid, str(user_id), cible, deadline, deadline_iso, "en_preparation", datetime.now(timezone.utc).isoformat()))
        con.commit(); con.close()

    def list_candidatures(self, user_id):
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT cible,deadline,statut FROM candidatures WHERE user_id=? ORDER BY created_at DESC",
                           (str(user_id),)).fetchall()
        con.close()
        return rows

    def update_statut(self, user_id, cible_query, statut) -> int:
        """Met à jour le statut de la/les candidature(s) dont la cible contient `cible_query`.
        Renvoie le nombre de lignes modifiées."""
        con = sqlite3.connect(self._path, timeout=10)
        now = datetime.now(timezone.utc).isoformat()
        con.execute("UPDATE candidatures SET statut=?, updated_at=? WHERE user_id=? AND lower(cible) LIKE ?",
                    (str(statut), now, str(user_id), f"%{str(cible_query).lower()}%"))
        n = con.total_changes
        con.commit(); con.close()
        return int(n)

    def set_note(self, user_id, cible_query, note) -> int:
        """Ajoute/remplace la note libre d'une candidature (ex. « entretien jeudi 14h »).
        Renvoie le nombre de lignes modifiées."""
        con = sqlite3.connect(self._path, timeout=10)
        now = datetime.now(timezone.utc).isoformat()
        con.execute("UPDATE candidatures SET note=?, updated_at=? WHERE user_id=? AND lower(cible) LIKE ?",
                    (str(note)[:500], now, str(user_id), f"%{str(cible_query).lower()}%"))
        n = con.total_changes
        con.commit(); con.close()
        return int(n)

    def list_candidatures_full(self, user_id):
        """Liste enrichie pour le suivi : cible, deadline, statut, note, dates."""
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("""SELECT cible,deadline,statut,note,created_at,updated_at
                              FROM candidatures WHERE user_id=? ORDER BY created_at DESC""",
                           (str(user_id),)).fetchall()
        con.close()
        return rows

    def all_candidatures(self):
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("""SELECT id,user_id,cible,deadline_iso,reminders_sent FROM candidatures
                              WHERE deadline_iso IS NOT NULL AND deadline_iso!=''""").fetchall()
        con.close()
        return rows

    def mark_reminder(self, cand_id, milestone):
        con = sqlite3.connect(self._path, timeout=10)
        row = con.execute("SELECT reminders_sent FROM candidatures WHERE id=?", (cand_id,)).fetchone()
        parts = [p for p in ((row[0] or "").split(",") if row else []) if p]
        if str(milestone) not in parts:
            parts.append(str(milestone))
        con.execute("UPDATE candidatures SET reminders_sent=? WHERE id=?", (",".join(parts), cand_id))
        con.commit(); con.close()

    # ---- offres (par utilisateur, notif digest) ----
    def add(self, user_id, opp) -> bool:
        url = opp.get("url") or opp.get("portail_officiel") or (str(opp.get("titre", "")) + str(opp.get("organisation", "")))
        oid = hashlib.sha1(f"{user_id}|{url}".encode("utf-8", "ignore")).hexdigest()
        con = sqlite3.connect(self._path, timeout=10)
        try:
            if con.execute("SELECT 1 FROM offres WHERE id=?", (oid,)).fetchone():
                return False
            con.execute("""INSERT INTO offres(id,user_id,titre,organisation,type,url,pays,financement,deadline,score,raison,statut,notified,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (oid, str(user_id), opp.get("titre", ""), opp.get("organisation", ""), opp.get("type", ""),
                         url, opp.get("pays", ""), opp.get("financement", ""), opp.get("deadline", ""),
                         int(opp.get("score_composite", 0) or 0), opp.get("raison", ""), "nouvelle", 0,
                         datetime.now(timezone.utc).isoformat()))
            con.commit(); return True
        finally:
            con.close()

    def pending(self, user_id, min_score: int = 60) -> list:
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("""SELECT id,titre,organisation,type,url,financement,deadline,score,raison
                              FROM offres WHERE user_id=? AND notified=0 AND score>=? ORDER BY score DESC""",
                           (str(user_id), min_score)).fetchall()
        con.close()
        return rows

    def mark_notified(self, ids: list):
        if not ids:
            return
        con = sqlite3.connect(self._path, timeout=10)
        con.executemany("UPDATE offres SET notified=1 WHERE id=?", [(i,) for i in ids])
        con.commit(); con.close()

    def count_pending(self, min_score: int = 60) -> int:
        con = sqlite3.connect(self._path, timeout=10)
        n = con.execute("SELECT COUNT(*) FROM offres WHERE notified=0 AND score>=?", (min_score,)).fetchone()[0]
        con.close()
        return int(n)

    def user_stats(self, user_id, days: int = 7) -> dict:
        """Total d'offres et nombre ajouté sur les N derniers jours (gamification / preuve sociale)."""
        con = sqlite3.connect(self._path, timeout=10)
        total = con.execute("SELECT COUNT(*) FROM offres WHERE user_id=?", (str(user_id),)).fetchone()[0]
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        recent = con.execute("SELECT COUNT(*) FROM offres WHERE user_id=? AND created_at>=?",
                             (str(user_id), since)).fetchone()[0]
        con.close()
        return {"total": int(total), "recent": int(recent)}

    # ---- feedback appris 👍/👎 ----
    def _ensure_feedback(self):
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("""CREATE TABLE IF NOT EXISTS feedback (
            user_id TEXT, signal TEXT, score INTEGER DEFAULT 0, updated_at TEXT,
            PRIMARY KEY(user_id, signal))""")
        con.commit(); con.close()

    def add_feedback(self, user_id, signal, vote):
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("""INSERT INTO feedback(user_id,signal,score,updated_at) VALUES(?,?,?,?)
                       ON CONFLICT(user_id,signal) DO UPDATE SET score=score+excluded.score, updated_at=excluded.updated_at""",
                    (str(user_id), str(signal), int(vote), datetime.now(timezone.utc).isoformat()))
        con.commit(); con.close()

    def feedback_delta(self, user_id, signal) -> int:
        # Signal appris : +👍/-👎 cumulés → ajustement borné du score (±25).
        con = sqlite3.connect(self._path, timeout=10)
        row = con.execute("SELECT score FROM feedback WHERE user_id=? AND signal=?",
                          (str(user_id), str(signal))).fetchone()
        con.close()
        if not row:
            return 0
        return max(-25, min(25, int(row[0]) * 8))

    def feedback_counts(self) -> tuple:
        """(nb signaux aimés, nb signaux rejetés) — pour le panel /retours admin."""
        con = sqlite3.connect(self._path, timeout=10)
        try:
            pos = con.execute("SELECT COUNT(*) FROM feedback WHERE score > 0").fetchone()[0]
            neg = con.execute("SELECT COUNT(*) FROM feedback WHERE score < 0").fetchone()[0]
        except Exception:
            pos = neg = 0
        con.close()
        return int(pos or 0), int(neg or 0)

    # ---- journal des « incompris » (persistant : survit aux redéploiements, v3.89) ----
    def _ensure_misses(self):
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("""CREATE TABLE IF NOT EXISTS misses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, uid TEXT, canal TEXT,
            kind TEXT, etape TEXT, text TEXT)""")
        con.commit(); con.close()

    def add_miss(self, row: dict) -> None:
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("INSERT INTO misses(ts,uid,canal,kind,etape,text) VALUES(?,?,?,?,?,?)",
                    (row.get("ts", ""), row.get("uid", ""), row.get("canal", ""),
                     row.get("kind", ""), row.get("etape", ""), str(row.get("text", ""))[:200]))
        # Rétention bornée : on garde les 2000 derniers.
        con.execute("DELETE FROM misses WHERE id <= (SELECT MAX(id) FROM misses) - 2000")
        con.commit(); con.close()

    def list_misses(self, limit: int = 40) -> list:
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT ts,uid,canal,kind,etape,text FROM misses ORDER BY id DESC LIMIT ?",
                           (int(limit),)).fetchall()
        con.close()
        return [dict(zip(("ts", "uid", "canal", "kind", "etape", "text"), r)) for r in rows]

    # ---- compteurs de routage ----
    # En mémoire, ces compteurs mentaient deux fois : uvicorn tourne avec 2 workers, donc
    # chacun ne voyait que la moitié du trafic et `/misses` affichait l'un ou l'autre au
    # hasard ; et tout repartait à zéro à chaque déploiement. Un taux de compréhension qui
    # dépend du worker qui répond ne vaut rien.
    def _ensure_compteurs(self):
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("CREATE TABLE IF NOT EXISTS compteurs (nom TEXT PRIMARY KEY, n INTEGER NOT NULL DEFAULT 0)")
        con.commit(); con.close()

    def bump_counter(self, nom: str, n: int = 1) -> None:
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("INSERT INTO compteurs(nom, n) VALUES(?, ?) "
                    "ON CONFLICT(nom) DO UPDATE SET n = n + excluded.n", (str(nom)[:40], int(n)))
        con.commit(); con.close()

    def get_counters(self) -> dict:
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT nom, n FROM compteurs").fetchall()
        con.close()
        return {r[0]: int(r[1]) for r in rows}

    def reset_counters(self, noms=None) -> None:
        con = sqlite3.connect(self._path, timeout=10)
        if noms:
            con.executemany("DELETE FROM compteurs WHERE nom = ?", [(str(x),) for x in noms])
        else:
            con.execute("DELETE FROM compteurs")
        con.commit(); con.close()

    # ---- bannières de la vitrine ----
    #
    # Une file de programmes datés, de pays différents. Celui « à la une » y reste
    # JUSQU'À SON EXPIRATION, puis le suivant prend la place — décision du Propriétaire
    # du 26/11/2026. D'où le drapeau `vedette` en base plutôt qu'un calcul à la volée :
    # sans mémoire, un programme ajouté entre-temps avec une échéance plus proche
    # volerait la une à celui en cours, et la vitrine changerait de sujet sans raison
    # visible pour quelqu'un qui revient.
    #
    # Règle d'or : rien n'entre ici sans une `fin` (date limite réelle) et une `url`
    # (source vérifiable). Un bandeau est une affirmation publique ; une date approximative
    # y fait plus de dégâts qu'une absence de bandeau.
    def _ensure_bannieres(self):
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("""CREATE TABLE IF NOT EXISTS bannieres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pays TEXT NOT NULL, titre TEXT NOT NULL, texte TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE, debut TEXT NOT NULL, fin TEXT NOT NULL,
            vedette INTEGER DEFAULT 0, retiree INTEGER DEFAULT 0,
            origine TEXT DEFAULT 'cron', created_at TEXT)""")
        con.commit(); con.close()

    def banniere_add(self, pays: str, titre: str, texte: str, url: str,
                     debut: str, fin: str, origine: str = "cron") -> int:
        """Ajoute un programme à la file. Renvoie son id, ou 0 si l'URL est déjà connue
        (l'unicité par URL évite qu'un cron quotidien empile dix fois le même programme)."""
        if not (pays and titre and texte and url and debut and fin):
            return 0
        con = sqlite3.connect(self._path, timeout=10)
        try:
            cur = con.execute(
                "INSERT INTO bannieres(pays,titre,texte,url,debut,fin,origine,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (str(pays)[:60], str(titre)[:200], str(texte)[:400], str(url)[:500],
                 str(debut)[:10], str(fin)[:10], str(origine)[:20],
                 datetime.now(timezone.utc).isoformat()))
            con.commit()
            return int(cur.lastrowid or 0)
        except sqlite3.IntegrityError:
            return 0
        finally:
            con.close()

    def banniere_liste(self, inclure_retirees: bool = False) -> list:
        con = sqlite3.connect(self._path, timeout=10)
        q = ("SELECT id,pays,titre,texte,url,debut,fin,vedette,retiree,origine "
             "FROM bannieres")
        if not inclure_retirees:
            q += " WHERE retiree = 0"
        q += " ORDER BY fin ASC"
        rows = con.execute(q).fetchall()
        con.close()
        return [{"id": r[0], "pays": r[1], "titre": r[2], "texte": r[3], "url": r[4],
                 "debut": r[5], "fin": r[6], "vedette": bool(r[7]), "retiree": bool(r[8]),
                 "origine": r[9]} for r in rows]

    def banniere_vedette(self, aujourdhui: str) -> dict:
        """Le programme à afficher aujourd'hui, ou {} s'il n'y en a aucun.

        La vedette en cours est conservée tant que sa fenêtre est ouverte. Quand elle
        expire, on prend parmi les ouvertes celle dont l'échéance est la plus proche, en
        **évitant le pays de la vedette sortante** quand un autre pays est disponible :
        le Propriétaire veut des programmes de pays différents, et deux bandeaux français
        de suite donneraient l'impression d'un outil qui ne connaît que la France.
        """
        con = sqlite3.connect(self._path, timeout=10)
        try:
            cur = con.execute(
                "SELECT id,pays,titre,texte,url,debut,fin FROM bannieres "
                "WHERE retiree = 0 AND vedette = 1 AND debut <= ? AND fin >= ? LIMIT 1",
                (aujourdhui, aujourdhui))
            row = cur.fetchone()
            if row:
                return {"id": row[0], "pays": row[1], "titre": row[2], "texte": row[3],
                        "url": row[4], "debut": row[5], "fin": row[6]}
            # La vedette a expiré (ou il n'y en avait pas) : on passe à la suivante.
            sortant = con.execute(
                "SELECT pays FROM bannieres WHERE vedette = 1 LIMIT 1").fetchone()
            pays_sortant = (sortant[0] if sortant else "") or ""
            ouvertes = con.execute(
                "SELECT id,pays,titre,texte,url,debut,fin FROM bannieres "
                "WHERE retiree = 0 AND debut <= ? AND fin >= ? ORDER BY fin ASC",
                (aujourdhui, aujourdhui)).fetchall()
            if not ouvertes:
                con.execute("UPDATE bannieres SET vedette = 0 WHERE vedette = 1")
                con.commit()
                return {}
            autre_pays = [r for r in ouvertes if (r[1] or "") != pays_sortant]
            choix = (autre_pays or ouvertes)[0]
            con.execute("UPDATE bannieres SET vedette = 0 WHERE vedette = 1")
            con.execute("UPDATE bannieres SET vedette = 1 WHERE id = ?", (choix[0],))
            con.commit()
            return {"id": choix[0], "pays": choix[1], "titre": choix[2], "texte": choix[3],
                    "url": choix[4], "debut": choix[5], "fin": choix[6]}
        finally:
            con.close()

    def banniere_retirer(self, bid: int) -> bool:
        """Retire sans supprimer : on garde la trace de ce qui a été affiché publiquement."""
        con = sqlite3.connect(self._path, timeout=10)
        cur = con.execute("UPDATE bannieres SET retiree = 1, vedette = 0 WHERE id = ?", (int(bid),))
        con.commit(); con.close()
        return bool(cur.rowcount)

    def banniere_pays_en_file(self, aujourdhui: str) -> list:
        """Les pays déjà présents dans la file et non expirés — pour que le cron cherche
        AILLEURS plutôt que d'empiler cinq programmes du même pays."""
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT DISTINCT pays FROM bannieres "
                           "WHERE retiree = 0 AND fin >= ?", (aujourdhui,)).fetchall()
        con.close()
        return [r[0] for r in rows if r[0]]

    def banniere_purge(self, avant: str) -> int:
        """Marque retirées les bannières expirées depuis longtemps (hygiène, pas affichage :
        l'expiration est déjà gérée par la fenêtre)."""
        con = sqlite3.connect(self._path, timeout=10)
        cur = con.execute("UPDATE bannieres SET retiree = 1, vedette = 0 "
                          "WHERE retiree = 0 AND fin < ?", (str(avant)[:10],))
        con.commit(); con.close()
        return int(cur.rowcount or 0)

    # ---- journal /contact ----
    def _ensure_contacts(self):
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("""CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, username TEXT,
            message TEXT, forwarded INTEGER DEFAULT 0, created_at TEXT)""")
        con.commit(); con.close()

    def add_contact(self, user_id, username, message, forwarded: bool) -> int:
        con = sqlite3.connect(self._path, timeout=10)
        cur = con.execute("INSERT INTO contacts(user_id,username,message,forwarded,created_at) VALUES(?,?,?,?,?)",
                          (str(user_id), str(username or ""), str(message or "")[:4000],
                           1 if forwarded else 0, datetime.now(timezone.utc).isoformat()))
        cid = cur.lastrowid
        con.commit(); con.close()
        return int(cid or 0)

    def list_contacts(self, limit: int = 20) -> list:
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("""SELECT id, user_id, username, message, forwarded, created_at
                              FROM contacts ORDER BY id DESC LIMIT ?""", (int(limit),)).fetchall()
        con.close()
        return rows

    def _ensure_broadcasts(self):
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("""CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id TEXT, filtres TEXT,
            message TEXT, cibles INTEGER DEFAULT 0, envoyes INTEGER DEFAULT 0,
            echecs INTEGER DEFAULT 0, created_at TEXT)""")
        con.commit(); con.close()

    def add_broadcast(self, admin_id, filtres: str, message: str, cibles: int, envoyes: int, echecs: int) -> int:
        con = sqlite3.connect(self._path, timeout=10)
        cur = con.execute(
            "INSERT INTO broadcasts(admin_id,filtres,message,cibles,envoyes,echecs,created_at) VALUES(?,?,?,?,?,?,?)",
            (str(admin_id or ""), str(filtres or "")[:400], str(message or "")[:2000],
             int(cibles), int(envoyes), int(echecs), datetime.now(timezone.utc).isoformat()))
        bid = cur.lastrowid
        con.commit(); con.close()
        return int(bid or 0)

    def list_broadcasts(self, limit: int = 15) -> list:
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("""SELECT id, admin_id, filtres, message, cibles, envoyes, echecs, created_at
                              FROM broadcasts ORDER BY id DESC LIMIT ?""", (int(limit),)).fetchall()
        con.close()
        return rows


class ProfileStore:
    """Persistance des profils par IDENTIFIANT (code de récupération).
    - Chaque utilisateur reçoit un code stable (NEX-XXXXX) à la 1re sauvegarde.
    - Chaque sauvegarde archive une VERSION ; on ne restaure que la MEILLEURE (plus riche),
      pour « garder les meilleures données » même si l'utilisateur change de canal/appareil.
    """
    def __init__(self, path: str = DB_PATH):
        self._path = path
        con = sqlite3.connect(self._path)
        con.execute("""CREATE TABLE IF NOT EXISTS profiles (
            code TEXT PRIMARY KEY, user_id TEXT, data TEXT, quality INTEGER DEFAULT 0,
            version INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)""")
        con.execute("CREATE TABLE IF NOT EXISTS profile_user_map (user_id TEXT PRIMARY KEY, code TEXT)")
        con.execute("""CREATE TABLE IF NOT EXISTS profile_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, user_id TEXT,
            data TEXT, quality INTEGER DEFAULT 0, created_at TEXT)""")
        con.commit(); con.close()

    def code_for(self, user_id: str) -> Optional[str]:
        con = sqlite3.connect(self._path, timeout=10)
        row = con.execute("SELECT code FROM profile_user_map WHERE user_id=?", (str(user_id),)).fetchone()
        con.close()
        return row[0] if row else None

    def _fresh_code(self, con) -> str:
        for _ in range(8):
            code = _new_recovery_code()
            if not con.execute("SELECT 1 FROM profiles WHERE code=?", (code,)).fetchone():
                return code
        return _new_recovery_code() + secrets.choice(_CODE_ALPHABET)

    def save(self, user_id: str, data: dict) -> str:
        """Enregistre une version du profil et renvoie le code de récupération (créé si besoin).
        La ligne `profiles` conserve la MEILLEURE version (quality maximale)."""
        now = datetime.now(timezone.utc).isoformat()
        q = profile_quality(data)
        payload = json.dumps(data, ensure_ascii=False)
        con = sqlite3.connect(self._path, timeout=10)
        try:
            row = con.execute("SELECT code FROM profile_user_map WHERE user_id=?", (str(user_id),)).fetchone()
            code = row[0] if row else self._fresh_code(con)
            if not row:
                con.execute("INSERT OR REPLACE INTO profile_user_map(user_id,code) VALUES(?,?)", (str(user_id), code))
            # Historique (toujours archivé)
            con.execute("INSERT INTO profile_versions(code,user_id,data,quality,created_at) VALUES(?,?,?,?,?)",
                        (code, str(user_id), payload, q, now))
            # Ligne principale : on ne remplace que si la nouvelle version est AU MOINS aussi riche.
            cur = con.execute("SELECT quality, version FROM profiles WHERE code=?", (code,)).fetchone()
            if cur is None:
                con.execute("INSERT INTO profiles(code,user_id,data,quality,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                            (code, str(user_id), payload, q, 1, now, now))
            elif q >= int(cur[0] or 0):
                con.execute("UPDATE profiles SET user_id=?, data=?, quality=?, version=?, updated_at=? WHERE code=?",
                            (str(user_id), payload, q, int(cur[1] or 1) + 1, now, code))
            con.commit()
            return code
        finally:
            con.close()

    def best(self, code: str) -> Optional[dict]:
        """Meilleure version connue pour ce code (profiles = déjà la max ; repli sur l'historique)."""
        code = (code or "").strip().upper()
        con = sqlite3.connect(self._path, timeout=10)
        try:
            row = con.execute("SELECT data, quality FROM profiles WHERE code=?", (code,)).fetchone()
            best_data, best_q = (json.loads(row[0]), int(row[1] or 0)) if row else (None, -1)
            vrow = con.execute("SELECT data, quality FROM profile_versions WHERE code=? ORDER BY quality DESC LIMIT 1", (code,)).fetchone()
            if vrow and int(vrow[1] or 0) > best_q:
                best_data = json.loads(vrow[0])
            return best_data
        finally:
            con.close()

    def restore(self, code: str, new_user_id: str) -> Optional[dict]:
        """Restaure le meilleur profil du code sur un nouvel utilisateur (portage inter-canaux)."""
        data = self.best(code)
        if data is None:
            return None
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("INSERT OR REPLACE INTO profile_user_map(user_id,code) VALUES(?,?)",
                    (str(new_user_id), (code or "").strip().upper()))
        con.commit(); con.close()
        return data


class UsageStore:
    """Compteurs d'usage par jour et par fonctionnalité — support des quotas gratuits.
    (L'admin n'est jamais compté : la vérification se fait côté appelant.)"""
    def __init__(self, path: str = DB_PATH):
        self._path = path
        con = sqlite3.connect(self._path)
        con.execute("""CREATE TABLE IF NOT EXISTS usage (
            user_id TEXT, day TEXT, feature TEXT, count INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, day, feature))""")
        con.commit(); con.close()

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def count(self, user_id: str, feature: str, day: Optional[str] = None) -> int:
        day = day or self._today()
        con = sqlite3.connect(self._path, timeout=10)
        row = con.execute("SELECT count FROM usage WHERE user_id=? AND day=? AND feature=?",
                          (str(user_id), day, str(feature))).fetchone()
        con.close()
        return int(row[0]) if row else 0

    def bump(self, user_id: str, feature: str, day: Optional[str] = None) -> int:
        """Incrémente et renvoie le nouveau compteur du jour."""
        day = day or self._today()
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("""INSERT INTO usage(user_id,day,feature,count) VALUES(?,?,?,1)
                       ON CONFLICT(user_id,day,feature) DO UPDATE SET count=count+1""",
                    (str(user_id), day, str(feature)))
        n = con.execute("SELECT count FROM usage WHERE user_id=? AND day=? AND feature=?",
                       (str(user_id), day, str(feature))).fetchone()[0]
        con.commit(); con.close()
        return int(n)


class PremiumStore:
    """Codes d'abonnement premium : générés en lots (vendus sur Chariow), activés via /premium.
    Un code = un tier (premium/pro/vip) + une durée en jours ; usage unique."""
    def __init__(self, path: str = DB_PATH):
        self._path = path
        con = sqlite3.connect(self._path)
        con.execute("""CREATE TABLE IF NOT EXISTS premium_codes (
            code TEXT PRIMARY KEY, tier TEXT, days INTEGER, batch TEXT,
            status TEXT DEFAULT 'unused', used_by TEXT, used_at TEXT, created_at TEXT)""")
        con.commit(); con.close()

    def _fresh_code(self, con) -> str:
        for _ in range(10):
            code = "PRM-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
            if not con.execute("SELECT 1 FROM premium_codes WHERE code=?", (code,)).fetchone():
                return code
        return "PRM-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(10))

    def create_codes(self, tier: str, days: int, count: int, batch: str = "") -> list:
        now = datetime.now(timezone.utc).isoformat()
        out = []
        con = sqlite3.connect(self._path, timeout=10)
        try:
            for _ in range(max(1, int(count))):
                code = self._fresh_code(con)
                con.execute("INSERT INTO premium_codes(code,tier,days,batch,status,created_at) VALUES(?,?,?,?, 'unused', ?)",
                            (code, tier, int(days), batch or now[:10], now))
                out.append(code)
            con.commit()
        finally:
            con.close()
        return out

    def info(self, code: str) -> Optional[dict]:
        code = (code or "").strip().upper()
        con = sqlite3.connect(self._path, timeout=10)
        row = con.execute("SELECT code,tier,days,status,used_by,used_at FROM premium_codes WHERE code=?", (code,)).fetchone()
        con.close()
        if not row:
            return None
        return {"code": row[0], "tier": row[1], "days": int(row[2] or 0), "status": row[3],
                "used_by": row[4], "used_at": row[5]}

    def redeem(self, code: str, user_id: str) -> dict:
        """Consomme un code (usage unique). Renvoie {ok, tier, days} ou {ok:False, reason}."""
        code = (code or "").strip().upper()
        con = sqlite3.connect(self._path, timeout=10)
        try:
            row = con.execute("SELECT tier,days,status FROM premium_codes WHERE code=?", (code,)).fetchone()
            if not row:
                return {"ok": False, "reason": "introuvable"}
            if row[2] == "used":
                return {"ok": False, "reason": "déjà utilisé"}
            con.execute("UPDATE premium_codes SET status='used', used_by=?, used_at=? WHERE code=? AND status='unused'",
                        (str(user_id), datetime.now(timezone.utc).isoformat(), code))
            if con.total_changes == 0:      # course : consommé entre-temps
                return {"ok": False, "reason": "déjà utilisé"}
            con.commit()
            return {"ok": True, "tier": row[0], "days": int(row[1] or 0)}
        finally:
            con.close()

    def stats(self) -> dict:
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT status, COUNT(*) FROM premium_codes GROUP BY status").fetchall()
        con.close()
        return {s: int(n) for s, n in rows}

    def list_codes(self, status: Optional[str] = None, limit: int = 100) -> list:
        """Liste les codes (optionnellement filtrés par statut 'used'/'unused'),
        les plus récents d'abord. Renvoie des dicts {code,tier,days,status,used_by,used_at,created_at,batch}."""
        con = sqlite3.connect(self._path, timeout=10)
        try:
            q = ("SELECT code,tier,days,status,used_by,used_at,created_at,batch "
                 "FROM premium_codes")
            args: list = []
            if status in ("used", "unused"):
                q += " WHERE status=?"
                args.append(status)
            q += " ORDER BY created_at DESC LIMIT ?"
            args.append(int(limit))
            rows = con.execute(q, args).fetchall()
        finally:
            con.close()
        return [{"code": r[0], "tier": r[1], "days": int(r[2] or 0), "status": r[3],
                 "used_by": r[4], "used_at": r[5], "created_at": r[6], "batch": r[7]} for r in rows]

    def statuses(self, codes: list) -> dict:
        """Statut de codes PRÉCIS (cross-check d'une liste collée) : {CODE: 'unused'|'used'|'unknown'}."""
        norm = [c.strip().upper() for c in (codes or []) if c and c.strip()]
        if not norm:
            return {}
        out = {c: "unknown" for c in norm}
        con = sqlite3.connect(self._path, timeout=10)
        try:
            qmarks = ",".join("?" * len(norm))
            rows = con.execute(f"SELECT code,status FROM premium_codes WHERE code IN ({qmarks})", norm).fetchall()
            for code, st in rows:
                out[str(code).upper()] = st
        finally:
            con.close()
        return out


class CreditStore:
    """Codes de crédits FONGIBLES : chaque code = N crédits utilisables sur n'importe quelle action.
    Usage unique. Vendus sur Chariow, activés via /credits <code>. (Monétisation flexible sans abonnement.)"""
    def __init__(self, path: str = DB_PATH):
        self._path = path
        con = sqlite3.connect(self._path)
        con.execute("""CREATE TABLE IF NOT EXISTS credit_codes (
            code TEXT PRIMARY KEY, credits INTEGER, batch TEXT,
            status TEXT DEFAULT 'unused', used_by TEXT, used_at TEXT, created_at TEXT)""")
        con.commit(); con.close()

    def _fresh_code(self, con) -> str:
        for _ in range(10):
            code = "CRD-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
            if not con.execute("SELECT 1 FROM credit_codes WHERE code=?", (code,)).fetchone():
                return code
        return "CRD-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(10))

    def create_codes(self, credits: int, count: int, batch: str = "") -> list:
        now = datetime.now(timezone.utc).isoformat()
        out = []
        con = sqlite3.connect(self._path, timeout=10)
        try:
            for _ in range(max(1, int(count))):
                code = self._fresh_code(con)
                con.execute("INSERT INTO credit_codes(code,credits,batch,status,created_at) VALUES(?,?,?, 'unused', ?)",
                            (code, int(credits), batch or now[:10], now))
                out.append(code)
            con.commit()
        finally:
            con.close()
        return out

    def redeem(self, code: str, user_id: str) -> dict:
        """Consomme un code (usage unique). Renvoie {ok, credits} ou {ok:False, reason}."""
        code = (code or "").strip().upper()
        con = sqlite3.connect(self._path, timeout=10)
        try:
            row = con.execute("SELECT credits,status FROM credit_codes WHERE code=?", (code,)).fetchone()
            if not row:
                return {"ok": False, "reason": "introuvable"}
            if row[1] == "used":
                return {"ok": False, "reason": "déjà utilisé"}
            con.execute("UPDATE credit_codes SET status='used', used_by=?, used_at=? WHERE code=? AND status='unused'",
                        (str(user_id), datetime.now(timezone.utc).isoformat(), code))
            if con.total_changes == 0:
                return {"ok": False, "reason": "déjà utilisé"}
            con.commit()
            return {"ok": True, "credits": int(row[0] or 0)}
        finally:
            con.close()

    def stats(self) -> dict:
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT status, COUNT(*) FROM credit_codes GROUP BY status").fetchall()
        con.close()
        return {s: int(n) for s, n in rows}


class ReferralStore:
    """Parrainage : un code stable par utilisateur ; chaque filleul n'est parrainé qu'une fois."""
    def __init__(self, path: str = DB_PATH):
        self._path = path
        con = sqlite3.connect(self._path)
        con.execute("CREATE TABLE IF NOT EXISTS referral_codes (user_id TEXT PRIMARY KEY, code TEXT UNIQUE)")
        con.execute("""CREATE TABLE IF NOT EXISTS referrals (
            referred_user TEXT PRIMARY KEY, referrer_user TEXT, status TEXT DEFAULT 'pending', created_at TEXT)""")
        con.commit(); con.close()

    def code_for(self, user_id: str) -> str:
        con = sqlite3.connect(self._path, timeout=10)
        try:
            row = con.execute("SELECT code FROM referral_codes WHERE user_id=?", (str(user_id),)).fetchone()
            if row:
                return row[0]
            for _ in range(10):
                code = "P" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
                if not con.execute("SELECT 1 FROM referral_codes WHERE code=?", (code,)).fetchone():
                    con.execute("INSERT INTO referral_codes(user_id,code) VALUES(?,?)", (str(user_id), code))
                    con.commit(); return code
            code = "P" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
            con.execute("INSERT INTO referral_codes(user_id,code) VALUES(?,?)", (str(user_id), code))
            con.commit(); return code
        finally:
            con.close()

    def user_by_code(self, code: str) -> Optional[str]:
        con = sqlite3.connect(self._path, timeout=10)
        row = con.execute("SELECT user_id FROM referral_codes WHERE code=?", ((code or "").strip(),)).fetchone()
        con.close()
        return row[0] if row else None

    def attribute(self, referred_user: str, referrer_user: str) -> bool:
        """Enregistre un filleul (une seule fois, jamais soi-même). True si nouvellement enregistré."""
        if not referrer_user or str(referred_user) == str(referrer_user):
            return False
        con = sqlite3.connect(self._path, timeout=10)
        try:
            if con.execute("SELECT 1 FROM referrals WHERE referred_user=?", (str(referred_user),)).fetchone():
                return False
            con.execute("INSERT INTO referrals(referred_user,referrer_user,status,created_at) VALUES(?,?, 'pending', ?)",
                        (str(referred_user), str(referrer_user), datetime.now(timezone.utc).isoformat()))
            con.commit(); return True
        finally:
            con.close()

    def mark_completed(self, referred_user: str) -> Optional[str]:
        """Marque le filleul comme complété (onboarding fini). Renvoie le parrain SI transition réussie."""
        con = sqlite3.connect(self._path, timeout=10)
        try:
            row = con.execute("SELECT referrer_user, status FROM referrals WHERE referred_user=?",
                             (str(referred_user),)).fetchone()
            if not row or row[1] == "completed":
                return None
            con.execute("UPDATE referrals SET status='completed' WHERE referred_user=? AND status!='completed'",
                        (str(referred_user),))
            con.commit()
            return row[0] if con.total_changes else None
        finally:
            con.close()

    def count_completed(self, referrer_user: str) -> int:
        con = sqlite3.connect(self._path, timeout=10)
        n = con.execute("SELECT COUNT(*) FROM referrals WHERE referrer_user=? AND status='completed'",
                       (str(referrer_user),)).fetchone()[0]
        con.close()
        return int(n)


class Cache:
    """Cache TTL sur SQLite (utilisé pour Tavily 6 h et embeddings 7 j)."""
    def __init__(self, path: str = DB_PATH):
        self._path = path
        con = sqlite3.connect(self._path)
        con.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT, expires REAL)")
        con.commit(); con.close()

    def get(self, key):
        con = sqlite3.connect(self._path, timeout=10)
        row = con.execute("SELECT v,expires FROM cache WHERE k=?", (key,)).fetchone()
        con.close()
        if row and row[1] > time.time():
            try:
                return json.loads(row[0])
            except Exception:
                return None
        return None

    def set(self, key, value, ttl: int = 21600):
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("INSERT INTO cache(k,v,expires) VALUES(?,?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v, expires=excluded.expires",
                    (key, json.dumps(value, ensure_ascii=False), time.time() + ttl))
        con.commit(); con.close()


class LinkStore:
    """Raccourcisseur de liens maison : un code court -> URL cible, avec comptage de clics.
    Sert à n'afficher QU'UN lien propre par offre et à pouvoir mesurer/mettre à jour ensuite."""
    _ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"  # sans caractères ambigus

    def __init__(self, path: str = DB_PATH):
        self._path = path
        con = sqlite3.connect(self._path)
        con.execute("""CREATE TABLE IF NOT EXISTS links (
            code TEXT PRIMARY KEY, url TEXT UNIQUE, clicks INTEGER DEFAULT 0, created_at TEXT)""")
        con.commit(); con.close()

    def _gen_code(self, n: int = 6) -> str:
        import secrets
        return "".join(secrets.choice(self._ALPHABET) for _ in range(n))

    def shorten(self, url: str) -> str:
        """Retourne un code court stable pour cette URL (réutilisé si déjà vu)."""
        url = (url or "").strip()
        if not url:
            return ""
        con = sqlite3.connect(self._path, timeout=10)
        try:
            row = con.execute("SELECT code FROM links WHERE url=?", (url,)).fetchone()
            if row:
                return row[0]
            for _ in range(5):
                code = self._gen_code()
                try:
                    con.execute("INSERT INTO links(code,url,clicks,created_at) VALUES(?,?,0,?)",
                                (code, url, datetime.now(timezone.utc).isoformat()))
                    con.commit()
                    return code
                except sqlite3.IntegrityError:
                    # collision de code (rare) : on réessaie ; ou l'URL a été insérée entre-temps
                    row = con.execute("SELECT code FROM links WHERE url=?", (url,)).fetchone()
                    if row:
                        return row[0]
            return ""
        finally:
            con.close()

    def resolve(self, code: str) -> Optional[str]:
        """Retourne l'URL cible et incrémente le compteur de clics."""
        con = sqlite3.connect(self._path, timeout=10)
        try:
            row = con.execute("SELECT url FROM links WHERE code=?", (str(code or ""),)).fetchone()
            if not row:
                return None
            con.execute("UPDATE links SET clicks=clicks+1 WHERE code=?", (str(code),))
            con.commit()
            return row[0]
        finally:
            con.close()


class RecruiterOfferStore:
    """Offres déposées par des RECRUTEURS via le bot. Chaque offre passe par une
    validation admin (et un paiement, l'offre de recrutement étant payante) avant
    d'être diffusée aux profils correspondants ou à tous.
    Statuts : 'en_attente' (déposée, à valider+payer) · 'validee' (diffusée) · 'refusee'."""
    _FIELDS = ("titre", "entreprise", "lieu", "contrat", "description",
               "profil_recherche", "remuneration", "postuler", "deadline")

    def __init__(self, path: str = DB_PATH):
        self._path = path
        con = sqlite3.connect(self._path)
        con.execute("""CREATE TABLE IF NOT EXISTS recruiter_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recruiter_id TEXT, recruiter_channel TEXT, recruiter_chat_id TEXT, recruiter_name TEXT,
            titre TEXT, entreprise TEXT, lieu TEXT, contrat TEXT, description TEXT,
            profil_recherche TEXT, remuneration TEXT, postuler TEXT, deadline TEXT,
            status TEXT DEFAULT 'en_attente', created_at TEXT,
            decided_at TEXT, decided_by TEXT, broadcast_count INTEGER DEFAULT 0)""")
        con.commit(); con.close()

    def add(self, recruiter: dict, offer: dict) -> int:
        now = datetime.now(timezone.utc).isoformat()
        con = sqlite3.connect(self._path, timeout=10)
        try:
            cur = con.execute(
                """INSERT INTO recruiter_offers
                (recruiter_id, recruiter_channel, recruiter_chat_id, recruiter_name,
                 titre, entreprise, lieu, contrat, description, profil_recherche,
                 remuneration, postuler, deadline, status, created_at)
                VALUES (?,?,?,?, ?,?,?,?,?,?, ?,?,?, 'en_attente', ?)""",
                (str(recruiter.get("user_id", "")), recruiter.get("channel", ""),
                 str(recruiter.get("chat_id", "")), recruiter.get("name", ""),
                 offer.get("titre", ""), offer.get("entreprise", ""), offer.get("lieu", ""),
                 offer.get("contrat", ""), offer.get("description", ""),
                 offer.get("profil_recherche", ""), offer.get("remuneration", ""),
                 offer.get("postuler", ""), offer.get("deadline", ""), now))
            con.commit()
            return int(cur.lastrowid)
        finally:
            con.close()

    def _row_to_dict(self, r) -> dict:
        cols = ("id", "recruiter_id", "recruiter_channel", "recruiter_chat_id", "recruiter_name",
                "titre", "entreprise", "lieu", "contrat", "description", "profil_recherche",
                "remuneration", "postuler", "deadline", "status", "created_at",
                "decided_at", "decided_by", "broadcast_count")
        return {c: r[i] for i, c in enumerate(cols)}

    def get(self, offer_id: int) -> Optional[dict]:
        con = sqlite3.connect(self._path, timeout=10)
        r = con.execute("SELECT * FROM recruiter_offers WHERE id=?", (int(offer_id),)).fetchone()
        con.close()
        return self._row_to_dict(r) if r else None

    def list_by_status(self, status: Optional[str] = None, limit: int = 30) -> list:
        con = sqlite3.connect(self._path, timeout=10)
        try:
            if status:
                rows = con.execute("SELECT * FROM recruiter_offers WHERE status=? ORDER BY id DESC LIMIT ?",
                                   (status, int(limit))).fetchall()
            else:
                rows = con.execute("SELECT * FROM recruiter_offers ORDER BY id DESC LIMIT ?",
                                   (int(limit),)).fetchall()
        finally:
            con.close()
        return [self._row_to_dict(r) for r in rows]

    def set_status(self, offer_id: int, status: str, by: str = "", broadcast_count: int = 0) -> bool:
        con = sqlite3.connect(self._path, timeout=10)
        try:
            con.execute("""UPDATE recruiter_offers
                SET status=?, decided_at=?, decided_by=?, broadcast_count=? WHERE id=?""",
                        (status, datetime.now(timezone.utc).isoformat(), str(by),
                         int(broadcast_count), int(offer_id)))
            con.commit()
            return con.total_changes > 0
        finally:
            con.close()

    def stats(self) -> dict:
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT status, COUNT(*) FROM recruiter_offers GROUP BY status").fetchall()
        con.close()
        return {s: int(n) for s, n in rows}


# ── Singletons partagés — même contrat qu'avant la PR-A ──
session_manager = SessionManager()
opp_store = OppStore()
opp_store._ensure_feedback()
opp_store._ensure_contacts()
opp_store._ensure_broadcasts()
opp_store._ensure_misses()
opp_store._ensure_compteurs()
opp_store._ensure_bannieres()
profile_store = ProfileStore()
usage_store = UsageStore()
premium_store = PremiumStore()
credit_store = CreditStore()
referral_store = ReferralStore()
cache = Cache()
link_store = LinkStore()
recruiter_offer_store = RecruiterOfferStore()


# ── Droit à l'effacement (RGPD art. 17) ────────────────────────────────────────────────────────
# Toutes les tables vivent dans le MÊME fichier SQLite : un effacement complet tient donc dans
# UNE transaction (tout ou rien — jamais de suppression à moitié faite).
#
# Deux traitements distincts, assumés et documentés dans la politique de confidentialité :
#  • EFFACÉ   : tout ce qui décrit la personne (profil, CV, historique, candidatures, messages…).
#  • ANONYMISÉ: les lignes qu'on doit garder pour empêcher la fraude (un code promo doit rester
#               « utilisé », sinon il redevient réutilisable) ou pour ne pas amputer les données
#               d'AUTRES utilisateurs (le parrainage de quelqu'un d'autre). L'identifiant y est
#               remplacé par une chaîne vide : plus aucun lien avec la personne.
_DELETE_BY_USER = [          # (table, colonne identifiant)
    ("sessions",          "user_id"),   # profil, CV analysé, historique de conversation
    ("offres",            "user_id"),   # opportunités trouvées pour elle (+ scores)
    ("candidatures",      "user_id"),
    ("feedback",          "user_id"),   # ses 👍/👎 sur les offres
    ("usage",             "user_id"),   # compteurs d'usage quotidiens
    ("contacts",          "user_id"),   # messages envoyés à l'équipe
    ("misses",            "uid"),       # messages non compris, journalisés avec leur texte
    ("profiles",          "user_id"),   # profil PORTABLE (/moncode) — sinon le CV survivait
    ("profile_versions",  "user_id"),
    ("profile_user_map",  "user_id"),
    ("referral_codes",    "user_id"),
    ("referrals",         "referred_user"),
    ("recruiter_offers",  "recruiter_id"),
]
_ANONYMIZE_BY_USER = [       # (table, colonne) — la ligne reste, l'identifiant disparaît
    ("referrals",     "referrer_user"),   # garde le parrainage des AUTRES intact
    ("premium_codes", "used_by"),         # garde le code « utilisé » (anti-réutilisation)
    ("credit_codes",  "used_by"),
]


def delete_user_data(user_id: str, path: str = DB_PATH) -> dict:
    """Efface TOUTES les données d'une personne, en une seule transaction.

    Retourne le détail par table ({'sessions': 1, 'offres': 12, …}) pour pouvoir le prouver
    (journal, test, réponse à une demande RGPD). Lève l'exception en cas d'échec : l'appelant
    ne doit JAMAIS annoncer une suppression qui n'a pas eu lieu.
    """
    uid = str(user_id or "").strip()
    if not uid:
        raise ValueError("delete_user_data : user_id vide")
    detail: dict = {}
    con = sqlite3.connect(path, timeout=30)
    try:
        with con:                                  # COMMIT si tout passe, ROLLBACK sinon
            for table, col in _DELETE_BY_USER:
                try:
                    cur = con.execute(f"DELETE FROM {table} WHERE {col} = ?", (uid,))
                except sqlite3.OperationalError:   # table pas encore créée sur cette instance
                    continue
                if cur.rowcount:
                    detail[table] = detail.get(table, 0) + cur.rowcount
            for table, col in _ANONYMIZE_BY_USER:
                try:
                    cur = con.execute(f"UPDATE {table} SET {col} = '' WHERE {col} = ?", (uid,))
                except sqlite3.OperationalError:
                    continue
                if cur.rowcount:
                    detail[f"{table}.{col} (anonymisé)"] = cur.rowcount
    finally:
        con.close()
    return detail
