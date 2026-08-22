"""Client HTTP partagé (pool keep-alive) pour tous les appels sortants — LLM, Tavily,
Telegram, WhatsApp, Messenger, sources. Extrait de main.py (PR-B du refactor).

Un seul httpx.AsyncClient réutilisé : évite le handshake TCP/TLS à chaque requête.
Timeout passé par requête (le default sert de garde-fou)."""
from __future__ import annotations
from typing import Optional
import httpx

_http_client: Optional[httpx.AsyncClient] = None


def http() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
    return _http_client


async def shutdown_http() -> None:
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
