from backend.app.models import User, AuditLog
from conftest import ADMIN_PASSWORD, create_team_user


def test_health_and_admin_shell(client):
    response=client.get("/api/v1/health")
    assert response.status_code==200 and response.json()["status"]=="ok"
    assert client.get("/api/v1/auth/me").status_code==401
    html=client.get("/")
    assert html.status_code==200
    assert "Auvorent Advisory" in html.text
    assert "noindex" in html.text
    assert "script-src 'self'" in html.headers["content-security-policy"]


def test_login_requires_csrf_and_rejects_bad_password(client):
    form={"email":"owner@example.com","password":ADMIN_PASSWORD}
    assert client.post("/api/v1/auth/login",json=form).status_code==403
    csrf=client.get("/api/v1/auth/csrf").json()["csrf_token"]
    wrong=client.post("/api/v1/auth/login",json={**form,"password":"incorrect"},headers={"X-CSRF-Token":csrf})
    assert wrong.status_code==401
    assert "Invalid credentials" in wrong.json()["detail"]
    good=client.post("/api/v1/auth/login",json=form,headers={"X-CSRF-Token":csrf})
    assert good.status_code==200
    cookie=good.headers["set-cookie"]
    assert "httponly" in cookie.lower() and "samesite=strict" in cookie.lower()
    assert client.get("/api/v1/auth/me").json()["user"]["role"]=="super_admin"


def test_wrong_origin_blocked_even_with_csrf(client):
    csrf=client.get("/api/v1/auth/csrf").json()["csrf_token"]
    response=client.post("/api/v1/auth/login",json={"email":"owner@example.com","password":ADMIN_PASSWORD},headers={"X-CSRF-Token":csrf,"Origin":"https://malicious.example"})
    assert response.status_code==403
    assert client.get("/api/v1/auth/me").status_code==401


def test_admin_dashboard_reports_real_counts(logged_client):
    data=logged_client.get("/api/v1/dashboard").json()
    assert data["metrics"]["total_users"]==1
    assert data["metrics"]["active_sessions"]==1
    assert data["v6_website"]["documented_content_routes"]==17
    assert data["v6_website"]["integration_status"]=="cms_v6_staging_integrated"
    assert "cms_page_records" in data["v6_website"]
    assert len(data["modules"])==6
    assert [m["status"] for m in data["modules"]]==["implemented"]*6


def test_role_based_access_and_initial_password_change(logged_client, app):
    editor=create_team_user(logged_client,"editor@example.com","editor")
    assert editor["must_change_password"] is True
    from fastapi.testclient import TestClient
    with TestClient(app) as other:
        token=other.get("/api/v1/auth/csrf").json()["csrf_token"]
        good=other.post("/api/v1/auth/login",json={"email":"editor@example.com","password":"Created-User-Pass!2026"},headers={"X-CSRF-Token":token})
        assert good.status_code==200
        assert other.get("/api/v1/dashboard").status_code==403
        change=other.post("/api/v1/auth/change-password",json={"current_password":"Created-User-Pass!2026","new_password":"Another-Strong-Pass!2026"},headers={"X-CSRF-Token":token})
        assert change.status_code==200
        assert other.get("/api/v1/dashboard").status_code==200
        assert other.get("/api/v1/users").status_code==403
        assert other.get("/api/v1/audit").status_code==403


def test_create_search_update_disable_user_and_revoke_sessions(logged_client,app):
    from fastapi.testclient import TestClient
    user=create_team_user(logged_client,"editor@example.com")
    listing=logged_client.get("/api/v1/users?search=editor").json()
    assert listing["total"]==1
    update=logged_client.patch("/api/v1/users/"+user["id"],headers={"X-CSRF-Token":logged_client.csrf_token},json={"role":"reviewer"})
    assert update.status_code==200 and update.json()["user"]["role"]=="reviewer"
    with TestClient(app) as other:
        token=other.get("/api/v1/auth/csrf").json()["csrf_token"]
        other.post("/api/v1/auth/login",json={"email":"editor@example.com","password":"Created-User-Pass!2026"},headers={"X-CSRF-Token":token})
        assert other.get("/api/v1/auth/me").status_code==200
        disabled=logged_client.patch("/api/v1/users/"+user["id"],headers={"X-CSRF-Token":logged_client.csrf_token},json={"is_active":False})
        assert disabled.status_code==200
        assert other.get("/api/v1/auth/me").status_code==401
    bad=logged_client.patch("/api/v1/users/"+logged_client.get("/api/v1/auth/me").json()["user"]["id"],headers={"X-CSRF-Token":logged_client.csrf_token},json={"is_active":False})
    assert bad.status_code==400


