"""Safety rules of the deterministic decision engine."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.services.decision_engine import DecisionInput, evaluate

NOW = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def waste_input(**overrides) -> DecisionInput:
    """A clear-cut wastage situation that passes every check."""
    base = DecisionInput(
        now=NOW, automation_mode="dry_run", real_switching_enabled=False, telemetry_stale_seconds=45,
        manual_on_cooldown_minutes=15, appliance_id=1, appliance_name="AC", essential=False, auto_off_allowed=True,
        appliance_override=False, appliance_state="on", power_w=1400, standby_threshold_w=5,
        last_reading_at=NOW - timedelta(seconds=3), last_manual_on_at=None, room_auto_enabled=True,
        room_override_active=False, occupancy_state="vacant", occupancy_updated_at=NOW - timedelta(seconds=3),
        vacant_since=NOW - timedelta(minutes=20), min_vacancy_minutes=10, device_kind="simulated",
        device_connection="online", device_control_validated=False, occupancy_sensor_status="ok",
    )
    return replace(base, **overrides)


def test_clear_waste_in_dry_run_records_dry_run_shutdown():
    d = evaluate(waste_input())
    assert d.data_ok and d.waste_detected
    assert d.action == "auto_shutdown" and d.execution_mode == "dry_run"
    assert d.blockers == []


def test_auto_mode_simulated_device_executes_simulated():
    d = evaluate(waste_input(automation_mode="auto"))
    assert d.action == "auto_shutdown" and d.execution_mode == "simulated"


def test_recommend_mode_never_acts():
    d = evaluate(waste_input(automation_mode="recommend"))
    assert d.action == "recommend_shutdown" and d.execution_mode is None


@pytest.mark.parametrize("override,expected_blocker", [
    ({"last_reading_at": NOW - timedelta(seconds=120)}, "power_data_fresh"),
    ({"last_reading_at": None, "power_w": None}, "power_data_present"),
    ({"occupancy_state": "unknown"}, "occupancy_known"),
    ({"occupancy_updated_at": NOW - timedelta(minutes=5)}, "occupancy_fresh"),
    ({"occupancy_updated_at": None}, "occupancy_fresh"),
    ({"occupancy_sensor_status": "fault"}, "occupancy_sensor_ok"),
    ({"device_connection": "offline"}, "device_online"),
    ({"device_connection": None, "device_kind": None}, "device_online"),
    ({"appliance_state": "unknown"}, "appliance_state_known"),
])
def test_missing_or_stale_data_prevents_any_shutdown(override, expected_blocker):
    for mode in ("recommend", "dry_run", "auto"):
        d = evaluate(waste_input(automation_mode=mode, **override))
        assert d.action == "none", (mode, override)
        assert not d.data_ok
        assert expected_blocker in d.blockers
        assert d.execution_mode is None


@pytest.mark.parametrize("override,blocker", [
    ({"appliance_override": True}, "no_appliance_override"),
    ({"room_override_active": True}, "no_room_override"),
    ({"auto_off_allowed": False}, "auto_off_policy"),
    ({"room_auto_enabled": False}, "room_automation_enabled"),
    ({"schedule_active": True, "schedule_label": "Lecture"}, "no_active_schedule"),
    ({"schedule_starting_soon": True}, "no_upcoming_schedule"),
    ({"last_manual_on_at": NOW - timedelta(minutes=2)}, "no_recent_manual_on"),
    ({"pending_command": True}, "no_pending_command"),
    ({"recent_auto_command": True}, "no_recent_auto_command"),
])
def test_policy_blockers_downgrade_to_recommendation(override, blocker):
    d = evaluate(waste_input(automation_mode="auto", **override))
    assert d.waste_detected
    assert d.action == "recommend_shutdown"
    assert blocker in d.blockers
    assert d.execution_mode is None


def test_old_manual_on_does_not_block():
    d = evaluate(waste_input(last_manual_on_at=NOW - timedelta(minutes=30)))
    assert d.action == "auto_shutdown"


def test_essential_load_is_excluded_even_from_recommendation():
    d = evaluate(waste_input(essential=True, automation_mode="auto"))
    assert d.action == "none"
    assert "not_essential_load" in d.blockers


def test_occupied_room_is_not_waste():
    d = evaluate(waste_input(occupancy_state="occupied", vacant_since=None))
    assert d.action == "none" and not d.waste_detected


def test_short_vacancy_is_not_waste():
    d = evaluate(waste_input(vacant_since=NOW - timedelta(minutes=3)))
    assert d.action == "none" and not d.waste_detected


def test_standby_power_is_not_waste():
    d = evaluate(waste_input(power_w=3.0))
    assert d.action == "none"


def test_anomaly_alone_never_authorizes_shutdown():
    # Occupied room + strong anomaly: no shutdown in any mode.
    for mode in ("recommend", "dry_run", "auto"):
        d = evaluate(waste_input(automation_mode=mode, occupancy_state="occupied", vacant_since=None,
                                 anomaly_flag=True, anomaly_score=0.4))
        assert d.action == "none"
        assert any("never authorize" in n for n in d.notes)


def test_anomaly_does_not_change_waste_outcome():
    a = evaluate(waste_input(automation_mode="auto"))
    b = evaluate(waste_input(automation_mode="auto", anomaly_flag=True, anomaly_score=0.3))
    assert (a.action, a.execution_mode) == (b.action, b.execution_mode)


def test_hardware_requires_global_switch_and_validation():
    hw = dict(automation_mode="auto", device_kind="esp32")
    d = evaluate(waste_input(**hw))
    assert d.action == "recommend_shutdown"
    assert set(d.blockers) == {"real_switching_enabled", "device_control_validated"}

    d = evaluate(waste_input(**hw, real_switching_enabled=True))
    assert d.action == "recommend_shutdown" and d.blockers == ["device_control_validated"]

    d = evaluate(waste_input(**hw, device_control_validated=True))
    assert d.action == "recommend_shutdown" and d.blockers == ["real_switching_enabled"]

    d = evaluate(waste_input(**hw, real_switching_enabled=True, device_control_validated=True))
    assert d.action == "auto_shutdown" and d.execution_mode == "hardware"


def test_hardware_dry_run_never_sends():
    d = evaluate(waste_input(device_kind="esp32", automation_mode="dry_run"))
    assert d.execution_mode == "dry_run"


def test_every_decision_is_explained():
    d = evaluate(waste_input())
    names = {c.name for c in d.checks}
    assert {"power_data_fresh", "occupancy_known", "vacancy_duration", "not_essential_load"} <= names
    assert d.summary
    assert d.to_dict()["checks"][0]["detail"]
