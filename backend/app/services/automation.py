"""Glue between the database and the pure decision engine; executes decisions safely."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from ..context import AppContext
from ..models import Appliance, Command, Device, Room
from . import alerts
from .commands import create_command, pending_command
from .decision_engine import Decision, DecisionInput, evaluate
from .schedules import ScheduleWindow, active_windows, window_starting_within
from .settings_service import RuntimeSettings, load_settings


def room_override_active(room: Room, now) -> bool:
    return room.manual_override and (room.override_until is None or room.override_until > now)


def occupancy_sensor_status(room: Room) -> str:
    sensors = [d for d in room.devices if d.has_occupancy_sensor]
    if not sensors:
        return "unknown"
    return "fault" if any(d.sensor_status == "fault" for d in sensors) else sensors[0].sensor_status


def build_input(ctx: AppContext, db: Session, appliance: Appliance, rs: RuntimeSettings) -> DecisionInput:
    now = ctx.clock.now()
    room = appliance.room
    device: Device | None = appliance.device
    windows = [ScheduleWindow(s.day_of_week, s.start_time, s.end_time, s.label, s.enabled) for s in room.schedules]
    active = active_windows(windows, now, rs.timezone)
    soon = window_starting_within(windows, now, rs.timezone, rs.schedule_grace_minutes)
    cooldown_start = now - timedelta(minutes=rs.auto_command_cooldown_minutes)
    recent_auto = db.query(Command).filter(
        Command.appliance_id == appliance.id, Command.origin == "automation",
        Command.status.in_(("pending", "sent", "acknowledged", "failed", "timeout")),
        Command.created_at >= cooldown_start).first() is not None
    return DecisionInput(
        now=now, automation_mode=rs.automation_mode, real_switching_enabled=ctx.settings.real_switching_enabled,
        telemetry_stale_seconds=ctx.settings.telemetry_stale_seconds,
        manual_on_cooldown_minutes=rs.manual_on_cooldown_minutes,
        appliance_id=appliance.id, appliance_name=appliance.name, essential=appliance.essential,
        auto_off_allowed=appliance.auto_off_allowed, appliance_override=appliance.manual_override,
        appliance_state=appliance.state, power_w=appliance.last_power_w,
        standby_threshold_w=appliance.standby_threshold_w, last_reading_at=appliance.last_reading_at,
        last_manual_on_at=appliance.last_manual_on_at,
        room_auto_enabled=room.auto_control_enabled, room_override_active=room_override_active(room, now),
        occupancy_state=room.occupancy_state, occupancy_updated_at=room.occupancy_updated_at,
        vacant_since=room.vacant_since, min_vacancy_minutes=room.min_vacancy_minutes,
        device_kind=device.kind if device else None,
        device_connection=device.connection_status if device else None,
        device_control_validated=bool(device and device.control_validated),
        occupancy_sensor_status=occupancy_sensor_status(room),
        schedule_active=bool(active), schedule_label=active[0].label if active else None,
        schedule_starting_soon=soon is not None,
        anomaly_flag=appliance.anomaly_streak >= rs.anomaly_persistence,
        anomaly_score=appliance.last_anomaly_score,
        pending_command=pending_command(db, appliance.id) is not None,
        recent_auto_command=recent_auto,
    )


def evaluate_appliance(ctx: AppContext, db: Session, appliance: Appliance,
                       rs: RuntimeSettings | None = None) -> Decision:
    rs = rs or load_settings(db)
    decision = evaluate(build_input(ctx, db, appliance, rs))
    ctx.decisions[appliance.id] = decision.to_dict()
    return decision


def _act(ctx: AppContext, db: Session, appliance: Appliance, decision: Decision) -> None:
    now = ctx.clock.now()
    key = f"waste:{appliance.id}"
    room = appliance.room
    if decision.action in ("recommend_shutdown", "auto_shutdown"):
        watts = appliance.last_power_w or 0
        vac_min = (now - room.vacant_since).total_seconds() / 60 if room.vacant_since else 0
        alert, _ = alerts.raise_alert(
            db, now=now, alert_type="vacant_room_waste", dedupe_key=key, severity="warning",
            title=f"{appliance.name} running in vacant {room.name}",
            message=f"{watts:.0f} W drawn while the room has been vacant for {vac_min:.0f} min. {decision.summary}.",
            room_id=room.id, appliance_id=appliance.id, device_id=appliance.device_id,
            source=appliance.last_source, details={"decision": decision.to_dict()},
            recommendation=f"Switch off {appliance.name} ({watts:.0f} W)")
        if decision.action == "auto_shutdown":
            if decision.execution_mode == "dry_run":
                already = db.query(Command).filter(
                    Command.appliance_id == appliance.id, Command.origin == "automation",
                    Command.status == "dry_run", Command.created_at >= alert.created_at).first()
                if already:
                    return
            create_command(ctx, db, appliance, "off", origin="automation", actor="automation",
                           reason=decision.summary, decision=decision.to_dict(),
                           dry_run=decision.execution_mode == "dry_run")
    elif decision.data_ok and not decision.waste_detected:
        alerts.resolve_alerts(db, key, now=now, note="wastage condition cleared")


def run_automation(ctx: AppContext, db: Session) -> list[Decision]:
    rs = load_settings(db)
    out = []
    for appliance in db.query(Appliance).all():
        d = evaluate_appliance(ctx, db, appliance, rs)
        _act(ctx, db, appliance, d)
        out.append(d)
    return out
