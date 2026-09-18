# Prediction katmanı: ölçülebilir olasılık, öğrenen model, ablasyon

Tahmin hedefi (Bölüm 4): *"Bu kullanıcının önümüzdeki 7 gün içinde SOC tarafından doğrulanmış bir vakaya konu olma
olasılığı."* Doğrulama yöntemi: 7 gün sonunda gerçekleşme kontrolü. Bu belge, o kontrolün kodda nasıl yapıldığını anlatır.

## İki sinyal + olasılık

| Sinyal | Yöntem | Kod |
|---|---|---|
| Risk yörüngesi | Günün taze UEBA skoru serisi üzerinde EWMA + 7 günlük eğim (MAD ile normalize); prediction tespitleri seriye geri yazılmaz (kendi kendini besleme yok) | `prediction.PredictionLayer.signals` |
| Rejim değişimi | 30 günlük davranış bileşik serisinde ikili bölütleme changepoint (F istatistiği + robust kayma) | `stats.changepoint_mean_shift` |
| 7 günlük olasılık | Sabit sıralı özellik vektörü → **sezgisel model** (başlangıç) veya **öğrenen lojistik model** | `prediction_model` |

Özellik vektörü (`PREDICTION_FEATURES`): yörünge eğimi, rejim skoru, kısa/uzun EWMA, pozitif gün sayısı, mevcut
yüzdelik, ayrılık bildirimi, yetki değişimi, yeni hesap, 7g USB toplamı, hacim z, 14g hacim eğimi, yeni hassas uygulama.
Sıra sabittir; özellik değişince `MODEL_VERSION` değişir ve eski model yüklenmez (geri alınabilirlik, 14.6).

## Kalibrasyon ölçümü (her koşuda, kontrol grubu dahil)

Her varlık-gün için `(özellikler, p7)` satırı kaydedilir. Gerçekleşme: test verisinde cevap anahtarı penceresi
(senaryo [gün, gün+7] içinde aktif), üretimde analistin `gercek_pozitif` etiketi. `metrics.json → tahmin_kalibrasyonu`:

- **Brier** ve **Brier beceri skoru** (taban oranına göre; negatifse "hep taban oranını söylemek" daha iyidir),
- **AUC** (sıralama gücü), **ECE** (güvenilirlik: "%30 dediğinde %30 mu?"), 10 kutulu güvenilirlik tablosu.

Sentetik 150 kullanıcı / 30 gün koşusunda sezgisel model: AUC 0,83 ama Brier 0,039 > taban 0,018 (beceri −1,14) —
**sıralaması iyi, kalibrasyonu kötü** (aşırı yüksek olasılık veriyor). Bu tam olarak "uydurma katsayı" eleştirisinin
sayısal hâlidir ve modelin neden etiketten öğrenmesi gerektiğini gösterir.

## Öğrenen model (`ztp … --train-prediction`)

- Giriş şartı (14.5): en az `supervised_min_labels` (200) satır, her sınıftan ≥5 örnek.
- **Zamansal holdout:** günlerin son %30'u eğitime girmez; rapor modelin görmediği günler üzerindedir.
- Sınıf ağırlığı yok: amaç kalibre olasılık, dengeleme olasılıkları şişirir.
- Katsayılar JSON'da (`prediction_model.json`, durum deposu `prediction_model`); pickle yok, denetlenebilir.
- Her tahmin "katsayı × standartlaştırılmış özellik" katkılarıyla açıklanır (vaka `tahmin_7g.bilesenler`).

Sentetik koşu, holdout 15 gün / 1658 satır / 13 pozitif:

| | Brier | AUC | ECE |
|---|---|---|---|
| Sezgisel (başlangıç) | 0,038 | 0,952 | 0,108 |
| Lojistik (öğrenen) | **0,016** | **0,993** | **0,028** |
| Taban oranı | 0,008 | — | — |

**CERT r4.2** (1000 kullanıcı, 90 gün, 72.468 varlık-gün, 699 pozitif satır; holdout = son 33 gün, 19.787 satır, 168 pozitif):

| | Brier | Beceri (taban 0,0084) | AUC | ECE |
|---|---|---|---|---|
| Sezgisel (başlangıç) | 0,0251 | **−1,99** (taban orandan kötü) | 0,609 | 0,063 |
| Lojistik (öğrenen, görmediği 33 gün) | **0,0081** | +0,04 | **0,858** | **0,0016** |

