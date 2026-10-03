from backend.app.phase2 import router as phase2_router
from backend.app.phase3 import router as phase3_router
from backend.app.phase4 import router as phase4_router
from backend.app.phase5 import router as phase5_router
from backend.app.phase6 import router as phase6_router


def _required_permissions(route) -> set[str]:
    found = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        permission = getattr(dep.call, "required_permission", None)
        if permission:
            found.add(permission)
        stack.extend(dep.dependencies)
    return found


def _route(source, *, path: str, method: str):
    matches = [
        route
        for route in source.routes
        if getattr(route, "path", None) == path and method.upper() in (getattr(route, "methods", None) or set())
    ]
    assert len(matches) == 1, f"Expected exactly one {method} {path} route, got {len(matches)}"
    return matches[0]


def test_high_risk_endpoints_keep_exact_server_side_permissions(app):
    expected = [
        (app, "POST", "/api/v1/users", "users:manage"),
        (app, "PATCH", "/api/v1/users/{user_id}", "users:manage"),
        (app, "POST", "/api/v1/users/{user_id}/reset-password", "users:manage"),
        (app, "GET", "/api/v1/audit", "audit:read"),
        (phase2_router, "PATCH", "/api/v1/settings", "settings:manage"),
        (phase4_router, "PATCH", "/api/v1/forms/settings", "settings:manage"),
        (phase4_router, "POST", "/api/v1/inquiries/{inquiry_id}/resend", "settings:manage"),
        (phase4_router, "DELETE", "/api/v1/inquiries/{inquiry_id}", "settings:manage"),
        (phase3_router, "POST", "/api/v1/media", "media:manage"),
        (phase5_router, "POST", "/api/v1/publishing/build", "content:publish"),
        (phase5_router, "POST", "/api/v1/publishing/run-due", "content:publish"),
        (phase5_router, "POST", "/api/v1/publishing/rollback/{release_id}", "content:publish"),
        (phase5_router, "POST", "/api/v1/reviews/{review_id}/decision", "content:approve"),
        (phase6_router, "POST", "/api/v1/integration/export-production", "content:publish"),
    ]

    mismatches = []
    for source, method, path, permission in expected:
        route = _route(source, path=path, method=method)
        actual = _required_permissions(route)
        if permission not in actual:
            mismatches.append(((method, path), permission, sorted(actual)))
    assert mismatches == [], f"High-risk routes lost required permission bindings: {mismatches}"


def test_read_only_roles_cannot_gain_mutation_permissions_from_matrix():
    from backend.app.security import PERMISSIONS

    assert "content:edit" not in PERMISSIONS["viewer"]
    assert "content:publish" not in PERMISSIONS["viewer"]
    assert "settings:manage" not in PERMISSIONS["viewer"]
    assert "users:manage" not in PERMISSIONS["viewer"]
    assert "media:manage" not in PERMISSIONS["viewer"]

    assert "content:edit" not in PERMISSIONS["reviewer"]
    assert "content:publish" not in PERMISSIONS["reviewer"]
    assert "settings:manage" not in PERMISSIONS["reviewer"]
    assert "users:manage" not in PERMISSIONS["reviewer"]
    assert "content:approve" in PERMISSIONS["reviewer"]


def test_editor_cannot_publish_or_manage_global_security_settings():
    from backend.app.security import PERMISSIONS

    assert "content:edit" in PERMISSIONS["editor"]
    assert "media:manage" in PERMISSIONS["editor"]
    assert "content:publish" not in PERMISSIONS["editor"]
    assert "content:approve" not in PERMISSIONS["editor"]
    assert "settings:manage" not in PERMISSIONS["editor"]
    assert "users:manage" not in PERMISSIONS["editor"]
