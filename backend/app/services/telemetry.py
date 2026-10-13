"""Telemetry ingestion pipeline (shared by HTTP devices and the in-process simulator)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from ..adapters.telemetry_parsers import TelemetryPayload
from ..context import AppContext, emit
from ..ml.features import ReadingContext
from ..models import Appliance, Device, EnergyRecord, OccupancyReading, Room, TelemetryReading
from . import alerts
from .commands import close_savings
from .energy import BUCKET_MINUTES, Tariff, interval_energy_kwh, split_by_bucket
from .events import log_event
from .settings_service import RuntimeSettings, load_settings

log = logging.getLogger(__name__)

MAX_CLOCK_SKEW_S = 300
NORMAL_READINGS_TO_CLEAR_ANOMALY = 5


@dataclass
class IngestResult:
    accepted: int = 0
    skipped: int = 0
    unknown_channels: list[int] = field(default_factory=list)
    used_server_time: bool = False
    anomalies: list[int] = field(default_factory=list)


def _effective_ts(now: datetime, ts: datetime | None) -> tuple[datetime, bool]:
    if ts is None:
        return now, True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    if abs((ts - now).total_seconds()) > MAX_CLOCK_SKEW_S:
        return now, True  # device clock not trustworthy (e.g. no NTP) -> server receive time
    return ts, False


def add_energy(db: Session, *, appliance: Appliance, t0: datetime, t1: datetime, kwh: float, wasted: bool,
               source: str, tariff: Tariff) -> None:
    """Distribute an interval's energy over 15-minute buckets (split at bucket boundaries)."""
    for bucket, frac in split_by_bucket(t0, t1):
        part = kwh * frac
        rec = (db.query(EnergyRecord)
               .filter(EnergyRecord.appliance_id == appliance.id, EnergyRecord.period_start == bucket,
                       EnergyRecord.source == source).one_or_none())
        if rec is None:
            rec = EnergyRecord(appliance_id=appliance.id, room_id=appliance.room_id, period_start=bucket,
                               energy_kwh=0.0, wasted_kwh=0.0, cost=0.0, source=source)
            db.add(rec)
        rec.energy_kwh += part
        rec.cost += tariff.cost(part, bucket + timedelta(minutes=BUCKET_MINUTES / 2))
        if wasted:
            rec.wasted_kwh += part


def _update_device_health(ctx: AppContext, db: Session, device: Device, payload: TelemetryPayload,
                          now: datetime, client_ip: str | None) -> None:
    was = device.connection_status
    device.last_seen_at = now
    device.connection_status = "online"
    if payload.health:
        h = payload.health
        device.firmware_version = h.firmware or device.firmware_version
        device.rssi_dbm = h.rssi_dbm if h.rssi_dbm is not None else device.rssi_dbm
        device.uptime_s = h.uptime_s if h.uptime_s is not None else device.uptime_s
        device.free_heap = h.free_heap if h.free_heap is not None else device.free_heap
        device.ip_address = h.ip or client_ip or device.ip_address
    elif client_ip:
        device.ip_address = client_ip
    if was != "online":
        log_event(db, "device", f"Device '{device.name}' is online" + (" again" if was == "offline" else ""),
                  now=now, device_id=device.id, room_id=device.room_id)
        alerts.resolve_alerts(db, f"device_offline:{device.id}", now=now, note="device reconnected")
        emit(db, "device", {"id": device.id, "connection_status": "online"})


def _process_reading(ctx: AppContext, db: Session, rs: RuntimeSettings, tariff: Tariff, device: Device,
                     appliance: Appliance, room: Room, r, ts: datetime, result: IngestResult) -> dict | None:
    if appliance.last_reading_at and ts <= appliance.last_reading_at:
        result.skipped += 1  # duplicate / out-of-order reading
        return None
    source = device.source
    prev_ts, prev_p = appliance.last_reading_at, appliance.last_power_w
    delta_kwh = 0.0
    prev_fresh = prev_ts is not None and prev_p is not None and \
        (ts - prev_ts).total_seconds() <= ctx.settings.max_integration_gap_seconds
    if prev_fresh:
        delta_kwh = interval_energy_kwh(prev_p, r.power_w, (ts - prev_ts).total_seconds())
        wasted = (room.occupancy_state == "vacant" and not appliance.essential
                  and max(prev_p, r.power_w) > appliance.standby_threshold_w)
        add_energy(db, appliance=appliance, t0=prev_ts, t1=ts, kwh=delta_kwh, wasted=wasted, source=source,
                   tariff=tariff)

    pred = ctx.anomaly.predict(ReadingContext(
        power_w=r.power_w, rated_power_w=appliance.rated_power_w, standby_threshold_w=appliance.standby_threshold_w,
        voltage_v=r.voltage_v, current_a=r.current_a, relay_on=r.relay_on,
        prev_power_w=prev_p if prev_fresh else None))

    db.add(TelemetryReading(appliance_id=appliance.id, device_id=device.id, room_id=appliance.room_id, ts=ts,
                            received_at=ctx.clock.now(), power_w=r.power_w, voltage_v=r.voltage_v,
                            current_a=r.current_a, relay_on=r.relay_on, source=source, energy_delta_kwh=delta_kwh,
                            anomaly_score=pred.score, is_anomaly=pred.is_anomaly, anomaly_method=pred.method))

    appliance.last_power_w = r.power_w
    appliance.last_voltage_v = r.voltage_v
    appliance.last_current_a = r.current_a
    appliance.last_reading_at = ts
    appliance.last_source = source
    appliance.last_anomaly_score = pred.score
    if r.relay_on is not None:
        appliance.state = "on" if r.relay_on else "off"
    else:
        appliance.state = "on" if r.power_w > appliance.standby_threshold_w else "off"
    if r.power_w > appliance.standby_threshold_w:
        close_savings(db, now=ts, reason="switched_on", appliance_id=appliance.id)

    # Anomaly persistence (hysteresis): streak > 0 counts anomalous readings, < 0 normal ones.
    key = f"anomaly:{appliance.id}"
    if pred.is_anomaly:
        appliance.anomaly_streak = max(appliance.anomaly_streak, 0) + 1
        result.anomalies.append(appliance.id)
        if appliance.anomaly_streak >= rs.anomaly_persistence:
            alerts.raise_alert(
                db, now=ts, alert_type="anomaly", dedupe_key=key, severity="warning",
                title=f"Abnormal consumption: {appliance.name} ({room.name})",
                message="; ".join(pred.reasons) or "unusual electrical behaviour",
                room_id=room.id, appliance_id=appliance.id, device_id=device.id, source=source,
                details={"score": pred.score, "method": pred.method, "power_w": r.power_w,
                         "voltage_v": r.voltage_v, "current_a": r.current_a, "model_version": ctx.anomaly.version,
                         "reasons": pred.reasons},
                recommendation="Inspect the appliance. Anomalies are advisory and never trigger automatic shutdown.")
    else:
        appliance.anomaly_streak = min(appliance.anomaly_streak, 0) - 1
        if appliance.anomaly_streak <= -NORMAL_READINGS_TO_CLEAR_ANOMALY:
            alerts.resolve_alerts(db, key, now=ts, note="readings back to normal")
    result.accepted += 1
    return {"appliance_id": appliance.id, "power_w": round(r.power_w, 2), "state": appliance.state,
            "anomaly": pred.is_anomaly, "score": pred.score}


