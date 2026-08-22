"""Persistance NexMove — 3 stores SQLite + singletons.
Extrait de main.py sans changement de comportement (PR-A du plan de refactor).
Base : `data/sessions.db` (mono-fichier, WAL). Toutes les méthodes ouvrent leur
propre connexion (timeout 10s) et la referment ; c'est le pattern historique.
"""
from __future__ import annotations
import os, json, sqlite3, hashlib, time
from datetime import datetime, timezone, timedelta
from typing import Optional

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
                    "ALTER TABLE candidatures ADD COLUMN reminders_sent TEXT DEFAULT ''"):
            try:
                con.execute(ddl)
            except Exception:
                pass
        con.execute("""CREATE TABLE IF NOT EXISTS sources_offres (
            id TEXT PRIMARY KEY, titre TEXT, url TEXT, resume TEXT, date TEXT, created_at TEXT)""")
        try:
            con.execute("ALTER TABLE sources_offres ADD COLUMN type TEXT DEFAULT 'bourse'")
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
            con.execute("INSERT INTO sources_offres(id,titre,url,resume,date,type,created_at) VALUES(?,?,?,?,?,?,?)",
                        (oid, it.get("titre", ""), it.get("url", ""), it.get("resume", ""), it.get("date", ""),
                         it.get("type", "bourse"), datetime.now(timezone.utc).isoformat()))
            con.commit(); return True
        finally:
            con.close()

    def search_sources(self, keywords, limit=80):
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT titre,url,resume,type FROM sources_offres ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        con.close()
        kws = [str(k).lower() for k in keywords if k and len(str(k)) > 2]
        scored = []
        for (titre, url, resume, typ) in rows:
            txt = (str(titre) + " " + str(resume)).lower()
            sc = sum(1 for k in kws if k in txt)
            if sc > 0:
                scored.append((sc, {"titre": titre, "url": url, "resume": resume, "type": typ or "bourse"}))
        scored.sort(key=lambda x: -x[0])
        return [d for _, d in scored[:10]]

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


# ── Singletons partagés — même contrat qu'avant la PR-A ──
session_manager = SessionManager()
opp_store = OppStore()
opp_store._ensure_feedback()
opp_store._ensure_contacts()
cache = Cache()
