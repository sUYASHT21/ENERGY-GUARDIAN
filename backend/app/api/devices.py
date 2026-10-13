from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..context import AppContext, emit
from ..models import Device, Room
from ..schemas import DeviceCreate, DeviceCreated, DeviceOut, DeviceUpdate
from ..security import generate_device_key, hash_device_key, role_at_least
from ..services.analytics import device_health
from ..services.events import log_event
from .deps import CurrentUser, admin, get_ctx, get_db, operator, viewer

router = APIRouter(tags=["devices"])


def _device_or_404(db: Session, device_id: int) -> Device:
    d = db.get(Device, device_id)
    if d is None:
        raise HTTPException(404, "device not found")
    return d


def device_dict(d: Device, now) -> dict:
    return {**DeviceOut.model_validate(d).model_dump(mode="json"), "health": device_health(d, now),
            "appliance_count": len(d.appliances)}


@router.get("/devices")
def list_devices(_: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    now = ctx.clock.now()
    return [device_dict(d, now) for d in db.query(Device).order_by(Device.id).all()]


@router.get("/devices/{device_id}")
def get_device(device_id: int, _: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx),
               db: Session = Depends(get_db)):
    d = _device_or_404(db, device_id)
    return {**device_dict(d, ctx.clock.now()),
            "appliances": [{"id": a.id, "name": a.name, "relay_channel": a.relay_channel, "state": a.state}
                           for a in sorted(d.appliances, key=lambda a: a.relay_channel)]}


@router.post("/devices", response_model=DeviceCreated, status_code=201)
def create_device(body: DeviceCreate, user: CurrentUser = Depends(admin), ctx: AppContext = Depends(get_ctx),
                  db: Session = Depends(get_db)):
    """Register a controller. The API key is returned **once**; only its hash is stored."""
    if body.kind == "simulated" and not ctx.settings.simulation_enabled:
        raise HTTPException(422, "simulation is disabled")
    if db.query(Device).filter(Device.uid == body.uid).first():
        raise HTTPException(409, "a device with this uid already exists")
    if body.room_id is not None and db.get(Room, body.room_id) is None:
        raise HTTPException(422, "room not found")
    key = generate_device_key()
    d = Device(uid=body.uid, name=body.name, kind=body.kind, room_id=body.room_id,
               has_occupancy_sensor=body.has_occupancy_sensor, api_key_hash=hash_device_key(key))
    db.add(d)
    db.flush()
    log_event(db, "config", f"Device '{d.name}' ({d.kind}) registered", now=ctx.clock.now(), actor=user.username,
              device_id=d.id, room_id=d.room_id)
    return DeviceCreated(device=DeviceOut.model_validate(d), api_key=key)


@router.patch("/devices/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, body: DeviceUpdate, user: CurrentUser = Depends(operator),
                  ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    d = _device_or_404(db, device_id)
    changes = body.model_dump(exclude_unset=True)
    if "control_validated" in changes:
        # Marking a controller as safe to switch real loads is an admin-only decision.
        if not role_at_least(user.role, "admin"):
            raise HTTPException(403, "only admins can change control validation")
    if "room_id" in changes and changes["room_id"] is not None and db.get(Room, changes["room_id"]) is None:
        raise HTTPException(422, "room not found")
    for k, v in changes.items():
        setattr(d, k, v)
    log_event(db, "config", f"Device '{d.name}' updated: {sorted(changes)}", now=ctx.clock.now(),
              actor=user.username, device_id=d.id, details=changes,
              level="warning" if changes.get("control_validated") else "info")
    emit(db, "device", {"id": d.id})
    return d


@router.post("/devices/{device_id}/rotate-key", response_model=DeviceCreated)
def rotate_key(device_id: int, user: CurrentUser = Depends(admin), ctx: AppContext = Depends(get_ctx),
               db: Session = Depends(get_db)):
    d = _device_or_404(db, device_id)
    key = generate_device_key()
    d.api_key_hash = hash_device_key(key)
    log_event(db, "config", f"API key rotated for device '{d.name}'", now=ctx.clock.now(), actor=user.username,
              device_id=d.id)
    return DeviceCreated(device=DeviceOut.model_validate(d), api_key=key)


@router.delete("/devices/{device_id}", status_code=204)
def delete_device(device_id: int, user: CurrentUser = Depends(admin), ctx: AppContext = Depends(get_ctx),
                  db: Session = Depends(get_db)):
    d = _device_or_404(db, device_id)
    log_event(db, "config", f"Device '{d.name}' deleted", now=ctx.clock.now(), actor=user.username, device_id=d.id)
    db.delete(d)
