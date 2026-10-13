"""Schedule evaluation (expected room usage windows, in the configured local timezone)."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .energy import _parse_hhmm, time_in_window


@dataclass(frozen=True)
class ScheduleWindow:
    day_of_week: int
    start_time: str
    end_time: str
    label: str = ""
    enabled: bool = True


def _windows_active_at(windows: Iterable[ScheduleWindow], local: datetime) -> list[ScheduleWindow]:
    t = local.time()
    out = []
    for w in windows:
        if not w.enabled:
            continue
        start, end = _parse_hhmm(w.start_time), _parse_hhmm(w.end_time)
        if start < end:
            if w.day_of_week == local.weekday() and time_in_window(t, start, end):
                out.append(w)
        else:  # crosses midnight: belongs to the day it starts on
            if (w.day_of_week == local.weekday() and t >= start) or (
                w.day_of_week == (local.weekday() - 1) % 7 and t < end
            ):
                out.append(w)
    return out


def active_windows(windows: Iterable[ScheduleWindow], now_utc: datetime, tz: str) -> list[ScheduleWindow]:
    return _windows_active_at(list(windows), now_utc.astimezone(ZoneInfo(tz)))


def window_starting_within(
    windows: Iterable[ScheduleWindow], now_utc: datetime, tz: str, minutes: float
) -> ScheduleWindow | None:
    """Return a window that is not active now but becomes active within ``minutes``."""
    windows = list(windows)
    local = now_utc.astimezone(ZoneInfo(tz))
    if minutes <= 0:
        return None
    active_now = set(_windows_active_at(windows, local))
    step = 1.0
    m = step
    while m <= minutes:
        for w in _windows_active_at(windows, local + timedelta(minutes=m)):
            if w not in active_now:
                return w
        m += step
    return None
