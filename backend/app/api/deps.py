"""FastAPI dependencies: context, DB session, user and device authentication."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..context import AppContext
from ..models import Device, User
from ..security import decode_access_token, role_at_least, verify_device_key

bearer = HTTPBearer(auto_error=False)


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def get_db(ctx: AppContext = Depends(get_ctx)) -> Iterator[Session]:
    with ctx.db.session() as db:
        yield db


@dataclass
class CurrentUser:
    id: int
    username: str
    role: str


def user_from_token(ctx: AppContext, db: Session, token: str) -> CurrentUser:
    try:
        payload = decode_access_token(token, ctx.settings.secret_key)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"}) from exc
    user = db.query(User).filter(User.username == payload["sub"]).one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user inactive or not found")
    return CurrentUser(user.id, user.username, user.role)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                 ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> CurrentUser:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required",
                            headers={"WWW-Authenticate": "Bearer"})
    return user_from_token(ctx, db, creds.credentials)


def require_role(role: str):
    def dep(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if not role_at_least(user.role, role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role '{role}'")
        return user

    return dep


viewer = require_role("viewer")
operator = require_role("operator")
admin = require_role("admin")


def current_device(x_device_id: str = Header(..., alias="X-Device-Id", max_length=64),
                   x_device_key: str = Header(..., alias="X-Device-Key", max_length=128),
                   db: Session = Depends(get_db)) -> Device:
    dev = db.query(Device).filter(Device.uid == x_device_id).one_or_none()
    # Same error for unknown id and wrong key to avoid device enumeration.
    if dev is None or not verify_device_key(x_device_key, dev.api_key_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid device credentials")
    if dev.kind == "simulated":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "simulated devices cannot use the hardware API")
    return dev
