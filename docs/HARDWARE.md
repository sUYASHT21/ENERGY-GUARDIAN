# Hardware integration (ESP32)

> Status: the HTTP protocol is implemented and tested end-to-end with the Python emulator
> (`tools/esp32_emulator.py`) and backend tests. The reference Arduino sketch in
> `firmware/esp32/` has **not been compiled or run on physical hardware** by the project
> authors. Treat it as a starting point and validate on a bench.

## Reference bill of materials (per room node)

| Part | Purpose | Notes |
|---|---|---|
| ESP32 DevKit (WROOM-32) | controller, Wi-Fi | 3.3 V logic |
| HC-SR501 / AM312 PIR | occupancy | mount for full room coverage; PIR misses motionless people → use a generous minimum vacancy |
| PZEM-004T v3 (one per channel, Modbus addresses 0x01…) | power, voltage, current | CT clamp on the appliance's live wire; isolated |
| 4-channel opto-isolated relay board (or contactors for AC/heaters) | switching | rated for the load; NC contact keeps loads on when de-energised |
| 5 V supply (HLK-PM01) | power | in a proper enclosure |

Mains wiring must be done by a qualified electrician.

## Wiring (defaults in `config.example.h`)

| ESP32 pin | Connects to |
|---|---|
| GPIO 27 | PIR OUT |
| GPIO 16, 17, 18, 19 | relay IN1–IN4 (channels 0–3) |
| GPIO 25 (RX2) / 26 (TX2) | PZEM TX / RX (shared Modbus bus, distinct addresses) |

Relay **channel numbers** must match the `relay_channel` configured for each appliance in the
dashboard.

## Provisioning

1. Dashboard → **Devices → Register device**: uid (e.g. `esp32-lab301`), kind `ESP32 hardware`,
   room. Copy the API key (shown once; only its hash is stored).
2. Dashboard → room → **Add appliance** for each relay channel (controller + channel + rated W).
3. `cp firmware/esp32/smart_energy_guardian/config.example.h config.h`, fill Wi-Fi, base URL,
   device id and key. Libraries: ArduinoJson v7, PZEM004Tv30. Board: "ESP32 Dev Module". Flash.
4. The device appears **online** within one telemetry interval. Readings are labelled
   **Hardware**. Commands stay blocked until real switching is enabled (see SAFETY.md).

## HTTP protocol

Base path `/api/v1/esp32`. Every request carries:

```
X-Device-Id: esp32-lab301
X-Device-Key: seg_...
Content-Type: application/json
```

### `POST /telemetry` (every 5 s)

```json
{
  "format": "seg.v1",
  "ts": "2026-10-13T10:00:00Z",
  "occupancy": {"occupied": true, "people_count": 3, "sensor_ok": true},
  "readings": [
    {"channel": 0, "power_w": 152.3, "voltage_v": 229.8, "current_a": 0.71, "relay_on": true}
  ],
  "health": {"firmware": "1.0.0", "rssi_dbm": -61, "uptime_s": 3600, "free_heap": 182000}
}
```

* `ts` is optional; without NTP omit it — the server uses its receive time (also used when the
  device clock is off by more than 5 min).
* `occupied: null` or `sensor_ok: false` ⇒ occupancy **unknown** ⇒ automation blocked + alert.
* Omit a channel whose meter did not respond; the backend marks it stale (no data is invented).
* Limits: ≤ 32 readings, channel 0–63, power 0–100 kW, voltage 0–500 V, current 0–500 A.

Compact alternative for constrained nodes (`compact.v1`):

```json
{"format": "compact.v1", "occ": 1, "sok": 1, "pc": 3, "ch": [[0, 152.3, 229.8, 0.71, 1]], "fw": "1.0.0", "rssi": -61, "up": 3600}
```

Response:

```json
{
  "accepted": 1, "skipped": 0, "unknown_channels": [], "used_server_time": true,
  "server_time": "2026-10-13T10:00:00.123Z",
  "commands": [{"command_id": 42, "channel": 0, "appliance_id": 7, "action": "off", "expires_at": "2026-10-13T10:00:20Z"}],
  "poll_interval_s": 5
}
```

### Commands and acknowledgements

Commands arrive in the telemetry response (or via `GET /commands`). They are absolute and
idempotent; a command is re-delivered until acknowledged or expired. After switching:

```
POST /commands/{command_id}/ack
{"success": true, "relay_on": false}
{"success": false, "relay_on": true, "error": "power still present after OFF (relay fault?)"}
```

| Situation | Backend result |
|---|---|
| ack `success: true` | `acknowledged`, appliance state from `relay_on`, savings episode may start |
| ack `success: false` | `failed` + `command_failed` alert |
| no ack within `COMMAND_TIMEOUT_SECONDS` (20 s) | `timeout` + `command_timeout` alert |
| late/duplicate ack | ignored (original outcome kept), logged |
| device silent > `DEVICE_OFFLINE_SECONDS` (30 s) | device `offline`, appliance states `unknown`, alert |

### Other endpoints

* `POST /heartbeat` — body = `health` object; keeps the device online without readings.
* `GET /config` — channel map (no secrets).

## Testing without hardware

```bash
python tools/esp32_emulator.py --register --admin-password <admin password>   # normal
python tools/esp32_emulator.py --device-id <uid> --device-key <key> --vacant         # wastage
python tools/esp32_emulator.py --device-id <uid> --device-key <key> --vacant --fail-commands
python tools/esp32_emulator.py --device-id <uid> --device-key <key> --vacant --no-ack
python tools/esp32_emulator.py --device-id <uid> --device-key <key> --sensor-fault
```

Register emulators with kind `emulator`: their data is labelled **Emulated ESP32** and they are
never subject to — or able to bypass — the hardware switching gate.

## Adding other hardware

* **New payload format:** add a parser to `app/adapters/telemetry_parsers.py::PARSERS`.
* **New command transport** (MQTT, push-HTTP to the device): implement `CommandTransport` in
  `app/adapters/base.py` and register it in `TRANSPORTS`. Acknowledgement/timeout handling is
  transport-independent.
