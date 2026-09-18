"""Kural koşulları için güvenli ifade değerlendirici; 21.2 eşik keşfine karşı kısmi rastgeleleştirme."""

from __future__ import annotations

import ast
import hashlib
from typing import Any


class SafeExpr:
    """Kural koşulları için güvenli ifade değerlendirici (yalnızca karşılaştırma, mantık ve aritmetik).
    21.2: ondalık eşikler ±jitter ile kısmen rastgeleleştirilir (kural+gün tohumlu → tekrarlanabilir, dışarıdan tahmin edilemez)."""

    ALLOWED = (
        ast.Expression,
        ast.BoolOp,
        ast.And,
        ast.Or,
        ast.Not,
        ast.UnaryOp,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.BinOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.Eq,
        ast.NotEq,
        ast.USub,
    )

    def __init__(self, expr: str):
        self.expr = expr
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, self.ALLOWED):
                raise ValueError(f"Kural ifadesinde izin verilmeyen yapı: {type(node).__name__} ({expr})")
        self.tree = tree

    def compile(self, jitter: float = 0.0, seed: str = "") -> Any:
        tree = self.tree
        if jitter > 0:
            tree = ast.parse(self.expr, mode="eval")
            i = 0
            for node in ast.walk(tree):
                if isinstance(node, ast.Compare):
                    for j, c in enumerate(node.comparators):
                        if (
                            isinstance(c, ast.Constant)
                            and isinstance(c.value, float)
                            and not isinstance(node.ops[j], (ast.Eq, ast.NotEq))
                        ):
                            h = int(hashlib.sha256(f"{seed}|{self.expr}|{i}".encode()).hexdigest(), 16)
                            u = (h % 20001) / 10000.0 - 1.0
                            c.value = c.value * (1 + jitter * u)
                            i += 1
            ast.fix_missing_locations(tree)
        return compile(tree, "<kural>", "eval")


class _Signals(dict):
    def __missing__(self, key):
        return float("nan")
