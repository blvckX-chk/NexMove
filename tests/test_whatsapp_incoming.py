"""Tests du parsing des messages entrants WhatsApp (routeur _extract_incoming)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))

import main   # noqa: E402


def test_wa_incoming_text():
    t, cb, d = main._extract_incoming("whatsapp", {"type": "text", "text": {"body": "salut"}})
    assert t == "salut" and cb is None and d is None


def test_wa_incoming_document_pdf():
    raw = {"type": "document", "document": {"id": "DOC1", "filename": "CV.pdf"}}
    t, cb, d = main._extract_incoming("whatsapp", raw)
    assert d and d["id"] == "DOC1" and d["filename"] == "CV.pdf"


def test_wa_incoming_image_jpeg():
    """WhatsApp envoie image.id — on doit générer un filename image (routé vers vision Gemini)."""
    raw = {"type": "image", "image": {"id": "IMG1", "mime_type": "image/jpeg"}}
    t, cb, d = main._extract_incoming("whatsapp", raw)
    assert d and d["id"] == "IMG1" and d["filename"] == "cv.jpg"


def test_wa_incoming_image_png():
    raw = {"type": "image", "image": {"id": "IMG2", "mime_type": "image/png"}}
    t, cb, d = main._extract_incoming("whatsapp", raw)
    assert d and d["filename"] == "cv.png"


def test_wa_incoming_button_reply():
    raw = {"type": "interactive", "interactive": {"button_reply": {"id": "act:veille"}}}
    t, cb, d = main._extract_incoming("whatsapp", raw)
    assert cb == "act:veille"


def test_wa_incoming_list_reply():
    raw = {"type": "interactive", "interactive": {"list_reply": {"id": "m:cf"}}}
    t, cb, d = main._extract_incoming("whatsapp", raw)
    assert cb == "m:cf"


def test_wa_incoming_button_template():
    raw = {"type": "button", "button": {"payload": "act:aide"}}
    t, cb, d = main._extract_incoming("whatsapp", raw)
    assert cb == "act:aide"


def test_wa_incoming_audio_poliment_rejete():
    t, cb, d = main._extract_incoming("whatsapp", {"type": "audio"})
    assert t == "__wa_unsupported__"


def test_wa_incoming_video_poliment_rejete():
    t, cb, d = main._extract_incoming("whatsapp", {"type": "video"})
    assert t == "__wa_unsupported__"


def test_wa_incoming_sticker_poliment_rejete():
    t, cb, d = main._extract_incoming("whatsapp", {"type": "sticker"})
    assert t == "__wa_unsupported__"
