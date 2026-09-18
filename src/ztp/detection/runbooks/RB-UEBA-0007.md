# RB-UEBA-0007 — Mesai dışı toplu dosya erişimi

**Amaç:** Mesai dışında dosya erişim sayısında Poisson beklentisinin çok üstünde artış.

## İlk kontroller (analist)
- Hangi paylaşımlar; hassas sınıflandırma
- Dosya işlemleri: okuma mı kopyalama mı; USB/bulut takibi
- Yedekleme/otomasyon hesabı mı

## Yükseltme kriteri
Hassas paylaşım + kopyalama + dışa aktarım kanalı → yükselt.

## Bilinen yanlış pozitif kalıpları
- Bakım pencereleri (bastırma penceresi tanımla)
- Toplu taşıma projeleri

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
