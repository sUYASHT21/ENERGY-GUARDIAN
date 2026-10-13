"""Device-facing HTTP API used by ESP32 controllers (and the ESP32 emulator).

Authentication: headers ``X-Device-Id`` (device uid) and ``X-Device-Key`` (secret issued at
registration). See docs/HARDWARE.md for the full protocol.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..adapters.telemetry_parsers import HealthIn, PayloadError, TelemetryPayload, parse_payload
from ..context import AppContext
from ..models import Device
from ..schemas import CommandAck
from ..services import commands as command_service
from ..services import telemetry as telemetry_service
from .deps import current_device, get_ctx, get_db

router = APIRouter(prefix="/esp32", tags=["esp32 device API"])


@router.post("/telemetry")
def post_telemetry(request: Request, raw: dict = Body(...), device: Device = Depends(current_device),
                   ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    """Ingest a telemetry payload. The response carries any pending commands so a device
    can work with a single request per cycle."""
    try:
        payload = parse_payload(raw)
    except PayloadError as exc:
        raise HTTPException(422, f"invalid telemetry payload: {exc}") from exc
    result = telemetry_service.ingest(ctx, db, device, payload, request.client.host if request.client else None)
    return {
        "accepted": result.accepted,
        "skipped": result.skipped,
        "unknown_channels": sorted(set(result.unknown_channels)),
        "used_server_time": result.used_server_time,
        "server_time": ctx.clock.now().isoformat(),
        "commands": command_service.fetch_pending(ctx, db, device),
        "poll_interval_s": 5,
    }


@router.post("/heartbeat")
def heartbeat(request: Request, health: HealthIn | None = Body(default=None), device: Device = Depends(current_device),
              ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    telemetry_service.ingest(ctx, db, device, TelemetryPayload(health=health),
                             request.client.host if request.client else None)
    return {"server_time": ctx.clock.now().isoformat(), "connection_status": device.connection_status}


@router.get("/commands")
def get_commands(device: Device = Depends(current_device), ctx: AppContext = Depends(get_ctx),
                 db: Session = Depends(get_db)):
    """Pending commands for this device. Commands are idempotent (absolute on/off), so a device
    may safely re-execute a command it receives twice."""
    return {"commands": command_service.fetch_pending(ctx, db, device), "server_time": ctx.clock.now().isoformat()}


@router.post("/commands/{command_id}/ack")
def ack_command(command_id: int, body: CommandAck, device: Device = Depends(current_device),
                ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    try:
        cmd = command_service.acknowledge(ctx, db, device, command_id, success=body.success,
                                          relay_on=body.relay_on, error=body.error)
    except command_service.CommandRejected as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"command_id": cmd.id, "status": cmd.status}


@router.get("/config")
def device_config(device: Device = Depends(current_device), ctx: AppContext = Depends(get_ctx)):
    """Channel map so firmware can label relays; no secrets are returned."""
    return {
        "uid": device.uid, "name": device.name, "room_id": device.room_id,
        "has_occupancy_sensor": device.has_occupancy_sensor,
        "channels": [{"channel": a.relay_channel, "appliance_id": a.id, "name": a.name,
                      "rated_power_w": a.rated_power_w} for a in sorted(device.appliances, key=lambda a: a.relay_channel)],
        "telemetry_interval_s": 5,
        "command_timeout_s": ctx.settings.command_timeout_seconds,
    }
