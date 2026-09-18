"""Derin graf analizi — 11.6: yalnızca riskli alt küme için çok adımlı yollar, yanal hareket, etki alanı, ATT&CK eşleşmesi."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Set, Tuple

import pandas as pd

from ztp.config import TenantConfig
from ztp.detection.engine import Hit
from ztp.graph.knowledge import KnowledgeGraph
from ztp.graph.store import NetworkXGraphStore
from ztp.schema import DAY


@dataclass
class GraphFindings:
    devices: List[str]
    shared_devices: List[dict]
    paths_to_critical: List[List[str]]
    blast_radius: int
    common_points: List[dict]
    techniques: List[dict]
    structural_score: float


class DeepGraphAnalyzer:
    def __init__(
        self, cfg: TenantConfig, store: NetworkXGraphStore, kg: KnowledgeGraph, critical_assets: Sequence[str], n_users: int
    ):
        self.cfg, self.store, self.kg = cfg, store, kg
        self.critical = [f"resource:{a}" for a in critical_assets]
        self.n_users = max(n_users, 1)

    @staticmethod
    def _u(node: str) -> str:
        return node.split(":", 1)[1]

    def analyze(self, sid: str, day: pd.Timestamp, risky_sids: Set[str], hits: List[Hit], pseudo) -> Tuple[GraphFindings, dict]:
        since = day - 7 * DAY
        me = f"user:{sid}"
        devices = [self._u(n) for n, et, _ in self.store.neighbors(me, "kullandi", since, "out") if n.startswith("device:")]
        shared = []
        for dev in devices:
            for n, et, meta in self.store.neighbors(f"device:{dev}", "kullandi", since, "in"):
                other = self._u(n)
                if other != sid:
                    shared.append(
                        dict(
                            cihaz=dev,
                            diger_kullanici=pseudo(other),
                            riskli=other in risky_sids,
                            gun_once=int((day - meta["last_ts"].normalize()).days),
                        )
                    )
        paths = []
        PATH_TYPES = {"user", "device", "resource"}
        for c in self.critical:
            # yanal hareket yolu: ara düğümler yalnızca kullanıcı/cihaz (ortak paylaşım üzerinden 'yol' sayılmaz)
            for p in self.store.paths_between(me, c, max_hops=3, since=since, node_types={"user", "device"}):
                if self._time_ordered(p):
                    paths.append([self._label(n, pseudo) for n in p])
        # etki alanı: 2 adımda ulaşılabilen kaynaklar (cihaz → diğer kullanıcı → kaynak dahil)
        reach = self.store.reachable_within(me, 3, since, PATH_TYPES)
        blast = len([n for n in reach if n.startswith("resource:")])
        # ortak nokta: riskli kullanıcıların birlikte eriştiği, popülasyonun >%20'sinin kullanmadığı kaynaklar
        my_res = {n for n, et, _ in self.store.neighbors(me, "eristi", since, "out")}
        common = []
        for r in my_res:
            users = {self._u(n) for n, et, _ in self.store.neighbors(r, "eristi", since, "in")}
            if len(users) > 0.05 * self.n_users:  # yaygın kaynak (ortak paylaşım) ortak nokta sayılmaz
                continue
            others = (users & risky_sids) - {sid}
            if others:
                common.append(dict(kaynak=self._u(r), riskli_kullanicilar=[pseudo(o) for o in sorted(others)]))
        techs = []
        for t in sorted({t for h in hits for t in h.attack}):
            techs.append(dict(teknik=t, ad=self.kg.technique_name(t), taktik=self.kg.tactic(t), gruplar=self.kg.groups_using(t)))
            self.store.add_edge(me, f"technique:{t}", "eslesti", day)
        structural = (
            0.4 * min(1.0, len(paths) / 3.0)
            + 0.3 * min(1.0, sum(1 for s in shared if s["riskli"]) / 2.0 + 0.5 * min(1, len(shared)))
            + 0.3 * min(1.0, blast / 25.0)
        )
        gf = GraphFindings(devices, shared, paths[:5], blast, common[:5], techs, round(min(structural, 1.0), 3))
        signals = dict(
            paylasilan_cihaz_sayisi=len({s["cihaz"] for s in shared}),
            paylasilan_cihaz_riskli_kullanici=sum(1 for s in shared if s["riskli"]),
            kritik_varliga_yol_sayisi=len(paths),
            etki_alani=blast,
            ortak_kaynak_riskli_kume=len(common),
        )
        return gf, signals

    def _time_ordered(self, path: List[str]) -> bool:
        """11.3 zaman damgası zorunluluğu: A→B, B→C'den önce gerçekleşmiş olmalı ki zincir sayılsın."""
        prev = None
        for a, b in zip(path, path[1:]):
            rel = self.store.g[a][b]["rel"] if self.store.g.has_edge(a, b) else self.store.g[b][a]["rel"]
            first = min(m["first_ts"] for m in rel.values())
            last = max(m["last_ts"] for m in rel.values())
            if prev is not None and last < prev:
                return False
            prev = first
        return True

    def _label(self, node: str, pseudo) -> str:
        t, v = node.split(":", 1)
        return pseudo(v) if t == "user" else f"{v}{' (kritik)' if node in self.critical else ''}"
