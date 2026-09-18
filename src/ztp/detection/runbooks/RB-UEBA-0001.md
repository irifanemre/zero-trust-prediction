# RB-UEBA-0001 — Mesai dışı aktivite

**Amaç:** Kullanıcının alışılmış giriş saatinden belirgin sapma veya beklenmedik gece girişi.

## İlk kontroller (analist)
- Girişin cihazı ve kaynağı (VPN mi, ofis mi) — mesai dışı VPN + yeni cihaz birleşimi öncelikli
- Aynı gün dosya/USB/bulut aktivitesi var mı (UEBA-0007/0017/0003 ile korelasyon)
- Takvim: nöbet, proje teslimi, saat dilimi değişikliği (seyahat)

## Yükseltme kriteri
Aynı gün farklı taktikten ikinci tespit varsa veya hassas kaynağa erişildiyse yükselt.

## Bilinen yanlış pozitif kalıpları
- Gece vardiyası/nöbetli roller (baseline zamanla öğrenir; ilk 30 gün akran kıyası)
- Saat dilimi değişen seyahat

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
