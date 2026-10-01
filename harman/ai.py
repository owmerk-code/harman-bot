"""AI görevleri. KURAL: AI fiyat tahmin etmez, tek başına işlem açamaz, riski ARTIRAMAZ.

* Trader vetosu  : Opus 5.5 + GPT-6.1 Sol bağımsız; birinin reddi yeter (risk azaltmak tek görüşle olur).
* Haber kontrolü : Sonnet 5.5 -> 'devam' | 'kucult' (yarı boyut) | 'iptal'.
* Erken çıkış    : Sonnet 5.5, yalnız açık pozisyonun coinini anan yeni haber varsa sorulur.
* Rapor/analiz   : Sonnet 5.5 günlük, Opus 5.5 haftalık; AI çalışmazsa düz şablon gider.
Önceki deneyin dersleri: uzun metin KIRPILIR (karar çöpe gitmez); istem boyu sabit tutulur; her rol için yedek model.
"""
from __future__ import annotations

import json
from typing import Any

from harman.cli_ai import CliClient, Model, available

MODELS = {
    "opus": Model("harman-opus55", "claude_cli", "claude-opus-5-5"),
    "gpt": Model("harman-gpt61sol", "codex_cli", "gpt-6.1-sol"),
    "sonnet": Model("harman-sonnet55", "claude_cli", "claude-sonnet-5-5"),
    "fable": Model("harman-fable51", "claude_cli", "claude-fable-5-1"),
}
FALLBACK = {"opus": ["opus", "fable", "sonnet"], "gpt": ["gpt"], "sonnet": ["sonnet", "opus"]}
MAX_PROMPT_CHARS = 12_000

BASE = ("Sen bir kripto kagit-para botunun yardimcisisin. Fiyat TAHMIN ETME. Yalniz istenen JSON'u dondur, baska metin "
        "yazma. Turkce, kisa ve sade yaz. Emin degilsen temkinli tarafi sec.")


def _parse(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text[text.index("{"): text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None


class Ai:
    def __init__(self, *, client_factory: Any = None, timeout: float = 180.0, log: Any = None) -> None:
        self.factory = client_factory or (lambda c: CliClient(c, timeout=timeout))
        self.log = log or (lambda kind, text: None)

    def ask(self, role: str, task: str, payload: dict[str, Any], schema: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
        prompt = json.dumps(payload, ensure_ascii=False)[:MAX_PROMPT_CHARS]
        for key in FALLBACK[role]:
            cand = MODELS[key]
            if not available(cand):
                continue
            try:
                res = self.factory(cand).complete(system=BASE + "\n" + task, prompt=prompt, schema=schema, max_tokens=2000)
                data = _parse(res.text or "")
                if data is not None:
                    return cand.model, data
                self.log("ai_hata", f"{cand.model}: JSON yok")
            except Exception as exc:  # bir model düşerse yedeğe geç
                self.log("ai_hata", f"{cand.model}: {type(exc).__name__}: {str(exc)[:150]}")
        return None

    # --- 1) trader vetosu: iki firma bağımsız, birinin reddi yeter ---
    def veto_traders(self, rows: list[dict[str, Any]]) -> tuple[set[str], list[str]]:
        task = ("Asagidaki kopya trader'lar kural testini gecti. Gorevin KUMARBAZ ya da GUVENILMEZ olanlari bulmak: "
                "kazancin tek bir sansli doneme dayanmasi, zarari acik tutma, asiri kaldirac, tutarsizlik. Supheli olanlari "
                'reddet. JSON: {"reddet": [{"kod": "...", "neden": "kisa"}]}. Hepsi iyiyse bos liste.')
        schema = {"type": "object", "properties": {"reddet": {"type": "array", "items": {"type": "object", "properties": {
            "kod": {"type": "string"}, "neden": {"type": "string"}}, "required": ["kod", "neden"]}}}, "required": ["reddet"]}
        rejected: set[str] = set()
        notes: list[str] = []
        valid_codes = {r["kod"] for r in rows}
        for role in ("opus", "gpt"):
            got = self.ask(role, task, {"traderlar": rows}, schema)
            if not got:
                notes.append(f"{role}: cevap yok")
                continue
            model, data = got
            for item in data.get("reddet") or []:
                code = str(item.get("kod", ""))
                if code in valid_codes:
                    rejected.add(code)
                    notes.append(f"{model}: {code} reddedildi - {str(item.get('neden', ''))[:120]}")
        return rejected, notes

    # --- 2) haber kontrolü: yalnız küçültür/iptal eder ---
    def news_check(self, inst: str, side: int, headlines: list[str]) -> tuple[float, str]:
        if not headlines:
            return 1.0, "ilgili haber yok"
        task = ("Bir kagit-para islemi acilmak uzere. Son haberlerde bu islem icin CIDDI risk var mi? Riski yalniz "
                'AZALTABILIRSIN. JSON: {"karar": "devam"|"kucult"|"iptal", "gerekce": "kisa"}')
        schema = {"type": "object", "properties": {"karar": {"type": "string", "enum": ["devam", "kucult", "iptal"]},
                                                   "gerekce": {"type": "string"}}, "required": ["karar", "gerekce"]}
        got = self.ask("sonnet", task, {"coin": inst, "yon": "long" if side > 0 else "short",
                                        "son_haberler": headlines[:15]}, schema)
        if not got:
            return 0.0, "AI cevap vermedi: guvenli taraf, islem acilmadi"  # AI yoksa yeni risk yok
        _, data = got
        factor = {"devam": 1.0, "kucult": 0.5, "iptal": 0.0}.get(str(data.get("karar")), 0.0)
        return factor, str(data.get("gerekce", ""))[:300]

    # --- 3) erken çıkış: yalnız kapatabilir ---
    def early_exit(self, items: list[dict[str, Any]]) -> list[tuple[int, str]]:
        if not items:
            return []
        task = ("Acik kagit-para pozisyonlari ve onlari ilgilendiren YENI haberler asagida. Hangisinde haber, pozisyonu "
                'acik tutmayi ciddi bicimde riskli yapiyor? Yalniz KAPATMA onerebilirsin. JSON: {"kapat": [{"id": 1, "neden": "kisa"}]}')
        schema = {"type": "object", "properties": {"kapat": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "integer"}, "neden": {"type": "string"}}, "required": ["id", "neden"]}}}, "required": ["kapat"]}
        got = self.ask("sonnet", task, {"pozisyonlar": items}, schema)
        if not got:
            return []
        valid = {int(i["id"]) for i in items}
        return [(int(x["id"]), str(x.get("neden", ""))[:200]) for x in got[1].get("kapat") or []
                if str(x.get("id", "")).lstrip("-").isdigit() and int(x["id"]) in valid]

    # --- 4/5) raporlar ---
    def write(self, role: str, task: str, facts: dict[str, Any], limit: int = 1500) -> str | None:
        schema = {"type": "object", "properties": {"metin": {"type": "string"}}, "required": ["metin"]}
        got = self.ask(role, task + ' JSON: {"metin": "..."}', facts, schema)
        return str(got[1].get("metin", "")).strip()[:limit] if got else None
