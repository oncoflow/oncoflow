"""Contract and unit tests for Phase 1 Node UI FastAPI endpoints and fixes."""

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from src.application.use_cases import (
    PatientMDTFormExtractionService,
    PatientRecordService,
)
from src.domain.patient_mdt_form import get_domain_mdt_form_cls
from src.domain.worker.queue_job import JobStatus, JobType
from src.infrastructure.documents.repositories import (
    InMemoryDocumentCacheRepository,
    InMemoryPatientMDTFormRepository,
    InMemoryPatientRepository,
)
from src.infrastructure.queue.memory_queue import InMemoryQueueManager, QueueJob
from src.routers import dependencies as api_deps
from src.routers.dependencies import get_domain_config
from src.routers.patientmdtform import (
    get_extraction_service,
    get_mdt_form_repo,
    get_record_service,
)
from src.routers.queue import get_queue_manager

APP_API_PATH = Path(__file__).resolve().parent.parent / "app-api.py"


@pytest.fixture(scope="module")
def api_app():
    """Load the FastAPI app without running lifespan workers."""
    spec = importlib.util.spec_from_file_location("app_api_phase1", APP_API_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


@pytest.fixture
def client(api_app):
    """Return a TestClient with clean dependency overrides per test."""
    api_app.dependency_overrides.clear()
    yield TestClient(api_app)
    api_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. RCPCardResponse & PatientCardResponse extended fields
# ---------------------------------------------------------------------------
def test_rcp_and_patient_card_responses_include_processing_and_care_fields(
    api_app, client, tmp_path
):
    """Verify GET /patientmdtform and GET /patientmdtform/patients return all card fields."""
    patient_repo = InMemoryPatientRepository()
    mdt_repo = InMemoryPatientMDTFormRepository()
    cache_repo = InMemoryDocumentCacheRepository()
    conf = api_deps.get_base_config().model_copy()
    conf.rcp.path = str(tmp_path)

    doc_data: dict[str, Any] = {
        "file": "case1.pdf",
        "link": "/tmp/case1.pdf",
        "processing_status": "RUNNING",
        "processing_step": "WAVE_2_CLINICAL",
        "processing_progress_pct": 65.0,
        "PatientAdministrative": {
            "first_name": "Jean",
            "last_name": "Dupont",
            "date_birth": "1970-05-10",
            "date_rcp": "2026-04-01",
            "gender": "Male",
        },
        "CareOrientationProposal": {
            "care_adaptation_suggested": True,
            "suggested_priority": "Urgent, a treatment is needed quickly",
            "proposed_care_type": "Palliative chemotherapy",
            "clinical_rationale": "Rapid progression",
        },
    }
    mdt_repo.upsert_fields("case1.pdf", doc_data)

    service = PatientRecordService(
        patient_repo=patient_repo,
        mdt_form_repo=mdt_repo,
        cache_repo=cache_repo,
        config=conf,
    )
    service.synchronize_patient_from_admin(
        filename="case1.pdf",
        admin_data=doc_data["PatientAdministrative"],
    )

    api_app.dependency_overrides[get_record_service] = lambda: service

    rcps_resp = client.get("/api/v1/patientmdtform")
    assert rcps_resp.status_code == 200
    rcps = rcps_resp.json()
    assert len(rcps) == 1
    rcp_card = rcps[0]
    assert rcp_card["file"] == "case1.pdf"
    assert rcp_card["link"] == "/tmp/case1.pdf"
    assert rcp_card["processing_status"] == "RUNNING"
    assert rcp_card["processing_step"] == "WAVE_2_CLINICAL"
    assert rcp_card["processing_progress_pct"] == 65.0
    assert rcp_card["care_adaptation_suggested"] is True
    assert rcp_card["proposed_care_type"] == "Palliative chemotherapy"

    patients_resp = client.get("/api/v1/patientmdtform/patients")
    assert patients_resp.status_code == 200
    p_cards = patients_resp.json()
    assert len(p_cards) == 1
    p_card = p_cards[0]
    assert p_card["file"] == "case1.pdf"
    assert p_card["link"] == "/tmp/case1.pdf"
    assert p_card["processing_status"] == "RUNNING"
    assert p_card["processing_step"] == "WAVE_2_CLINICAL"
    assert p_card["processing_progress_pct"] == 65.0
    assert p_card["care_adaptation_suggested"] is True
    assert p_card["proposed_care_type"] == "Palliative chemotherapy"


# ---------------------------------------------------------------------------
# 2. GET /api/v1/patientmdtform/schema (pure domain schema, no UI/design elements)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("domain", ["oncology", "sma"])
def test_get_patientmdtform_schema_returns_pure_domain_sections_and_enums(
    api_app, client, domain, monkeypatch
):
    """Verify GET /api/v1/patientmdtform/schema returns pure domain sections and enums without UI icons/design."""
    base_conf = api_deps.get_base_config().model_copy(
        update={"domain": domain, "allowed_domains": "oncology,sma"}
    )
    monkeypatch.setattr(api_deps, "get_base_config", lambda: base_conf)
    api_deps.get_domain_scoped_config.cache_clear()

    resp = client.get(f"/api/v1/patientmdtform/schema?domain={domain}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == domain
    assert isinstance(body["sections"], list)
    assert len(body["sections"]) > 0

    section_names = [s["name"] for s in body["sections"]]
    form_cls = get_domain_mdt_form_cls(domain)
    for model_cls in form_cls.get_clinical_models():
        assert model_cls.__name__ in section_names

    for sec in body["sections"]:
        assert set(sec.keys()) == {
            "name",
            "description",
            "multi_agent",
            "collaborative",
            "agents",
            "editable",
            "json_schema",
        }
        assert "icon" not in sec
        assert "tab" not in sec
        assert "pole" not in sec
        assert isinstance(sec["json_schema"], dict)

    # Check editable matches domain policy
    care_sec = next(
        s for s in body["sections"] if s["name"] == "CareOrientationProposal"
    )
    assert care_sec["editable"] is False
    mtd_sec = next(s for s in body["sections"] if s["name"] == "MTDCompleted")
    assert mtd_sec["editable"] is True

    # Enums check
    assert "Gender" in body["enums"]
    assert "PatientPriority" in body["enums"]
    assert "WHOPerformanceStatus" in body["enums"]
    assert "PrimaryOrganEnum" in body["enums"]


# ---------------------------------------------------------------------------
# 3. GET /api/v1/resources/{filename}/file
# ---------------------------------------------------------------------------
def test_get_resource_file_serves_pdf_inline_and_validates_path(
    api_app, client, tmp_path
):
    """Verify GET /api/v1/resources/{filename}/file serves PDF inline and rejects traversal."""
    conf = api_deps.get_base_config().model_copy()
    conf.rcp.additional_path = str(tmp_path)
    pdf_file = tmp_path / "TNCD_colon.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 mock resource pdf")

    api_app.dependency_overrides[get_domain_config] = lambda: conf

    resp = client.get("/api/v1/resources/TNCD_colon.pdf/file")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "inline" in resp.headers.get("content-disposition", "")
    assert resp.content == b"%PDF-1.4 mock resource pdf"

    missing_resp = client.get("/api/v1/resources/nonexistent.pdf/file")
    assert missing_resp.status_code == 404

    bad_resp = client.get("/api/v1/resources/..%5Csecret.pdf/file")
    assert bad_resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. GET /api/v1/patientmdtform/{filename}/pdf (?inline=true & ?variant=bbox)
# ---------------------------------------------------------------------------
def test_download_rcp_pdf_inline_and_bbox_variant(api_app, client, tmp_path):
    """Verify GET /patientmdtform/{filename}/pdf supports ?inline=true and ?variant=bbox."""
    conf = api_deps.get_base_config().model_copy()
    conf.rcp.path = str(tmp_path)
    plain_pdf = tmp_path / "doc1.pdf"
    plain_pdf.write_bytes(b"%PDF-1.4 plain content")

    api_app.dependency_overrides[get_domain_config] = lambda: conf

    # Default (attachment)
    resp_default = client.get("/api/v1/patientmdtform/doc1.pdf/pdf")
    assert resp_default.status_code == 200
    assert "attachment" in resp_default.headers.get("content-disposition", "")
    assert resp_default.content == b"%PDF-1.4 plain content"

    # Inline
    resp_inline = client.get("/api/v1/patientmdtform/doc1.pdf/pdf?inline=true")
    assert resp_inline.status_code == 200
    assert "inline" in resp_inline.headers.get("content-disposition", "")

    # Variant bbox fallback when .bbox does not exist yet
    resp_bbox_fallback = client.get(
        "/api/v1/patientmdtform/doc1.pdf/pdf?inline=true&variant=bbox"
    )
    assert resp_bbox_fallback.status_code == 200
    assert resp_bbox_fallback.content == b"%PDF-1.4 plain content"

    # Variant bbox when .bbox exists on disk
    bbox_pdf = tmp_path / "doc1.pdf.bbox"
    bbox_pdf.write_bytes(b"%PDF-1.4 highlighted bbox content")
    resp_bbox = client.get(
        "/api/v1/patientmdtform/doc1.pdf/pdf?inline=true&variant=bbox"
    )
    assert resp_bbox.status_code == 200
    assert resp_bbox.content == b"%PDF-1.4 highlighted bbox content"
    assert "inline" in resp_bbox.headers.get("content-disposition", "")


# ---------------------------------------------------------------------------
# 5. Per-form computed metrics & mdt_date on patient detail and single form
# ---------------------------------------------------------------------------
def test_per_form_metrics_and_mdt_date_in_detail_and_patient_endpoints(
    api_app, client, tmp_path
):
    """Verify GET /patientmdtform/{f} and GET /patientmdtform/patients/{id} include metrics and mdt_date."""
    patient_repo = InMemoryPatientRepository()
    mdt_repo = InMemoryPatientMDTFormRepository()
    cache_repo = InMemoryDocumentCacheRepository()
    conf = api_deps.get_base_config().model_copy()
    conf.rcp.path = str(tmp_path)

    doc_data: dict[str, Any] = {
        "file": "form_metrics.pdf",
        "processing_status": "COMPLETED",
        "processing_progress_pct": 100.0,
        "PatientAdministrative": {
            "first_name": "Marie",
            "last_name": "Curie",
            "date_birth": "1965-11-07",
            "date_rcp": "2026-03-15",
            "gender": "Female",
        },
        "CareOrientationProposal": {
            "care_adaptation_suggested": True,
            "suggested_priority": "Urgent, a treatment is needed quickly",
            "proposed_care_type": "Surgery",
            "clinical_rationale": "Resectable tumor",
        },
    }
    mdt_repo.upsert_fields("form_metrics.pdf", doc_data)

    service = PatientRecordService(
        patient_repo=patient_repo,
        mdt_form_repo=mdt_repo,
        cache_repo=cache_repo,
        config=conf,
    )
    saved_patient, _ = service.synchronize_patient_from_admin(
        filename="form_metrics.pdf",
        admin_data=doc_data["PatientAdministrative"],
    )
    pid = saved_patient.patient_id

    api_app.dependency_overrides[get_record_service] = lambda: service
    api_app.dependency_overrides[get_mdt_form_repo] = lambda: mdt_repo
    api_app.dependency_overrides[get_domain_config] = lambda: conf

    form_resp = client.get("/api/v1/patientmdtform/form_metrics.pdf")
    assert form_resp.status_code == 200
    form_body = form_resp.json()
    assert "metrics" in form_body and form_body["metrics"] is not None
    assert form_body["metrics"]["urgency_score"] == 0
    assert form_body["metrics"]["last_name"] == "Curie"
    assert form_body["mdt_date"] is not None
    assert form_body["mdt_date"].startswith("2026-03-15")

    patient_resp = client.get(f"/api/v1/patientmdtform/patients/{pid}")
    assert patient_resp.status_code == 200
    p_body = patient_resp.json()
    assert len(p_body["rcps"]) == 1
    rcp_entry = p_body["rcps"][0]
    assert "metrics" in rcp_entry and rcp_entry["metrics"] is not None
    assert rcp_entry["metrics"]["urgency_score"] == 0
    assert rcp_entry["mdt_date"].startswith("2026-03-15")


# ---------------------------------------------------------------------------
# 6. GET /patientmdtform/{filename}/jobs-state & Queue filename filter before limit
# ---------------------------------------------------------------------------
def test_queue_jobs_filename_filter_applied_before_limit_and_jobs_state(
    api_app, client, tmp_path, monkeypatch
):
    """Verify filename filter happens before limit in /queue/jobs and /patientmdtform/{f}/jobs-state works."""
    manager = InMemoryQueueManager(auto_start_workers=False)
    base_time = datetime(2026, 4, 1, 10, 0, 0)
    # Add 5 jobs for different files; target.pdf is older so it's at the end after reverse sort
    j_target = QueueJob(
        filename="target.pdf",
        job_type=JobType.WAVE2_CLINICAL,
        status=JobStatus.PROCESSING,
        priority=20,
        domain="oncology",
        current_step="Extracting clinical",
        created_at=base_time,
    ).model_dump(mode="python")
    j_target["job_type"] = JobType.WAVE2_CLINICAL.value
    j_target["status"] = JobStatus.PROCESSING.value
    manager._jobs[j_target["job_id"]] = j_target

    for idx in range(4):
        j_other = QueueJob(
            filename=f"other_{idx}.pdf",
            job_type=JobType.WAVE1_ADMIN,
            status=JobStatus.PENDING,
            priority=10,
            domain="oncology",
            created_at=base_time + timedelta(minutes=idx + 1),
        ).model_dump(mode="python")
        j_other["job_type"] = JobType.WAVE1_ADMIN.value
        j_other["status"] = JobStatus.PENDING.value
        manager._jobs[j_other["job_id"]] = j_other

    api_app.dependency_overrides[get_queue_manager] = lambda: manager

    # Query with limit=1 and filename=target.pdf -> must return target.pdf even though 4 newer jobs exist
    q_resp = client.get("/api/v1/queue/jobs?filename=target.pdf&limit=1")
    assert q_resp.status_code == 200
    jobs = q_resp.json()
    assert len(jobs) == 1
    assert jobs[0]["filename"] == "target.pdf"

    # Test GET /api/v1/patientmdtform/{filename}/jobs-state
    conf = api_deps.get_base_config().model_copy()
    conf.rcp.path = str(tmp_path)
    conf.queue.api_url = ""
    api_app.dependency_overrides[get_domain_config] = lambda: conf
    monkeypatch.setattr(
        "src.infrastructure.queue.memory_queue.get_global_queue_manager",
        lambda *_a, **_kw: manager,
    )

    patient_repo = InMemoryPatientRepository()
    mdt_repo = InMemoryPatientMDTFormRepository()
    cache_repo = InMemoryDocumentCacheRepository()
    service = PatientRecordService(
        patient_repo=patient_repo,
        mdt_form_repo=mdt_repo,
        cache_repo=cache_repo,
        config=conf,
    )
    ext_service = PatientMDTFormExtractionService(
        config=conf,
        patient_repo=patient_repo,
        mdt_form_repo=mdt_repo,
        cache_repo=cache_repo,
        patient_record_service=service,
    )
    api_app.dependency_overrides[get_extraction_service] = lambda: ext_service

    state_resp = client.get("/api/v1/patientmdtform/target.pdf/jobs-state")
    assert state_resp.status_code == 200
    state_body = state_resp.json()
    assert state_body["has_any_job"] is True
    assert state_body["has_full_job"] is True
    assert state_body["current_step"] == "Extracting clinical"
    assert len(state_body["jobs"]) == 1
    assert state_body["jobs"][0]["filename"] == "target.pdf"


# ---------------------------------------------------------------------------
# 7. Optional language on ChatRequest and ResourceChatRequest
# ---------------------------------------------------------------------------
def test_chat_requests_support_per_request_language_override(
    api_app, client, tmp_path, monkeypatch
):
    """Verify ChatRequest and ResourceChatRequest pass language override to agent without global mutation."""
    patient_repo = InMemoryPatientRepository()
    mdt_repo = InMemoryPatientMDTFormRepository()
    cache_repo = InMemoryDocumentCacheRepository()
    conf = api_deps.get_base_config().model_copy(update={"language": "french"})
    conf.rcp.path = str(tmp_path)
    conf.rcp.additional_path = str(tmp_path)
    (tmp_path / "case_chat.pdf").write_bytes(b"%PDF-1.4 test")
    (tmp_path / "guideline.pdf").write_bytes(b"%PDF-1.4 guideline")

    mdt_repo.upsert_fields(
        "case_chat.pdf",
        {
            "file": "case_chat.pdf",
            "PatientAdministrative": {
                "first_name": "Paul",
                "last_name": "Bernard",
                "date_birth": "1955-01-01",
            },
        },
    )
    service = PatientRecordService(
        patient_repo=patient_repo,
        mdt_form_repo=mdt_repo,
        cache_repo=cache_repo,
        config=conf,
    )
    saved_patient, _ = service.synchronize_patient_from_admin(
        "case_chat.pdf",
        {
            "first_name": "Paul",
            "last_name": "Bernard",
            "date_birth": "1955-01-01",
        },
    )
    pid = saved_patient.patient_id

    api_app.dependency_overrides[get_record_service] = lambda: service
    api_app.dependency_overrides[get_mdt_form_repo] = lambda: mdt_repo
    api_app.dependency_overrides[get_domain_config] = lambda: conf

    captured_languages: list[str] = []

    class DummyAgent:
        def __init__(self, config, **kwargs):
            captured_languages.append(config.language)

        def ask(self, message: str):
            return SimpleNamespace(response=f"Answered: {message}")

    dummy_agents = SimpleNamespace(
        list={"MDT Summary": DummyAgent, "Ressource Assistant": DummyAgent}
    )

    class DummyReader:
        def __init__(self, *args, **kwargs):
            pass

        def read_document(self):
            return None

    class DummyRessources:
        def __init__(self, config):
            pass

        def list_ressources(self):
            return ["guideline.pdf"]

        def is_indexed(self, filename: str):
            return True

    monkeypatch.setattr(
        "src.routers.patientmdtform.get_domain_agents", lambda _d: dummy_agents
    )
    monkeypatch.setattr("src.routers.patientmdtform.DocumentReader", DummyReader)
    monkeypatch.setattr(
        "src.routers.patientmdtform._build_extraction_service",
        lambda c, db=None, filename=None: SimpleNamespace(
            build_patient_readers=lambda files: [DummyReader()]
        ),
    )
    monkeypatch.setattr(
        "src.routers.resources.get_domain_agents", lambda _d: dummy_agents
    )
    monkeypatch.setattr("src.routers.resources.DocumentReader", DummyReader)
    monkeypatch.setattr("src.routers.resources.Ressources", DummyRessources)

    resp1 = client.post(
        f"/api/v1/patientmdtform/patients/{pid}/chat",
        json={
            "agent_name": "MDT Summary",
            "message": "What is the staging?",
            "language": "english",
        },
    )
    assert resp1.status_code == 200
    assert captured_languages[-1] == "english"
    assert conf.language == "french"  # No mutation of shared config

    resp2 = client.post(
        "/api/v1/patientmdtform/case_chat.pdf/chat",
        json={
            "agent_name": "MDT Summary",
            "message": "Summary?",
            "language": "english",
        },
    )
    assert resp2.status_code == 200
    assert captured_languages[-1] == "english"

    resp3 = client.post(
        "/api/v1/resources/guideline.pdf/chat",
        json={"message": "First line?", "language": "english"},
    )
    assert resp3.status_code == 200
    assert captured_languages[-1] == "english"
    assert conf.language == "french"


# ---------------------------------------------------------------------------
# 8. GET /api/v1/patients (?identified_only=true)
# ---------------------------------------------------------------------------
def test_list_raw_patients_and_identified_only_filter(api_app, client, tmp_path):
    """Verify GET /api/v1/patients returns raw patients with display_label and filters unidentified."""
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
        filename="identified.pdf",
        admin_data={
            "first_name": "Claire",
            "last_name": "Moreau",
            "born_name": "Petit",
            "date_birth": "1982-09-20",
            "gender": "Female",
        },
    )
    # Also create an unidentified fallback patient
    service.synchronize_patient_from_admin(
        filename="unidentified.pdf",
        admin_data={},
    )

    api_app.dependency_overrides[get_record_service] = lambda: service

    all_resp = client.get("/api/v1/patients")
    assert all_resp.status_code == 200
    all_patients = all_resp.json()
    assert len(all_patients) == 2

    id_resp = client.get("/api/v1/patients?identified_only=true")
    assert id_resp.status_code == 200
    identified = id_resp.json()
    assert len(identified) == 1
    p = identified[0]
    assert p["patient_id"] == "moreau_claire_1982_09_20"
    assert p["born_name"] == "Petit"
    assert p["gender"] == "Female"
    assert p["files"] == ["identified.pdf"]
    assert "Moreau" in p["display_label"]


