"""Auvorent Advisory CMS — Phases 1–5: secure CMS, content and lead workflows."""
from __future__ import annotations
import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings
from .db import Base, make_engine, make_session_factory
from .models import AuditLog, CMSession, LoginAttempt, User, Page, CollectionEntry, MediaAsset, utcnow
from .schemas import ChangePasswordInput, CreateUserInput, LoginInput, ResetUserPasswordInput, UpdateUserInput
from .phase2 import router as phase2_router
from .phase3 import router as phase3_router
from .phase4 import router as phase4_router
from .phase5 import router as phase5_router
from .phase6 import router as phase6_router
from .security import (
    ROLES, audit, create_session, current_user, fingerprint_token,
    get_db, hash_password, require_csrf, require_permission, user_out, verify_password,
)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
MAX_API_REQUEST_BYTES = 12 * 1024 * 1024
MAX_PUBLIC_JSON_BYTES = 128 * 1024

MODULES = [
    {"id": 1,"name": "Foundation & Security", "status": "implemented", "description": "Login, roles, account administration, audit and dashboard"},
    {"id": 2,"name": "Page Studio & Global Structure", "status": "implemented", "description": "V6 content extraction, pages, sections, navigation and settings"},
    {"id": 3,"name": "Collections, Media & Assets", "status": "implemented", "description": "Services, industries, insights, images and custom icons"},
    {"id": 4,"name": "Leads, Forms & Assessments", "status": "implemented", "description": "Form builder, inquiry inbox, email routing and optimization check"},
    {"id": 5,"name": "SEO, Review & Publishing", "status": "implemented", "description": "SEO validation, two-person approvals, private previews and atomic local-staging releases"},
    {"id": 6,"name": "V6 Integration & Production Readiness", "status": "implemented", "description": "Dynamic content integration, QA, monitoring and deployment"},
]


