from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError

from backend.app.phase2 import router as phase2_router
from backend.app.phase3 import router as phase3_router
from backend.app.phase4 import router as phase4_router
from backend.app.phase5 import router as phase5_router
from backend.app.phase6 import VisualEdit, router as phase6_router
from backend.app.phase6_renderer import clean_fragment, safe_local_url
from backend.app.schemas import (
    CreatePageInput,
    CreateSectionInput,
    NavigationItemInput,
    ReorderSectionsInput,
    UpdateSettingsInput,
)
from backend.app.security import PERMISSIONS, current_user, require_csrf


def _dependency_calls(route: APIRoute):
    calls = []
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        calls.append(dep.call)
        stack.extend(dep.dependencies)
    return calls


def _required_permissions(route: APIRoute):
    return {
        permission
        for call in _dependency_calls(route)
        if (permission := getattr(call, "required_permission", None))
    }


def test_navigation_blocks_script_and_protocol_relative_urls():
    for bad in (
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "//evil.example/path",
        "/../../admin",
        "http://example.com",
    ):
        with pytest.raises(ValidationError):
            NavigationItemInput(label="Unsafe", url=bad)

    assert NavigationItemInput(label="Contact", url="/contact/").url == "/contact/"
    assert NavigationItemInput(label="External", url="https://example.com/path").url.startswith("https://")


def test_page_slug_and_template_identifiers_are_bounded():
    with pytest.raises(ValidationError):
        CreatePageInput(title="Bad", route="/bad/", slug="Bad Slug")
    with pytest.raises(ValidationError):
        CreatePageInput(title="Bad", route="/bad/", slug="bad", template="../../template")


def test_section_payload_size_is_bounded():
    CreateSectionInput(section_key="hero", section_type="hero", content={"heading": "Safe"})
    with pytest.raises(ValidationError):
        CreateSectionInput(section_key="hero", section_type="hero", content={"body": "x" * (257 * 1024)})


def test_section_reorder_rejects_duplicate_ids():
    with pytest.raises(ValidationError):
        ReorderSectionsInput(section_ids=["one", "one"])


def test_settings_batch_and_values_are_bounded():
    UpdateSettingsInput(values={"brand.tagline": "Business clarity"})
    with pytest.raises(ValidationError):
        UpdateSettingsInput(values={f"k{i}": "v" for i in range(26)})
    with pytest.raises(ValidationError):
        UpdateSettingsInput(values={"brand.tagline": "x" * (33 * 1024)})


def test_visual_editor_rejects_control_characters_and_invalid_field_keys():
    VisualEdit(text_overrides={"text_0": "Safe editorial copy"}, link_overrides={"link_0": "/contact/"})
    with pytest.raises(ValidationError):
        VisualEdit(text_overrides={"text_0": "hello\x00world"})
    with pytest.raises(ValidationError):
        VisualEdit(alt_overrides={"image_0": "alt\x07text"})
    with pytest.raises(ValidationError):
        VisualEdit(text_overrides={"../../text": "bad"})
    with pytest.raises(ValidationError):
        VisualEdit(link_overrides={"link_0": "javascript:alert(1)"})


def test_visual_editor_payload_is_bounded():
    with pytest.raises(ValidationError):
        VisualEdit(text_overrides={f"text_{i}": "x" * 2000 for i in range(150)})


def test_renderer_removes_executable_html_and_unsafe_urls():
    dirty = """
    <section onclick="alert(1)">
      <script>alert(1)</script>
      <iframe src="https://evil.example"></iframe>
      <a href="javascript:alert(1)">bad</a>
      <img src="https://evil.example/a.png" onerror="alert(1)">
      <p class="safe-class">Hello</p>
    </section>
    """
    clean = clean_fragment(dirty).lower()
    assert "<script" not in clean
    assert "<iframe" not in clean
    assert "onclick" not in clean
    assert "onerror" not in clean
    assert "javascript:" not in clean
    assert "https://evil.example" not in clean
    assert "hello" in clean


def test_local_url_guard_blocks_traversal_and_external_protocols():
    assert safe_local_url("/contact/?from=assessment") == "/contact/?from=assessment"
    assert safe_local_url("/assets/image.webp") == "/assets/image.webp"
    for bad in ("//evil.example", "../secret", "/a/../secret", "javascript:alert(1)", "https://evil.example"):
        assert safe_local_url(bad) is None


