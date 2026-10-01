"""Kağıt-para defteri ve SERT risk kuralları (AI bunları değiştiremez).

* İşlem başına özsermayenin %1'i riske edilir; tutar = risk / stop mesafesi.
* Tek pozisyon en fazla özsermayenin %50'si; toplam açık tutar en fazla 2x; en fazla 5 açık pozisyon;
  toplam açık risk en fazla %5.
* Gün içinde -%3 -> o gün yeni giriş yok. Zirveden -%15 -> hesap durur (yeni giriş yok, çıkışlar sürer).
* Stop zorunlu: 2 x ATR(14, 1 saat), %1,5-%8 arası. Kâr-al = 2 x stop mesafesi. En uzun tutma 72 saat.
* Maliyet: taraf başı %0,05 komisyon + %0,05 kayma (fiyata işlenir). Rapor 'sert' görünümü ek %0,2 düşer.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from harman.store import Store

CAPITAL = 2000.0
RISK_PCT = 0.01
MAX_POS_NOTIONAL = 0.50
MAX_GROSS = 2.0
MAX_POSITIONS = 5
MAX_OPEN_RISK = 0.05
DAY_LOSS = 0.03
MAX_DRAWDOWN = 0.15
FEE = 0.0005
SLIP = 0.0005
STOP_ATR_MULT = 2.0
STOP_MIN, STOP_MAX = 0.015, 0.08
TP_R = 2.0
MAX_HOLD_H = 72
MIN_NOTIONAL = 10.0
SEVERE_EXTRA = 0.002


def atr_stop_pct(candles: list[dict[str, float]]) -> float:
    if len(candles) < 15:
        return STOP_MAX
    trs = []
    for prev, cur in zip(candles[-15:-1], candles[-14:]):
        trs.append(max(cur["h"] - cur["l"], abs(cur["h"] - prev["c"]), abs(cur["l"] - prev["c"])))
    atr = sum(trs) / len(trs)
    return min(STOP_MAX, max(STOP_MIN, STOP_ATR_MULT * atr / candles[-1]["c"]))


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


class Ledger:
    def __init__(self, name: str, store: Store, capital: float = CAPITAL) -> None:
        self.name, self.store, self.capital = name, store, capital

    # --- değerleme ---
    def realized(self) -> float:
        row = self.store.db.execute("SELECT COALESCE(SUM(pnl),0) s FROM positions WHERE ledger=? AND status='closed'",
                                    (self.name,)).fetchone()
        return float(row["s"])

    def unrealized(self, prices: dict[str, float]) -> float:
        total = 0.0
        for p in self.store.open_positions(self.name):
            mark = prices.get(p["inst"], p["entry_px"])
            total += (mark - p["entry_px"]) * p["qty"] * p["side"] - p["fees"]
        return total

    def equity(self, prices: dict[str, float]) -> float:
        return self.capital + self.realized() + self.unrealized(prices)

    def mark(self, prices: dict[str, float], now_ms: int) -> float:
        eq = self.equity(prices)
        peak = max(self.store.get(f"{self.name}:peak", self.capital), eq)
        self.store.put(f"{self.name}:peak", peak)
        day = self.store.get(f"{self.name}:day")
        if not day or day["date"] != _day(now_ms):
            self.store.put(f"{self.name}:day", {"date": _day(now_ms), "start": eq})
        if eq <= peak * (1 - MAX_DRAWDOWN) and not self.store.get(f"{self.name}:halted"):
            self.store.put(f"{self.name}:halted", True)
            self.store.log(now_ms, "durdu", f"zirveden -%{MAX_DRAWDOWN*100:.0f}: yeni giris kapali", self.name)
        self.store.record_equity(self.name, now_ms, round(eq, 4))
        return eq

    # --- giriş ---
    def why_not(self, inst: str, prices: dict[str, float], now_ms: int) -> str | None:
        if self.store.get(f"{self.name}:halted"):
            return "hesap durdu (zirveden -%15)"
        eq = self.equity(prices)
        day = self.store.get(f"{self.name}:day") or {"start": eq}
        if eq <= day["start"] * (1 - DAY_LOSS):
            return "gunluk kayip freni (-%3)"
        opens = self.store.open_positions(self.name)
        if len(opens) >= MAX_POSITIONS:
            return "en fazla 5 acik pozisyon"
        if any(p["inst"] == inst for p in opens):
            return "bu coinde zaten pozisyon var"
        risk = sum(abs(p["entry_px"] - p["stop_px"]) * p["qty"] for p in opens)
        if risk >= eq * MAX_OPEN_RISK:
            return "toplam acik risk %5 dolu"
        if sum(p["entry_px"] * p["qty"] for p in opens) >= eq * MAX_GROSS - MIN_NOTIONAL:
            return "toplam tutar 2x siniri dolu"
        return None

    def open(self, *, inst: str, side: int, price: float, stop_pct: float, backers: list[str], now_ms: int,
             size_factor: float = 1.0, note: str = "") -> int | None:
        prices = {inst: price}
        for p in self.store.open_positions(self.name):
            prices.setdefault(p["inst"], p["entry_px"])
        eq = self.equity(prices)
        opens = self.store.open_positions(self.name)
        gross = sum(p["entry_px"] * p["qty"] for p in opens)
        risk_left = eq * MAX_OPEN_RISK - sum(abs(p["entry_px"] - p["stop_px"]) * p["qty"] for p in opens)
        risk_usd = min(eq * RISK_PCT * max(0.0, min(1.0, size_factor)), risk_left)
        notional = min(risk_usd / stop_pct, eq * MAX_POS_NOTIONAL, eq * MAX_GROSS - gross)
        if notional < MIN_NOTIONAL:
            return None
        entry = price * (1 + side * SLIP)
        qty = notional / entry
        return self.store.insert_position(
            ledger=self.name, inst=inst, side=side, qty=qty, entry_px=entry, entry_ms=now_ms,
            stop_px=entry * (1 - side * stop_pct), tp_px=entry * (1 + side * TP_R * stop_pct),
            backers=json.dumps(backers), fees=notional * FEE, note=note[:500])

    # --- çıkış ---
    def close(self, pos: Any, *, price: float, now_ms: int, reason: str) -> float:
        exit_px = price * (1 - pos["side"] * SLIP)
        fees = pos["fees"] + exit_px * pos["qty"] * FEE
        pnl = (exit_px - pos["entry_px"]) * pos["qty"] * pos["side"] - fees
        self.store.close_position(pos["id"], exit_px=exit_px, exit_ms=now_ms, reason=reason, fees=fees, pnl=pnl)
        return pnl

    def check_stops(self, pos: Any, candles: list[dict[str, float]]) -> tuple[float, int, str] | None:
        """Girişten sonraki 15 dk mumlarında stop/kâr-al. Aynı mumda ikisi de varsa STOP sayılır (temkinli)."""
        for c in candles:
            if c["ts"] + 900_000 <= pos["entry_ms"]:
                continue
            if pos["side"] > 0:
                if c["l"] <= pos["stop_px"]:
                    return min(pos["stop_px"], c["o"]), c["ts"] + 900_000, "stop"
                if c["h"] >= pos["tp_px"]:
                    return pos["tp_px"], c["ts"] + 900_000, "kar-al"
            else:
                if c["h"] >= pos["stop_px"]:
                    return max(pos["stop_px"], c["o"]), c["ts"] + 900_000, "stop"
                if c["l"] <= pos["tp_px"]:
                    return pos["tp_px"], c["ts"] + 900_000, "kar-al"
        return None
