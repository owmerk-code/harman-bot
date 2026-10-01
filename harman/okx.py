"""OKX herkese açık API (anahtar gerekmez): kopya trader listesi, pozisyonlar, fiyat ve mumlar.

Yalnız OKUR. Hız sınırına saygı için her istek arasında kısa bekleme ve geçici hatalarda yeniden deneme var.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

BASE = "https://www.okx.com"


class OkxError(RuntimeError):
    pass


class Okx:
    def __init__(self, *, client: Any = None, pause: float = 0.25, retries: int = 3) -> None:
        self.client = client or httpx.Client(timeout=20, headers={"User-Agent": "harman-bot/1"})
        self.pause = pause
        self.retries = retries

    def _get(self, path: str, params: dict[str, str]) -> list[Any]:
        last = "?"
        for attempt in range(self.retries):
            try:
                body = self.client.get(BASE + path, params=params).json()
            except Exception as exc:  # ağ hatası: kısa bekle, tekrar dene
                last = type(exc).__name__
                time.sleep(1.5 * (attempt + 1))
                continue
            code = str(body.get("code"))
            if code == "0":
                time.sleep(self.pause)
                return body.get("data") or []
            last = f"{code} {body.get('msg', '')}"
            if code in ("50011", "50013"):  # hız sınırı / sistem meşgul
                time.sleep(2.0 * (attempt + 1))
                continue
            break
        raise OkxError(f"{path}: {last}")

    def lead_traders(self) -> list[dict[str, Any]]:
        out, page = [], 1
        while True:
            data = self._get("/api/v5/copytrading/public-lead-traders",
                             {"instType": "SWAP", "sortType": "overview", "limit": "20", "page": str(page)})
            block = data[0] if data else {}
            ranks = block.get("ranks") or []
            out += ranks
            if not ranks or page >= int(block.get("totalPage") or 1):
                return out
            page += 1

    def history(self, code: str, *, max_pages: int = 20) -> list[dict[str, Any]]:
        out, after = [], None
        for _ in range(max_pages):
            params = {"instType": "SWAP", "uniqueCode": code, "limit": "100"}
            if after:
                params["after"] = after
            data = self._get("/api/v5/copytrading/public-subpositions-history", params)
            out += data
            if len(data) < 100:
                break
            after = data[-1]["subPosId"]
        return out

    def positions(self, code: str) -> list[dict[str, Any]]:
        return self._get("/api/v5/copytrading/public-current-subpositions", {"instType": "SWAP", "uniqueCode": code})

    def tickers(self) -> dict[str, dict[str, Any]]:
        return {row["instId"]: row for row in self._get("/api/v5/market/tickers", {"instType": "SWAP"})}

    def candles(self, inst: str, bar: str = "1H", limit: int = 100) -> list[dict[str, float]]:
        """Eskiden yeniye sıralı mumlar: ts (açılış ms), o, h, l, c. Yalnız kapanmış mumlar."""
        rows = self._get("/api/v5/market/candles", {"instId": inst, "bar": bar, "limit": str(limit)})
        out = [{"ts": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4])}
               for r in rows if len(r) > 8 and r[8] == "1"]
        return sorted(out, key=lambda c: c["ts"])


def side_of(row: dict[str, Any]) -> int:
    side = row.get("posSide")
    if side == "long":
        return 1
    if side == "short":
        return -1
    return 1 if float(row.get("subPos") or 0) > 0 else -1


def usd_volume(ticker: dict[str, Any]) -> float:
    """SWAP için volCcy24h taban para birimi cinsindendir; son fiyatla USD'ye çevrilir."""
    try:
        return float(ticker.get("volCcy24h") or 0) * float(ticker.get("last") or 0)
    except (TypeError, ValueError):
        return 0.0
