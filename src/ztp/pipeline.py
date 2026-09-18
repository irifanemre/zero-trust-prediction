"""Boru hattı — 7.2 diyagramı: müşteri bazında izole çalışır (17.1); bilgi grafı ortak, gözlem grafı ve baseline izole."""

from __future__ import annotations

import json
import logging
import math
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from ztp.config import TenantConfig
from ztp.data.dataset import Dataset
from ztp.detection.catalog import export_catalog
from ztp.detection.engine import DetectionEngine
from ztp.features import extract_features
from ztp.feedback import LabelStore
from ztp.graph.analysis import DeepGraphAnalyzer, GraphFindings
from ztp.graph.knowledge import KnowledgeGraph
from ztp.graph.observation import ObservationGraphBuilder
from ztp.graph.store import NetworkXGraphStore
from ztp.identity import IdentityResolver, Pseudonymizer
from ztp.metrics import HealthMonitor, MetricsCollector
from ztp.peers import PeerGroups
from ztp.prediction import PredictionLayer
from ztp.profile import ProfileEngine
from ztp.quality import DataQualityMonitor
from ztp.reporting.llm import LLMReporter
from ztp.reporting.template import TemplateReporter, describe_hit
from ztp.response import tiered_response
from ztp.schema import DAY, to_utc_naive
from ztp.scoring import RiskResult, RiskScorer

LOG = logging.getLogger(__name__)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if math.isnan(float(o)) else float(o)
    if isinstance(o, float) and math.isnan(o):
        return None
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


