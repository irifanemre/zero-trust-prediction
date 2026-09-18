"""Uçtan uca: sentetik kurumda boru hattı çalışır, kapsama ölçülür, çıktılar ve analist geri bildirimi tutarlıdır."""

import json

import pandas as pd
import pytest

from ztp.cli import main
from ztp.config import TenantConfig
from ztp.data.synthetic import SyntheticOrg
from ztp.detection.catalog import load_catalog
from ztp.pipeline import ZeroTrustPredictionPipeline
from ztp.reporting.llm import LLMReporter
from ztp.response import authorize_containment, tiered_response


def test_synthetic_dataset_shape():
    data = SyntheticOrg(n_users=30, n_days=40, eval_days=5, end_day=pd.Timestamp("2026-03-01"), seed=1).build()
    assert len(data.directory) == 34  # 30 insan + 4 servis hesabı
    assert set(data.events["source"]) >= {"ad", "proxy", "file_server", "edr", "dlp"}
    assert any(g.get("negatif") for g in data.ground_truth)
    assert data.events["time"].is_monotonic_increasing


@pytest.mark.slow
def test_pipeline_end_to_end(tmp_path):
    end = pd.Timestamp("2026-09-16")
    cfg = TenantConfig(tenant_id="t", alarm_budget_per_day=6, threshold_jitter=0.0)
    data = SyntheticOrg(n_users=80, n_days=cfg.long_window_days + 10 + 12, eval_days=12, end_day=end, seed=7).build()
    pipe = ZeroTrustPredictionPipeline(cfg, data, load_catalog(), tmp_path)
    pipe.run(end - pd.Timedelta(days=11), end, warmup_days=10)
    out = tmp_path / "t"
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["vaka_hacmi"]["gun"] == 12
    assert all(d["kuyruk"] <= cfg.alarm_budget_per_day + d["kritik"] for d in metrics["gunluk"])  # bütçe garantisi (13.5)
    assert metrics["kapsama"]["senaryo"] >= 1
    cov = json.loads((out / "coverage_report.json").read_text(encoding="utf-8"))
    neg = [c for c in cov if "NEGATIF" in c["senaryo"]]
    assert neg and neg[0]["sonuc"].startswith("GEÇTİ")  # negatif kontrol uyarı üretmemeli
    cases = list((out / "cases").glob("*.json"))
    assert cases
    case = json.loads(cases[0].read_text(encoding="utf-8"))
    assert case["kullanici"].startswith("U-") and "_sid" not in case  # takma ad; gerçek kimlik vakada yok (20.1)
    assert (out / "identity_vault.RESTRICTED.json").exists()
    assert case["ozet_kaynagi"].startswith("sablon")
    assert 0 <= case["risk"] <= 100 and case["mudahale"]["seviye"] in ("Düşük", "Orta", "Yüksek")
    # detection-as-code dışa aktarımı ve kural sağlığı
    assert (out / "detections" / "UEBA-0001.yaml").exists()
    assert "UEBA-IF01" in metrics["golge_mod"]["kurallar"] or metrics["golge_mod"]["uyari"] >= 0
    # analist etiketi CLI üzerinden
    rc = main(["--out", str(tmp_path), "--tenant", "t", "--label", case["case_id"], "--decision", "belirsiz", "--analyst", "a1"])
    assert rc == 0
    labels = json.loads((out / "labels.json").read_text(encoding="utf-8"))
    assert labels[0]["case_id"] == case["case_id"]


def test_rule_tests_cli():
    assert main(["--test-rules"]) == 0


def test_tiered_response_never_blocks_on_prediction():
    assert tiered_response(95, critical=False)["seviye"] == "Yüksek"
    assert tiered_response(70, critical=False)["seviye"] == "Orta"
    assert "engelle" not in tiered_response(99, critical=True)["aksiyon"].lower()
    ok, _ = authorize_containment({}, None)
    assert not ok
    ok, _ = authorize_containment({}, dict(karar="yanlis_pozitif", analist="a"))
    assert not ok
    ok, _ = authorize_containment({}, dict(karar="gercek_pozitif", analist="a"))
    assert ok


def test_llm_output_validation_rejects_hallucinated_references():
    case = dict(
        case_id="C-1",
        kullanici="U-1000",
        departman="x",
        gun="2026-01-01",
        risk=50,
        tespitler=[dict(kural="UEBA-0003", ad="Hacim", aciklama="a", kanit=["E-0000001"])],
        kanit_serileri={},
        graf=dict(paylasilan_cihazlar=[], ortak_noktalar=[]),
        baglam={},
    )
    ok, problems = LLMReporter._validate("Kullanıcı U-1000 hacmi arttı [E-0000001].", case)
    assert ok and problems == []
    ok, problems = LLMReporter._validate("U-1000 ve U-2000 şüpheli [E-0000001, E-00000ff].", case)
    assert not ok and len(problems) == 2
    ok, problems = LLMReporter._validate("Her şey normal.", case)
    assert not ok
