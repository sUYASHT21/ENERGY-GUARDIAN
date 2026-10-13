"""Sensor payload adapters.

Devices may send telemetry in different shapes. Each parser converts a raw JSON payload to the
canonical :class:`TelemetryPayload`. Register new sensor formats in ``PARSERS``.

Supported formats
-----------------
``seg.v1`` (default, verbose)::

    {"format": "seg.v1", "ts": "2026-10-13T10:00:00Z",
     "occupancy": {"occupied": true, "people_count": 3, "sensor_ok": true},
     "readings": [{"channel": 0, "power_w": 152.3, "voltage_v": 229.8, "current_a": 0.71, "relay_on": true}],
     "health": {"firmware": "1.0.0", "rssi_dbm": -61, "uptime_s": 3600, "free_heap": 182000}}

``compact.v1`` (small payload for constrained nodes)::

    {"format": "compact.v1", "occ": 1, "sok": 1, "pc": 3,
     "ch": [[0, 152.3, 229.8, 0.71, 1]], "fw": "1.0.0", "rssi": -61, "up": 3600, "heap": 182000}

    ``occ``: 1 occupied, 0 vacant, -1 unknown; each ``ch`` row is
    [channel, power_w, voltage_v, current_a, relay_on(0/1)].
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel, Field, ValidationError


class OccupancyIn(BaseModel):
    occupied: bool | None = None
    people_count: int | None = Field(default=None, ge=0, le=10000)
    sensor_ok: bool = True


class ReadingIn(BaseModel):
    channel: int = Field(ge=0, le=63)
    power_w: float = Field(ge=0, le=100_000)
    voltage_v: float | None = Field(default=None, ge=0, le=500)
    current_a: float | None = Field(default=None, ge=0, le=500)
    relay_on: bool | None = None


class HealthIn(BaseModel):
    firmware: str | None = Field(default=None, max_length=32)
    rssi_dbm: int | None = Field(default=None, ge=-130, le=0)
    uptime_s: int | None = Field(default=None, ge=0)
    free_heap: int | None = Field(default=None, ge=0)
    ip: str | None = Field(default=None, max_length=64)


class TelemetryPayload(BaseModel):
    ts: datetime | None = None
    occupancy: OccupancyIn | None = None
    readings: list[ReadingIn] = Field(default_factory=list, max_length=32)
    health: HealthIn | None = None


class PayloadError(ValueError):
    pass


def parse_seg_v1(raw: dict) -> TelemetryPayload:
    return TelemetryPayload.model_validate({k: v for k, v in raw.items() if k not in ("format", "device_uid")})


def parse_compact_v1(raw: dict) -> TelemetryPayload:
    occ_raw = raw.get("occ")
    occupancy = None
    if occ_raw is not None or "sok" in raw:
        occupied = None if occ_raw in (None, -1) else bool(occ_raw)
        occupancy = {"occupied": occupied, "people_count": raw.get("pc"), "sensor_ok": bool(raw.get("sok", 1))}
    readings = []
    for row in raw.get("ch", []):
        if not isinstance(row, list | tuple) or len(row) < 2:
            raise PayloadError("each 'ch' row must be [channel, power_w, voltage_v?, current_a?, relay_on?]")
        r = {"channel": row[0], "power_w": row[1]}
        if len(row) > 2 and row[2] is not None:
            r["voltage_v"] = row[2]
        if len(row) > 3 and row[3] is not None:
            r["current_a"] = row[3]
        if len(row) > 4 and row[4] is not None:
            r["relay_on"] = bool(row[4])
        readings.append(r)
    health = {"firmware": raw.get("fw"), "rssi_dbm": raw.get("rssi"), "uptime_s": raw.get("up"),
              "free_heap": raw.get("heap")}
    return TelemetryPayload.model_validate({"ts": raw.get("ts"), "occupancy": occupancy, "readings": readings,
                                            "health": health})


PARSERS: dict[str, Callable[[dict], TelemetryPayload]] = {
    "seg.v1": parse_seg_v1,
    "compact.v1": parse_compact_v1,
}


def parse_payload(raw: dict) -> TelemetryPayload:
    if not isinstance(raw, dict):
        raise PayloadError("payload must be a JSON object")
    fmt = raw.get("format", "seg.v1")
    parser = PARSERS.get(fmt)
    if parser is None:
        raise PayloadError(f"unsupported payload format '{fmt}'")
    try:
        return parser(raw)
    except ValidationError as exc:
        raise PayloadError(exc.errors(include_url=False, include_context=False)) from exc
