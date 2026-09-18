# RB-UEBA-0006 — Başarısız giriş yığını

**Amaç:** Kısa sürede beklentinin çok üstünde başarısız giriş.

## İlk kontroller (analist)
- Ardından başarılı giriş var mı (kaba kuvvet başarısı)
- Kaynak IP/cihaz kullanıcının mı
- Parola değişikliği sonrası eski oturumlar

## Yükseltme kriteri
Başarısız yığın + başarılı giriş + yeni cihaz → yükselt.

## Bilinen yanlış pozitif kalıpları
- Parola değişikliği sonrası önbelleklenmiş kimlik bilgileri
- Servis hesabı yapılandırma hataları

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
