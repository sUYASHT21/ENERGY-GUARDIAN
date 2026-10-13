"""Dashboard, alerts, commands, events, settings, ML and simulation endpoints."""
from __future__ import annotations

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import Integer, cast, func
from sqlalchemy.orm import Session

from ..context import AppContext, emit
from ..models import Alert, Appliance, Command, EventLog, MLModelRecord, Room, TelemetryReading
from ..schemas import AlertActionRequest, CommandCreate, ScenarioRequest, TrainRequest
from ..services import alerts as alert_service
from ..services import analytics, ml_service
from ..services import commands as command_service
from ..services.events import log_event
from ..services.settings_service import RuntimeSettings, load_settings, save_settings
from .deps import CurrentUser, admin, get_ctx, get_db, operator, viewer

router = APIRouter()
RANGE_HOURS = {"24h": (24, "hour"), "7d": (24 * 7, "day"), "30d": (24 * 30, "day")}


# ---------------------------------------------------------------- dashboard
@router.get("/dashboard/summary", tags=["dashboard"])
def dashboard_summary(_: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx),
                      db: Session = Depends(get_db)):
    return analytics.summary(ctx, db)


@router.get("/dashboard/history", tags=["dashboard"])
def dashboard_history(range: Literal["24h", "7d", "30d"] = "24h", room_id: int | None = None,
                      _: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx),
                      db: Session = Depends(get_db)):
    hours, group = RANGE_HOURS[range]
    return analytics.history(ctx, db, hours=hours, group=group, room_id=room_id)


@router.get("/dashboard/rooms", tags=["dashboard"])
def dashboard_rooms(hours: int = Query(default=24, ge=1, le=24 * 60), _: CurrentUser = Depends(viewer),
                    ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    return analytics.room_breakdown(ctx, db, hours=hours)


@router.get("/dashboard/live-power", tags=["dashboard"])
def dashboard_live_power(minutes: int = Query(default=15, ge=1, le=180), room_id: int | None = None,
                         _: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx),
                         db: Session = Depends(get_db)):
    bucket = 15 if minutes <= 30 else 60
    return analytics.live_power_series(ctx, db, minutes=minutes, bucket_s=bucket, room_id=room_id)


@router.get("/dashboard/overview", tags=["dashboard"])
def dashboard_overview(_: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx),
                       db: Session = Depends(get_db)):
    """Per-room occupancy and appliance status for the dashboard grid."""
    out = []
    for room in db.query(Room).order_by(Room.name).all():
        apps = sorted(room.appliances, key=lambda a: a.relay_channel)
        out.append({
            "id": room.id, "name": room.name, "room_type": room.room_type, "occupancy_state": room.occupancy_state,
            "people_count": room.people_count, "vacant_since": room.vacant_since.isoformat() if room.vacant_since else None,
            "occupancy_source": room.occupancy_source, "manual_override": room.manual_override,
            "power_w": round(sum((a.last_power_w or 0) for a in apps if a.state == "on"), 1),
            "appliances": [{"id": a.id, "name": a.name, "type": a.appliance_type, "state": a.state,
                            "power_w": a.last_power_w, "essential": a.essential, "source": a.last_source,
                            "anomaly": a.anomaly_streak >= 2,
                            "decision": (ctx.decisions.get(a.id) or {}).get("action")} for a in apps],
            "devices": [{"id": d.id, "name": d.name, "kind": d.kind, "connection_status": d.connection_status,
                         "sensor_status": d.sensor_status} for d in room.devices],
        })
    return out


