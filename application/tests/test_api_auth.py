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
