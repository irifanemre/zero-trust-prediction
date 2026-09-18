"""Tespit motoru — 12.1 yaşam döngüsü (taslak → gölge → yayında → emekli), 12.5 bastırma, 8.3 kaynak askıya alma."""

from __future__ import annotations

import ast
import logging
import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd

from ztp.config import TenantConfig
from ztp.detection.expr import SafeExpr, _Signals
from ztp.schema import DAY, SOURCE_ALIAS
from ztp.stats import EPS, sigmoid

LOG = logging.getLogger(__name__)


@dataclass
class Hit:
    rule_id: str
    ad: str
    katman: str
    day: pd.Timestamp
    severity: float
    weight: float
    attack: List[str]
    evidence: List[str]
    sinyaller: Dict[str, Any]
    durum: str
    aciklama: str = ""  # tespit anındaki bağlamla üretilen açıklama (sonraki günlerde bağlam değişir)


class DetectionEngine:
    def __init__(self, cfg: TenantConfig, catalog: List[dict], describe: Optional[Callable[["Hit", dict], str]] = None):
        self.describe = (
            describe  # tespit anındaki bağlamla açıklama üretir (raporlama katmanı enjekte eder; motor rapora bağımlı değildir)
        )
        self.cfg = cfg
        self.rules: List[dict] = []
        self.disabled: Dict[str, str] = {}
        self.errors: Counter = Counter()
        self.compiled: Dict[str, List[SafeExpr]] = {}
        avail = set(cfg.available_sources) | {"_internal"}
        for r in catalog:
            r = dict(r)
            if r["durum"] == "emekli":
                self.disabled[r["id"]] = "emekli"
                continue
            if r["durum"] == "yayinda" and not r.get("runbook"):
                LOG.warning("%s runbook'suz — yayına alınamaz, gölge moda düşürüldü (17.4)", r["id"])
                r["durum"] = "golge-modda"
            missing = [k for k in r["veri_kaynaklari"] if SOURCE_ALIAS.get(k, k) not in avail]
            if missing:
                self.disabled[r["id"]] = f"kaynak yok: {missing} (11.1)"
                continue
            self.compiled[r["id"]] = [SafeExpr(c) for c in r["mantik"]["kosullar"]]
            self.rules.append(r)
        self.shadow_log: List[dict] = []
        self.suppressed_log: List[dict] = []
        self.skipped_dq: Counter = Counter()

    @staticmethod
    def severity(rule: dict, s: dict) -> float:
        """13.2 Şiddet: sapmanın büyüklüğü sigmoid ile 0–1'e sıkıştırılır (ham z kullanılmaz; tek uç değer domine etmesin)."""
        sd = rule["siddet"]
        v = s.get(sd["sinyal"], float("nan"))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return 0.5
        esik = sd["esik"]
        if sd.get("donusum") == "log10":
            v, esik = -math.log10(max(float(v), 1e-300)), -math.log10(esik)
        return sigmoid((float(v) - esik) / max(sd["olcek"], EPS))

    def _suppressed(self, rule: dict, s: dict, day: pd.Timestamp, sid: str, pseudo: str) -> Optional[str]:
        for b in rule.get("bastirma", []):
            if b == "servis_hesaplari" and s.get("servis_hesabi") == 1:
                return "servis_hesaplari"
            if b == "yedekleme_penceresi" and day.dayofweek == 6:
                hrs = s.get("mesai_disi_saatler") or []
                if hrs and all(2.0 <= h < 4.0 for h in hrs):
                    return "yedekleme_penceresi (Pazar 02:00-04:00)"
        for sup in self.cfg.suppressions:  # 12.5: en dar kapsam, son kullanma tarihi, gerekçe, sahip
            if sup.get("rule_id") not in (rule["id"], "*"):
                continue
            if sup.get("sid") not in (sid, pseudo, "*"):
                continue
            end = (
                pd.Timestamp(sup.get("end"))
                if sup.get("end")
                else pd.Timestamp(sup["start"]) + self.cfg.suppression_default_days * DAY
            )
            if pd.Timestamp(sup["start"]) <= day <= end:
                return f"musteri_bastirma:{sup.get('reason', '?')} (sahip {sup.get('owner', '?')})"
        return None

    def evaluate(
        self,
        day: pd.Timestamp,
        sid: str,
        pseudo: str,
        signals: dict,
        evidence: dict,
        dq: Dict[str, dict],
        layers: Sequence[str],
        explain: Optional[dict] = None,
    ) -> List[Hit]:
        hits = []
        s = _Signals(signals)
        for rule in self.rules:
            if rule["katman"] not in layers:
                continue
            # 8.3: dayandığı kaynak askıdaysa tespit otomatik askıya alınır
            suspended = [k for k in rule["veri_kaynaklari"] if dq.get(SOURCE_ALIAS.get(k, k), {}).get("durum") == "askida"]
            if suspended:
                self.skipped_dq[rule["id"]] += 1
                continue
            try:
                ok = all(
                    bool(eval(e.compile(self.cfg.threshold_jitter, f"{rule['id']}|{day.date()}"), {"__builtins__": {}}, s))
                    for e in self.compiled[rule["id"]]
                )
            except Exception as exc:  # 17.5 kural çalışma hataları izlenir; sessizce atlanmaz
                self.errors[rule["id"]] += 1
                LOG.warning("Kural hatası %s: %s", rule["id"], exc)
                continue
            if not ok:
                continue
            why = self._suppressed(rule, s, day, sid, pseudo)
            if why:
                self.suppressed_log.append(dict(gun=str(day.date()), kural=rule["id"], kullanici=pseudo, neden=why))
                continue
            ev = [e for k in rule["kanit"] for e in (evidence.get(k) or [])][:12]
            hit = Hit(
                rule["id"],
                rule["ad"],
                rule["katman"],
                day,
                self.severity(rule, signals),
                float(rule["agirlik"]),
                rule["attack"],
                ev,
                {k: signals.get(k) for k in _names(rule)},
                rule["durum"],
            )
            hit.aciklama = self.describe(hit, explain or {}) if self.describe else ""
            if rule["durum"] == "golge-modda":  # 13.6: uyarı üretir, analiste iletilmez; precision ölçülür
                self.shadow_log.append(
                    dict(gun=str(day.date()), kural=rule["id"], kullanici=pseudo, siddet=round(hit.severity, 3))
                )
                continue
            hits.append(hit)
        return hits


def _names(rule: dict) -> List[str]:
    out = []
    for c in rule["mantik"]["kosullar"]:
        for node in ast.walk(ast.parse(c, mode="eval")):
            if isinstance(node, ast.Name) and node.id not in out:
                out.append(node.id)
    return out
