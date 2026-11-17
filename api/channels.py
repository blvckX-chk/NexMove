"""Canaux d'envoi — Telegram, WhatsApp Cloud API, Messenger.
Extrait de main.py (PR-C du refactor). Comportement STRICTEMENT identique :
- même token Telegram (env ou fichier de repli), même fallback Markdown → texte brut
- mêmes buttons WhatsApp (jusqu'à 3) / list (au-delà)
- mêmes quick replies Messenger
"""
from __future__ import annotations
import os, json, logging
from typing import Optional

from http_client import http

logger = logging.getLogger("forge-nex")


# ── Lecture du token Telegram (env ou fichier de repli) ──
def _read_telegram_token() -> str:
    tok = os.getenv("TELEGRAM_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if tok:
        return tok.strip()
    for _p in ("data/telegram_token.txt", "/app/data/telegram_token.txt", "telegram_token.txt"):
        try:
            with open(_p) as _f:
                _v = _f.read().strip()
                if _v:
                    return _v
        except Exception:
            pass
    return ""


TELEGRAM_TOKEN        = _read_telegram_token()
WHATSAPP_TOKEN        = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID     = os.getenv("WHATSAPP_PHONE_ID", "")
MESSENGER_TOKEN       = os.getenv("MESSENGER_TOKEN", "")


# ── MIME helper (partagé par les 3 canaux) ──
def _mime_for(filename: str) -> str:
    fn = (filename or "").lower()
    if fn.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if fn.endswith(".pdf"):
        return "application/pdf"
    return "application/octet-stream"


# ── Découpage des messages longs (partagé par les 3 canaux) ──
# Chaque canal a une limite (Telegram 4096, WhatsApp 4096 / 1024 pour un message à boutons,
# Messenger 2000). Avant, on TRONQUAIT : la fin des messages longs (ex. récap CV + question)
# disparaissait. On découpe désormais proprement aux paragraphes, puis aux lignes, puis aux mots.
def split_message(text: str, limit: int) -> list:
    text = text or ""
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for para in text.split("\n\n"):
        cand = f"{cur}\n\n{para}" if cur else para
        if len(cand) <= limit:
            cur = cand
            continue
        if cur:
            parts.append(cur)
            cur = ""
        while len(para) > limit:
            cut = para.rfind("\n", 0, limit)
            if cut <= 0:
                cut = para.rfind(" ", 0, limit)
            if cut <= 0:
                cut = limit
            parts.append(para[:cut].rstrip())
            para = para[cut:].lstrip()
        cur = para
    if cur:
        parts.append(cur)
    return [p for p in parts if p.strip()] or [text[:limit]]


def split_head_tail(text: str, limit: int):
    """Pour un message À BOUTONS dont le corps est limité : renvoie (tête, queue) où la queue
    (≤ limit, idéalement le dernier paragraphe = la question) porte les boutons, et la tête
    (éventuellement vide) part en messages texte normaux avant."""
    text = text or ""
    if len(text) <= limit:
        return "", text
    head, sep, last = text.rpartition("\n\n")
    if sep and 0 < len(last) <= limit:
        return head, last
    parts = split_message(text, limit)
    return "\n\n".join(parts[:-1]), parts[-1]


# ───────────────────────── Telegram ─────────────────────────
async def _tg(method: str, payload: dict) -> bool:
    if not TELEGRAM_TOKEN:
        return False
    try:
        r = await http().post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}", json=payload, timeout=25.0)
        if r.status_code != 200:
            logger.error(f"tg {method} chat={payload.get('chat_id')} {r.status_code}: {r.text[:150]}")
        return r.status_code == 200
    except Exception as e:
        logger.error(f"tg {method}: {e}")
        return False


