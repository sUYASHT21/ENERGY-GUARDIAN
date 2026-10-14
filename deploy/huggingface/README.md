---
title: Energy Guardian API
emoji: ⚡
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 8000
pinned: false
short_description: FastAPI backend of Smart Energy Guardian (IoT energy management)
---

# Smart Energy Guardian — backend API

FastAPI backend (simulator, safety decision engine, ML anomaly detection, ESP32 device API).
This Space is deployed automatically from the GitHub repository by
`.github/workflows/deploy-hf-space.yml` — edit the code there, not here.

* Health: `/api/v1/health`
* API docs: `/docs`

Configuration lives in this Space's **Settings → Variables and secrets** (see `docs/DEPLOYMENT.md`
in the GitHub repository).
