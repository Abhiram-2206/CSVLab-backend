import pytest
from app.core.security import create_access_token
from datetime import timedelta


def test_register_success(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "newuser@example.com", "password": "SecurePassword123!"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert "id" in data
    assert "password" not in data
    assert "password_hash" not in data


def test_register_duplicate_email(client, user_a_credentials):
    # Register once
    client.post("/api/v1/auth/register", json=user_a_credentials)
    # Register second time
    response = client.post("/api/v1/auth/register", json=user_a_credentials)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_register_short_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "short@example.com", "password": "123"},
    )
    assert response.status_code == 422


def test_login_success(client, user_a_credentials):
    client.post("/api/v1/auth/register", json=user_a_credentials)
    response = client.post("/api/v1/auth/login", json=user_a_credentials)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client, user_a_credentials):
    client.post("/api/v1/auth/register", json=user_a_credentials)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": user_a_credentials["email"], "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_login_nonexistent_user(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Password123!"},
    )
    assert response.status_code == 401


def test_refresh_token_flow(client, user_a_credentials):
    client.post("/api/v1/auth/register", json=user_a_credentials)
    login_resp = client.post("/api/v1/auth/login", json=user_a_credentials)
    refresh_token = login_resp.json()["refresh_token"]

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_refresh_token_invalid(client):
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid.jwt.token"},
    )
    assert response.status_code == 401


def test_missing_auth_header(client):
    response = client.get("/api/v1/datasets/")
    assert response.status_code == 401


def test_expired_or_invalid_token(client):
    response = client.get(
        "/api/v1/datasets/",
        headers={"Authorization": "Bearer invalid_token_value"},
    )
    assert response.status_code == 401
