# RB-REL-0016 — Ortak kaynak erişen riskli kullanıcı kümesi

**Amaç:** Aynı anda riskli çıkan kullanıcılar nadir bir kaynağı paylaşıyor.

## İlk kontroller (analist)
- Kaynak ne, hangi departman
- Kullanıcılar arasında iş ilişkisi var mı
- Kaynak yeni mi oluşturuldu

## Yükseltme kriteri
Kaynak hassas ve ilişki açıklanamıyorsa koordineli faaliyet şüphesiyle yükselt.

## Bilinen yanlış pozitif kalıpları
- Departman içi proje paylaşımları

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
