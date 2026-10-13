"""Energy, cost, carbon and savings calculations.

Conventions
-----------
* Power is in watts (W); energy is in kilowatt-hours (kWh).
* Energy between two readings is integrated with the trapezoidal rule:
  ``E[kWh] = (P1 + P2) / 2 [W] * dt [s] / 3_600_000``.
* Gaps longer than ``max_gap_s`` are *not* integrated (we do not invent data); they are
  reported as uncovered time instead.
* Savings are **estimates** based on a stated counterfactual (the load would have kept
  drawing its pre-shutdown power), capped at a configurable horizon.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

J_PER_KWH = 3_600_000.0


def interval_energy_kwh(p1_w: float, p2_w: float, dt_s: float) -> float:
    """Trapezoidal energy (kWh) between two power samples ``dt_s`` seconds apart."""
    if dt_s <= 0:
        return 0.0
    if p1_w < 0 or p2_w < 0:
        raise ValueError("power must be non-negative")
    return (p1_w + p2_w) / 2.0 * dt_s / J_PER_KWH


def constant_power_kwh(power_w: float, hours: float) -> float:
    return max(power_w, 0.0) * max(hours, 0.0) / 1000.0


@dataclass
class IntegrationResult:
    energy_kwh: float
    covered_s: float
    gap_s: float


def integrate_kwh(samples: Sequence[tuple[datetime, float]], max_gap_s: float) -> IntegrationResult:
    """Integrate a time series of (timestamp, watts). Samples need not be sorted."""
    pts = sorted(samples, key=lambda s: s[0])
    energy = covered = gap = 0.0
    for (t0, p0), (t1, p1) in zip(pts, pts[1:], strict=False):
        dt = (t1 - t0).total_seconds()
        if dt <= 0:
            continue
        if dt > max_gap_s:
            gap += dt
            continue
        energy += interval_energy_kwh(p0, p1, dt)
        covered += dt
    return IntegrationResult(energy, covered, gap)


BUCKET_MINUTES = 15  # aligns with every real-world UTC offset (incl. +5:30, +5:45)


def bucket_floor(dt: datetime, minutes: int = BUCKET_MINUTES) -> datetime:
    return dt.replace(minute=dt.minute - dt.minute % minutes, second=0, microsecond=0)


def split_by_bucket(t0: datetime, t1: datetime, minutes: int = BUCKET_MINUTES) -> list[tuple[datetime, float]]:
    """Split [t0, t1) into fixed UTC buckets. Returns (bucket_start, fraction_of_interval)."""
    total = (t1 - t0).total_seconds()
    if total <= 0:
        return []
    out: list[tuple[datetime, float]] = []
    cur = t0
    while cur < t1:
        bucket = bucket_floor(cur, minutes)
        nxt = min(bucket + timedelta(minutes=minutes), t1)
        out.append((bucket, (nxt - cur).total_seconds() / total))
        cur = nxt
    return out


# ---------------------------------------------------------------------------
# Tariffs
# ---------------------------------------------------------------------------
def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def time_in_window(t: time, start: time, end: time) -> bool:
    """Half-open window [start, end); supports windows crossing midnight."""
    if start == end:
        return False
    if start < end:
        return start <= t < end
    return t >= start or t < end


@dataclass
class TouPeriod:
    name: str
    start: str
    end: str
    rate: float


@dataclass
class Tariff:
    flat_rate: float
    currency: str = "INR"
    tou_enabled: bool = False
    tou_periods: list[TouPeriod] = field(default_factory=list)
    timezone: str = "UTC"

    def rate_at(self, dt_utc: datetime) -> float:
        if self.tou_enabled and self.tou_periods:
            local = dt_utc.astimezone(ZoneInfo(self.timezone)).time()
            for p in self.tou_periods:
                if time_in_window(local, _parse_hhmm(p.start), _parse_hhmm(p.end)):
                    return p.rate
        return self.flat_rate

    def cost(self, kwh: float, at: datetime) -> float:
        return kwh * self.rate_at(at)


def carbon_kg(kwh: float, factor_kg_per_kwh: float) -> float:
    return kwh * factor_kg_per_kwh


# ---------------------------------------------------------------------------
# Savings
# ---------------------------------------------------------------------------
def estimated_avoided_kwh(
    baseline_w: float, started_at: datetime, ended_at: datetime | None, now: datetime, cap_hours: float
) -> float:
    """Estimated energy avoided by keeping a load off.

    Counterfactual: the load would have kept drawing ``baseline_w`` until the episode ended
    (load switched back on / room re-occupied). Duration is capped at ``cap_hours``.
    """
    end = ended_at or now
    hours = max((end - started_at).total_seconds(), 0.0) / 3600.0
    return constant_power_kwh(baseline_w, min(hours, cap_hours))


def sum_kwh(values: Iterable[float]) -> float:
    return float(sum(values))
