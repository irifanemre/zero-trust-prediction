# RB-HONEY-0018 — Tuzak hesap kullanımı

**Amaç.** Meşru kullanımı olmayan bir hesap (tuzak AD hesabı, tuzak servis hesabı, tuzak API anahtarı kimliği) kullanıldı.
Bu tespit istatistiksel değildir: baseline yoktur, tek etkileşim yeterlidir, alarm bütçesinden bağımsızdır.

**İlk kontroller (15 dk).**
1. Kanıt olaylarındaki kaynak cihaz ve IP kimin? Vaka, tuzak hesabın kendisine değil bu kaynağa atfedilmiştir
   (`baglam.tuzak_varliklar`, `tespitler[].kanit`). Cihaz sahibi ile eşleşiyor mu, yoksa paylaşımlı/yabancı cihaz mı?
2. Oturum başarılı mı, başarısız mı? Başarısız deneme de tuzak kimliğinin **bilindiğini** gösterir (parola dökümü,
   kimlik bilgisi sızıntısı).
3. Aynı kaynaktan son 7 günde başka tespit var mı (keşif, yeni cihaz, mesai dışı)?

**Yükseltme kriteri.** Başarılı oturum VEYA aynı gün ikinci taktikten tespit → olay yönetimine devir; kimlik açma
(break-glass) ikinci onayla.

**Bilinen yanlış pozitif kalıpları.** Kırmızı takım tatbikatı (takvimle doğrulanır); tuzak hesabın yanlışlıkla bir
gruba/otomasyona eklenmesi (ilk etkileşimde tuzağın dağıtımı gözden geçirilir). Kural bastırılmaz; tuzak düzeltilir.

**Kapatma.** Etiket zorunlu; yanlış pozitifte sebep "tuzak_dagitim_hatasi" veya "tatbikat".