class ZeroTrustPredictionPipeline:
    def __init__(self, cfg: TenantConfig, data: Dataset, catalog: List[dict], out_dir: Path):
        self.cfg, self.data, self.catalog = cfg, data, catalog
        self.out = out_dir / cfg.tenant_id
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "cases").mkdir(exist_ok=True)
        export_catalog(catalog, self.out / "detections")
        self.health = HealthMonitor()
        self.pseud = Pseudonymizer(cfg.pseudonym_secret, self.out / "audit.jsonl")
        self.labels = LabelStore(self.out / "labels.json")
        self.kg = KnowledgeGraph()
        self.engine = DetectionEngine(cfg, catalog, describe=describe_hit)
        self.llm = LLMReporter(cfg)
        self.cases: List[dict] = []
        self.dq_last: dict = {}
        self.final_risk: Dict[str, Dict[pd.Timestamp, float]] = defaultdict(dict)

    # ------------------------------------------------------------------
    def prepare(self) -> None:
        t0 = time.perf_counter()
        d = self.data
        d.events["time"] = to_utc_naive(d.events["time"])
        d.events["received_time"] = to_utc_naive(d.events["received_time"])
        for c in ("hire_date", "resignation_notice_date", "resignation_date", "role_change_date", "privilege_grant_date"):
            d.directory[c] = pd.to_datetime(d.directory[c])
        self.resolver = IdentityResolver(d.directory, d.ip_leases)
        self.events = self.resolver.resolve(d.events)
        self.health.time("kimlik_eslestirme", t0)
        lat = (self.events["received_time"] - self.events["time"]).dt.total_seconds() / 60
        self.health.data_latency_min = {s: round(float(v), 1) for s, v in lat.groupby(self.events["source"]).median().items()}
        t0 = time.perf_counter()
        self.dq = DataQualityMonitor(self.cfg, self.events)
        self.health.time("veri_kalitesi", t0)
        t0 = time.perf_counter()
        crit = list(self.cfg.critical_assets) or list(d.critical_assets)
        self.feats = extract_features(self.events, crit)
        self.health.time("ozellik_cikarimi", t0)
        self.peers = PeerGroups(d.directory, self.cfg.min_peer_group)
        self.profile = ProfileEngine(self.cfg, self.feats, d.directory, d.leaves, self.events, self.peers)
        self.pred = PredictionLayer(self.cfg, self.feats, d.directory, d.leaves)
        self.store = NetworkXGraphStore()
        self.graph_builder = ObservationGraphBuilder(self.store, crit)
        self.deep = DeepGraphAnalyzer(self.cfg, self.store, self.kg, crit, int((~d.directory.is_service.astype(bool)).sum()))
        self.scorer = RiskScorer(self.cfg, self.kg, self.labels)
        self.metrics = MetricsCollector(self.cfg, d.ground_truth, self.catalog)
        self.events_by_day = {k: g for k, g in self.events.groupby(self.events["time"].dt.normalize())}
        LOG.info(
            "Hazırlık: %d olay, %d varlık-gün, %d kullanıcı, akran grupları=%s",
            len(self.events),
            len(self.feats),
            d.directory.shape[0],
            dict(Counter(self.peers.key_of.values())),
        )

    # ------------------------------------------------------------------
    def run(self, start: pd.Timestamp, end: pd.Timestamp, warmup_days: int) -> None:
        self.prepare()

        # Kapsama ölçümü yalnızca DEĞERLENDİRME penceresiyle kesişen senaryolar üzerinden yapılır (ısınma/geçmiş dönemde vaka üretilmez)
        def _overlaps(g: dict) -> bool:
            w = g.get("pencere") or [g.get("baslangic_tarihi"), g.get("olay_tarihi")]
            return pd.Timestamp(w[1]) >= start - 7 * DAY and pd.Timestamp(w[0]) <= end + 7 * DAY

        self.metrics.gt = [g for g in self.metrics.gt if _overlaps(g)]
        self.metrics.eval_range = (start, end)
        # Graf: değerlendirme öncesi geçmiş (uzun pencere) kenarları — akran kıyası için tüm popülasyon (Prensip 2)
        t0 = time.perf_counter()
        for day, ev in self.events_by_day.items():
            if day < start - warmup_days * DAY:
                self.graph_builder.ingest_day(ev)
        self.health.time("graf_olusturma", t0)
        day = start - warmup_days * DAY
        while day <= end:
            self._run_day(day, produce_cases=day >= start)
            day += DAY
        self._write_outputs(end)

    def _run_day(self, day: pd.Timestamp, produce_cases: bool) -> None:
        cfg = self.cfg
        ev_day = self.events_by_day.get(day, self.events.iloc[0:0])
        # 1) veri kalitesi
        t0 = time.perf_counter()
        dq = self.dq.assess(day)
        self.dq_last = dq
        self.health.time("veri_kalitesi", t0)
        # 2) graf oluşturma (düşük maliyet, tüm kullanıcılar)
        t0 = time.perf_counter()
        self.graph_builder.ingest_day(ev_day)
        self.health.time("graf_olusturma", t0)
        # 3) UEBA: baseline + sinyaller + tespitler
        t0 = time.perf_counter()
        ctx = self.profile.context(day)
        today = self.profile.today(day)
        signals, explains, evidences, hits_today = {}, {}, {}, {}
        for _, row in today.iterrows():
            sid = row["sid"]
            s, ex, evid = self.profile.signals(ctx, row)
            signals[sid], explains[sid], evidences[sid] = s, ex, evid
            if s.get("zehirleme_suphesi"):
                self.metrics.flags[sid].add("zehirleme_suphesi")
            hits_today[sid] = self.engine.evaluate(day, sid, self.pseud.pseudo(sid), s, evid, dq, ("UEBA", "veri-kalitesi"), ex)
        self.health.time("ueba", t0)
        # 4) Prediction: geçici günlük risk (UEBA) → yörünge/rejim sinyalleri → prediction tespitleri
        t0 = time.perf_counter()
        results: Dict[str, RiskResult] = {}
        for sid in signals:
            self.scorer.add_hits(sid, hits_today[sid])
            prov = self.scorer.compute(sid, day, signals[sid])
            # risk serisine GÜNÜN taze UEBA sinyali yazılır (7 günlük pencere/bozunum değil): yörünge yeni kanıtla ölçülür
            self.pred.record_risk(sid, day, sum(h.weight * h.severity for h in prov.hits if h.day == day))
            cur_pct = float(np.searchsorted(np.sort([v for _, v in self.scorer.pool]), prov.raw) / max(1, len(self.scorer.pool)))
            ps, pex, pev = self.pred.signals(sid, day, signals[sid], ctx, cur_pct)
            signals[sid].update(ps)
            explains[sid].update(pex)
            evidences[sid].update(pev)
            ph = self.engine.evaluate(
                day, sid, self.pseud.pseudo(sid), signals[sid], evidences[sid], dq, ("Prediction",), explains[sid]
            )
            hits_today[sid].extend(ph)
            self.scorer.add_hits(sid, ph)
            results[sid] = self.scorer.compute(sid, day, signals[sid])
            self.final_risk[sid][day] = results[sid].raw
        self.health.time("prediction", t0)
        # 5) kalibrasyon + alarm bütçesi
        t0 = time.perf_counter()
        self.scorer.calibrate(day, results)
        queue = self.scorer.select_queue(day, results)
        self.health.time("skorlama", t0)
        self.health.rule_errors = self.engine.errors
        self.health.profile_fresh[str(day.date())] = f"baseline {len(ctx.p_med)} kullanıcı, pencere {cfg.long_window_days}g"
        if not produce_cases:
            return
        # 6) derin graf analizi (yalnızca riskli alt küme) → ilişkisel tespitler → birleşik skor → vaka
        t0 = time.perf_counter()
        risky = set(queue)
        cases_today = []
        for sid in queue:
            r = results[sid]
            gf, gsig = self.deep.analyze(sid, day, risky, [h for h in r.hits if h.day == day], self.pseud.pseudo)
            signals[sid].update(gsig)
            rel_hits = self.engine.evaluate(
                day,
                sid,
                self.pseud.pseudo(sid),
                signals[sid],
                {"graf": [f"graf:{sid[-6:]}@{day.date()}"]},
                dq,
                ("iliskisel",),
                explains[sid],
            )
            if rel_hits:
                self.scorer.add_hits(sid, rel_hits)
                r = self.scorer.compute(sid, day, signals[sid])
                r.percentile, r.critical = results[sid].percentile, results[sid].critical
                results[sid] = r
            cases_today.append(self._build_case(sid, day, r, gf, signals[sid], explains[sid], evidences[sid]))
        self.health.time("derin_graf_ve_rapor", t0)
        self.health.record_volume(day, len(queue))
        self.metrics.record_day(
            day, results, queue, len([s for s in self.engine.suppressed_log if s["gun"] == str(day.date())]), len(ev_day)
        )
        self._write_queue(day, cases_today, dq)
        LOG.info(
            "%s: aktif=%d tespitli=%d kuyruk=%d kritik=%d askıda_kaynak=%s",
            day.date(),
            len(results),
            sum(1 for r in results.values() if r.raw > 0),
            len(queue),
            sum(1 for s in queue if results[s].critical),
            [k for k, v in dq.items() if v["durum"] == "askida"],
        )

    # ------------------------------------------------------------------
    def _build_case(self, sid: str, day: pd.Timestamp, r: RiskResult, gf: GraphFindings, s: dict, ex: dict, evid: dict) -> dict:
        cfg = self.cfg
        pseudo = self.pseud.pseudo(sid)
        u = self.data.directory.set_index("sid").loc[sid]
        combined = 100.0 * (cfg.fusion_temporal_weight * r.percentile + cfg.fusion_structural_weight * gf.structural_score)
        prev_raw = self.final_risk[sid].get(day - 7 * DAY, 0.0)
        delta = int(round(100 * (r.raw - prev_raw) / max(r.raw, prev_raw, 1.0)))
        hits = []
        for h in sorted(r.hits, key=lambda h: -r.contributions.get(f"{h.rule_id}@{h.day.date()}", 0)):
            hits.append(
                dict(
                    kural=h.rule_id,
                    ad=h.ad,
                    katman=h.katman,
                    gun=str(h.day.date()),
                    siddet=round(h.severity, 3),
                    agirlik=h.weight,
                    katki=round(r.contributions.get(f"{h.rule_id}@{h.day.date()}", 0), 2),
                    kanit=h.evidence,
                    attack=h.attack,
                    aciklama=h.aciklama or describe_hit(h, ex),
                )
            )
        timeline = []
        if ex.get("rejim_degisimi"):
            timeline.append(f"{s.get('rejim_degisim_gun')} gün önce — {ex['rejim_degisimi']}")
        if ex.get("yetki_artisi"):
            timeline.append(f"yetki — {ex['yetki_artisi']}")
        if ex.get("sessizlik"):
            timeline.append(f"sessizlik — {ex['sessizlik']}")
        for h in sorted(r.hits, key=lambda h: h.day):
            timeline.append(f"{(day - h.day).days} gün önce — {h.ad}" if h.day != day else f"bugün — {h.ad}")
        seen = set()
        timeline = [t for t in timeline if not (t in seen or seen.add(t))][:8]
        case = dict(
            case_id=f"C-{day.strftime('%Y%m%d')}-{pseudo[2:]}",
            musteri=cfg.tenant_id,
            gun=str(day.date()),
            kullanici=pseudo,
            _sid=sid,
            departman=str(u["dept"]),
            risk=int(round(combined)),
            delta_7g=delta,
            yuzdelik=round(r.percentile, 4),
            ham_skor=round(r.raw, 2),
            yapisal_skor=gf.structural_score,
            kritik=bool(r.critical),
            carpanlar=r.multipliers,
            tespitler=hits,
            baglam={k: v for k, v in ex.items() if k not in ("tahmin_7g",)},
            tahmin_7g=ex.get("tahmin_7g", dict(olasilik=s.get("tahmin_7g_olasilik", 0), bilesenler={})),
            graf=dict(
                cihazlar=gf.devices,
                paylasilan_cihazlar=gf.shared_devices,
                kritik_yollar=gf.paths_to_critical,
                etki_alani=gf.blast_radius,
                ortak_noktalar=gf.common_points,
                teknikler=gf.techniques,
            ),
            zaman_cizelgesi=timeline,
            kanit_serileri={k: v for k, v in evid.items() if k in ("risk_serisi", "rejim", "yetki", "silence")},
            mudahale=tiered_response(combined, r.critical),
        )
        case["ozet"], case["ozet_kaynagi"] = self.llm.summarize(case)
        case["rapor"] = TemplateReporter.render(case)
        self.cases.append(case)
        with open(self.out / "cases" / f"{case['case_id']}.json", "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in case.items() if k != "_sid"}, f, ensure_ascii=False, indent=2, default=_json_default)
        return case

    def _write_queue(self, day: pd.Timestamp, cases: List[dict], dq: dict) -> None:
        with open(self.out / f"queue_{day.date()}.txt", "w", encoding="utf-8") as f:
            f.write(
                f"İNCELEME KUYRUĞU — {self.cfg.tenant_id} — {day.date()} — bütçe {self.cfg.alarm_budget_per_day}, kuyruk {len(cases)}\n"
            )
            f.write("Veri kalitesi: " + ", ".join(f"{k}={v['durum']}" for k, v in dq.items()) + "\n\n")
            for c in cases:
                f.write(c["rapor"] + "\n\n")

    def _write_outputs(self, last_day: pd.Timestamp) -> None:
        summ = self.metrics.summary(self.labels, self.engine.shadow_log, self.engine.suppressed_log, self.engine, last_day)
        summ["llm"] = dict(cagri=self.llm.calls, token=self.llm.tokens, backend=self.cfg.llm_backend)
        summ["kimlik_eslestirme"] = dict(cozumsuz=self.resolver.unresolved_by_source, kuyruk=len(self.resolver.unresolved_queue))
        (self.out / "metrics.json").write_text(
            json.dumps(summ, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8"
        )
        (self.out / "health.json").write_text(
            json.dumps(self.health.snapshot(self.dq_last), ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8"
        )
        (self.out / "coverage_report.json").write_text(
            json.dumps(summ["kapsama"]["detay"], ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8"
        )
        with open(self.out / "shadow_log.jsonl", "w", encoding="utf-8") as f:
            for s in self.engine.shadow_log:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        with open(self.out / "suppressed.jsonl", "w", encoding="utf-8") as f:
            for s in self.engine.suppressed_log:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        self.resolver.unresolved_queue.to_csv(self.out / "unresolved_identity_queue.csv", index=False)
        # 20.1 erişim ayrımı: gerçek kimlik eşlemesi ayrı, kısıtlı dosyada (üretimde ayrı yetki alanı / vault)
        vault = {
            p: dict(sid=s, display_name=str(self.data.directory.set_index("sid").loc[s, "display_name"]))
            for s, p in self.pseud.forward.items()
        }
        (self.out / "identity_vault.RESTRICTED.json").write_text(
            json.dumps(vault, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._print_summary(summ)

    def _print_summary(self, summ: dict) -> None:
        print("\n" + "=" * 100)
        print(f"ÇALIŞMA ÖZETİ — müşteri {self.cfg.tenant_id} — çıktı dizini: {self.out}")
        print("=" * 100)
        print(
            f"Vaka hacmi: toplam {summ['vaka_hacmi']['toplam']} / {summ['vaka_hacmi']['gun']} gün (günlük ort. {summ['vaka_hacmi']['gunluk_ort']}, bütçe {summ['vaka_hacmi']['butce']})"
        )
        print(
            f"Gölge mod uyarıları: {summ['golge_mod']['uyari']} (analiste iletilmedi)  |  Bastırılan: {summ['bastirma']['bastirilan']} (oran {summ['bastirma']['oran']})"
        )
        print(f"Kimlik: çözümlenemeyen={summ['kimlik_eslestirme']['cozumsuz']}  |  LLM: {summ['llm']}")
        print(
            f"Kural sağlığı: devre dışı={list(summ['kural_sagligi']['devre_disi'])} 30g tetiklenmeyen={summ['kural_sagligi']['gun30_tetiklenmeyen']} DQ askıda atlanan={summ['kural_sagligi']['dq_askida_atlanan']}"
        )
        print(f"Bileşen katkısı (skor payı): {summ['bilesen_katkisi']}")
        lp = summ.get("etiketli_veri_precision")
        if lp:
            print(
                f"Etiketli veri precision@N: {lp['precision_at_n']} ({lp['dogru']} doğru / {lp['kuyruk_varlik_gun']} kuyruk varlık-günü; {lp['insider_sayisi']} bilinen insider)"
                f" | sıralı prefiks: "
                + ", ".join(f"{k}={lp[k]}" for k in ("precision@1", "precision@3", "precision@5", "precision@10"))
                + f" | kullanıcı bazında: {lp['kullanici_bazinda']}"
            )
        if summ["kapsama"]["senaryo"]:
            print(f"\nKAPSAMA (19.6): {summ['kapsama']['tespit']}/{summ['kapsama']['senaryo']} pozitif senaryo yakalandı")
            detay = summ["kapsama"]["detay"]
            if len(detay) > 12:  # CERT gibi çok örnekli setlerde senaryo tipine göre özet
                agg = defaultdict(lambda: Counter())
                erk = defaultdict(list)
                for c in detay:
                    key = c["senaryo"].rsplit("-", 1)[0]
                    agg[key][("KISMİ" if "kısmi pencere" in c["sonuc"] else c["sonuc"].split(" ")[0])] += 1
                    if c["erkenlik_gun"] is not None:
                        erk[key].append(c["erkenlik_gun"])
                for key, cnt in sorted(agg.items()):
                    n = sum(cnt.values())
                    print(
                        f"  {key:<22} n={n:<3} "
                        + " ".join(f"{k}={v}" for k, v in sorted(cnt.items()))
                        + (f"  erkenlik(gün) medyan={np.median(erk[key]):.0f}" if erk[key] else "")
                    )
                for c in detay:
                    if c["sonuc"].startswith("GEÇTİ"):
                        print(f"    ✓ {c['senaryo']:<34} kuyruk={c['gercek_sonuc']} erkenlik={c['erkenlik_gun']}")
            else:
                for c in detay:
                    print(
                        f"  {c['sonuc']:<48} {c['senaryo']:<40} beklenen={c['beklenen_tespit']} gerçek={c['gercek_sonuc']} erkenlik={c['erkenlik_gun']} bayrak={c['bayraklar']}"
                    )
        print(f"\nSağlık uyarıları: {self.health.warnings or 'yok'}")
        print(f"Katman süreleri (sn): {dict((k, round(v, 1)) for k, v in self.health.layer_time.items())}")
        print(
            "\nHatırlatma: precision@N ve analist mutabakatı ETİKET gerektirir → --label ile vaka kapatın; recall üretim hedefi değildir (1.3)."
        )
