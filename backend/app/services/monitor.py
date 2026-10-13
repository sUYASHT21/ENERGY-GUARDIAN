"""Periodic supervision: connectivity, data freshness, timeouts, overrides, automation."""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from ..context import AppContext, emit
from ..models import Appliance, Device, OccupancyReading, Room, SavingsRecord, TelemetryReading
from . import alerts
from .automation import run_automation
from .commands import expire_commands
from .events import log_event
from .settings_service import load_settings

log = logging.getLogger(__name__)
RETENTION_DAYS = 30


def update_device_status(ctx: AppContext, db: Session) -> None:
    now = ctx.clock.now()
    limit = now - timedelta(seconds=ctx.settings.device_offline_seconds)
    for dev in db.query(Device).filter(Device.connection_status == "online").all():
        if dev.last_seen_at is None or dev.last_seen_at < limit:
            dev.connection_status = "offline"
            for a in dev.appliances:
                a.state = "unknown"  # relay state can no longer be confirmed
            alerts.raise_alert(
                db, now=now, alert_type="device_offline", dedupe_key=f"device_offline:{dev.id}", severity="critical",
                title=f"Controller offline: {dev.name}",
                message=f"No data for more than {ctx.settings.device_offline_seconds}s. Appliance states are unknown; "
                        "automatic control is suspended for its appliances.",
                room_id=dev.room_id, device_id=dev.id, source=dev.source,
                recommendation="Check power and Wi-Fi of the controller.")
            log_event(db, "device", f"Device '{dev.name}' went offline", now=now, level="warning",
                      device_id=dev.id, room_id=dev.room_id)
            emit(db, "device", {"id": dev.id, "connection_status": "offline"})


def check_freshness(ctx: AppContext, db: Session) -> None:
    now = ctx.clock.now()
    limit = now - timedelta(seconds=ctx.settings.telemetry_stale_seconds)
    for room in db.query(Room).filter(Room.occupancy_state != "unknown").all():
        if room.occupancy_updated_at is None or room.occupancy_updated_at < limit:
            log_event(db, "occupancy", f"{room.name}: occupancy data stale → unknown", now=now, level="warning",
                      room_id=room.id)
            room.occupancy_state, room.vacant_since = "unknown", None
            emit(db, "room", {"id": room.id, "occupancy_state": "unknown"})
    for a in db.query(Appliance).all():
        key = f"stale_data:{a.id}"
        dev = a.device
        stale = a.last_reading_at is None or a.last_reading_at < limit
        if stale and dev is not None and dev.connection_status == "online":
            alerts.raise_alert(db, now=now, alert_type="stale_data", dedupe_key=key, severity="warning",
                               title=f"No recent readings for {a.name}",
                               message="Controller is online but this channel is not reporting. Automatic "
                                       "control is suspended for this appliance.",
                               room_id=a.room_id, appliance_id=a.id, device_id=dev.id, source=dev.source,
                               recommendation="Check the power-measurement sensor for this channel.")
        elif not stale:
            alerts.resolve_alerts(db, key, now=now, note="readings resumed")


def expire_overrides(ctx: AppContext, db: Session) -> None:
    now = ctx.clock.now()
    for room in db.query(Room).filter(Room.manual_override.is_(True), Room.override_until.is_not(None)).all():
        if room.override_until <= now:
            room.manual_override, room.override_until, room.override_reason = False, None, ""
            log_event(db, "override", f"Manual override expired for {room.name}", now=now, room_id=room.id)


def cap_savings(ctx: AppContext, db: Session) -> None:
    now = ctx.clock.now()
    cap = timedelta(hours=load_settings(db).savings_cap_hours)
    for rec in db.query(SavingsRecord).filter(SavingsRecord.ended_at.is_(None)).all():
        if now - rec.started_at >= cap:
            rec.ended_at, rec.end_reason = rec.started_at + cap, "cap_reached"


def prune(ctx: AppContext, db: Session) -> int:
    cutoff = ctx.clock.now() - timedelta(days=RETENTION_DAYS)
    n = db.query(TelemetryReading).filter(TelemetryReading.ts < cutoff).delete()
    n += db.query(OccupancyReading).filter(OccupancyReading.ts < cutoff).delete()
    return n


def run_once(ctx: AppContext) -> None:
    """One supervision cycle. Each step commits separately so one failure cannot block the rest."""
    steps = (expire_commands, update_device_status, check_freshness, expire_overrides, cap_savings, run_automation)
    for step in steps:
        try:
            with ctx.db.session() as db:
                step(ctx, db)
        except Exception:  # pragma: no cover - logged, loop continues
            log.exception("monitor step %s failed", step.__name__)
