"""Yollar ve .env okuma (yalnız iki ayar gerekir: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LOGS = ROOT / "logs"
DB = DATA / "harman.db"
CODEX_VERSION = "0.160.0"
CODEX_EXE = ROOT / "tools" / f"codex-{CODEX_VERSION}" / "node_modules" / "@openai" / "codex-win32-x64" / "vendor" / \
    "x86_64-pc-windows-msvc" / "bin" / "codex.exe"


def load_env(path: Path | None = None) -> dict[str, str]:
    """Basit .env okuyucu: ANAHTAR=deger satırları; # yorum; tırnaklar soyulur. Ortam değişkeni önceliklidir."""
    values: dict[str, str] = {}
    path = path or ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key in list(values):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def setting(name: str, default: str = "") -> str:
    return os.environ.get(name) or load_env().get(name, default)