def test_public_site_header_policy_covers_admin_api_and_clickjacking():
    headers = (Path(__file__).resolve().parents[1] / "seed" / "v6_site" / "_headers").read_text(encoding="utf-8")
    lower = headers.lower()
    assert "strict-transport-security" in lower
    assert "x-frame-options: deny" in lower
    assert "frame-ancestors 'none'" in lower
    assert "object-src 'none'" in lower
    assert "https://admin.auvorent.com" in headers


def test_every_private_mutation_is_bound_to_csrf(app):
    mutating = {"POST", "PUT", "PATCH", "DELETE"}
    public_exemptions = {
        "/api/v1/public/forms/{slug}/submit",
        "/api/v1/public/assessments/{slug}/evaluate",
    }
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/v1/"):
            continue
        methods = set(route.methods or ()) & mutating
        if not methods or route.path in public_exemptions:
            continue
        if require_csrf not in _dependency_calls(route):
            missing.append((sorted(methods), route.path))
    assert missing == [], f"Private state-changing routes missing CSRF binding: {missing}"


def test_every_nonpublic_api_route_is_bound_to_authentication(app):
    public_paths = {
        "/api/v1/health",
        "/api/v1/auth/csrf",
        "/api/v1/auth/login",
        "/api/v1/public/forms/{slug}",
        "/api/v1/public/forms/{slug}/submit",
        "/api/v1/public/assessments/{slug}",
        "/api/v1/public/assessments/{slug}/evaluate",
    }
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/v1/") or route.path in public_paths:
            continue
        calls = _dependency_calls(route)
        has_auth = current_user in calls or any(getattr(call, "__name__", "") == "check" for call in calls)
        if not has_auth:
            missing.append(route.path)
    assert missing == [], f"Private API routes missing authentication/permission binding: {missing}"


def test_sensitive_handlers_keep_exact_server_side_permissions(app):
    expected = {
        "users": "users:manage",
        "create_user": "users:manage",
        "update_user": "users:manage",
        "admin_reset_password": "users:manage",
        "audit_events": "audit:read",
        "delete_page": "settings:manage",
        "update_settings": "settings:manage",
        "update_lead_settings": "settings:manage",
        "upload_media": "media:manage",
        "patch_media": "media:manage",
        "replace_media": "media:manage",
        "delete_media": "media:manage",
        "review_decision": "content:approve",
        "build": "content:publish",
        "run_due": "content:publish",
        "rollback": "content:publish",
        "export_release": "content:publish",
    }
    source_routes=[]
    for source_router in (phase2_router, phase3_router, phase4_router, phase5_router, phase6_router):
        source_routes.extend(route for route in source_router.routes if isinstance(route, APIRoute))
    # Main-app handlers are defined directly on the FastAPI instance; phase
    # handlers are checked on their source routers so a framework clone cannot
    # strip the inspectable permission marker used only by this regression test.
    source_routes.extend(route for route in app.routes if isinstance(route, APIRoute))
    routes_by_name={route.name:route for route in source_routes}
    missing=[]
    incorrect=[]
    for name, permission in expected.items():
        route=routes_by_name.get(name)
        if route is None:
            missing.append(name)
            continue
        permissions=_required_permissions(route)
        if permission not in permissions:
            incorrect.append((name, permission, sorted(permissions)))
    assert missing == [], f"Expected sensitive handlers disappeared: {missing}"
    assert incorrect == [], f"Sensitive handlers lost required RBAC bindings: {incorrect}"


def test_privileged_permissions_are_not_inherited_by_lower_roles():
    assert "users:manage" in PERMISSIONS["super_admin"]
    assert "audit:read" in PERMISSIONS["super_admin"]
    for role in ("admin", "editor", "reviewer", "viewer"):
        assert "users:manage" not in PERMISSIONS[role]
        assert "audit:read" not in PERMISSIONS[role]
    for role in ("editor", "reviewer", "viewer"):
        assert "settings:manage" not in PERMISSIONS[role]
        assert "content:publish" not in PERMISSIONS[role]
    assert "media:manage" in PERMISSIONS["editor"]
    for role in ("reviewer", "viewer"):
        assert "media:manage" not in PERMISSIONS[role]
    assert "content:approve" in PERMISSIONS["reviewer"]
    assert "content:edit" not in PERMISSIONS["reviewer"]


def test_public_lead_frontend_does_not_use_raw_html_sinks():
    root = Path(__file__).resolve().parents[1]
    for relative in ("seed/v6_assets/cms-public.js", "frontend/assets/phase4.js", "frontend/assets/phase6.js"):
        source = (root / relative).read_text(encoding="utf-8")
        assert ".innerHTML" not in source
        assert "insertAdjacentHTML" not in source
        assert "document.write" not in source
