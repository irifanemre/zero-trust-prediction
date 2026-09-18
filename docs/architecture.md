# Mimari

Bu belge, referans mimari dokümanındaki bölümlerin kodda nereye karşılık geldiğini, mimari kararları (ADR) ve
bilinen sınırları özetler. Doküman bölüm numaraları köşeli parantez içinde verilmiştir.

## Katmanlar ve modüller

| Bölüm | Konu | Modül / sınıf |
|---|---|---|
| 7.2 | Katman akışı | `pipeline.ZeroTrustPredictionPipeline._run_day` |
| 8.1 | OCSF şeması | `schema.EVENT_COLUMNS`, `OCSF_*` |
| 8.2 / 11.2 | Varlık çözümleme: kanonik SID, zaman aralıklı IP→kullanıcı, çözümlenmemiş kuyruk, servis hesapları | `identity.IdentityResolver` |
| 8.3 | Veri kalitesi: kaynak askıya alma, geç olay, saat dilimi, takvim etkisi | `quality.DataQualityMonitor` + `detection.engine.DetectionEngine.evaluate` |
| 9.1 | Akran grubu: yapısal (min 8, üst seviyeye çıkma), davranışsal (30 gün) | `peers.PeerGroups` |
| 9.2 | Hesap yaşına göre ağırlık; akran ağırlığı hiç sıfırlanmaz; 7g/90g zehirleme şüphesi | `stats.age_weights`, `stats.drift_suspicion`, `profile.ProfileEngine.signals` |
| 9.3 / 17.2 | Rol değişimi sıfırlaması, izin takvimi | `profile.ProfileEngine.context`, `prediction.PredictionLayer.signals` |
| 10.1–10.7 | Robust z, Poisson/NegBin, dairesel, EWMA, mevsimsellik, Jaccard, changepoint | `stats` |
| 11.3 / 14.3 | Graf soyutlaması, bilgi/gözlem grafı ayrımı | `graph.store`, `graph.knowledge`, `graph.observation` |
| 11.4 | UEBA üç bileşen | `profile.ProfileEngine` |
| 11.5 / 4 | Prediction: yörünge + rejim, 7 günlük ufuk | `prediction.PredictionLayer` |
| 11.6 | Derin graf analizi (riskli alt küme) | `graph.analysis.DeepGraphAnalyzer` |
| 12.1 | Detection-as-code | `detection/rules/*.yaml`, `detection.catalog`, `detection.expr.SafeExpr` |
| 12.2 | Tespit 1–16 (+17, IF01) | `detection/rules/` |
| 12.5 | Bastırma | `config.TenantConfig.suppressions`, `DetectionEngine._suppressed` |
| 13.2–13.5 | Skor formülü, çarpanlar, yüzdelik kalibrasyon, alarm bütçesi | `scoring.RiskScorer` |
| 13.6 | Gölge mod | `durum: golge-modda` → `shadow_log.jsonl` |
| 7.3 | Kademeli müdahale; tahmin engellemez | `response` |
| 15 | LLM yalnızca raporlamada; kanıta bağlı; şablon yedek; çıktı doğrulaması; injection'a kapalı istem; RAG bilgi tabanı | `reporting.llm`, `reporting.sanitize`, `reporting.rag`, `reporting.template` |
| 18 | Analist arayüzü | `reporting.template.TemplateReporter` |
| 11.8 / 17.3 | Etiket deposu, FP sebebi zorunlu, ×0.2 çarpanı | `feedback.LabelStore` |
| 17.5 | Sistem sağlığı | `metrics.HealthMonitor` |
| 19.4 / 19.6 | Ölçüm, kapsama/erkenlik kanıtı, precision@k | `metrics.MetricsCollector` |
| 20.1 | Takma ad, break-glass, erişim ayrımı | `identity.Pseudonymizer` |
| 21.2 | Eşik keşfine karşı rastgeleleştirme | `detection.expr.SafeExpr.compile(jitter)` |
| 17.1 | Çok müşterili yapı | `config.TenantConfig`, çıktı `ztp_out/<tenant>/` |

