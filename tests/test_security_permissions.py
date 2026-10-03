from fastapi.routing import APIRoute


def _permissions(route: APIRoute) -> set[str]:
    found = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        call = dep.call
        permission = getattr(call, "required_permission", None)
        if permission:
            found.add(permission)
        stack.extend(dep.dependencies)
    return found


def _route_map(app):
    mapping = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or ():
            mapping[(method.upper(), route.path)] = route
    return mapping


def test_high_risk_routes_keep_exact_server_side_permissions(app):
    routes = _route_map(app)
    expected = {
        ("POST", "/api/v1/users"): "users:manage",
        ("PATCH", "/api/v1/users/{user_id}"): "users:manage",
        ("POST", "/api/v1/users/{user_id}/reset-password"): "users:manage",
        ("GET", "/api/v1/audit"): "audit:read",
        ("PATCH", "/api/v1/settings"): "settings:manage",
        ("PATCH", "/api/v1/forms/settings"): "settings:manage",
        ("POST", "/api/v1/inquiries/{inquiry_id}/resend"): "settings:manage",
        ("DELETE", "/api/v1/inquiries/{inquiry_id}"): "settings:manage",
        ("POST", "/api/v1/media"): "media:manage",
        ("POST", "/api/v1/publishing/build"): "content:publish",
        ("POST", "/api/v1/publishing/run-due"): "content:publish",
        ("POST", "/api/v1/publishing/rollback/{release_id}"): "content:publish",
        ("POST", "/api/v1/reviews/{review_id}/decision"): "content:approve",
        ("POST", "/api/v1/integration/export-production"): "content:publish",
    }
    missing_routes = [key for key in expected if key not in routes]
    assert missing_routes == [], f"Expected security-sensitive routes missing: {missing_routes}"

    mismatches = []
    for key, permission in expected.items():
        actual = _permissions(routes[key])
        if permission not in actual:
            mismatches.append((key, permission, sorted(actual)))
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
