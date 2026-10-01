"""Telegram'a düz metin gönderir. Ayarlar .env'den: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID."""
from __future__ import annotations

from typing import Any

import httpx

from harman.config import setting


def send(text: str, *, client: Any = None) -> bool:
    token, chat = setting("TELEGRAM_BOT_TOKEN"), setting("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    try:
        http = client or httpx.Client(timeout=15)
        resp = http.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True})
        return resp.status_code == 200 and bool(resp.json().get("ok"))
    except Exception:
        return False
