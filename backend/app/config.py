from __future__ import annotations
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _weak_secret(key: str) -> bool:
    normalized = key.strip().lower()
    known = {
        "change-me", "changeme", "development", "development-secret",
        "replace-me", "secret", "supersecret",
    }
    return (
        len(key) < 32
        or len(set(key)) < 10
        or normalized in known
        or normalized.startswith(("change-me", "replace-me", "example-secret", "test-secret"))
    )


def _validated_origin(name: str, value: str, *, production: bool) -> str:
    value = (value or "").strip().rstrip("/")
    if not production:
        return value
    if not value:
        raise RuntimeError(f"Production requires {name}")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(f"{name} must be a clean HTTPS origin with no path, credentials, query or fragment")
    return value


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    database_url: str = "sqlite:///./instance/auvorent-cms.sqlite"
    secret_key: str = ""
    session_secure: bool = False
    session_hours: int = 12
    login_rate_limit: int = 10
    public_origin: str = ""
    media_root: str = ""
    publish_root: str = ""
    public_site_origin: str = ""
    public_form_rate_limit: int = 8
    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    mail_from: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(ROOT / ".env")
        env = os.getenv("CMS_ENV", "development").lower().strip()
        production = env == "production"
        key = os.getenv("CMS_SECRET_KEY", "")
        if production and _weak_secret(key):
            raise RuntimeError("Production requires a strong, unique CMS_SECRET_KEY of at least 32 characters")
        if not key:
            key = secrets.token_urlsafe(48)  # development only, changes on restart

        secure = os.getenv("CMS_SESSION_SECURE", "true" if production else "false").lower() == "true"
        if production and not secure:
            raise RuntimeError("Production requires CMS_SESSION_SECURE=true")

        database_url = os.getenv("CMS_DATABASE_URL", "sqlite:///./instance/auvorent-cms.sqlite").strip()
        if production and database_url.lower().startswith("sqlite:"):
            raise RuntimeError("Production requires a managed non-SQLite database")

        public_origin = _validated_origin(
            "CMS_PUBLIC_ADMIN_ORIGIN",
            os.getenv("CMS_PUBLIC_ADMIN_ORIGIN", ""),
            production=production,
        )
        public_site_origin = _validated_origin(
            "CMS_PUBLIC_SITE_ORIGIN",
            os.getenv("CMS_PUBLIC_SITE_ORIGIN", ""),
            production=production,
        )

        return cls(
            environment=env,
            database_url=database_url,
            secret_key=key,
            session_secure=secure,
            session_hours=_bounded_int("CMS_SESSION_HOURS", 12, 1, 24),
            login_rate_limit=_bounded_int("CMS_LOGIN_RATE_LIMIT", 10, 3, 50),
            public_origin=public_origin,
            media_root=os.getenv("CMS_MEDIA_ROOT", ""),
            publish_root=os.getenv("CMS_PUBLISH_ROOT", ""),
            public_site_origin=public_site_origin,
            public_form_rate_limit=_bounded_int("CMS_PUBLIC_FORM_RATE_LIMIT", 8, 1, 100),
            resend_api_key=os.getenv("CMS_RESEND_API_KEY", "").strip(),
            smtp_host=os.getenv("CMS_SMTP_HOST", "").strip(),
            smtp_port=_bounded_int("CMS_SMTP_PORT", 587, 1, 65535),
            smtp_username=os.getenv("CMS_SMTP_USERNAME", ""),
            smtp_password=os.getenv("CMS_SMTP_PASSWORD", ""),
            mail_from=os.getenv("CMS_MAIL_FROM", "").strip(),
        )
