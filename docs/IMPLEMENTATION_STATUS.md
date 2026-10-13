# Implementation Status — Smart Energy Guardian

This file is the resume point for development. Update it at the end of every stage.

## Plan (stages)

| # | Stage | Status |
|---|-------|--------|
| 0 | Repo inspection, plan, scaffolding | in progress |
| 1 | Backend core: config, DB models, schemas, auth, logging | pending |
| 2 | Energy calculations (kWh integration, tariffs, savings, carbon) | pending |
| 3 | Deterministic decision (safety) engine | pending |
| 4 | ML pipeline (synthetic data, Isolation Forest, rule fallback, metrics) | pending |
| 5 | Telemetry ingestion, alerts, commands (ack/timeout), device status, event log | pending |
| 6 | Device adapters + ESP32 HTTP interface + firmware sketch + emulator | pending |
| 7 | Simulation engine + scenarios + history backfill | pending |
| 8 | REST API + WebSocket | pending |
| 9 | Backend tests (unit + integration) | pending |
| 10 | Frontend (React/TS/Vite/Tailwind/Recharts) | pending |
| 11 | Frontend tests | pending |
| 12 | Docker Compose, e2e smoke test | pending |
| 13 | Documentation (README, architecture, API, hardware, safety, ML, demo) | pending |

## Key design decisions

- Monorepo: `backend/` (FastAPI), `frontend/` (Vite React), `firmware/esp32/`, `tools/`, `docs/`.
- SQLite + SQLAlchemy 2 (sync sessions); tables created via `create_all` on startup.
- Data source label on every telemetry/energy/savings row: `simulation` | `emulator` | `hardware`,
  derived server-side from the registered device kind (never trusted from the payload).
- Commands use one queue + acknowledgement protocol for both simulated and ESP32 devices.
- Automation modes: `recommend`, `dry_run` (default), `auto`. Real (hardware) switching additionally
  requires env `REAL_SWITCHING_ENABLED=true` AND the device being marked `control_validated` by an admin.
- Anomaly results are inputs to the decision engine only — they never authorize a shutdown alone.
- A `Clock` abstraction allows deterministic tests of freshness/timeouts.

## Log
