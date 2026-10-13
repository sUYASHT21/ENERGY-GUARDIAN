"""REST API: authentication, authorization, validation, CRUD, alerts, commands, settings."""
from app.models import Alert
from app.services import alerts as alert_service
from tests.conftest import ADMIN_PW, create_room_with_device, login, push

API = "/api/v1"


def test_health_is_public(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.json()["real_switching_enabled"] is False


def test_endpoints_require_authentication(client):
    for path in ("/rooms", "/dashboard/summary", "/alerts", "/commands", "/settings", "/ml/status", "/events"):
        assert client.get(API + path).status_code == 401, path


def test_invalid_token_rejected(client):
    r = client.get(f"{API}/rooms", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


def test_login_failure_and_rate_limit(client):
    for _ in range(8):
        assert client.post(f"{API}/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    r = client.post(f"{API}/auth/login", json={"username": "admin", "password": ADMIN_PW})
    assert r.status_code == 429


def test_roles_enforced(client, auth):
    assert client.post(f"{API}/users", json={"username": "viewer1", "password": "viewerpass1", "role": "viewer"},
                       headers=auth).status_code == 201
    assert client.post(f"{API}/users", json={"username": "op1", "password": "operatorpass1", "role": "operator"},
                       headers=auth).status_code == 201
    v = login(client, "viewer1", "viewerpass1")
    op = login(client, "op1", "operatorpass1")
    assert client.get(f"{API}/rooms", headers=v).status_code == 200
    assert client.post(f"{API}/rooms", json={"name": "X"}, headers=v).status_code == 403
    assert client.post(f"{API}/rooms", json={"name": "X"}, headers=op).status_code == 201
    assert client.put(f"{API}/settings", json={"automation_mode": "auto"}, headers=op).status_code == 403
    assert client.post(f"{API}/ml/train", json={}, headers=op).status_code == 403
    assert client.post(f"{API}/devices", json={"uid": "esp-1", "name": "E"}, headers=op).status_code == 403


def test_room_appliance_schedule_crud_and_validation(client, auth):
    r = client.post(f"{API}/rooms", json={"name": "Lab 1", "room_type": "laboratory", "min_vacancy_minutes": 5},
                    headers=auth)
    assert r.status_code == 201
    room = r.json()
    assert room["occupancy_state"] == "unknown"
    assert client.post(f"{API}/rooms", json={"name": "Lab 1"}, headers=auth).status_code == 409
    assert client.post(f"{API}/rooms", json={"name": "Bad", "room_type": "garage"}, headers=auth).status_code == 422
    assert client.post(f"{API}/rooms", json={"name": "Bad", "min_vacancy_minutes": 0}, headers=auth).status_code == 422

    dev = client.post(f"{API}/devices", json={"uid": "esp32-lab1", "name": "Lab node", "room_id": room["id"]},
                      headers=auth)
    assert dev.status_code == 201 and dev.json()["api_key"].startswith("seg_")
    dev_id = dev.json()["device"]["id"]
    assert dev.json()["device"]["source"] == "hardware"

    a = client.post(f"{API}/appliances", json={"name": "Lights", "room_id": room["id"], "device_id": dev_id,
                                               "relay_channel": 0, "rated_power_w": 200}, headers=auth)
    assert a.status_code == 201
    # duplicate relay channel on the same device
    dup = client.post(f"{API}/appliances", json={"name": "Fan", "room_id": room["id"], "device_id": dev_id,
                                                 "relay_channel": 0, "rated_power_w": 75}, headers=auth)
    assert dup.status_code == 409
    # standby threshold must be below rating
    bad = client.post(f"{API}/appliances", json={"name": "Fan", "room_id": room["id"], "rated_power_w": 10,
                                                 "standby_threshold_w": 20}, headers=auth)
    assert bad.status_code == 422

    s = client.post(f"{API}/schedules", json={"room_id": room["id"], "day_of_week": 0, "start_time": "09:00",
                                              "end_time": "11:00", "label": "Lab"}, headers=auth)
    assert s.status_code == 201
    assert client.post(f"{API}/schedules", json={"room_id": room["id"], "day_of_week": 7, "start_time": "09:00",
                                                 "end_time": "11:00"}, headers=auth).status_code == 422
    assert client.post(f"{API}/schedules", json={"room_id": room["id"], "day_of_week": 1, "start_time": "25:00",
                                                 "end_time": "11:00"}, headers=auth).status_code == 422

    detail = client.get(f"{API}/rooms/{room['id']}", headers=auth).json()
    assert len(detail["appliances"]) == 1 and len(detail["schedules"]) == 1
    assert detail["appliances"][0]["decision"]["action"] == "none"

    assert client.patch(f"{API}/appliances/{a.json()['id']}", json={"essential": True}, headers=auth).json()["essential"]
    assert client.delete(f"{API}/schedules/{s.json()['id']}", headers=auth).status_code == 204
    assert client.delete(f"{API}/rooms/{room['id']}", headers=auth).status_code == 204
    assert client.get(f"{API}/rooms/{room['id']}", headers=auth).status_code == 404


def test_validation_error_format(client, auth):
    r = client.post(f"{API}/rooms", json={"name": ""}, headers=auth)
    assert r.status_code == 422
    assert r.json()["detail"] == "validation error" and r.json()["errors"]


def test_settings_validation_and_env_locked_fields(client, auth):
    s = client.get(f"{API}/settings", headers=auth).json()
    assert s["runtime"]["automation_mode"] == "dry_run"  # safe default
    assert s["environment"]["real_switching_enabled"] is False
    r = client.put(f"{API}/settings", json={"real_switching_enabled": True}, headers=auth)
    assert r.status_code == 422  # cannot be enabled through the API
    assert client.put(f"{API}/settings", json={"tariff_flat_rate": -1}, headers=auth).status_code == 422
    assert client.put(f"{API}/settings", json={"timezone": "Mars/Base"}, headers=auth).status_code == 422
    assert client.put(f"{API}/settings", json={"automation_mode": "yolo"}, headers=auth).status_code == 422
    ok = client.put(f"{API}/settings", json={"tariff_flat_rate": 9.5, "currency": "INR"}, headers=auth)
    assert ok.status_code == 200 and ok.json()["runtime"]["tariff_flat_rate"] == 9.5
    assert client.get(f"{API}/settings", headers=auth).json()["runtime"]["tariff_flat_rate"] == 9.5


def test_alert_acknowledge_and_resolve(client, auth, ctx):
    with ctx.db.session() as db:
        a, created = alert_service.raise_alert(db, now=ctx.clock.now(), alert_type="anomaly", dedupe_key="k1",
                                               title="Test alert")
        assert created
        _, created2 = alert_service.raise_alert(db, now=ctx.clock.now(), alert_type="anomaly", dedupe_key="k1",
                                                title="Test alert")
        assert not created2  # deduplicated
        alert_id = a.id
    alerts = client.get(f"{API}/alerts", headers=auth).json()
    assert len(alerts) == 1 and alerts[0]["occurrences"] == 2
    r = client.post(f"{API}/alerts/{alert_id}/acknowledge", headers=auth)
    assert r.json()["acknowledged"] and r.json()["acknowledged_by"] == "admin"
    r = client.post(f"{API}/alerts/{alert_id}/resolve", json={"note": "fixed"}, headers=auth)
    assert r.json()["resolved"] and r.json()["resolution_note"] == "fixed"
    assert client.get(f"{API}/alerts", headers=auth).json() == []
    assert len(client.get(f"{API}/alerts?status=resolved", headers=auth).json()) == 1
    assert client.post(f"{API}/alerts/999/acknowledge", headers=auth).status_code == 404
    with ctx.db.session() as db:
        assert db.get(Alert, alert_id).resolved


def test_manual_command_on_simulated_device(client, auth, ctx):
    ids = create_room_with_device(ctx)
    push(ctx, ids["device_id"], occupied=True, powers=[300.0])
    r = client.post(f"{API}/commands", json={"appliance_id": ids["appliance_ids"][0], "action": "off"}, headers=auth)
    assert r.status_code == 201
    c = r.json()
    assert c["status"] == "pending" and c["mode"] == "simulated" and c["expires_at"]
    # a second command while the first is pending is blocked
    r2 = client.post(f"{API}/commands", json={"appliance_id": ids["appliance_ids"][0], "action": "on"}, headers=auth)
    assert r2.json()["status"] == "blocked" and "pending" in r2.json()["error"]


def test_manual_command_blocked_when_device_offline(client, auth, ctx):
    ids = create_room_with_device(ctx)  # never reported -> never_seen
    r = client.post(f"{API}/commands", json={"appliance_id": ids["appliance_ids"][0], "action": "off"}, headers=auth)
    assert r.json()["status"] == "blocked" and "never_seen" in r.json()["error"]


def test_hardware_command_blocked_while_real_switching_disabled(client, auth, ctx):
    ids = create_room_with_device(ctx, kind="esp32", uid="esp-hw", validated=True)
    push(ctx, ids["device_id"], occupied=True, powers=[300.0])
    r = client.post(f"{API}/commands", json={"appliance_id": ids["appliance_ids"][0], "action": "off"}, headers=auth)
    assert r.json()["status"] == "blocked" and "REAL_SWITCHING_ENABLED" in r.json()["error"]
    # dry-run is always allowed and never sent
    r = client.post(f"{API}/commands", json={"appliance_id": ids["appliance_ids"][0], "action": "off", "dry_run": True},
                    headers=auth)
    assert r.json()["status"] == "dry_run"


def test_essential_load_requires_admin_confirmation(client, auth, ctx):
    ids = create_room_with_device(ctx, appliances=(("Server", "server", 400.0, True),))
    push(ctx, ids["device_id"], occupied=True, powers=[300.0])
    aid = ids["appliance_ids"][0]
    r = client.post(f"{API}/commands", json={"appliance_id": aid, "action": "off"}, headers=auth)
    assert r.json()["status"] == "blocked" and "essential" in r.json()["error"]
    r = client.post(f"{API}/commands", json={"appliance_id": aid, "action": "off", "confirm_essential": True},
                    headers=auth)
    assert r.json()["status"] == "pending"


def test_room_override(client, auth, ctx):
    ids = create_room_with_device(ctx)
    r = client.post(f"{API}/rooms/{ids['room_id']}/override", json={"enabled": True, "minutes": 30, "reason": "exam"},
                    headers=auth)
    assert r.json()["manual_override"] and r.json()["override_until"]
    events = client.get(f"{API}/events?category=override", headers=auth).json()
    assert events and "ENABLED" in events[0]["message"]


def test_dashboard_endpoints(client, auth, ctx, clock):
    ids = create_room_with_device(ctx)
    for _ in range(3):
        push(ctx, ids["device_id"], occupied=True, powers=[360.0])
        clock.advance(10)
    s = client.get(f"{API}/dashboard/summary", headers=auth).json()
    assert s["energy_today_kwh"] > 0 and s["currency"] == "INR"
    assert s["data_sources_live"] == ["simulation"]
    assert "ESTIMATE" in s["estimated_savings"]["label"]
    h = client.get(f"{API}/dashboard/history?range=24h", headers=auth).json()
    assert h["group"] == "hour" and sum(p["energy_kwh"] for p in h["series"]) > 0
    assert client.get(f"{API}/dashboard/history?range=1y", headers=auth).status_code == 422
    assert client.get(f"{API}/dashboard/live-power?minutes=5", headers=auth).json()
    ov = client.get(f"{API}/dashboard/overview", headers=auth).json()
    assert ov[0]["appliances"][0]["state"] == "on"
    assert client.get(f"{API}/telemetry?minutes=5", headers=auth).json()
