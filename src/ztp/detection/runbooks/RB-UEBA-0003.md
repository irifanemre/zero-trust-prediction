# RB-UEBA-0003 — Anormal veri çıkış hacmi

**Amaç:** Kişisel/akran baseline'ına göre veri çıkış hacminde sıçrama.

## İlk kontroller (analist)
- Hedef: hangi uygulama/alan adı, kurum onaylı mı
- Dosya kaynağı: hangi paylaşımlardan, hassas mı
- Zehirleme şüphesi bayrağı varsa 90 günlük eğilime bak

## Yükseltme kriteri
Bulut depolama/kişisel e-posta hedefli ve hassas kaynak kaynaklıysa yükselt.

## Bilinen yanlış pozitif kalıpları
- Yedekleme, toplu rapor dönemleri (ekip geneli aynı gün)
- Büyük dosya transferi gerektiren roller

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
