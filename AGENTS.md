# HARMAN — proje notu (Codex için)

## Sahibi ve iletişim
- Sahibi teknik değil, Türkçe konuşur. **Sade Türkçe, kısa cevap, tablolar.** Uzun ve teknik mesajlarda kafası karışıyor
  ("bişey anlamadım" derse daha da basitleştir). Terim kullanma ya da hemen açıkla.
- Mühendislik kararlarını sana bıraktı: kendin karar ver, rakamlarla raporla. **Yalnız para, gerçek hesap (mainnet),
  hesap/şifre ve silme işlerinde sor.**
- Dürüst ol: kötü sonucu yumuşatma, emin olmadığını söyle, hatanı açıkça düzelt.
- Bu, sahibinin dediği gibi **son deneme**. Hedefi: "AI ile pasif gelir — kârlı bir trader ne yapıyorsa bot yapsın".

## Ne bu proje
OKX'teki sağlam kopya trader'ları izleyen **kağıt-para** botu. Seçilmiş trader'lardan en az 3'ü son 24 saatte aynı
coinde aynı yöne girerse sanal işlem açar. Gerçek emir YOK. Docker yok, tek SQLite dosyası.
- Kod: `harman/` (okx, vetting=eleme, signals=harmanlama, ledger=risk ve defter, ai, cli_ai, news, telegram, store)
- Tur: `scripts/harman_tur.py` — Windows zamanlanmış görevi **"HARMAN Bot"**, 15 dk'da bir, pythonw (pencere yok)
- Yedek: `scripts/yedekle.py` — her akşam DB'yi GitHub `veri-yedek` dalına; `--geri-al` ile geri yükler
- Kurulum (yeni PC): `kur.ps1`, ayrıntı README.md
- GitHub: `github.com/owmerk-code/harman-bot` (gizli). Kod `main`, veri `veri-yedek`.
- `.env` yalnız `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` içerir — ASLA commit etme.

## Deney ve karar (DEĞİŞTİRME)
- Protokol: `research/harman_v1_protocol.json` — kurallar ve **13 Kasım 2026** karar ölçütleri SONUÇ GÖRÜLMEDEN yazıldı.
  **Sonuca bakıp kural/eşik değiştirmek yasak** (yeni sürüm = yeni deney). Yalnız veri/altyapı kusuru düzeltilebilir;
  düzeltme protokolün `corrections` listesine yazılır.
- İkiz deney: `kural` defteri (yalnız kurallar) vs `ai` defteri (kurallar + AI). AI yalnız riski AZALTABİLİR:
  Opus 5.5 + GPT-6.1 Sol trader vetosu (haftalık, birinin reddi yeter), Sonnet 5.5 haber kontrolü/erken çıkış/rapor.
  AI cevap vermezse `ai` defteri yeni işlem açmaz.
  **18 Ekim 2026: AI kolu KAPATILDI** (Claude aboneliği bitti) — `scripts/harman_tur.py` içinde `AI_KOLU_KAPALI = True`.
  `ai` defteri 16 Ekim sonucuyla dondu; yalnız `kural` defteri işlem yapıyor. Raporda `ai` "kapandı" olarak görünür.
  AI kolu yeniden açılacaksa: `AI_KOLU_KAPALI = False` + tutanağa tarih yaz.
- Risk (ledger.py): işlem başı %1, tek pozisyon ≤%50, toplam ≤2x, ≤5 pozisyon, açık risk ≤%5, ATR stop %1,5-8,
  kâr-al 2R, en uzun 72 saat, gün -%3 fren, zirveden -%15 durur.
- Karar: YEŞİL (küçük gerçek para, sahibinin kararı) / SARI (4 hafta uzat) / KIRMIZI (bırak). Ölçütler protokolde.

## Durum (18 Ekim 2026)
- Gün 17. Başlangıç 1 Ekim, BTC 84.571. `kural`: **+%4,1** (2.081 $, 18 kapanmış işlem, 9 kazanç), açık BTC long.
  `ai`: **−%3,0** (1.941 $, 12 işlem, 4 kazanç), 16 Ekim'den beri işlem yok. BTC'yi tutmak: −%3,2.
- Son eleme 16 Ekim: 250 trader incelendi, 19 kuralı geçti, AI 7 reddetti -> kural 19 / ai 12. Sıradaki eleme 23 Ekim.
- AI kolu 18 Ekim'de kapatıldı (Claude aboneliği bitti). Karar günü 13 Kasım: yalnız `kural` defteri değerlendirilecek.
- Düzeltme (işlem yokken): seçilenlerin pozisyonlarının çoğu GİZLİYDİ -> `MAX_HIDDEN_SHARE 0.20` eklendi.
- 17 Ekim 05:28-15:24 PC kapalıydı (10 saat): o aralıkta tur yok, veri boşluğu normaldir, hata değil.

## Durum raporu nasıl çıkarılır
```powershell
.venv\Scripts\python.exe scripts\harman_tur.py --kuru      # rapor metni (göndermeden)
```
Ayrıntı için `data/harman.db` (tablolar: positions, equity, events, kv, snapshots). Günlük: `logs/YYYY-MM-DD.log`.
Zamanlanmış görev kontrolü: `Get-ScheduledTaskInfo -TaskName "HARMAN Bot"`.

## Bilinen dersler
- AI CLI'ları (Codex, Codex) abonelikle çalışır; bu PC'deki girişleri kullanır. Sahibi çıkış yaparsa bozulur.
  GPT-6.1 Sol yeni Codex ister: sürüm `tools/codex-0.160.0` (git'te yok; kur.ps1 kurar). Yeni model çıkınca eski CLI
  "desteklenmiyor" der — önce SÜRÜMÜ kontrol et, sağlayıcıyı suçlama.
- OKX kopya-trade API'si yalnız ~3 ay geçmiş verir; bazı trader'lar pozisyon gizler (boş instId); trader silinebilir
  ("60004 Trader doesn't exist") — bu hayatta kalma yanlılığı kaydıdır, `snapshots` tablosu herkesi 6 saatte bir kaydeder.
- Testler: `.venv\Scripts\python.exe -m pytest -q` (pytest.ini basetemp=.pytest-tmp gerekli, yoksa izin hatası).

## Geçmiş (bağlam)
Eylül 2026'da `Desktop\QUANTBOT` projesinde 35 hesaplık AI arenası denendi (15 model, 16 gün): hiçbir hesap BTC'yi
tutmaktan iyi olmadı, AI trader'lar toplamda zararda. PC'de Docker 7/24 sürdürülemedi. Arena kapatıldı; arşivi
`arsiv_arena/` (yerel) ve GitHub `veri-yedek` dalında. Ondan önce 18 kurallı strateji testi de geçememişti; en iyisi
"trend + risk ayarı" çöküşlerde kaybı ~yarıya indirmişti (2018-2024). OKX araştırması (1 Ekim): 111 aktif liderin
40.940 işlemi, 1x ve maliyet sonrası ortanca +%0,33/işlem — ilk pozitif işaret, ama 3 ay ve yükseliş dönemi.
