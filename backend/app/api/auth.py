from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..context import AppContext
from ..models import User
from ..schemas import LoginRequest, TokenResponse, UserCreate, UserOut, UserUpdate
from ..security import create_access_token, hash_password, verify_password
from ..services.events import log_event
from .deps import CurrentUser, admin, current_user, get_ctx, get_db

router = APIRouter(tags=["auth"])


class LoginRateLimiter:
    """Max ``limit`` failed logins per (ip, username) within ``window`` seconds."""

    def __init__(self, limit: int = 8, window: float = 300):
        self.limit, self.window = limit, window
        self._fails: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque:
        q = self._fails[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, time.monotonic())) >= self.limit

    def fail(self, key: str) -> None:
        with self._lock:
            self._prune(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)


limiter = LoginRateLimiter()


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    key = f"{request.client.host if request.client else '?'}:{body.username.lower()}"
    if limiter.blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many failed login attempts; try later")
    user = db.query(User).filter(User.username == body.username).one_or_none()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        limiter.fail(key)
        log_event(db, "auth", f"Failed login for '{body.username[:64]}'", now=ctx.clock.now(), level="warning")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid username or password")
    limiter.reset(key)
    token = create_access_token(user.username, user.role, ctx.settings.secret_key, ctx.settings.access_token_minutes)
    log_event(db, "auth", f"User '{user.username}' logged in", now=ctx.clock.now(), actor=user.username)
    return TokenResponse(access_token=token, expires_in_minutes=ctx.settings.access_token_minutes,
                         user=UserOut.model_validate(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    return db.get(User, user.id)


@router.get("/users", response_model=list[UserOut])
def list_users(_: CurrentUser = Depends(admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, user: CurrentUser = Depends(admin), ctx: AppContext = Depends(get_ctx),
                db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, "username already exists")
    u = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    db.add(u)
    db.flush()
    log_event(db, "auth", f"User '{u.username}' created with role {u.role}", now=ctx.clock.now(), actor=user.username)
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, user: CurrentUser = Depends(admin),
                ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")
    if u.id == user.id and (body.role not in (None, "admin") or body.is_active is False):
        raise HTTPException(400, "you cannot demote or deactivate yourself")
    if body.role is not None:
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.password:
        u.password_hash = hash_password(body.password)
    log_event(db, "auth", f"User '{u.username}' updated", now=ctx.clock.now(), actor=user.username)
    return u
