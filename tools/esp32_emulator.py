#!/usr/bin/env python3
"""ESP32 protocol emulator for Smart Energy Guardian (standard library only).

Speaks exactly the HTTP protocol of firmware/esp32 (telemetry, piggy-backed commands,
acknowledgements) so the hardware interface can be exercised without hardware. Register the
device with kind "emulator" so its data is labelled "emulator", never "hardware".

Examples
--------
  # create a room, an emulator device and two appliances, then run:
  python tools/esp32_emulator.py --register --admin-password guardian-demo

  # run with existing credentials:
  python tools/esp32_emulator.py --device-id emu-lab301 --device-key seg_...

  # failure modes:
  python tools/esp32_emulator.py ... --vacant --fail-commands   # NACK every command
  python tools/esp32_emulator.py ... --vacant --no-ack          # never acknowledge (timeouts)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request

APPLIANCES = [("Lights (emulated)", "light", 300.0), ("Fan (emulated)", "fan", 150.0)]


def request(base: str, method: str, path: str, body: dict | None = None, headers: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {path} -> HTTP {exc.code}: {exc.read().decode()[:300]}") from exc


def register(args) -> tuple[str, str]:
    tok = request(args.base_url, "POST", "/api/v1/auth/login",
                  {"username": args.admin_user, "password": args.admin_password})["access_token"]
    auth = {"Authorization": f"Bearer {tok}"}
    rooms = request(args.base_url, "GET", "/api/v1/rooms", headers=auth)
    room = next((r for r in rooms if r["name"] == args.room), None)
    if room is None:
        room = request(args.base_url, "POST", "/api/v1/rooms", {"name": args.room, "room_type": "laboratory",
                                                                "min_vacancy_minutes": 1, "capacity": 20}, headers=auth)
    uid = args.device_id or "emu-" + str(random.randint(1000, 9999))
    created = request(args.base_url, "POST", "/api/v1/devices",
                      {"uid": uid, "name": f"ESP32 emulator {uid}", "kind": "emulator", "room_id": room["id"]}, headers=auth)
    for ch, (name, atype, watts) in enumerate(APPLIANCES):
        request(args.base_url, "POST", "/api/v1/appliances",
                {"name": name, "appliance_type": atype, "room_id": room["id"], "device_id": created["device"]["id"],
                 "relay_channel": ch, "rated_power_w": watts, "standby_threshold_w": 5}, headers=auth)
    print(f"Registered device {uid} in room '{args.room}'. Key (shown once): {created['api_key']}")
    return uid, created["api_key"]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--device-id")
    p.add_argument("--device-key")
    p.add_argument("--register", action="store_true", help="create room/device/appliances via the admin API first")
    p.add_argument("--admin-user", default="admin")
    p.add_argument("--admin-password", default="guardian-demo")
    p.add_argument("--room", default="LAB-301 IoT Lab (emulated ESP32)")
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--vacant", action="store_true", help="report the room as vacant (creates wastage)")
    p.add_argument("--sensor-fault", action="store_true", help="report an occupancy sensor fault")
    p.add_argument("--fail-commands", action="store_true", help="acknowledge every command as failed")
    p.add_argument("--no-ack", action="store_true", help="never acknowledge commands")
    p.add_argument("--compact", action="store_true", help="use the compact.v1 payload format")
    p.add_argument("--count", type=int, default=0, help="stop after N cycles (0 = forever)")
    args = p.parse_args()

    if args.register:
        args.device_id, args.device_key = register(args)
    if not (args.device_id and args.device_key):
        p.error("--device-id and --device-key are required (or use --register)")
    headers = {"X-Device-Id": args.device_id, "X-Device-Key": args.device_key}
    relays = [True] * len(APPLIANCES)
    start = time.monotonic()
    n = 0
    while args.count == 0 or n < args.count:
        n += 1
        occupied = None if args.sensor_fault else (not args.vacant)
        readings = []
        for ch, (_, _, watts) in enumerate(APPLIANCES):
            v = random.gauss(230, 2)
            pw = max(0.0, watts * random.uniform(0.92, 1.0)) if relays[ch] else 0.0
            readings.append({"channel": ch, "power_w": round(pw, 1), "voltage_v": round(v, 1),
                             "current_a": round(pw / (v * 0.95), 3), "relay_on": relays[ch]})
        health = {"firmware": "emu-1.0.0", "rssi_dbm": random.randint(-70, -50),
                  "uptime_s": int(time.monotonic() - start), "free_heap": random.randint(150_000, 190_000)}
        if args.compact:
            body = {"format": "compact.v1", "occ": -1 if occupied is None else int(occupied), "sok": int(not args.sensor_fault),
                    "ch": [[r["channel"], r["power_w"], r["voltage_v"], r["current_a"], int(r["relay_on"])] for r in readings],
                    "fw": health["firmware"], "rssi": health["rssi_dbm"], "up": health["uptime_s"], "heap": health["free_heap"]}
        else:
            body = {"format": "seg.v1", "occupancy": {"occupied": occupied, "sensor_ok": not args.sensor_fault},
                    "readings": readings, "health": health}
        res = request(args.base_url, "POST", "/api/v1/esp32/telemetry", body, headers)
        print(f"[{n}] sent {len(readings)} readings, occupied={occupied}, relays={relays} -> accepted={res['accepted']}"
              f", commands={len(res['commands'])}")
        for cmd in res["commands"]:
            ch = cmd["channel"]
            if args.no_ack:
                print(f"    command #{cmd['command_id']} {cmd['action']} ch{ch}: NOT acknowledging (--no-ack)")
                continue
            if args.fail_commands or ch is None or not 0 <= ch < len(relays):
                r = request(args.base_url, "POST", f"/api/v1/esp32/commands/{cmd['command_id']}/ack",
                            {"success": False, "relay_on": relays[ch] if ch is not None and 0 <= ch < len(relays) else None,
                             "error": "emulated relay fault"}, headers)
            else:
                relays[ch] = cmd["action"] == "on"
                r = request(args.base_url, "POST", f"/api/v1/esp32/commands/{cmd['command_id']}/ack",
                            {"success": True, "relay_on": relays[ch]}, headers)
            print(f"    command #{cmd['command_id']} {cmd['action']} ch{ch} -> {r['status']}")
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
