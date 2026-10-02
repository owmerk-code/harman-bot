r"""HARMAN turu: her 15 dakikada bir (PC açıksa). Docker/sunucu GEREKMEZ. Gerçek emir GÖNDERMEZ.

Kullanım:
    .venv\Scripts\python.exe scripts\harman_tur.py            # normal tur
    .venv\Scripts\python.exe scripts\harman_tur.py --rapor    # günlük raporu hemen gönder
    .venv\Scripts\python.exe scripts\harman_tur.py --kuru     # Telegram'a göndermeden raporu yazdır

İki kağıt defter yan yana (ikiz deney): 'kural' (yalnız kurallar) ve 'ai' (kurallar + AI vetosu/haber/erken çıkış).
Böylece AI'ın gerçekten katkı yapıp yapmadığı ölçülür. Protokol: research/harman_v1_protocol.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from harman.ledger import SEVERE_EXTRA, Ledger, atr_stop_pct  # noqa: E402
from harman.okx import Okx, side_of, usd_volume  # noqa: E402
from harman.signals import EXIT_MIN_HOLDERS, consensus, still_backed  # noqa: E402
from harman.store import Store  # noqa: E402
from harman import vetting  # noqa: E402

from harman.config import DB, LOGS as LOG_DIR  # noqa: E402
LOCK = ROOT / "data" / "tur.lock"
ISTANBUL = timezone(timedelta(hours=3))
LEDGERS = ("kural", "ai")
MIN_USD_VOLUME = 100_000_000
VET_EVERY_DAYS = 7
FULL_SNAPSHOT_HOURS = 6
REPORT_HOUR = 21
NAMES = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple", "DOGE": "dogecoin", "BNB": "binance",
         "ADA": "cardano", "AVAX": "avalanche", "LINK": "chainlink", "TON": "toncoin", "SUI": "sui", "LTC": "litecoin"}
MACRO = ("fed", "sec", "rate", "inflation", "etf", "hack", "exploit", "ban", "lawsuit", "tariff")


def log(text: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(LOG_DIR / f"{stamp[:10]}.log", "a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {text}\n")


def telegram(text: str) -> bool:
    from harman.telegram import send
    ok = send(text)
    if not ok:
        log("telegram gonderilemedi (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID .env'de mi?)")
    return ok


# --------------------------------------------------------------------------- haberler
def refresh_news(store: Store, now_ms: int) -> list[dict[str, Any]]:
    from harman.news import FEEDS, fetch
    items = {i["id"]: i for i in store.get("news", [])}
    for name, url in FEEDS:
        try:
            for ev in fetch(name, url):
                if now_ms - ev["ms"] <= 24 * 3_600_000:
                    items.setdefault(ev["id"], ev)
        except Exception as exc:
            log(f"haber kaynagi {name}: {type(exc).__name__}: {str(exc)[:150]}")
    fresh = sorted((i for i in items.values() if now_ms - i["ms"] <= 24 * 3_600_000), key=lambda i: -i["ms"])[:200]
    store.put("news", fresh)
    return fresh


def relevant(news: list[dict[str, Any]], inst: str, *, since_ms: int) -> list[str]:
    base = inst.split("-")[0]
    words = {base.lower(), NAMES.get(base, base).lower()}
    out = []
    for item in news:
        if item["ms"] < since_ms:
            continue
        title = item["t"].lower()
        if any(f" {w}" in f" {title}" for w in words) or any(m in title for m in MACRO):
            out.append(item["t"])
    return out


# --------------------------------------------------------------------------- trader eleme
def vet(store: Store, okx: Okx, ai: Any, now_ms: int) -> None:
    traders = okx.lead_traders()
    verdicts = []
    for t in traders:
        if int(t.get("leadDays") or 0) < vetting.MIN_LEAD_DAYS:
            continue
        try:
            verdicts.append(vetting.evaluate(t, okx.history(t["uniqueCode"]), okx.positions(t["uniqueCode"]), now_ms=now_ms))
        except Exception as exc:
            log(f"eleme {t.get('uniqueCode')}: {type(exc).__name__}: {str(exc)[:150]}")
    chosen = vetting.select(verdicts)
    rule_codes = [v.code for v in chosen]
    rows = [{"kod": v.code, "isim": v.nick, **v.stats} for v in chosen]
    rejected, notes = ai.veto_traders(rows) if rows else (set(), [])
    ai_codes = [c for c in rule_codes if c not in rejected]
    store.put("all_active_codes", [str(t["uniqueCode"]) for t in traders])
    store.put("traders:kural", rule_codes)
    store.put("traders:ai", ai_codes)
    store.put("traders:info", {v.code: {"isim": v.nick, **v.stats} for v in chosen})
    store.put("last_vet_ms", now_ms)
    summary = (f"eleme: {len(traders)} trader, {len(verdicts)} incelendi, {len(chosen)} kurali gecti, "
               f"AI {len(rejected)} tanesini reddetti -> kural {len(rule_codes)} / ai {len(ai_codes)}")
    store.log(now_ms, "eleme", summary + (" | " + " ; ".join(notes) if notes else ""))
    log(summary)


# --------------------------------------------------------------------------- tur
def observe(store: Store, okx: Okx, codes: list[str], now_ms: int) -> list[dict[str, Any]]:
    rows, bad = [], 0
    for code in codes:
        try:
            positions = okx.positions(code)
        except Exception as exc:
            log(f"pozisyon {code}: {type(exc).__name__}: {str(exc)[:150]}")
            continue
        for p in positions:  # tek bozuk satir o trader'in butun pozisyonlarini dusurmesin
            try:
                rows.append({"code": code, "inst": p["instId"], "side": side_of(p), "open_ms": int(p["openTime"]),
                             "lever": float(p.get("lever") or 0), "open_px": float(p.get("openAvgPx") or 0),
                             "sub_id": str(p.get("subPosId"))})
            except (KeyError, TypeError, ValueError):
                bad += 1
    if bad:
        log(f"{bad} bozuk pozisyon satiri atlandi")
    store.snapshot(now_ms, rows)
    return rows


def run_ledger(name: str, store: Store, okx: Okx, ai: Any, rows: list[dict[str, Any]], prices: dict[str, float],
               universe: set[str], news: list[dict[str, Any]], now_ms: int) -> None:
    led = Ledger(name, store)
    codes = set(store.get(f"traders:{name}", []))
    mine = [r for r in rows if r["code"] in codes]
    last_ms = store.get(f"{name}:last_ms", now_ms - 900_000)

    # 1) çıkışlar: stop/kâr-al (15 dk mumları), süre, trader'lar çıktı
    for pos in store.open_positions(name):
        try:
            hit = led.check_stops(pos, okx.candles(pos["inst"], "15m", 100))
        except Exception as exc:
            log(f"{name} mum {pos['inst']}: {type(exc).__name__}: {str(exc)[:150]}")
            hit = None
        if hit:
            px, ts, why = hit
            pnl = led.close(pos, price=px, now_ms=ts, reason=why)
            store.log(now_ms, "cikis", f"{pos['inst']} {why} pnl {pnl:+.2f}", name)
            continue
        price = prices.get(pos["inst"])
        if price is None:
            continue
        if now_ms - pos["entry_ms"] >= 72 * 3_600_000:
            pnl = led.close(pos, price=price, now_ms=now_ms, reason="sure doldu")
            store.log(now_ms, "cikis", f"{pos['inst']} sure doldu pnl {pnl:+.2f}", name)
        elif still_backed(json.loads(pos["backers"]), mine, inst=pos["inst"], side=pos["side"]) < EXIT_MIN_HOLDERS:
            pnl = led.close(pos, price=price, now_ms=now_ms, reason="traderlar cikti")
            store.log(now_ms, "cikis", f"{pos['inst']} traderlar cikti pnl {pnl:+.2f}", name)

    # 2) AI erken çıkış (yalnız 'ai' defteri, yalnız yeni ilgili haber varsa)
    if name == "ai":
        items = []
        for pos in store.open_positions(name):
            heads = relevant(news, pos["inst"], since_ms=last_ms)
            if heads:
                items.append({"id": pos["id"], "coin": pos["inst"], "yon": "long" if pos["side"] > 0 else "short",
                              "yeni_haberler": heads[:8]})
        for pid, why in ai.early_exit(items):
            pos = next((p for p in store.open_positions(name) if p["id"] == pid), None)
            if pos and pos["inst"] in prices:
                pnl = led.close(pos, price=prices[pos["inst"]], now_ms=now_ms, reason="AI haber cikisi")
                store.log(now_ms, "cikis", f"{pos['inst']} AI haber cikisi ({why}) pnl {pnl:+.2f}", name)

    led.mark(prices, now_ms)

    # 3) girişler: en az 3 seçilmiş trader aynı coin/yönde taze pozisyonda
    for sig in consensus(mine, now_ms=now_ms, universe=universe):
        reason = led.why_not(sig.inst, prices, now_ms)
        if reason or sig.inst not in prices:
            continue
        factor, note = 1.0, f"{len(sig.backers)} trader, ters {sig.opposite}"
        if name == "ai":
            factor, why = ai.news_check(sig.inst, sig.side, relevant(news, sig.inst, since_ms=now_ms - 12 * 3_600_000))
            note += f" | AI: {why}"
            if factor <= 0:
                store.log(now_ms, "giris_iptal", f"{sig.inst} {note}", name)
                continue
        try:
            stop_pct = atr_stop_pct(okx.candles(sig.inst, "1H", 100))
        except Exception:
            continue
        pid = led.open(inst=sig.inst, side=sig.side, price=prices[sig.inst], stop_pct=stop_pct,
                       backers=list(sig.backers), now_ms=now_ms, size_factor=factor, note=note)
        if pid:
            store.log(now_ms, "giris", f"{sig.inst} {'LONG' if sig.side > 0 else 'SHORT'} stop %{stop_pct*100:.1f} "
                                       f"boyut x{factor:.1f} | {note}", name)
    store.put(f"{name}:last_ms", now_ms)


# --------------------------------------------------------------------------- rapor
def facts(store: Store, prices: dict[str, float], now_ms: int) -> dict[str, Any]:
    start_ms = store.get("start_ms", now_ms)
    btc0, btc = store.get("btc_start"), prices.get("BTC-USDT-SWAP")
    out: dict[str, Any] = {"gun": int((now_ms - start_ms) / 8.64e7) + 1,
                           "btc_tut_getiri_pct": round((btc / btc0 - 1) * 100, 2) if btc0 and btc else None,
                           "bugun_calisan_tur": len([t for t in store.get("runs", []) if t >= now_ms - 8.64e7]),
                           "beklenen_tur": 96}
    day0 = now_ms - 8.64e7
    for name in LEDGERS:
        led = Ledger(name, store)
        closed = store.closed_positions(name)
        eq = led.equity(prices)
        severe = eq - sum(p["entry_px"] * p["qty"] * SEVERE_EXTRA for p in closed)
        today = [p for p in closed if p["exit_ms"] >= day0]
        out[name] = {"ozsermaye": round(eq, 2), "getiri_pct": round((eq / led.capital - 1) * 100, 2),
                     "sert_maliyet_getiri_pct": round((severe / led.capital - 1) * 100, 2),
                     "kapanan_islem": len(closed),
                     "kazanma_pct": round(sum(p["pnl"] > 0 for p in closed) / len(closed) * 100) if closed else None,
                     "bugun_kapanan": [f"{p['inst'].split('-')[0]} {p['exit_reason']} {p['pnl']:+.2f}$" for p in today],
                     "acik": [f"{p['inst'].split('-')[0]} {'long' if p['side'] > 0 else 'short'}" for p in store.open_positions(name)],
                     "durdu": bool(store.get(f"{name}:halted"))}
    out["takip_edilen_trader"] = {"kural": len(store.get("traders:kural", [])), "ai": len(store.get("traders:ai", []))}
    errs = [r["text"] for r in store.db.execute("SELECT text FROM events WHERE kind='ai_hata' AND ts_ms>=?", (day0,))]
    out["ai_baglanti_hatasi_24s"] = len(errs)
    out["ai_hata_ornek"] = errs[-3:]
    return out


def template(f: dict[str, Any]) -> str:
    lines = [f"Gün {f['gun']} | BTC sadece tutulsaydı: {f['btc_tut_getiri_pct']}%"]
    for name, title in (("kural", "Kurallı bot"), ("ai", "AI destekli bot")):
        d = f[name]
        lines.append(f"{title}: {d['ozsermaye']} $ ({d['getiri_pct']:+}%), {d['kapanan_islem']} işlem, açık: {', '.join(d['acik']) or 'yok'}")
    lines.append(f"Bugün çalışan tur: {f['bugun_calisan_tur']}/{f['beklenen_tur']}")
    if f.get("ai_baglanti_hatasi_24s"):
        lines.append(f"⚠️ AI'lara {f['ai_baglanti_hatasi_24s']} kez ulaşılamadı (Claude/Codex girişini kontrol et)")
    return "\n".join(lines)


def report(store: Store, ai: Any, prices: dict[str, float], now_ms: int, *, send: bool) -> str:
    f = facts(store, prices, now_ms)
    task = ("Sahibine (teknik olmayan biri) gunluk KISA Turkce rapor yaz: iki botun (kurallı ve AI destekli) durumu, "
            "BTC'yi sadece tutmakla kiyas, bugun ne oldu. Sayi uydurma, yalniz verilenleri kullan. 6-8 satir. "
            "ai_baglanti_hatasi_24s sifirdan buyukse son satirda 'AI'lara ulasilamadi, Claude/Codex girisini kontrol et' de.")
    body = ai.write("sonnet", task, f) or template(f)
    if datetime.fromtimestamp(now_ms / 1000, tz=ISTANBUL).weekday() == 6:
        weekly = ai.write("opus", "Haftalik kisa analiz yaz: hangi bot neden iyi/kotu gitti, AI katki yapti mi, "
                                  "dikkat edilecek ne var. Kural degistirmeyi ONERME (deney sabit). 5 satir.", f, 900)
        if weekly:
            body += "\n\n📊 Haftalık analiz:\n" + weekly
    text = f"🤖 HARMAN günlük rapor — {datetime.fromtimestamp(now_ms/1000, tz=ISTANBUL):%d.%m %H:%M}\n\n{body}\n\n(Sanal para. Gerçek emir yok.)"
    if send and telegram(text):
        store.put("last_report_day", datetime.fromtimestamp(now_ms / 1000, tz=ISTANBUL).date().isoformat())
    return text


def daily_backup(store: Store, day: str) -> None:
    """Günde bir: veritabanı GitHub'daki gizli 'veri-yedek' dalına. Başarısızsa ertesi tur tekrar dener."""
    import yedekle
    try:
        result = yedekle.backup()
        store.put("last_backup_day", day)
        log(f"yedek: {result}")
    except Exception as exc:
        log(f"yedek HATASI: {type(exc).__name__}: {str(exc)[:200]}")
        fails = int(store.get("backup_fail_streak", 0)) + 1
        store.put("backup_fail_streak", fails)
        if fails == 4:
            telegram(f"⚠️ HARMAN: veri yedeği 4 kez GitHub'a gönderilemedi ({type(exc).__name__}).")
        return
    store.put("backup_fail_streak", 0)


