# Operasyon: günlük servis modu, kalıcı durum, entegrasyon, runbook'lar

## Çalışma biçimleri

| Biçim | Komut | Ne zaman |
|---|---|---|
| Toplu (değerlendirme/ısınma) | `ztp --synthetic …` / `ztp --cert-dir …` / dosyalardan | Mimari doğrulama, kalibrasyon, yeni müşteri ısınması (90 günlük baseline) |
| Toplu + durum kaydı | `… --state` | Günlük moda geçiş öncesi: baseline, tespit geçmişi, yüzdelik havuzu, açık vakalar, takma adlar kaydedilir |
| **Günlük servis** | `ztp --daily 2026-09-17 --events gun.parquet --directory dizin.csv --config musteri.yaml --out ./ztp_out` | Her gece: durumu yükle → günün ham olaylarını işle → budama → durumu kaydet → kuyruk/vaka/sink çıktıları |

Günlük mod **idempotenttir**: su seviyesi (son işlenen gün) aşılmış bir gün `--force` olmadan yeniden işlenmez;
işlem sırası gün gün olmalıdır. Aynı veri için toplu koşu ile "toplu ısınma + gün gün artımlı" birebir aynı kuyruğu
üretir; bu eşdeğerlik `tests/test_state.py::test_batch_equals_incremental` ile korunur.

## Kalıcı durum (`ztp_out/<tenant>/state.sqlite`)

Tek dosya SQLite; ek bağımlılık yok; yedeklenebilir, taşınabilir, şema sürümü kontrol edilir.

| Saklanan | Neden | Budama |
|---|---|---|
| Varlık-gün özellikleri, cihaz-gün tablosu | Baseline (9.2) ve ajan sessizliği (#10) ham olay olmadan hesaplanır | uzun pencere + 7 gün |
| Veri kalitesi günlük istatistikleri | Kaynak hacmi referansı (8.3) | uzun pencere |
| Gözlem grafı kenarları | Derin analiz / akran kıyası (11.3) | son görülme < eşik |
| Tespit geçmişi, yüzdelik havuzu, risk serileri | 7 günlük pencere, kalibrasyon, yörünge (13.x, 4.1) | pencere |
| Açık vakalar (`last_queued`), kuyruk geçmişi | Yeni kanıt olmadan yeniden sunulmaz; precision@k | — |
| Takma ad eşlemesi | Kararlı `U-xxxx` (20.1) | — |
| Tahmin satırları ve öğrenen model | Kalibrasyon ölçümü ve eğitim (14.5/14.6) | pencere |

**Ham olay saklanmaz** (20.1 saklama süresi): yalnızca türev veri tutulur.

## Dosya girişi (günlük mod)

- Olaylar: CSV/Parquet, OCSF-lite kolonları (`event_id, time, source, actor_raw` zorunlu; diğerleri opsiyonel).
- Dizin: `sid, ad_sam, upn, dept, hire_date` zorunlu; `primary_device, title_level, location, is_service, is_privileged,
  resignation_notice_date, role_change_date, privilege_grant_date` opsiyonel.
- `--leases` (ip, sid, start, end) zaman aralıklı IP eşlemesi; `--leaves` (sid, start, end, tur) izin takvimi.
Şema hatası açık hata verir; sessiz düşüş yoktur.

## Entegrasyon (17.6)

Vakalar dosyalara ek olarak yapılandırılmış **sink**'lere akar; gerçek kimlik hiçbir sink'e gitmez.

```yaml
sinks:
  - type: jsonl                      # ztp_out/<tenant>/cases.jsonl — SIEM/log toplayıcı alımı
  - type: webhook                    # SOAR / ticketing
    url: https://soar.example/api/ztp
    secret_env: ZTP_WEBHOOK_SECRET   # gövde HMAC-SHA256 ile imzalanır: X-ZTP-Signature: sha256=<hex>
    headers: {Authorization: "Bearer …"}
    timeout: 10
    retries: 3                       # 5xx/429/ağ hatasında üstel geri çekilme; 4xx'te yeniden deneme yok
```

Sink hataları izole edilir ve sayılır; boru hattı durmaz.

## Aldatma katmanı (honeytoken)

Tuzak varlıklar müşteri yapılandırmasında listelenir; meşru kullanımı olmadığından her etkileşim deterministik kritik tespittir
(`HONEY-0018` hesap, `HONEY-0019` dosya/paylaşım, `HONEY-0020` sunucu). Baseline, akran kıyası ve eşik jitter'ı uygulanmaz.

```yaml
honeytokens:
  hesaplar:  [svc-backup-legacy, adm-eski]          # aktör adı (AD sAM/UPN/API kimliği), büyük/küçük harf duyarsız
  kaynaklar: ['\\FS-01\finans\bonus_2026*']         # dosya/paylaşım yolu; fnmatch kalıbı olabilir
  cihazlar:  [HONEY-SRV-01]                          # hiçbir iş akışında olmayan sunucu/host
```

- Tuzak **hesabın** kullanımı hesabın kendisine değil, kullanımın geldiği yere yazılır: cihaz sahibi → IP kiralaması →
  (ikisi de yoksa) tuzak hesabın kendi kimliği. Hiçbiri çözümlenemezse veya kaynak bir servis hesabıysa olay
  `honeytoken_unattributed.csv` kuyruğuna düşer ve `health.json → uyarilar` içinde sayılır; sessizce kaybolmaz.
- Kural bastırılmaz: yanlış pozitif kaynağı (yedekleme, tarayıcı, indeksleme) servis hesabı olarak işaretlenir veya tuzak
  dağıtımı düzeltilir. Runbook'lar: `RB-HONEY-0018/19/20`.
- Tuzağın taşındığı kaynak (AD, dosya sunucusu) veri kalitesi katmanınca askıya alınmış olsa da gelen tuzak kanıtı geçerlidir
  (kanıt *varlığı* kuralı; `veri_kaynaklari: [tuzak]`).

## Runbook'lar (17.4)

Her kuralın `src/ztp/detection/runbooks/RB-<id>.md` içeriği vardır: amaç, ilk kontroller, yükseltme kriteri,
bilinen yanlış pozitif kalıpları, kapatma. Katalog doğrulaması runbook dosyası olmayan kuralı yüklemez; analist
raporunda her tespit satırı runbook kimliğine bağlanır.

## Sağlık ve idempotentlik kontrol listesi (gece işi)

1. `health.json` → `uyarilar` boş mu (uyarı hacmi ani düşüşü = sistem durmuş olabilir).
2. `son_veri_kalitesi` → askıda kaynak var mı; varsa hangi tespitler atlandı (`kural_sagligi.dq_askida_atlanan`).
3. `metrics.json` → `kural_sagligi.gun30_tetiklenmeyen` (ölü kural), `bastirma.oran` (bastırma kayması).
4. Su seviyesi beklenen güne eşit mi (`state.sqlite` → `watermark`).
5. `honeytoken_unattributed.csv` boş mu; değilse atfedilemeyen tuzak etkileşimleri elle incelenir (kaynak cihaz/IP).
