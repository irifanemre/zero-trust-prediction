"""Kimlik eşleştirme katmanı (8.2 / 11.2) ve takma adlaştırma (20.1, ADR-008)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

import pandas as pd

LOG = logging.getLogger(__name__)


class IdentityResolver:
    def __init__(self, directory: pd.DataFrame, ip_leases: pd.DataFrame):
        self.alias: Dict[Tuple[str, str], str] = {}
        for r in directory.itertuples(index=False):
            sid = r.sid
            for src, raw in (
                ("ad", r.ad_sam),
                ("file_server", r.ad_sam),
                ("vpn", r.vpn_user),
                ("dlp", r.upn),
                ("edr", sid),
                ("ad", r.upn),
                ("hr", sid),
                ("*", r.ad_sam),
                ("*", r.upn),
                ("*", r.vpn_user),
                ("*", sid),
            ):
                if isinstance(raw, str):
                    self.alias[(src, raw.lower())] = sid  # ("*", raw): kaynak bağımsız yedek eşleme (ör. CERT'te aktör = user_id)
        self.leases = ip_leases.copy()
        self.service_sids: Set[str] = set(directory.loc[directory.is_service.astype(bool), "sid"])
        self.unresolved_by_source: Dict[str, int] = {}
        self.unresolved_queue = pd.DataFrame()

    def resolve(self, events: pd.DataFrame) -> pd.DataFrame:
        ev = events.copy()
        raws = ev["actor_raw"].astype(str).str.lower().values
        ev["canonical"] = [
            self.alias.get((src, raw)) or self.alias.get(("*", raw)) for src, raw in zip(ev["source"].values, raws)
        ]
        # Proxy: aktör = IP → kiralama tablosu üzerinden zaman aralıklı eşleme (DHCP değişir; anlık eşleme yanlış kişiye yazar)
        mask = ev["source"].eq("proxy") & ev["canonical"].isna()
        if mask.any() and not self.leases.empty:
            px = ev.loc[mask, ["event_id", "src_ip", "time"]].merge(self.leases, left_on="src_ip", right_on="ip", how="inner")
            px = px[(px["time"] >= px["start"]) & (px["time"] < px["end"])].drop_duplicates("event_id")
            ev.loc[mask, "canonical"] = ev.loc[mask, "event_id"].map(px.set_index("event_id")["sid"])
        ev["is_service"] = ev["canonical"].isin(self.service_sids)
        unres = ev[ev["canonical"].isna()]
        self.unresolved_by_source = unres.groupby("source").size().to_dict()
        self.unresolved_queue = unres[["event_id", "source", "actor_raw", "src_ip", "time"]].head(2000)
        LOG.info("Kimlik eşleştirme: %d olay, çözümlenemeyen=%s", len(ev), self.unresolved_by_source)
        return ev


class Pseudonymizer:
    """20.1 Takma adlaştırma varsayılandır (ADR-008). Analist U-4471 görür; gerçek kimlik yalnızca break-glass ile açılır."""

    def __init__(self, secret: str, audit_path: Optional[Path] = None):
        self.secret = secret.encode()
        self.forward: Dict[str, str] = {}
        self.reverse: Dict[str, str] = {}
        self.audit_path = audit_path

    def pseudo(self, sid: str) -> str:
        if sid in self.forward:
            return self.forward[sid]
        h = int(hmac.new(self.secret, sid.encode(), hashlib.sha256).hexdigest(), 16)
        code = h % 10000
        while f"U-{code:04d}" in self.reverse:
            code = (code + 1) % 10000
        p = f"U-{code:04d}"
        self.forward[sid], self.reverse[p] = p, sid
        return p

    def break_glass(self, pseudonym: str, analyst: str, approver: str, reason: str) -> Optional[str]:
        """Kimlik açma: ikinci onay zorunlu, işlem loglanır (20.1 Break-glass, erişim ayrımı)."""
        if not approver or approver == analyst:
            raise PermissionError("Break-glass için analistten farklı ikinci onaylayan gerekir.")
        sid = self.reverse.get(pseudonym)
        rec = dict(
            ts=pd.Timestamp.utcnow().isoformat(),
            islem="break_glass",
            takma_ad=pseudonym,
            analist=analyst,
            onaylayan=approver,
            gerekce=reason,
            sonuc=("acildi" if sid else "bulunamadi"),
        )
        if self.audit_path:
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return sid
