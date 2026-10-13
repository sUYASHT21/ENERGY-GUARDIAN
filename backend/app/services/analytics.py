"""Dashboard aggregates: live power, energy, waste, estimated savings, history series."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..context import AppContext
from ..models import Alert, Appliance, Device, EnergyRecord, Room, SavingsRecord, TelemetryReading
from .energy import BUCKET_MINUTES, Tariff, carbon_kg, estimated_avoided_kwh, split_by_bucket
from .settings_service import RuntimeSettings, load_settings


def local_midnight_utc(now: datetime, tz: str) -> datetime:
    local = now.astimezone(ZoneInfo(tz))
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(ZoneInfo("UTC"))


def savings_totals(records: list[SavingsRecord], *, now: datetime, cap_hours: float, tariff: Tariff,
                   since: datetime | None = None) -> dict:
    """Estimated avoided energy/cost for savings episodes, optionally only the part after ``since``."""
    kwh = cost = 0.0
    by_source: dict[str, float] = defaultdict(float)
    for r in records:
        cap_end = r.started_at + timedelta(hours=cap_hours)
        end = min(r.ended_at or now, cap_end, now)
        start = max(r.started_at, since) if since else r.started_at
        if end <= start:
            continue
        e = estimated_avoided_kwh(r.baseline_power_w, start, end, now, cap_hours)
        kwh += e
        by_source[r.source] += e
        for bucket, frac in split_by_bucket(start, end):
            cost += tariff.cost(e * frac, bucket + timedelta(minutes=BUCKET_MINUTES / 2))
    return {"kwh": kwh, "cost": cost, "by_source": dict(by_source)}


def _energy_since(db: Session, since: datetime, room_id: int | None = None) -> dict:
    q = db.query(EnergyRecord.source, func.sum(EnergyRecord.energy_kwh), func.sum(EnergyRecord.wasted_kwh),
                 func.sum(EnergyRecord.cost)).filter(EnergyRecord.period_start >= since)
    if room_id is not None:
        q = q.filter(EnergyRecord.room_id == room_id)
    out = {"energy_kwh": 0.0, "wasted_kwh": 0.0, "cost": 0.0, "by_source": {}}
    for source, e, w, c in q.group_by(EnergyRecord.source).all():
        out["energy_kwh"] += e or 0
        out["wasted_kwh"] += w or 0
        out["cost"] += c or 0
        out["by_source"][source] = round(e or 0, 4)
    return out


def device_health(dev: Device, now: datetime) -> dict:
    """Simple, explainable health score (0-100)."""
    score = 100
    issues = []
    if dev.connection_status != "online":
        score -= 60
        issues.append(dev.connection_status)
    if dev.sensor_status == "fault":
        score -= 25
        issues.append("occupancy sensor fault")
    if dev.rssi_dbm is not None and dev.rssi_dbm < -80:
        score -= 10
        issues.append(f"weak Wi-Fi ({dev.rssi_dbm} dBm)")
    if dev.error_count:
        score -= min(15, dev.error_count * 3)
        issues.append(f"{dev.error_count} errors")
    return {"score": max(score, 0), "issues": issues}


def summary(ctx: AppContext, db: Session) -> dict:
    now = ctx.clock.now()
    rs: RuntimeSettings = load_settings(db)
    tariff = rs.tariff()
    midnight = local_midnight_utc(now, rs.timezone)
    stale_limit = now - timedelta(seconds=ctx.settings.telemetry_stale_seconds)

    appliances = db.query(Appliance).all()
    live_w = 0.0
    live_by_source: dict[str, float] = defaultdict(float)
    states = {"on": 0, "off": 0, "unknown": 0}
    for a in appliances:
        states[a.state if a.state in states else "unknown"] += 1
        if a.last_reading_at and a.last_reading_at >= stale_limit and a.last_power_w is not None:
            live_w += a.last_power_w
            live_by_source[a.last_source or "unknown"] += a.last_power_w

    today = _energy_since(db, midnight)
    wasted_cost = sum(
        tariff.cost(w, ps + timedelta(minutes=BUCKET_MINUTES / 2))
        for ps, w in db.query(EnergyRecord.period_start, EnergyRecord.wasted_kwh)
        .filter(EnergyRecord.period_start >= midnight, EnergyRecord.wasted_kwh > 0).all())
    savings_recs = db.query(SavingsRecord).all()
    sav_today = savings_totals(savings_recs, now=now, cap_hours=rs.savings_cap_hours, tariff=tariff, since=midnight)
    sav_total = savings_totals(savings_recs, now=now, cap_hours=rs.savings_cap_hours, tariff=tariff)

    rooms = db.query(Room).all()
    occ = {"occupied": 0, "vacant": 0, "unknown": 0}
    for r in rooms:
        occ[r.occupancy_state] = occ.get(r.occupancy_state, 0) + 1
    devices = db.query(Device).all()
    dev_counts: dict[str, int] = defaultdict(int)
    for d in devices:
        dev_counts[d.connection_status] += 1
    open_alerts = db.query(Alert.severity, func.count()).filter(Alert.resolved.is_(False)).group_by(Alert.severity).all()
    unacked = db.query(func.count(Alert.id)).filter(Alert.resolved.is_(False), Alert.acknowledged.is_(False)).scalar()

    sources_live = sorted(k for k, v in live_by_source.items())
    sim = ctx.simulator
    return {
        "generated_at": now.isoformat(),
        "timezone": rs.timezone,
        "currency": rs.currency,
        "live_power_w": round(live_w, 1),
        "live_power_by_source": {k: round(v, 1) for k, v in live_by_source.items()},
        "energy_today_kwh": round(today["energy_kwh"], 4),
        "energy_today_by_source": today["by_source"],
        "cost_today": round(today["cost"], 2),
        "wasted_today_kwh": round(today["wasted_kwh"], 4),
        "wasted_cost_today": round(wasted_cost, 2),
        "wasted_co2_today_kg": round(carbon_kg(today["wasted_kwh"], rs.carbon_factor_kg_per_kwh), 3),
        "estimated_savings": {
            "label": "ESTIMATE — avoided energy assumes the load would have kept running at its pre-shutdown "
                     f"power until re-occupancy/switch-on, capped at {rs.savings_cap_hours:g} h.",
            "today_kwh": round(sav_today["kwh"], 4),
            "today_cost": round(sav_today["cost"], 2),
            "today_co2_kg": round(carbon_kg(sav_today["kwh"], rs.carbon_factor_kg_per_kwh), 3),
            "total_kwh": round(sav_total["kwh"], 4),
            "total_cost": round(sav_total["cost"], 2),
            "total_co2_kg": round(carbon_kg(sav_total["kwh"], rs.carbon_factor_kg_per_kwh), 3),
            "by_source": {k: round(v, 4) for k, v in sav_total["by_source"].items()},
            "episodes": len(savings_recs),
            "active_episodes": sum(1 for r in savings_recs if r.ended_at is None),
        },
        "carbon_today_kg": round(carbon_kg(today["energy_kwh"], rs.carbon_factor_kg_per_kwh), 3),
        "carbon_factor_kg_per_kwh": rs.carbon_factor_kg_per_kwh,
        "tariff_rate_now": tariff.rate_at(now),
        "rooms": {"total": len(rooms), **occ},
        "appliances": {"total": len(appliances), **states},
        "devices": {"total": len(devices), **dev_counts},
        "alerts": {"open": sum(c for _, c in open_alerts), "unacknowledged": unacked or 0,
                   "by_severity": {s: c for s, c in open_alerts}},
        "data_sources_live": sources_live,
        "simulation": {"enabled": ctx.settings.simulation_enabled, "running": bool(sim and sim.running)},
        "automation_mode": rs.automation_mode,
        "real_switching_enabled": ctx.settings.real_switching_enabled,
        "ml": {"method": ctx.anomaly.method, "model_version": ctx.anomaly.version},
    }


def history(ctx: AppContext, db: Session, *, hours: int, group: str, room_id: int | None = None) -> dict:
    """Energy/waste/cost series grouped by local hour or day, split by data source."""
    now = ctx.clock.now()
    rs = load_settings(db)
    tz = ZoneInfo(rs.timezone)
    if group == "day":
        start_local = (now.astimezone(tz) - timedelta(hours=hours)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_local = (now.astimezone(tz) - timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)
    since = start_local.astimezone(ZoneInfo("UTC"))
    q = db.query(EnergyRecord).filter(EnergyRecord.period_start >= since)
    if room_id is not None:
        q = q.filter(EnergyRecord.room_id == room_id)
    buckets: dict[str, dict] = {}
    for rec in q.all():
        local = rec.period_start.astimezone(tz)
        key = local.strftime("%Y-%m-%d") if group == "day" else local.strftime("%Y-%m-%d %H:00")
        b = buckets.setdefault(key, {"period": key, "energy_kwh": 0.0, "wasted_kwh": 0.0, "cost": 0.0,
                                     "simulation_kwh": 0.0, "emulator_kwh": 0.0, "hardware_kwh": 0.0})
        b["energy_kwh"] += rec.energy_kwh
        b["wasted_kwh"] += rec.wasted_kwh
        b["cost"] += rec.cost
        b[f"{rec.source}_kwh"] += rec.energy_kwh
    # Fill empty periods so charts show gaps honestly as zero-consumption-recorded periods.
    series = []
    cur = start_local
    end_local = now.astimezone(tz)
    step = timedelta(days=1) if group == "day" else timedelta(hours=1)
    while cur <= end_local:
        key = cur.strftime("%Y-%m-%d") if group == "day" else cur.strftime("%Y-%m-%d %H:00")
        b = buckets.get(key, {"period": key, "energy_kwh": 0.0, "wasted_kwh": 0.0, "cost": 0.0,
                              "simulation_kwh": 0.0, "emulator_kwh": 0.0, "hardware_kwh": 0.0})
        series.append({k: (round(v, 4) if isinstance(v, float) else v) for k, v in b.items()})
        cur = (cur + step).astimezone(tz)
    return {"group": group, "timezone": rs.timezone, "currency": rs.currency, "series": series}


def room_breakdown(ctx: AppContext, db: Session, *, hours: int) -> list[dict]:
    since = ctx.clock.now() - timedelta(hours=hours)
    rows = (db.query(EnergyRecord.room_id, func.sum(EnergyRecord.energy_kwh), func.sum(EnergyRecord.wasted_kwh),
                     func.sum(EnergyRecord.cost))
            .filter(EnergyRecord.period_start >= since).group_by(EnergyRecord.room_id).all())
    names = {r.id: r.name for r in db.query(Room).all()}
    return [{"room_id": rid, "room": names.get(rid, str(rid)), "energy_kwh": round(e or 0, 4),
             "wasted_kwh": round(w or 0, 4), "cost": round(c or 0, 2)} for rid, e, w, c in rows]


def live_power_series(ctx: AppContext, db: Session, *, minutes: int = 15, bucket_s: int = 15,
                      room_id: int | None = None) -> list[dict]:
    """Total power over time: average each appliance within a bucket, then sum across appliances."""
    now = ctx.clock.now()
    since = now - timedelta(minutes=minutes)
    q = db.query(TelemetryReading.ts, TelemetryReading.appliance_id, TelemetryReading.power_w,
                 TelemetryReading.source).filter(TelemetryReading.ts >= since)
    if room_id is not None:
        q = q.filter(TelemetryReading.room_id == room_id)
    acc: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    sources: dict[int, set] = defaultdict(set)
    for ts, aid, p, src in q.all():
        b = int(ts.timestamp()) // bucket_s * bucket_s
        acc[b][aid].append(p)
        sources[b].add(src)
    out = []
    for b in sorted(acc):
        total = sum(sum(v) / len(v) for v in acc[b].values())
        out.append({"ts": datetime.fromtimestamp(b, tz=now.tzinfo).isoformat(), "power_w": round(total, 1),
                    "sources": sorted(sources[b])})
    return out
