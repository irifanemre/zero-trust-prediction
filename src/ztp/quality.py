"""Veri kalitesi kontrolü — 8.3: kaynak eşiğin altına düşerse ona dayanan tespitler otomatik askıya alınır."""

from __future__ import annotations

from typing import Dict

import pandas as pd

from ztp.config import TenantConfig
from ztp.schema import DAY


class DataQualityMonitor:
    def __init__(self, cfg: TenantConfig, events: pd.DataFrame):
        self.cfg = cfg
        ev = events
        day = ev["time"].dt.normalize()
        late = (ev["received_time"] - ev["time"]) > pd.Timedelta(hours=1)
        tz_err = ev["time"] > ev["received_time"] + pd.Timedelta(minutes=1)  # alınış zamanı olay zamanından önce olamaz
        g = pd.DataFrame(
            {"source": ev["source"], "day": day, "late": late, "unres": ev["canonical"].isna(), "tz": tz_err}
        ).groupby(["source", "day"])
        self.stats = g.agg(n=("late", "size"), late=("late", "mean"), unres=("unres", "mean"), tz=("tz", "sum"))
        self.sources = sorted(ev["source"].unique())

    def assess(self, day: pd.Timestamp) -> Dict[str, dict]:
        out = {}
        ratios = {}
        for src in self.sources:
            hist = self.stats.loc[src] if src in self.stats.index.get_level_values(0) else pd.DataFrame()
            # 10.5: hacim referansı haftanın aynı günleriyle kurulur (hafta sonu düşüşü toplama bozulması değildir)
            same_dow = [day - 7 * k * DAY for k in range(1, 7)]
            base = hist.loc[[d for d in same_dow if d in hist.index], "n"] if len(hist) else pd.Series(dtype=float)
            if len(base) < 2 and len(hist):
                base = hist[(hist.index < day) & (hist.index >= day - 14 * DAY)]["n"]
            today = hist.loc[day] if (len(hist) and day in hist.index) else None
            n_today = int(today["n"]) if today is not None else 0
            baseline = float(base.median()) if len(base) else 0.0
            ratio = (n_today / baseline) if baseline > 0 else 1.0
            late_ratio = float(today["late"]) if today is not None else 0.0
            unres_ratio = float(today["unres"]) if today is not None else 0.0
            tz_errors = int(today["tz"]) if today is not None else 0
            status = "ok"
            reasons = []
            if baseline >= 20:
                ratios[src] = ratio
            if baseline >= 20 and ratio < self.cfg.dq_min_volume_ratio:  # düşük hacimli kaynakta Poisson gürültüsü askıya almasın
                status, _ = "askida", reasons.append(f"hacim düşüşü (bugün {n_today}, referans medyan {baseline:.0f})")
            if unres_ratio > self.cfg.dq_max_unresolved_ratio:
                status, _ = "askida", reasons.append(f"kanonik kimliğe bağlanamayan oran %{unres_ratio * 100:.0f}")
            if late_ratio > self.cfg.dq_max_late_ratio and status == "ok":
                status, _ = "bozulmus", reasons.append(f"geç gelen olay oranı %{late_ratio * 100:.0f}")
            if tz_errors > 0:
                reasons.append(f"saat dilimi tutarsızlığı şüphesi ({tz_errors} olay)")
            out[src] = dict(
                durum=status,
                olay=n_today,
                olay_saat=round(n_today / 24.0, 1),
                medyan14g=baseline,
                gec_oran=round(late_ratio, 3),
                cozumsuz_oran=round(unres_ratio, 3),
                nedenler=reasons,
            )
        # 10.5 takvim etkisi: tüm kaynaklar birlikte orantılı düşüyorsa bu toplama bozulması değil, tatil/az çalışılan gündür
        if len(ratios) >= 2 and all(r < self.cfg.dq_min_volume_ratio for r in ratios.values()):
            for src, o in out.items():
                if (
                    o["durum"] == "askida"
                    and any("hacim düşüşü" in r for r in o["nedenler"])
                    and o["cozumsuz_oran"] <= self.cfg.dq_max_unresolved_ratio
                ):
                    o["durum"] = "ok"
                    o["nedenler"].append("tüm kaynaklar birlikte düştü → takvim etkisi (tatil) varsayıldı, askıya alınmadı")
        return out
