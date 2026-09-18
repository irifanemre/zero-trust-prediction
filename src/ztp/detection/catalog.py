"""Detection-as-code kataloğu — 12.1.

Kurallar uygulama koduna gömülmez; her tespit sürüm kontrollü bir YAML dosyasıdır (Sigma benzeri).
Paketle birlikte gelen katalog `ztp/detection/rules/` dizinindedir; müşteri bazında farklı bir dizin verilebilir.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional, Union

import yaml

LOG = logging.getLogger(__name__)
RULES_DIR = Path(__file__).resolve().parent / "rules"
REQUIRED_FIELDS = (
    "id",
    "ad",
    "surum",
    "durum",
    "katman",
    "attack",
    "veri_kaynaklari",
    "mantik",
    "siddet",
    "agirlik",
    "sahip",
    "kanit",
    "test_senaryolari",
)
VALID_STATES = ("taslak", "golge-modda", "yayinda", "emekli")


def validate_rule(rule: dict) -> List[str]:
    """Tanım dosyasının zorunlu alanlarını ve yaşam döngüsü durumunu doğrular; hata listesi döndürür."""
    errors = [f"eksik alan: {k}" for k in REQUIRED_FIELDS if k not in rule]
    if rule.get("durum") not in VALID_STATES:
        errors.append(f"geçersiz durum: {rule.get('durum')!r} (beklenen: {', '.join(VALID_STATES)})")
    if not isinstance(rule.get("mantik", {}).get("kosullar"), list) or not rule.get("mantik", {}).get("kosullar"):
        errors.append("mantik.kosullar boş olamaz")
    if rule.get("durum") == "yayinda" and not rule.get("runbook"):
        errors.append("runbook olmadan kural yayında olamaz (17.4)")
    return errors


def load_catalog(det_dir: Optional[Union[str, Path]] = None) -> List[dict]:
    """Dizindeki tüm kural dosyalarını yükler ve doğrular. Dizin verilmezse paket kataloğu kullanılır."""
    p = Path(det_dir) if det_dir else RULES_DIR
    files = sorted(list(p.glob("*.yaml")) + list(p.glob("*.yml")) + list(p.glob("*.json")))
    if not files:
        raise FileNotFoundError(f"Tespit tanımı bulunamadı: {p}")
    catalog: List[dict] = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            rule = json.load(fh) if f.suffix == ".json" else yaml.safe_load(fh)
        problems = validate_rule(rule)
        if problems:
            raise ValueError(f"{f.name}: " + "; ".join(problems))
        catalog.append(rule)
    ids = [r["id"] for r in catalog]
    if len(ids) != len(set(ids)):
        raise ValueError("Katalogda yinelenen kural kimliği var")
    LOG.info("Detection-as-code: %d kural yüklendi (%s)", len(catalog), p)
    return catalog


def export_catalog(catalog: List[dict], out_dir: Union[str, Path]) -> None:
    """Kataloğu (müşteri çıktısı olarak) YAML dosyalarına yazar — çalışan sürümün kaydı."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for r in catalog:
        with open(out / f"{r['id']}.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(r, f, allow_unicode=True, sort_keys=False)
