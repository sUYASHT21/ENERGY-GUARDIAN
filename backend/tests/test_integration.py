"""End-to-end flows through telemetry -> energy -> decision engine -> alerts -> commands -> savings,
including every simulator scenario. Time is driven by a FakeClock, so results are deterministic."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.models import Alert, Appliance, Command, Device, Room, SavingsRecord, Schedule
from app.services import commands as command_service
from app.services import monitor
from tests.conftest import create_room_with_device, login, make_settings, push

API = "/api/v1"


def _cycle(ctx, clock, device_id, *, occupied, powers, seconds=5, n=1):
    for _ in range(n):
        push(ctx, device_id, occupied=occupied, powers=powers)
        monitor.run_once(ctx)
        clock.advance(seconds)


def _alerts(ctx, alert_type, open_only=True):
    with ctx.db.session() as db:
        q = db.query(Alert).filter(Alert.alert_type == alert_type)
        if open_only:
            q = q.filter(Alert.resolved.is_(False))
        return q.all()


def _commands(ctx, **filters):
    with ctx.db.session() as db:
        q = db.query(Command)
        for k, v in filters.items():
            q = q.filter(getattr(Command, k) == v)
        return q.order_by(Command.id).all()


def test_full_waste_flow_dry_run_then_auto_with_savings(client, auth, ctx, clock):
    ids = create_room_with_device(ctx, min_vacancy=1.0, appliances=(("AC", "ac", 1500.0, False),))
    aid = ids["appliance_ids"][0]
    # Occupied: no waste
    _cycle(ctx, clock, ids["device_id"], occupied=True, powers=[1200.0], n=3)
    assert _alerts(ctx, "vacant_room_waste") == []
    # Vacant but below min vacancy time: still nothing
    _cycle(ctx, clock, ids["device_id"], occupied=False, powers=[1200.0], n=6)
    assert _alerts(ctx, "vacant_room_waste") == []
    # After > 1 minute vacant: waste alert + exactly one dry-run command (no repeats)
    _cycle(ctx, clock, ids["device_id"], occupied=False, powers=[1200.0], n=12)
    assert len(_alerts(ctx, "vacant_room_waste")) == 1
    dry = _commands(ctx, status="dry_run")
    assert len(dry) == 1 and dry[0].origin == "automation" and dry[0].decision["action"] == "auto_shutdown"
    assert _commands(ctx, status="pending") == []  # nothing was sent in dry-run

    # Switch to auto: a simulated command is queued
    assert client.put(f"{API}/settings", json={"automation_mode": "auto"}, headers=auth).status_code == 200
    _cycle(ctx, clock, ids["device_id"], occupied=False, powers=[1200.0])
    pending = _commands(ctx, status="pending")
    assert len(pending) == 1 and pending[0].mode == "simulated"
    # The (virtual) device fetches and acknowledges it
    with ctx.db.session() as db:
        dev = db.get(Device, ids["device_id"])
        delivered = command_service.fetch_pending(ctx, db, dev)
        assert delivered[0]["action"] == "off"
        command_service.acknowledge(ctx, db, dev, delivered[0]["command_id"], success=True, relay_on=False)
    with ctx.db.session() as db:
        assert db.get(Appliance, aid).state == "off"
        rec = db.query(SavingsRecord).one()
        assert rec.baseline_power_w == pytest.approx(1200.0) and rec.ended_at is None
    # Appliance stays off for 1 hour in the vacant room
    _cycle(ctx, clock, ids["device_id"], occupied=False, powers=[0.0], seconds=60, n=60)
    assert _alerts(ctx, "vacant_room_waste") == []  # resolved once the load is off
    s = client.get(f"{API}/dashboard/summary", headers=auth).json()
    # ~1.2 kW avoided for ~1 h (+ the few seconds of the first cycle)
    assert s["estimated_savings"]["total_kwh"] == pytest.approx(1.2, rel=0.03)
    assert s["estimated_savings"]["total_cost"] == pytest.approx(1.2 * 8.0, rel=0.03)
    assert s["estimated_savings"]["by_source"] == {"simulation": pytest.approx(1.2, rel=0.03)}
    # Re-occupancy closes the savings episode
    _cycle(ctx, clock, ids["device_id"], occupied=True, powers=[0.0])
    with ctx.db.session() as db:
        assert db.query(SavingsRecord).one().end_reason == "room_reoccupied"


def test_active_schedule_blocks_automatic_shutdown(client, auth, ctx, clock):
    ids = create_room_with_device(ctx, min_vacancy=1.0)
    # FakeClock: Monday 09:00 UTC = 14:30 Asia/Kolkata
    with ctx.db.session() as db:
        db.add(Schedule(room_id=ids["room_id"], day_of_week=0, start_time="14:00", end_time="16:00", label="Lecture"))
    client.put(f"{API}/settings", json={"automation_mode": "auto"}, headers=auth)
    _cycle(ctx, clock, ids["device_id"], occupied=False, powers=[380.0], n=20)
    alerts = _alerts(ctx, "vacant_room_waste")
    assert len(alerts) == 1
    assert "no_active_schedule" in alerts[0].details["decision"]["blockers"]
    assert _commands(ctx) == []  # recommendation only


def test_manual_override_blocks_automation(client, auth, ctx, clock):
    ids = create_room_with_device(ctx, min_vacancy=1.0)
    client.put(f"{API}/settings", json={"automation_mode": "auto"}, headers=auth)
    client.post(f"{API}/rooms/{ids['room_id']}/override", json={"enabled": True, "minutes": 60}, headers=auth)
    _cycle(ctx, clock, ids["device_id"], occupied=False, powers=[380.0], n=20)
    assert _commands(ctx) == []
    assert "no_room_override" in _alerts(ctx, "vacant_room_waste")[0].details["decision"]["blockers"]


def test_stale_data_prevents_shutdown(client, auth, ctx, clock):
    ids = create_room_with_device(ctx, min_vacancy=1.0)
    client.put(f"{API}/settings", json={"automation_mode": "auto"}, headers=auth)
    _cycle(ctx, clock, ids["device_id"], occupied=False, powers=[380.0], n=5)
    clock.advance(minutes=2)  # device silent: data stale, then device offline
    monitor.run_once(ctx)
    assert _commands(ctx) == []
    with ctx.db.session() as db:
        assert db.get(Room, ids["room_id"]).occupancy_state == "unknown"
    d = ctx.decisions[ids["appliance_ids"][0]]
    assert d["action"] == "none" and not d["data_ok"]
    assert len(_alerts(ctx, "device_offline")) == 1


def test_websocket_requires_token_and_streams(client, auth):
    token = auth["Authorization"].split()[1]
    with client.websocket_connect(f"/ws?token={token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "summary" and "live_power_w" in msg["data"]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=bad") as ws:
            ws.receive_json()


# ---------------------------------------------------------------------------
# Simulator scenarios on the seeded demo campus
# ---------------------------------------------------------------------------
@pytest.fixture
def demo(tmp_path, clock):
    settings = make_settings(tmp_path, seed_demo_data=True, history_backfill_days=1, ml_autotrain=True,
                             simulation_tick_seconds=3)
    app = create_app(settings, clock)
    with TestClient(app) as c:
        yield app.state.ctx, c, login(c)


def _run(ctx, clock, seconds):
    for _ in range(int(seconds / 3)):
        ctx.simulator.tick()
        monitor.run_once(ctx)
        clock.advance(3)


def _room_id(ctx, prefix):
    with ctx.db.session() as db:
        return db.query(Room).filter(Room.name.startswith(prefix)).one().id


def test_demo_campus_seeded_with_history_and_model(demo):
    ctx, c, auth = demo
    assert ctx.anomaly.method == "isolation_forest"
    status = c.get(f"{API}/ml/status", headers=auth).json()
    assert status["active_model"]["metrics"]["roc_auc"] > 0.9 and "SYNTHETIC" in status["disclaimer"]
    hist = c.get(f"{API}/dashboard/history?range=24h", headers=auth).json()
    assert sum(p["simulation_kwh"] for p in hist["series"]) > 0
    assert sum(p["hardware_kwh"] for p in hist["series"]) == 0  # simulated history is labelled as such


def test_scenarios_end_to_end(demo, clock):
    ctx, c, auth = demo
    sim = ctx.simulator
    _run(ctx, clock, 90)  # CR-102 starts in vacant_waste, LAB-202 in anomaly

    # vacant waste -> dry-run (default mode)
    cr102 = _room_id(ctx, "CR-102")
    waste = [a for a in _alerts(ctx, "vacant_room_waste") if a.room_id == cr102]
    assert waste, "expected waste alerts in CR-102"
    assert _commands(ctx, status="dry_run")
    assert not _commands(ctx, mode="simulated")

    # anomaly scenario -> ML anomaly alert on LAB-202
    lab202 = _room_id(ctx, "LAB-202")
    assert any(a.room_id == lab202 for a in _alerts(ctx, "anomaly"))

    # auto mode -> simulated commands acknowledged, savings start
    c.put(f"{API}/settings", json={"automation_mode": "auto"}, headers=auth)
    _run(ctx, clock, 15)
    acked = _commands(ctx, status="acknowledged")
    assert acked and all(cmd.mode == "simulated" for cmd in acked)
    _run(ctx, clock, 60)
    assert c.get(f"{API}/dashboard/summary", headers=auth).json()["estimated_savings"]["total_kwh"] > 0

    # NOTE: the fake clock is Monday 14:30 Asia/Kolkata, when CR-101 and LAB-201 have scheduled sessions
    # (automation correctly blocked there), so scenarios needing automatic commands use other rooms.

    # sensor failure -> occupancy unknown, critical alert, automation blocked
    lab201 = _room_id(ctx, "LAB-201")
    sim.set_scenario(lab201, "sensor_failure")
    _run(ctx, clock, 9)
    assert any(a.room_id == lab201 for a in _alerts(ctx, "sensor_failure"))
    with ctx.db.session() as db:
        lab201_apps = [a.id for a in db.query(Appliance).filter(Appliance.room_id == lab201)]
    assert all("occupancy_known" in ctx.decisions[a]["blockers"] for a in lab201_apps)

    # command failure -> failed ack alert
    lab202 = _room_id(ctx, "LAB-202")
    sim.set_scenario(lab202, "command_failure")
    _run(ctx, clock, 90)
    assert _commands(ctx, status="failed")
    assert any(a.room_id == lab202 for a in _alerts(ctx, "command_failed"))

    # command timeout -> timeout alert
    hst = _room_id(ctx, "HST-A12")
    sim.set_scenario(hst, "command_timeout")
    _run(ctx, clock, 90 + ctx.settings.command_timeout_seconds)
    assert any(a.room_id == hst for a in _alerts(ctx, "command_timeout"))

    # offline -> device offline alert, appliances unknown, no new commands for that room
    cr101 = _room_id(ctx, "CR-101")
    sim.set_scenario(cr101, "offline")
    _run(ctx, clock, ctx.settings.device_offline_seconds + 6)
    assert any(a.room_id == cr101 for a in _alerts(ctx, "device_offline"))
    with ctx.db.session() as db:
        apps = db.query(Appliance).filter(Appliance.room_id == cr101).all()
        assert all(a.state == "unknown" for a in apps)
        n_before = db.query(Command).filter(Command.appliance_id.in_([a.id for a in apps])).count()
    _run(ctx, clock, 30)
    with ctx.db.session() as db:
        assert db.query(Command).filter(Command.appliance_id.in_([a.id for a in apps])).count() == n_before

    # Global safety invariants over the whole run
    with ctx.db.session() as db:
        essential_ids = {a.id for a in db.query(Appliance).filter(Appliance.essential.is_(True))}
        manual_only = {a.id for a in db.query(Appliance).filter(Appliance.auto_off_allowed.is_(False))}
        auto_cmds = db.query(Command).filter(Command.origin == "automation").all()
    assert auto_cmds
    assert not [cmd for cmd in auto_cmds if cmd.appliance_id in essential_ids], "essential load was switched"
    assert not [cmd for cmd in auto_cmds if cmd.appliance_id in manual_only], "manual-only load was switched"
    assert not [cmd for cmd in auto_cmds if cmd.mode == "hardware"], "hardware command without enablement"

    # reset restores scenarios
    sim.reset()
    status = c.get(f"{API}/simulation", headers=auth).json()
    assert {r["room"].split()[0]: r["scenario"] for r in status["rooms"]}["CR-102"] == "vacant_waste"


def test_simulation_api(demo):
    ctx, c, auth = demo
    s = c.get(f"{API}/simulation", headers=auth).json()
    assert s["enabled"] and "vacant_waste" in s["scenarios"]
    rid = s["rooms"][0]["room_id"]
    url = f"{API}/simulation/scenario"
    assert c.post(url, json={"room_id": rid, "scenario": "bogus"}, headers=auth).status_code == 422
    assert c.post(url, json={"room_id": 9999, "scenario": "normal"}, headers=auth).status_code == 404
    r = c.post(f"{API}/simulation/scenario", json={"room_id": rid, "scenario": "offline"}, headers=auth)
    assert next(x for x in r.json()["rooms"] if x["room_id"] == rid)["scenario"] == "offline"
    assert c.post(f"{API}/simulation/tick?steps=2", headers=auth).json()["tick"] == 2


def test_ml_train_endpoint(demo):
    ctx, c, auth = demo
    r = c.post(f"{API}/ml/train", json={"seed": 7}, headers=auth)
    assert r.status_code == 200 and r.json()["active"] and r.json()["params"]["seed"] == 7
    st = c.get(f"{API}/ml/status", headers=auth).json()
    assert st["model_version"] == r.json()["version"] and len(st["models"]) == 2
    first = [m for m in st["models"] if m["id"] != r.json()["id"]][0]
    assert c.post(f"{API}/ml/models/{first['id']}/activate", headers=auth).json()["active"]


def test_late_vacancy_timer_restarts_after_unknown(ctx, clock):
    """Unknown occupancy resets the vacancy timer — vacancy must be re-established."""
    ids = create_room_with_device(ctx, min_vacancy=1.0)
    _cycle(ctx, clock, ids["device_id"], occupied=False, powers=[380.0], n=10)
    push(ctx, ids["device_id"], occupied=None, sensor_ok=False, powers=[380.0])
    clock.advance(5)
    push(ctx, ids["device_id"], occupied=False, powers=[380.0])
    with ctx.db.session() as db:
        assert db.get(Room, ids["room_id"]).vacant_since == clock.now()
