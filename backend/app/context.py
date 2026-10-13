"""Application context: shared services wired together once per app instance."""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from .clock import Clock
from .config import Settings
from .database import Database
from .ml.model import AnomalyService

if TYPE_CHECKING:
    from .simulation.engine import Simulator

log = logging.getLogger(__name__)


class EventBus:
    """Fan-out of JSON-able messages to WebSocket subscribers. ``publish`` is thread-safe."""

    def __init__(self, max_queue: int = 500):
        self._subs: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._max_queue = max_queue
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    def publish(self, msg: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._fanout, msg)
        except RuntimeError:  # loop shutting down
            pass

    def _fanout(self, msg: dict) -> None:
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            if q.full():
                try:
                    q.get_nowait()  # drop oldest for slow consumers
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(msg)


def emit(db: Session, msg_type: str, data: Any) -> None:
    """Queue a bus message that is published only if the transaction commits."""
    db.info.setdefault("outbox", []).append({"type": msg_type, "data": data})


@dataclass
class AppContext:
    settings: Settings
    db: Database
    clock: Clock
    anomaly: AnomalyService = field(default_factory=AnomalyService)
    bus: EventBus = field(default_factory=EventBus)
    decisions: dict[int, dict] = field(default_factory=dict)
    simulator: Simulator | None = None
    started_at: Any = None

    def __post_init__(self):
        bus = self.bus

        @event.listens_for(self.db.SessionLocal, "after_commit")
        def _flush_outbox(session):  # pragma: no cover - exercised indirectly
            for msg in session.info.pop("outbox", []):
                bus.publish(msg)

        @event.listens_for(self.db.SessionLocal, "after_rollback")
        def _drop_outbox(session):  # pragma: no cover
            session.info.pop("outbox", None)
