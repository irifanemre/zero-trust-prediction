# RB-PRED-0014 — Ayrılık öncesi davranış deseni

**Amaç:** Ayrılık bildirimi sonrası hacim artışı / bulut / USB.

## İlk kontroller (analist)
- Ayrılış tarihi ve erişim kısıtlama planı
- Alınan verinin sınıfı
- Yönetici bilgilendirmesi

## Yükseltme kriteri
Hassas veri + dış kanal → İK ve hukukla koordineli yükselt.

## Bilinen yanlış pozitif kalıpları
- Devir-teslim amaçlı meşru veri paketleme (yöneticiyle doğrula)

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