# ---------------------------------------------------------------------------
# 9. GET /api/v1/patientmdtform/resolve?patient_id=&file=
# ---------------------------------------------------------------------------
def test_resolve_patient_record_handles_identified_and_unidentified_file(
    api_app, client, tmp_path
):
    """Verify GET /api/v1/patientmdtform/resolve resolves both identified patients and standalone files."""
    patient_repo = InMemoryPatientRepository()
    mdt_repo = InMemoryPatientMDTFormRepository()
    cache_repo = InMemoryDocumentCacheRepository()
    conf = api_deps.get_base_config().model_copy()
    conf.rcp.path = str(tmp_path)

    mdt_repo.upsert_fields(
        "orphan.pdf",
        {
            "file": "orphan.pdf",
            "processing_status": "RUNNING",
            "processing_progress_pct": 25.0,
        },
    )
    mdt_repo.upsert_fields(
        "linked.pdf",
        {
            "file": "linked.pdf",
            "processing_status": "COMPLETED",
            "processing_progress_pct": 100.0,
            "PatientAdministrative": {
                "first_name": "Luc",
                "last_name": "Besson",
                "date_birth": "1959-03-18",
                "date_rcp": "2026-02-10",
            },
        },
    )

    service = PatientRecordService(
        patient_repo=patient_repo,
        mdt_form_repo=mdt_repo,
        cache_repo=cache_repo,
        config=conf,
    )
    saved_patient, _ = service.synchronize_patient_from_admin(
        "linked.pdf",
        {
            "first_name": "Luc",
            "last_name": "Besson",
            "date_birth": "1959-03-18",
            "date_rcp": "2026-02-10",
        },
    )
    pid = saved_patient.patient_id

    api_app.dependency_overrides[get_record_service] = lambda: service
    api_app.dependency_overrides[get_domain_config] = lambda: conf

    # 1) Unidentified orphan file
    resp_orphan = client.get("/api/v1/patientmdtform/resolve?file=orphan.pdf")
    assert resp_orphan.status_code == 200
    body_orphan = resp_orphan.json()
    assert body_orphan["patient"] is None
    assert body_orphan["selected_file"] == "orphan.pdf"
    assert body_orphan["latest_file"] == "orphan.pdf"
    assert len(body_orphan["rcps"]) == 1
    assert body_orphan["rcps"][0]["file"] == "orphan.pdf"
    assert body_orphan["rcps"][0]["metrics"]["processing_status"] == "RUNNING"

    # 2) Identified patient
    resp_linked = client.get(f"/api/v1/patientmdtform/resolve?patient_id={pid}")
    assert resp_linked.status_code == 200
    body_linked = resp_linked.json()
    assert body_linked["patient"]["patient_id"] == pid
    assert body_linked["selected_file"] == "linked.pdf"
    assert body_linked["latest_file"] == "linked.pdf"
    assert len(body_linked["rcps"]) == 1
    assert body_linked["rcps"][0]["mdt_date"].startswith("2026-02-10")


