"""Akran grubu — 9.1: yapısal (min 8 kişi, üst seviyeye çıkma) + davranışsal (30 gün sonra kümeleme)."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, Optional

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans


class PeerGroups:
    def __init__(self, directory: pd.DataFrame, min_size: int):
        self.min_size = min_size
        d = directory[~directory["is_service"].astype(bool)]
        self.key_of: Dict[str, str] = {}
        c3 = Counter(zip(d.dept, d.title_level, d.location))
        c2 = Counter(zip(d.dept, d.location))
        c1 = Counter(d.dept)
        for r in d.itertuples(index=False):
            if c3[(r.dept, r.title_level, r.location)] >= min_size:
                k = f"{r.dept}/L{r.title_level}/{r.location}"
            elif c2[(r.dept, r.location)] >= min_size:
                k = f"{r.dept}/{r.location}"
            elif c1[r.dept] >= min_size:
                k = f"{r.dept}"
            else:
                k = "TUM_KURUM"
            self.key_of[r.sid] = k
        for sid in directory.loc[directory["is_service"].astype(bool), "sid"]:
            self.key_of[sid] = "SERVIS_HESAPLARI"
        self.dept_of = dict(zip(directory.sid, directory.dept))
        self.behavioral_conflict: Dict[str, int] = {}
        self._last_fit: Optional[pd.Timestamp] = None

    def key(self, sid: str) -> str:
        return self.key_of.get(sid, "TUM_KURUM")

    def fit_behavioral(self, hist: pd.DataFrame, day: pd.Timestamp, min_days: int) -> None:
        """Kullanılan uygulama kümesi + çalışma saati profili üzerinden kümeleme. Haftada bir yenilenir."""
        if self._last_fit is not None and (day - self._last_fit).days < 7:
            return
        span = (hist["day"].max() - hist["day"].min()).days if len(hist) else 0
        if span < min_days or hist["sid"].nunique() < 3 * self.min_size:
            return
        apps = Counter(a for s in hist["apps"] for a in s)
        top_apps = [a for a, _ in apps.most_common(25)]
        rows, sids = [], []
        for sid, grp in hist.groupby("sid"):
            if len(grp) < 10:
                continue
            app_vec = np.array([np.mean([a in s for s in grp["apps"]]) for a in top_apps])
            hrs = grp["first_logon_hour"].dropna().values
            hist_h = np.histogram(hrs, bins=[0, 5, 8, 10, 13, 18, 24])[0] / max(len(hrs), 1)
            rows.append(
                np.concatenate([app_vec, hist_h, [np.log1p(grp["bytes_out"].median()), np.log1p(grp["files_accessed"].median())]])
            )
            sids.append(sid)
        if len(sids) < 3 * self.min_size:
            return
        k = max(2, min(8, len(set(self.dept_of[s] for s in sids))))
        labels = KMeans(n_clusters=k, n_init=5, random_state=0).fit_predict(np.array(rows))
        by_cluster = defaultdict(list)
        for s, lbl in zip(sids, labels):
            by_cluster[lbl].append(self.dept_of[s])
        majority = {lbl: Counter(v).most_common(1)[0] for lbl, v in by_cluster.items()}
        self.behavioral_conflict = {}
        for s, lbl in zip(sids, labels):
            dept, cnt = majority[lbl]
            purity = cnt / len(by_cluster[lbl])
            # 9.1: çelişkide yapısal grup esas alınır; çelişkinin kendisi zayıf bir sinyaldir
            self.behavioral_conflict[s] = int(purity > 0.5 and dept != self.dept_of[s])
        self._last_fit = day
