# Safety model

Automatic switching of electrical loads in occupied buildings can cause harm (people left in
the dark, lab experiments or servers interrupted). The system is therefore **conservative by
construction**: every shutdown must be positively justified by fresh data, and any doubt
blocks automation.

## Defaults

| Setting | Default | Where |
|---|---|---|
| Automation mode | `dry_run` — decisions are recorded, nothing is sent | runtime setting (admin) |
| Real hardware switching | **disabled** (`REAL_SWITCHING_ENABLED=false`) | environment only, needs restart |
| Per-device control | not validated (`control_validated=false`) | admin action per ESP32 |
| Data source | simulation | — |

Hardware commands require **all three**: mode `auto`, `REAL_SWITCHING_ENABLED=true`, and the
specific ESP32 marked *control validated* by an admin. The environment flag cannot be changed
through the API (the settings endpoint rejects it with HTTP 422).

## Decision engine rules (`app/services/decision_engine.py`)

A shutdown is considered only when **every** check passes. Each check is returned with a
human-readable detail and shown in the room page.

**1. Data quality — failure ⇒ no action at all (not even a recommendation):**

* power telemetry present and fresh (`TELEMETRY_STALE_SECONDS`, default 45 s)
* occupancy known (`occupied`/`vacant`), fresh, and the occupancy sensor not in fault
* controller online (`DEVICE_OFFLINE_SECONDS`, default 30 s) and relay state known

**2. Wastage condition:** load above its standby threshold, room vacant, and vacant for at least
the room's minimum vacancy time. The vacancy timer **restarts** after any period of unknown
occupancy.

**3. Safety policy — failure ⇒ recommendation only (human decides):**

* essential loads (server, fridge, emergency lighting) are excluded **entirely**
* manual override on the room or appliance
* appliance policy "manual only" (e.g. lab workstations with unsaved work)
* room automation disabled
* scheduled session active, or starting within the grace period (default 10 min)
* appliance switched on manually within the cooldown (default 15 min)
* a command is already pending, or an automatic command was issued within the cooldown

**4. Mode:** `recommend` never acts; `dry_run` records; `auto` sends via the device adapter
(hardware gate as above).

**Anomaly detection never authorizes a shutdown.** Anomaly results are attached to decisions
as notes and raise their own alerts; they do not count toward the wastage condition. Tested in
`tests/test_decision_engine.py::test_anomaly_alone_never_authorizes_shutdown`.

## Command safety gate (`app/services/commands.py::gate`)

Applied to manual *and* automatic commands:

* essential load OFF requires an admin **and** explicit confirmation
* controller must be online; no other command pending for the appliance
* ESP32 hardware requires `REAL_SWITCHING_ENABLED` and device validation

Blocked commands are persisted with status `blocked` and the reason (audit trail).

## Acknowledgements and failure handling

* Commands expire after `COMMAND_TIMEOUT_SECONDS` (default 20 s) → status `timeout` + alert;
  the appliance state is treated as uncertain.
* Failed acknowledgements → status `failed` + alert; device error counter increments.
* Late or duplicate acks are idempotent and never overwrite the recorded outcome.
* Commands are absolute (`on`/`off`), so re-delivery is harmless.
* A controller going offline sets its appliances' state to `unknown`, blocking automation.

## Firmware fail-safe (reference design)

The reference wiring powers appliances through the relay's **normally-closed** contact, so a
de-energised relay (boot, brown-out, firmware crash) leaves loads **on**. The firmware turns
loads on at boot and verifies OFF commands with the power meter before acknowledging success.

## Authentication & authorization

* Users: PBKDF2-SHA256 password hashes (240k iterations), JWT (HS256) access tokens.
  Roles: `viewer` (read), `operator` (rooms, appliances, alerts, manual commands, simulation),
  `admin` (settings, devices, keys, ML training, users, essential-load override).
* Login rate limiting (8 failures / 5 min per IP+username).
* Devices: per-device random API key, only its SHA-256 hash stored; shown once; rotatable.
  Unknown device and wrong key return the same 401. Simulated devices cannot use the device API.
* In `APP_ENV=production` the app refuses to start with the default `SECRET_KEY` or
  `ADMIN_PASSWORD`.
* Input validation on every endpoint (pydantic): ranges for power/voltage/current, channel
  numbers, time formats, payload size (≤ 32 readings).

## Before enabling real switching

1. Use certified relay modules rated for the load (inductive loads such as AC compressors need
   contactors), installed by a qualified electrician; keep manual wall switches functional.
2. Bench-test the firmware: boot state, Wi-Fi loss, backend loss, relay verification.
3. Run in `dry_run` with hardware telemetry for at least several days; review the dry-run
   commands for false positives (PIR blind spots!) and tune minimum vacancy times.
4. Mark exactly one device as validated, set `REAL_SWITCHING_ENABLED=true`, monitor, expand.
