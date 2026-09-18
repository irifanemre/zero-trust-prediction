# RB-UEBA-0009 — Akran grubundan yapısal sapma

**Amaç:** Kullanıcının 7 günlük profili akran grubundan çok değişkenli olarak uzak.

## İlk kontroller (analist)
- Hangi özellikler sapıyor (katkı listesi)
- Rol/proje değişikliği var mı
- Gölge modda: precision ölçümü için etiketle

## Yükseltme kriteri
Tek başına yükseltilmez; başka tespitle birleşince değerlendirilir.

## Bilinen yanlış pozitif kalıpları
- Rol değişimi sonrası geçiş dönemi
- Küçük akran grupları

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
