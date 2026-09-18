"""19.1 Katman 1 — kural birim testleri (tanımın parçası, sürekli entegrasyonda çalışır)."""

from __future__ import annotations

from typing import List

from ztp.detection.expr import SafeExpr, _Signals


def run_rule_tests(catalog: List[dict]) -> bool:
    """19.1 Katman 1 — birim testleri: her kuralın tetiklemesi/tetiklememesi gereken senaryolar (sürekli entegrasyonda çalışır)."""
    ok_all = True
    for r in catalog:
        exprs = [SafeExpr(c) for c in r["mantik"]["kosullar"]]
        for t in r.get("test_senaryolari", []):
            s = _Signals(t["sinyaller"])
            got = all(bool(eval(e.compile(), {"__builtins__": {}}, s)) for e in exprs)
            status = "GEÇTİ" if got == t["beklenen"] else "KALDI"
            ok_all &= got == t["beklenen"]
            print(f"  [{status}] {r['id']:10s} {t['ad']:40s} beklenen={t['beklenen']} sonuç={got}")
    return ok_all
