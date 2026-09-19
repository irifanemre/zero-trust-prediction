# RB-HONEY-0020 — Tuzak sunucu / cihaz etkileşimi

**Amaç.** Hiçbir iş akışında kullanılmayan tuzak sunucuya (honeypot host) oturum açıldı veya bağlantı kuruldu:
yanal hareket / iç keşif göstergesi. Deterministik kanıt, bütçeden bağımsız.

**İlk kontroller (15 dk).**
1. Kaynak kullanıcı/cihaz ve protokol (RDP/SMB/SSH). Başarılı mı? Hangi kimlik bilgisiyle?
2. Aynı kaynaktan kısa sürede başka sunuculara bağlantı var mı (tarama deseni → `REL-0015`, `UEBA-0008`)?
3. Kullanıcı ayrıcalıklı mı; hesap yaşı; yeni cihaz/konum tespiti var mı?

**Yükseltme kriteri.** Başarılı oturum VEYA aynı gün ikinci taktikten tespit VEYA ayrıcalıklı hesap.

**Bilinen yanlış pozitif kalıpları.** Zafiyet tarayıcıları, envanter/keşif araçları, izleme sistemleri — servis hesabı
olarak işaretlenir. Tuzağın yanlışlıkla DNS/yük dengeleyici havuzuna alınması.

**Kapatma.** Etiket zorunlu; yanlış pozitifte tuzağın ağdaki konumu gözden geçirilir.
