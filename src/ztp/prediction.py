"""Zero Trust Prediction katmanı — 3.3 / 4 / 11.5: risk yörüngesi + rejim değişimi, 7 günlük ufuk. Tahmin cezalandırıcı karar üretmez (ADR-010)."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ztp.config import TenantConfig
from ztp.features import FEATURE_FLOOR
from ztp.prediction_model import HeuristicModel, LogisticModel, feature_vector
from ztp.profile import DayContext
from ztp.schema import CLOUD_APPS, DAY
from ztp.stats import changepoint_mean_shift, ewma, linear_slope, mad, robust_z


class PredictionLayer:
    def __init__(self, cfg: TenantConfig, directory: pd.DataFrame, leaves: pd.DataFrame):
        self.cfg = cfg
        self.dir = directory.set_index("sid")
        self.leaves = leaves
        self.user_feats: Dict[str, pd.DataFrame] = {}
        self.risk_series: Dict[str, Dict[pd.Timestamp, float]] = defaultdict(dict)
        self.heuristic = HeuristicModel()
        self.model: Optional[LogisticModel] = None  # etiketten öğrenen model (14.5 giriş şartı sağlanınca yüklenir)
        self.rows: List[dict] = []  # entity-gün tahmin satırları (kalibrasyon ölçümü ve eğitim verisi)

    def bind_features(self, feats: pd.DataFrame) -> None:
        """Günün başında güncel varlık-gün özelliklerini bağlar (artımlı koşuda tablo her gün büyür)."""
        self.user_feats = {sid: g.set_index("day").sort_index() for sid, g in feats.groupby("sid")} if len(feats) else {}

    def prune(self, before: pd.Timestamp) -> None:
        for sid in list(self.risk_series):
            self.risk_series[sid] = {d: v for d, v in self.risk_series[sid].items() if d >= before}

    def record_risk(self, sid: str, day: pd.Timestamp, raw: float) -> None:
        self.risk_series[sid][day] = raw

    def signals(
        self, sid: str, day: pd.Timestamp, ueba_signals: dict, ctx: DayContext, current_pct: float
    ) -> Tuple[dict, dict, dict]:
        s, ex, evid = {}, {}, {}
        u = self.dir.loc[sid]
        # --- risk yörüngesi (4.1 sinyal 1) ---
        series = [self.risk_series[sid].get(day - k * DAY, 0.0) for k in range(29, -1, -1)]
        ek, eu = ewma(series, 0.4), ewma(series, 0.1)
        scale = max(mad(series) / 0.6745, 0.5)
        s["risk_ewma_kisa"], s["risk_ewma_uzun"] = ek[-1], eu[-1]
        s["risk_egim_7g"] = linear_slope(ek[-7:]) / scale
        s["risk_pozitif_gun_7g"] = int(sum(1 for v in series[-7:] if v > 0))  # sürekli artış: tek sıçrama değil
        evid["risk_serisi"] = [f"seri:{(day - k * DAY).date()}={series[-1 - k]:.1f}" for k in range(6, -1, -1)]
        ex["risk_serisi_7g"] = [round(v, 1) for v in series[-7:]]
        # --- rejim değişimi (4.1 sinyal 2): davranış bileşik serisi üzerinde changepoint ---
        uf = self.user_feats.get(sid)
        s["rejim_degisim_skoru"], s["rejim_degisim_gun"] = 0.0, -1
        s["yetki_sonrasi_kaynak_z"] = 0.0
        s["hacim_trend_14g"] = 0.0
        s["bulut_yeni_uygulama"] = 0
        s["sessizlik_gun"], s["izin_kayitli"], s["donus_aktivite_z"] = 0, 0, 0.0
        if uf is not None:
            win = uf[(uf.index <= day) & (uf.index > day - 30 * DAY)]
            if len(win) >= 10:
                comp = pd.DataFrame(
                    {
                        "b": np.log1p(win["bytes_out"]),
                        "r": win["distinct_resources"],
                        "o": win["offhours_ratio"] * 10,
                        "k": win["recon_process_count"],
                        "s": win["sensitive_access_count"],
                    }
                )
                comp = (comp - comp.median()) / (comp.apply(mad) / 0.6745 + 0.5)
                cp = changepoint_mean_shift(comp.mean(axis=1).values, min_seg=4)
                if cp and cp.f_stat > 8 and cp.shift_z > 0 and cp.days_ago <= 12:
                    s["rejim_degisim_skoru"], s["rejim_degisim_gun"] = cp.shift_z, cp.days_ago
                    ex["rejim_degisimi"] = (
                        f"{cp.days_ago} gün önce davranış profili değişti (kayma {cp.shift_z:.1f} MAD, F={cp.f_stat:.0f})"
                    )
                    evid["rejim"] = [f"seri:changepoint@{(day - cp.days_ago * DAY).date()}"]
            # #11 yetki artışı sonrası kayma: yetki tarihi öncesi/sonrası kaynak çeşitliliği
            g = u["privilege_grant_date"]
            if not pd.isna(g) and 0 <= (day - g).days <= 30:
                before = uf[(uf.index < g) & (uf.index >= g - 60 * DAY)]["distinct_resources"]
                after = uf[(uf.index >= g) & (uf.index <= day)]["distinct_resources"]
                if len(before) >= 5 and len(after) >= 3:
                    s["yetki_sonrasi_kaynak_z"] = robust_z(float(after.median()), float(before.median()), mad(before), 0.5)
                    ex["yetki_artisi"] = (
                        f"yetki {(day - g).days} gün önce verildi; kaynak çeşitliliği {before.median():.0f} → {after.median():.0f}"
                    )
                    evid["yetki"] = [f"ik:yetki_degisimi@{g.date()}"]
            # #13 uzun sessizlik: bugünden önceki son aktif gün
            prev = uf[uf.index < day]
            if len(prev):
                last = prev.index.max()
                gap = int((day - last).days) - 1
                s["sessizlik_gun"] = gap
                if gap >= 7:
                    lv = self.leaves[self.leaves["sid"] == sid] if len(self.leaves) else self.leaves
                    s["izin_kayitli"] = int(any((r.start <= day - DAY) and (r.end >= last + DAY) for r in lv.itertuples()))
                    zs = []
                    for c in ("event_count", "bytes_out", "files_accessed"):
                        base = prev[c]
                        cur = float(uf.loc[day, c]) if day in uf.index else 0.0
                        zs.append(robust_z(cur, float(base.median()), mad(base), FEATURE_FLOOR[c]))
                    s["donus_aktivite_z"] = max(zs)
                    ex["sessizlik"] = (
                        f"{gap} gün aktivite yok (son aktif {last.date()}); izin kaydı: {'var' if s['izin_kayitli'] else 'yok'}"
                    )
            # #14 ayrılık öncesi desen: 14 günlük hacim eğimi + bulut uygulaması
            w14 = uf[(uf.index <= day) & (uf.index > day - 14 * DAY)]
            if len(w14) >= 5:
                pmad = float(ctx.p_mad.loc[sid, "bytes_out"]) if sid in ctx.p_mad.index else float("nan")
                sc = max((pmad / 0.6745) if not math.isnan(pmad) else 0.0, 0.1 * float(w14["bytes_out"].median()), 1e6)
                s["hacim_trend_14g"] = linear_slope(w14["bytes_out"].values) / sc
                p_apps = ctx.p_sets["apps"].get(sid, frozenset())
                recent_apps = frozenset().union(*w14["apps"])
                (recent_apps & CLOUD_APPS) - (p_apps - frozenset().union(*w14["apps"]))
                # bulut uygulaması son 14 günde ilk kez göründü mü (uzun pencerenin 14 gün öncesinde yoktu)
                older = uf[(uf.index <= day - 14 * DAY) & (uf.index > day - 90 * DAY)]
                older_apps = frozenset().union(*older["apps"]) if len(older) else frozenset()
                s["bulut_yeni_uygulama"] = int(bool((recent_apps & CLOUD_APPS) - older_apps))
                if s["bulut_yeni_uygulama"]:
                    ex["bulut_uygulama"] = sorted((recent_apps & CLOUD_APPS) - older_apps)
        # --- 7 günlük ufuk olasılığı: sezgisel başlangıç modeli; etiket biriktiğinde öğrenen model (11.8/14.5) ---
        f = feature_vector(ueba_signals, s, current_pct)
        p_h, comp_h = self.heuristic.predict(f)
        if self.model is not None:
            p7, comp = self.model.predict(f)
            model_name = self.model.name
        else:
            p7, comp, model_name = p_h, comp_h, self.heuristic.name
        s["tahmin_7g_olasilik"] = p7
        s["tahmin_7g_sezgisel"] = p_h
        ex["tahmin_7g"] = dict(
            olasilik=round(p7, 3), model=model_name, bilesenler={k: round(v, 2) for k, v in comp.items() if abs(v) > 0.005}
        )
        self.rows.append(dict(gun=str(day.date()), sid=sid, ozellikler=f, p7=round(p7, 4), p7_sezgisel=round(p_h, 4)))
        return s, ex, evid
