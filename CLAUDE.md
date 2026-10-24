# HARMAN — proje notu (Claude için)

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

## Durum (25 Ekim 2026)
- Gün 24. Başlangıç 1 Ekim, BTC 84.571 → 25 Ekim ~80.400 (−%5,0). `kural`: **2.100 $ (+%5,0)**, 25 kapanmış işlem,
  12 kazanç (%48), net +72,96; açık BTC long + ETH long. Max düşüş %5,5 (sınır %10). `ai` donuk: 1.940,82 $ (−%2,96).
- Eleme 23 Ekim: 241 trader tarandı, 136 incelendi, **16 kuralı geçti** (önceki 19; AI kolu kapalı, veto yok).
- Yedek düzeltildi (25 Ekim): DB 103 MB ile GitHub 100 MB sınırını aşınca yedek 23-24 Ekim'de 24 tur başarısız;
  `yedekle.py` artık gzip'li gönderiyor (103→28 MB). Ayrıntı protokol `corrections` listesinde.
- **Sahibinin planı (25 Ekim'de söyledi)**: deney 1 ayı tamamlar → 1 Kasım ara bakış, resmî karar **13 Kasım** protokol
  ölçütleriyle. Yeşil çıkarsa sıra: (1) ÖNCE sunucu — PC kapalıyken gerçek parada stop uygulanamaz, (2) küçük sabit
  gerçek para (200-500 $ bandı, sahibinin kararı), kurallara dokunmadan 1 ay, (3) sonuç iyi ise ölçekleme. AI kolu
  abonelik bitene dek kapalı kalır.

## Durum raporu nasıl çıkarılır
```powershell
.venv\Scripts\python.exe scripts\harman_tur.py --kuru      # rapor metni (göndermeden)
```
Ayrıntı için `data/harman.db` (tablolar: positions, equity, events, kv, snapshots). Günlük: `logs/YYYY-MM-DD.log`.
Zamanlanmış görev kontrolü: `Get-ScheduledTaskInfo -TaskName "HARMAN Bot"`.

## Bilinen dersler
- Sunucu seçeneği (20 Ekim 2026): sahibi araştırmayı istedi ama şimdilik PC'de devam diyor. PC kapalı olunca turlar
  kaçıyor (17/19 Ekim'de ~10 saat). Adaylar: Oracle Always Free (0 €, kredi kartı ister, kapasite dolu olabilir),
  Contabo Core VPS 4 (~5,50 €/ay, 4 vCPU/8GB), Hetzner (~4-6 €, kapasite bazen dolu). Avrupa lokasyonu şart (ABD IP'si
  OKX riski). Geçiş planı: GitHub yedeğinden DB geri yükleme (yedekle.py --geri-al) + cron 15 dk + PC görevini kapama.
- AI CLI'ları (Claude Code, Codex) abonelikle çalışır; bu PC'deki girişleri kullanır. Sahibi çıkış yaparsa bozulur.
  GPT-6.1 Sol yeni Codex ister: sürüm `tools/codex-0.160.0` (git'te yok; kur.ps1 kurar). Yeni model çıkınca eski CLI
  "desteklenmiyor" der — önce SÜRÜMÜ kontrol et, sağlayıcıyı suçlama.
- OKX kopya-trade API'si yalnız ~3 ay geçmiş verir; bazı trader'lar pozisyon gizler (boş instId); trader silinebilir
  ("60004 Trader doesn't exist") — bu hayatta kalma yanlılığı kaydıdır, `snapshots` tablosu herkesi 6 saatte bir kaydeder.
- Risk kuralları ölçüldü (18 Ekim 2026, 19 işlem): bağlayıcı olan TEK kural "tek pozisyon %50 tutar sınırı" oldu (19 işlemin
  15'i takıldı) — bu yüzden işlem başına risk hedeflenen %1 (20 $) yerine ortalama %0,83 (16,6 $) kaldı. Diğerleri hiç
  zorlanmadı: en fazla 2 açık pozisyon (sınır 5), en yüksek toplam tutar 2.037 $ (sınır 4.000 $), en yüksek açık risk 38,7 $
  (sınır 100 $), günlük/zirve frenleri hiç tetiklenmedi. İşlem sayısını kısıtlayan risk kuralları değil, sinyal azlığıydı
  (bot zamanın %23'ünde pozisyonsuzdu). Ders: "risk yüzdesini artırmak" tek başına bir şey değiştirmez, kesen tutar sınırıdır;
  seviye yükseltmek istiyorsan tutar sınırı yükseltilir — ama bu 13 Kasım sonrası YENİ sürüm/deney konusudur, mevcut deney
  sonuç görüldükten sonra değiştirilmez.
- Yedek boyutu sınırı (24-25 Ekim): DB 100 MB'ı aşınca GitHub push'u reddetti (tek dosya 100 MB sınırı; 24 başarısız
  deneme; veri yerelde sağlaktı, GitHub yedeği 22 Ekim'de dondu). Çözüm: yedek artık kopyada VACUUM + gzip
  (`harman.db.gz`, 103→28 MB); `--geri-al` iki biçimi de okur, yüklemeden önce `PRAGMA quick_check` doğrular.
  Canlı DB'de VACUUM yapılmaz (bot çakışır; kopyada yapılır). DB ~4 MB/gün büyüyor (snapshots); gzip yıllarca yeterli.
- Testler: `.venv\Scripts\python.exe -m pytest -q` (pytest.ini basetemp=.pytest-tmp gerekli, yoksa izin hatası).

## Geçmiş (bağlam)
Eylül 2026'da `Desktop\QUANTBOT` projesinde 35 hesaplık AI arenası denendi (15 model, 16 gün): hiçbir hesap BTC'yi
tutmaktan iyi olmadı, AI trader'lar toplamda zararda. PC'de Docker 7/24 sürdürülemedi. Arena kapatıldı; arşivi
`arsiv_arena/` (yerel) ve GitHub `veri-yedek` dalında. Ondan önce 18 kurallı strateji testi de geçememişti; en iyisi
"trend + risk ayarı" çöküşlerde kaybı ~yarıya indirmişti (2018-2024). OKX araştırması (1 Ekim): 111 aktif liderin
40.940 işlemi, 1x ve maliyet sonrası ortanca +%0,33/işlem — ilk pozitif işaret, ama 3 ay ve yükseliş dönemi.
