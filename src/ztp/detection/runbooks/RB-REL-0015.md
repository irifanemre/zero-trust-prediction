# RB-REL-0015 — Paylaşılan cihaz üzerinden yayılma

**Amaç:** Paylaşılan cihaz üzerinden kritik varlığa zaman-sıralı yol.

## İlk kontroller (analist)
- Yoldaki diğer kullanıcılar riskli mi
- Cihazda kimlik bilgisi hırsızlığı işareti (keylogger/süreç)
- Kritik varlığa erişim yetkisi var mıydı

## Yükseltme kriteri
Yetkisiz kritik varlık erişimi → yükselt; cihazı inceleme kapsamına al.

## Bilinen yanlış pozitif kalıpları
- Ortak alan makineleri
- Yetkili yönetici hesapları

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
