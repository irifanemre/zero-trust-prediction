"""OCSF-lite olay şeması ve ortak sabitler — 8.1 (kaynak bağımsızlığı: analiz katmanı yalnızca bu kolonları görür)."""

from __future__ import annotations

import math

import pandas as pd

DAY = pd.Timedelta(days=1)
OCSF_AUTH, OCSF_PROCESS, OCSF_FILE, OCSF_NETWORK, OCSF_HTTP, OCSF_EMAIL = 3002, 1007, 1001, 4001, 4002, 4009

EVENT_COLUMNS = [
    "event_id",
    "time",
    "received_time",
    "class_uid",
    "source",
    "actor_raw",
    "device",
    "src_ip",
    "country",
    "resource",
    "app",
    "action",
    "outcome",
    "bytes_out",
    "process",
    "parent_process",
    "cmdline",
    "category",
]
# 11.1 Kaynak adları (tespit tanımlarındaki 'veri_kaynaklari' → gerçek kaynak)
SOURCE_ALIAS = {
    "ad_oturum": "ad",
    "ad": "ad",
    "ik": "hr",
    "hr": "hr",
    "proxy": "proxy",
    "edr": "edr",
    "vpn": "vpn",
    "dosya_sunucu": "file_server",
    "file_server": "file_server",
    "dlp": "dlp",
    "risk_serisi": "_internal",
    "graf": "_internal",
    "eposta": "email",
    "email": "email",
}
RECON_PROCESSES = {"whoami.exe", "net.exe", "nltest.exe", "nslookup.exe", "dsquery.exe", "adfind.exe"}
RECON_CMD_HINTS = ("Get-ADUser", "net group", "net view", "/dclist", "whoami /all", "-type=srv")
CLOUD_APPS = {"personal_cloud", "file_transfer", "webdav", "paste_site", "cloud_storage"}
# Kişisel "ilk kez" tek başına anlamlı olan hassas uygulama kategorileri (akran kullansa bile): sızıntı kanalı, iş arama, saldırı aracı
SENSITIVE_APPS = CLOUD_APPS | {"job_search", "hacking_tools"}
COUNTRY_COORDS = {
    "TR": (39.0, 35.0),
    "DE": (51.0, 10.0),
    "NL": (52.3, 4.9),
    "GB": (51.5, -0.1),
    "US": (38.9, -77.0),
    "RU": (55.7, 37.6),
    "AE": (24.4, 54.4),
    "FR": (48.9, 2.3),
}


def haversine_km(a: str, b: str) -> float:
    if a not in COUNTRY_COORDS or b not in COUNTRY_COORDS:
        return 3000.0
    (la1, lo1), (la2, lo2) = COUNTRY_COORDS[a], COUNTRY_COORDS[b]
    p1, p2 = math.radians(la1), math.radians(la2)
    dphi, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def to_utc_naive(s: pd.Series) -> pd.Series:
    """8.3: UTC / yerel saat karışması klasik hata kaynağıdır — her şey UTC'ye çekilir (tz bilgisi düşürülür)."""
    s = pd.to_datetime(s, utc=True)
    return s.dt.tz_convert("UTC").dt.tz_localize(None)
