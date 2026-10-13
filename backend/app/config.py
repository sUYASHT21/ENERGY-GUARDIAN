"""Application configuration loaded from environment variables / .env file.

Security-sensitive switches (real hardware switching, secrets) are *only* configurable
through the environment, never through the runtime settings API.
"""
from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = BACKEND_DIR / "data"

INSECURE_DEFAULT_SECRET = "dev-insecure-secret-change-me"
INSECURE_DEFAULT_PASSWORD = "guardian-demo"

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"
    app_name: str = "Smart Energy Guardian"
    log_level: str = "INFO"

    database_url: str = f"sqlite:///{DEFAULT_DATA_DIR / 'energy_guardian.db'}"
    model_dir: Path = DEFAULT_DATA_DIR / "models"

    # --- Security -------------------------------------------------------------
    secret_key: str = INSECURE_DEFAULT_SECRET
    access_token_minutes: int = Field(default=720, ge=5, le=60 * 24 * 7)
    admin_username: str = "admin"
    admin_password: str = INSECURE_DEFAULT_PASSWORD
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080"

    # --- Hardware safety --------------------------------------------------------
    # Master switch for sending commands to *physical* ESP32 relays. Off by default.
    real_switching_enabled: bool = False

    # --- Timing ---------------------------------------------------------------
    command_timeout_seconds: int = Field(default=20, ge=2, le=600)
    device_offline_seconds: int = Field(default=30, ge=5, le=3600)
    telemetry_stale_seconds: int = Field(default=45, ge=5, le=3600)
    monitor_interval_seconds: float = Field(default=3.0, gt=0, le=60)
    # Largest gap between two readings that is still integrated into kWh.
    max_integration_gap_seconds: int = Field(default=300, ge=5, le=3600)

    # --- Simulation -------------------------------------------------------------
    simulation_enabled: bool = True
    simulation_autostart: bool = True
    simulation_tick_seconds: float = Field(default=3.0, gt=0, le=60)
    seed_demo_data: bool = True
    history_backfill_days: int = Field(default=7, ge=0, le=60)
    simulation_seed: int = 42

    # --- Background work --------------------------------------------------------
    background_tasks_enabled: bool = True
    ml_autotrain: bool = True

    @field_validator("model_dir", mode="before")
    @classmethod
    def _expand_path(cls, v):  # noqa: N805
        return Path(v).expanduser()

    @model_validator(mode="after")
    def _check_security(self) -> Settings:
        if self.app_env == "production":
            if self.secret_key == INSECURE_DEFAULT_SECRET or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be set to a random value of >= 32 chars in production")
            if self.admin_password == INSECURE_DEFAULT_PASSWORD or len(self.admin_password) < 10:
                raise ValueError("ADMIN_PASSWORD must be changed (>= 10 chars) in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def using_insecure_defaults(self) -> bool:
        return self.secret_key == INSECURE_DEFAULT_SECRET or self.admin_password == INSECURE_DEFAULT_PASSWORD


@lru_cache
def get_settings() -> Settings:
    return Settings()


def generate_secret() -> str:
    return secrets.token_urlsafe(48)
