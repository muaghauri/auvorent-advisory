from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import timedelta
from typing import Callable
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .models import AuditLog, CMSession, User, utcnow

_hasher = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)
_dummy_hash = _hasher.hash(secrets.token_urlsafe(24))
_MAX_BROWSER_TOKEN = 256
_BROWSER_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,256}$")

ROLES = ("super_admin", "admin", "editor", "reviewer", "viewer")
PERMISSIONS: dict[str, set[str]] = {
    "super_admin": {"dashboard:read", "users:manage", "audit:read", "content:edit", "content:read", "media:read", "content:approve", "content:publish", "settings:manage", "inquiries:read", "media:manage"},
    "admin": {"dashboard:read", "content:edit", "content:read", "media:read", "content:approve", "content:publish", "settings:manage", "inquiries:read", "media:manage"},
    "editor": {"dashboard:read", "content:edit", "content:read", "media:read", "media:manage"},
    "reviewer": {"dashboard:read", "content:read", "media:read", "content:approve"},
    "viewer": {"dashboard:read", "content:read", "media:read"},
}

_SENSITIVE_AUDIT_KEYS = {
    "password", "current_password", "new_password", "initial_password",
    "secret", "secret_key", "token", "csrf", "csrf_token", "session",
    "session_token", "authorization", "api_key", "apikey", "access_key",
    "private_key", "smtp_password", "database_url", "cookie",
}


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 128:
        raise ValueError("Password must contain between 12 and 128 characters")
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash or _dummy_hash, password)
    except (VerifyMismatchError, VerificationError, ValueError):
        return False


def fingerprint_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User, hours: int) -> str:
    token = secrets.token_urlsafe(48)
    db.add(CMSession(id=str(uuid.uuid4()), user_id=user.id, token_hash=fingerprint_token(token), expires_at=utcnow()+timedelta(hours=hours)))
    db.flush()
    return token


def _sanitize_audit_value(value, *, key: str = ""):
    normalized = key.lower().replace("-", "_")
    if any(marker in normalized for marker in _SENSITIVE_AUDIT_KEYS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k)[:120]: _sanitize_audit_value(v, key=str(k)) for k, v in list(value.items())[:100]}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_audit_value(v) for v in list(value)[:100]]
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:500]


def audit(db: Session, action: str, actor: str | None = None, target_type: str = "system", target_id: str | None = None, **details) -> None:
    # Defense in depth: callers should never pass credentials, but redact likely
    # sensitive values centrally in case a future code path does so accidentally.
    safe_details = {str(k)[:120]: _sanitize_audit_value(v, key=str(k)) for k, v in list(details.items())[:100]}
    db.add(AuditLog(
        actor_user_id=actor,
        action=action[:160],
        target_type=target_type[:80],
        target_id=str(target_id)[:160] if target_id is not None else None,
        detail=json.dumps(safe_details, separators=(",", ":"), sort_keys=True),
    ))


def get_db(request: Request):
    with request.app.state.db_factory() as db:
        yield db


def _valid_browser_token(value: str | None) -> bool:
    return bool(value and len(value) <= _MAX_BROWSER_TOKEN and _BROWSER_TOKEN_RE.fullmatch(value))


def require_csrf(request: Request):
    cookie = request.cookies.get("auv_csrf")
    header = request.headers.get("X-CSRF-Token")
    if not _valid_browser_token(cookie) or not _valid_browser_token(header) or not hmac.compare_digest(cookie, header):
        raise HTTPException(403, "Invalid CSRF token")

    # Modern browsers tell us whether a request originated cross-site. Treat an
    # explicit cross-site signal as hostile even if another header is missing.
    fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
    if fetch_site and fetch_site not in {"same-origin", "same-site", "none"}:
        raise HTTPException(403, "Cross-origin request rejected")

    origin = request.headers.get("origin")
    if origin:
        if len(origin) > 512:
            raise HTTPException(403, "Cross-origin request rejected")
        expected = request.app.state.settings.public_origin or str(request.base_url).rstrip("/")
        actual_parsed = urlparse(origin)
        expected_parsed = urlparse(expected)
        if (
            actual_parsed.username
            or actual_parsed.password
            or actual_parsed.path not in ("", "/")
            or actual_parsed.params
            or actual_parsed.query
            or actual_parsed.fragment
            or actual_parsed.scheme != expected_parsed.scheme
            or actual_parsed.hostname != expected_parsed.hostname
            or (actual_parsed.port or (443 if actual_parsed.scheme == "https" else 80))
               != (expected_parsed.port or (443 if expected_parsed.scheme == "https" else 80))
        ):
            raise HTTPException(403, "Cross-origin request rejected")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("auv_admin_session")
    if not _valid_browser_token(token):
        raise HTTPException(401, "Authentication required")
    sess = db.query(CMSession).filter(CMSession.token_hash == fingerprint_token(token), CMSession.revoked_at.is_(None), CMSession.expires_at > utcnow()).first()
    if not sess:
        raise HTTPException(401, "Session expired or revoked")
    user = db.get(User, sess.user_id)
    if not user or not user.is_active or user.role not in ROLES:
        raise HTTPException(401, "Account unavailable")
    return user


def require_permission(permission: str) -> Callable:
    if not permission or not any(permission in allowed for allowed in PERMISSIONS.values()):
        raise ValueError(f"Unknown CMS permission: {permission}")

    def check(user: User = Depends(current_user)) -> User:
        if user.must_change_password:
            raise HTTPException(403, "Change your password before continuing")
        if permission not in PERMISSIONS.get(user.role, set()):
            raise HTTPException(403, "Insufficient permissions")
        return user

    # Security regression tests can inspect the exact server-side permission
    # attached to a route without changing FastAPI's dependency behavior.
    check.required_permission = permission
    return check


def user_out(user: User) -> dict:
    return {"id":user.id,"email":user.email,"full_name":user.full_name,"role":user.role,
            "is_active":user.is_active,"must_change_password":user.must_change_password,
            "created_at":user.created_at.isoformat()+"Z", "last_login_at":user.last_login_at.isoformat()+"Z" if user.last_login_at else None}
