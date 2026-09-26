from __future__ import annotations
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import timedelta
from typing import Callable
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .models import CMSession, User, AuditLog, utcnow

_hasher = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)
_dummy_hash = _hasher.hash(secrets.token_urlsafe(24))

ROLES = ("super_admin", "admin", "editor", "reviewer", "viewer")
PERMISSIONS: dict[str, set[str]] = {
    "super_admin": {"dashboard:read", "users:manage", "audit:read", "content:edit", "content:read", "media:read", "content:approve", "content:publish", "settings:manage", "inquiries:read", "media:manage"},
    "admin": {"dashboard:read", "content:edit", "content:read", "media:read", "content:approve", "content:publish", "settings:manage", "inquiries:read", "media:manage"},
    "editor": {"dashboard:read", "content:edit", "content:read", "media:read", "media:manage"},
    "reviewer": {"dashboard:read", "content:read", "media:read", "content:approve"},
    "viewer": {"dashboard:read", "content:read", "media:read"},
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

def audit(db: Session, action: str, actor: str | None = None, target_type: str = "system", target_id: str | None = None, **details) -> None:
    # Never log passwords, session tokens, CSRF tokens, provider keys or secrets.
    db.add(AuditLog(actor_user_id=actor, action=action, target_type=target_type, target_id=target_id, detail=json.dumps(details, separators=(",", ":"), sort_keys=True)))

def get_db(request: Request):
    with request.app.state.db_factory() as db:
        yield db

def require_csrf(request: Request):
    cookie = request.cookies.get("auv_csrf")
    header = request.headers.get("X-CSRF-Token")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(403, "Invalid CSRF token")
    origin = request.headers.get("origin")
    if origin:
        expected = request.app.state.settings.public_origin or str(request.base_url).rstrip("/")
        if urlparse(origin).netloc != urlparse(expected).netloc or urlparse(origin).scheme != urlparse(expected).scheme:
            raise HTTPException(403, "Cross-origin request rejected")

def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("auv_admin_session")
    if not token:
        raise HTTPException(401, "Authentication required")
    sess = db.query(CMSession).filter(CMSession.token_hash == fingerprint_token(token), CMSession.revoked_at.is_(None), CMSession.expires_at > utcnow()).first()
    if not sess:
        raise HTTPException(401, "Session expired or revoked")
    user = db.get(User, sess.user_id)
    if not user or not user.is_active or user.role not in ROLES:
        raise HTTPException(401, "Account unavailable")
    return user

def require_permission(permission: str) -> Callable:
    def check(user: User = Depends(current_user)) -> User:
        if user.must_change_password:
            raise HTTPException(403, "Change your password before continuing")
        if permission not in PERMISSIONS.get(user.role, set()):
            raise HTTPException(403, "Insufficient permissions")
        return user
    return check

def user_out(user: User) -> dict:
    return {"id":user.id,"email":user.email,"full_name":user.full_name,"role":user.role,
            "is_active":user.is_active,"must_change_password":user.must_change_password,
            "created_at":user.created_at.isoformat()+"Z", "last_login_at":user.last_login_at.isoformat()+"Z" if user.last_login_at else None}
