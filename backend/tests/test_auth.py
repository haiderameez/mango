from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings
from tests.conftest import auth_headers, register


def test_register_returns_user_without_password_hash(client):
    body = register(client)

    assert body["email"] == "engineer@example.com"
    assert "password_hash" not in body
    assert "password" not in body


def test_register_rejects_duplicate_email(client):
    register(client)

    response = client.post(
        "/auth/register",
        json={"name": "Someone", "email": "engineer@example.com", "password": "hunter2hunter2"},
    )

    assert response.status_code == 409


def test_register_rejects_invalid_email(client):
    response = client.post(
        "/auth/register", json={"name": "A", "email": "not-an-email", "password": "hunter2hunter2"}
    )

    assert response.status_code == 422


def test_login_returns_bearer_token(client):
    register(client)

    response = client.post(
        "/auth/login", json={"email": "engineer@example.com", "password": "hunter2hunter2"}
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_login_rejects_wrong_password(client):
    register(client)

    response = client.post(
        "/auth/login", json={"email": "engineer@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 401


def test_login_rejects_unknown_email(client):
    response = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "hunter2hunter2"}
    )

    assert response.status_code == 401


def test_me_returns_current_user(client, headers):
    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["email"] == "engineer@example.com"


def test_me_requires_a_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_a_garbage_token(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer not.a.token"})

    assert response.status_code == 401


def test_me_rejects_an_expired_token(client):
    register(client)

    expired = jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401


def test_me_rejects_a_token_signed_with_another_key(client):
    register(client)

    forged = jwt.encode({"sub": "1"}, "a-different-secret", algorithm="HS256")

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


def test_me_rejects_a_token_for_a_deleted_user(client):
    token = auth_headers(client)["Authorization"].split()[1]
    missing_user = jwt.encode(
        {"sub": "9999", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {missing_user}"})

    assert response.status_code == 401


def test_password_is_stored_hashed(client, db):
    register(client)

    from app.models.user import User

    user = db.query(User).one()

    assert user.password_hash != "hunter2hunter2"
    assert user.password_hash.startswith("$argon2")


def test_health_needs_no_token(client):
    assert client.get("/health").json() == {"status": "ok"}
