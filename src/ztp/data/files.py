"""Dosya tabanlı veri girişi (günlük servis modu): OCSF-lite olaylar + İK/AD dizini + IP kiralama + izin takvimi.

CSV veya Parquet. Şema doğrulanır; eksik zorunlu kolon açık hata verir (sessizce yanlış çalışma yok — 8.3 ilkesi)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import pandas as pd

from ztp.data.dataset import Dataset
from ztp.schema import EVENT_COLUMNS

REQUIRED_EVENT_COLUMNS = ("event_id", "time", "source", "actor_raw")
REQUIRED_DIRECTORY_COLUMNS = ("sid", "ad_sam", "upn", "dept", "hire_date")
DIRECTORY_DATE_COLUMNS = ("hire_date", "resignation_notice_date", "resignation_date", "role_change_date", "privilege_grant_date")


def _read(path: Union[str, Path]) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    if p.suffix.lower() in (".parquet", ".pq"):
        return pd.read_parquet(p)
    return pd.read_csv(p)


def load_events_file(path: Union[str, Path]) -> pd.DataFrame:
    df = _read(path)
    missing = [c for c in REQUIRED_EVENT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Olay dosyasında zorunlu kolon eksik: {missing} ({path})")
    for c in EVENT_COLUMNS:
        if c not in df.columns:
            df[c] = None
    df["time"] = pd.to_datetime(df["time"])
    df["received_time"] = (
        pd.to_datetime(df["received_time"]).fillna(df["time"]) if df["received_time"].notna().any() else df["time"]
    )
    df["bytes_out"] = pd.to_numeric(df["bytes_out"], errors="coerce").fillna(0).astype("int64")
    df["class_uid"] = pd.to_numeric(df["class_uid"], errors="coerce").fillna(0).astype(int)
    df["outcome"] = df["outcome"].fillna("success")
    df["action"] = df["action"].fillna("")
    return df[EVENT_COLUMNS].sort_values("time").reset_index(drop=True)


def load_directory_file(path: Union[str, Path]) -> pd.DataFrame:
    df = _read(path)
    missing = [c for c in REQUIRED_DIRECTORY_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Dizin dosyasında zorunlu kolon eksik: {missing} ({path})")
    for c in ("vpn_user", "primary_device", "display_name", "location"):
        if c not in df.columns:
            df[c] = df["sid"] if c in ("vpn_user", "display_name") else None
    for c in ("title_level",):
        if c not in df.columns:
            df[c] = 1
    for c in ("is_service", "is_privileged"):
        df[c] = df[c].astype(bool) if c in df.columns else False
    for c in DIRECTORY_DATE_COLUMNS:
        df[c] = pd.to_datetime(df[c]) if c in df.columns else pd.NaT
    if df["sid"].duplicated().any():
        raise ValueError("Dizinde yinelenen sid var")
    return df.reset_index(drop=True)


def load_leases_file(path: Optional[Union[str, Path]]) -> pd.DataFrame:
    if not path:
        return pd.DataFrame(columns=["ip", "sid", "start", "end"])
    df = _read(path)
    for c in ("ip", "sid", "start", "end"):
        if c not in df.columns:
            raise ValueError(f"Kiralama dosyasında kolon eksik: {c}")
    df["start"], df["end"] = pd.to_datetime(df["start"]), pd.to_datetime(df["end"])
    return df


def load_leaves_file(path: Optional[Union[str, Path]]) -> pd.DataFrame:
    if not path:
        return pd.DataFrame(columns=["sid", "start", "end", "tur"])
    df = _read(path)
    for c in ("sid", "start", "end"):
        if c not in df.columns:
            raise ValueError(f"İzin dosyasında kolon eksik: {c}")
    df["start"], df["end"] = pd.to_datetime(df["start"]), pd.to_datetime(df["end"])
    if "tur" not in df.columns:
        df["tur"] = "izin"
    return df


def dataset_from_files(
    events: Optional[Union[str, Path]],
    directory: Union[str, Path],
    leases: Optional[Union[str, Path]] = None,
    leaves: Optional[Union[str, Path]] = None,
    critical_assets: Optional[list] = None,
    name: str = "dosya",
) -> Dataset:
    ev = load_events_file(events) if events else pd.DataFrame(columns=EVENT_COLUMNS)
    if ev.empty:
        ev["time"] = pd.to_datetime(ev["time"])
        ev["received_time"] = pd.to_datetime(ev["received_time"])
    return Dataset(
        name,
        load_directory_file(directory),
        load_leases_file(leases),
        ev,
        load_leaves_file(leaves),
        [],
        list(critical_assets or []),
    )
