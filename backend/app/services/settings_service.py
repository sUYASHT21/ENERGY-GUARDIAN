"""Runtime (database-backed) settings editable by administrators.

Hardware switching is intentionally *not* a runtime setting; it lives in the environment.
"""
from __future__ import annotations

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from ..clock import utcnow
from ..models import SettingEntry
from .energy import Tariff, TouPeriod

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class TouPeriodModel(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    start: str = Field(pattern=HHMM)
    end: str = Field(pattern=HHMM)
    rate: float = Field(ge=0, le=1000)


class RuntimeSettings(BaseModel):
    automation_mode: Literal["recommend", "dry_run", "auto"] = "dry_run"
    currency: str = Field(default="INR", min_length=1, max_length=8)
    tariff_flat_rate: float = Field(default=8.0, ge=0, le=1000, description="Currency units per kWh")
    tariff_tou_enabled: bool = False
    tariff_tou_periods: list[TouPeriodModel] = Field(
        default_factory=lambda: [TouPeriodModel(name="Evening peak", start="18:00", end="22:00", rate=10.0)]
    )
    # Default grid emission factor (kg CO2 per kWh). Approximate value for the Indian grid;
    # replace with the factor published for your region.
    carbon_factor_kg_per_kwh: float = Field(default=0.71, ge=0, le=5)
    timezone: str = "Asia/Kolkata"
    default_min_vacancy_minutes: float = Field(default=10.0, ge=0.5, le=240)
    schedule_grace_minutes: float = Field(default=10.0, ge=0, le=120)
    manual_on_cooldown_minutes: float = Field(default=15.0, ge=0, le=240)
    anomaly_persistence: int = Field(default=2, ge=1, le=20)
    savings_cap_hours: float = Field(default=8.0, gt=0, le=24)
    auto_command_cooldown_minutes: float = Field(default=5.0, ge=0, le=240)

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone: {v}") from exc
        return v

    @model_validator(mode="after")
    def _tou_needs_periods(self):
        if self.tariff_tou_enabled and not self.tariff_tou_periods:
            raise ValueError("time-of-use tariff enabled but no periods configured")
        return self

    def tariff(self) -> Tariff:
        return Tariff(
            flat_rate=self.tariff_flat_rate,
            currency=self.currency,
            tou_enabled=self.tariff_tou_enabled,
            tou_periods=[TouPeriod(**p.model_dump()) for p in self.tariff_tou_periods],
            timezone=self.timezone,
        )


def load_settings(db: Session) -> RuntimeSettings:
    stored = {e.key: e.value for e in db.query(SettingEntry).all()}
    known = {k: v for k, v in stored.items() if k in RuntimeSettings.model_fields}
    try:
        return RuntimeSettings(**known)
    except ValueError:
        # Corrupt stored values must never take the system down; fall back to defaults.
        return RuntimeSettings()


def save_settings(db: Session, updates: dict, actor: str) -> RuntimeSettings:
    current = load_settings(db).model_dump()
    current.update(updates)
    validated = RuntimeSettings(**current)  # raises ValidationError on bad input
    now = utcnow()
    for key, value in validated.model_dump(mode="json").items():
        if key not in updates:
            continue
        entry = db.get(SettingEntry, key)
        if entry is None:
            db.add(SettingEntry(key=key, value=value, updated_at=now, updated_by=actor))
        else:
            entry.value = value
            entry.updated_at = now
            entry.updated_by = actor
    db.flush()
    return validated