@router.get("/telemetry", tags=["dashboard"])
def recent_telemetry(appliance_id: int | None = None, room_id: int | None = None,
                     minutes: int = Query(default=10, ge=1, le=24 * 60), limit: int = Query(default=500, ge=1, le=5000),
                     _: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    q = db.query(TelemetryReading).filter(TelemetryReading.ts >= ctx.clock.now() - timedelta(minutes=minutes))
    if appliance_id is not None:
        q = q.filter(TelemetryReading.appliance_id == appliance_id)
    if room_id is not None:
        q = q.filter(TelemetryReading.room_id == room_id)
    rows = q.order_by(TelemetryReading.ts.desc()).limit(limit).all()
    return [{"id": r.id, "appliance_id": r.appliance_id, "ts": r.ts.isoformat(), "power_w": r.power_w,
             "voltage_v": r.voltage_v, "current_a": r.current_a, "relay_on": r.relay_on, "source": r.source,
             "energy_delta_kwh": r.energy_delta_kwh, "anomaly_score": r.anomaly_score, "is_anomaly": r.is_anomaly,
             "anomaly_method": r.anomaly_method} for r in reversed(rows)]


@router.get("/decisions", tags=["dashboard"])
def latest_decisions(_: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx)):
    """Most recent decision-engine output per appliance (refreshed every monitor cycle)."""
    return list(ctx.decisions.values())


# ---------------------------------------------------------------- alerts
@router.get("/alerts", tags=["alerts"])
def list_alerts(status: Literal["open", "resolved", "all"] = "open", alert_type: str | None = None,
                severity: str | None = None, room_id: int | None = None,
                limit: int = Query(default=100, ge=1, le=1000), _: CurrentUser = Depends(viewer),
                db: Session = Depends(get_db)):
    q = db.query(Alert)
    if status == "open":
        q = q.filter(Alert.resolved.is_(False))
    elif status == "resolved":
        q = q.filter(Alert.resolved.is_(True))
    if alert_type:
        q = q.filter(Alert.alert_type == alert_type)
    if severity:
        q = q.filter(Alert.severity == severity)
    if room_id is not None:
        q = q.filter(Alert.room_id == room_id)
    return [alert_service.alert_to_dict(a) for a in q.order_by(Alert.last_seen_at.desc()).limit(limit).all()]


def _alert_or_404(db: Session, alert_id: int) -> Alert:
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "alert not found")
    return a


@router.post("/alerts/{alert_id}/acknowledge", tags=["alerts"])
def acknowledge_alert(alert_id: int, user: CurrentUser = Depends(operator), ctx: AppContext = Depends(get_ctx),
                      db: Session = Depends(get_db)):
    a = alert_service.acknowledge(db, _alert_or_404(db, alert_id), now=ctx.clock.now(), user=user.username)
    return alert_service.alert_to_dict(a)


@router.post("/alerts/{alert_id}/resolve", tags=["alerts"])
def resolve_alert(alert_id: int, body: AlertActionRequest = Body(default_factory=AlertActionRequest),
                  user: CurrentUser = Depends(operator), ctx: AppContext = Depends(get_ctx),
                  db: Session = Depends(get_db)):
    a = alert_service.resolve_manually(db, _alert_or_404(db, alert_id), now=ctx.clock.now(), user=user.username,
                                       note=body.note)
    return alert_service.alert_to_dict(a)


# ---------------------------------------------------------------- commands
@router.get("/commands", tags=["commands"])
def list_commands(status: str | None = None, appliance_id: int | None = None,
                  limit: int = Query(default=100, ge=1, le=1000), _: CurrentUser = Depends(viewer),
                  db: Session = Depends(get_db)):
    q = db.query(Command)
    if status:
        q = q.filter(Command.status == status)
    if appliance_id is not None:
        q = q.filter(Command.appliance_id == appliance_id)
    return [command_service.command_to_dict(c) for c in q.order_by(Command.id.desc()).limit(limit).all()]


@router.post("/commands", status_code=201, tags=["commands"])
def create_command(body: CommandCreate, user: CurrentUser = Depends(operator), ctx: AppContext = Depends(get_ctx),
                   db: Session = Depends(get_db)):
    """Manual appliance command. Passes through the same safety gate as automation;
    blocked commands are recorded with the reason (HTTP 201 with status 'blocked')."""
    appliance = db.get(Appliance, body.appliance_id)
    if appliance is None:
        raise HTTPException(404, "appliance not found")
    cmd = command_service.create_command(ctx, db, appliance, body.action, origin="manual", actor=user.username,
                                         reason=body.reason or f"manual {body.action} by {user.username}",
                                         dry_run=body.dry_run, confirm_essential=body.confirm_essential,
                                         actor_role=user.role)
    return command_service.command_to_dict(cmd)


