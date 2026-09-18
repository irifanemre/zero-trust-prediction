# RB-UEBA-0017 — Taşınabilir medya anomalisi

**Amaç:** İlk kez USB kullanımı veya günlük/haftalık kullanımda belirgin artış.

## İlk kontroller (analist)
- Kopyalanan dosya sayısı/boyutu ve sınıfı
- Mesai dışı mı
- Cihaz ilkesi: USB izinli rol mü

## Yükseltme kriteri
Hassas dosya + mesai dışı veya ayrılık bildirimi → yükselt.

## Bilinen yanlış pozitif kalıpları
- Saha/teknik roller (baseline zamanla öğrenir)
- Onaylı veri taşıma talepleri

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
