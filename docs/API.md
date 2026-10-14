# REST & WebSocket API

Interactive OpenAPI documentation is served by the backend at **`/docs`** (Swagger UI) and
`/openapi.json`. This page summarises the 57 endpoints.

## Authentication

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' -d '{"username":"admin","password":"guardian-demo"}' | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/dashboard/summary
```

Roles: **V** viewer (read), **O** operator, **A** admin. Device endpoints use
`X-Device-Id` + `X-Device-Key`. Errors: `{"detail": "..."}`; validation errors (422):
`{"detail": "validation error", "errors": [{"loc": [...], "msg": "...", "type": "..."}]}`.

## Endpoints

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/api/v1/health` | public | liveness, simulation/real-switching flags, ML method |
| POST | `/api/v1/auth/login` | public | JWT access token (rate limited) |
| GET | `/api/v1/auth/me` | V | current user |
| GET / POST | `/api/v1/users` | A | list / create users |
| PATCH | `/api/v1/users/{id}` | A | role, active flag, password |
| GET / POST | `/api/v1/rooms` | V / O | list / create rooms |
| GET | `/api/v1/rooms/{id}` | V | room + appliances **with live decision explanations** + devices + schedules |
| PATCH / DELETE | `/api/v1/rooms/{id}` | O | update / delete |
| POST | `/api/v1/rooms/{id}/override` | O | manual override `{enabled, minutes?, reason}` |
| GET / POST | `/api/v1/appliances` | V / O | list (`?room_id=`) / create |
| GET | `/api/v1/appliances/{id}` | V | appliance + decision |
| PATCH / DELETE | `/api/v1/appliances/{id}` | O | update (policy, override) / delete |
| GET / POST | `/api/v1/schedules` | V / O | list (`?room_id=`) / create |
| PATCH / DELETE | `/api/v1/schedules/{id}` | O | update / delete |
| GET | `/api/v1/devices` | V | devices with health score |
| POST | `/api/v1/devices` | A | register → returns API key **once** |
| GET / PATCH / DELETE | `/api/v1/devices/{id}` | V / O* / A | detail / update (*`control_validated` admin only) / delete |
| POST | `/api/v1/devices/{id}/rotate-key` | A | new API key |
| GET | `/api/v1/dashboard/summary` | V | live power, energy, waste, estimated savings, cost, CO₂, counts, modes |
| GET | `/api/v1/dashboard/history?range=24h\|7d\|30d&room_id=` | V | energy/waste/cost series split by data source |
| GET | `/api/v1/dashboard/rooms?hours=` | V | per-room breakdown |
| GET | `/api/v1/dashboard/live-power?minutes=&room_id=` | V | total power time series |
| GET | `/api/v1/dashboard/overview` | V | room grid with appliance states |
| GET | `/api/v1/telemetry?appliance_id=&room_id=&minutes=` | V | raw readings with anomaly scores |
| GET | `/api/v1/decisions` | V | latest decision per appliance |
| GET | `/api/v1/alerts?status=open\|resolved\|all&alert_type=&severity=&room_id=` | V | alerts |
| POST | `/api/v1/alerts/{id}/acknowledge` | O | acknowledge |
| POST | `/api/v1/alerts/{id}/resolve` | O | resolve `{note?}` |
| GET | `/api/v1/commands?status=&appliance_id=` | V | command log |
| POST | `/api/v1/commands` | O | manual command `{appliance_id, action: on\|off, dry_run?, reason?, confirm_essential?}` — passes the safety gate; blocked commands return `status: "blocked"` + reason |
| GET | `/api/v1/events?category=&level=&before_id=` | V | audit log |
| GET | `/api/v1/settings` | V | runtime settings + read-only environment flags |
| PUT | `/api/v1/settings` | A | partial update (unknown / env-only keys → 422) |
| GET | `/api/v1/ml/status` | V | method, active model, metrics, registry, disclaimers |
| POST | `/api/v1/ml/train` | A | `{seed, n_estimators, contamination}` → train, evaluate, activate |
| POST | `/api/v1/ml/models/{id}/activate` | A | switch model |
| GET | `/api/v1/ml/scores?appliance_id=&minutes=&only_anomalies=` | V | recent scores |
| GET | `/api/v1/simulation` | V | state, scenarios, room assignments |
| POST | `/api/v1/simulation/start` · `/stop` · `/reset` | O | control |
| POST | `/api/v1/simulation/scenario` | O | `{room_id, scenario}` |
| POST | `/api/v1/simulation/tick?steps=` | O | advance manually |
| POST | `/api/v1/esp32/telemetry` | device | ingest; response carries pending commands |
| POST | `/api/v1/esp32/heartbeat` | device | health only |
| GET | `/api/v1/esp32/commands` | device | pending commands |
| POST | `/api/v1/esp32/commands/{id}/ack` | device | `{success, relay_on?, error?}` |
| GET | `/api/v1/esp32/config` | device | channel map |

See `docs/HARDWARE.md` for device payloads.

## WebSocket `/ws?token=<JWT>`

Server → client JSON messages `{"type": ..., "data": ...}`, published only after the
corresponding database transaction commits:

| type | when |
|---|---|
| `summary` | on connect and every monitor cycle (~3 s): same body as `/dashboard/summary` |
| `telemetry` | each ingested payload (device, room, per-appliance power/state/anomaly) |
| `alert` | alert created / acknowledged / resolved |
| `command` | command created / sent / acknowledged / failed / timed out |
| `device`, `room`, `appliance` | state changes |
| `settings`, `simulation`, `event` | configuration, simulator, audit events |

An invalid token closes the socket with code 4401.
