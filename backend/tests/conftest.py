from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.telemetry_parsers import OccupancyIn, ReadingIn, TelemetryPayload
from app.clock import FakeClock
from app.config import Settings
from app.main import create_app
from app.models import Appliance, Device, Room
from app.security import hash_device_key
from app.services import telemetry as telemetry_service

ADMIN_PW = "test-admin-password"


def make_settings(tmp_path: Path, **overrides) -> Settings:
    base = dict(
        app_env="test", database_url=f"sqlite:///{tmp_path / 'test.db'}", model_dir=tmp_path / "models",
        secret_key="x" * 40, admin_password=ADMIN_PW, background_tasks_enabled=False, simulation_autostart=False,
        seed_demo_data=False, history_backfill_days=0, ml_autotrain=False, log_level="WARNING",
        command_timeout_seconds=20, device_offline_seconds=30, telemetry_stale_seconds=45,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def app(settings, clock):
    return create_app(settings, clock)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def ctx(app, client):  # client fixture triggers lifespan/bootstrap
    return app.state.ctx


def login(client: TestClient, username="admin", password=ADMIN_PW) -> dict:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client) -> dict:
    return login(client)


DEVICE_KEY = "seg_test_device_key_0123456789"


def create_room_with_device(ctx, *, kind="simulated", uid="node-1", room_name="Room A", min_vacancy=10.0,
                            appliances=(("Lights", "light", 400.0, False),), validated=False):
    """Create a room, a device and appliances directly in the DB. Returns ids."""
    with ctx.db.session() as db:
        room = Room(name=room_name, room_type="classroom", min_vacancy_minutes=min_vacancy)
        db.add(room)
        db.flush()
        dev = Device(uid=uid, name=f"Node {uid}", kind=kind, room_id=room.id, api_key_hash=hash_device_key(DEVICE_KEY),
                     has_occupancy_sensor=True, control_validated=validated)
        db.add(dev)
        db.flush()
        ids = []
        for ch, (name, atype, watts, essential) in enumerate(appliances):
            a = Appliance(name=name, appliance_type=atype, room_id=room.id, device_id=dev.id, relay_channel=ch,
                          rated_power_w=watts, standby_threshold_w=5.0, essential=essential)
            db.add(a)
            db.flush()
            ids.append(a.id)
        return {"room_id": room.id, "device_id": dev.id, "appliance_ids": ids}


def push(ctx, device_id: int, *, occupied: bool | None, powers: list[float], relay: list[bool] | None = None,
         sensor_ok: bool = True, voltage: float = 230.0):
    """Ingest one telemetry payload at the current fake-clock time."""
    relay = relay if relay is not None else [p > 5 for p in powers]
    with ctx.db.session() as db:
        dev = db.get(Device, device_id)
        payload = TelemetryPayload(
            ts=ctx.clock.now(),
            occupancy=OccupancyIn(occupied=occupied, sensor_ok=sensor_ok),
            readings=[ReadingIn(channel=i, power_w=p, voltage_v=voltage, current_a=p / (voltage * 0.95) if p else 0,
                                relay_on=r) for i, (p, r) in enumerate(zip(powers, relay, strict=False))])
        return telemetry_service.ingest(ctx, db, dev, payload)
