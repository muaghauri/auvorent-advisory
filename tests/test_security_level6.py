import json

import pytest

from backend.app import cloudflare_pages, config, storage
from backend.app.security import _sanitize_audit_value


def test_weak_secret_rejects_predictable_values():
    assert config._weak_secret("a" * 48) is True
    assert config._weak_secret("change-me-please-change-me-please-change-me") is True
    assert config._weak_secret("A8v!m2Q#z7Lp9R$x4Tk6W@c1Ny5Hj3Fs0") is False


def test_production_origin_requires_clean_https():
    assert config._validated_origin("TEST", "https://admin.example.com/", production=True) == "https://admin.example.com"
    for bad in (
        "http://admin.example.com",
        "https://user:pass@admin.example.com",
        "https://admin.example.com/path",
        "https://admin.example.com/?debug=1",
    ):
        with pytest.raises(RuntimeError):
            config._validated_origin("TEST", bad, production=True)


def test_audit_redaction_is_recursive_and_bounded():
    value = {
        "api_key": "should-never-appear",
        "nested": {"authorization": "Bearer abc", "ok": "visible"},
        "long": "x" * 5000,
    }
    clean = _sanitize_audit_value(value)
    dumped = json.dumps(clean)
    assert "should-never-appear" not in dumped
    assert "Bearer abc" not in dumped
    assert clean["nested"]["ok"] == "visible"
    assert len(clean["long"]) == 2000


def test_r2_keys_are_restricted():
    assert storage._safe_key("123e4567-e89b-12d3-a456-426614174000.webp")
    assert storage._safe_key("123e4567-e89b-12d3-a456-426614174000.webp.thumb.webp")
    for bad in ("../secret", "/absolute", "a//b", "a/../b", " bad", "x\x00y"):
        with pytest.raises(ValueError):
            storage._safe_key(bad)


def test_r2_endpoint_must_be_clean_https_origin():
    assert storage._safe_endpoint("https://example.r2.cloudflarestorage.com/") == "https://example.r2.cloudflarestorage.com"
    for bad in (
        "http://example.r2.cloudflarestorage.com",
        "https://user:pass@example.r2.cloudflarestorage.com",
        "https://example.r2.cloudflarestorage.com/path",
        "https://example.r2.cloudflarestorage.com?debug=1",
        "javascript:alert(1)",
    ):
        with pytest.raises(RuntimeError):
            storage._safe_endpoint(bad)


def test_r2_bucket_name_is_restricted(monkeypatch):
    monkeypatch.setenv("R2_BUCKET", "auvorent-media")
    assert storage.bucket_name() == "auvorent-media"
    for bad in ("", "/bad", "bad bucket", "x" * 64):
        monkeypatch.setenv("R2_BUCKET", bad)
        with pytest.raises(RuntimeError):
            storage.bucket_name()


def test_r2_put_rejects_oversized_objects_before_network(monkeypatch):
    monkeypatch.setenv("R2_BUCKET", "auvorent-media")
    oversized = b"x" * (storage.MAX_OBJECT_BYTES + 1)
    with pytest.raises(ValueError):
        storage.put_bytes("safe-object.webp", oversized, "image/webp")


def test_cloudflare_deploy_inputs_are_bounded():
    cloudflare_pages._validate_deploy_inputs("auvorent-site", "main", "Security release", 300)
    for project in ("", "-bad", "Bad Project", "x" * 70):
        with pytest.raises(cloudflare_pages.CloudflarePagesError):
            cloudflare_pages._validate_deploy_inputs(project, "main", "ok", 300)
    with pytest.raises(cloudflare_pages.CloudflarePagesError):
        cloudflare_pages._validate_deploy_inputs("auvorent-site", "../main", "ok", 300)
    with pytest.raises(cloudflare_pages.CloudflarePagesError):
        cloudflare_pages._validate_deploy_inputs("auvorent-site", "main", "bad\nmessage", 300)


def test_cloudflare_deploy_environment_does_not_inherit_application_secrets(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/tmp/home")
    monkeypatch.setenv("CMS_DATABASE_URL", "postgresql://user:secret@example/db")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "r2-secret")
    monkeypatch.setenv("CMS_SMTP_PASSWORD", "mail-secret")
    monkeypatch.setenv("CMS_SECRET_KEY", "session-secret")

    env = cloudflare_pages._deployment_env("a" * 32, "cloudflare-token-value-12345")

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/tmp/home"
    assert env["CLOUDFLARE_ACCOUNT_ID"] == "a" * 32
    assert env["CLOUDFLARE_API_TOKEN"] == "cloudflare-token-value-12345"
    assert env["CI"] == "true"
    assert "CMS_DATABASE_URL" not in env
    assert "R2_SECRET_ACCESS_KEY" not in env
    assert "CMS_SMTP_PASSWORD" not in env
    assert "CMS_SECRET_KEY" not in env


def test_cloudflare_redaction_hides_token_and_authorization():
    token = "top-secret-token"
    raw = f"authorization: Bearer abc123 api_token={token} {token}"
    clean = cloudflare_pages._redact(raw, token)
    assert token not in clean
    assert "abc123" not in clean
    assert "[REDACTED]" in clean
