"""Tests unitaires du module channels.py — sans réseau."""
import os, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))
os.environ.setdefault("TELEGRAM_TOKEN", "")
os.environ.setdefault("WHATSAPP_TOKEN", "")
os.environ.setdefault("MESSENGER_TOKEN", "")

import channels  # noqa: E402


# ------------------ MIME helper ------------------
def test_mime_pdf():
    assert channels._mime_for("cv.pdf") == "application/pdf"
    assert channels._mime_for("CV_ABC.PDF") == "application/pdf"


def test_mime_docx():
    assert channels._mime_for("cv.docx").endswith("wordprocessingml.document")


def test_mime_default():
    assert channels._mime_for("truc.xyz") == "application/octet-stream"
    assert channels._mime_for("") == "application/octet-stream"


# ------------------ Telegram inline keyboard ------------------
def test_tg_keyboard_2_par_ligne():
    kb = channels._tg_keyboard([("A", "act:a"), ("B", "act:b"), ("C", "act:c"), ("D", "act:d")])
    assert "inline_keyboard" in kb
    rows = kb["inline_keyboard"]
    assert len(rows) == 2 and len(rows[0]) == 2 and len(rows[1]) == 2
    assert rows[0][0]["text"] == "A" and rows[0][0]["callback_data"] == "act:a"


def test_tg_keyboard_impair():
    kb = channels._tg_keyboard([("A", "act:a"), ("B", "act:b"), ("C", "act:c")])
    rows = kb["inline_keyboard"]
    assert len(rows) == 2 and len(rows[1]) == 1
    assert rows[1][0]["text"] == "C"


def test_tg_keyboard_vide():
    kb = channels._tg_keyboard([])
    assert kb["inline_keyboard"] == []


# ------------------ Garde-fous sans token ------------------
import asyncio


def test_tg_sans_token():
    channels.TELEGRAM_TOKEN = ""   # patch local
    ok = asyncio.run(channels._tg("sendMessage", {}))
    assert ok is False


def test_wa_send_sans_config():
    channels.WHATSAPP_TOKEN = ""
    channels.WHATSAPP_PHONE_ID = ""
    ok = asyncio.run(channels.wa_send({}))
    assert ok is False


def test_fb_send_sans_token():
    channels.MESSENGER_TOKEN = ""
    ok = asyncio.run(channels.fb_send({}))
    assert ok is False


def test_wa_get_media_sans_token():
    channels.WHATSAPP_TOKEN = ""
    res = asyncio.run(channels.wa_get_media("media123"))
    assert res is None
