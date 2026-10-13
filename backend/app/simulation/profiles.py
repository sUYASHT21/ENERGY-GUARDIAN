"""Synthetic electrical behaviour of common appliance types.

These profiles are *synthetic* approximations used for simulation and for generating
clearly-labelled ML training data. They are not measurements.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

NOMINAL_VOLTAGE = 230.0


@dataclass(frozen=True)
class Profile:
    rated_w: float
    on_ratio: tuple[float, float]  # typical fraction of rated power when running
    jitter: float  # relative noise
    power_factor: tuple[float, float]
    cycling: bool = False  # compressor-style duty cycling (AC / fridge)
    standby_w: float = 0.0


PROFILES: dict[str, Profile] = {
    "light": Profile(40, (0.95, 1.0), 0.01, (0.90, 0.98)),
    "fan": Profile(75, (0.75, 1.0), 0.03, (0.85, 0.95)),
    "ac": Profile(1500, (0.55, 1.0), 0.05, (0.85, 0.95), cycling=True, standby_w=3),
    "projector": Profile(280, (0.9, 1.0), 0.02, (0.90, 0.98), standby_w=2),
    "computer": Profile(150, (0.4, 0.9), 0.08, (0.90, 0.99), standby_w=2),
    "lab_equipment": Profile(500, (0.5, 0.95), 0.06, (0.80, 0.95), standby_w=4),
    "heater": Profile(1000, (0.97, 1.0), 0.01, (0.98, 1.0)),
    "refrigerator": Profile(200, (0.6, 1.0), 0.05, (0.80, 0.92), cycling=True, standby_w=2),
    "server": Profile(400, (0.6, 0.85), 0.04, (0.92, 0.99)),
    "emergency_light": Profile(15, (0.95, 1.0), 0.01, (0.9, 0.98)),
    "other": Profile(100, (0.7, 1.0), 0.05, (0.85, 0.97)),
}


def profile_for(appliance_type: str) -> Profile:
    return PROFILES.get(appliance_type, PROFILES["other"])


def normal_reading(
    rng: np.random.Generator, appliance_type: str, rated_w: float, on: bool, prev_ratio: float | None = None
) -> tuple[float, float, float]:
    """Return (power_w, voltage_v, current_a) for a normally-behaving appliance."""
    prof = profile_for(appliance_type)
    voltage = float(rng.normal(NOMINAL_VOLTAGE, 2.5))
    if not on:
        power = float(max(0.0, rng.normal(prof.standby_w, prof.standby_w * 0.1 + 0.05))) if prof.standby_w else 0.0
        pf = 0.6
    else:
        lo, hi = prof.on_ratio
        if prev_ratio is not None and lo <= prev_ratio <= hi * 1.05:
            # random walk around the previous level keeps consecutive readings realistic
            ratio = float(np.clip(prev_ratio + rng.normal(0, (hi - lo) * 0.08), lo, hi))
        else:
            ratio = float(rng.uniform(lo, hi))
        ratio *= float(1 + rng.normal(0, prof.jitter))
        power = max(0.0, ratio * rated_w)
        pf = float(rng.uniform(*prof.power_factor))
    current = power / (voltage * pf) if power > 0 else 0.0
    return power, voltage, current