# --------------------------------------------------------------------------- ana
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapor", action="store_true")
    ap.add_argument("--kuru", action="store_true")
    args = ap.parse_args(argv)
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 20 * 60:
        log("baska tur suruyor; cikiliyor")
        return 0
    LOCK.write_text(str(os.getpid()))
    store = Store(DB)
    try:
        from harman.ai import Ai
        okx = Okx()
        ai = Ai(log=lambda kind, text: store.log(int(time.time() * 1000), kind, text))
        now_ms = int(time.time() * 1000)
        tickers = okx.tickers()
        prices = {k: float(v["last"]) for k, v in tickers.items() if v.get("last")}
        if args.rapor or args.kuru:
            print(report(store, ai, prices, now_ms, send=not args.kuru))
            return 0
        if store.get("start_ms") is None:
            store.put("start_ms", now_ms)
            store.put("btc_start", prices.get("BTC-USDT-SWAP"))
            store.log(now_ms, "basla", f"HARMAN basladi; BTC {prices.get('BTC-USDT-SWAP')}")
        universe = {k for k, v in tickers.items() if k.endswith("-USDT-SWAP") and usd_volume(v) >= MIN_USD_VOLUME}
        if not store.get("traders:kural") or now_ms - store.get("last_vet_ms", 0) >= VET_EVERY_DAYS * 8.64e7:
            vet(store, okx, ai, now_ms)
        codes = sorted(set(store.get("traders:kural", [])) | set(store.get("traders:ai", [])))
        rows = observe(store, okx, codes, now_ms)
        if now_ms - store.get("last_full_snapshot_ms", 0) >= FULL_SNAPSHOT_HOURS * 3_600_000:
            others = [c for c in store.get("all_active_codes", []) if c not in codes]
            observe(store, okx, others, now_ms)  # hayatta kalma yanlılığına karşı: herkesin kaydı bizde
            store.put("last_full_snapshot_ms", now_ms)
        news = refresh_news(store, now_ms)
        for name in LEDGERS:
            run_ledger(name, store, okx, ai, rows, prices, universe, news, now_ms)
        runs = [t for t in store.get("runs", []) if t >= now_ms - 3 * 8.64e7] + [now_ms]
        store.put("runs", runs)
        store.put("fail_streak", 0)
        local = datetime.fromtimestamp(now_ms / 1000, tz=ISTANBUL)
        if local.hour >= REPORT_HOUR and store.get("last_report_day") != local.date().isoformat():
            report(store, ai, prices, now_ms, send=True)
        if store.get("last_backup_day") != local.date().isoformat() and local.hour >= REPORT_HOUR:
            daily_backup(store, local.date().isoformat())
        log(f"tur tamam: {len(codes)} trader, {len(rows)} pozisyon, evren {len(universe)}, "
            + ", ".join(f"{n} {Ledger(n, store).equity(prices):.2f}" for n in LEDGERS))
        return 0
    except Exception as exc:
        streak = int(store.get("fail_streak", 0)) + 1
        store.put("fail_streak", streak)
        log(f"HATA ({streak}. ust uste): {type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}")
        if streak == 3:
            telegram(f"⚠️ HARMAN botu 3 turdur çalışamıyor: {type(exc).__name__}: {str(exc)[:200]}")
        return 1
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
