"""Unit and contract tests for FastAPI DI, typed schemas, and `/api/v1/bug-reports`."""

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.use_cases import PatientRecordService
from src.domain.bug_report import BugCategory, BugSeverity, BugStatus
from src.infrastructure.documents.repositories import (
    InMemoryBugReportRepository,
    InMemoryDocumentCacheRepository,
    InMemoryPatientMDTFormRepository,
    InMemoryPatientRepository,
)
from src.routers import dependencies as api_deps
from src.routers.bug_reports import get_bug_report_repo
from src.routers.patientmdtform import get_record_service

APP_API_PATH = Path(__file__).resolve().parent.parent / "app-api.py"


@pytest.fixture(scope="module")
def api_app():
    spec = importlib.util.spec_from_file_location("app_api_improvements", APP_API_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


@pytest.fixture
def client(api_app):
    api_app.dependency_overrides.clear()
    yield TestClient(api_app)
    api_app.dependency_overrides.clear()


def test_queue_domains_uses_cached_get_base_config(client, monkeypatch):
    conf = api_deps.get_base_config().model_copy(
        update={"domain": "sma", "allowed_domains": "oncology,sma"}
    )
    monkeypatch.setattr("src.routers.queue.get_base_config", lambda: conf)

    resp = client.get("/api/v1/queue/domains")
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_domain"] == "sma"
    assert data["allowed_domains"] == ["oncology", "sma"]


def test_patientmdtform_record_service_dependency_override(api_app, client, tmp_path):
    patient_repo = InMemoryPatientRepository()
    mdt_repo = InMemoryPatientMDTFormRepository()
    cache_repo = InMemoryDocumentCacheRepository()
    conf = api_deps.get_base_config().model_copy()
    conf.rcp.path = str(tmp_path)

    service = PatientRecordService(
        patient_repo=patient_repo,
        mdt_form_repo=mdt_repo,
        cache_repo=cache_repo,
        config=conf,
    )
    service.synchronize_patient_from_admin(
        filename="sample.pdf",
        admin_data={
            "first_name": "Alice",
            "last_name": "Martin",
            "date_birth": "1980-04-12",
            "date_rcp": "2026-03-01",
            "gender": "Female",
        },
    )

    api_app.dependency_overrides[get_record_service] = lambda: service

    resp = client.get("/api/v1/patientmdtform/patients")
    assert resp.status_code == 200
    cards = resp.json()
    assert len(cards) == 1
    assert cards[0]["patient_id"] == "martin_alice_1980_04_12"


def test_bug_reports_crud_lifecycle_with_in_memory_repo(api_app, client):
    repo = InMemoryBugReportRepository()
    api_app.dependency_overrides[get_bug_report_repo] = lambda: repo

    # 1. Create a bug report
    create_resp = client.post(
        "/api/v1/bug-reports",
        json={
            "title": "OCR date parsing issue",
            "description": "Date of birth was misread on page 2",
            "category": BugCategory.import_pdf.value,
            "severity": BugSeverity.high.value,
            "page": "datas",
            "reporter": "dr_dupont",
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    bug_id = created["bug_id"]
    assert bug_id.startswith("bug_")
    assert created["status"] == BugStatus.open.value
    assert created["category"] == "import_pdf"
    assert created["severity"] == "high"

    # 2. List bug reports (with and without status filter)
    list_resp = client.get("/api/v1/bug-reports")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["bug_id"] == bug_id

    filtered_empty = client.get("/api/v1/bug-reports?status=resolved")
    assert filtered_empty.status_code == 200
    assert filtered_empty.json() == []

    # 3. Update status
    patch_resp = client.patch(
        f"/api/v1/bug-reports/{bug_id}/status",
        json={"status": BugStatus.resolved.value},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "resolved"

    filtered_resolved = client.get("/api/v1/bug-reports?status=resolved")
    assert len(filtered_resolved.json()) == 1

    # 4. Update non-existent bug report -> 404
    not_found_patch = client.patch(
        "/api/v1/bug-reports/bug_unknown/status",
        json={"status": "closed"},
    )
    assert not_found_patch.status_code == 404

    # 5. Delete bug report
    del_resp = client.delete(f"/api/v1/bug-reports/{bug_id}")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"bug_id": bug_id, "deleted": True}

    # 6. Delete again -> 404
    del_again = client.delete(f"/api/v1/bug-reports/{bug_id}")
    assert del_again.status_code == 404
