"""Kademeli müdahale — 7.3: engelleme kararı tahmine değil, doğrulanmış tespite ve insan kararına bağlanır (ADR-010)."""

from __future__ import annotations

from typing import Optional, Tuple


def tiered_response(combined: float, critical: bool) -> dict:
    if critical or combined >= 85:
        return dict(seviye="Yüksek", aksiyon="Analiste vaka açılır; insan değerlendirmesi", kullanici_etkisi="Yok (arka planda)")
    if combined >= 65:
        return dict(
            seviye="Orta", aksiyon="Hassas kaynaklara erişimde ek doğrulama (step-up MFA) önerisi", kullanici_etkisi="Sınırlı"
        )
    return dict(seviye="Düşük", aksiyon="İzleme sıklığının artırılması, ek log toplama", kullanici_etkisi="Yok")


def authorize_containment(case: dict, label: Optional[dict]) -> Tuple[bool, str]:
    """Erişim kısıtlama/engelleme YALNIZCA doğrulanmış olay (analist: gerçek_pozitif) + yetkili insan kararıyla."""
    if not label or label.get("karar") != "gercek_pozitif":
        return False, "Engelleme reddedildi: doğrulanmış olay yok (tahmine dayalı engelleme yapılmaz — 7.3)."
    return True, f"Doğrulanmış olay ({label['analist']}): erişim kısıtlama yetkili insan onayıyla uygulanabilir."
