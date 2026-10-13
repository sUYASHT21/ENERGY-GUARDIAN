"""Alert lifecycle: raise (deduplicated), acknowledge, resolve."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..context import emit
from ..models import Alert
from .events import log_event


def alert_to_dict(a: Alert) -> dict:
    return {
        "id": a.id, "alert_type": a.alert_type, "severity": a.severity, "title": a.title,
        "message": a.message, "room_id": a.room_id, "appliance_id": a.appliance_id, "device_id": a.device_id,
        "source": a.source, "details": a.details, "recommendation": a.recommendation,
        "created_at": a.created_at.isoformat(), "last_seen_at": a.last_seen_at.isoformat(),
        "occurrences": a.occurrences, "acknowledged": a.acknowledged, "acknowledged_by": a.acknowledged_by,
        "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        "resolved": a.resolved, "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "resolution_note": a.resolution_note,
    }


def open_alert(db: Session, dedupe_key: str) -> Alert | None:
    return db.query(Alert).filter(Alert.dedupe_key == dedupe_key, Alert.resolved.is_(False)).first()


def raise_alert(
    db: Session,
    *,
    now,
    alert_type: str,
    dedupe_key: str,
    title: str,
    message: str = "",
    severity: str = "warning",
    room_id: int | None = None,
    appliance_id: int | None = None,
    device_id: int | None = None,
    source: str | None = None,
    details: dict | None = None,
    recommendation: str | None = None,
) -> tuple[Alert, bool]:
    """Create an alert, or refresh the existing open alert with the same dedupe key.

    Returns (alert, created)."""
    existing = open_alert(db, dedupe_key)
    if existing:
        existing.last_seen_at = now
        existing.occurrences += 1
        if details is not None:
            existing.details = details
        if message:
            existing.message = message
        if recommendation is not None:
            existing.recommendation = recommendation
        # escalate severity but never silently downgrade
        order = {"info": 0, "warning": 1, "critical": 2}
        if order[severity] > order[existing.severity]:
            existing.severity = severity
        return existing, False
    a = Alert(alert_type=alert_type, severity=severity, title=title, message=message, room_id=room_id,
              appliance_id=appliance_id, device_id=device_id, dedupe_key=dedupe_key, source=source,
              details=details or {}, recommendation=recommendation, created_at=now, last_seen_at=now)
    db.add(a)
    db.flush()
    log_event(db, "alert", f"{severity.upper()}: {title}", now=now,
              level="warning" if severity != "info" else "info",
              room_id=room_id, appliance_id=appliance_id, device_id=device_id,
              details={"alert_id": a.id, "type": alert_type})
    emit(db, "alert", alert_to_dict(a))
    return a, True


def resolve_alerts(db: Session, dedupe_key: str, *, now, note: str) -> int:
    n = 0
    for a in db.query(Alert).filter(Alert.dedupe_key == dedupe_key, Alert.resolved.is_(False)).all():
        a.resolved = True
        a.resolved_at = now
        a.resolution_note = note
        n += 1
        emit(db, "alert", alert_to_dict(a))
    return n


def acknowledge(db: Session, alert: Alert, *, now, user: str) -> Alert:
    if not alert.acknowledged:
        alert.acknowledged = True
        alert.acknowledged_by = user
        alert.acknowledged_at = now
        log_event(db, "alert", f"Alert #{alert.id} acknowledged", now=now, actor=user,
                  room_id=alert.room_id, appliance_id=alert.appliance_id, details={"alert_id": alert.id})
        emit(db, "alert", alert_to_dict(alert))
    return alert


def resolve_manually(db: Session, alert: Alert, *, now, user: str, note: str | None) -> Alert:
    if not alert.resolved:
        alert.resolved = True
        alert.resolved_at = now
        alert.resolution_note = note or f"resolved by {user}"
        if not alert.acknowledged:
            alert.acknowledged, alert.acknowledged_by, alert.acknowledged_at = True, user, now
        log_event(db, "alert", f"Alert #{alert.id} resolved", now=now, actor=user,
                  room_id=alert.room_id, appliance_id=alert.appliance_id, details={"alert_id": alert.id})
        emit(db, "alert", alert_to_dict(alert))
    return alert
