"""Pydantic request/response schemas for the REST API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import APPLIANCE_TYPES, DEVICE_KINDS, ROOM_TYPES

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
RoomType = Literal[ROOM_TYPES]  # type: ignore[valid-type]
ApplianceType = Literal[APPLIANCE_TYPES]  # type: ignore[valid-type]
DeviceKind = Literal[DEVICE_KINDS]  # type: ignore[valid-type]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth / users
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(ORM):
    id: int
    username: str
    role: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=256)
    role: Literal["viewer", "operator", "admin"] = "viewer"


class UserUpdate(BaseModel):
    role: Literal["viewer", "operator", "admin"] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)


# ---------------------------------------------------------------- rooms
class RoomBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    room_type: RoomType = "classroom"
    building: str = Field(default="", max_length=100)
    floor: int = Field(default=0, ge=-5, le=200)
    capacity: int = Field(default=0, ge=0, le=10000)
    auto_control_enabled: bool = True
    min_vacancy_minutes: float = Field(default=10.0, ge=0.5, le=240)


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    room_type: RoomType | None = None
    building: str | None = Field(default=None, max_length=100)
    floor: int | None = Field(default=None, ge=-5, le=200)
    capacity: int | None = Field(default=None, ge=0, le=10000)
    auto_control_enabled: bool | None = None
    min_vacancy_minutes: float | None = Field(default=None, ge=0.5, le=240)


class RoomOut(ORM, RoomBase):
    id: int
    manual_override: bool
    override_until: datetime | None
    override_reason: str
    occupancy_state: str
    occupancy_updated_at: datetime | None
    vacant_since: datetime | None
    people_count: int | None
    occupancy_source: str | None


class OverrideRequest(BaseModel):
    enabled: bool
    minutes: float | None = Field(default=None, gt=0, le=7 * 24 * 60, description="None = until disabled")
    reason: str = Field(default="", max_length=200)


# ---------------------------------------------------------------- appliances
class ApplianceBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    appliance_type: ApplianceType = "light"
    room_id: int
    device_id: int | None = None
    relay_channel: int = Field(default=0, ge=0, le=63)
    rated_power_w: float = Field(default=100.0, gt=0, le=100_000)
    standby_threshold_w: float = Field(default=5.0, ge=0, le=10_000)
    essential: bool = False
    auto_off_allowed: bool = True

    @model_validator(mode="after")
    def _threshold_below_rating(self):
        if self.standby_threshold_w >= self.rated_power_w:
            raise ValueError("standby_threshold_w must be lower than rated_power_w")
        return self


class ApplianceCreate(ApplianceBase):
    pass


class ApplianceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    appliance_type: ApplianceType | None = None
    room_id: int | None = None
    device_id: int | None = None
    relay_channel: int | None = Field(default=None, ge=0, le=63)
    rated_power_w: float | None = Field(default=None, gt=0, le=100_000)
    standby_threshold_w: float | None = Field(default=None, ge=0, le=10_000)
    essential: bool | None = None
    auto_off_allowed: bool | None = None
    manual_override: bool | None = None


class ApplianceOut(ORM, ApplianceBase):
    id: int
    manual_override: bool
    state: str
    last_power_w: float | None
    last_voltage_v: float | None
    last_current_a: float | None
    last_reading_at: datetime | None
    last_source: str | None
    last_anomaly_score: float | None
    anomaly_streak: int


# ---------------------------------------------------------------- devices
class DeviceCreate(BaseModel):
    uid: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    name: str = Field(min_length=1, max_length=100)
    kind: DeviceKind = "esp32"
    room_id: int | None = None
    has_occupancy_sensor: bool = True


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    room_id: int | None = None
    has_occupancy_sensor: bool | None = None
    control_validated: bool | None = None


class DeviceOut(ORM):
    id: int
    uid: str
    name: str
    kind: str
    source: str
    room_id: int | None
    has_occupancy_sensor: bool
    control_validated: bool
    connection_status: str
    last_seen_at: datetime | None
    firmware_version: str | None
    ip_address: str | None
    rssi_dbm: int | None
    uptime_s: int | None
    free_heap: int | None
    sensor_status: str
    error_count: int


class DeviceCreated(BaseModel):
    device: DeviceOut
    api_key: str = Field(description="Shown once. Store it in the device firmware configuration.")


# ---------------------------------------------------------------- schedules
class ScheduleBase(BaseModel):
    room_id: int
    day_of_week: int = Field(ge=0, le=6, description="0=Monday … 6=Sunday")
    start_time: str = Field(pattern=HHMM)
    end_time: str = Field(pattern=HHMM)
    label: str = Field(default="", max_length=100)
    enabled: bool = True

    @field_validator("end_time")
    @classmethod
    def _not_empty_window(cls, v, info):
        if info.data.get("start_time") == v:
            raise ValueError("start_time and end_time must differ")
        return v


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleUpdate(BaseModel):
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    start_time: str | None = Field(default=None, pattern=HHMM)
    end_time: str | None = Field(default=None, pattern=HHMM)
    label: str | None = Field(default=None, max_length=100)
    enabled: bool | None = None


class ScheduleOut(ORM, ScheduleBase):
    id: int


# ---------------------------------------------------------------- alerts / commands
class AlertActionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=200)


class CommandCreate(BaseModel):
    appliance_id: int
    action: Literal["on", "off"]
    dry_run: bool = False
    reason: str = Field(default="", max_length=300)
    confirm_essential: bool = False


# ---------------------------------------------------------------- simulation / ml
class ScenarioRequest(BaseModel):
    room_id: int
    scenario: str = Field(min_length=1, max_length=40)


class TrainRequest(BaseModel):
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    n_estimators: int = Field(default=200, ge=10, le=1000)
    contamination: float = Field(default=0.03, gt=0, le=0.5)


# ---------------------------------------------------------------- esp32
class CommandAck(BaseModel):
    success: bool
    relay_on: bool | None = None
    error: str | None = Field(default=None, max_length=300)
