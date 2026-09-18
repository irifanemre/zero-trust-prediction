"""Komut satırı arayüzü: sentetik/CERT koşuları, kural testleri, analist etiketi."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from ztp.config import TenantConfig
from ztp.data.cert import load_cert_dataset
from ztp.data.synthetic import SyntheticOrg
from ztp.detection.catalog import load_catalog
from ztp.detection.testing import run_rule_tests
from ztp.feedback import FP_REASONS, LabelStore
from ztp.pipeline import ZeroTrustPredictionPipeline
from ztp.response import authorize_containment
from ztp.schema import DAY

LOG = logging.getLogger(__name__)


def cmd_label(args) -> None:
    out = Path(args.out) / args.tenant
    store = LabelStore(out / "labels.json")
    p = out / "cases" / f"{args.label}.json"
    if not p.exists():
        sys.exit(f"Vaka bulunamadı: {p}")
    case = json.loads(p.read_text(encoding="utf-8"))
    vault = (
        json.loads((out / "identity_vault.RESTRICTED.json").read_text(encoding="utf-8"))
        if (out / "identity_vault.RESTRICTED.json").exists()
        else {}
    )
    case["_sid"] = vault.get(case["kullanici"], {}).get("sid")
    rec = store.add(case, args.decision, args.analyst, args.reason, args.note or "")
    print("Etiket kaydedildi:", json.dumps(rec, ensure_ascii=False, indent=2))
    ok, msg = authorize_containment(case, rec)
    print("Müdahale yetkisi:", msg)
    print("Geri besleme metrikleri:", json.dumps(store.metrics(), ensure_ascii=False, indent=2))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Zero Trust Prediction — mimari doğrulama (MVP) script'i")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--synthetic", action="store_true", help="sentetik kurum + enjekte senaryolar (kör test/regresyon)")
    src.add_argument("--cert-dir", help="CERT Insider Threat dizini, ör. cert_data/r4.2 (birincil doğrulama)")
    ap.add_argument("--answers-dir", help="CERT cevap anahtarı dizini (varsayılan: <cert-dir>/../answers)")
    ap.add_argument("--config", help="müşteri yapılandırma dosyası (YAML); komut satırı değerleri dosyayı ezer")
    ap.add_argument("--tenant", default="musteri-A")
    ap.add_argument("--users", type=int, default=150)
    ap.add_argument("--days", type=int, default=30, help="değerlendirme penceresi (gün)")
    ap.add_argument("--warmup", type=int, default=21, help="risk serisi ısınma günü (vaka üretilmez)")
    ap.add_argument("--budget", type=int, default=8, help="alarm bütçesi N = analist kapasitesi (13.5)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--end", help="değerlendirme son günü (YYYY-MM-DD); varsayılan bugün")
    ap.add_argument("--out", default="./ztp_out")
    ap.add_argument("--detections-dir", help="detection-as-code YAML dizini (yoksa gömülü katalog)")
    ap.add_argument("--llm", default="none", choices=["none", "ollama", "anthropic"])
    ap.add_argument("--ollama-model", default="llama3.1")
    ap.add_argument("--test-rules", action="store_true", help="kural birim testlerini çalıştır ve çık")
    ap.add_argument("--label", help="vaka kimliği — analist kararı yaz")
    ap.add_argument("--decision", choices=["gercek_pozitif", "yanlis_pozitif", "belirsiz"])
    ap.add_argument("--reason", choices=sorted(FP_REASONS))
    ap.add_argument("--analyst", default="analist")
    ap.add_argument("--note")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    args.users_given = any(a.startswith("--users") for a in (argv if argv is not None else sys.argv[1:]))
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    catalog = load_catalog(args.detections_dir)
    if args.test_rules:
        print("Detection-as-code birim testleri (19.1 Katman 1):")
        return 0 if run_rule_tests(catalog) else 1
    if args.label:
        if not args.decision:
            sys.exit("--decision zorunlu")
        cmd_label(args)
        return 0
    if not args.synthetic and not args.cert_dir:
        args.synthetic = True
        LOG.info("Kaynak belirtilmedi; sentetik veri kullanılıyor")

    end = pd.Timestamp(args.end).normalize() if args.end else pd.Timestamp.utcnow().tz_localize(None).normalize()
    overrides = dict(
        tenant_id=args.tenant, alarm_budget_per_day=args.budget, llm_backend=args.llm, ollama_model=args.ollama_model
    )
    cfg = TenantConfig.from_yaml(args.config, **overrides) if args.config else TenantConfig(**overrides)
    if args.synthetic:
        n_days = cfg.long_window_days + args.warmup + args.days
        data = SyntheticOrg(n_users=args.users, n_days=n_days, eval_days=args.days, end_day=end, seed=args.seed).build()
    else:
        if not args.end:
            sys.exit("CERT için --end (veri aralığı içinde bir gün, ör. 2010-11-30) zorunludur")
        start_hist = end - (cfg.long_window_days + args.warmup + args.days) * DAY
        answers = args.answers_dir or str(Path(args.cert_dir).parent / "answers")
        data = load_cert_dataset(
            args.cert_dir, start_hist, end, max_users=(args.users if args.users_given else None), answers_dir=answers
        )
        # 11.1 kademeli işlevsellik: yalnızca mevcut kaynaklar (CERT'te EDR/VPN yok; r1'de e-posta/dosya da yok)
        cfg.available_sources = tuple(sorted(set(data.events["source"].unique()) | {"hr"}))
        LOG.info("Mevcut kaynaklar: %s", cfg.available_sources)
    start = end - (args.days - 1) * DAY
    pipe = ZeroTrustPredictionPipeline(cfg, data, catalog, Path(args.out))
    pipe.run(start, end, args.warmup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