async def send_message(chat_id, text, keyboard=None) -> bool:
    parts = split_message(text, 4000)   # découpe (avant : tronqué à 4000)
    ok = True
    for i, part in enumerate(parts):
        payload = {"chat_id": str(chat_id), "text": part, "parse_mode": "Markdown", "disable_web_page_preview": True}
        if keyboard and i == len(parts) - 1:   # boutons sur la DERNIÈRE partie
            payload["reply_markup"] = keyboard
        sent = await _tg("sendMessage", payload)
        if not sent:
            # Repli sans Markdown : un */_/[ déséquilibré déclenche 400 "can't parse entities".
            payload.pop("parse_mode", None)
            sent = await _tg("sendMessage", payload)
        ok = sent and ok
    return ok


async def tg_get_file(file_id: str):
    """Télécharge un fichier Telegram (getFile puis download). Renvoie les octets ou None.
    Sert au webhook Telegram natif (réception des CV en document/photo)."""
    if not (TELEGRAM_TOKEN and file_id):
        return None
    try:
        r = await http().get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile",
                             params={"file_id": file_id}, timeout=20.0)
        if r.status_code != 200:
            logger.error(f"tg getFile {r.status_code}: {r.text[:150]}")
            return None
        path = (r.json().get("result") or {}).get("file_path")
        if not path:
            return None
        fr = await http().get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}",
                              timeout=45.0, follow_redirects=True)
        return fr.content if fr.status_code == 200 else None
    except Exception as e:
        logger.error(f"tg getFile: {e}")
        return None


async def edit_message(chat_id, message_id, text, keyboard=None) -> bool:
    try:
        mid = int(message_id)
    except Exception:
        return await send_message(chat_id, text, keyboard)
    payload = {"chat_id": str(chat_id), "message_id": mid, "text": (text or "")[:4000], "parse_mode": "Markdown", "disable_web_page_preview": True}
    if keyboard:
        payload["reply_markup"] = keyboard
    ok = await _tg("editMessageText", payload)
    if not ok:
        payload.pop("parse_mode", None)
        ok = await _tg("editMessageText", payload)
    return ok


async def answer_callback(cb_id, text: str = "") -> bool:
    return await _tg("answerCallbackQuery", {"callback_query_id": str(cb_id), "text": text[:180]})


async def _send_telegram_document(chat_id, filename, pdf_bytes, caption: str = "") -> bool:
    if not TELEGRAM_TOKEN:
        return False
    try:
        r = await http().post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
            data={"chat_id": str(chat_id), "caption": (caption or "")[:1000]},
            files={"document": (filename, pdf_bytes, _mime_for(filename))},
            timeout=45.0,
        )
        return r.status_code == 200
    except Exception as e:
        logger.error(f"sendDocument erreur: {e}")
        return False


def _btn(text: str, data: str) -> dict:
    return {"text": text, "callback_data": data}


def _kb(rows: list) -> dict:
    return {"inline_keyboard": rows}


def _tg_keyboard(options: list) -> dict:
    """Options [(label, action_id), ...] -> clavier inline Telegram (2 boutons/ligne)."""
    rows, cur = [], []
    for (lbl, aid) in options:
        cur.append(_btn(lbl, aid))
        if len(cur) == 2:
            rows.append(cur); cur = []
    if cur:
        rows.append(cur)
    return _kb(rows)


# ──────────────────────── WhatsApp Cloud API ────────────────────────
async def wa_send(payload: dict) -> bool:
    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_ID):
        return False
    try:
        r = await http().post(f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/messages",
                              headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}, json=payload, timeout=25.0)
        if r.status_code != 200:
            logger.error(f"wa {r.status_code}: {r.text[:200]}")
        return r.status_code == 200
    except Exception as e:
        logger.error(f"wa send: {e}")
        return False


async def wa_text(to, text: str) -> bool:
    ok = True
    for part in split_message(text, 4000):   # découpe au lieu de tronquer
        ok = await wa_send({"messaging_product": "whatsapp", "to": str(to), "type": "text",
                            "text": {"body": part, "preview_url": True}}) and ok
    return ok


