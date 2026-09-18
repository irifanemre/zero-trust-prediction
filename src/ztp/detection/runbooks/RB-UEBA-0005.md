# RB-UEBA-0005 — Yeni cihaz veya konum

**Amaç:** Kişi ve akran için yeni cihaz, ya da başkasına atanmış cihazdan giriş.

## İlk kontroller (analist)
- Cihazın sahibi kim, sahibi o sırada oturum açık mı
- Cihazda ne yapıldı: USB, dosya, keşif süreçleri
- BT talep kaydı var mı (cihaz değişimi)

## Yükseltme kriteri
Başkasına atanmış cihaz + mesai dışı veya USB → yükselt.

## Bilinen yanlış pozitif kalıpları
- Cihaz yenileme dönemleri
- Ortak alan makineleri (paylaşımlı olarak işaretle)

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
