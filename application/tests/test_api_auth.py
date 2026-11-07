"""API authentication (APP_API_TOKEN) tests — no external service required."""

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from src.routers import dependencies as api_deps

APP_API_PATH = Path(__file__).resolve().parent.parent / "app-api.py"
TOKEN = "test-token-123"


@pytest.fixture(scope="module")
def client():
    spec = importlib.util.spec_from_file_location("app_api_auth", APP_API_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # No context manager: the lifespan (queue workers, Mongo recovery) is not started.
    return TestClient(module.app)


@pytest.fixture
def with_token(monkeypatch):
    conf = api_deps.get_base_config().model_copy()
    conf.api_token = SecretStr(TOKEN)
    monkeypatch.setattr(api_deps, "get_base_config", lambda: conf)
    yield


def test_missing_token_is_rejected(client, with_token):
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


def test_wrong_token_is_rejected(client, with_token):
    resp = client.get(
        "/api/v1/agents", headers={"Authorization": "Bearer not-the-token"}
    )
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "headers",
    [{"Authorization": f"Bearer {TOKEN}"}, {"X-API-Key": TOKEN}],
)
def test_valid_token_is_accepted(client, with_token, headers):
    resp = client.get("/api/v1/agents", headers=headers)
    assert resp.status_code != 401


def test_public_endpoints_stay_open(client, with_token):
    assert client.get("/api/v1/openapi.json").status_code == 200


def test_openapi_declares_security_schemes(client):
    spec = client.get("/api/v1/openapi.json").json()
    schemes = spec["components"]["securitySchemes"]
    assert {"HTTPBearer", "APIKeyHeader"} <= set(schemes)


def test_security_headers_and_request_id_are_injected(client):
    resp = client.get("/health", headers={"X-Request-ID": "req-hospital-001"})
    assert resp.status_code == 200
    assert resp.headers["x-request-id"] == "req-hospital-001"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert "camera=()" in resp.headers["permissions-policy"]
    assert resp.headers["cross-origin-opener-policy"] == "same-origin"
    assert resp.headers["cross-origin-resource-policy"] == "same-origin"
    assert "default-src 'none'" in resp.headers["content-security-policy"]
    assert "no-store" in resp.headers["cache-control"]


def test_invalid_request_id_is_replaced_with_safe_uuid(client):
    resp = client.get("/health", headers={"X-Request-ID": "bad id with spaces\r\n"})
    assert resp.status_code == 200
    assert resp.headers["x-request-id"] != "bad id with spaces\r\n"
    assert len(resp.headers["x-request-id"]) == 36


def test_cors_preflight_and_allowed_origin(client):
    preflight = client.options(
        "/api/v1/agents",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,X-Oncoflow-Domain",
        },
    )
    assert preflight.status_code == 200
    assert (
        preflight.headers.get("access-control-allow-origin") == "http://localhost:3000"
    )
    assert preflight.headers.get("access-control-allow-credentials") == "true"

    disallowed = client.get(
        "/health",
        headers={"Origin": "https://evil.example.com"},
    )
    assert "access-control-allow-origin" not in disallowed.headers


def test_payload_exceeding_max_body_bytes_returns_413(client, monkeypatch):
    conf = api_deps.get_base_config().model_copy(deep=True)
    conf.api.max_body_bytes = 2048
    monkeypatch.setattr(api_deps, "get_base_config", lambda: conf)

    resp = client.post(
        "/api/v1/bug-reports",
        content=b"x" * 4096,
        headers={"Content-Type": "application/json", "Content-Length": "4096"},
    )
    assert resp.status_code == 413
    assert "4096" in resp.json()["detail"]


def test_rate_limiting_returns_429_and_exempts_health(client, monkeypatch):
    api_deps.reset_rate_limit_buckets()
    conf = api_deps.get_base_config().model_copy(deep=True)
    conf.api.rate_limit_enabled = True
    conf.api.rate_limit_requests = 2
    conf.api.rate_limit_window_seconds = 60
    monkeypatch.setattr(api_deps, "get_base_config", lambda: conf)

    try:
        assert client.get("/api/v1/openapi.json").status_code == 200
        assert client.get("/api/v1/openapi.json").status_code == 200
        limited = client.get("/api/v1/openapi.json")
        assert limited.status_code == 429
        assert "retry-after" in limited.headers
        # Different user or forwarded client IP gets its own rate-limit bucket
        other_user = client.get(
            "/api/v1/openapi.json",
            headers={
                "X-Forwarded-For": "10.0.0.15",
                "X-Oncoflow-User": "dr.autre",
            },
        )
        assert other_user.status_code == 200
        # /health must remain exempt even when rate limit is reached
        assert client.get("/health").status_code == 200
    finally:
        api_deps.reset_rate_limit_buckets()


def test_docs_require_auth_when_configured(client, monkeypatch):
    conf = api_deps.get_base_config().model_copy(deep=True)
    conf.api_token = SecretStr(TOKEN)
    conf.api.docs_require_auth = True
    monkeypatch.setattr(api_deps, "get_base_config", lambda: conf)

    assert client.get("/api/v1/openapi.json").status_code == 401
    assert (
        client.get(
            "/api/v1/openapi.json",
            headers={"Authorization": f"Bearer {TOKEN}"},
        ).status_code
        == 200
    )
