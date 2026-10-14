# Architecture

## System overview

```mermaid
flowchart LR
  subgraph Field["Rooms (classrooms · labs · hostels)"]
    PIR[PIR occupancy sensor]
    PZEM[PZEM-004T power meter]
    REL[Relay board]
    ESP[ESP32 controller<br/>firmware/esp32]
    PIR --> ESP
    PZEM --> ESP
    ESP --> REL
  end
  EMU[ESP32 emulator<br/>tools/esp32_emulator.py]
  SIM[In-process simulator<br/>app/simulation]

  subgraph Backend["FastAPI backend (app/)"]
    DEV[Device API<br/>/api/v1/esp32/*]
    ING[Telemetry pipeline<br/>energy · occupancy · ML]
    ML[Anomaly service<br/>Isolation Forest + rules]
    MON[Monitor loop<br/>offline · stale · timeouts]
    DE[Decision engine<br/>pure, deterministic]
    CMD[Command service<br/>safety gate · ack · timeout]
    ALR[Alerts + event log]
    API[REST API + JWT auth]
    WS[WebSocket /ws]
    DB[(SQLite or Postgres/Supabase<br/>SQLAlchemy)]
  end
  UI[React dashboard<br/>frontend/]

  ESP -- "HTTPS JSON (X-Device-Id/Key)" --> DEV
  EMU -- same protocol --> DEV
  SIM -- same service functions --> ING
  DEV --> ING
  ING --> ML
  ING --> DB
  MON --> DE
  DE --> CMD
  DE --> ALR
  CMD --> DB
  ALR --> DB
  CMD -. "commands in telemetry response / GET /commands" .-> DEV
  API --> DB
  UI -- REST --> API
  WS -- live events --> UI
```

## Deployment topology

Local: one machine (Docker Compose or dev servers) with SQLite. Cloud (free, no card): Vercel serves
the dashboard, a Hugging Face Docker Space runs the long-lived FastAPI process, Supabase hosts Postgres — see
[DEPLOYMENT.md](DEPLOYMENT.md). The same code runs in both; only `DATABASE_URL` and
`VITE_API_URL` differ.

## Backend modules

| Module | Responsibility |
|---|---|
| `app/config.py` | Environment configuration (pydantic-settings). Security switches live **only** here. |
| `app/models.py` | ORM: users, rooms, devices, appliances, telemetry, occupancy readings, energy records (15-min buckets), savings records, schedules, alerts, commands, event log, settings, ML model registry. |
| `app/services/energy.py` | Pure energy maths: trapezoidal kWh, bucket splitting, tariffs (flat + time-of-use), carbon, savings estimate. |
| `app/services/telemetry.py` | Ingestion pipeline shared by HTTP devices and the simulator. |
| `app/services/decision_engine.py` | Pure, deterministic decision function with full explanations. |
| `app/services/automation.py` | Builds decision inputs from the DB, executes decisions (alerts, dry-run/real commands). |
| `app/services/commands.py` | Safety gate, queueing, delivery, acknowledgement, timeouts, savings episodes. |
| `app/services/monitor.py` | Periodic supervision: device offline detection, stale data, command timeouts, override expiry, savings cap, automation. |
| `app/services/analytics.py` | Dashboard aggregates and history series. |
| `app/ml/` | Features, synthetic data generator, Isolation Forest training/evaluation, rule fallback, thread-safe model holder. |
| `app/adapters/` | Device command transports (ESP32 HTTP pull, simulated) and sensor payload parsers (`seg.v1`, `compact.v1`). |
| `app/simulation/` | Appliance power profiles, simulator (virtual ESP32s with scenarios), history backfill. |
| `app/api/` | REST routers + auth dependencies. |
| `app/context.py` | Wires shared services; event bus publishing WebSocket messages **after DB commit**. |

## Telemetry → decision → command sequence

```mermaid
sequenceDiagram
  participant D as ESP32 / emulator / simulator
  participant B as Backend
  participant M as Monitor loop (every 3 s)
  participant U as Dashboard
  D->>B: POST /esp32/telemetry (occupancy, per-channel W/V/A, relay states, health)
  B->>B: integrate kWh into 15-min buckets (wasted if room vacant)
  B->>B: score each reading (Isolation Forest) → anomaly streak → alert
  B->>B: update room occupancy / vacant_since, device health
  B-->>D: 200 {accepted, commands: [...pending]}
  M->>B: expire commands, mark offline/stale, evaluate decision engine
  alt waste + all checks pass + mode=auto
    B->>B: create command (pending, expires in 20 s)
  else blocked by policy or mode=recommend
    B->>B: raise "vacant_room_waste" alert with recommendation
  else mode=dry_run
    B->>B: record dry-run command (nothing sent)
  end
  D->>B: next telemetry → receives command → switches relay
  D->>B: POST /esp32/commands/{id}/ack {success, relay_on}
  B->>B: acknowledged → appliance off → savings episode starts
  B-->>U: WebSocket: command / alert / summary events
```

## Data model (simplified)

```mermaid
erDiagram
  ROOM ||--o{ APPLIANCE : contains
  ROOM ||--o{ DEVICE : hosts
  ROOM ||--o{ SCHEDULE : "expected use"
  DEVICE ||--o{ APPLIANCE : "relay channel"
  APPLIANCE ||--o{ TELEMETRY : readings
  ROOM ||--o{ OCCUPANCY_READING : readings
  APPLIANCE ||--o{ ENERGY_RECORD : "15-min kWh"
  APPLIANCE ||--o{ COMMAND : commands
  COMMAND ||--o| SAVINGS_RECORD : "estimated avoided kWh"
  APPLIANCE ||--o{ ALERT : alerts
```

Every telemetry, occupancy, energy and savings row carries `source` ∈ {`simulation`, `emulator`,
`hardware`}, derived server-side from the registered device kind — never from the payload.

## Concurrency

* FastAPI sync endpoints run in a thread pool; SQLite runs in WAL mode with a busy timeout.
* The simulator and monitor run as asyncio tasks that offload DB work with `asyncio.to_thread`.
* WebSocket messages are queued on the SQLAlchemy session and published only in `after_commit`,
  so clients never see uncommitted state.
* A `Clock` abstraction lets tests drive time deterministically (`FakeClock`).

## Frontend

React 19 + TypeScript + Vite + Tailwind v4 + Recharts. `AuthProvider` (JWT in localStorage),
`LiveProvider` (WebSocket with exponential-backoff reconnect and HTTP polling fallback) and a
`useApi` hook that refetches on relevant live message types (throttled). Colours are design tokens
with a validated colour-blind-safe chart palette and full dark mode; status is always icon + label.
Data-source badges (Simulated / Emulated ESP32 / Hardware) appear wherever data is displayed.
