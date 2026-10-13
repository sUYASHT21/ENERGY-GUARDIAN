"""Persistent event log (audit trail)."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..context import emit
from ..models import EventLog

log = logging.getLogger("seg.events")


def log_event(
    db: Session,
    category: str,
    message: str,
    *,
    now,
    level: str = "info",
    actor: str | None = None,
    room_id: int | None = None,
    appliance_id: int | None = None,
    device_id: int | None = None,
    details: dict | None = None,
) -> EventLog:
    ev = EventLog(ts=now, level=level, category=category, message=message, actor=actor, room_id=room_id,
                  appliance_id=appliance_id, device_id=device_id, details=details or {})
    db.add(ev)
    db.flush()
    getattr(log, "warning" if level == "warning" else "error" if level == "error" else "info")(
        "[%s] %s", category, message)
    emit(db, "event", {"id": ev.id, "ts": now.isoformat(), "level": level, "category": category,
                       "message": message})
    return ev
