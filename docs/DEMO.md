# Demonstration walkthrough (no hardware needed)

Start the stack (`docker compose up --build` → http://localhost:8080, or the local dev commands
in the README → http://127.0.0.1:5173) and sign in as `admin` / `guardian-demo`.

The demo campus has five rooms with simulated controllers. Demo rooms use a **1-minute minimum
vacancy** so wastage is detected quickly (production default: 10 min). Seven days of simulated
history are backfilled so charts have context. Everything simulated carries a purple
**Simulated** badge, and the top bar reads *Simulation mode — data is synthetic*.

| # | Step | What to show | Expected result |
|---|---|---|---|
| 1 | **Dashboard** | KPI tiles, live power chart, room grid, device health | Values update every ~3 s over WebSocket ("Live" indicator). Savings tiles say *Estimate*. |
| 2 | **Vacant-room wastage** | CR-102 starts in *vacant waste* (lights, fans, projector, AC left on) | After ~1 min: four *vacant room waste* alerts; Commands page shows **dry-run** OFF commands (default mode: nothing is sent). |
| 3 | **Why?** | Rooms → CR-102 → expand *Split AC* | Every check (data quality, wastage, safety, mode) with pass/fail and detail. |
| 4 | **Simulated shutdown** | Settings → Automation **Automatic** → Save | Within seconds: OFF commands *pending → sent → acknowledged* by the virtual controller, appliances OFF, waste alerts auto-resolve, *Estimated savings* starts counting. |
| 5 | **Anomaly (ML)** | LAB-202 runs *anomaly*; open **ML model** | Flagged readings + score chart for *Test benches*; *Abnormal consumption* alert. **No shutdown**: room is occupied and anomalies never authorize one. Metrics panel shows precision/recall/F1/ROC-AUC with the *synthetic evaluation* disclaimer. |
| 6 | **Policy blocks** | LAB-201 *Workstations* are *manual only*; CR-101 / LAB-201 have weekday schedules | Wastage there produces *recommendations* (alert lists the blocker, e.g. `no_active_schedule`, `auto_off_policy`), never commands. Try **Manual override** on a room: automation stops for it. |
| 7 | **Sensor failure** | Simulation → set a room to *sensor failure* | Occupancy **unknown**, critical *Occupancy sensor failure* alert, decisions show `occupancy_known` failing → no action. |
| 8 | **Offline device** | Set a room to *offline* | After 30 s: device **offline**, critical alert, appliance states **unknown**, automation suspended. Set back to *normal* → device online, alert auto-resolves. |
| 9 | **Failed command** | Room without active schedule (e.g. LAB-202 or HST-A12) → *command failure*, automation *auto* | Command status **failed**, *Command OFF failed* alert with the relay-fault message. |
| 10 | **Timed-out command** | *command timeout* | Command **timeout** after 20 s + alert. |
| 11 | **Acknowledge alerts** | Alerts page → Acknowledge / Resolve / Apply recommendation | Who/when recorded; Event log shows the audit trail. |
| 12 | **History & tariff** | History (24 h / 7 d / 30 d, per room); Settings → change tariff or enable time-of-use | Costs use the configured tariff; table view available; simulated vs hardware kWh separated. |
| 13 | **Hardware path** | `python tools/esp32_emulator.py --register --vacant` | New room "LAB-301 IoT Lab", device labelled **Emulated ESP32**, telemetry over the real HTTP protocol; in *auto* mode OFF commands arrive in the telemetry response and are acknowledged. |
| 14 | **Hardware safety** | Register an *ESP32 hardware* device | Any command to it is **blocked** ("REAL_SWITCHING_ENABLED=false") until the env flag is set *and* an admin marks the device validated. |

Reset: Simulation → **Reset scenarios**; Settings → automation back to **Dry-run**.
