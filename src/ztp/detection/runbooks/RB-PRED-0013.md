# RB-PRED-0013 — Uzun sessizlik sonrası yoğun aktivite

**Amaç:** Kayıtlı izin olmadan uzun aktivitesizlik sonrası patlama.

## İlk kontroller (analist)
- İK: izin/rapor kaydı eksik mi
- Dönüş sonrası erişilen kaynaklar olağan mı
- Hesap dönüşte yeni cihazdan mı kullanıldı

## Yükseltme kriteri
Kayıtsız boşluk + yeni cihaz/hacim → hesap ele geçirme şüphesiyle yükselt.

## Bilinen yanlış pozitif kalıpları
- İK takvimine işlenmemiş izinler (veri kalitesi)

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
