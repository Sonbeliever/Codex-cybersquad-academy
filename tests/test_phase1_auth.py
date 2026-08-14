from __future__ import annotations


def test_registration_login_me_and_logout_flow(client):
    registered = client.post(
        "/api/auth/register",
        json={
            "full_name": "Amina Musa",
            "email": "amina@example.com",
            "password": "securepass123",
        },
    )
    assert registered.status_code == 201
    body = registered.get_json()
    assert body["success"] is True
    assert body["data"]["user"]["role"] == "student"
    assert "password_hash" not in body["data"]["user"]

    login = client.post(
        "/api/auth/login",
        json={"email": "amina@example.com", "password": "securepass123"},
    )
    assert login.status_code == 200
    token = login.get_json()["data"]["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.get_json()["data"]["user"]["email"] == "amina@example.com"

    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200

    revoked = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert revoked.status_code == 401
    assert revoked.get_json()["error"] == "TOKEN_REVOKED"


def test_invalid_login_and_duplicate_email(client):
    client.post(
        "/api/auth/register",
        json={
            "full_name": "Amina Musa",
            "email": "amina@example.com",
            "password": "securepass123",
        },
    )

    duplicate = client.post(
        "/api/auth/register",
        json={
            "full_name": "Amina Musa",
            "email": "amina@example.com",
            "password": "securepass123",
        },
    )
    assert duplicate.status_code == 409

    invalid = client.post(
        "/api/auth/login",
        json={"email": "amina@example.com", "password": "wrong-password"},
    )
    assert invalid.status_code == 401
    assert invalid.get_json()["error"] == "INVALID_CREDENTIALS"
