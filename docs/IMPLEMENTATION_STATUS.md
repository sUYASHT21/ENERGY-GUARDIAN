# Implementation Status — Smart Energy Guardian

This file is the resume point for development. Update it at the end of every stage.

## Stages

| # | Stage | Status |
|---|-------|--------|
| 0 | Repo inspection, plan, scaffolding | done |
| 1 | Backend core: config, DB models, schemas, auth, logging | done |
| 2 | Energy calculations (kWh integration, tariffs, savings, carbon) | done |
| 3 | Deterministic decision (safety) engine | done |
| 4 | ML pipeline (synthetic data, Isolation Forest, rule fallback, metrics) | done |
| 5 | Telemetry ingestion, alerts, commands (ack/timeout), device status, event log | done |
| 6 | Device adapters + ESP32 HTTP interface + firmware sketch + emulator | done (firmware not hardware-tested) |
| 7 | Simulation engine + scenarios + history backfill | done |
| 8 | REST API (57 endpoints) + WebSocket | done |
| 9 | Backend tests | done — 104 passing |
| 10 | Frontend (React/TS/Vite/Tailwind/Recharts), 12 pages | done |
| 11 | Frontend tests (vitest) + Playwright E2E | done — 18 unit + 4 E2E passing |
| 12 | Docker Compose, CI workflow | done — stack built and E2E-verified locally |
| 13 | Documentation | done |

## How to resume

```bash
make setup && make test        # all suites should pass
make backend & make frontend   # or: docker compose up --build
```

Key entry points: `backend/app/main.py` (app factory, lifespan, WebSocket),
`backend/app/services/decision_engine.py` (safety logic), `backend/app/services/telemetry.py`
(ingestion), `backend/app/simulation/engine.py` (simulator), `frontend/src/App.tsx`.

## Key design decisions

- Monorepo: `backend/` (FastAPI), `frontend/` (Vite React), `firmware/esp32/`, `tools/`, `docs/`.
- SQLite + SQLAlchemy 2 (sync sessions, WAL); tables created via `create_all` on startup.
- Data source label on every telemetry/energy/savings row: `simulation` | `emulator` | `hardware`,
  derived server-side from the registered device kind (never trusted from the payload).
- One command queue + acknowledgement protocol for simulated, emulated and ESP32 devices; the
  simulator calls the same `fetch_pending` / `acknowledge` functions as the HTTP endpoints.
- Automation modes: `recommend`, `dry_run` (default), `auto`. Hardware switching additionally
  requires env `REAL_SWITCHING_ENABLED=true` AND the device marked `control_validated` by an admin.
- Anomaly results are context only — they never authorize a shutdown.
- Energy in 15-minute UTC buckets (aligns with half-hour timezone offsets such as IST).
- WebSocket messages are published only after DB commit (SQLAlchemy `after_commit` outbox).
- `Clock` abstraction → deterministic tests of freshness, timeouts, vacancy and savings.

## Findings fixed during development (from tests)

1. ML: single-reading anomaly injection missed *sustained* over-consumption → anomaly episodes.
2. ML: normal-only training (novelty detection) collapsed recall to 0.24 (Isolation Forest cannot
   split on features constant in normal data) → unsupervised training with unlabelled anomalies.
3. Login rate limiter was module-global (leaked across app instances) → per-app context.
4. Frontend `useApi` throttle left a stale "pending" ref after StrictMode remount, so pages stopped
   live-refreshing → rewritten as cancel/reschedule effect, with a regression test proven to fail
   on the old code.
5. Top-bar indicators depended solely on the WebSocket → HTTP polling fallback.
6. nginx resolved the backend only at startup → lazy DNS resolution (survives backend restarts).

## Known limitations / future work

- ESP32 firmware not compiled or run on hardware (no toolchain/hardware in the build environment).
- ML evaluated only on synthetic data; voltage-fault recall 59 %. Needs labelled field data.
- No database migrations (Alembic) — schema changes require a fresh DB in this version.
- In-memory login rate limiting and event bus → single backend process (no horizontal scaling).
- No HTTPS termination in the compose file; put a TLS reverse proxy in front for real deployments
  (device keys and JWTs must not travel over plain HTTP outside a lab network).
- Occupancy is binary per room (PIR); people counting/camera sensors could replace it through a
  new payload parser.
- History backfill is simulated; charts mix it only with clearly separated per-source totals.

## Log

- 2026-10-13: stages 0–9 (backend, 101 tests), ML training fixes.
- 2026-10-14: frontend + tests, Playwright E2E, firmware, emulator, Docker, CI, docs; final run
  104 backend / 18 frontend / 4 E2E passing.
