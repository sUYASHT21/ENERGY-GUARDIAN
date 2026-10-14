# Smart Energy Guardian — AI-Based IoT Energy Management System

Detects unnecessary electricity consumption in classrooms, laboratories and hostels by combining
occupancy sensing, electrical measurements, schedules and machine learning. It raises alerts,
recommends or (safely) simulates appliance shutdown, and visualises consumption, waste and
estimated savings.

> **Simulation and dry-run by default.** The complete demo runs without hardware. Real relay
> switching is disabled until explicitly enabled in the environment **and** validated per device.
> Anomaly detection never authorizes a shutdown on its own.

## Features

* **Live dashboard** — power, energy today, cost, waste in vacant rooms, *estimated* savings
  (kWh / cost / CO₂), room occupancy, appliance status, device health, open alerts; WebSocket
  updates with HTTP fallback; light/dark themes; responsive down to phone width.
* **Management** — rooms, appliances (rated power, standby threshold, essential / manual-only
  policies), schedules, manual overrides, devices with one-time API keys, users & roles.
* **Deterministic decision engine** — combines data freshness, occupancy, vacancy duration,
  schedules, overrides, appliance policy, device status, pending commands and mode. Every
  decision is explained check-by-check in the UI.
* **ML anomaly detection** — scikit-learn Isolation Forest on electrical features with training,
  evaluation metrics, model registry, per-reading scores and a transparent rule fallback.
  Trained and evaluated on clearly labelled **synthetic** data.
* **Commands with acknowledgements** — safety gate, queue, delivery via telemetry response or
  polling, ack / failure / timeout handling, idempotent re-delivery, full audit log.
* **ESP32 interface** — documented HTTP protocol, reference Arduino firmware, and a Python
  emulator speaking the same protocol.
* **Simulation mode** — virtual ESP32s with scenarios: normal, vacant-room waste, anomaly,
  sensor failure, offline device, failed command, command timeout; 7-day history backfill.
* **Correct energy accounting** — trapezoidal kWh into 15-minute buckets, no invented data across
  gaps, configurable flat / time-of-use tariffs and grid emission factor.
* **Security** — JWT auth with viewer/operator/admin roles, PBKDF2 password hashing, login rate
  limiting, hashed device keys, input validation everywhere, production refuses default secrets.

## Repository layout

```
backend/        FastAPI app (app/), tests (tests/), Dockerfile
frontend/       React + TypeScript + Vite + Tailwind + Recharts, unit tests, Playwright e2e
firmware/esp32/ reference ESP32 Arduino sketch (not yet hardware-tested)
tools/          esp32_emulator.py (stdlib only)
docs/           architecture, API, hardware, safety, ML, energy maths, demo, implementation status
```

## Quick start

### Option A — Docker Compose (recommended)

```bash
cp .env.example .env          # edit SECRET_KEY / ADMIN_PASSWORD for anything beyond a local demo
docker compose up --build
```

* Dashboard: <http://localhost:8080> — sign in with `admin` / `guardian-demo` (from `.env`)
* API + Swagger UI: <http://localhost:8000/docs>

Behind a TLS-intercepting corporate proxy, pass its CA to the build:
`EXTRA_CA_FILE=/path/ca.pem docker compose -f docker-compose.yml -f docker-compose.proxy-ca.yml up --build`

### Option B — local development (Python ≥ 3.11, Node ≥ 20)

```bash
make setup            # backend/.venv + pip install, frontend npm ci
make backend          # terminal 1: API on http://127.0.0.1:8000
make frontend         # terminal 2: dashboard on http://127.0.0.1:5173 (proxies /api and /ws)
```

Without `make`:

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.asgi:app --host 127.0.0.1 --port 8000
cd frontend && npm ci && npm run dev
```

On first start the backend creates the SQLite database, the admin user, the simulated demo
campus with 7 days of simulated history, trains the anomaly model (≈2 s) and starts the simulator.

## Tests

```bash
make test-backend     # ruff + pytest            (cd backend && .venv/bin/pytest)
make test-frontend    # tsc + vitest              (cd frontend && npm run typecheck && npm test)
make e2e              # Playwright against a running stack; E2E_BASE_URL=http://localhost:8080 for Docker
```

Latest local run (2026-10-14):

| Suite | Result |
|---|---|
| Backend `pytest` (energy maths, decision engine, ML, telemetry, API/auth/validation, ESP32 protocol, end-to-end simulator scenarios, config) | **104 passed** |
| Backend `ruff` | clean |
| Frontend `tsc` + `vitest` (formatters, components, login→dashboard, decision explanation, commands, alerts, settings, live-refresh regression) | **18 passed** |
| Frontend production build | OK |
| Playwright E2E against the Docker Compose stack (live data, decision checks, sensor-failure scenario, auto-mode command acknowledgement) | **4 passed** |

A CI workflow (`.github/workflows/ci.yml`) runs the same suites.

## Demo

See **[docs/DEMO.md](docs/DEMO.md)** for a 14-step walkthrough (wastage → dry-run → simulated
shutdown → savings, anomaly, sensor failure, offline device, failed/timed-out commands, ESP32
emulator, hardware safety gate).

## Documentation

| Doc | Contents |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | components, sequence and data-model diagrams |
| [SAFETY.md](docs/SAFETY.md) | decision rules, command gate, hardware enablement procedure, auth |
| [HARDWARE.md](docs/HARDWARE.md) | BOM, wiring, provisioning, full device HTTP protocol, emulator |
| [API.md](docs/API.md) | all REST endpoints, WebSocket messages |
| [ML.md](docs/ML.md) | features, synthetic data, training, metrics and their limits |
| [ENERGY.md](docs/ENERGY.md) | kWh integration, waste, tariffs, carbon, savings estimate |
| [IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) | progress log and known limitations |

## Configuration

All settings are environment variables (see `.env.example`). Security-relevant switches —
`REAL_SWITCHING_ENABLED`, `SECRET_KEY`, `ADMIN_PASSWORD` — are environment-only. Operational
settings (automation mode, tariff, carbon factor, timezone, thresholds) are editable by admins
in the Settings page and stored in the database.

## Honest limitations

* **No physical hardware was used.** The ESP32 sketch is untested on real devices; the protocol
  is tested with the emulator and backend tests.
* **ML metrics are on synthetic data** from the project's own generator (F1 0.775, ROC-AUC 0.995,
  voltage-fault recall only 59 %). They demonstrate a working, reproducible pipeline — not
  real-world accuracy.
* **Savings are estimates** based on a stated counterfactual; the only measured quantities are
  energy and energy consumed while the occupancy sensor reported "vacant".
* PIR occupancy sensing misses motionless occupants; minimum vacancy times mitigate but do not
  eliminate this.
* SQLite + `create_all` (no migrations) suits a single-site deployment; use PostgreSQL + Alembic
  for larger ones. Login rate limiting is in-memory (single process).

More in [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md).
