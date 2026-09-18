# RB-PRED-0012 — Risk yörüngesinde sürekli artış

**Amaç:** Günlük UEBA sinyali birkaç gündür yükseliyor.

## İlk kontroller (analist)
- Seriyi oluşturan tespitler hangileri
- Tek kaynaklı mı, farklı taktiklerden mi
- İK sinyali (ayrılık, yetki) var mı

## Yükseltme kriteri
Farklı taktiklerden artan seri → yükselt.

## Bilinen yanlış pozitif kalıpları
- Proje kapanışı gibi dönemsel yoğunluklar (akran serisiyle karşılaştır)

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
