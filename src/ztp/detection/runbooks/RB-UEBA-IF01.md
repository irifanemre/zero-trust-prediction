# RB-UEBA-IF01 — Isolation Forest destek

**Amaç:** Çok değişkenli, tanımlanmamış türden sapma (gölge mod).

## İlk kontroller (analist)
- Katkı listesi (hangi özellikler)
- Aynı gün kural tabanlı tespit var mı

## Yükseltme kriteri
Tek başına yükseltilmez; ablasyonla değer ürettiği ölçülmeden skora girmez.

## Bilinen yanlış pozitif kalıpları
- Aykırı ama meşru roller (sistem yöneticileri)

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