# ---------------------------------------------------------------------------
# 10 & 11. Batch upload with batch_id, GET /batches/{batch_id}, GET /{filename}/status
# ---------------------------------------------------------------------------
def test_upload_with_batch_id_and_batch_and_file_status_endpoints(
    api_app, client, tmp_path, monkeypatch
):
    """Verify POST /patientmdtform/upload accepts batch_id, GET /batches/{id}, and GET /{f}/status."""
    patient_repo = InMemoryPatientRepository()
    mdt_repo = InMemoryPatientMDTFormRepository()
    cache_repo = InMemoryDocumentCacheRepository()
    conf = api_deps.get_base_config().model_copy()
    conf.rcp.path = str(tmp_path)
    conf.rcp.display_type = "mongodb"
    conf.queue.enabled = True
    conf.queue.api_url = ""

    service = PatientRecordService(
        patient_repo=patient_repo,
        mdt_form_repo=mdt_repo,
        cache_repo=cache_repo,
        config=conf,
    )
    manager = InMemoryQueueManager(auto_start_workers=False)
    monkeypatch.setattr(
        manager.executor,
        "on_job_enqueued",
        lambda **kw: mdt_repo.upsert_fields(
            kw["filename"],
            {
                "file": kw["filename"],
                "processing_status": "PENDING",
                "processing_step": "QUEUED",
                "processing_progress_pct": 5.0,
            },
        ),
    )

    def build_ext_service(c, db=None, filename=None):
        return PatientMDTFormExtractionService(
            config=c,
            patient_repo=patient_repo,
            mdt_form_repo=mdt_repo,
            cache_repo=cache_repo,
            patient_record_service=service,
            filename=filename,
        )

    api_app.dependency_overrides[get_record_service] = lambda: service
    api_app.dependency_overrides[get_mdt_form_repo] = lambda: mdt_repo
    api_app.dependency_overrides[get_domain_config] = lambda: conf
    api_app.dependency_overrides[get_queue_manager] = lambda: manager
    api_app.dependency_overrides[get_extraction_service] = lambda: build_ext_service(
        conf
    )
    monkeypatch.setattr(
        "src.routers.patientmdtform._build_extraction_service", build_ext_service
    )
    monkeypatch.setattr(
        "src.infrastructure.queue.memory_queue.get_global_queue_manager",
        lambda *_a, **_kw: manager,
    )

    upload_resp = client.post(
        "/api/v1/patientmdtform/upload",
        files={"file": ("batch_doc1.pdf", b"%PDF-1.4 content", "application/pdf")},
        data={"batch_id": "batch_shared_123"},
    )
    assert upload_resp.status_code == 200
    up_body = upload_resp.json()
    assert up_body["batch_id"] == "batch_shared_123"
    uploaded_filename = up_body["filename"]
    assert uploaded_filename.endswith(".pdf")

    # Seed initial status in mdt_repo for the uploaded file
    mdt_repo.upsert_fields(
        uploaded_filename,
        {
            "file": uploaded_filename,
            "processing_status": "PENDING",
            "processing_step": "QUEUED",
            "processing_progress_pct": 5.0,
        },
    )

    # Check GET /api/v1/patientmdtform/batches/{batch_id}
    batch_resp = client.get("/api/v1/patientmdtform/batches/batch_shared_123")
    assert batch_resp.status_code == 200
    batch_body = batch_resp.json()
    assert batch_body["batch_id"] == "batch_shared_123"
    assert len(batch_body["files"]) == 1
    file_item = batch_body["files"][0]
    assert file_item["filename"] == uploaded_filename
    assert file_item["processing_status"] == "PENDING"
    assert file_item["pct"] >= 5.0

    # Check GET /api/v1/patientmdtform/{filename}/status
    status_resp = client.get(f"/api/v1/patientmdtform/{uploaded_filename}/status")
    assert status_resp.status_code == 200
    st_body = status_resp.json()
    assert st_body["processing_status"] == "PENDING"
    assert st_body["processing_step"] == "QUEUED"
    assert st_body["processing_progress_pct"] == 5.0


