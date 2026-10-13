"""Time source abstraction. All business logic receives time from a Clock so tests can
control it deterministically. All datetimes are timezone-aware UTC."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; treat naive datetimes as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class Clock:
    def now(self) -> datetime:
        return utcnow()


class FakeClock(Clock):
    def __init__(self, start: datetime | None = None):
        self._now = start or datetime(2026, 1, 5, 9, 0, tzinfo=UTC)  # a Monday

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float = 0, **kwargs) -> datetime:
        self._now = self._now + timedelta(seconds=seconds, **kwargs)
        return self._now

    def set(self, dt: datetime) -> None:
        self._now = ensure_utc(dt)
