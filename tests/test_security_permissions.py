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


def _endpoint_map(app):
    """Map endpoint function names to routes.

    FastAPI may clone APIRouter routes during include_router(), so function-name
    binding is a more stable regression target than internal route-object
    identity. Paths/methods remain exercised by the existing endpoint tests.
    """
    mapping = {}
    for route in app.routes:
        if isinstance(route, APIRoute):
            mapping.setdefault(getattr(route.endpoint, "__name__", ""), []).append(route)
    return mapping


def test_high_risk_endpoints_keep_exact_server_side_permissions(app):
    routes = _endpoint_map(app)
    expected = {
        "create_user": "users:manage",
        "update_user": "users:manage",
        "admin_reset_password": "users:manage",
        "audit_events": "audit:read",
        "update_settings": "settings:manage",
        "update_lead_settings": "settings:manage",
        "resend_notification": "settings:manage",
        "delete_inquiry": "settings:manage",
        "upload_media": "media:manage",
        "build": "content:publish",
        "run_due": "content:publish",
        "rollback": "content:publish",
        "review_decision": "content:approve",
        "export_release": "content:publish",
    }
    missing = sorted(name for name in expected if name not in routes)
    assert missing == [], f"Expected security-sensitive endpoints missing: {missing}"

    mismatches = []
    for name, permission in expected.items():
        actual = set().union(*(_permissions(route) for route in routes[name]))
        if permission not in actual:
            mismatches.append((name, permission, sorted(actual)))
    assert mismatches == [], f"High-risk endpoints lost required permission bindings: {mismatches}"


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
