# Deployment — 100 % free stack (no credit card)

```mermaid
flowchart LR
  U[Browser] -->|HTTPS| V[Vercel Hobby<br/>React dashboard]
  U -->|REST + WebSocket| H[Hugging Face Space<br/>Docker · FastAPI backend<br/>simulator · monitor · ML · ESP32 API]
  E[ESP32 / emulator] -->|HTTPS| H
  H -->|SQL over TLS<br/>Session pooler| S[(Supabase Free<br/>Postgres)]
  P[UptimeRobot Free<br/>ping every 5 min] -->|/api/v1/health| H
  G[GitHub main] -->|auto-deploy| V
  G -->|GitHub Action| H
```

| Part | Service | Cost |
|---|---|---|
| Dashboard | **Vercel** Hobby | free, no card |
| Backend | **Hugging Face Spaces** — Docker, CPU basic | free, no card |
| Database | **Supabase** Free — use the **Session pooler** connection | free, no card |
| Keep-awake | **UptimeRobot** Free | free, no card |

> **Do not** buy Supabase's "IPv4 add-on". It is only needed for the *Direct connection*; the
> **Session pooler** connection used here works over IPv4 for free.

Why a separate backend host at all? The backend must run continuously (3-second simulator and
safety-monitor loops, WebSockets). Vercel functions stop after each request and Supabase does not
run Python, so the FastAPI app lives in a free Docker Space.

Free-plan behaviour to know: free Spaces sleep after a period without visits and Supabase pauses a
project after a week of inactivity — the UptimeRobot ping keeps the Space awake, and the awake
backend writes to Supabase constantly, so neither happens. Free Spaces must be **public** for the
dashboard to reach them (only the backend code is visible; secrets stay private in the Space
settings). Plans change over time — check limits when you sign up.

---

## Step 1 — Supabase connection string

1. Supabase dashboard → your project → **Connect** (top bar).
2. Choose **Session pooler** (not "Direct connection"). Copy the URI:
   `postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-<n>-<region>.pooler.supabase.com:5432/postgres`
3. Replace `[YOUR-PASSWORD]` with your database password. Special characters (`@ ! : / # ?`) can
   be pasted as-is — the backend encodes them automatically.

The backend creates all tables on first start; browse them later under **Table Editor**.
The project URL and publishable key are **not** needed — the backend connects to Postgres directly.

## Step 2 — Hugging Face Space (backend)

1. Create a free account at <https://huggingface.co> (no card).
2. **New → Space**: name `energy-guardian-api`, SDK **Docker** → *Blank*, hardware
   **CPU basic · Free**, visibility **Public** → Create.
3. Space → **Settings → Variables and secrets**:

   | Type | Name | Value |
   |---|---|---|
   | Secret | `DATABASE_URL` | the Session pooler URI from step 1 |
   | Secret | `SECRET_KEY` | a long random string, e.g. output of `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
   | Secret | `ADMIN_PASSWORD` | your dashboard login password (≥ 10 characters) |
   | Variable | `APP_ENV` | `production` |
   | Variable | `MODEL_DIR` | `/tmp/models` |
   | Variable | `CORS_ORIGINS` | your Vercel URL from step 4, e.g. `https://energy-guardian.vercel.app` |
   | Variable | `CORS_ORIGIN_REGEX` | `https://.*\.vercel\.app` |

4. Hugging Face → **Settings → Access Tokens** → create a token with **Write** permission.

## Step 3 — Connect GitHub → Space (automatic deploys)

GitHub repository → **Settings → Secrets and variables → Actions**:

* **Secrets** tab → `HF_TOKEN` = the write token from step 2.4
* **Variables** tab → `HF_SPACE` = `<your-hf-username>/energy-guardian-api`

Then GitHub → **Actions → Deploy backend to Hugging Face Space → Run workflow** (afterwards it runs
on every push to `main` that touches `backend/`). The Space builds (≈ 3–5 min the first time);
check `https://<your-hf-username>-energy-guardian-api.hf.space/api/v1/health`.

## Step 4 — Vercel (dashboard)

1. <https://vercel.com> → sign in with GitHub → **Add New → Project** → import this repository
   (leave Root Directory as the repo root; settings come from `vercel.json`).
2. **Environment Variables**: `VITE_API_URL` = `https://<your-hf-username>-energy-guardian-api.hf.space`
3. **Deploy**, open the URL and sign in as `admin` with your `ADMIN_PASSWORD`.
4. Put the Vercel URL into the Space variable `CORS_ORIGINS` (step 2.3) if you have not yet.

## Step 5 — Keep it awake (UptimeRobot)

<https://uptimerobot.com> → free account → **New monitor** → HTTP(s) →
`https://<your-hf-username>-energy-guardian-api.hf.space/api/v1/health`, interval **5 minutes**.
(Backup without another account: set the repository variable `BACKEND_URL` to the same base URL
and `.github/workflows/keepalive.yml` pings every 10 minutes.)

## Step 6 — ESP32 / emulator

Point devices at the Space URL (`SEG_BASE_URL` in the firmware `config.h`), or:
`python tools/esp32_emulator.py --base-url https://<user>-energy-guardian-api.hf.space --register --admin-password <ADMIN_PASSWORD>`

---

## Behaviour on restart / redeploy

* All data (rooms, telemetry, history, alerts, commands, users, settings) lives in Supabase and is
  kept; the demo campus is not re-seeded.
* The Space disk is ephemeral: on boot the backend rebuilds the active ML model from the parameters
  stored in Supabase (deterministic — identical model and metrics; tested).
* Simulator scenarios reset to their defaults.

## Managing it

| Task | Where |
|---|---|
| Deploy a change | push to `main` → Vercel redeploys the dashboard, the GitHub Action redeploys the Space |
| Backend logs | Space → **Logs** tab |
| Dashboard deployments | Vercel → project → **Deployments** |
| Browse / edit data | Supabase → **Table Editor** / **SQL Editor** |
| Backup | `pg_dump "<DATABASE_URL>" > backup.sql` (Supabase Free has no automatic backups) |
| Reset all data | Supabase SQL Editor: `drop schema public cascade; create schema public;` → restart the Space |
| Change admin password | `PATCH /api/v1/users/{id}` via `<space-url>/docs` (`ADMIN_PASSWORD` only seeds the first admin) |

## Security checklist

* Never commit `DATABASE_URL` or passwords — they belong only in the Space secrets.
* If a database password was ever shared in chat or email, reset it: Supabase → **Project Settings
  → Database → Reset database password**, then update the `DATABASE_URL` secret.
* `REAL_SWITCHING_ENABLED` stays `false` (default) until real hardware is validated (docs/SAFETY.md).

## Alternatives

* **Render** free web service: `render.yaml` blueprint is included (same env vars; Render may ask
  for payment details on some accounts — use Hugging Face if it does).
* **Single machine:** `docker compose up -d --build` (frontend + backend + local SQLite, or set
  `DATABASE_URL` to Supabase).

## Testing against Postgres locally

```bash
docker run -d --name seg-pg -e POSTGRES_PASSWORD=pgtest -e POSTGRES_DB=seg -p 5433:5432 postgres:16-alpine
cd backend && TEST_DATABASE_URL=postgresql://postgres:pgtest@127.0.0.1:5433/seg .venv/bin/pytest
```
