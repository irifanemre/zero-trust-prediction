"""İstatistiksel yöntemler — Bölüm 10. Her yöntemin NEDEN seçildiği dokümanda; burada uygulaması var."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np

EPS = 1e-9


def mad(x: Iterable[float]) -> float:
    a = np.asarray(list(x), dtype=float)
    a = a[~np.isnan(a)]
    if a.size == 0:
        return float("nan")
    return float(np.median(np.abs(a - np.median(a))))


def robust_z(x: float, median: float, mad_value: float, floor: float = 0.0) -> float:
    """10.1 Robust z-score: z = 0.6745 × (x − medyan) / MAD. Klasik z değil: aykırı değerler tahmini bozmasın."""
    if median is None or (isinstance(median, float) and math.isnan(median)):
        return float("nan")
    scale = mad_value if (mad_value is not None and not math.isnan(mad_value) and mad_value > 0) else 0.0
    scale = max(scale, floor, EPS)
    return 0.6745 * (x - median) / scale


def poisson_sf(k: int, lam: float) -> float:
    """10.2 P(X ≥ k) — sayım verisine z-score uygulanmaz; düşük sayılarda bol yanlış pozitif üretir."""
    k = int(k)
    if k <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    k = min(k, 5000)
    log_p, cdf = -lam, 0.0
    for i in range(k):
        if i > 0:
            log_p += math.log(lam) - math.log(i)
        cdf += math.exp(log_p)
        if cdf >= 1.0:
            break
    return float(min(1.0, max(0.0, 1.0 - cdf)))


def negbin_sf(k: int, mean: float, var: float) -> float:
    """10.2 Aşırı yayılım (overdispersion) varsa negatif binom; yoksa Poisson."""
    if mean <= 0:
        return 0.0 if k > 0 else 1.0
    if var is None or math.isnan(var) or var <= mean * 1.5:
        return poisson_sf(k, mean)
    r = mean**2 / (var - mean)
    p = r / (r + mean)
    k = min(int(k), 5000)
    cdf = 0.0
    for i in range(k):
        lp = math.lgamma(i + r) - math.lgamma(i + 1) - math.lgamma(r) + r * math.log(p) + i * math.log(1 - p)
        cdf += math.exp(lp)
        if cdf >= 1.0:
            break
    return float(min(1.0, max(0.0, 1.0 - cdf)))


@dataclass
class CircularStats:
    mean_hour: float
    circ_std_hours: float
    resultant: float  # R (0..1) — yoğunlaşma
    kappa: float  # von Mises yoğunlaşma parametresi (yaklaşık)
    n: int


def circular_stats(hours: Iterable[float]) -> Optional[CircularStats]:
    """10.3 Saat verisi döngüseldir: 23:00 ile 01:00 arası 2 saattir. Birim çember + von Mises."""
    h = np.asarray([v for v in hours if v is not None and not (isinstance(v, float) and math.isnan(v))], dtype=float)
    if h.size == 0:
        return None
    ang = h * 2 * math.pi / 24.0
    c, s = float(np.cos(ang).mean()), float(np.sin(ang).mean())
    r = math.hypot(c, s)
    mean = math.atan2(s, c) % (2 * math.pi)
    circ_std = math.sqrt(-2 * math.log(r)) if r > 1e-6 else math.pi
    if r < 0.53:
        kappa = 2 * r + r**3 + 5 * r**5 / 6
    elif r < 0.85:
        kappa = -0.4 + 1.39 * r + 0.43 / (1 - r)
    else:
        kappa = 1 / (r**3 - 4 * r**2 + 3 * r + 1e-9)
    return CircularStats(mean / (2 * math.pi) * 24.0, circ_std / (2 * math.pi) * 24.0, r, kappa, int(h.size))


def circular_deviation_z(hour: float, cs: CircularStats, floor_hours: float = 0.75) -> float:
    d = abs(((hour - cs.mean_hour) + 12.0) % 24.0 - 12.0)  # dairesel mesafe (saat)
    return d / max(cs.circ_std_hours, floor_hours)


def ewma(values: Sequence[float], alpha: float) -> List[float]:
    """10.4 Üstel ağırlıklı hareketli ortalama — meşru kaymayı takip eder."""
    out, s = [], None
    for v in values:
        s = v if s is None else alpha * v + (1 - alpha) * s
        out.append(s)
    return out


def drift_suspicion(short_med: float, long_med: float, long_mad: float, threshold_z: float) -> bool:
    """9.2 / 10.4: kısa pencere (7g) ile uzun pencere (90g) farkı eşiği aşarsa bu meşru kayma değil, zehirleme şüphesidir."""
    if any(math.isnan(v) for v in (short_med, long_med, long_mad)):
        return False
    scale = max(long_mad / 0.6745, 0.1 * abs(long_med), EPS)
    return (short_med - long_med) / scale > threshold_z


def jaccard(a: Set, b: Set) -> float:
    """10.6 Küme farkı — 'ilk kez görülen' bir mesafe değil küme sorusudur."""
    if not a and not b:
        return 1.0
    return len(a & b) / max(1, len(a | b))


@dataclass
class ChangePoint:
    index: int
    shift_z: float
    f_stat: float
    days_ago: int


def changepoint_mean_shift(x: Sequence[float], min_seg: int = 5) -> Optional[ChangePoint]:
    """10.7 Değişim noktası tespiti (ikili bölütleme, ortalama kayması). Trend analizi ani sıçramayı kaçırır; bu yakalar."""
    a = np.asarray(x, dtype=float)
    n = a.size
    if n < 2 * min_seg:
        return None
    cs, cs2 = np.cumsum(a), np.cumsum(a**2)
    total_sse = cs2[-1] - cs[-1] ** 2 / n
    best_k, best_gain = None, -1.0
    for k in range(min_seg, n - min_seg + 1):
        s1, q1, n1 = cs[k - 1], cs2[k - 1], k
        s2, q2, n2 = cs[-1] - s1, cs2[-1] - q1, n - k
        gain = total_sse - ((q1 - s1**2 / n1) + (q2 - s2**2 / n2))
        if gain > best_gain:
            best_k, best_gain = k, gain
    if best_k is None:
        return None
    before, after = a[:best_k], a[best_k:]
    scale = max(mad(before) / 0.6745, 0.1 * abs(float(np.median(before))), 0.25)
    shift_z = float((np.median(after) - np.median(before)) / scale)
    f_stat = float(best_gain / (((total_sse - best_gain) / max(n - 2, 1)) + EPS))
    return ChangePoint(best_k, shift_z, f_stat, n - best_k)


def sigmoid(v: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, v))))


def linear_slope(y: Sequence[float]) -> float:
    a = np.asarray(y, dtype=float)
    if a.size < 3:
        return 0.0
    xs = np.arange(a.size, dtype=float)
    xs -= xs.mean()
    return float((xs * (a - a.mean())).sum() / max((xs**2).sum(), EPS))


def age_weights(age_days: int) -> Tuple[float, float]:
    """9.2 Baseline ağırlıklandırma: (akran, kişisel). Akran ağırlığı HİÇ sıfırlanmaz (ADR-007)."""
    if age_days <= 14:
        return 1.0, 0.0
    if age_days <= 30:
        return 0.7, 0.3
    if age_days <= 60:
        return 0.3, 0.7
    return 0.15, 0.85
