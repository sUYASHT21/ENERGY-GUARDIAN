from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, unquote

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def _encode_password(rest: str) -> str:
    """Percent-encode the password in ``user:password@host...`` so passwords containing ``@``,
    ``:``, ``/``, ``#`` or ``?`` work when pasted verbatim. Already-encoded passwords are kept."""
    at = rest.rfind("@")
    if at < 0:
        return rest
    userinfo, hostpart = rest[:at], rest[at + 1:]
    user, sep, password = userinfo.partition(":")
    if not sep:
        return rest
    return f"{user}:{quote(unquote(password), safe='')}@{hostpart}"


def normalize_url(url: str) -> str:
    """Accept the URI formats hosting providers hand out (e.g. Supabase's ``postgresql://`` or the
    legacy ``postgres://``), select the psycopg 3 driver and encode special password characters."""
    for prefix in ("postgres://", "postgresql://", "postgresql+psycopg://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + _encode_password(url[len(prefix):])
    return url


def is_postgres(url: str) -> bool:
    return normalize_url(url).startswith("postgresql")


def make_engine(url: str) -> Engine:
    url = normalize_url(url)
    connect_args: dict = {}
    engine_kwargs: dict = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 30}
        path = url.replace("sqlite:///", "", 1)
        if path and path != ":memory:" and not path.startswith("file:"):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    elif url.startswith("postgresql"):
        # Supabase's pooler (PgBouncer/Supavisor in transaction mode) does not support prepared
        # statements; disabling them is harmless on a direct/session connection.
        connect_args = {"prepare_threshold": None, "connect_timeout": 10}
        if "supabase" in url and "sslmode=" not in url:
            connect_args["sslmode"] = "require"
        # Small pool: free-tier poolers allow a limited number of clients. pre_ping/recycle
        # transparently replace connections the pooler or network dropped while idle.
        engine_kwargs = {"pool_size": 5, "max_overflow": 5, "pool_pre_ping": True, "pool_recycle": 300}
    engine = create_engine(url, connect_args=connect_args, future=True, **engine_kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            if ":memory:" not in url:
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return engine


class Database:
    """Holds the engine + session factory. One instance per application."""

    def __init__(self, url: str):
        self.url = normalize_url(url)
        self.engine = make_engine(url)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def create_all(self) -> None:
        from . import models  # noqa: F401  (register models)

        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        from . import models  # noqa: F401

        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self.SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