# ---------------------------------------------------------------- events
@router.get("/events", tags=["events"])
def list_events(category: str | None = None, level: str | None = None, before_id: int | None = None,
                limit: int = Query(default=100, ge=1, le=1000), _: CurrentUser = Depends(viewer),
                db: Session = Depends(get_db)):
    q = db.query(EventLog)
    if category:
        q = q.filter(EventLog.category == category)
    if level:
        q = q.filter(EventLog.level == level)
    if before_id:
        q = q.filter(EventLog.id < before_id)
    return [{"id": e.id, "ts": e.ts.isoformat(), "level": e.level, "category": e.category, "message": e.message,
             "actor": e.actor, "room_id": e.room_id, "appliance_id": e.appliance_id, "device_id": e.device_id,
             "details": e.details} for e in q.order_by(EventLog.id.desc()).limit(limit).all()]


# ---------------------------------------------------------------- settings
def _settings_response(ctx: AppContext, rs: RuntimeSettings) -> dict:
    s = ctx.settings
    return {
        "runtime": rs.model_dump(mode="json"),
        "environment": {  # read-only: change via environment variables + restart
            "app_env": s.app_env, "real_switching_enabled": s.real_switching_enabled,
            "simulation_enabled": s.simulation_enabled, "command_timeout_seconds": s.command_timeout_seconds,
            "device_offline_seconds": s.device_offline_seconds, "telemetry_stale_seconds": s.telemetry_stale_seconds,
            "max_integration_gap_seconds": s.max_integration_gap_seconds,
            "using_insecure_defaults": s.using_insecure_defaults,
        },
    }


@router.get("/settings", tags=["settings"])
def get_settings_endpoint(_: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx),
                          db: Session = Depends(get_db)):
    return _settings_response(ctx, load_settings(db))


@router.put("/settings", tags=["settings"])
def update_settings(updates: dict = Body(...), user: CurrentUser = Depends(admin), ctx: AppContext = Depends(get_ctx),
                    db: Session = Depends(get_db)):
    unknown = set(updates) - set(RuntimeSettings.model_fields)
    if unknown:
        raise HTTPException(422, f"unknown or read-only settings: {sorted(unknown)}")
    try:
        rs = save_settings(db, updates, user.username)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False)) from exc
    log_event(db, "settings", f"Settings updated: {sorted(updates)}", now=ctx.clock.now(), actor=user.username,
              level="warning" if "automation_mode" in updates else "info", details=updates)
    emit(db, "settings", rs.model_dump(mode="json"))
    return _settings_response(ctx, rs)