def create_app(settings: Settings | None = None, *, create_schema: bool | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.environment == "production" and (len(settings.secret_key) < 32 or not settings.session_secure):
        raise RuntimeError("Production requires a strong secret and secure cookies")
    app = FastAPI(
        title="Auvorent Advisory CMS API", version="0.6.0", description="Phases 1–6: integrated V6 CMS, guarded release exports and deployment readiness",
        docs_url=None if settings.environment == "production" else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.environment == "production" else "/api/openapi.json",
    )
    app.state.settings = settings
    engine = make_engine(settings.database_url)
    app.state.engine = engine
    app.state.db_factory = make_session_factory(engine)
    app.include_router(phase2_router)
    app.include_router(phase3_router)
    app.include_router(phase4_router)
    app.include_router(phase5_router)
    app.include_router(phase6_router)
    if settings.public_site_origin:
        app.add_middleware(CORSMiddleware, allow_origins=[settings.public_site_origin],
            allow_credentials=False, allow_methods=["GET","POST"], allow_headers=["Content-Type"],
            max_age=1800)
    if settings.media_root:
        app.state.media_root = Path(settings.media_root).resolve()
    elif settings.database_url.startswith("sqlite:///") and ":memory:" not in settings.database_url:
        app.state.media_root = (Path(settings.database_url.removeprefix("sqlite:/// ".strip())).resolve().parent / "media")
    else:
        app.state.media_root = Path("instance/media").resolve()
    if create_schema is True or (create_schema is None and settings.environment != "production"):
        Base.metadata.create_all(engine)  # development/test convenience. Use Alembic in production.
    if settings.publish_root:
        app.state.publish_root=Path(settings.publish_root).resolve()
    elif settings.database_url.startswith('sqlite:///'):
        app.state.publish_root=Path(settings.database_url[len('sqlite:///'):]).resolve().parent / 'publishing'
    else:
        app.state.publish_root=Path('instance/publishing').resolve()
    app.state.publish_root.mkdir(parents=True,exist_ok=True)
    app.mount("/assets", StaticFiles(directory=Path(__file__).resolve().parents[2] / "seed" / "v6_assets"), name="v6-preview-assets")
    app.mount("/static", StaticFiles(directory=FRONTEND / "assets"), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        # Reject obviously oversized requests before JSON/multipart parsing. Media
        # uploads remain supported up to their existing 10 MB application limit.
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared = int(content_length)
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
            if declared < 0 or declared > MAX_API_REQUEST_BYTES:
                return JSONResponse({"detail": "Request body too large"}, status_code=413)
            if request.url.path.startswith("/api/v1/public/") and declared > MAX_PUBLIC_JSON_BYTES:
                return JSONResponse({"detail": "Public request body too large"}, status_code=413)

        if request.method in {"POST", "PUT", "PATCH"} and request.url.path.startswith("/api/v1/public/"):
            content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                return JSONResponse({"detail": "Public API accepts application/json only"}, status_code=415)

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"
        if request.url.path == "/api/docs":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'none'; "
                "form-action 'self'"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'none'; "
                "form-action 'self'"
            )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.get("/", include_in_schema=False)
    def index():
        response = FileResponse(FRONTEND / "index.html", media_type="text/html")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/health", tags=["System"])
    def health(db: Session = Depends(get_db)):
        try:
            db.query(User).limit(1).all()
        except Exception:
            raise HTTPException(503, "Database unavailable")
        return {"status": "ok", "application": "Auvorent CMS", "phase": 5}

    @app.get("/api/v1/auth/csrf", tags=["Authentication"])
    def get_csrf(request: Request, response: Response):
        csrf_token = request.cookies.get("auv_csrf")
        if not csrf_token or len(csrf_token) < 32:
            csrf_token = secrets.token_urlsafe(36)
        response.set_cookie("auv_csrf", csrf_token, max_age=settings.session_hours * 3600,
                            secure=settings.session_secure, httponly=False, samesite="strict", path="/")
        return {"csrf_token": csrf_token}

    @app.post("/api/v1/auth/login", dependencies=[Depends(require_csrf)], tags=["Authentication"])
    def login(payload: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
        email = str(payload.email).strip().lower()
        ip = request.client.host if request.client else "unknown"
        ip_hash = hashlib.sha256((settings.secret_key + ip).encode()).hexdigest()
        cutoff = utcnow() - timedelta(minutes=15)
        # Prune old attempts periodically without retaining IP identifiers indefinitely.
        db.query(LoginAttempt).filter(LoginAttempt.created_at < utcnow()-timedelta(days=2)).delete()
        recent = db.query(LoginAttempt).filter(LoginAttempt.ip_hash == ip_hash, LoginAttempt.created_at >= cutoff,
                                                LoginAttempt.succeeded.is_(False)).count()
        if recent >= settings.login_rate_limit:
            audit(db, "auth.rate_limited", target_type="security", reason="ip_login_limit")
            db.commit()
            raise HTTPException(429, "Too many login attempts. Try again later")
        user = db.query(User).filter(User.email == email).first()
        valid = verify_password(user.password_hash if user else None, payload.password)
        permitted = bool(user and user.is_active and valid and not (user.locked_until and user.locked_until > utcnow()))
        db.add(LoginAttempt(email=email, ip_hash=ip_hash, succeeded=permitted))
        if not permitted:
            if user and user.is_active:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= 5:
                    user.locked_until = utcnow() + timedelta(minutes=15)
                    user.failed_login_attempts = 0
            audit(db, "auth.login_failed", target_type="security", reason="invalid_credentials_or_locked")
            db.commit()
            raise HTTPException(401, "Invalid credentials or account temporarily unavailable")
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = utcnow()
        token = create_session(db, user, settings.session_hours)
        audit(db, "auth.login", actor=user.id, target_type="user", target_id=user.id)
        db.commit()
        response.set_cookie("auv_admin_session", token, max_age=settings.session_hours * 3600,
                            secure=settings.session_secure, httponly=True, samesite="strict", path="/")
        return {"user":user_out(user)}

    @app.get("/api/v1/auth/me", tags=["Authentication"])
    def me(user: User = Depends(current_user)):
        return {"user": user_out(user)}

    @app.post("/api/v1/auth/logout", dependencies=[Depends(require_csrf)], tags=["Authentication"])
    def logout(request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
        token = request.cookies.get("auv_admin_session")
        db.query(CMSession).filter(CMSession.token_hash == fingerprint_token(token)).update({"revoked_at": utcnow()})
        audit(db, "auth.logout", actor=user.id, target_type="user", target_id=user.id)
        db.commit()
        response.delete_cookie("auv_admin_session", path="/", samesite="strict", secure=settings.session_secure)
        return {"status":"logged_out"}

    @app.post("/api/v1/auth/change-password", dependencies=[Depends(require_csrf)], tags=["Authentication"])
    def change_password(payload: ChangePasswordInput, request: Request, response: Response,
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
        if not verify_password(user.password_hash, payload.current_password):
            raise HTTPException(400, "Current password is incorrect")
        if payload.current_password == payload.new_password:
            raise HTTPException(400, "New password must differ from current password")
        user.password_hash = hash_password(payload.new_password)
        user.must_change_password = False
        token = request.cookies.get("auv_admin_session")
        db.query(CMSession).filter(CMSession.user_id == user.id, CMSession.token_hash != fingerprint_token(token),
                                    CMSession.revoked_at.is_(None)).update({"revoked_at": utcnow()})
        audit(db, "user.password_changed", actor=user.id, target_type="user", target_id=user.id)
        db.commit()
        return {"user":user_out(user),"other_sessions_revoked":True}

    @app.get("/api/v1/dashboard", tags=["Dashboard"])
    def dashboard(user: User = Depends(require_permission("dashboard:read")), db: Session = Depends(get_db)):
        return {"user": user_out(user),
                "metrics": {"total_users":db.query(func.count(User.id)).scalar(),
                            "active_users":db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar(),
                            "active_sessions":db.query(func.count(CMSession.id)).filter(CMSession.revoked_at.is_(None), CMSession.expires_at > utcnow()).scalar(),
                            "audit_events":db.query(func.count(AuditLog.id)).scalar(),
                            "collection_records":db.query(func.count(CollectionEntry.id)).scalar(),
                            "media_assets":db.query(func.count(MediaAsset.id)).scalar()},
                "v6_website": {"documented_content_routes":17,"cms_page_records":db.query(func.count(Page.id)).scalar(),"integration_status":"cms_v6_staging_integrated"},
                "modules": MODULES}

    @app.get("/api/v1/users", tags=["Users"])
    def users(search: str = Query("", max_length=120), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
              actor: User = Depends(require_permission("users:manage")), db: Session = Depends(get_db)):
        q = db.query(User)
        if search:
            q = q.filter(User.email.ilike(f"%{search}%") | User.full_name.ilike(f"%{search}%"))
        return {"items":[user_out(u) for u in q.order_by(User.created_at.desc()).offset(offset).limit(limit).all()],
                "total":q.count(),"limit":limit,"offset":offset}

    @app.post("/api/v1/users", status_code=201, dependencies=[Depends(require_csrf)], tags=["Users"])
    def create_user(payload: CreateUserInput, actor: User = Depends(require_permission("users:manage")), db: Session = Depends(get_db)):
        normalized_email = str(payload.email).strip().lower()
        if db.query(User).filter(User.email == normalized_email).first():
            raise HTTPException(409, "An account with this email already exists")
        user = User(id=str(uuid.uuid4()), email=normalized_email, full_name=payload.full_name.strip(),
                    password_hash=hash_password(payload.initial_password), role=payload.role, is_active=True,
                    must_change_password=True)
        db.add(user)
        audit(db, "user.created", actor=actor.id, target_type="user", target_id=user.id, role=payload.role)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "An account with this email already exists")
        return {"user":user_out(user)}

    @app.patch("/api/v1/users/{user_id}", dependencies=[Depends(require_csrf)], tags=["Users"])
    def update_user(user_id: str, payload: UpdateUserInput,
                    actor: User = Depends(require_permission("users:manage")), db: Session = Depends(get_db)):
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404, "User not found")
        changes = payload.model_dump(exclude_unset=True)
        if target.id == actor.id and (("role" in changes and changes["role"] != actor.role) or changes.get("is_active") is False):
            raise HTTPException(400, "You cannot demote or disable your own account")
        if target.role == "super_admin" and (changes.get("role") not in (None, "super_admin") or changes.get("is_active") is False):
            others = db.query(User).filter(User.role == "super_admin", User.is_active.is_(True), User.id != target.id).count()
            if others == 0:
                raise HTTPException(400, "Cannot remove the last active Super Admin")
        for field, value in changes.items():
            if value is not None:
                setattr(target, field, value.strip() if field == "full_name" else value)
        if changes.get("is_active") is False or (changes.get("role") is not None):
            db.query(CMSession).filter(CMSession.user_id == target.id, CMSession.revoked_at.is_(None)).update({"revoked_at":utcnow()})
        audit(db,"user.updated",actor=actor.id,target_type="user",target_id=target.id,fields=list(changes.keys()))
        db.commit()
        return {"user":user_out(target)}

    @app.post("/api/v1/users/{user_id}/reset-password", dependencies=[Depends(require_csrf)], tags=["Users"])
    def admin_reset_password(user_id: str, payload: ResetUserPasswordInput,
                             actor: User = Depends(require_permission("users:manage")), db: Session = Depends(get_db)):
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404,"User not found")
        if target.id == actor.id:
            raise HTTPException(400,"Use change-password for your own account")
        target.password_hash = hash_password(payload.new_password)
        target.must_change_password = True
        db.query(CMSession).filter(CMSession.user_id == target.id, CMSession.revoked_at.is_(None)).update({"revoked_at":utcnow()})
        audit(db,"user.password_reset_by_admin",actor=actor.id,target_type="user",target_id=target.id)
        db.commit()
        return {"status":"reset","must_change_password":True}

    @app.get("/api/v1/audit", tags=["Security"])
    def audit_events(limit: int = Query(40, ge=1, le=100), offset: int = Query(0, ge=0),
                     actor: User = Depends(require_permission("audit:read")), db: Session = Depends(get_db)):
        rows = db.query(AuditLog).order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
        return {"items":[{"id":row.id,"action":row.action,"actor_user_id":row.actor_user_id,
                           "target_type":row.target_type,"target_id":row.target_id,
                           "detail":row.detail,"created_at":row.created_at.isoformat()+"Z"} for row in rows],
                "total":db.query(func.count(AuditLog.id)).scalar(),"limit":limit,"offset":offset}

    return app

app = create_app()
