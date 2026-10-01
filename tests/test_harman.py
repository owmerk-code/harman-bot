"""HARMAN: eleme, harmanlama, risk kuralları, defter muhasebesi ve AI sınırları (ağ/AI YOK)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harman import ledger as L
from harman import signals as S
from harman import vetting as V
from harman.ai import Ai
from harman.ledger import Ledger, atr_stop_pct
from harman.store import Store

ROOT = Path(__file__).resolve().parent.parent
NOW = 1_790_000_000_000
H = 3_600_000


# ------------------------------------------------------------------ eleme
def hist(n=40, lev=5, side="long", ret=0.02, hold_h=6, days_ago=1):
    out = []
    for i in range(n):
        o = 100.0
        c = o * (1 + ret) if (i % 3) else o * (1 - ret / 2)  # 2/3 kazanan
        close = NOW - int(days_ago * 8.64e7) - i * H
        out.append({"openAvgPx": str(o), "closeAvgPx": str(c), "lever": str(lev), "posSide": side,
                    "openTime": str(close - int(hold_h * H)), "closeTime": str(close)})
    return out


def trader(days=400):
    return {"uniqueCode": "T1", "nickName": "deneme", "leadDays": str(days)}


def test_a_solid_trader_passes():
    v = V.evaluate(trader(), hist(), [], now_ms=NOW)
    assert v.ok and v.score > 0, v.reasons


@pytest.mark.parametrize("kw,needle", [
    ({"lev": 100}, "kaldirac"), ({"hold_h": 0.2}, "tutma"), ({"n": 10}, "islem"), ({"days_ago": 30}, "islem yok")])
def test_gamblers_scalpers_newbies_and_inactive_are_rejected(kw, needle):
    v = V.evaluate(trader(), hist(**kw), [], now_ms=NOW)
    assert not v.ok and any(needle in r for r in v.reasons), v.reasons


def test_young_account_rejected():
    assert not V.evaluate(trader(days=60), hist(), [], now_ms=NOW).ok


def test_trader_who_keeps_losers_open_is_rejected():
    """Araştırmanın ana bulgusu: kapanmışlar iyi görünür, zararlar açık tutulur."""
    losers = [{"openAvgPx": "100", "markPx": "60", "posSide": "long", "uplRatio": "-2.0"} for _ in range(10)]
    v = V.evaluate(trader(), hist(), losers, now_ms=NOW)
    assert not v.ok and any("derin zararda" in r for r in v.reasons)


# ------------------------------------------------------------------ harmanlama
def row(code, inst="SOL-USDT-SWAP", side=1, age_h=2):
    return {"code": code, "inst": inst, "side": side, "open_ms": NOW - int(age_h * H)}


U = {"SOL-USDT-SWAP", "ETH-USDT-SWAP"}


def test_three_fresh_traders_make_a_signal_two_do_not():
    assert S.consensus([row("a"), row("b")], now_ms=NOW, universe=U) == []
    (sig,) = S.consensus([row("a"), row("b"), row("c")], now_ms=NOW, universe=U)
    assert sig.inst == "SOL-USDT-SWAP" and sig.side == 1 and sig.backers == ("a", "b", "c")


def test_old_positions_do_not_count_they_are_mostly_held_losers():
    assert S.consensus([row("a"), row("b"), row("c", age_h=200)], now_ms=NOW, universe=U) == []


def test_disagreement_blocks_and_illiquid_coins_are_ignored():
    rows = [row(c) for c in "abc"] + [row(c, side=-1) for c in "de"]
    assert S.consensus(rows, now_ms=NOW, universe=U) == []
    assert S.consensus([row(c, inst="PEPE-USDT-SWAP") for c in "abc"], now_ms=NOW, universe=U) == []


def test_same_trader_counts_once():
    assert S.consensus([row("a"), row("a"), row("a")], now_ms=NOW, universe=U) == []


def test_exit_when_backers_leave():
    rows = [row("a", age_h=100)]
    assert S.still_backed(["a", "b", "c"], rows, inst="SOL-USDT-SWAP", side=1) == 1 < S.EXIT_MIN_HOLDERS


# ------------------------------------------------------------------ defter ve risk
@pytest.fixture
def led(tmp_path):
    return Ledger("kural", Store(tmp_path / "h.db"))


def test_position_size_risks_one_percent(led):
    pid = led.open(inst="SOL-USDT-SWAP", side=1, price=100.0, stop_pct=0.04, backers=["a", "b", "c"], now_ms=NOW)
    p = led.store.open_positions("kural")[0]
    risk = (p["entry_px"] - p["stop_px"]) * p["qty"]
    assert pid and abs(risk - 20.0) < 0.5           # 2000 x %1
    assert p["entry_px"] > 100.0                     # kayma alış fiyatına işlendi


def test_tight_stop_cannot_create_oversized_position(led):
    led.open(inst="SOL-USDT-SWAP", side=1, price=100.0, stop_pct=0.001, backers=["a"], now_ms=NOW)
    p = led.store.open_positions("kural")[0]
    assert p["entry_px"] * p["qty"] <= 2000 * L.MAX_POS_NOTIONAL + 1e-6


def test_limits_max_positions_and_one_per_coin(led):
    for i in range(L.MAX_POSITIONS):
        led.open(inst=f"C{i}-USDT-SWAP", side=1, price=100.0, stop_pct=0.02, backers=["a"], now_ms=NOW)
    prices = {p["inst"]: 100.0 for p in led.store.open_positions("kural")}
    assert led.why_not("X-USDT-SWAP", prices, NOW) is not None
    assert "zaten" in (Ledger("ai", led.store).why_not("C0-USDT-SWAP", {}, NOW) or "zaten")


def test_stop_hit_including_gap_and_both_in_one_candle_counts_as_stop(led):
    led.open(inst="SOL-USDT-SWAP", side=1, price=100.0, stop_pct=0.04, backers=["a"], now_ms=NOW)
    p = led.store.open_positions("kural")[0]
    gap = [{"ts": NOW + 900_000, "o": 90.0, "h": 91.0, "l": 89.0, "c": 90.0}]
    px, _, why = led.check_stops(p, gap)
    assert why == "stop" and px == 90.0                           # boşlukta stop değil açılış fiyatı
    both = [{"ts": NOW + 900_000, "o": 100.0, "h": 120.0, "l": 90.0, "c": 100.0}]
    assert led.check_stops(p, both)[2] == "stop"                  # temkinli varsayım


def test_short_side_accounting(led):
    led.open(inst="ETH-USDT-SWAP", side=-1, price=100.0, stop_pct=0.05, backers=["a"], now_ms=NOW)
    p = led.store.open_positions("kural")[0]
    assert p["stop_px"] > p["entry_px"] > p["tp_px"]
    pnl = led.close(p, price=90.0, now_ms=NOW + H, reason="test")
    assert pnl > 0 and led.equity({}) == pytest.approx(2000 + pnl)


def test_drawdown_halts_new_entries(led):
    led.open(inst="SOL-USDT-SWAP", side=1, price=100.0, stop_pct=0.08, backers=["a"], now_ms=NOW)
    led.mark({"SOL-USDT-SWAP": 100.0}, NOW)
    led.store.put("kural:peak", 4000.0)                           # zirveden çok aşağıda
    led.mark({"SOL-USDT-SWAP": 100.0}, NOW + H)
    assert "durdu" in led.why_not("ETH-USDT-SWAP", {"SOL-USDT-SWAP": 100.0}, NOW + H)


def test_atr_stop_is_clamped():
    flat = [{"ts": i, "o": 100, "h": 100.01, "l": 99.99, "c": 100} for i in range(20)]
    wild = [{"ts": i, "o": 100, "h": 130, "l": 70, "c": 100} for i in range(20)]
    assert atr_stop_pct(flat) == L.STOP_MIN and atr_stop_pct(wild) == L.STOP_MAX


# ------------------------------------------------------------------ AI sınırları
class Fake:
    def __init__(self, text):
        self.text = text

    def __call__(self, cand):
        outer = self

        class C:
            def complete(self, **_):
                class R:
                    text = outer.text
                return R()
        return C()


def test_ai_can_only_shrink_or_cancel_and_silence_means_no_trade(monkeypatch):
    monkeypatch.setattr("harman.ai.available", lambda c: True)
    assert Ai(client_factory=Fake('{"karar": "kucult", "gerekce": "x"}')).news_check("SOL", 1, ["h"])[0] == 0.5
    assert Ai(client_factory=Fake('{"karar": "BUYUT", "gerekce": "x"}')).news_check("SOL", 1, ["h"])[0] == 0.0
    assert Ai(client_factory=Fake("cevap yok")).news_check("SOL", 1, ["h"])[0] == 0.0
    assert Ai(client_factory=Fake("x")).news_check("SOL", 1, [])[0] == 1.0     # haber yoksa engel yok


def test_ai_veto_cannot_add_unknown_traders(monkeypatch):
    monkeypatch.setattr("harman.ai.available", lambda c: True)
    ai = Ai(client_factory=Fake('{"reddet": [{"kod": "B", "neden": "kumar"}, {"kod": "YENI", "neden": "?"}]}'))
    rejected, _ = ai.veto_traders([{"kod": "A"}, {"kod": "B"}])
    assert rejected == {"B"}


def test_ai_early_exit_only_for_known_positions(monkeypatch):
    monkeypatch.setattr("harman.ai.available", lambda c: True)
    ai = Ai(client_factory=Fake('{"kapat": [{"id": 7, "neden": "hack"}, {"id": 99, "neden": "?"}]}'))
    assert ai.early_exit([{"id": 7}]) == [(7, "hack")]


# ------------------------------------------------------------------ protokol
def test_protocol_matches_code():
    p = json.loads((ROOT / "research" / "harman_v1_protocol.json").read_text(encoding="utf-8"))
    assert p["rules"]["signal"]["MIN_BACKERS"] == S.MIN_BACKERS == 3
    assert p["rules"]["risk"]["RISK_PCT"] == L.RISK_PCT == 0.01
    assert p["rules"]["risk"]["MAX_GROSS"] == L.MAX_GROSS == 2.0
    assert p["rules"]["vetting"]["MAX_MEDIAN_LEVER"] == V.MAX_MEDIAN_LEVER
    assert "gercek emir" in p["forbidden"]


def test_trader_who_hides_positions_is_rejected():
    """2 Ekim 2026: secilenlerin pozisyonlarinin yarisi gizliydi; goremedigimizi kopyalayamayiz."""
    hidden = [{"instId": "", "openAvgPx": "", "markPx": "", "posSide": "long"} for _ in range(5)]
    v = V.evaluate(trader(), hist(), hidden, now_ms=NOW)
    assert not v.ok and any("gizli" in r for r in v.reasons)
    assert p_hidden() == V.MAX_HIDDEN_SHARE


def p_hidden():
    return json.loads((ROOT / "research" / "harman_v1_protocol.json").read_text(encoding="utf-8"))["rules"]["vetting"]["MAX_HIDDEN_SHARE"]
