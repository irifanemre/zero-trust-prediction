# CERT Insider Threat Test Dataset ile doğrulama

Kaynak: Software Engineering Institute / CMU, *Insider Threat Test Dataset*, https://doi.org/10.1184/R1/12841247 (CC BY 4.0).
Sentetik olarak üretilmiş 1000 kullanıcılık bir kurumun logon / device / http / email / file kayıtları ve kırmızı takım
senaryolarının cevap anahtarı (`answers/insiders.csv`).

## Veri eşlemesi

| CERT dosyası | OCSF-lite | Not |
|---|---|---|
| `logon.csv` | Authentication (3002), kaynak `ad` | `DTAA/XXX0001` öneki kanonik kimliğe indirgenir |
| `device.csv` (Connect) | File (1001), kaynak `dlp`, `usb_copy` | Kullanıcı bazlı normal USB oranı vardır |
| `http.csv` | HTTP (4002), kaynak `proxy` | URL saklanmaz; **kategori** (cloud_storage, job_search, hacking_tools, …) |
| `email.csv` (r4.2+) | Email (4009), kaynak `email` | `size` → bytes_out; dış alıcı → `email_external` |
| `file.csv` (r4.2+) | File (1001), kaynak `file_server` | Taşınabilir medyaya kopya; dosya adı yerine uzantı kategorisi |
| `LDAP/*.csv` | İK/AD dizini | Aylık anlık görüntüler → işe giriş/ayrılış; departman → akran grubu |
| `psychometric.csv` | **okunmaz** | Kişilik verisi skorlamaya girmez (etik sınır / amaçla sınırlılık) |

## r4.2 koşusu

```
ztp --cert-dir cert_data/r4.2 --end 2010-11-30 --days 90 --budget 10 --tenant cert-r42 --out ./ztp_out
```

- 1000 kullanıcı, 13.261.768 olay (pencere: 14 May – 30 Kas 2010; değerlendirme 2 Eyl – 30 Kas), 134.835 varlık-gün
- Mevcut kaynaklar: ad, dlp, email, file_server, proxy (+hr). EDR/VPN yok → DQ-0010 devre dışı (kademeli işlevsellik)
- Süre: ≈ 8 dk (tek makine, Python)

### Kapsama (cevap anahtarı, 34 insider)

| Senaryo | n | Sonuç | Tetiklenen kurallar (tipik) | Medyan erkenlik |
|---|---|---|---|---|
| 1 — mesai dışı giriş + USB + wikileaks, ayrılış | 14 | 14/14 kuyrukta | UEBA-0001, 0007, 0017, 0002; farklı-taktik çarpanı ×2.5 | 8 gün |
| 2 — iş arama siteleri + USB artışı, ayrılış | 17 | 10/11 (6 senaryo kısmi pencere) | UEBA-0017 (7g kümülatif), 0002, PRED-0012 | 20 gün |
| 3 — sysadmin keylogger, amirin makinesi | 3 | 2/3 (1 bütçe dışı) | UEBA-0005 (başkasına atanmış cihaz), 0002 (hacking_tools) | 6 gün |

"Erkenlik" = senaryo bitişi − ilk kuyruk girişi (gün).

### Precision (cevap anahtarı etiket rolünde)

| Ölçüm | Değer |
|---|---|
| precision@1 | 0,39 |
| precision@3 | 0,22 |
| precision@5 | 0,14 |
| precision@10 (= bütçe) | 0,09 |
| Kuyruğa giren kullanıcı / insider | 263 / 27 (0,10) |

Yorum: bütçe her gün dolar; aktif insider olmayan günlerde kuyruk tek-sinyalli benign kullanıcılarla doldurulur.
Bu, sabit eşik yerine kapasite tabanlı kuyruk tasarımının bilinçli sonucudur ("sessiz günlerde kapsama"). Analist
kapasitesi 3 ise precision 0,22'ye çıkar; hangi N'in doğru olduğu ürün değil operasyon kararıdır.

## Prediction katmanı kalibrasyonu (r4.2, `--train-prediction`)

7 günlük olasılığın gerçekleşmeyle karşılaştırılması (cevap anahtarı etiket rolünde; zamansal holdout = son 33 gün):
sezgisel model AUC 0,61 / Brier 0,025 (taban 0,0084'ten kötü); öğrenen lojistik model AUC **0,86** / Brier **0,0081** /
ECE 0,0016. Ayrıntı ve yorum: `docs/prediction.md`.

## r1 koşusu (gürültü tabanı)

r1'in cevap anahtarı yoktur; 1000 benign kullanıcıda günde ≈ 7,8 vaka üretildi (bütçe 10). r1'in http hacmi aşırı
düzensizdir (bir gün 205 bin, ertesi gün 139 satır); veri kalitesi katmanı proxy'yi o günlerde askıya aldı — beklenen davranış.

## CERT'in ortaya çıkardığı tasarım düzeltmeleri

1. Paylaşımlı lab makineleri "yeni cihaz" sayılıyordu → akran cihaz kümesi, cihaz sahipliği (atanmış PC), akran
   taban-oranıyla ölçeklenen şiddet.
2. Günlük Poisson eşiğinin altında kalan USB artışı (2→5-7/gün) → **7 günlük kümülatif pencere** (eşik altı kalmaya karşı önlem).
3. İlk giriş saati normalken gece tekrar giriş → mesai dışı giriş sayısı sinyali.
4. Tatilde tüm kaynakların birlikte düşmesi → takvim etkisi; tek kaynak düşüşü → toplama bozulması.
5. Açık vaka yeni kanıt gelmeden yeniden kuyruğa alınmaz.
6. Tespit açıklamaları tespit anındaki bağlamla saklanır (bir hafta sonraki bağlamla yazılmaz).

## Sınırlar

- Kurallar r4.2 sonuçları görüldükten sonra ayarlandı → **döngüsel doğrulama riski**; yansız rakam için r5.2/r6.2'de tekrar.
- CERT'te İK sinyalleri, EDR ve coğrafi konum yoktur; PRED-0011/13/14, UEBA-0004/0006 ve DQ-0010 bu veride sınanamaz.
- http `content` alanı okunmaz; bayt hacmi yalnızca e-posta boyutundan gelir.
