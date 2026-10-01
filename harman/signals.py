"""Harmanlama: seçilmiş trader'ların TAZE pozisyonlarından ortak karar.

* Yalnız son FRESH_HOURS içinde açılmış pozisyonlar sayılır. Eski açık pozisyonlar çoğunlukla 'kapatılmayan
  zararlar'dır (araştırmada doğrulandı) ve sinyal değildir.
* Giriş: aynı coinde aynı yönde en az MIN_BACKERS ayrı trader VE ters yönde en fazla MAX_OPPOSITE.
* Çıkış: girişi tetikleyen trader'lardan en az EXIT_MIN_HOLDERS kişi pozisyonu hâlâ tutmuyorsa (yaşına bakılmaz).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FRESH_HOURS = 24
MIN_BACKERS = 3
MAX_OPPOSITE = 1
EXIT_MIN_HOLDERS = 2


@dataclass(frozen=True)
class Signal:
    inst: str
    side: int
    backers: tuple[str, ...]
    opposite: int


def consensus(rows: list[dict[str, Any]], *, now_ms: int, universe: set[str]) -> list[Signal]:
    """rows: {code, inst, side, open_ms}. Her trader her coin/yön için bir kez sayılır."""
    fresh_ms = now_ms - FRESH_HOURS * 3_600_000
    holders: dict[tuple[str, int], set[str]] = {}
    for r in rows:
        if r["inst"] in universe and r["open_ms"] >= fresh_ms:
            holders.setdefault((r["inst"], r["side"]), set()).add(r["code"])
    out = []
    for (inst, side), codes in holders.items():
        opposite = len(holders.get((inst, -side), set()))
        if len(codes) >= MIN_BACKERS and opposite <= MAX_OPPOSITE:
            out.append(Signal(inst, side, tuple(sorted(codes)), opposite))
    return sorted(out, key=lambda s: (-len(s.backers), s.inst))


def still_backed(backers: list[str], rows: list[dict[str, Any]], *, inst: str, side: int) -> int:
    """Girişi tetikleyenlerden kaçı aynı coin/yönde HÂLÂ pozisyon tutuyor (taze olması gerekmez)."""
    holding = {r["code"] for r in rows if r["inst"] == inst and r["side"] == side}
    return len(holding & set(backers))
