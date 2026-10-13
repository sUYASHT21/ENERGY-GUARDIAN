"""Hardware-free simulation of rooms, sensors, controllers and relays.

Every simulated device behaves like an ESP32 running the reference firmware:
it posts telemetry through the normal ingestion pipeline and fetches/acknowledges
commands through the same service functions used by the HTTP device API.
All data it produces is labelled ``source="simulation"``.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field

import numpy as np

from ..adapters.telemetry_parsers import HealthIn, OccupancyIn, ReadingIn, TelemetryPayload
from ..context import AppContext, emit
from ..ml.synthetic import anomalous_reading
from ..models import Appliance, Device, Room
from ..services import commands as command_service
from ..services import telemetry as telemetry_service
from ..services.events import log_event
from .profiles import normal_reading

log = logging.getLogger(__name__)

SCENARIOS: dict[str, str] = {
    "normal": "Occupancy changes naturally; occupants usually switch appliances off when leaving "
              "(sometimes they forget, creating realistic waste).",
    "vacant_waste": "Room is empty but appliances were left running — demonstrates waste detection "
                    "and (dry-run/simulated) shutdown.",
    "anomaly": "Room is occupied; the largest non-essential appliance shows abnormal electrical behaviour "
               "(over-consumption, spikes, low power factor) — demonstrates ML anomaly detection.",
    "sensor_failure": "Occupancy sensor reports invalid data — occupancy becomes 'unknown' and automatic "
                      "shutdown is blocked.",
    "offline": "Controller stops reporting and stops acknowledging commands — demonstrates offline "
               "detection and stale-data safety blocks.",
    "command_failure": "Room empty with appliances left on; the relay rejects commands — demonstrates "
                       "failed-acknowledgement handling.",
    "command_timeout": "Room empty with appliances left on; the controller never acknowledges commands — "
                       "demonstrates command timeouts.",
}
WASTE_SCENARIOS = ("vacant_waste", "command_failure", "command_timeout")
ANOMALY_KINDS_CYCLE = ("overconsumption", "overconsumption", "low_power_factor", "spike")


@dataclass
class RoomSim:
    scenario: str = "normal"
    occupied: bool = True
    ticks_in_state: int = 0
    anomaly_target: int | None = None


@dataclass
class ApplianceSim:
    relay_on: bool = False
    prev_ratio: float | None = None
    prev_power: float | None = None


@dataclass
class PendingAck:
    command_id: int
    device_id: int
    appliance_id: int
    action: str
    due_tick: int


@dataclass
class Simulator:
    ctx: AppContext
    seed: int = 42
    default_scenarios: dict[str, str] = field(default_factory=dict)  # room name -> scenario
    running: bool = False
    tick_count: int = 0

    def __post_init__(self):
        self.rng = np.random.default_rng(self.seed)
        self.rooms: dict[int, RoomSim] = {}
        self.appliances: dict[int, ApplianceSim] = {}
        self.pending_acks: list[PendingAck] = []
        self._lock = threading.RLock()
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------ control
    def _room(self, room: Room) -> RoomSim:
        rs = self.rooms.get(room.id)
        if rs is None:
            rs = RoomSim(scenario=self.default_scenarios.get(room.name, "normal"))
            self.rooms[room.id] = rs
            self._enter_scenario(room, rs)
        return rs

    def _app(self, a: Appliance) -> ApplianceSim:
        s = self.appliances.get(a.id)
        if s is None:
            s = ApplianceSim(relay_on=a.essential or a.state == "on")
            self.appliances[a.id] = s
        return s

    def _enter_scenario(self, room: Room, rs: RoomSim) -> None:
        rs.ticks_in_state = 0
        sims = [(a, self._app(a)) for a in room.appliances]
        if rs.scenario in WASTE_SCENARIOS:
            rs.occupied = False
            for a, s in sims:
                if a.appliance_type not in ("emergency_light",):
                    s.relay_on = True  # left on by the last occupants
        elif rs.scenario in ("anomaly", "sensor_failure", "normal"):
            rs.occupied = True
            for a, s in sims:
                s.relay_on = a.essential or a.appliance_type in ("light", "fan", "computer", "projector", "ac",
                                                                 "lab_equipment")
        candidates = [a for a in room.appliances if not a.essential]
        rs.anomaly_target = max(candidates, key=lambda a: a.rated_power_w).id if candidates else None

    def set_scenario(self, room_id: int, scenario: str, actor: str = "system") -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario '{scenario}'")
        with self._lock, self.ctx.db.session() as db:
            room = db.get(Room, room_id)
            if room is None:
                raise LookupError("room not found")
            rs = self._room(room)
            rs.scenario = scenario
            self._enter_scenario(room, rs)
            log_event(db, "simulation", f"Scenario for {room.name} set to '{scenario}'", now=self.ctx.clock.now(),
                      actor=actor, room_id=room.id)
            emit(db, "simulation", self.status_dict(db))

    def reset(self, actor: str = "system") -> None:
        with self._lock, self.ctx.db.session() as db:
            self.rooms.clear()
            self.appliances.clear()
            self.pending_acks.clear()
            log_event(db, "simulation", "Simulation scenarios reset to defaults", now=self.ctx.clock.now(),
                      actor=actor)
            emit(db, "simulation", self.status_dict(db))

    def status_dict(self, db) -> dict:
        rooms = []
        for room in db.query(Room).order_by(Room.id).all():
            if not any(d.kind == "simulated" for d in room.devices):
                continue
            rs = self.rooms.get(room.id)
            rooms.append({"room_id": room.id, "room": room.name,
                          "scenario": rs.scenario if rs else self.default_scenarios.get(room.name, "normal")})
        return {"running": self.running, "tick": self.tick_count,
                "tick_seconds": self.ctx.settings.simulation_tick_seconds,
                "scenarios": SCENARIOS, "rooms": rooms}

    # ------------------------------------------------------------------ tick
    def tick(self) -> None:
        with self._lock:
            self.tick_count += 1
            with self.ctx.db.session() as db:
                devices = db.query(Device).filter(Device.kind == "simulated").all()
                for dev in devices:
                    if dev.room is None:
                        continue
                    self._tick_device(db, dev)

    def _tick_device(self, db, dev: Device) -> None:
        room = dev.room
        rs = self._room(room)
        if rs.scenario == "offline":
            return  # silent: no telemetry, no acks
        self._process_commands(db, dev, rs)
        self._step_occupancy(room, rs)
        occ = self._occupancy_payload(room, rs) if dev.has_occupancy_sensor else None
        readings = []
        for a in dev.appliances:
            s = self._app(a)
            if a.essential:
                s.relay_on = True
            if rs.scenario == "anomaly" and a.id == rs.anomaly_target and s.relay_on and self.rng.random() < 0.9:
                kind = ANOMALY_KINDS_CYCLE[(self.tick_count // 10) % len(ANOMALY_KINDS_CYCLE)]
                p, v, i, _ = anomalous_reading(self.rng, kind, a.rated_power_w, s.prev_power)
            else:
                p, v, i = normal_reading(self.rng, a.appliance_type, a.rated_power_w, s.relay_on, s.prev_ratio)
            s.prev_power = p
            s.prev_ratio = p / a.rated_power_w if s.relay_on else None
            readings.append(ReadingIn(channel=a.relay_channel, power_w=round(p, 2), voltage_v=round(v, 1),
                                      current_a=round(i, 3), relay_on=s.relay_on))
        payload = TelemetryPayload(
            ts=self.ctx.clock.now(), occupancy=occ, readings=readings,
            health=HealthIn(firmware="sim-1.0", rssi_dbm=int(self.rng.integers(-72, -48)),
                            uptime_s=int(self.tick_count * self.ctx.settings.simulation_tick_seconds),
                            free_heap=int(self.rng.integers(150_000, 190_000)), ip="sim"))
        telemetry_service.ingest(self.ctx, db, dev, payload)

    def _occupancy_payload(self, room: Room, rs: RoomSim) -> OccupancyIn:
        if rs.scenario == "sensor_failure":
            return OccupancyIn(occupied=None, people_count=None, sensor_ok=False)
        people = int(self.rng.integers(3, max(room.capacity, 4) + 1)) if rs.occupied else 0
        return OccupancyIn(occupied=rs.occupied, people_count=people, sensor_ok=True)

    def _step_occupancy(self, room: Room, rs: RoomSim) -> None:
        rs.ticks_in_state += 1
        if rs.scenario in WASTE_SCENARIOS:
            rs.occupied = False
            return
        if rs.scenario in ("anomaly", "sensor_failure"):
            rs.occupied = True
            return
        # normal: two-state Markov chain (mean ~80 ticks occupied, ~50 ticks vacant)
        p_change = 1 / 80 if rs.occupied else 1 / 50
        if rs.ticks_in_state > 10 and self.rng.random() < p_change:
            rs.occupied = not rs.occupied
            rs.ticks_in_state = 0
            for a in room.appliances:
                if a.essential:
                    continue
                s = self._app(a)
                if rs.occupied:
                    s.relay_on = a.appliance_type in ("light", "fan") or self.rng.random() < 0.6
                elif self.rng.random() < 0.8:  # most occupants switch off; some forget
                    s.relay_on = False

    def _process_commands(self, db, dev: Device, rs: RoomSim) -> None:
        # 1) deliver acknowledgements that are due (simulated relay latency = 1 tick)
        due = [p for p in self.pending_acks if p.device_id == dev.id and p.due_tick <= self.tick_count]
        for p in due:
            self.pending_acks.remove(p)
            s = self.appliances.get(p.appliance_id) or ApplianceSim()
            self.appliances[p.appliance_id] = s
            if rs.scenario == "command_failure":
                command_service.acknowledge(self.ctx, db, dev, p.command_id, success=False, relay_on=s.relay_on,
                                            error="relay did not switch (simulated relay fault)")
            else:
                s.relay_on = p.action == "on"
                command_service.acknowledge(self.ctx, db, dev, p.command_id, success=True, relay_on=s.relay_on)
        # 2) fetch new commands (same call the ESP32 HTTP endpoint uses)
        known = {p.command_id for p in self.pending_acks}
        for c in command_service.fetch_pending(self.ctx, db, dev):
            if c["command_id"] in known or rs.scenario == "command_timeout":
                continue
            self.pending_acks.append(PendingAck(c["command_id"], dev.id, c["appliance_id"], c["action"],
                                                self.tick_count + 1))

    # ------------------------------------------------------------------ async loop
    async def _run(self) -> None:
        interval = self.ctx.settings.simulation_tick_seconds
        while self.running:
            try:
                await asyncio.to_thread(self.tick)
            except Exception:  # pragma: no cover - keep simulating
                log.exception("simulation tick failed")
            await asyncio.sleep(interval)

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._task = asyncio.get_running_loop().create_task(self._run())
        log.info("Simulation started (tick %.1fs)", self.ctx.settings.simulation_tick_seconds)

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