# ---------------------------------------------------------------- ML
@router.get("/ml/status", tags=["ml"])
def ml_status(_: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    active = db.query(MLModelRecord).filter(MLModelRecord.active.is_(True)).first()
    since = ctx.clock.now() - timedelta(hours=1)
    total, flagged = db.query(func.count(TelemetryReading.id), func.sum(cast(TelemetryReading.is_anomaly, Integer))) \
        .filter(TelemetryReading.ts >= since).one()
    return {
        "method": ctx.anomaly.method, "model_version": ctx.anomaly.version, "last_error": ctx.anomaly.last_error,
        "active_model": ml_service.record_to_dict(active) if active else None,
        "models": [ml_service.record_to_dict(r) for r in db.query(MLModelRecord).order_by(MLModelRecord.id.desc()).all()],
        "last_hour": {"readings_scored": total or 0, "flagged": int(flagged or 0)},
        "disclaimer": "Metrics are computed on SYNTHETIC labelled data generated by the app. They demonstrate a "
                      "working, reproducible pipeline and are not a measure of real-world accuracy.",
        "safety_note": "Anomaly results are advisory. They never authorize an automatic shutdown on their own.",
    }


@router.post("/ml/train", tags=["ml"])
def ml_train(body: TrainRequest = Body(default_factory=TrainRequest), user: CurrentUser = Depends(admin),
             ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    rec = ml_service.train_and_activate(ctx, db, seed=body.seed, n_estimators=body.n_estimators,
                                        contamination=body.contamination, actor=user.username)
    return ml_service.record_to_dict(rec)


@router.post("/ml/models/{model_id}/activate", tags=["ml"])
def ml_activate(model_id: int, user: CurrentUser = Depends(admin), ctx: AppContext = Depends(get_ctx),
                db: Session = Depends(get_db)):
    rec = db.get(MLModelRecord, model_id)
    if rec is None:
        raise HTTPException(404, "model not found")
    if not ml_service.activate(ctx, db, rec, user.username):
        raise HTTPException(500, f"could not load model artifact: {ctx.anomaly.last_error}")
    return ml_service.record_to_dict(rec)


@router.get("/ml/scores", tags=["ml"])
def ml_scores(appliance_id: int | None = None, minutes: int = Query(default=30, ge=1, le=24 * 60),
              only_anomalies: bool = False, limit: int = Query(default=300, ge=1, le=5000),
              _: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    q = db.query(TelemetryReading).filter(TelemetryReading.ts >= ctx.clock.now() - timedelta(minutes=minutes),
                                          TelemetryReading.anomaly_score.is_not(None))
    if appliance_id is not None:
        q = q.filter(TelemetryReading.appliance_id == appliance_id)
    if only_anomalies:
        q = q.filter(TelemetryReading.is_anomaly.is_(True))
    names = {a.id: a.name for a in db.query(Appliance).all()}
    rows = q.order_by(TelemetryReading.ts.desc()).limit(limit).all()
    return [{"ts": r.ts.isoformat(), "appliance_id": r.appliance_id, "appliance": names.get(r.appliance_id),
             "score": r.anomaly_score, "is_anomaly": r.is_anomaly, "method": r.anomaly_method,
             "power_w": r.power_w, "source": r.source} for r in reversed(rows)]


# ---------------------------------------------------------------- simulation
def _sim(ctx: AppContext):
    if ctx.simulator is None:
        raise HTTPException(409, "simulation is disabled (SIMULATION_ENABLED=false)")
    return ctx.simulator


@router.get("/simulation", tags=["simulation"])
def simulation_status(_: CurrentUser = Depends(viewer), ctx: AppContext = Depends(get_ctx),
                      db: Session = Depends(get_db)):
    if ctx.simulator is None:
        return {"enabled": False, "running": False}
    return {"enabled": True, **ctx.simulator.status_dict(db)}


@router.post("/simulation/start", tags=["simulation"])
async def simulation_start(user: CurrentUser = Depends(operator), ctx: AppContext = Depends(get_ctx)):
    sim = _sim(ctx)
    sim.start()
    with ctx.db.session() as db:
        log_event(db, "simulation", "Simulation started", now=ctx.clock.now(), actor=user.username)
        emit(db, "simulation", sim.status_dict(db))
        return sim.status_dict(db)


@router.post("/simulation/stop", tags=["simulation"])
async def simulation_stop(user: CurrentUser = Depends(operator), ctx: AppContext = Depends(get_ctx)):
    sim = _sim(ctx)
    await sim.stop()
    with ctx.db.session() as db:
        log_event(db, "simulation", "Simulation stopped", now=ctx.clock.now(), actor=user.username)
        emit(db, "simulation", sim.status_dict(db))
        return sim.status_dict(db)


@router.post("/simulation/scenario", tags=["simulation"])
def simulation_scenario(body: ScenarioRequest, user: CurrentUser = Depends(operator),
                        ctx: AppContext = Depends(get_ctx)):
    sim = _sim(ctx)
    try:
        sim.set_scenario(body.room_id, body.scenario, actor=user.username)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    with ctx.db.session() as db:
        return sim.status_dict(db)


@router.post("/simulation/reset", tags=["simulation"])
def simulation_reset(user: CurrentUser = Depends(operator), ctx: AppContext = Depends(get_ctx)):
    sim = _sim(ctx)
    sim.reset(actor=user.username)
    with ctx.db.session() as db:
        return sim.status_dict(db)


@router.post("/simulation/tick", tags=["simulation"])
def simulation_tick(steps: int = Query(default=1, ge=1, le=50), _: CurrentUser = Depends(operator),
                    ctx: AppContext = Depends(get_ctx)):
    """Advance the simulation manually (useful while it is stopped)."""
    sim = _sim(ctx)
    for _i in range(steps):
        sim.tick()
    with ctx.db.session() as db:
        return sim.status_dict(db)
