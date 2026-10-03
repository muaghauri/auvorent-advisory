import inspect

from fastapi.params import Depends

from backend.app.main import admin_reset_password, audit_events, create_user, update_user
from backend.app.phase2 import update_settings
from backend.app.phase3 import upload_media
from backend.app.phase4 import delete_inquiry, resend_notification, update_lead_settings
from backend.app.phase5 import review_decision
from backend.app.phase6 import export_release


def _required_permissions(endpoint) -> set[str]:
    """Inspect the server-side Depends bindings declared by an endpoint.

    This intentionally validates the source-level security contract rather than
    FastAPI's internal cloned route graph, which changes across framework
    versions. Endpoint reachability is already covered by the phase integration
    tests.
    """
    found = set()
    for parameter in inspect.signature(endpoint).parameters.values():
        default = parameter.default
        if not isinstance(default, Depends):
            continue
        dependency = default.dependency
        permission = getattr(dependency, "required_permission", None)
        if permission:
            found.add(permission)
    return found


def _router_endpoint(router, *, path: str, method: str):
    matches = [
        route.endpoint
        for route in router.routes
        if getattr(route, "path", None) == path and method.upper() in (getattr(route, "methods", None) or set())
    ]
    assert len(matches) == 1, f"Expected exactly one {method} {path} endpoint, got {len(matches)}"
    return matches[0]


def test_high_risk_endpoints_keep_exact_server_side_permissions():
    from backend.app.phase5 import router as phase5_router

    # Phase 5 publishing functions are resolved by path because their internal
    # function names are intentionally free to evolve while the API contract is
    # stable.
    build = _router_endpoint(phase5_router, path="/api/v1/publishing/build", method="POST")
    run_due = _router_endpoint(phase5_router, path="/api/v1/publishing/run-due", method="POST")
    rollback = _router_endpoint(phase5_router, path="/api/v1/publishing/rollback/{release_id}", method="POST")

    expected = {
        create_user: "users:manage",
        update_user: "users:manage",
        admin_reset_password: "users:manage",
        audit_events: "audit:read",
        update_settings: "settings:manage",
        update_lead_settings: "settings:manage",
        resend_notification: "settings:manage",
        delete_inquiry: "settings:manage",
        upload_media: "media:manage",
        build: "content:publish",
        run_due: "content:publish",
        rollback: "content:publish",
        review_decision: "content:approve",
        export_release: "content:publish",
    }

    mismatches = []
    for endpoint, permission in expected.items():
        actual = _required_permissions(endpoint)
        if permission not in actual:
            mismatches.append((endpoint.__name__, permission, sorted(actual)))
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
