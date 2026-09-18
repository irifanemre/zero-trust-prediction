# RB-PRED-0011 — Yetki artışı sonrası davranış kayması

**Amaç:** Yeni yetki iş tanımıyla ilgisiz alanlarda kullanılıyor.

## İlk kontroller (analist)
- Yetki talebinin gerekçesi ve kapsamı
- Erişilen kaynaklar gerekçeyle örtüşüyor mu
- Yetki geçici mi, süresi doldu mu

## Yükseltme kriteri
Gerekçe dışı kritik varlık erişimi → yükselt ve yetkiyi gözden geçirt.

## Bilinen yanlış pozitif kalıpları
- Geçiş dönemi görev devri
- Kapsamı geniş tanımlanmış roller

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