async def wa_menu(to, title: str, options: list) -> bool:
    opts = [(l[:20], a) for (l, a) in options][:10]
    # Corps d'un message interactif WhatsApp : 1024 car. max. Avant : coupé à 1000 (récap amputé).
    # Désormais : le début part en texte normal, la dernière partie porte les boutons.
    head, title = split_head_tail(title or "Menu", 1000)
    if head:
        await wa_text(to, head)
    if len(opts) <= 3:
        inter = {"type": "button", "body": {"text": title},
                 "action": {"buttons": [{"type": "reply", "reply": {"id": a[:200], "title": l}} for (l, a) in opts]}}
    else:
        inter = {"type": "list", "body": {"text": title},
                 "action": {"button": "Choisir", "sections": [{"title": "Options",
                            "rows": [{"id": a[:200], "title": l} for (l, a) in opts]}]}}
    return await wa_send({"messaging_product": "whatsapp", "to": str(to), "type": "interactive", "interactive": inter})


async def wa_document(to, filename, data, caption: str = "") -> bool:
    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_ID):
        return False
    try:
        _mt = _mime_for(filename)
        up = await http().post(f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/media",
                               headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
                               data={"messaging_product": "whatsapp", "type": _mt},
                               files={"file": (filename, data, _mt)}, timeout=45.0)
        if up.status_code != 200:
            logger.error(f"wa media {up.status_code}: {up.text[:200]}")
            return False
        mid = up.json().get("id")
        return await wa_send({"messaging_product": "whatsapp", "to": str(to), "type": "document",
                              "document": {"id": mid, "filename": filename, "caption": (caption or "")[:900]}})
    except Exception as e:
        logger.error(f"wa doc: {e}")
        return False


async def wa_get_media(media_id) -> Optional[bytes]:
    if not WHATSAPP_TOKEN:
        return None
    try:
        cli = http()
        meta = await cli.get(f"https://graph.facebook.com/v21.0/{media_id}",
                             headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}, timeout=30.0)
        url = meta.json().get("url")
        if not url:
            return None
        r = await cli.get(url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}, timeout=30.0)
        return r.content if r.status_code == 200 else None
    except Exception as e:
        logger.error(f"wa get_media: {e}")
        return None


# ─────────────────────── Messenger (Facebook Page) ───────────────────────
async def fb_send(payload: dict) -> bool:
    if not MESSENGER_TOKEN:
        return False
    try:
        r = await http().post("https://graph.facebook.com/v21.0/me/messages",
                              params={"access_token": MESSENGER_TOKEN}, json=payload, timeout=25.0)
        if r.status_code != 200:
            logger.error(f"fb {r.status_code}: {r.text[:200]}")
        return r.status_code == 200
    except Exception as e:
        logger.error(f"fb send: {e}")
        return False


async def fb_text(to, text: str) -> bool:
    # Messenger : 2000 car. max par message -> on DÉCOUPE (avant : tronqué à 1900, fin de message perdue).
    ok = True
    for part in split_message(text, 1900):
        ok = await fb_send({"recipient": {"id": str(to)}, "message": {"text": part}}) and ok
    return ok


async def fb_menu(to, text: str, options: list) -> bool:
    qrs = [{"content_type": "text", "title": l[:20], "payload": a[:900]} for (l, a) in options[:13]]
    # Avant : texte coupé à 640 car. -> récap CV amputé (« Ces informations sont-elles correctes » / « Ce »).
    # Désormais : le corps long part en messages normaux, la DERNIÈRE partie porte les boutons.
    head, tail = split_head_tail(text or "Menu", 1900)
    if head:
        await fb_text(to, head)
    return await fb_send({"recipient": {"id": str(to)}, "message": {"text": tail, "quick_replies": qrs}})


async def fb_document(to, filename, data, caption: str = "") -> bool:
    if not MESSENGER_TOKEN:
        return False
    try:
        if caption:
            await fb_text(to, caption)
        r = await http().post("https://graph.facebook.com/v21.0/me/messages", params={"access_token": MESSENGER_TOKEN},
                              data={"recipient": json.dumps({"id": str(to)}),
                                    "message": json.dumps({"attachment": {"type": "file", "payload": {"is_reusable": False}}})},
                              files={"filedata": (filename, data, _mime_for(filename))}, timeout=45.0)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"fb doc: {e}")
        return False
