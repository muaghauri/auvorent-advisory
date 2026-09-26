from __future__ import annotations
import uuid
import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import User
from backend.app.security import hash_password

ADMIN_PASSWORD = "S3cure-Initial-Password!"

@pytest.fixture
def app(tmp_path):
    settings=Settings(environment="testing", database_url="sqlite:///"+str(tmp_path / "cms.sqlite"),
                      secret_key="test-only-secret-string-not-for-production-0000",session_secure=False,
                      session_hours=12,login_rate_limit=10)
    instance=create_app(settings,create_schema=True)
    with instance.state.db_factory() as db:
        user=User(id=str(uuid.uuid4()),email="owner@example.com",full_name="Founding Administrator",
                  role="super_admin",password_hash=hash_password(ADMIN_PASSWORD),is_active=True,
                  must_change_password=False)
        db.add(user)
        db.commit()
    yield instance
    instance.state.engine.dispose()

@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client

@pytest.fixture
def logged_client(client):
    csrf=client.get("/api/v1/auth/csrf").json()["csrf_token"]
    response=client.post("/api/v1/auth/login", json={"email":"owner@example.com","password":ADMIN_PASSWORD},headers={"X-CSRF-Token":csrf})
    assert response.status_code==200,response.text
    client.csrf_token=csrf
    yield client

def create_team_user(client, email, role="editor", password="Created-User-Pass!2026"):
    response=client.post("/api/v1/users",headers={"X-CSRF-Token":client.csrf_token},json={"email":email,"full_name":"New Team Member","role":role,"initial_password":password})
    assert response.status_code==201,response.text
    return response.json()["user"]
