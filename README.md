# HARMAN — kopya trader harmanlama botu (kağıt para)

OKX'teki **sağlam** kopya trader'ları izler. En az 3'ü son 24 saatte aynı coinde aynı yöne girerse **sanal parayla**
işlem açar. Gerçek emir göndermez. Docker gerekmez, tek küçük dosyada çalışır.

- **Kurallar ve karar günü:** `research/harman_v1_protocol.json` (karar: **13 Kasım 2026**)
- **İki hesap yan yana:** `kural` (yalnız kurallar) ve `ai` (kurallar + AI kontrolü). AI'ın katkısı böyle ölçülür.
- **AI modelleri:** Opus 5.5 ve GPT-6.1 Sol (haftalık trader kontrolü), Sonnet 5.5 (haber, erken çıkış, akşam raporu).
  AI fiyat tahmin etmez, tek başına işlem açamaz, riski artıramaz.
- **Her gün:** 21:00'den sonra Telegram raporu + veri yedeği GitHub'daki gizli `veri-yedek` dalına.

## Bilgisayar giderse: yeni bilgisayara kurulum (~15 dakika)

1. **Programları kur:** [Python 3.12](https://www.python.org/downloads/), [Git](https://git-scm.com/download/win),
   [Node.js LTS](https://nodejs.org/), [GitHub CLI](https://cli.github.com/), [Claude Code](https://claude.com/claude-code).
2. **PowerShell'i aç** ve sırayla yaz:
   ```powershell
   gh auth login
   cd $HOME\Desktop
   gh repo clone owmerk-code/harman-bot HARMAN
   cd HARMAN
   powershell -ExecutionPolicy Bypass -File .\kur.ps1
   ```
   `kur.ps1` şunları yapar: Python ortamı, gerekli paketler, sabit Codex sürümü, **son veri yedeğini GitHub'dan indirme**,
   15 dakikalık otomatik görev.
3. **`.env` dosyası oluştur** (HARMAN klasöründe). İçine yalnız şu iki satır (değerleri not ettiğin yerden):
   ```
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_CHAT_ID=...
   ```
4. **AI girişleri:** PowerShell'de `claude` yaz ve giriş yap; sonra `tools\codex-0.160.0\...\codex.exe login`
   (kur.ps1 tam komutu ekrana yazar) ile ChatGPT hesabına giriş yap.
5. Bitti. Bot kaldığı yerden devam eder (en fazla 1 günlük veri kaybı).

## Elle komutlar

```powershell
.venv\Scripts\python.exe scripts\harman_tur.py            # bir tur çalıştır
.venv\Scripts\python.exe scripts\harman_tur.py --kuru     # raporu göndermeden göster
.venv\Scripts\python.exe scripts\yedekle.py               # şimdi yedekle
.venv\Scripts\python.exe -m pytest -q                     # testler
```

`arsiv_arena/` (yalnız yedek dalında): Eylül 2026 arenasının (35 hesap, 15 AI) tam veritabanı dökümü.
