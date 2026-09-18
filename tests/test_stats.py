"""Bölüm 10 istatistiksel yöntemlerin birim testleri."""

import math

import numpy as np
import pytest

from ztp.stats import (
    age_weights,
    changepoint_mean_shift,
    circular_deviation_z,
    circular_stats,
    drift_suspicion,
    ewma,
    jaccard,
    linear_slope,
    mad,
    negbin_sf,
    poisson_sf,
    robust_z,
    sigmoid,
)


def test_mad_ignores_outliers():
    assert mad([1, 2, 3, 4, 100]) == 1.0
    assert math.isnan(mad([]))


def test_robust_z_uses_mad_scaling():
    assert robust_z(10, 5, 1.0) == pytest.approx(0.6745 * 5)
    assert robust_z(10, 5, 0.0, floor=2.0) == pytest.approx(0.6745 * 2.5)  # MAD=0 → taban ölçek
    assert math.isnan(robust_z(1, float("nan"), 1))


def test_poisson_tail_matches_closed_form():
    lam = 2.0
    assert poisson_sf(0, lam) == 1.0
    assert poisson_sf(1, lam) == pytest.approx(1 - math.exp(-lam), rel=1e-9)
    assert poisson_sf(7, lam) == pytest.approx(0.0045338, rel=1e-3)
    assert poisson_sf(5, 0.0) == 0.0


def test_negbin_falls_back_to_poisson_without_overdispersion():
    assert negbin_sf(4, 2.0, 2.0) == pytest.approx(poisson_sf(4, 2.0))
    # aşırı yayılımda kuyruk daha kalındır
    assert negbin_sf(10, 2.0, 10.0) > poisson_sf(10, 2.0)


def test_circular_stats_handles_midnight_wraparound():
    cs = circular_stats([23.0, 0.5, 1.0, 23.5])
    assert cs is not None
    assert cs.mean_hour == pytest.approx(0.0, abs=0.3) or cs.mean_hour == pytest.approx(24.0, abs=0.3)
    assert cs.circ_std_hours < 1.5
    assert circular_deviation_z(12.0, cs) > 5


def test_circular_stats_empty():
    assert circular_stats([]) is None


def test_ewma_and_slope():
    assert ewma([1, 1, 1], 0.5) == [1, 1, 1]
    assert ewma([0, 10], 0.5)[-1] == 5
    assert linear_slope([1, 2, 3, 4]) == pytest.approx(1.0)
    assert linear_slope([1]) == 0.0


def test_drift_suspicion_flags_only_upward_drift():
    assert drift_suspicion(short_med=50, long_med=10, long_mad=2, threshold_z=2.5)
    assert not drift_suspicion(short_med=10, long_med=50, long_mad=2, threshold_z=2.5)
    assert not drift_suspicion(float("nan"), 1, 1, 2.5)


def test_jaccard():
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert jaccard({"a"}, {"b"}) == 0.0
    assert jaccard(set(), set()) == 1.0


def test_changepoint_detects_step():
    series = [1.0] * 12 + [8.0] * 8
    cp = changepoint_mean_shift(series, min_seg=4)
    assert cp is not None
    assert cp.index == 12
    assert cp.shift_z > 3
    assert cp.days_ago == 8


def test_changepoint_needs_minimum_length():
    assert changepoint_mean_shift([1, 2, 3], min_seg=5) is None


def test_sigmoid_bounds():
    assert sigmoid(0) == 0.5
    assert 0 < sigmoid(-1000) < 1e-6
    assert sigmoid(1000) > 1 - 1e-6


def test_age_weights_never_zero_peer():
    for age in (0, 14, 15, 30, 31, 60, 61, 400):
        peer, personal = age_weights(age)
        assert peer > 0  # ADR-007
        assert peer + personal == pytest.approx(1.0)
    assert age_weights(5) == (1.0, 0.0)
    assert age_weights(400) == (0.15, 0.85)


def test_numpy_inputs_accepted():
    assert mad(np.array([1.0, 2.0, 3.0])) == 1.0
