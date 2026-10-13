"""Appliance commands: safety gate, queueing, delivery, acknowledgement and timeouts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..adapters.base import transport_for
from ..context import AppContext, emit
from ..models import Appliance, Command, Device, Room, SavingsRecord
from . import alerts
from .events import log_event

OPEN_STATUSES = ("pending", "sent")


class CommandRejected(Exception):
    pass


def command_to_dict(c: Command) -> dict:
    return {
        "id": c.id, "appliance_id": c.appliance_id, "device_id": c.device_id, "action": c.action,
        "mode": c.mode, "status": c.status, "origin": c.origin, "requested_by": c.requested_by,
        "reason": c.reason, "decision": c.decision,
        "created_at": c.created_at.isoformat(), "sent_at": c.sent_at.isoformat() if c.sent_at else None,
        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        "result_relay_on": c.result_relay_on, "error": c.error,
    }


@dataclass
class GateResult:
    mode: str | None  # dry_run | simulated | emulator | hardware ; None if blocked
    blocked_reason: str | None


def pending_command(db: Session, appliance_id: int) -> Command | None:
    return (db.query(Command)
            .filter(Command.appliance_id == appliance_id, Command.status.in_(OPEN_STATUSES))
            .order_by(Command.id.desc()).first())


def gate(ctx: AppContext, db: Session, appliance: Appliance, action: str, *, dry_run: bool,
         confirm_essential: bool = False, actor_role: str = "operator") -> GateResult:
    """Safety gate applied to *every* command (manual or automatic)."""
    device = appliance.device
    if action == "off" and appliance.essential and not (confirm_essential and actor_role == "admin"):
        return GateResult(None, "essential load: switching off requires an admin with explicit confirmation")
    if dry_run:
        return GateResult("dry_run", None)
    if device is None:
        return GateResult(None, "appliance has no controller assigned")
    if device.connection_status != "online":
        return GateResult(None, f"controller is {device.connection_status}; device status unavailable")
    if pending_command(db, appliance.id):
        return GateResult(None, "another command for this appliance is still pending")
    if device.kind == "esp32":
        if not ctx.settings.real_switching_enabled:
            return GateResult(None, "real switching disabled (REAL_SWITCHING_ENABLED=false)")
        if not device.control_validated:
            return GateResult(None, "device control has not been validated by an administrator")
        return GateResult("hardware", None)
    return GateResult("emulator" if device.kind == "emulator" else "simulated", None)


def create_command(
    ctx: AppContext, db: Session, appliance: Appliance, action: str, *, origin: str, actor: str,
    reason: str = "", decision: dict | None = None, dry_run: bool = False, confirm_essential: bool = False,
    actor_role: str = "operator",
) -> Command:
    if action not in ("on", "off"):
        raise CommandRejected("action must be 'on' or 'off'")
    now = ctx.clock.now()
    g = gate(ctx, db, appliance, action, dry_run=dry_run, confirm_essential=confirm_essential,
             actor_role=actor_role)
    cmd = Command(appliance_id=appliance.id, device_id=appliance.device_id, action=action,
                  mode=g.mode or "blocked", origin=origin, requested_by=actor, reason=reason[:300],
                  decision=decision or {}, created_at=now)
    if g.blocked_reason:
        cmd.status, cmd.error, cmd.mode, cmd.completed_at = "blocked", g.blocked_reason[:300], "dry_run", now
    elif g.mode == "dry_run":
        cmd.status, cmd.completed_at = "dry_run", now
    else:
        cmd.status = "pending"
        cmd.expires_at = now + timedelta(seconds=ctx.settings.command_timeout_seconds)
    db.add(cmd)
    if action == "on" and origin == "manual" and cmd.status == "pending":
        appliance.last_manual_on_at = now
    db.flush()
    verb = {"blocked": "BLOCKED", "dry_run": "DRY-RUN", "pending": "queued"}[cmd.status]
    log_event(db, "command", f"{verb} {action.upper()} for '{appliance.name}' ({origin}, {cmd.mode})"
              + (f": {cmd.error}" if cmd.error else ""), now=now, actor=actor,
              level="warning" if cmd.status == "blocked" else "info", room_id=appliance.room_id,
              appliance_id=appliance.id, device_id=appliance.device_id,
              details={"command_id": cmd.id, "reason": reason})
    if cmd.status == "pending" and appliance.device is not None:
        transport_for(appliance.device).dispatch(cmd, appliance.device)
    emit(db, "command", command_to_dict(cmd))
    return cmd


def fetch_pending(ctx: AppContext, db: Session, device: Device) -> list[dict]:
    """Return undelivered/unacknowledged commands for a device and mark them as sent."""
    now = ctx.clock.now()
    cmds = (db.query(Command)
            .filter(Command.device_id == device.id, Command.status.in_(OPEN_STATUSES))
            .order_by(Command.id).all())
    out = []
    for c in cmds:
        if c.expires_at and c.expires_at <= now:
            continue  # will be expired by the monitor
        if c.status == "pending":
            c.status, c.sent_at = "sent", now
            emit(db, "command", command_to_dict(c))
        appliance = db.get(Appliance, c.appliance_id)
        out.append({"command_id": c.id, "channel": appliance.relay_channel if appliance else None,
                    "appliance_id": c.appliance_id, "action": c.action,
                    "expires_at": c.expires_at.isoformat() if c.expires_at else None})
    return out


def acknowledge(
    ctx: AppContext, db: Session, device: Device, command_id: int, *, success: bool,
    relay_on: bool | None = None, error: str | None = None,
) -> Command:
    now = ctx.clock.now()
    cmd = db.get(Command, command_id)
    if cmd is None or cmd.device_id != device.id:
        raise CommandRejected("unknown command for this device")
    if cmd.status not in OPEN_STATUSES:
        # Late or duplicate acknowledgement: keep the original outcome (idempotent).
        log_event(db, "command", f"Ignored late/duplicate ack for command #{cmd.id} (status {cmd.status})",
                  now=now, level="warning", device_id=device.id, appliance_id=cmd.appliance_id)
        return cmd
    appliance = db.get(Appliance, cmd.appliance_id)
    cmd.completed_at = now
    cmd.result_relay_on = relay_on
    if success:
        cmd.status = "acknowledged"
        if relay_on is not None and appliance is not None:
            appliance.state = "on" if relay_on else "off"
        if appliance is not None and cmd.action == "off":
            _maybe_open_savings(db, appliance, cmd, now, device.source)
        if appliance is not None and cmd.action == "on":
            close_savings(db, now=now, reason="switched_on", appliance_id=appliance.id)
        log_event(db, "command", f"ACK {cmd.action.upper()} for '{appliance.name if appliance else cmd.appliance_id}'",
                  now=now, device_id=device.id, appliance_id=cmd.appliance_id,
                  room_id=appliance.room_id if appliance else None, details={"command_id": cmd.id})
        alerts.resolve_alerts(db, f"command_failed:{cmd.appliance_id}", now=now, note="later command succeeded")
    else:
        cmd.status = "failed"
        cmd.error = (error or "device reported failure")[:300]
        device.error_count += 1
        name = appliance.name if appliance else f"appliance {cmd.appliance_id}"
        alerts.raise_alert(db, now=now, alert_type="command_failed", dedupe_key=f"command_failed:{cmd.appliance_id}",
                           title=f"Command {cmd.action.upper()} failed for {name}", message=cmd.error,
                           severity="warning", room_id=appliance.room_id if appliance else None,
                           appliance_id=cmd.appliance_id, device_id=device.id, source=device.source,
                           details={"command_id": cmd.id},
                           recommendation="Inspect the relay/appliance; switch manually if needed.")
    emit(db, "command", command_to_dict(cmd))
    return cmd


def expire_commands(ctx: AppContext, db: Session) -> int:
    now = ctx.clock.now()
    n = 0
    for cmd in (db.query(Command).filter(Command.status.in_(OPEN_STATUSES), Command.expires_at <= now).all()):
        cmd.status, cmd.completed_at = "timeout", now
        cmd.error = "no acknowledgement before timeout"
        appliance = db.get(Appliance, cmd.appliance_id)
        device = db.get(Device, cmd.device_id) if cmd.device_id else None
        if device:
            device.error_count += 1
        name = appliance.name if appliance else f"appliance {cmd.appliance_id}"
        alerts.raise_alert(db, now=now, alert_type="command_timeout", dedupe_key=f"command_timeout:{cmd.appliance_id}",
                           title=f"Command {cmd.action.upper()} timed out for {name}",
                           message=f"No acknowledgement within {ctx.settings.command_timeout_seconds}s; "
                                   "appliance state is uncertain.",
                           severity="warning", room_id=appliance.room_id if appliance else None,
                           appliance_id=cmd.appliance_id, device_id=cmd.device_id,
                           source=device.source if device else None, details={"command_id": cmd.id},
                           recommendation="Check controller connectivity; verify the appliance state on site.")
        log_event(db, "command", f"TIMEOUT {cmd.action.upper()} for '{name}'", now=now, level="warning",
                  appliance_id=cmd.appliance_id, device_id=cmd.device_id, details={"command_id": cmd.id})
        emit(db, "command", command_to_dict(cmd))
        n += 1
    return n


# ---------------------------------------------------------------------------
# Savings episodes
# ---------------------------------------------------------------------------
def _maybe_open_savings(db: Session, appliance: Appliance, cmd: Command, now: datetime, source: str) -> None:
    """Start an estimated-savings episode when a load in a vacant room is confirmed off."""
    room = db.get(Room, appliance.room_id)
    baseline = appliance.last_power_w or 0.0
    if room is None or room.occupancy_state != "vacant" or baseline <= appliance.standby_threshold_w:
        return
    if db.query(SavingsRecord).filter(SavingsRecord.appliance_id == appliance.id,
                                      SavingsRecord.ended_at.is_(None)).first():
        return
    db.add(SavingsRecord(appliance_id=appliance.id, room_id=appliance.room_id, command_id=cmd.id,
                         baseline_power_w=baseline, started_at=now, source=source))
    log_event(db, "savings", f"Estimated-savings episode started for '{appliance.name}' "
                             f"(baseline {baseline:.0f} W)", now=now, appliance_id=appliance.id,
              room_id=appliance.room_id)


def close_savings(db: Session, *, now: datetime, reason: str, appliance_id: int | None = None,
                  room_id: int | None = None) -> int:
    q = db.query(SavingsRecord).filter(SavingsRecord.ended_at.is_(None))
    if appliance_id is not None:
        q = q.filter(SavingsRecord.appliance_id == appliance_id)
    if room_id is not None:
        q = q.filter(SavingsRecord.room_id == room_id)
    n = 0
    for rec in q.all():
        rec.ended_at, rec.end_reason = now, reason
        n += 1
    return n
