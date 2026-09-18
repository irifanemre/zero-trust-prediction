"""Prediction katmanı: özellik vektörü, sezgisel/öğrenen model, kalibrasyon raporu, model eklentisi (14.6), ablasyon koşusu."""

import numpy as np
import pandas as pd
import pytest

from ztp.ablation import format_ablation, run_ablation
from ztp.config import TenantConfig
from ztp.data.synthetic import SyntheticOrg
from ztp.detection.catalog import load_catalog
from ztp.detection.engine import Hit
from ztp.feedback import LabelStore
from ztp.graph.knowledge import KnowledgeGraph
from ztp.pipeline import ZeroTrustPredictionPipeline
from ztp.prediction_model import (
    MODEL_VERSION,
    PREDICTION_FEATURES,
    HeuristicModel,
    LogisticModel,
    auc_score,
    calibration_report,
    feature_vector,
    rows_to_matrix,
)
from ztp.scoring import RiskScorer


def test_feature_vector_is_finite_and_ordered():
    f = feature_vector(
        dict(ayrilik_bildirimi=1, yetki_degisim_gun=3, hesap_yasi_gun=10, veri_hacmi_z=float("nan")), dict(risk_egim_7g=None), 0.9
    )
    assert tuple(f) == PREDICTION_FEATURES
    assert f["yetki_var"] == 1.0 and f["yeni_hesap"] == 1.0 and f["veri_hacmi_z"] == 0.0 and f["mevcut_yuzdelik"] == 0.9
    assert all(np.isfinite(v) for v in f.values())


def test_heuristic_model_monotone():
    m = HeuristicModel()
    low, _ = m.predict(feature_vector({}, {}, 0.0))
    high, comp = m.predict(feature_vector(dict(ayrilik_bildirimi=1), dict(risk_egim_7g=2.0, rejim_degisim_skoru=5.0), 1.0))
    assert 0 < low < 0.05 < high < 1 and comp["yorunge"] == 3.0


def test_logistic_model_fit_roundtrip_and_explanations():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(400, len(PREDICTION_FEATURES)))
    logit = 2.0 * X[:, 5] + 1.5 * X[:, 6] - 2.5
    y = (rng.uniform(size=400) < 1 / (1 + np.exp(-logit))).astype(int)
    m = LogisticModel.fit(X, y)
    assert m.n_train == 400 and m.positives == int(y.sum()) and m.version == MODEL_VERSION
    back = LogisticModel.from_dict(m.to_dict())
    f = dict(zip(PREDICTION_FEATURES, X[0]))
    p1, contrib = m.predict(f)
    p2, _ = back.predict(f)
    assert p1 == pytest.approx(p2) and len(contrib) <= 5 and "mevcut_yuzdelik" in contrib or "ayrilik_bildirimi" in contrib
    assert auc_score(m.predict_many(X), y) > 0.85
    with pytest.raises(ValueError):
        LogisticModel.from_dict({**m.to_dict(), "version": "eski"})
    with pytest.raises(ValueError):
        LogisticModel.fit(X[:20], np.zeros(20, dtype=int))  # tek sınıf


def test_calibration_report_detects_miscalibration():
    y = np.array([0] * 90 + [1] * 10)
    good = np.where(y == 1, 0.6, 0.05)
    bad = np.where(y == 1, 0.9, 0.5)
    rg, rb = calibration_report(good, y), calibration_report(bad, y)
    assert rg["brier"] < rb["brier"] and rg["brier_beceri"] > 0 > rb["brier_beceri"]
    assert rg["auc"] == 1.0 and rg["ece"] < rb["ece"] and rg["taban_orani"] == 0.1
    assert calibration_report([], []) == {"n": 0}


def test_rows_to_matrix_shape():
    rows = [dict(ozellikler=feature_vector({}, {}, 0.1)), dict(ozellikler=feature_vector({}, {}, 0.2))]
    assert rows_to_matrix(rows).shape == (2, len(PREDICTION_FEATURES))


def _hit(rule, day, w=5.0, sev=0.8, attack=("T1078",)):
    return Hit(rule, rule, "UEBA", day, sev, w, list(attack), [], {}, "yayinda")


def test_prediction_weight_adds_but_never_replaces_rule_score(tmp_path):
    day = pd.Timestamp("2026-02-10")
    for weight in (0.0, 0.5):
        scorer = RiskScorer(TenantConfig(prediction_weight=weight), KnowledgeGraph(), LabelStore(tmp_path / f"l{weight}.json"))
        scorer.add_hits("A", [_hit("R1", day)])
        r = scorer.compute("A", day, dict(tahmin_7g_olasilik=0.8))
        assert r.raw == pytest.approx(4.0 + (weight * 0.8 * 10))
        none = scorer.compute("B", day, dict(tahmin_7g_olasilik=0.99))  # tespiti olmayan kullanıcıya model tek başına puan vermez
        assert none.raw == 0.0


def test_multiplier_and_peer_flags_are_respected(tmp_path):
    day = pd.Timestamp("2026-02-10")
    scorer = RiskScorer(TenantConfig(correlation_multipliers=False), KnowledgeGraph(), LabelStore(tmp_path / "l.json"))
    scorer.add_hits("A", [_hit("R1", day, attack=("T1078",)), _hit("R2", day, attack=("T1567",))])
    assert scorer.compute("A", day, {}).multipliers == {}
    with pytest.raises(ValueError):
        TenantConfig(prediction_weight=0.5, llm_on_injection="x")


@pytest.mark.slow
def test_ablation_runner_and_training_on_small_synthetic(tmp_path):
    end = pd.Timestamp("2026-09-16")
    cfg = TenantConfig(tenant_id="abl", alarm_budget_per_day=4, threshold_jitter=0.0, supervised_min_labels=50)
    data = SyntheticOrg(n_users=60, n_days=cfg.long_window_days + 6 + 10, eval_days=10, end_day=end, seed=3).build()
    catalog = load_catalog()
    start = end - pd.Timedelta(days=9)
    variants = {
        "tam": dict(aciklama="ref"),
        "carpan_yok": dict(aciklama="çarpan kapalı", cfg=dict(correlation_multipliers=False)),
    }
    rows = run_ablation(cfg, data, catalog, tmp_path, start, end, 6, variants=variants)
    assert [r["varyant"] for r in rows] == ["tam", "carpan_yok"] and rows[0]["kapsama_farki"] == 0.0
    assert "ABLASYON" in format_ablation(rows) and (tmp_path / "abl__carpan_yok" / "metrics.json").exists()
    # öğrenen model: cevap anahtarı etiket rolünde, zamansal holdout ile
    pipe = ZeroTrustPredictionPipeline(cfg, data, catalog, tmp_path)
    pipe.run(start, end, 6)
    rep = pipe.train_prediction_model()
    assert rep["satir"] >= 50
    if rep.get("egitildi"):
        assert pipe.pred.model is not None and rep["egitim"]["n"] > 0 and (tmp_path / "abl" / "prediction_model.json").exists()
    else:
        assert "neden" in rep