Yorum: elle yazılmış katsayılar gerçek veride hem kötü sıralıyor hem aşırı olasılık veriyor; öğrenen model
kalibrasyonu düzeltiyor ve sıralamayı belirgin iyileştiriyor. Beceri skorunun taban orana yakın olması
beklenen bir durumdur: 7 günlük ufukta pozitif oranı %0,8 iken "kimin" değil "ne kadar olası" sorusu zordur —
AUC 0,86 kimin sorusuna cevap verir. Bu rakamlar cevap anahtarı etiket rolündeyken ölçüldü; üretimde etiket
analistten gelir ve aynı rapor `metrics.json → tahmin_kalibrasyonu` altında üretilir.

## Skora etkisi (14.6)

Model olasılığı kural skorunu **ezmez**: `prediction_weight > 0` ise ham skora `weight × p7 × 10` eklenir ve yalnızca
en az bir kural tespiti olan kullanıcıda (tespitsiz kullanıcıya model tek başına puan vermez). Varsayılan 0; ablasyon ve
etiketli kalibrasyon olmadan açılmaz.

## Ablasyon (`ztp … --ablation`, 19.5)

Aynı veri, aynı kod; bir bileşen kapalı: `prediction_yok` (PRED-* gölge), `iliskisel_yok` (REL-* gölge), `carpan_yok`
(13.3 çarpanlar kapalı), `akran_yok` (yalnızca kişisel baseline). Çıktı: kapsama, vaka hacmi, precision@N/@3, erkenlik,
tahmin AUC ve referansa göre Δ. Δ ≈ 0 ise bileşen bu veride değer üretmemiştir — 14.5'e göre devreye alınmaz.

**CERT r4.2 ablasyonu** (`--days 60`, 26 insider, bütçe 10):

| Varyant | Kapsama | Δ | prec@N | Δ | prec@3 | Tahmin AUC |
|---|---|---|---|---|---|---|
| tam (referans) | 16/26 | — | 0,081 | — | 0,189 | 0,640 |
| prediction_yok (PRED-* gölge) | 16/26 | 0 | 0,081 | 0 | 0,189 | 0,640 |
| iliskisel_yok (REL-* gölge) | 16/26 | 0 | 0,081 | 0 | 0,189 | 0,640 |
| carpan_yok | 16/26 | 0 | 0,077 | −0,004 | 0,178 | 0,640 |
| akran_yok | **13/26** | **−0,12** | 0,068 | −0,013 | 0,156 | 0,609 |

Bulgular (dürüst okuma):
- **Akran bağlamı en değerli bileşen**: kapatılınca kapsama 16→13, precision ve tahmin AUC düşüyor. Dokümanın
  "akran kıyası yanlış pozitifi düşüren en etkili sinyallerden biri" iddiası (11.4) bu veride doğrulandı.
- **Prediction kuralları (PRED-0011/12/13/14) CERT'te hiçbir şey katmıyor**: kapatılınca sonuç birebir aynı.
  Sebep açık — 11/13/14 İK sinyali gerektiriyor (CERT'te yok), 12 nadiren tetikleniyor. 14.5'e göre bu kurallar
  bu veride "hak edilmiş" değildir. Öte yandan öğrenen 7g olasılığı AUC 0,86 ile sıralıyor: prediction katmanının
  değeri kurallardan değil, kalibre olasılıktan geliyor. Sonraki adım: `prediction_weight > 0` varyantıyla
  öğrenen modelin kuyruk kalitesine etkisini ölçmek (model önce eğitilip durum deposundan yüklenmeli).
- İlişkisel kurallar (REL-*) bu pencerede fark yaratmadı; çarpanlar küçük ama pozitif katkı sağlıyor.

## Hâlâ eksik olan

- CERT'te İK sinyalleri (ayrılık bildirimi, yetki değişimi, izin takvimi) yoktur → PRED-0011/13/14 gerçek veride ölçülemedi.
- Öğrenen model doğrusal; etkileşimleri (ör. ayrılık × USB) yakalamak için gradient boosting adayıdır — ancak
  açıklanabilirlik (SHAP) ve 200+ etiket şartıyla.
- Kalibrasyon raporu gerçekleşmeyi cevap anahtarından alır; üretimde analist etiketi gecikmeli gelir (7+ gün) — günlük
  modda satırlar durum deposunda bekletilir ve etiket geldikçe değerlendirilir.
