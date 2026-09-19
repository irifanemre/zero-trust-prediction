# RB-HONEY-0019 — Tuzak dosya / paylaşım erişimi

**Amaç.** Kimsenin işi için gerekmeyen tuzak dosya veya paylaşım (ör. `\\FS\finans\bonus_listesi.xlsx`) açıldı/okundu.
Deterministik kanıt; baseline ve akran kıyası uygulanmaz.

**İlk kontroller (15 dk).**
1. Erişim türü (okuma / kopyalama / listeleme) ve hacim; aynı oturumda başka hassas kaynaklara erişim var mı?
2. Kullanıcı tuzağın bulunduğu dizine normalde erişir mi (dizin gezinme sırasında tıklama) yoksa doğrudan yol ile mi geldi?
   Doğrudan yol = önceden keşif.
3. Mesai dışı, yeni cihaz, USB veya bulut yükleme tespitleriyle birleşiyor mu (zincir davranışı)?

**Yükseltme kriteri.** Kopyalama/dışa aktarma VEYA aynı gün farklı taktikten ikinci tespit.

**Bilinen yanlış pozitif kalıpları.** Yedekleme, antivirüs tarama, arama indeksleme servis hesapları — bunlar dizinde
`is_service` olarak işaretlenir (atfedilemeyen kuyruğuna düşer, kural bastırılmaz). Dizin senkronizasyon araçları.

**Kapatma.** Etiket zorunlu; tuzak yolu değiştirilmez, gerekirse tuzak listesi güncellenir.
