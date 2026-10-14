# Deployment — free cloud stack (Vercel + Render + Supabase)

```mermaid
flowchart LR
  U[Browser] -->|HTTPS| V[Vercel<br/>React dashboard]
  U -->|REST + WebSocket| R[Render<br/>FastAPI backend<br/>simulator · monitor · ML · ESP32 API]
  E[ESP32 / emulator] -->|HTTPS| R
  R -->|SQL over TLS| S[(Supabase<br/>Postgres)]
  P[UptimeRobot<br/>ping every 5 min] -->|/api/v1/health| R
```

| Part | Service (free plan) | Why this host |
|---|---|---|
| Dashboard | **Vercel** | static React build, global CDN, auto-deploy from `main` |
| Backend | **Render** web service (Docker) | needs a *long-running* process (3 s simulator/monitor loops, WebSockets) — Vercel functions can't do that |
| Database | **Supabase** Postgres | persistent, managed, web table editor; survives backend restarts |
| Keep-awake | **UptimeRobot** (or cron-job.org) | Render free instances sleep after ~15 min without traffic |

Everything deploys automatically when you push to `main`. Free-plan limits change — check them when
you sign up. Known ones: Render free instances sleep when idle (hence the pinger); Supabase pauses a
project after 7 days without activity (the running backend writes constantly, so this does not
trigger while it is awake); Vercel Hobby is for non-commercial use.

---

## Step 1 — Supabase (database)

1. <https://supabase.com> → **New project**. Pick a region close to your Render region, set a
   **database password** (save it).
2. When it is ready, click **Connect** (top bar) → **Session pooler** → copy the URI. It looks like
   `postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:5432/postgres`
   * Replace `[YOUR-PASSWORD]`. If it contains special characters (`@ : / ? # %`), URL-encode them
     (e.g. `@` → `%40`).
   * Use the **Session pooler** URI, not "Direct connection": the direct host is IPv6-only on the
     free plan, while Render connects over IPv4.
3. Nothing else to do — the backend creates its tables on first start. Afterwards you can browse
   `rooms`, `alerts`, `telemetry`, `commands`, … in **Table Editor**.

> Security: the app talks to Postgres directly with this URI; it does not use Supabase's public
> REST API. Keep the URI secret (Render environment variable only). Leaving Row Level Security off
> is fine because the anon REST key is never used — or enable RLS on all tables to lock the REST
> API down completely; the backend's direct connection is unaffected.

## Step 2 — Render (backend)

1. <https://render.com> → sign in with GitHub → **New → Blueprint** → select this repository.
   Render reads `render.yaml` and creates `energy-guardian-api`.
2. Fill in the variables it asks for:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | the Supabase Session pooler URI from step 1 |
   | `ADMIN_PASSWORD` | a strong password (≥ 10 chars) — your dashboard login |
   | `CORS_ORIGINS` | your Vercel URL from step 3 (you can fill it in after step 3), e.g. `https://energy-guardian.vercel.app` |

   `SECRET_KEY` is generated automatically; `APP_ENV=production` refuses weak/default secrets;
   `REAL_SWITCHING_ENABLED=false` keeps hardware switching off; `CORS_ORIGIN_REGEX` already allows
   `*.vercel.app` preview URLs.
3. Deploy. Check `https://<your-service>.onrender.com/api/v1/health` → `{"status":"ok",…}`.
   First boot seeds the demo campus + 7 days of simulated history into Supabase and trains the
   model (≈ 1 min including the image build).
4. API docs: `https://<your-service>.onrender.com/docs`.

## Step 3 — Vercel (dashboard)

1. <https://vercel.com> → sign in with GitHub → **Add New → Project** → import this repository.
   Leave **Root Directory** as the repository root (build settings come from `vercel.json`).
2. **Environment Variables** → add `VITE_API_URL` = `https://<your-service>.onrender.com`
   (no trailing slash).
3. **Deploy** → open the URL, sign in as `admin` with your `ADMIN_PASSWORD`.
4. Put this URL into Render's `CORS_ORIGINS` (step 2) if you have not yet; Render redeploys.

## Step 4 — Keep the backend awake (UptimeRobot)

1. <https://uptimerobot.com> → free account → **New monitor** → type **HTTP(s)**.
2. URL: `https://<your-service>.onrender.com/api/v1/health`, interval **5 minutes**.
3. Bonus: it emails you if the backend goes down.

Backup option without another account: this repo has `.github/workflows/keepalive.yml` — add a
repository variable `BACKEND_URL` (GitHub → Settings → Secrets and variables → Actions →
Variables) and it pings every 10 minutes (GitHub may delay scheduled runs, so prefer UptimeRobot).

## Step 5 — Connect real or emulated ESP32s

Point devices at the Render URL (`SEG_BASE_URL` in `firmware/esp32/.../config.h`, or
`python tools/esp32_emulator.py --base-url https://<your-service>.onrender.com --register
--admin-password <ADMIN_PASSWORD>`). See [HARDWARE.md](HARDWARE.md).

---

## What happens on a restart / redeploy

* Rooms, devices, telemetry, energy history, alerts, commands, users and settings live in Supabase
  and are untouched; the demo campus is **not** re-seeded.
* The model registry lives in Supabase; Render's disk is ephemeral, so on boot the backend rebuilds
  the active model from its stored parameters (training is deterministic: same seed → identical
  model and metrics; tested in `tests/test_ml.py`).
* The simulator's per-room scenarios reset to their defaults (in-memory by design).

## Managing it

| Task | Where |
|---|---|
| Deploy a change | push to `main` → Vercel and Render redeploy automatically |
| Logs | Render → service → **Logs**; Vercel → project → **Deployments** |
| Browse / edit data | Supabase → **Table Editor** or **SQL Editor** |
| Backups | Supabase free has no automatic backups — export with `pg_dump "<DATABASE_URL>" > backup.sql` |
| Reset everything | Supabase SQL Editor: `drop schema public cascade; create schema public;` then restart the Render service |
| Rotate admin password | `PATCH /api/v1/users/{id}` with a new password (via `/docs`); the `ADMIN_PASSWORD` env var only seeds the first admin |

## Alternative: single machine (Docker Compose)

Runs frontend (nginx), backend and a local SQLite database on one host:

```bash
cp .env.example .env    # set SECRET_KEY / ADMIN_PASSWORD (optionally DATABASE_URL=Supabase)
docker compose up -d --build
```

## Testing against Postgres locally

```bash
docker run -d --name seg-pg -e POSTGRES_PASSWORD=pgtest -e POSTGRES_DB=seg -p 5433:5432 postgres:16-alpine
cd backend && TEST_DATABASE_URL=postgresql://postgres:pgtest@127.0.0.1:5433/seg .venv/bin/pytest
```

CI runs the backend suite on both SQLite and Postgres.
