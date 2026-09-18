"""Kalıcı durum ve artımlı koşu: toplu koşu == (toplu ısınma + gün gün artımlı) eşdeğerliği, idempotentlik, budama, dosya girişi."""

import json

import pandas as pd
import pytest

from ztp.config import TenantConfig
from ztp.data.files import dataset_from_files, load_events_file
from ztp.data.synthetic import SyntheticOrg
from ztp.detection.catalog import load_catalog
from ztp.graph.store import NetworkXGraphStore
from ztp.pipeline import ZeroTrustPredictionPipeline
from ztp.state import StateStore

END = pd.Timestamp("2026-09-16")
EVAL_DAYS = 6
SPLIT = 3  # ilk 3 gün toplu, kalan 3 gün artımlı


def _dataset():
    cfg = TenantConfig()
    return SyntheticOrg(
        n_users=50, n_days=cfg.long_window_days + 8 + EVAL_DAYS, eval_days=EVAL_DAYS, end_day=END, seed=11
    ).build()


def _queues(out_dir, tenant):
    q = {}
    for p in sorted((out_dir / tenant / "cases").glob("*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        q.setdefault(c["gun"], []).append((c["kullanici"], c["ham_skor"], sorted(h["kural"] for h in c["tespitler"])))
    return q


@pytest.mark.slow
def test_batch_equals_incremental(tmp_path):
    """Aynı veri: (A) 6 gün toplu; (B) 3 gün toplu + durum kaydı, sonra 3 gün 'yükle→işle→kaydet'. Kuyruklar birebir aynı olmalı."""
    catalog = load_catalog()
    start = END - (EVAL_DAYS - 1) * pd.Timedelta(days=1)
    # (A) toplu referans
    cfg_a = TenantConfig(tenant_id="A", alarm_budget_per_day=4, threshold_jitter=0.0)
    ZeroTrustPredictionPipeline(cfg_a, _dataset(), catalog, tmp_path / "a").run(start, END, warmup_days=8)
    ref = _queues(tmp_path / "a", "A")
    # (B) toplu ısınma (ilk SPLIT gün) + durum kaydı
    cfg_b = TenantConfig(tenant_id="B", alarm_budget_per_day=4, threshold_jitter=0.0)
    data_b = _dataset()
    split_end = start + (SPLIT - 1) * pd.Timedelta(days=1)
    state_path = tmp_path / "b" / "B" / "state.sqlite"
    ZeroTrustPredictionPipeline(cfg_b, data_b, catalog, tmp_path / "b", state=StateStore(state_path)).run(
        start, split_end, warmup_days=8
    )
    assert StateStore(state_path).watermark == split_end
    # artımlı günler: her gün yeni bir boru hattı örneği, yalnızca o günün ham olayları
    full = _dataset()
    for k in range(SPLIT, EVAL_DAYS):
        day = start + k * pd.Timedelta(days=1)
        ev_day = full.events[full.events["time"].dt.normalize() == day]
        day_data = type(full)(full.name, full.directory.copy(), full.ip_leases, ev_day, full.leaves, [], full.critical_assets)
        pipe = ZeroTrustPredictionPipeline(cfg_b, day_data, catalog, tmp_path / "b", state=StateStore(state_path))
        pipe.run_incremental(day, ev_day)
    inc = _queues(tmp_path / "b", "B")
    assert set(ref) == set(inc)
    for day in ref:
        assert ref[day] == inc[day], f"{day}: toplu {ref[day]} ≠ artımlı {inc[day]}"


def test_incremental_is_idempotent_and_requires_state(tmp_path):
    catalog = load_catalog()
    cfg = TenantConfig(tenant_id="C", alarm_budget_per_day=3, threshold_jitter=0.0)
    data = _dataset()
    start = END - (EVAL_DAYS - 1) * pd.Timedelta(days=1)
    st = StateStore(tmp_path / "C" / "state.sqlite")
    ZeroTrustPredictionPipeline(cfg, data, catalog, tmp_path, state=st).run(start, start, warmup_days=3)
    day = start + pd.Timedelta(days=1)
    ev = data.events[data.events["time"].dt.normalize() == day]
    pipe = ZeroTrustPredictionPipeline(cfg, data, catalog, tmp_path, state=StateStore(st.path))
    pipe.run_incremental(day, ev)
    with pytest.raises(ValueError):  # aynı gün ikinci kez: su seviyesi korur
        ZeroTrustPredictionPipeline(cfg, data, catalog, tmp_path, state=StateStore(st.path)).run_incremental(day, ev)
    ZeroTrustPredictionPipeline(cfg, data, catalog, tmp_path, state=StateStore(st.path)).run_incremental(day, ev, force=True)
    with pytest.raises(RuntimeError):  # durum deposu olmadan artımlı koşu yok
        ZeroTrustPredictionPipeline(cfg, data, catalog, tmp_path).run_incremental(day, ev)


def test_state_store_roundtrip(tmp_path):
    st = StateStore(tmp_path / "s.sqlite")
    st.put("x", {"a": [1, 2], "b": pd.Timestamp("2026-01-01")})
    assert st.get("x")["a"] == [1, 2]
    df = pd.DataFrame(
        dict(sid=["u1"], day=[pd.Timestamp("2026-01-02")], apps=[frozenset({"b", "a"})], evidence=[{"k": ["e1"]}], n=[3])
    )
    st.put_frame("f", df)
    back = st.get_frame("f")
    assert back.loc[0, "apps"] == frozenset({"a", "b"}) and back.loc[0, "day"] == pd.Timestamp("2026-01-02")
    assert back.loc[0, "evidence"] == {"k": ["e1"]} and st.get_frame("yok") is None
    st.set_watermark(pd.Timestamp("2026-01-05"))
    assert StateStore(tmp_path / "s.sqlite").watermark == pd.Timestamp("2026-01-05")


def test_graph_store_export_import_prune():
    g = NetworkXGraphStore()
    g.add_edge("user:a", "device:x", "kullandi", pd.Timestamp("2026-01-01"))
    g.add_edge("user:a", "device:x", "kullandi", pd.Timestamp("2026-01-09"))
    g.add_edge("user:b", "resource:r", "eristi", pd.Timestamp("2025-10-01"))
    rows = g.export_edges()
    h = NetworkXGraphStore()
    assert h.import_edges(rows) == 2
    assert h.g["user:a"]["device:x"]["rel"]["kullandi"]["count"] == 2
    assert h.g["user:a"]["device:x"]["rel"]["kullandi"]["last_ts"] == pd.Timestamp("2026-01-09")
    assert h.prune(pd.Timestamp("2025-12-01")) == 1 and "user:b" not in h.g


def test_file_loaders_validate_schema(tmp_path):
    ev = pd.DataFrame(dict(event_id=["e1"], time=["2026-01-01 09:00"], source=["ad"], actor_raw=["KURUM\\a.b"]))
    ev.to_csv(tmp_path / "ev.csv", index=False)
    df = load_events_file(tmp_path / "ev.csv")
    assert list(df.columns)[:4] == ["event_id", "time", "received_time", "class_uid"] and df.loc[0, "bytes_out"] == 0
    pd.DataFrame(dict(event_id=["e1"])).to_csv(tmp_path / "bad.csv", index=False)
    with pytest.raises(ValueError):
        load_events_file(tmp_path / "bad.csv")
    pd.DataFrame(dict(sid=["S1"], ad_sam=["KURUM\\a.b"], upn=["a@b"], dept=["IT"], hire_date=["2025-01-01"])).to_csv(
        tmp_path / "dir.csv", index=False
    )
    ds = dataset_from_files(tmp_path / "ev.csv", tmp_path / "dir.csv")
    assert ds.directory.loc[0, "is_service"] is False or ds.directory.loc[0, "is_service"] == False  # noqa: E712
    assert len(ds.events) == 1 and ds.ip_leases.empty
