# Smart Energy Guardian — common tasks
PY := backend/.venv/bin/python

.PHONY: setup backend frontend dev test test-backend test-frontend e2e lint build up down emulator

setup:            ## create backend venv + install frontend deps
	python3 -m venv backend/.venv
	$(PY) -m pip install -r backend/requirements-dev.txt
	cd frontend && npm ci

backend:          ## run the API (http://127.0.0.1:8000, docs at /docs)
	cd backend && .venv/bin/uvicorn app.asgi:app --reload --host 127.0.0.1 --port 8000

frontend:         ## run the dashboard dev server (http://127.0.0.1:5173)
	cd frontend && npm run dev -- --host 127.0.0.1

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/ruff check app tests && .venv/bin/pytest

test-frontend:
	cd frontend && npm run typecheck && npm test

e2e:              ## requires a running stack (make backend + make frontend, or docker compose up)
	cd frontend && npx playwright test

build:
	cd frontend && npm run build

up:
	docker compose up -d --build

down:
	docker compose down

emulator:         ## register an emulated ESP32 and stream telemetry
	$(PY) tools/esp32_emulator.py --register
