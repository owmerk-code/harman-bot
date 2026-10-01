"""Trader eleme (kurallar). Eşikler protokolde SONUÇ GÖRÜLMEDEN yazıldı; burada ve testte aynı değerler.

1 Ekim 2026 araştırmasından gelen dersler:
* Liderlerin ortanca kaldıracı 10x, işlemlerin %18'i 50x+ -> yüksek kaldıraçlılar elenir.
* Zararı kapatmayıp AÇIK tutma eğilimi var (2.152 açık pozisyonun %24'ü marjının yarısından fazlasını kaybetmiş)
  -> başarı ölçüsü kapanmış + açık işlemler BİRLİKTE hesaplanır; zararı uzun süre açık tutan elenir.
* 1 saatten kısa işlemlerde avantaj ~0 ve kopya gecikmesi bunu da siler -> kısa vadeli işlemciler elenir.
"""
from __future__ import annotations

import statistics as st
from dataclasses import dataclass, field
from math import sqrt
from typing import Any

from harman.okx import side_of

MIN_LEAD_DAYS = 180
MIN_TRADES = 30
MAX_MEDIAN_LEVER = 20.0
MAX_HIGH_LEVER_SHARE = 0.10   # 50x ve üstü işlemlerin payı
HIGH_LEVER = 50.0
MIN_MEDIAN_HOLD_H = 1.0
MIN_WIN_RATE = 0.52
MAX_DEEP_LOSER_SHARE = 0.25   # açık pozisyonların marjının %50+'sini kaybedenlerin payı
ACTIVE_DAYS = 14
TRIM = 0.05
COST = 0.0015                 # gidiş-dönüş komisyon + kayma (1x getiri üzerinden)
TOP_N = 20
MAX_HIDDEN_SHARE = 0.20      # acik pozisyonlarinin en fazla %20'si gizli olabilir (goremedigimizi kopyalayamayiz)


@dataclass
class Verdict:
    code: str
    nick: str
    ok: bool
    reasons: list[str] = field(default_factory=list)
    score: float = 0.0
    stats: dict[str, float] = field(default_factory=dict)


def trimmed_mean(values: list[float], trim: float = TRIM) -> float:
    v = sorted(values)
    k = int(len(v) * trim)
    core = v[k:len(v) - k] if k and len(v) > 2 * k else v
    return st.mean(core) if core else 0.0


def evaluate(trader: dict[str, Any], history: list[dict[str, Any]], open_rows: list[dict[str, Any]],
             *, now_ms: int) -> Verdict:
    v = Verdict(code=str(trader.get("uniqueCode")), nick=str(trader.get("nickName") or "?"), ok=False)
    closed = []
    for r in history:
        try:
            o, c = float(r["openAvgPx"]), float(r["closeAvgPx"])
            if o > 0 and c > 0:
                closed.append({"ret": (c / o - 1) * side_of(r) - COST, "lev": float(r.get("lever") or 0),
                               "hold_h": (int(r["closeTime"]) - int(r["openTime"])) / 3.6e6,
                               "close_ms": int(r["closeTime"])})
        except (KeyError, TypeError, ValueError):
            continue
    opens = []
    for p in open_rows:
        try:
            o, m = float(p["openAvgPx"]), float(p["markPx"])
            if o > 0 and m > 0:
                opens.append({"ret": (m / o - 1) * side_of(p) - COST, "upl": float(p.get("uplRatio") or 0)})
        except (KeyError, TypeError, ValueError):
            continue

    hidden = sum(1 for p in open_rows if not p.get("instId"))
    lead_days = int(trader.get("leadDays") or 0)
    rets = [x["ret"] for x in closed] + [x["ret"] for x in opens]
    levs = sorted(x["lev"] for x in closed)
    holds = sorted(x["hold_h"] for x in closed)
    stats = {
        "lead_days": lead_days, "trades": len(closed), "open": len(opens),
        "median_lever": levs[len(levs) // 2] if levs else 0.0,
        "high_lever_share": sum(lv >= HIGH_LEVER for lv in levs) / len(levs) if levs else 0.0,
        "median_hold_h": holds[len(holds) // 2] if holds else 0.0,
        "win_rate": sum(x > 0 for x in rets) / len(rets) if rets else 0.0,
        "trimmed_mean_pct": trimmed_mean(rets) * 100 if rets else 0.0,
        "deep_loser_share": sum(x["upl"] <= -0.5 for x in opens) / len(opens) if opens else 0.0,
        "days_since_trade": (now_ms - max(x["close_ms"] for x in closed)) / 8.64e7 if closed else 999.0,
        "hidden_share": hidden / len(open_rows) if open_rows else 0.0,
    }
    v.stats = {k: round(float(val), 4) for k, val in stats.items()}

    checks = [
        (lead_days >= MIN_LEAD_DAYS, f"{lead_days} gun deneyim (<{MIN_LEAD_DAYS})"),
        (len(closed) >= MIN_TRADES, f"{len(closed)} islem (<{MIN_TRADES})"),
        (stats["median_lever"] <= MAX_MEDIAN_LEVER, f"ortanca kaldirac {stats['median_lever']:.0f}x (>{MAX_MEDIAN_LEVER:.0f}x)"),
        (stats["high_lever_share"] <= MAX_HIGH_LEVER_SHARE, f"islemlerin %{stats['high_lever_share']*100:.0f}'i 50x+"),
        (stats["median_hold_h"] >= MIN_MEDIAN_HOLD_H, f"ortanca tutma {stats['median_hold_h']:.1f} saat (cok kisa)"),
        (stats["win_rate"] >= MIN_WIN_RATE, f"kazanma %{stats['win_rate']*100:.0f} (<%{MIN_WIN_RATE*100:.0f})"),
        (stats["trimmed_mean_pct"] > 0, f"acik+kapali islem ortalamasi {stats['trimmed_mean_pct']:+.2f}% (<=0)"),
        (stats["deep_loser_share"] <= MAX_DEEP_LOSER_SHARE,
         f"acik pozisyonlarin %{stats['deep_loser_share']*100:.0f}'i derin zararda (zarari acik tutuyor)"),
        (stats["days_since_trade"] <= ACTIVE_DAYS, f"{stats['days_since_trade']:.0f} gundur islem yok"),
        (stats["hidden_share"] <= MAX_HIDDEN_SHARE, f"acik pozisyonlarinin %{stats['hidden_share']*100:.0f}'i gizli"),
    ]
    v.reasons = [why for passed, why in checks if not passed]
    v.ok = not v.reasons
    v.score = stats["trimmed_mean_pct"] * sqrt(len(rets)) if v.ok else 0.0
    return v


def select(verdicts: list[Verdict], top_n: int = TOP_N) -> list[Verdict]:
    return sorted((v for v in verdicts if v.ok), key=lambda v: -v.score)[:top_n]
