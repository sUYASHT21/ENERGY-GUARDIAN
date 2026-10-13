"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .api import auth, devices, esp32, operations, rooms
from .api.deps import user_from_token
from .clock import Clock
from .config import Settings, get_settings
from .context import AppContext
from .database import Database
from .logging_config import configure_logging
from .seed import default_scenarios, ensure_admin, seed_demo
from .services import analytics, ml_service, monitor
from .services.events import log_event
from .simulation.engine import Simulator
from .simulation.history import backfill

log = logging.getLogger("seg")
API_PREFIX = "/api/v1"


def bootstrap(ctx: AppContext) -> None:
    """Create tables, seed data, load or train the anomaly model. Safe to call repeatedly."""
    ctx.db.create_all()
    with ctx.db.session() as db:
        ensure_admin(ctx, db)
        if ctx.settings.seed_demo_data and ctx.settings.simulation_enabled:
            if seed_demo(ctx, db):
                db.flush()
                n = backfill(db, now=ctx.clock.now(), days=ctx.settings.history_backfill_days)
                if n:
                    log_event(db, "simulation", f"Backfilled {n} simulated historical energy records "
                                                f"({ctx.settings.history_backfill_days} days)", now=ctx.clock.now())
    with ctx.db.session() as db:
        if not ml_service.load_active(ctx, db) and ctx.settings.ml_autotrain:
            log.info("No active anomaly model — training one on synthetic data")
            try:
                ml_service.train_and_activate(ctx, db, actor="system")
            except Exception:  # pragma: no cover - fallback keeps the system usable
                log.exception("Model training failed; rule-based fallback active")


async def _monitor_loop(ctx: AppContext) -> None:
    interval = ctx.settings.monitor_interval_seconds
    while True:
        try:
            await asyncio.to_thread(monitor.run_once, ctx)
            if ctx.bus.subscriber_count:
                summary = await asyncio.to_thread(_summary, ctx)
                ctx.bus.publish({"type": "summary", "data": summary})
        except Exception:  # pragma: no cover
            log.exception("monitor loop error")
        await asyncio.sleep(interval)


def _summary(ctx: AppContext) -> dict:
    with ctx.db.session() as db:
        return analytics.summary(ctx, db)


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    db = Database(settings.database_url)
    ctx = AppContext(settings=settings, db=db, clock=clock or Clock())
    if settings.simulation_enabled:
        ctx.simulator = Simulator(ctx, seed=settings.simulation_seed, default_scenarios=default_scenarios())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx.bus.bind_loop(asyncio.get_running_loop())
        ctx.started_at = ctx.clock.now()
        await asyncio.to_thread(bootstrap, ctx)
        tasks: list[asyncio.Task] = []
        if settings.background_tasks_enabled:
            tasks.append(asyncio.create_task(_monitor_loop(ctx)))
            if ctx.simulator and settings.simulation_autostart:
                ctx.simulator.start()
        log.info("%s %s started (env=%s, simulation=%s, real_switching=%s)", settings.app_name, __version__,
                 settings.app_env, settings.simulation_enabled, settings.real_switching_enabled)
        yield
        if ctx.simulator:
            await ctx.simulator.stop()
        for t in tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        db.engine.dispose()

    app = FastAPI(
        title="Smart Energy Guardian API",
        version=__version__,
        description="AI-based IoT energy management for classrooms, laboratories and hostels. "
                    "User endpoints require a Bearer token from `/api/v1/auth/login`; device endpoints "
                    "under `/api/v1/esp32` use `X-Device-Id` + `X-Device-Key` headers.",
        lifespan=lifespan,
    )
    app.state.ctx = ctx
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return JSONResponse({"detail": "validation error", "errors": errors}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):  # pragma: no cover - last resort
        log.exception("Unhandled error: %s", exc)
        return JSONResponse({"detail": "internal server error"}, status_code=500)

    api = APIRouter(prefix=API_PREFIX)

    @api.get("/health", tags=["system"])
    def health():
        return {"status": "ok", "version": __version__, "time": ctx.clock.now().isoformat(),
                "simulation_running": bool(ctx.simulator and ctx.simulator.running),
                "real_switching_enabled": settings.real_switching_enabled, "ml_method": ctx.anomaly.method}

    for r in (auth.router, rooms.router, devices.router, operations.router, esp32.router):
        api.include_router(r)
    app.include_router(api)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket, token: str = Query(default="")):
        """Live updates. Authenticate with ``/ws?token=<access token>``."""
        try:
            with ctx.db.session() as s:
                user_from_token(ctx, s, token)
        except Exception:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        q = ctx.bus.subscribe()
        try:
            await websocket.send_json({"type": "summary", "data": await asyncio.to_thread(_summary, ctx)})
            while True:
                msg = await q.get()
                await websocket.send_json(msg)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            ctx.bus.unsubscribe(q)

    return app