def update_occupancy(ctx: AppContext, db: Session, device: Device, room: Room, occ, ts: datetime) -> None:
    now = ts
    db.add(OccupancyReading(room_id=room.id, device_id=device.id, ts=ts, occupied=occ.occupied,
                            people_count=occ.people_count, sensor_ok=occ.sensor_ok, source=device.source))
    prev = room.occupancy_state
    sensor_key = f"sensor_failure:{room.id}"
    if not occ.sensor_ok or occ.occupied is None:
        new = "unknown"
        if device.sensor_status != "fault":
            device.sensor_status = "fault"
            device.error_count += 1
        alerts.raise_alert(
            db, now=now, alert_type="sensor_failure", dedupe_key=sensor_key, severity="critical",
            title=f"Occupancy sensor failure in {room.name}",
            message="Occupancy cannot be determined. Automatic shutdown is disabled for this room until the "
                    "sensor recovers.", room_id=room.id, device_id=device.id, source=device.source,
            recommendation="Check the PIR/occupancy sensor wiring and power.")
    else:
        new = "occupied" if occ.occupied else "vacant"
        if device.sensor_status != "ok":
            device.sensor_status = "ok"
            alerts.resolve_alerts(db, sensor_key, now=now, note="sensor readings valid again")
    room.occupancy_updated_at = ts
    room.people_count = occ.people_count
    room.occupancy_source = device.source
    if new != prev:
        room.occupancy_state = new
        room.vacant_since = ts if new == "vacant" else None
        log_event(db, "occupancy", f"{room.name}: {prev} → {new}", now=now, room_id=room.id, device_id=device.id)
        emit(db, "room", {"id": room.id, "occupancy_state": new})
    if new == "occupied":
        close_savings(db, now=ts, reason="room_reoccupied", room_id=room.id)


def ingest(ctx: AppContext, db: Session, device: Device, payload: TelemetryPayload,
           client_ip: str | None = None) -> IngestResult:
    now = ctx.clock.now()
    ts, used_server_time = _effective_ts(now, payload.ts)
    result = IngestResult(used_server_time=used_server_time)
    rs = load_settings(db)
    tariff = rs.tariff()
    _update_device_health(ctx, db, device, payload, now, client_ip)

    room = db.get(Room, device.room_id) if device.room_id else None
    by_channel = {a.relay_channel: a for a in device.appliances}
    emitted = []
    for r in payload.readings:
        appliance = by_channel.get(r.channel)
        if appliance is None:
            result.unknown_channels.append(r.channel)
            continue
        a_room = room if room is not None and room.id == appliance.room_id else db.get(Room, appliance.room_id)
        out = _process_reading(ctx, db, rs, tariff, device, appliance, a_room, r, ts, result)
        if out:
            emitted.append(out)
    # Occupancy after readings: the readings' interval belongs to the previous occupancy state.
    if payload.occupancy is not None and room is not None and device.has_occupancy_sensor:
        update_occupancy(ctx, db, device, room, payload.occupancy, ts)
    if result.unknown_channels:
        log_event(db, "telemetry", f"Device '{device.name}' sent readings for unmapped channels "
                                   f"{sorted(set(result.unknown_channels))}", now=now, level="warning",
                  device_id=device.id)
    db.flush()
    emit(db, "telemetry", {"device_id": device.id, "room_id": device.room_id, "ts": ts.isoformat(),
                           "source": device.source, "readings": emitted})
    return result
