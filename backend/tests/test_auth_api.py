from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def _login_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/admin/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_login_returns_jwt(db_engine):
    client = TestClient(app)
    response = client.post(
        "/api/admin/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_bad_credentials_401(db_engine):
    client = TestClient(app)
    response = client.post(
        "/api/admin/login",
        json={"username": settings.ADMIN_USERNAME, "password": "definitely-wrong"},
    )
    assert response.status_code == 401


def test_admin_route_requires_token(db_engine):
    client = TestClient(app)
    assert client.get("/api/admin/documents").status_code == 401
    assert (
        client.get("/api/admin/documents", headers={"Authorization": "Bearer garbage"}).status_code
        == 401
    )
    assert client.get("/api/admin/documents", headers=_login_headers(client)).status_code == 200


def test_login_rate_limited_429(db_engine):
    from app.core.ratelimit import limiter

    limiter.enabled = True
    client = TestClient(app)

    codes = [
        client.post(
            "/api/admin/login",
            json={"username": settings.ADMIN_USERNAME, "password": "wrong"},
        ).status_code
        for _ in range(11)  # LOGIN_RATE_LIMIT is 10/minute
    ]

    assert codes[0] == 401
    assert 429 in codes
