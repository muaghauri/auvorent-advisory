from __future__ import annotations
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

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
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    mail_from: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(ROOT / ".env")
        env = os.getenv("CMS_ENV", "development").lower()
        key = os.getenv("CMS_SECRET_KEY", "")
        if env == "production" and len(key) < 32:
            raise RuntimeError("Production requires CMS_SECRET_KEY of at least 32 characters")
        if not key:
            key = secrets.token_urlsafe(48)  # development only, changes on restart
        secure = os.getenv("CMS_SESSION_SECURE", "true" if env == "production" else "false").lower() == "true"
        if env == "production" and not secure:
            raise RuntimeError("Production requires CMS_SESSION_SECURE=true")
        return cls(
            environment=env,
            database_url=os.getenv("CMS_DATABASE_URL", "sqlite:///./instance/auvorent-cms.sqlite"),
            secret_key=key,
            session_secure=secure,
            session_hours=int(os.getenv("CMS_SESSION_HOURS", "12")),
            login_rate_limit=int(os.getenv("CMS_LOGIN_RATE_LIMIT", "10")),
            public_origin=os.getenv("CMS_PUBLIC_ADMIN_ORIGIN", "").rstrip("/"),
            media_root=os.getenv("CMS_MEDIA_ROOT", ""),
            publish_root=os.getenv("CMS_PUBLISH_ROOT", ""),
            public_site_origin=os.getenv("CMS_PUBLIC_SITE_ORIGIN", "").rstrip("/"),
            public_form_rate_limit=max(1,int(os.getenv("CMS_PUBLIC_FORM_RATE_LIMIT", "8"))),
            smtp_host=os.getenv("CMS_SMTP_HOST", ""),
            smtp_port=int(os.getenv("CMS_SMTP_PORT", "587")),
            smtp_username=os.getenv("CMS_SMTP_USERNAME", ""),
            smtp_password=os.getenv("CMS_SMTP_PASSWORD", ""),
            mail_from=os.getenv("CMS_MAIL_FROM", ""),
        )