def test_reset_password_requires_change_and_invalidates_existing_session(logged_client,app):
    from fastapi.testclient import TestClient
    user=create_team_user(logged_client,"employee@example.com")
    with TestClient(app) as other:
        token=other.get("/api/v1/auth/csrf").json()["csrf_token"]
        other.post("/api/v1/auth/login",json={"email":"employee@example.com","password":"Created-User-Pass!2026"},headers={"X-CSRF-Token":token})
        result=logged_client.post(f"/api/v1/users/{user['id']}/reset-password",json={"new_password":"Replaced-Strong-Pass2026!"},headers={"X-CSRF-Token":logged_client.csrf_token})
        assert result.status_code==200
        assert other.get("/api/v1/auth/me").status_code==401
        assert other.post("/api/v1/auth/login",json={"email":"employee@example.com","password":"Created-User-Pass!2026"},headers={"X-CSRF-Token":token}).status_code==401
        new=other.post("/api/v1/auth/login",json={"email":"employee@example.com","password":"Replaced-Strong-Pass2026!"},headers={"X-CSRF-Token":token})
        assert new.status_code==200
        assert new.json()["user"]["must_change_password"] is True


def test_duplicate_accounts_rejected(logged_client):
    create_team_user(logged_client,"employee@example.com")
    dup=logged_client.post("/api/v1/users",headers={"X-CSRF-Token":logged_client.csrf_token},json={"email":"employee@example.com","full_name":"Duplicate Person","role":"viewer","initial_password":"Test-Initial-Pass2026!"})
    assert dup.status_code==409


def test_audit_never_contains_passwords(logged_client):
    create_team_user(logged_client,"audited@example.com")
    events=logged_client.get("/api/v1/audit").json()["items"]
    assert any(x["action"]=="user.created" for x in events)
    assert "Created-User-Pass!2026" not in str(events)
    assert logged_client.get("/api/v1/audit?limit=200").status_code==422


def test_logout_revokes_cookie_session(logged_client):
    assert logged_client.get("/api/v1/auth/me").status_code==200
    assert logged_client.post("/api/v1/auth/logout",headers={"X-CSRF-Token":logged_client.csrf_token}).status_code==200
    assert logged_client.get("/api/v1/auth/me").status_code==401


def test_login_rate_limited_per_ip(client):
    token=client.get("/api/v1/auth/csrf").json()["csrf_token"]
    for i in range(10):
        response=client.post("/api/v1/auth/login",json={"email":f"unknown{i}@example.com","password":"not-the-password"},headers={"X-CSRF-Token":token})
        assert response.status_code==401
    assert client.post("/api/v1/auth/login",json={"email":"owner@example.com","password":ADMIN_PASSWORD},headers={"X-CSRF-Token":token}).status_code==429


def test_password_change_invalid_current_logged_client(logged_client):
    wrong=logged_client.post("/api/v1/auth/change-password",json={"current_password":"wrong","new_password":"Some-Other-Pass2026!"},headers={"X-CSRF-Token":logged_client.csrf_token})
    assert wrong.status_code==400


def test_production_configuration_guard(app):
    from backend.app.config import Settings
    from backend.app.main import create_app
    import pytest
    with pytest.raises(RuntimeError):
        create_app(Settings(environment="production",secret_key="weak",session_secure=False),create_schema=False)


def test_account_lockout_and_recovery_after_lock_expiry(client, app):
    from backend.app.models import utcnow
    from datetime import timedelta
    token=client.get('/api/v1/auth/csrf').json()['csrf_token']
    for _ in range(5):
        bad=client.post('/api/v1/auth/login',json={'email':'owner@example.com','password':'wrong-pass'},headers={'X-CSRF-Token':token})
        assert bad.status_code==401
    locked=client.post('/api/v1/auth/login',json={'email':'owner@example.com','password':ADMIN_PASSWORD},headers={'X-CSRF-Token':token})
    assert locked.status_code==401
    with app.state.db_factory() as db:
        user=db.query(User).filter_by(email='owner@example.com').first()
        assert user.locked_until is not None
        user.locked_until=utcnow()-timedelta(seconds=1)
        db.commit()
    response=client.post('/api/v1/auth/login',json={'email':'owner@example.com','password':ADMIN_PASSWORD},headers={'X-CSRF-Token':token})
    assert response.status_code==200


def test_whitespace_only_user_name_rejected(logged_client):
    result=logged_client.post('/api/v1/users',headers={'X-CSRF-Token':logged_client.csrf_token},json={'email':'blank@example.com','full_name':'    ','role':'editor','initial_password':'Enough-Length-2026!'})
    assert result.status_code==422


def test_last_super_admin_cannot_demote_self(logged_client):
    user_id=logged_client.get('/api/v1/auth/me').json()['user']['id']
    result=logged_client.patch(f'/api/v1/users/{user_id}',headers={'X-CSRF-Token':logged_client.csrf_token},json={'role':'viewer'})
    assert result.status_code==400
