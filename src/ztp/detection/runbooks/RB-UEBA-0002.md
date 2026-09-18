# RB-UEBA-0002 — İlk kez görülen uygulama

**Amaç:** Kişi (ve hassas kategorilerde akran) için daha önce görülmemiş uygulama/kategori kullanımı.

## İlk kontroller (analist)
- Kategori: bulut depolama / iş arama / saldırı aracı ise doğrudan bağlamı sor
- Hacim ve tekrar: tek ziyaret mi, sürekli mi
- Ayrılık bildirimi / İK sinyali var mı

## Yükseltme kriteri
Hassas kategori + hacim artışı veya USB birleşimi → yükselt.

## Bilinen yanlış pozitif kalıpları
- Yeni proje/araç geçişleri (takım genelinde aynı gün görülür)
- Reklam yönlendirmeleri

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
