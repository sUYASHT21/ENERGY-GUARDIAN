"""Telemetry ingestion: energy accounting, occupancy state, anomaly persistence."""
from datetime import timedelta

import pytest

from app.models import Alert, Appliance, Device, EnergyRecord, Room, TelemetryReading
from tests.conftest import create_room_with_device, push


def _energy(ctx, appliance_id):
    with ctx.db.session() as db:
        recs = db.query(EnergyRecord).filter(EnergyRecord.appliance_id == appliance_id).all()
        return sum(r.energy_kwh for r in recs), sum(r.wasted_kwh for r in recs), sum(r.cost for r in recs)


def test_constant_load_for_one_hour_yields_exact_kwh_and_cost(ctx, clock):
    ids = create_room_with_device(ctx, appliances=(("Heater", "heater", 2000.0, False),))
    for _ in range(361):  # 1000 W every 10 s for exactly one hour
        push(ctx, ids["device_id"], occupied=True, powers=[1000.0])
        clock.advance(10)
    kwh, wasted, cost = _energy(ctx, ids["appliance_ids"][0])
    assert kwh == pytest.approx(1.0, rel=1e-9)
    assert wasted == 0
    assert cost == pytest.approx(8.0)  # default flat tariff 8.0/kWh


def test_energy_split_into_15_minute_buckets(ctx, clock):
    ids = create_room_with_device(ctx)
    clock.set(clock.now().replace(minute=13, second=0))
    push(ctx, ids["device_id"], occupied=True, powers=[600.0])
    clock.advance(minutes=4)  # 09:13 -> 09:17 crosses the 09:15 bucket boundary
    push(ctx, ids["device_id"], occupied=True, powers=[600.0])
    with ctx.db.session() as db:
        recs = sorted(db.query(EnergyRecord).all(), key=lambda r: r.period_start)
    assert len(recs) == 2
    assert recs[0].energy_kwh == pytest.approx(0.02)  # 600 W * 2 min
    assert recs[1].energy_kwh == pytest.approx(0.02)


def test_gap_longer_than_limit_is_not_integrated(ctx, clock):
    ids = create_room_with_device(ctx)
    push(ctx, ids["device_id"], occupied=True, powers=[1000.0])
    clock.advance(seconds=ctx.settings.max_integration_gap_seconds + 1)
    push(ctx, ids["device_id"], occupied=True, powers=[1000.0])
    assert _energy(ctx, ids["appliance_ids"][0])[0] == 0


def test_energy_in_vacant_room_counts_as_waste_except_essential(ctx, clock):
    ids = create_room_with_device(ctx, appliances=(("Light", "light", 400.0, False),
                                                   ("Fridge", "refrigerator", 300.0, True)))
    push(ctx, ids["device_id"], occupied=False, powers=[360.0, 150.0])
    clock.advance(seconds=60)
    push(ctx, ids["device_id"], occupied=False, powers=[360.0, 150.0])
    light_kwh, light_waste, _ = _energy(ctx, ids["appliance_ids"][0])
    fridge_kwh, fridge_waste, _ = _energy(ctx, ids["appliance_ids"][1])
    assert light_waste == pytest.approx(light_kwh) and light_kwh == pytest.approx(0.006)
    assert fridge_waste == 0 and fridge_kwh > 0


def test_out_of_order_readings_are_skipped(ctx, clock):
    ids = create_room_with_device(ctx)
    push(ctx, ids["device_id"], occupied=True, powers=[100.0])
    clock.advance(-5)
    res = push(ctx, ids["device_id"], occupied=True, powers=[100.0])
    assert res.skipped == 1 and res.accepted == 0


def test_device_clock_skew_falls_back_to_server_time(ctx, clock):
    from app.adapters.telemetry_parsers import ReadingIn, TelemetryPayload
    from app.services import telemetry
    ids = create_room_with_device(ctx)
    with ctx.db.session() as db:
        dev = db.get(Device, ids["device_id"])
        res = telemetry.ingest(ctx, db, dev, TelemetryPayload(ts=clock.now() - timedelta(days=3),
                                                              readings=[ReadingIn(channel=0, power_w=50)]))
    assert res.used_server_time
    with ctx.db.session() as db:
        assert db.query(TelemetryReading).one().ts == clock.now()


def test_occupancy_transitions_and_vacant_since(ctx, clock):
    ids = create_room_with_device(ctx)
    push(ctx, ids["device_id"], occupied=True, powers=[100.0])
    clock.advance(30)
    t_vacant = clock.now()
    push(ctx, ids["device_id"], occupied=False, powers=[100.0])
    clock.advance(30)
    push(ctx, ids["device_id"], occupied=False, powers=[100.0])
    with ctx.db.session() as db:
        room = db.get(Room, ids["room_id"])
        assert room.occupancy_state == "vacant" and room.vacant_since == t_vacant
    push(ctx, ids["device_id"], occupied=True, powers=[100.0])
    with ctx.db.session() as db:
        room = db.get(Room, ids["room_id"])
        assert room.occupancy_state == "occupied" and room.vacant_since is None


def test_sensor_failure_sets_unknown_and_raises_alert(ctx, clock):
    ids = create_room_with_device(ctx)
    push(ctx, ids["device_id"], occupied=None, sensor_ok=False, powers=[100.0])
    with ctx.db.session() as db:
        assert db.get(Room, ids["room_id"]).occupancy_state == "unknown"
        assert db.get(Device, ids["device_id"]).sensor_status == "fault"
        alert = db.query(Alert).filter(Alert.alert_type == "sensor_failure").one()
        assert alert.severity == "critical" and not alert.resolved
    clock.advance(5)
    push(ctx, ids["device_id"], occupied=True, powers=[100.0])
    with ctx.db.session() as db:
        assert db.query(Alert).filter(Alert.alert_type == "sensor_failure").one().resolved


def test_anomaly_alert_requires_persistence_and_clears(ctx, clock):
    ids = create_room_with_device(ctx, appliances=(("AC", "ac", 1000.0, False),))
    aid = ids["appliance_ids"][0]
    push(ctx, ids["device_id"], occupied=True, powers=[900.0])
    clock.advance(5)
    push(ctx, ids["device_id"], occupied=True, powers=[2900.0])  # 1st anomalous reading (rules: >1.4x rated)
    with ctx.db.session() as db:
        assert db.query(Alert).filter(Alert.alert_type == "anomaly").count() == 0
    clock.advance(5)
    push(ctx, ids["device_id"], occupied=True, powers=[2950.0])  # 2nd -> alert
    with ctx.db.session() as db:
        a = db.query(Alert).filter(Alert.alert_type == "anomaly").one()
        assert a.appliance_id == aid and not a.resolved
        assert db.get(Appliance, aid).anomaly_streak == 2
    # The drop back to normal is itself a sudden change (flagged once); then 5 normal readings clear it.
    for _ in range(6):
        clock.advance(5)
        push(ctx, ids["device_id"], occupied=True, powers=[900.0])
    with ctx.db.session() as db:
        assert db.query(Alert).filter(Alert.alert_type == "anomaly").one().resolved


def test_unknown_channels_reported(ctx):
    ids = create_room_with_device(ctx)
    res = push(ctx, ids["device_id"], occupied=True, powers=[10.0, 20.0, 30.0])
    assert res.accepted == 1 and sorted(res.unknown_channels) == [1, 2]