# ---------------------------------------------------------------------------
# 12. GET /api/v1/me & require_admin on destructive endpoints
# ---------------------------------------------------------------------------
def test_me_endpoint_and_require_admin_protection(api_app, client, monkeypatch):
    """Verify GET /api/v1/me and require_admin enforce proxy secret and admin role."""
    conf = api_deps.get_base_config().model_copy()
    conf.proxy_secret = SecretStr("top-secret-proxy")
    conf.admin_users = "dr_admin,Dr Admin"
    monkeypatch.setattr(api_deps, "get_base_config", lambda: conf)

    manager = InMemoryQueueManager(auto_start_workers=False)
    api_app.dependency_overrides[get_queue_manager] = lambda: manager

    # 1. Spoofed user header WITHOUT valid proxy secret -> ignored on /me
    me_spoof = client.get(
        "/api/v1/me",
        headers={"X-Oncoflow-User": "dr_admin"},
    )
    assert me_spoof.status_code == 200
    assert me_spoof.json() == {
        "username": None,
        "display_name": None,
        "is_admin": False,
    }

    # 2. Valid proxy secret + non-admin user
    me_user = client.get(
        "/api/v1/me",
        headers={
            "X-Oncoflow-Proxy-Secret": "top-secret-proxy",
            "X-Oncoflow-User": "dr_regular",
            "X-Oncoflow-User-Name": "Dr Regular",
        },
    )
    assert me_user.status_code == 200
    assert me_user.json() == {
        "username": "dr_regular",
        "display_name": "Dr Regular",
        "is_admin": False,
    }

    # 3. Valid proxy secret + admin user
    me_admin = client.get(
        "/api/v1/me",
        headers={
            "X-Oncoflow-Proxy-Secret": "top-secret-proxy",
            "X-Oncoflow-User": "dr_admin",
            "X-Oncoflow-User-Name": "Dr Admin",
        },
    )
    assert me_admin.status_code == 200
    assert me_admin.json() == {
        "username": "dr_admin",
        "display_name": "Dr Admin",
        "is_admin": True,
    }

    # 4. Non-admin blocked on destructive endpoints
    non_admin_headers = {
        "X-Oncoflow-Proxy-Secret": "top-secret-proxy",
        "X-Oncoflow-User": "dr_regular",
    }
    assert (
        client.post("/api/v1/queue/clean", headers=non_admin_headers).status_code == 403
    )
    assert (
        client.delete(
            "/api/v1/queue/locks?force_all=true", headers=non_admin_headers
        ).status_code
        == 403
    )
    assert (
        client.delete("/api/v1/queue/jobs/job1", headers=non_admin_headers).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/queue/jobs/job1/retry", headers=non_admin_headers
        ).status_code
        == 403
    )
    assert (
        client.delete(
            "/api/v1/patientmdtform/patients/p1", headers=non_admin_headers
        ).status_code
        == 403
    )

    # 5. Spoofed admin header WITHOUT valid proxy secret blocked on destructive endpoints
    spoof_headers = {"X-Oncoflow-User": "dr_admin"}
    assert client.post("/api/v1/queue/clean", headers=spoof_headers).status_code == 403
    assert (
        client.delete(
            "/api/v1/patientmdtform/patients/p1", headers=spoof_headers
        ).status_code
        == 403
    )

    # 6. Admin with valid proxy secret allowed on destructive endpoints
    admin_headers = {
        "X-Oncoflow-Proxy-Secret": "top-secret-proxy",
        "X-Oncoflow-User": "dr_admin",
    }
    assert client.post("/api/v1/queue/clean", headers=admin_headers).status_code == 200
    assert (
        client.delete(
            "/api/v1/queue/locks?force_all=true", headers=admin_headers
        ).status_code
        == 200
    )

    # 7. Internal service call (no X-Oncoflow-User header) remains allowed
    assert client.post("/api/v1/queue/clean").status_code == 200