## Bağımlılık yönü

```
schema, stats
   └─▶ features, identity, quality, graph.store/knowledge/observation, data.*
          └─▶ peers ─▶ profile ─▶ prediction
          └─▶ detection.expr ─▶ detection.engine ─▶ scoring ─▶ graph.analysis
                                                       └─▶ reporting.template ─▶ reporting.llm
                                                       └─▶ metrics
                                                             └─▶ pipeline ─▶ cli
```

`detection.engine` raporlama katmanını bilmez: açıklama üretici (`describe`) boru hattı tarafından enjekte edilir.
`graph.analysis` derin analizde yalnızca `graph.store` arayüzünü kullanır; NetworkX yerine başka bir depo koymak
`GraphStore` uygulamasını değiştirmekle sınırlıdır (ADR-003).

## Mimari karar kayıtları

| ADR | Karar | Kodda |
|---|---|---|
| 001 | Ana dedektör kişisel robust baseline; Isolation Forest destek | `profile.ProfileEngine`, `UEBA-IF01` gölge modda |
| 002 | LLM skorlama yolunda yer almaz | `reporting.llm` yalnızca vaka özeti üretir |
| 003 | Graf erişimi soyutlama arkasında | `graph.store.GraphStore` |
| 004 | CERT birincil doğrulama; sentetik veri regresyon için | `data.cert`, `data.synthetic` |
| 005 | Sabit eşik yerine alarm bütçesi | `scoring.RiskScorer.select_queue` |
| 006 | Saat verisinde dairesel istatistik | `stats.circular_stats` |
| 007 | Akran ağırlığı hiç sıfırlanmaz | `stats.age_weights` |
| 008 | Takma adlaştırma varsayılan | `identity.Pseudonymizer` |
| 009 | RAG yalnızca analist bağlamı/raporlama için | (skorlamada kullanılmaz) |
| 010 | Tahmin otomatik engelleme üretmez | `response.authorize_containment` |

## Bilinen sınırlar ve yol haritası

1. **Kalıcı durum yok.** Baseline, tespit geçmişi, yüzdelik havuzu ve açık vakalar her koşuda yeniden hesaplanır.
   Günlük servis için depo katmanı (Parquet/DuckDB) ve artımlı baseline gerekir.
2. **Öğrenen sıralama yok.** 200 etiket eşiği sağlandığında kural skorunun üstüne eklenen (onu ezmeyen) denetimli
   sıralayıcı — bugün yalnızca hazırlık bayrağı var.
3. **Prediction katmanı gerçek veride kısmen doğrulandı.** CERT'te İK sinyalleri (yetki değişimi, ayrılık bildirimi,
   izin takvimi) bulunmadığından PRED-0011/13/14 yalnızca sentetik veride sınandı. Ablasyon koşusu otomatik değil.
4. **Döngüsel doğrulama riski.** Kurallar r4.2 sonuçları görüldükten sonra ayarlandı; yansız ölçüm için r5.2/r6.2'de
   tekrar gerekir.
5. **Bilgi grafı örnek alt küme.** ATT&CK STIX beslemesi ve tehdit istihbaratı entegrasyonu yok.
6. **Gizlilik iskelet düzeyinde.** Kimlik kasası düz dosya; saklama süreleri ve silme hakkı uygulanmadı; rol ayrımı
   zorlanmıyor.
7. **Entegrasyon yok.** Çıktı dosya tabanlı; SOAR/ticketing bağlantısı ve runbook içerikleri eksik.
8. **Ölçek.** 1000 kullanıcı × 111 gün ≈ 8 dk (tek makine). Her gün 90 günlük pencere yeniden hesaplanır; artımlı
   istatistik ve vektörleştirme ile 5–10× kazanç mümkün.
