"""Deterministic energy-management decision engine.

The engine is a pure function: given a snapshot of one appliance and its context it returns
a :class:`Decision` with every check it evaluated, so each outcome is explainable.

Evaluation order
----------------
1. **Data quality** — fresh power telemetry, known & fresh occupancy, healthy occupancy sensor,
   reachable device and known relay state. If any fails, *no* shutdown is recommended or
   executed (we cannot conclude anything from missing data).
2. **Waste condition** — load drawing more than its standby threshold in a room that has been
   vacant for at least the room's minimum vacancy time.
3. **Safety policy** — essential loads are excluded entirely; manual overrides, appliance
   policy, room automation flag, active/upcoming schedules, a recent manual switch-on,
   pending/recent commands and the hardware-switching gate all block *automatic* action,
   leaving at most a recommendation for a human.
4. **Mode** — ``recommend`` never acts; ``dry_run`` records what it would do; ``auto`` sends a
   command through the device's adapter.

Anomaly scores are reported as context only: an anomaly never satisfies the waste condition
and never authorizes a shutdown by itself.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal

Action = Literal["none", "recommend_shutdown", "auto_shutdown"]


@dataclass
class DecisionInput:
    now: datetime
    automation_mode: Literal["recommend", "dry_run", "auto"]
    real_switching_enabled: bool
    telemetry_stale_seconds: float
    manual_on_cooldown_minutes: float
    # appliance
    appliance_id: int
    appliance_name: str
    essential: bool
    auto_off_allowed: bool
    appliance_override: bool
    appliance_state: str  # on | off | unknown
    power_w: float | None
    standby_threshold_w: float
    last_reading_at: datetime | None
    last_manual_on_at: datetime | None
    # room
    room_auto_enabled: bool
    room_override_active: bool
    occupancy_state: str  # occupied | vacant | unknown
    occupancy_updated_at: datetime | None
    vacant_since: datetime | None
    min_vacancy_minutes: float
    # device
    device_kind: str | None  # simulated | emulator | esp32 | None
    device_connection: str | None  # online | offline | never_seen | None
    device_control_validated: bool
    occupancy_sensor_status: str  # ok | fault | unknown
    # schedule
    schedule_active: bool = False
    schedule_label: str | None = None
    schedule_starting_soon: bool = False
    # anomaly (informational)
    anomaly_flag: bool = False
    anomaly_score: float | None = None
    # command bookkeeping
    pending_command: bool = False
    recent_auto_command: bool = False


@dataclass
class Check:
    name: str
    category: Literal["data", "waste", "safety", "mode"]
    passed: bool
    detail: str


@dataclass
class Decision:
    appliance_id: int
    action: Action
    data_ok: bool
    waste_detected: bool
    execution_mode: str | None
    summary: str
    checks: list[Check] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    evaluated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _age_s(now: datetime, ts: datetime | None) -> float | None:
    return None if ts is None else (now - ts).total_seconds()


def evaluate(inp: DecisionInput) -> Decision:
    checks: list[Check] = []
    notes: list[str] = []

    def add(name, category, passed, detail):
        checks.append(Check(name, category, bool(passed), detail))
        return bool(passed)

    # ---- 1. Data quality ---------------------------------------------------
    age_p = _age_s(inp.now, inp.last_reading_at)
    add("power_data_present", "data", inp.power_w is not None and age_p is not None,
        "power telemetry received" if age_p is not None else "no power telemetry for this appliance")
    add("power_data_fresh", "data", age_p is not None and age_p <= inp.telemetry_stale_seconds,
        f"last reading {age_p:.0f}s ago (limit {inp.telemetry_stale_seconds:.0f}s)" if age_p is not None
        else "no reading")
    age_o = _age_s(inp.now, inp.occupancy_updated_at)
    add("occupancy_known", "data", inp.occupancy_state in ("occupied", "vacant"),
        f"occupancy is '{inp.occupancy_state}'")
    add("occupancy_fresh", "data", age_o is not None and age_o <= inp.telemetry_stale_seconds,
        f"occupancy updated {age_o:.0f}s ago" if age_o is not None else "no occupancy reading")
    add("occupancy_sensor_ok", "data", inp.occupancy_sensor_status != "fault",
        f"occupancy sensor status '{inp.occupancy_sensor_status}'")
    add("device_online", "data", inp.device_connection == "online",
        f"controller is '{inp.device_connection or 'not assigned'}'")
    add("appliance_state_known", "data", inp.appliance_state in ("on", "off"),
        f"relay/appliance state '{inp.appliance_state}'")
    data_ok = all(c.passed for c in checks if c.category == "data")

    # ---- 2. Waste condition ------------------------------------------------
    drawing = (inp.power_w or 0.0) > inp.standby_threshold_w and inp.appliance_state == "on"
    add("load_drawing_power", "waste", drawing,
        f"{(inp.power_w or 0):.1f} W vs standby threshold {inp.standby_threshold_w:.1f} W")
    vacant = inp.occupancy_state == "vacant"
    add("room_vacant", "waste", vacant, f"room occupancy '{inp.occupancy_state}'")
    vac_min = _age_s(inp.now, inp.vacant_since)
    vac_min = None if vac_min is None else vac_min / 60.0
    add("vacancy_duration", "waste", vacant and vac_min is not None and vac_min >= inp.min_vacancy_minutes,
        f"vacant for {vac_min:.1f} min (needs {inp.min_vacancy_minutes:g} min)" if vac_min is not None
        else "no vacancy start recorded")
    waste = data_ok and all(c.passed for c in checks if c.category == "waste")

    # ---- 3. Safety policy (only meaningful once waste is established) ------
    add("not_essential_load", "safety", not inp.essential,
        "essential load — excluded from shutdown" if inp.essential else "non-essential load")
    add("no_appliance_override", "safety", not inp.appliance_override,
        "manual override active on appliance" if inp.appliance_override else "no appliance override")
    add("no_room_override", "safety", not inp.room_override_active,
        "manual override active on room" if inp.room_override_active else "no room override")
    add("auto_off_policy", "safety", inp.auto_off_allowed,
        "appliance policy allows automatic off" if inp.auto_off_allowed else "appliance policy: manual only")
    add("room_automation_enabled", "safety", inp.room_auto_enabled,
        "room automation enabled" if inp.room_auto_enabled else "room automation disabled")
    add("no_active_schedule", "safety", not inp.schedule_active,
        f"scheduled session active: {inp.schedule_label}" if inp.schedule_active else "no scheduled session")
    add("no_upcoming_schedule", "safety", not inp.schedule_starting_soon,
        "scheduled session starts soon" if inp.schedule_starting_soon else "no session starting soon")
    age_m = _age_s(inp.now, inp.last_manual_on_at)
    recent_manual = age_m is not None and age_m < inp.manual_on_cooldown_minutes * 60
    add("no_recent_manual_on", "safety", not recent_manual,
        f"switched on manually {age_m / 60:.1f} min ago" if recent_manual else "no recent manual switch-on")
    add("no_pending_command", "safety", not inp.pending_command,
        "a command is already pending" if inp.pending_command else "no pending command")
    add("no_recent_auto_command", "safety", not inp.recent_auto_command,
        "automatic command issued recently (cooldown)" if inp.recent_auto_command else "no recent automatic command")

    if inp.anomaly_flag:
        notes.append(
            f"Anomaly detected (score {inp.anomaly_score:.3f}). Informational only — anomalies never "
            "authorize a shutdown by themselves." if inp.anomaly_score is not None
            else "Anomaly detected (informational only)."
        )

    blockers = [c.name for c in checks if c.category == "safety" and not c.passed]
    exec_mode: str | None = None

    if not data_ok:
        failed = [c.name for c in checks if c.category == "data" and not c.passed]
        action: Action = "none"
        summary = "Insufficient or stale data — automatic shutdown prevented (" + ", ".join(failed) + ")"
        blockers = failed
    elif not waste:
        action = "none"
        summary = "No wastage detected"
        blockers = []
    elif inp.essential:
        action = "none"
        summary = "Wastage pattern on an essential load — excluded from shutdown"
    elif blockers:
        action = "recommend_shutdown"
        summary = "Wastage detected; automatic shutdown blocked by policy (" + ", ".join(blockers) + ")"
    elif inp.automation_mode == "recommend":
        action = "recommend_shutdown"
        summary = "Wastage detected; automation mode is 'recommend' — human action required"
        add("automation_mode", "mode", False, "mode 'recommend' never switches loads")
    elif inp.automation_mode == "dry_run":
        action = "auto_shutdown"
        exec_mode = "dry_run"
        summary = "Wastage detected; dry-run shutdown recorded (no command sent)"
        add("automation_mode", "mode", True, "dry-run: decision logged, nothing switched")
    else:  # auto
        if inp.device_kind == "esp32":
            gate_ok = add("real_switching_enabled", "mode", inp.real_switching_enabled,
                          "REAL_SWITCHING_ENABLED is " + ("on" if inp.real_switching_enabled else "off"))
            val_ok = add("device_control_validated", "mode", inp.device_control_validated,
                         "device control validated by admin" if inp.device_control_validated
                         else "device control not yet validated")
            if gate_ok and val_ok:
                action, exec_mode = "auto_shutdown", "hardware"
                summary = "Wastage detected; shutdown command sent to hardware"
            else:
                action = "recommend_shutdown"
                blockers = [n for n, ok in (("real_switching_enabled", gate_ok),
                                            ("device_control_validated", val_ok)) if not ok]
                summary = "Wastage detected; hardware switching gate closed — human action required"
        else:
            action = "auto_shutdown"
            exec_mode = "emulator" if inp.device_kind == "emulator" else "simulated"
            summary = f"Wastage detected; {exec_mode} shutdown command issued"
            add("automation_mode", "mode", True, f"auto mode on a {inp.device_kind} device")

    return Decision(
        appliance_id=inp.appliance_id,
        action=action,
        data_ok=data_ok,
        waste_detected=waste,
        execution_mode=exec_mode,
        summary=summary,
        checks=checks,
        blockers=blockers,
        notes=notes,
        evaluated_at=inp.now.isoformat(),
    )
