from datetime import UTC, datetime, timedelta

import pytest

from app.services.energy import (
    Tariff,
    TouPeriod,
    bucket_floor,
    carbon_kg,
    constant_power_kwh,
    estimated_avoided_kwh,
    integrate_kwh,
    interval_energy_kwh,
    split_by_bucket,
    time_in_window,
)

T0 = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)


def test_constant_1kw_for_1h_is_1kwh():
    assert interval_energy_kwh(1000, 1000, 3600) == pytest.approx(1.0)
    assert constant_power_kwh(1000, 1) == pytest.approx(1.0)


def test_trapezoid_ramp():
    # ramp 0 -> 2000 W over 1 h = average 1000 W = 1 kWh
    assert interval_energy_kwh(0, 2000, 3600) == pytest.approx(1.0)


def test_zero_or_negative_dt_gives_zero():
    assert interval_energy_kwh(500, 500, 0) == 0
    assert interval_energy_kwh(500, 500, -5) == 0


def test_negative_power_rejected():
    with pytest.raises(ValueError):
        interval_energy_kwh(-1, 10, 10)


def test_integrate_series_sums_intervals():
    # 100 W sampled every 10 s for 1 h -> 0.1 kWh
    samples = [(T0 + timedelta(seconds=10 * i), 100.0) for i in range(361)]
    res = integrate_kwh(samples, max_gap_s=60)
    assert res.energy_kwh == pytest.approx(0.1)
    assert res.covered_s == pytest.approx(3600)
    assert res.gap_s == 0


def test_integrate_skips_large_gaps_and_unsorted_input():
    samples = [(T0 + timedelta(minutes=30), 1000.0), (T0, 1000.0), (T0 + timedelta(minutes=10), 1000.0)]
    res = integrate_kwh(samples, max_gap_s=15 * 60)
    # 0-10 min integrated (1/6 kWh); 10-30 min gap (20 min) is not invented
    assert res.energy_kwh == pytest.approx(1000 * 600 / 3_600_000)
    assert res.gap_s == pytest.approx(1200)


def test_split_by_bucket_across_boundaries():
    t0 = T0 + timedelta(minutes=10)
    t1 = T0 + timedelta(minutes=40)
    parts = split_by_bucket(t0, t1)
    assert [p[0] for p in parts] == [T0, T0 + timedelta(minutes=15), T0 + timedelta(minutes=30)]
    assert [round(p[1], 4) for p in parts] == [round(5 / 30, 4), 0.5, round(10 / 30, 4)]
    assert sum(p[1] for p in parts) == pytest.approx(1.0)


def test_bucket_floor():
    assert bucket_floor(T0 + timedelta(minutes=29, seconds=59)) == T0 + timedelta(minutes=15)


def test_flat_tariff():
    t = Tariff(flat_rate=8.0)
    assert t.cost(2.5, T0) == pytest.approx(20.0)


def test_time_of_use_tariff_with_midnight_window():
    t = Tariff(flat_rate=8.0, tou_enabled=True, timezone="Asia/Kolkata",
               tou_periods=[TouPeriod("peak", "18:00", "22:00", 10.0), TouPeriod("night", "22:00", "06:00", 5.0)])
    # 13:00 UTC = 18:30 IST -> peak
    assert t.rate_at(datetime(2026, 1, 5, 13, 0, tzinfo=UTC)) == 10.0
    # 20:00 UTC = 01:30 IST -> night window crossing midnight
    assert t.rate_at(datetime(2026, 1, 5, 20, 0, tzinfo=UTC)) == 5.0
    # 06:00 UTC = 11:30 IST -> flat
    assert t.rate_at(datetime(2026, 1, 5, 6, 0, tzinfo=UTC)) == 8.0


def test_tou_disabled_uses_flat():
    t = Tariff(flat_rate=7.0, tou_enabled=False, tou_periods=[TouPeriod("p", "00:00", "23:59", 99.0)])
    assert t.rate_at(T0) == 7.0


def test_time_window_edges():
    from datetime import time
    assert time_in_window(time(9, 0), time(9, 0), time(10, 0))
    assert not time_in_window(time(10, 0), time(9, 0), time(10, 0))
    assert not time_in_window(time(9, 0), time(9, 0), time(9, 0))


def test_carbon():
    assert carbon_kg(10, 0.71) == pytest.approx(7.1)


def test_savings_estimate_and_cap():
    # 1500 W off for 2 h -> 3 kWh
    assert estimated_avoided_kwh(1500, T0, T0 + timedelta(hours=2), T0 + timedelta(hours=5), 8) == pytest.approx(3.0)
    # open episode uses "now" and is capped at 8 h
    assert estimated_avoided_kwh(1000, T0, None, T0 + timedelta(hours=20), 8) == pytest.approx(8.0)
    # never negative
    assert estimated_avoided_kwh(1000, T0, T0 - timedelta(hours=1), T0, 8) == 0
