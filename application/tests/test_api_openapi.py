"""Smoke tests of the FastAPI OpenAPI contract (no external service required)."""

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

APP_API_PATH = Path(__file__).resolve().parent.parent / "app-api.py"


@pytest.fixture(scope="module")
def api_app():
    spec = importlib.util.spec_from_file_location("app_api", APP_API_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


@pytest.fixture(scope="module")
def client(api_app):
    # No context manager: the lifespan (queue workers, Mongo recovery) is not started.
    return TestClient(api_app)


def test_openapi_endpoint_is_versioned(client):
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "Oncoflow Cross-Domain API"


def test_every_json_endpoint_declares_a_response_schema(client):
    spec = client.get("/api/v1/openapi.json").json()
    missing = []
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            content = operation["responses"].get("200", {}).get("content", {})
            if "application/pdf" in content:
                continue
            schema = content.get("application/json", {}).get("schema", {})
            if not schema:
                missing.append(f"{method.upper()} {path}")
    assert not missing, f"Endpoints without response_model: {missing}"
