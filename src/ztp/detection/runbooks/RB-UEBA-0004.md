# RB-UEBA-0004 — İmkânsız seyahat

**Amaç:** Ardışık girişler arasında fiziksel olarak mümkün olmayan hız.

## İlk kontroller (analist)
- İki girişin kaynağı: VPN çıkış noktası, mobil operatör, proxy
- Aynı anda iki oturum açık mı
- Kullanıcıya doğrulama: seyahatte mi

## Yükseltme kriteri
VPN çıkış noktasıyla açıklanamıyorsa hesap ele geçirme varsayımıyla yükselt.

## Bilinen yanlış pozitif kalıpları
- Kurumsal VPN/CDN çıkış noktaları
- Mobil ağ coğrafi hataları

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
