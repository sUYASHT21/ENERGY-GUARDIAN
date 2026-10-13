"""Feature extraction for electrical anomaly detection.

The anomaly model looks at *electrical behaviour only*. Occupancy and time-of-day are
deliberately excluded: wastage in vacant rooms is decided by the deterministic engine,
not by the ML model.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..simulation.profiles import NOMINAL_VOLTAGE

FEATURE_NAMES = ["power_ratio", "delta_ratio", "voltage_dev", "power_factor", "relay_mismatch"]


@dataclass
class ReadingContext:
    power_w: float
    rated_power_w: float
    standby_threshold_w: float
    voltage_v: float | None = None
    current_a: float | None = None
    relay_on: bool | None = None
    prev_power_w: float | None = None


def extract(ctx: ReadingContext) -> np.ndarray:
    rated = max(ctx.rated_power_w, 1.0)
    power_ratio = min(max(ctx.power_w, 0.0) / rated, 10.0)
    delta_ratio = 0.0 if ctx.prev_power_w is None else min(abs(ctx.power_w - ctx.prev_power_w) / rated, 10.0)
    voltage_dev = 0.0 if ctx.voltage_v is None else (ctx.voltage_v - NOMINAL_VOLTAGE) / NOMINAL_VOLTAGE
    if ctx.voltage_v and ctx.current_a and ctx.voltage_v > 0 and ctx.current_a > 0 and ctx.power_w > ctx.standby_threshold_w:
        pf = min(ctx.power_w / (ctx.voltage_v * ctx.current_a), 2.0)
    else:
        pf = 0.9  # neutral value when the load is off or V/I are not reported
    mismatch = 1.0 if (ctx.relay_on is False and ctx.power_w > ctx.standby_threshold_w) else 0.0
    return np.array([power_ratio, delta_ratio, voltage_dev, pf, mismatch], dtype=float)
