"""Rooms, appliances and schedules."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..context import AppContext, emit
from ..models import Appliance, Device, Room, Schedule
from ..schemas import (
    ApplianceCreate,
    ApplianceOut,
    ApplianceUpdate,
    OverrideRequest,
    RoomCreate,
    RoomOut,
    RoomUpdate,
    ScheduleCreate,
    ScheduleOut,
    ScheduleUpdate,
)
from ..services.automation import evaluate_appliance
from ..services.events import log_event
from .deps import CurrentUser, get_ctx, get_db, operator, viewer

router = APIRouter()


def _room_or_404(db: Session, room_id: int) -> Room:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(404, "room not found")
    return room


def _appliance_or_404(db: Session, appliance_id: int) -> Appliance:
    a = db.get(Appliance, appliance_id)
    if a is None:
        raise HTTPException(404, "appliance not found")
    return a


# ---------------------------------------------------------------- rooms
@router.get("/rooms", response_model=list[RoomOut], tags=["rooms"])
def list_rooms(_: CurrentUser = Depends(viewer), db: Session = Depends(get_db)):
    return db.query(Room).order_by(Room.name).all()


@router.post("/rooms", response_model=RoomOut, status_code=201, tags=["rooms"])
def create_room(body: RoomCreate, user: CurrentUser = Depends(operator), ctx: AppContext = Depends(get_ctx),
                db: Session = Depends(get_db)):
    if db.query(Room).filter(Room.name == body.name).first():
        raise HTTPException(409, "a room with this name already exists")
    room = Room(**body.model_dump())
    db.add(room)
    db.flush()
    log_event(db, "config", f"Room '{room.name}' created", now=ctx.clock.now(), actor=user.username, room_id=room.id)
    return room


@router.get("/rooms/{room_id}", tags=["rooms"])
def room_detail(room_id: int, _: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx),
                db: Session = Depends(get_db)):
    room = _room_or_404(db, room_id)
    appliances = []
    for a in sorted(room.appliances, key=lambda x: x.relay_channel):
        decision = evaluate_appliance(ctx, db, a)  # read-only evaluation for the explanation panel
        appliances.append({**ApplianceOut.model_validate(a).model_dump(mode="json"), "decision": decision.to_dict()})
    return {
        "room": RoomOut.model_validate(room).model_dump(mode="json"),
        "appliances": appliances,
        "devices": [{"id": d.id, "name": d.name, "kind": d.kind, "connection_status": d.connection_status,
                     "sensor_status": d.sensor_status} for d in room.devices],
        "schedules": [ScheduleOut.model_validate(s).model_dump() for s in room.schedules],
    }


@router.patch("/rooms/{room_id}", response_model=RoomOut, tags=["rooms"])
def update_room(room_id: int, body: RoomUpdate, user: CurrentUser = Depends(operator),
                ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    room = _room_or_404(db, room_id)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and db.query(Room).filter(Room.name == changes["name"], Room.id != room_id).first():
        raise HTTPException(409, "a room with this name already exists")
    for k, v in changes.items():
        setattr(room, k, v)
    log_event(db, "config", f"Room '{room.name}' updated: {sorted(changes)}", now=ctx.clock.now(),
              actor=user.username, room_id=room.id, details=changes)
    emit(db, "room", {"id": room.id})
    return room


@router.delete("/rooms/{room_id}", status_code=204, tags=["rooms"])
def delete_room(room_id: int, user: CurrentUser = Depends(operator), ctx: AppContext = Depends(get_ctx),
                db: Session = Depends(get_db)):
    room = _room_or_404(db, room_id)
    log_event(db, "config", f"Room '{room.name}' deleted", now=ctx.clock.now(), actor=user.username, room_id=room.id)
    db.delete(room)


@router.post("/rooms/{room_id}/override", response_model=RoomOut, tags=["rooms"])
def set_override(room_id: int, body: OverrideRequest, user: CurrentUser = Depends(operator),
                 ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    """Manual override: while active, automation never switches anything in this room."""
    room = _room_or_404(db, room_id)
    now = ctx.clock.now()
    room.manual_override = body.enabled
    room.override_until = now + timedelta(minutes=body.minutes) if body.enabled and body.minutes else None
    room.override_reason = body.reason if body.enabled else ""
    log_event(db, "override", f"Manual override {'ENABLED' if body.enabled else 'disabled'} for {room.name}"
              + (f" for {body.minutes:g} min" if body.enabled and body.minutes else ""),
              now=now, actor=user.username, room_id=room.id, details={"reason": body.reason})
    emit(db, "room", {"id": room.id})
    return room


# ---------------------------------------------------------------- appliances
def _validate_appliance_refs(db: Session, room_id: int, device_id: int | None, channel: int,
                             exclude_id: int | None = None) -> None:
    _room_or_404(db, room_id)
    if device_id is None:
        return
    dev = db.get(Device, device_id)
    if dev is None:
        raise HTTPException(422, "device not found")
    if dev.room_id is not None and dev.room_id != room_id:
        raise HTTPException(422, "device belongs to a different room")
    clash = db.query(Appliance).filter(Appliance.device_id == device_id, Appliance.relay_channel == channel)
    if exclude_id is not None:
        clash = clash.filter(Appliance.id != exclude_id)
    if clash.first():
        raise HTTPException(409, f"relay channel {channel} on this device is already in use")


@router.get("/appliances", response_model=list[ApplianceOut], tags=["appliances"])
def list_appliances(room_id: int | None = Query(default=None), _: CurrentUser = Depends(viewer),
                    db: Session = Depends(get_db)):
    q = db.query(Appliance)
    if room_id is not None:
        q = q.filter(Appliance.room_id == room_id)
    return q.order_by(Appliance.room_id, Appliance.relay_channel).all()


@router.post("/appliances", response_model=ApplianceOut, status_code=201, tags=["appliances"])
def create_appliance(body: ApplianceCreate, user: CurrentUser = Depends(operator),
                     ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    _validate_appliance_refs(db, body.room_id, body.device_id, body.relay_channel)
    a = Appliance(**body.model_dump())
    db.add(a)
    db.flush()
    log_event(db, "config", f"Appliance '{a.name}' added", now=ctx.clock.now(), actor=user.username,
              room_id=a.room_id, appliance_id=a.id)
    return a


@router.get("/appliances/{appliance_id}", tags=["appliances"])
def appliance_detail(appliance_id: int, _: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx),
                     db: Session = Depends(get_db)):
    a = _appliance_or_404(db, appliance_id)
    return {**ApplianceOut.model_validate(a).model_dump(mode="json"),
            "decision": evaluate_appliance(ctx, db, a).to_dict()}


@router.patch("/appliances/{appliance_id}", response_model=ApplianceOut, tags=["appliances"])
def update_appliance(appliance_id: int, body: ApplianceUpdate, user: CurrentUser = Depends(operator),
                     ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    a = _appliance_or_404(db, appliance_id)
    changes = body.model_dump(exclude_unset=True)
    room_id = changes.get("room_id", a.room_id)
    device_id = changes.get("device_id", a.device_id)
    channel = changes.get("relay_channel", a.relay_channel)
    if {"room_id", "device_id", "relay_channel"} & changes.keys():
        _validate_appliance_refs(db, room_id, device_id, channel, exclude_id=a.id)
    rated = changes.get("rated_power_w", a.rated_power_w)
    standby = changes.get("standby_threshold_w", a.standby_threshold_w)
    if standby >= rated:
        raise HTTPException(422, "standby_threshold_w must be lower than rated_power_w")
    for k, v in changes.items():
        setattr(a, k, v)
    log_event(db, "config", f"Appliance '{a.name}' updated: {sorted(changes)}", now=ctx.clock.now(),
              actor=user.username, room_id=a.room_id, appliance_id=a.id, details=changes)
    emit(db, "appliance", {"id": a.id})
    return a


@router.delete("/appliances/{appliance_id}", status_code=204, tags=["appliances"])
def delete_appliance(appliance_id: int, user: CurrentUser = Depends(operator), ctx: AppContext = Depends(get_ctx),
                     db: Session = Depends(get_db)):
    a = _appliance_or_404(db, appliance_id)
    log_event(db, "config", f"Appliance '{a.name}' deleted", now=ctx.clock.now(), actor=user.username,
              room_id=a.room_id, appliance_id=a.id)
    db.delete(a)


# ---------------------------------------------------------------- schedules
@router.get("/schedules", response_model=list[ScheduleOut], tags=["schedules"])
def list_schedules(room_id: int | None = Query(default=None), _: CurrentUser = Depends(viewer),
                   db: Session = Depends(get_db)):
    q = db.query(Schedule)
    if room_id is not None:
        q = q.filter(Schedule.room_id == room_id)
    return q.order_by(Schedule.room_id, Schedule.day_of_week, Schedule.start_time).all()


@router.post("/schedules", response_model=ScheduleOut, status_code=201, tags=["schedules"])
def create_schedule(body: ScheduleCreate, user: CurrentUser = Depends(operator), ctx: AppContext = Depends(get_ctx),
                    db: Session = Depends(get_db)):
    _room_or_404(db, body.room_id)
    s = Schedule(**body.model_dump())
    db.add(s)
    db.flush()
    log_event(db, "config", f"Schedule added ({s.label or 'unnamed'})", now=ctx.clock.now(), actor=user.username,
              room_id=s.room_id)
    return s


@router.patch("/schedules/{schedule_id}", response_model=ScheduleOut, tags=["schedules"])
def update_schedule(schedule_id: int, body: ScheduleUpdate, user: CurrentUser = Depends(operator),
                    ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    s = db.get(Schedule, schedule_id)
    if s is None:
        raise HTTPException(404, "schedule not found")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("start_time", s.start_time) == changes.get("end_time", s.end_time):
        raise HTTPException(422, "start_time and end_time must differ")
    for k, v in changes.items():
        setattr(s, k, v)
    log_event(db, "config", f"Schedule #{s.id} updated", now=ctx.clock.now(), actor=user.username, room_id=s.room_id)
    return s


@router.delete("/schedules/{schedule_id}", status_code=204, tags=["schedules"])
def delete_schedule(schedule_id: int, user: CurrentUser = Depends(operator), ctx: AppContext = Depends(get_ctx),
                    db: Session = Depends(get_db)):
    s = db.get(Schedule, schedule_id)
    if s is None:
        raise HTTPException(404, "schedule not found")
    log_event(db, "config", f"Schedule #{s.id} deleted", now=ctx.clock.now(), actor=user.username, room_id=s.room_id)
    db.delete(s)

