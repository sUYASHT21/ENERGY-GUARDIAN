"""Authentication primitives: password hashing, JWT access tokens, device API keys."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

import jwt

from .clock import utcnow

PBKDF2_ITERATIONS = 240_000
ROLE_RANK = {"viewer": 0, "operator": 1, "admin": 2}


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, dk_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


def create_access_token(username: str, role: str, secret: str, minutes: int) -> str:
    now = utcnow()
    payload = {"sub": username, "role": role, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, secret: str) -> dict:
    """Raises jwt.PyJWTError on invalid/expired tokens."""
    return jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["sub", "exp"]})


def generate_device_key() -> str:
    return "seg_" + secrets.token_urlsafe(32)


def hash_device_key(key: str) -> str:
    # Device keys are high-entropy random tokens, so a fast hash is appropriate.
    return hashlib.sha256(key.encode()).hexdigest()


def verify_device_key(key: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_device_key(key), stored_hash)


def role_at_least(role: str, required: str) -> bool:
    return ROLE_RANK.get(role, -1) >= ROLE_RANK[required]


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
