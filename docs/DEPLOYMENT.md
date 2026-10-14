# Deployment

The system has two parts with different hosting needs:

| Part | Needs | Host |
|---|---|---|
| Frontend (static React build) | static files + SPA routing | **Vercel** (`vercel.json` at repo root) |
| Backend (FastAPI) | a long-running process (simulator, monitor loop), WebSockets, a writable SQLite file | **Render / Railway / Fly.io / any VM** (Docker) — *not* Vercel serverless |

Vercel serverless functions are short-lived and stateless, so the backend's background
simulation, live WebSocket stream and SQLite database cannot run there.

## 1. Backend on Render (free tier works)

1. Render dashboard → **New → Blueprint** → select this GitHub repository (uses `render.yaml`).
2. Set `ADMIN_PASSWORD` (≥ 10 characters — production refuses weak/default secrets) and
   `CORS_ORIGINS` (your Vercel URL, e.g. `https://energy-guardian.vercel.app`).
   `SECRET_KEY` is generated automatically; `CORS_ORIGIN_REGEX` already allows `*.vercel.app` previews.
3. Deploy, then open `https://<service>.onrender.com/api/v1/health`.

Free-tier notes: the service sleeps when idle (first request takes ~1 min) and the disk is
ephemeral — the demo campus, history and model are re-created on each restart. Attach a
persistent disk at `/app/data` (paid) to keep data.

## 2. Frontend on Vercel

1. Vercel dashboard → **Add New → Project** → import this GitHub repository.
   Keep the root directory as the repository root (settings come from `vercel.json`).
2. **Environment Variables:** `VITE_API_URL = https://<service>.onrender.com` (no trailing slash).
3. Deploy. The dashboard calls the API and opens the WebSocket at `VITE_API_URL` directly.

CLI alternative (from the repository root):

```bash
npm i -g vercel
vercel login
vercel --prod --build-env VITE_API_URL=https://<service>.onrender.com
```

## 3. Single host (Docker Compose)

Everything on one machine (nginx serves the frontend and proxies `/api` and `/ws`):

```bash
cp .env.example .env    # set SECRET_KEY / ADMIN_PASSWORD
docker compose up -d --build
```

Put a TLS reverse proxy (Caddy, Traefik, nginx + certbot) in front for anything public.
