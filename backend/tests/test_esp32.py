"""ESP32 device HTTP protocol: auth, telemetry formats, command delivery, ack, timeout."""
from app.models import Alert, Appliance, Command, Device
from app.services import commands as command_service
from app.services import monitor
from tests.conftest import DEVICE_KEY, create_room_with_device

API = "/api/v1/esp32"


def dev_headers(uid="esp-1", key=DEVICE_KEY):
    return {"X-Device-Id": uid, "X-Device-Key": key}


def test_device_auth(client, ctx):
    create_room_with_device(ctx, kind="esp32", uid="esp-1")
    assert client.get(f"{API}/commands").status_code == 422  # headers missing
    assert client.get(f"{API}/commands", headers=dev_headers(key="wrong")).status_code == 401
    assert client.get(f"{API}/commands", headers=dev_headers(uid="nope")).status_code == 401
    assert client.get(f"{API}/commands", headers=dev_headers()).status_code == 200


def test_simulated_devices_cannot_use_hardware_api(client, ctx):
    create_room_with_device(ctx, kind="simulated", uid="sim-x")
    assert client.get(f"{API}/commands", headers=dev_headers(uid="sim-x")).status_code == 403


def test_telemetry_seg_v1_labelled_hardware(client, ctx):
    ids = create_room_with_device(ctx, kind="esp32", uid="esp-1")
    body = {"format": "seg.v1", "occupancy": {"occupied": True, "people_count": 4},
            "readings": [{"channel": 0, "power_w": 350.5, "voltage_v": 231.0, "current_a": 1.6, "relay_on": True}],
            "health": {"firmware": "1.0.0", "rssi_dbm": -60, "uptime_s": 100, "free_heap": 150000}}
    r = client.post(f"{API}/telemetry", json=body, headers=dev_headers())
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 1 and r.json()["commands"] == []
    assert r.json()["used_server_time"] is True  # no ts -> server time
    with ctx.db.session() as db:
        a = db.get(Appliance, ids["appliance_ids"][0])
        d = db.get(Device, ids["device_id"])
        assert a.last_source == "hardware" and a.state == "on" and a.last_power_w == 350.5
        assert d.connection_status == "online" and d.firmware_version == "1.0.0" and d.rssi_dbm == -60


def test_telemetry_compact_format(client, ctx):
    ids = create_room_with_device(ctx, kind="emulator", uid="esp-1")
    body = {"format": "compact.v1", "occ": 0, "sok": 1, "ch": [[0, 120.0, 230.0, 0.55, 1]], "fw": "1.1", "rssi": -70}
    r = client.post(f"{API}/telemetry", json=body, headers=dev_headers())
    assert r.status_code == 200 and r.json()["accepted"] == 1
    with ctx.db.session() as db:
        assert db.get(Appliance, ids["appliance_ids"][0]).last_source == "emulator"


def test_invalid_payloads_rejected(client, ctx):
    create_room_with_device(ctx, kind="esp32", uid="esp-1")
    bad = [
        {"readings": [{"channel": 0, "power_w": -5}]},
        {"readings": [{"channel": 99, "power_w": 5}]},
        {"readings": [{"channel": 0, "power_w": 5, "voltage_v": 9000}]},
        {"format": "unknown.v9"},
        {"format": "compact.v1", "ch": [[0]]},
    ]
    for body in bad:
        assert client.post(f"{API}/telemetry", json=body, headers=dev_headers()).status_code == 422, body


def _online_esp(client, ctx, kind="emulator"):
    ids = create_room_with_device(ctx, kind=kind, uid="esp-1")
    client.post(f"{API}/telemetry", json={"occupancy": {"occupied": False},
                                          "readings": [{"channel": 0, "power_w": 380, "relay_on": True}]},
                headers=dev_headers())
    return ids


