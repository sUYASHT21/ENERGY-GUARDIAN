"""Backfill of *simulated* historical energy records so history charts have context on first run.

Rows are written with ``source="simulation"`` and are only generated for simulated devices.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy.orm import Session

from ..models import Appliance, EnergyRecord
from ..services.energy import BUCKET_MINUTES, bucket_floor
from ..services.settings_service import load_settings
from .profiles import profile_for


def occupancy_probability(room_type: str, weekday: bool, hour: int) -> float:
    """Probability that a room is in use, by room type, weekday flag and local hour."""
    if room_type == "hostel":
        if 0 <= hour < 6:
            return 0.9  # asleep in room
        if 6 <= hour < 9 or 18 <= hour < 24:
            return 0.8
        return 0.25 if weekday else 0.6
    if not weekday:
        return 0.05
    if room_type == "laboratory":
        return 0.75 if 10 <= hour < 17 else 0.03
    return 0.8 if 9 <= hour < 17 and hour != 13 else 0.04  # classroom / office


def backfill(db: Session, *, now: datetime, days: int, seed: int = 7) -> int:
    if days <= 0 or db.query(EnergyRecord).first() is not None:
        return 0
    rs = load_settings(db)
    tz = ZoneInfo(rs.timezone)
    tariff = rs.tariff()
    rng = np.random.default_rng(seed)
    end = bucket_floor(now)
    start = end - timedelta(days=days)
    appliances = [a for a in db.query(Appliance).all() if a.device is not None and a.device.kind == "simulated"]
    rows = []
    bucket_h = BUCKET_MINUTES / 60
    t = start
    while t < end:
        local = t.astimezone(tz)
        weekday = local.weekday() < 5
        for a in appliances:
            prof = profile_for(a.appliance_type)
            if a.essential:
                duty = 0.5 if prof.cycling else 1.0
                on_frac = duty
                wasted_frac = 0.0
            else:
                p_occ = occupancy_probability(a.room.room_type, weekday, local.hour)
                occupied = rng.random() < p_occ
                if occupied:
                    on_frac = 1.0 if a.appliance_type in ("light", "fan") else float(rng.uniform(0.4, 1.0))
                    wasted_frac = 0.0
                else:
                    # sometimes appliances are left running in an empty room
                    on_frac = float(rng.uniform(0.5, 1.0)) if rng.random() < 0.08 else 0.0
                    wasted_frac = on_frac
            if on_frac <= 0:
                continue
            ratio = float(np.mean(prof.on_ratio)) * (0.6 if prof.cycling else 1.0)
            kwh = a.rated_power_w * ratio * on_frac * bucket_h / 1000.0
            wasted = kwh * (wasted_frac / on_frac) if on_frac else 0.0
            rows.append(EnergyRecord(appliance_id=a.id, room_id=a.room_id, period_start=t, energy_kwh=kwh,
                                     wasted_kwh=wasted, cost=tariff.cost(kwh, t + timedelta(minutes=BUCKET_MINUTES / 2)),
                                     source="simulation"))
        t += timedelta(minutes=BUCKET_MINUTES)
    db.add_all(rows)
    db.flush()
    return len(rows)
