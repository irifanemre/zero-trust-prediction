# RB-UEBA-0008 — Hesap yaşı × keşif yoğunluğu

**Amaç:** Yeni hesabın akrandan belirgin geniş/yoğun keşif yapması.

## İlk kontroller (analist)
- Erişilen kaynaklar iş tanımıyla ilgili mi
- Keşif süreçleri (whoami/net/nltest) hangi cihazda
- İşe alım kaynağı ve yöneticisiyle doğrula

## Yükseltme kriteri
İş tanımı dışı kritik varlıklara erişim varsa yükselt.

## Bilinen yanlış pozitif kalıpları
- Oryantasyon dönemi geniş erişim
- BT/güvenlik rolleri (keşif normal)

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
