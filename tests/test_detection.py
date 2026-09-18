"""Detection-as-code: güvenli ifade değerlendirici, katalog doğrulama, kural birim testleri, motor yaşam döngüsü."""

import pandas as pd
import pytest

from ztp.config import TenantConfig
from ztp.detection.catalog import RULES_DIR, load_catalog, validate_rule
from ztp.detection.engine import DetectionEngine
from ztp.detection.expr import SafeExpr, _Signals
from ztp.detection.testing import run_rule_tests


def _eval(expr: str, **sig) -> bool:
    return bool(eval(SafeExpr(expr).compile(), {"__builtins__": {}}, _Signals(sig)))


def test_safe_expr_basic_logic():
    assert _eval("a > 3.0 and (b == 1 or c < 0.001)", a=4, b=0, c=1e-5)
    assert not _eval("a > 3.0 and b == 1", a=4, b=0)
    assert _eval("x + y >= 1", x=0, y=1)


def test_safe_expr_missing_signal_is_false():
    assert not _eval("bilinmeyen > 1")  # NaN karşılaştırması False
    assert not _eval("bilinmeyen == 1")


@pytest.mark.parametrize("bad", ["__import__('os')", "a.b > 1", "f(x) > 1", "[1,2]", "a if b else c", "lambda: 1"])
def test_safe_expr_rejects_unsafe_constructs(bad):
    with pytest.raises(ValueError):
        SafeExpr(bad)


def test_threshold_jitter_only_touches_float_thresholds():
    e = SafeExpr("a > 3.0 and n >= 1 and f == 1")
    code = e.compile(jitter=0.05, seed="UEBA-0001|2026-01-01")
    # tam sayı eşikler ve eşitlikler değişmez: n=1, f=1 sağlanmalı; a=3.2 ±%5 içinde belirsiz olabilir → a büyük seçildi
    assert eval(code, {"__builtins__": {}}, _Signals(dict(a=4.0, n=1, f=1)))
    # aynı tohum → aynı sonuç (tekrarlanabilirlik), farklı tohum → farklı eşik olabilir ama kural bozulmaz
    assert e.compile(jitter=0.05, seed="s").co_consts == e.compile(jitter=0.05, seed="s").co_consts


def test_packaged_catalog_is_valid():
    catalog = load_catalog()
    assert len(catalog) >= 17
    ids = {r["id"] for r in catalog}
    assert {"UEBA-0001", "UEBA-0003", "DQ-0010", "PRED-0012", "REL-0015"} <= ids
    for r in catalog:
        assert validate_rule(r) == [], r["id"]
        assert r["test_senaryolari"], f"{r['id']}: test senaryosu yok (19.1)"


def test_catalog_rule_unit_tests_pass(capsys):
    assert run_rule_tests(load_catalog())


def test_validate_rule_reports_problems():
    errs = validate_rule(dict(id="X", durum="yayinda", mantik=dict(kosullar=[])))
    assert any("runbook" in e for e in errs)
    assert any("kosullar" in e for e in errs)
    assert any("eksik alan" in e for e in errs)


def test_missing_source_disables_rule_and_shadow_rules_do_not_hit():
    cfg = TenantConfig(available_sources=("ad", "hr"), threshold_jitter=0.0)
    engine = DetectionEngine(cfg, load_catalog())
    assert "UEBA-0003" in engine.disabled  # proxy yok → devre dışı (11.1)
    assert "UEBA-0001" not in engine.disabled
    day = pd.Timestamp("2026-01-05")
    hits = engine.evaluate(
        day,
        "sid",
        "U-0001",
        dict(saat_sapmasi_z=5.0, servis_hesabi=0, mesai_disi_saatler=[3.0]),
        {"logon": ["E-1"]},
        {},
        ("UEBA",),
    )
    assert [h.rule_id for h in hits] == ["UEBA-0001"]
    assert hits[0].evidence == ["E-1"]
    assert 0.5 < hits[0].severity < 1.0


def test_service_account_suppression_is_logged():
    cfg = TenantConfig(threshold_jitter=0.0)
    engine = DetectionEngine(cfg, load_catalog())
    day = pd.Timestamp("2026-01-05")
    hits = engine.evaluate(day, "sid", "U-0001", dict(saat_sapmasi_z=5.0, servis_hesabi=1), {}, {}, ("UEBA",))
    assert hits == []
    assert engine.suppressed_log and engine.suppressed_log[-1]["neden"] == "servis_hesaplari"


def test_suspended_source_skips_dependent_rules():
    cfg = TenantConfig(threshold_jitter=0.0)
    engine = DetectionEngine(cfg, load_catalog())
    dq = {"ad": {"durum": "askida"}}
    hits = engine.evaluate(
        pd.Timestamp("2026-01-05"), "sid", "U-0001", dict(saat_sapmasi_z=5.0, servis_hesabi=0), {}, dq, ("UEBA",)
    )
    assert hits == []
    assert engine.skipped_dq["UEBA-0001"] == 1


def test_rules_dir_exists():
    assert RULES_DIR.is_dir() and any(RULES_DIR.glob("*.yaml"))
