"""Boru hattına verilen veri paketi."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import pandas as pd


@dataclass
class Dataset:
    name: str
    directory: (
        pd.DataFrame
    )  # İK/AD dizini: sid, ad_sam, upn, vpn_user, primary_device, dept, title_level, location, hire_date, ...
    ip_leases: pd.DataFrame  # (ip, sid, start, end) — IP→kullanıcı eşlemesi ZAMAN ARALIKLIDIR (8.2)
    events: pd.DataFrame  # OCSF-lite olaylar
    leaves: pd.DataFrame  # devamsızlık takvimi (9.3 uzun izin dönüşü)
    ground_truth: List[dict]  # enjekte edilen senaryolar (kapsama/erkenlik ölçümü için)
    critical_assets: List[str]
    honeytokens: Dict[str, List[str]] = field(default_factory=dict)  # aldatma katmanı tuzakları (yapılandırma ezer)