def test_command_delivery_and_ack(client, ctx, clock):
    ids = _online_esp(client, ctx)
    with ctx.db.session() as db:
        cmd = command_service.create_command(ctx, db, db.get(Appliance, ids["appliance_ids"][0]), "off",
                                             origin="manual", actor="admin")
        cid = cmd.id
        assert cmd.status == "pending" and cmd.mode == "emulator"
    r = client.get(f"{API}/commands", headers=dev_headers()).json()
    assert r["commands"][0]["command_id"] == cid and r["commands"][0]["channel"] == 0
    assert r["commands"][0]["action"] == "off"
    with ctx.db.session() as db:
        assert db.get(Command, cid).status == "sent"
    # re-delivered until acknowledged (idempotent on/off)
    assert client.get(f"{API}/commands", headers=dev_headers()).json()["commands"][0]["command_id"] == cid
    clock.advance(1)
    r = client.post(f"{API}/commands/{cid}/ack", json={"success": True, "relay_on": False}, headers=dev_headers())
    assert r.json()["status"] == "acknowledged"
    with ctx.db.session() as db:
        assert db.get(Appliance, ids["appliance_ids"][0]).state == "off"
    assert client.get(f"{API}/commands", headers=dev_headers()).json()["commands"] == []
    # duplicate ack is idempotent
    r = client.post(f"{API}/commands/{cid}/ack", json={"success": False}, headers=dev_headers())
    assert r.json()["status"] == "acknowledged"


def test_failed_ack_raises_alert(client, ctx):
    ids = _online_esp(client, ctx)
    with ctx.db.session() as db:
        cid = command_service.create_command(ctx, db, db.get(Appliance, ids["appliance_ids"][0]), "off",
                                             origin="manual", actor="admin").id
    r = client.post(f"{API}/commands/{cid}/ack", json={"success": False, "relay_on": True, "error": "relay stuck"},
                    headers=dev_headers())
    assert r.json()["status"] == "failed"
    with ctx.db.session() as db:
        a = db.query(Alert).filter(Alert.alert_type == "command_failed").one()
        assert "relay stuck" in a.message


def test_ack_for_other_device_rejected(client, ctx):
    ids = _online_esp(client, ctx)
    with ctx.db.session() as db:
        cid = command_service.create_command(ctx, db, db.get(Appliance, ids["appliance_ids"][0]), "off",
                                             origin="manual", actor="admin").id
    create_room_with_device(ctx, kind="emulator", uid="esp-2", room_name="Room B")
    r = client.post(f"{API}/commands/{cid}/ack", json={"success": True}, headers=dev_headers(uid="esp-2"))
    assert r.status_code == 404


def test_command_timeout(client, ctx, clock):
    ids = _online_esp(client, ctx)
    with ctx.db.session() as db:
        cid = command_service.create_command(ctx, db, db.get(Appliance, ids["appliance_ids"][0]), "off",
                                             origin="manual", actor="admin").id
    clock.advance(ctx.settings.command_timeout_seconds + 1)
    monitor.run_once(ctx)
    with ctx.db.session() as db:
        assert db.get(Command, cid).status == "timeout"
        assert db.query(Alert).filter(Alert.alert_type == "command_timeout").count() == 1
    # late ack does not overwrite the timeout
    r = client.post(f"{API}/commands/{cid}/ack", json={"success": True, "relay_on": False}, headers=dev_headers())
    assert r.json()["status"] == "timeout"


def test_device_goes_offline_and_recovers(client, ctx, clock):
    ids = _online_esp(client, ctx)
    clock.advance(ctx.settings.device_offline_seconds + 1)
    monitor.run_once(ctx)
    with ctx.db.session() as db:
        assert db.get(Device, ids["device_id"]).connection_status == "offline"
        assert db.get(Appliance, ids["appliance_ids"][0]).state == "unknown"
        assert db.query(Alert).filter(Alert.alert_type == "device_offline", Alert.resolved.is_(False)).count() == 1
    client.post(f"{API}/heartbeat", json={"firmware": "1.0.1"}, headers=dev_headers())
    with ctx.db.session() as db:
        assert db.get(Device, ids["device_id"]).connection_status == "online"
        assert db.query(Alert).filter(Alert.alert_type == "device_offline", Alert.resolved.is_(False)).count() == 0


def test_device_config(client, ctx):
    create_room_with_device(ctx, kind="esp32", uid="esp-1")
    cfg = client.get(f"{API}/config", headers=dev_headers()).json()
    assert cfg["channels"][0]["channel"] == 0 and "api_key" not in str(cfg)
