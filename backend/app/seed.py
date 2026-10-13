"""Initial data: admin account and (optionally) a simulated demo campus."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .context import AppContext
from .models import Appliance, Device, Room, Schedule, User
from .security import generate_device_key, hash_device_key, hash_password
from .services.events import log_event

log = logging.getLogger(__name__)

# name, type, building, floor, capacity, min_vacancy_minutes, default scenario
DEMO_ROOMS = [
    ("CR-101 Lecture Hall", "classroom", "Academic Block A", 1, 60, 1.0, "normal"),
    ("CR-102 Seminar Room", "classroom", "Academic Block A", 1, 30, 1.0, "vacant_waste"),
    ("LAB-201 Computer Lab", "laboratory", "Academic Block B", 2, 40, 1.0, "normal"),
    ("LAB-202 Electronics Lab", "laboratory", "Academic Block B", 2, 30, 1.0, "anomaly"),
    ("HST-A12 Hostel Room", "hostel", "Hostel A", 1, 2, 1.0, "normal"),
]

# room name -> [(appliance name, type, rated W, essential, auto_off_allowed)]
DEMO_APPLIANCES = {
    "CR-101 Lecture Hall": [("Lights bank", "light", 320, False, True), ("Ceiling fans", "fan", 300, False, True),
                            ("Projector", "projector", 280, False, True), ("Split AC", "ac", 1500, False, True)],
    "CR-102 Seminar Room": [("Lights bank", "light", 160, False, True), ("Ceiling fans", "fan", 150, False, True),
                            ("Projector", "projector", 250, False, True), ("Split AC", "ac", 1200, False, True)],
    "LAB-201 Computer Lab": [("Lights bank", "light", 400, False, True),
                             ("Workstations (20)", "computer", 2400, False, False),
                             ("Precision AC", "ac", 1800, False, True), ("Lab server", "server", 400, True, False)],
    "LAB-202 Electronics Lab": [("Lights bank", "light", 240, False, True),
                                ("Test benches", "lab_equipment", 800, False, True),
                                ("Exhaust fans", "fan", 150, False, True),
                                ("Chemical fridge", "refrigerator", 200, True, False),
                                ("Emergency lighting", "emergency_light", 30, True, False)],
    "HST-A12 Hostel Room": [("Room light", "light", 40, False, True), ("Ceiling fan", "fan", 75, False, True),
                            ("Room heater", "heater", 1000, False, True), ("Study laptop", "computer", 65, False, False)],
}

# room name -> [(days, start, end, label)]  — local time (Asia/Kolkata by default)
DEMO_SCHEDULES = {
    "CR-101 Lecture Hall": [(range(0, 5), "09:00", "13:00", "Morning lectures"),
                            (range(0, 5), "14:00", "16:00", "Afternoon lectures")],
    "LAB-201 Computer Lab": [(range(0, 5), "10:00", "12:00", "Programming lab"),
                             (range(0, 5), "14:00", "17:00", "Project hours")],
    "LAB-202 Electronics Lab": [((1, 3), "14:00", "17:00", "Electronics practical")],
}


def ensure_admin(ctx: AppContext, db: Session) -> None:
    s = ctx.settings
    user = db.query(User).filter(User.username == s.admin_username).one_or_none()
    if user is None:
        db.add(User(username=s.admin_username, password_hash=hash_password(s.admin_password), role="admin"))
        log.info("Created admin user '%s'", s.admin_username)
    if s.using_insecure_defaults:
        log.warning("Using INSECURE default secret/password — set SECRET_KEY and ADMIN_PASSWORD in .env")


def seed_demo(ctx: AppContext, db: Session) -> bool:
    if db.query(Room).first() is not None:
        return False
    now = ctx.clock.now()
    for name, rtype, building, floor, cap, min_vac, _ in DEMO_ROOMS:
        room = Room(name=name, room_type=rtype, building=building, floor=floor, capacity=cap,
                    min_vacancy_minutes=min_vac)
        db.add(room)
        db.flush()
        uid = "sim-" + name.split()[0].lower()
        device = Device(uid=uid, name=f"Sim node {name.split()[0]}", kind="simulated", room_id=room.id,
                        api_key_hash=hash_device_key(generate_device_key()), has_occupancy_sensor=True)
        db.add(device)
        db.flush()
        for ch, (aname, atype, watts, essential, auto_ok) in enumerate(DEMO_APPLIANCES[name]):
            db.add(Appliance(name=aname, appliance_type=atype, room_id=room.id, device_id=device.id,
                             relay_channel=ch, rated_power_w=watts, standby_threshold_w=max(5.0, watts * 0.03),
                             essential=essential, auto_off_allowed=auto_ok))
        for days, start, end, label in DEMO_SCHEDULES.get(name, []):
            for d in days:
                db.add(Schedule(room_id=room.id, day_of_week=d, start_time=start, end_time=end, label=label))
    log_event(db, "system", "Seeded simulated demo campus (5 rooms, simulated controllers)", now=now)
    return True


def default_scenarios() -> dict[str, str]:
    return {name: scenario for name, *_, scenario in DEMO_ROOMS}
