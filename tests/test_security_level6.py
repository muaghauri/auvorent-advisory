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


def test_cloudflare_deploy_inputs_are_bounded():
    cloudflare_pages._validate_deploy_inputs("auvorent-site", "main", "Security release", 300)
    for project in ("", "-bad", "Bad Project", "x" * 70):
        with pytest.raises(cloudflare_pages.CloudflarePagesError):
            cloudflare_pages._validate_deploy_inputs(project, "main", "ok", 300)
    with pytest.raises(cloudflare_pages.CloudflarePagesError):
        cloudflare_pages._validate_deploy_inputs("auvorent-site", "../main", "ok", 300)
    with pytest.raises(cloudflare_pages.CloudflarePagesError):
        cloudflare_pages._validate_deploy_inputs("auvorent-site", "main", "bad\nmessage", 300)


def test_cloudflare_redaction_hides_token_and_authorization():
    token = "top-secret-token"
    raw = f"authorization: Bearer abc123 api_token={token} {token}"
    clean = cloudflare_pages._redact(raw, token)
    assert token not in clean
    assert "abc123" not in clean
    assert "[REDACTED]" in clean