# ---------------------------------------------------------------------------
# 13. Per-section rerun preserves manual edits when preserve_manual_edits=True
# ---------------------------------------------------------------------------
def test_per_section_rerun_honours_preserve_manual_edits(
    api_app, client, tmp_path, monkeypatch
):
    """Verify POST /{f}/process {model_name} honours preserve_manual_edits."""
    patient_repo = InMemoryPatientRepository()
    mdt_repo = InMemoryPatientMDTFormRepository()
    cache_repo = InMemoryDocumentCacheRepository()
    conf = api_deps.get_base_config().model_copy()
    conf.rcp.path = str(tmp_path)
    (tmp_path / "manual_case.pdf").write_bytes(b"%PDF-1.4 content")

    # Seed document with a manual edit on PatientPerformanceStatus
    mdt_repo.upsert_fields(
        "manual_case.pdf",
        {
            "file": "manual_case.pdf",
            "PatientPerformanceStatus": {"who_performance_status": 1},
            "manual_edits": {
                "PatientPerformanceStatus": {
                    "is_manual": True,
                    "edited_at": "2026-04-01T10:00:00Z",
                    "edited_by": "dr_house",
                    "human_value": {"who_performance_status": 1},
                    "modified_fields": {
                        "who_performance_status": {"ai_value": 0, "human_value": 1}
                    },
                }
            },
        },
    )

    service = PatientRecordService(
        patient_repo=patient_repo,
        mdt_form_repo=mdt_repo,
        cache_repo=cache_repo,
        config=conf,
    )
    api_app.dependency_overrides[get_record_service] = lambda: service
    api_app.dependency_overrides[get_mdt_form_repo] = lambda: mdt_repo
    api_app.dependency_overrides[get_domain_config] = lambda: conf

    # Force synchronous path in POST /{f}/process
    monkeypatch.setattr(
        "src.routers.patientmdtform._is_queue_enabled", lambda _c: False
    )

    class DummyReader:
        def __init__(self, **kwargs):
            pass

        def read_document(self):
            return None

    monkeypatch.setattr("src.routers.patientmdtform.DocumentReader", DummyReader)

    extract_called = {"count": 0}

    def spy_extract_section(self, model_cls, **kwargs):
        extract_called["count"] += 1
        target_form = kwargs.get("form") or self.form
        clear_manual_flag = kwargs.get("clear_manual_flag", False)
        instance = model_cls(who_performance_status=3)
        target_form.set_section(model_cls.__name__, instance)
        if clear_manual_flag and model_cls.__name__ in target_form.manual_edits:
            target_form.manual_edits = (
                self.form_cls.archive_manual_edit_before_ai_rerun(
                    target_form.manual_edits, model_cls.__name__
                )
            )
        update_dict = {model_cls.__name__: instance.model_dump(mode="json")}
        if clear_manual_flag:
            update_dict["manual_edits"] = dict(target_form.manual_edits)
        mdt_repo.upsert_fields("manual_case.pdf", update_dict)
        return instance

    monkeypatch.setattr(
        PatientMDTFormExtractionService, "extract_section", spy_extract_section
    )
    monkeypatch.setattr(
        "src.routers.patientmdtform._build_extraction_service",
        lambda c, db=None, filename=None: PatientMDTFormExtractionService(
            config=c,
            patient_repo=patient_repo,
            mdt_form_repo=mdt_repo,
            cache_repo=cache_repo,
            patient_record_service=service,
            filename=filename,
        ),
    )

    # A) Calling POST /{f}/process with model_name and preserve_manual_edits=True (default)
    # must NOT overwrite or clear the manual flag!
    resp_preserve = client.post(
        "/api/v1/patientmdtform/manual_case.pdf/process",
        json={
            "model_name": "PatientPerformanceStatus",
            "preserve_manual_edits": True,
        },
    )
    assert resp_preserve.status_code == 200
    stored_after_preserve = mdt_repo.get_by_file("manual_case.pdf")
    assert (
        stored_after_preserve["manual_edits"]["PatientPerformanceStatus"]["is_manual"]
        is True
    )
    assert (
        stored_after_preserve["PatientPerformanceStatus"]["who_performance_status"] == 1
    )
    assert extract_called["count"] == 0

    # B) Calling POST /{f}/process with model_name and preserve_manual_edits=False
    # must re-extract and archive the manual flag (setting is_manual=False) without wiping manual_edits dict!
    resp_overwrite = client.post(
        "/api/v1/patientmdtform/manual_case.pdf/process",
        json={
            "model_name": "PatientPerformanceStatus",
            "preserve_manual_edits": False,
        },
    )
    assert resp_overwrite.status_code == 200
    stored_after_overwrite = mdt_repo.get_by_file("manual_case.pdf")
    assert (
        stored_after_overwrite["manual_edits"]["PatientPerformanceStatus"]["is_manual"]
        is False
    )
    assert (
        len(
            stored_after_overwrite["manual_edits"]["PatientPerformanceStatus"].get(
                "archived_judge_traces", []
            )
        )
        == 1
    )
    assert (
        stored_after_overwrite["PatientPerformanceStatus"]["who_performance_status"]
        == 3
    )
    assert extract_called["count"] == 1
