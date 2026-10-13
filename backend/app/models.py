"""SQLAlchemy ORM models."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .clock import utcnow
from .database import Base


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in SQLite, always returns tz-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Enumerations (stored as strings for readability / portability)
# ---------------------------------------------------------------------------
ROOM_TYPES = ("classroom", "laboratory", "hostel", "office", "other")
APPLIANCE_TYPES = (
    "light", "fan", "ac", "projector", "computer", "lab_equipment",
    "heater", "refrigerator", "server", "emergency_light", "other",
)
DEVICE_KINDS = ("simulated", "emulator", "esp32")
DATA_SOURCES = ("simulation", "emulator", "hardware")
OCCUPANCY_STATES = ("occupied", "vacant", "unknown")
USER_ROLES = ("viewer", "operator", "admin")
COMMAND_ACTIONS = ("on", "off")
COMMAND_STATUSES = ("pending", "sent", "acknowledged", "failed", "timeout", "dry_run", "blocked")
COMMAND_MODES = ("dry_run", "simulated", "emulator", "hardware")
ALERT_SEVERITIES = ("info", "warning", "critical")
ALERT_TYPES = (
    "vacant_room_waste", "anomaly", "sensor_failure", "device_offline", "stale_data",
    "command_failed", "command_timeout", "after_hours_usage",
)


def source_for_kind(kind: str) -> str:
    return {"simulated": "simulation", "emulator": "emulator", "esp32": "hardware"}[kind]


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    room_type: Mapped[str] = mapped_column(String(20), default="classroom")
    building: Mapped[str] = mapped_column(String(100), default="")
    floor: Mapped[int] = mapped_column(Integer, default=0)
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    auto_control_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_vacancy_minutes: Mapped[float] = mapped_column(Float, default=10.0)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    override_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    override_reason: Mapped[str] = mapped_column(String(200), default="")
    # Derived occupancy state, maintained by the telemetry pipeline / monitor.
    occupancy_state: Mapped[str] = mapped_column(String(10), default="unknown")
    occupancy_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    vacant_since: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    people_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occupancy_source: Mapped[str | None] = mapped_column(String(12), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    appliances: Mapped[list[Appliance]] = relationship(back_populates="room", cascade="all, delete-orphan")
    devices: Mapped[list[Device]] = relationship(back_populates="room")
    schedules: Mapped[list[Schedule]] = relationship(back_populates="room", cascade="all, delete-orphan")


class Device(Base):
    """A controller node (ESP32 or simulated equivalent) that reports telemetry and drives relays."""

    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # e.g. "esp32-lab1"
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(12), default="simulated")
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    api_key_hash: Mapped[str] = mapped_column(String(128))
    has_occupancy_sensor: Mapped[bool] = mapped_column(Boolean, default=True)
    # Must be set by an admin after independent validation before real relays may switch.
    control_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    connection_status: Mapped[str] = mapped_column(String(12), default="never_seen")  # online/offline/never_seen
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rssi_dbm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uptime_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_heap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sensor_status: Mapped[str] = mapped_column(String(12), default="unknown")  # ok/fault/unknown
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    room: Mapped[Room | None] = relationship(back_populates="devices")
    appliances: Mapped[list[Appliance]] = relationship(back_populates="device")

    @property
    def source(self) -> str:
        return source_for_kind(self.kind)


class Appliance(Base):
    __tablename__ = "appliances"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    appliance_type: Mapped[str] = mapped_column(String(20), default="light")
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    relay_channel: Mapped[int] = mapped_column(Integer, default=0)
    rated_power_w: Mapped[float] = mapped_column(Float, default=100.0)
    standby_threshold_w: Mapped[float] = mapped_column(Float, default=5.0)
    # Policies
    essential: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_off_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    # Live state (from telemetry)
    state: Mapped[str] = mapped_column(String(10), default="unknown")  # on/off/unknown
    last_power_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_current_a: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_reading_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_source: Mapped[str | None] = mapped_column(String(12), nullable=True)
    last_manual_on_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    anomaly_streak: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    room: Mapped[Room] = relationship(back_populates="appliances")
    device: Mapped[Device | None] = relationship(back_populates="appliances")


class TelemetryReading(Base):
    __tablename__ = "telemetry"
    id: Mapped[int] = mapped_column(primary_key=True)
    appliance_id: Mapped[int] = mapped_column(ForeignKey("appliances.id", ondelete="CASCADE"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(UTCDateTime)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    power_w: Mapped[float] = mapped_column(Float)
    voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_a: Mapped[float | None] = mapped_column(Float, nullable=True)
    relay_on: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source: Mapped[str] = mapped_column(String(12))
    energy_delta_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_anomaly: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    anomaly_method: Mapped[str | None] = mapped_column(String(20), nullable=True)

    __table_args__ = (Index("ix_telemetry_appliance_ts", "appliance_id", "ts"), Index("ix_telemetry_ts", "ts"))


class OccupancyReading(Base):
    __tablename__ = "occupancy_readings"
    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime)
    occupied: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # None = sensor could not decide
    people_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sensor_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(12))

    __table_args__ = (Index("ix_occ_room_ts", "room_id", "ts"),)


class EnergyRecord(Base):
    """15-minute energy bucket per appliance (kWh), built incrementally from telemetry."""

    __tablename__ = "energy_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    appliance_id: Mapped[int] = mapped_column(ForeignKey("appliances.id", ondelete="CASCADE"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    period_start: Mapped[datetime] = mapped_column(UTCDateTime)
    energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    wasted_kwh: Mapped[float] = mapped_column(Float, default=0.0)  # consumed while room was vacant
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(12))

    __table_args__ = (
        Index("ix_energy_unique", "appliance_id", "period_start", "source", unique=True),
        Index("ix_energy_period", "period_start"),
    )


class SavingsRecord(Base):
    """An *estimated* saving episode that starts when an appliance is confirmed switched off
    because of a waste decision. Avoided energy = baseline power x off-duration (capped)."""

    __tablename__ = "savings_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    appliance_id: Mapped[int] = mapped_column(ForeignKey("appliances.id", ondelete="CASCADE"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    command_id: Mapped[int | None] = mapped_column(ForeignKey("commands.id", ondelete="SET NULL"), nullable=True)
    baseline_power_w: Mapped[float] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(12))


class Schedule(Base):
    __tablename__ = "schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Monday .. 6=Sunday
    start_time: Mapped[str] = mapped_column(String(5))  # "HH:MM" local time
    end_time: Mapped[str] = mapped_column(String(5))
    label: Mapped[str] = mapped_column(String(100), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    room: Mapped[Room] = relationship(back_populates="schedules")


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(30), index=True)
    severity: Mapped[str] = mapped_column(String(10), default="warning")
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, default="")
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=True)
    appliance_id: Mapped[int | None] = mapped_column(ForeignKey("appliances.id", ondelete="CASCADE"), nullable=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(120), index=True)
    source: Mapped[str | None] = mapped_column(String(12), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    recommendation: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Command(Base):
    __tablename__ = "commands"
    id: Mapped[int] = mapped_column(primary_key=True)
    appliance_id: Mapped[int] = mapped_column(ForeignKey("appliances.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(4))
    mode: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(14), index=True)
    origin: Mapped[str] = mapped_column(String(10))  # automation / manual
    requested_by: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(300), default="")
    decision: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    result_relay_on: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)


class EventLog(Base):
    __tablename__ = "event_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    level: Mapped[str] = mapped_column(String(10), default="info")
    category: Mapped[str] = mapped_column(String(20), index=True)
    message: Mapped[str] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    room_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    appliance_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SettingEntry(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class MLModelRecord(Base):
    __tablename__ = "ml_models"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(40), unique=True)
    algorithm: Mapped[str] = mapped_column(String(40), default="isolation_forest")
    trained_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    data_source: Mapped[str] = mapped_column(String(40), default="synthetic")
    n_train: Mapped[int] = mapped_column(Integer, default=0)
    n_test: Mapped[int] = mapped_column(Integer, default=0)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    path: Mapped[str] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
