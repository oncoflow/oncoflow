from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from src.application.config import AppConfig
from src.application.use_cases.patient_record import PatientRecordService
from src.domain.patient import Patient
from src.domain.patient_dashboard import (
    evaluate_patient_record_summary_obsolescence,
    get_domain_metric_descriptors,
    build_patient_metric_series,
    parse_raw_metric_value,
)
from src.domain.sma.patient_mdt_sma_form import PatientMDTSmaForm
from src.domain.oncology.patient_mdt_oncologic_form import PatientMDTOncologicForm
from src.domain.worker.queue_job import JobPriority, JobStatus, JobType
from src.infrastructure.documents.repositories import (
    InMemoryPatientMDTFormRepository,
    InMemoryPatientRepository,
)
from src.infrastructure.queue.memory_queue import InMemoryQueueManager


# ---------------------------------------------------------------------------
# 1. Non-Integer Raw Motor Scores (RULM / HFMSE / CHOP-INTEND) in SMA Form
# ---------------------------------------------------------------------------


def test_sma_motor_function_accepts_int_float_ratio_bilateral_and_annotative_raw_values():
    """MotorFunctionStatus must accept int, float, ratio, bilateral, and annotative strings."""
    # Integer values
    m_int = PatientMDTSmaForm.MotorFunctionStatus(
        sma_type="Type 2",
        motor_milestones=["Assis sans appui"],
        hfmse_score=42,
        chop_intend_score=50,
        rulm_score=32,
    )
    assert m_int.rulm_score == 32
    assert m_int.hfmse_score == 42

    # Float values
    m_float = PatientMDTSmaForm.MotorFunctionStatus(
        sma_type="Type 2",
        motor_milestones=["Assis sans appui"],
        rulm_score=31.5,
    )
    assert m_float.rulm_score == 31.5

    # Ratio strings (e.g., "34/37")
    m_ratio = PatientMDTSmaForm.MotorFunctionStatus(
        sma_type="Type 2",
        motor_milestones=["Assis sans appui"],
        rulm_score="34/37",
        hfmse_score="40/66",
    )
    assert m_ratio.rulm_score == "34/37"
    assert m_ratio.hfmse_score == "40/66"

    # Bilateral strings (e.g., "28 (D) / 30 (G)")
    m_bilat = PatientMDTSmaForm.MotorFunctionStatus(
        sma_type="Type 3",
        motor_milestones=["Station debout"],
        rulm_score="28 (D) / 30 (G)",
    )
    assert m_bilat.rulm_score == "28 (D) / 30 (G)"

    # Annotative / qualitative strings
    m_annot = PatientMDTSmaForm.MotorFunctionStatus(
        sma_type="Type 2",
        motor_milestones=["Tenue de tête"],
        rulm_score="Non testable (fatigue)",
    )
    assert m_annot.rulm_score == "Non testable (fatigue)"


def test_sma_motor_function_rejects_out_of_bounds_numeric_scores():
    """Pure numeric scores outside clinical scale bounds (e.g. RULM > 37 or < 0) must still fail validation."""
    with pytest.raises(ValidationError):
        PatientMDTSmaForm.MotorFunctionStatus(
            sma_type="Type 2",
            motor_milestones=[],
            rulm_score=45,
        )

    with pytest.raises(ValidationError):
        PatientMDTSmaForm.MotorFunctionStatus(
            sma_type="Type 2",
            motor_milestones=[],
            rulm_score=-2,
        )

    with pytest.raises(ValidationError):
        PatientMDTSmaForm.MotorFunctionStatus(
            sma_type="Type 2",
            motor_milestones=[],
            hfmse_score=75,
        )


# ---------------------------------------------------------------------------
# 2. Raw Metric Parsing & Multi-Year Longitudinal Series
# ---------------------------------------------------------------------------


def test_parse_raw_metric_value_preserves_raw_and_extracts_numeric_or_bilateral():
    """parse_raw_metric_value must keep raw_value untouched while extracting plotting coordinates."""
    descriptors = {d.metric_key: d for d in get_domain_metric_descriptors("sma")}
    rulm_desc = descriptors["MotorFunctionStatus.rulm_score"]

    obs_ratio = parse_raw_metric_value("34/37", rulm_desc)
    assert obs_ratio.raw_value == "34/37"
    assert obs_ratio.display_value == "34/37"
    assert obs_ratio.numeric_value == 34.0
    assert obs_ratio.is_annotative_only is False

    obs_bilat = parse_raw_metric_value("28 (D) / 30 (G)", rulm_desc)
    assert obs_bilat.raw_value == "28 (D) / 30 (G)"
    assert obs_bilat.display_value == "28 (D) / 30 (G)"
    assert obs_bilat.sub_values == {"D": 28.0, "G": 30.0}
    assert obs_bilat.numeric_value == 29.0
    assert obs_bilat.is_annotative_only is False

    obs_annot = parse_raw_metric_value("Non testé (fatigue)", rulm_desc)
    assert obs_annot.raw_value == "Non testé (fatigue)"
    assert obs_annot.display_value == "Non testé (fatigue)"
    assert obs_annot.numeric_value is None
    assert obs_annot.is_annotative_only is True


def test_build_patient_metric_series_multi_year_proportional_timeline():
    """Multi-year forms (2021 -> 2026) must produce chronological series with proportional x_ratio and manual flags."""
    forms = [
        {
            "file": "rcp_2026.pdf",
            "PatientAdministrative": {"date_rcp": "2026-03-10"},
            "MotorFunctionStatus": {
                "sma_type": "Type 2",
                "motor_milestones": ["Assis sans appui", "Fauteuil électrique"],
                "rulm_score": "34/37",
                "hfmse_score": 44,
            },
            "RespiratoryFunction": {
                "requires_ventilation_support": True,
                "ventilation_type": "Non-invasive ventilation (NIV/BiPAP)",
                "forced_vital_capacity_percent": 68.0,
            },
            "manual_edits": {
                "MotorFunctionStatus": {
                    "edited_at": "2026-03-11T10:00:00",
                    "edited_by": "Dr. Martin",
                }
            },
        },
        {
            "file": "rcp_2024.pdf",
            "PatientAdministrative": {"date_rcp": "2024-03-10"},
            "MotorFunctionStatus": {
                "sma_type": "Type 2",
                "motor_milestones": ["Assis sans appui"],
                "rulm_score": "Non testé (fatigue)",
                "hfmse_score": 40,
            },
            "RespiratoryFunction": {
                "requires_ventilation_support": False,
                "ventilation_type": "None",
                "forced_vital_capacity_percent": 72.0,
            },
        },
        {
            "file": "rcp_2021.pdf",
            "PatientAdministrative": {"date_rcp": "2021-03-10"},
            "MotorFunctionStatus": {
                "sma_type": "Type 2",
                "motor_milestones": ["Assis sans appui"],
                "rulm_score": "28 (D) / 30 (G)",
                "hfmse_score": 36,
            },
            "RespiratoryFunction": {
                "requires_ventilation_support": False,
                "ventilation_type": "None",
                "forced_vital_capacity_percent": 78.0,
            },
        },
    ]

    series_list = build_patient_metric_series(forms, domain="sma")
    by_key = {s.metric_key: s for s in series_list}

    assert "MotorFunctionStatus.rulm_score" in by_key
    rulm_series = by_key["MotorFunctionStatus.rulm_score"]
    assert len(rulm_series.points) == 3

    # Chronological order: 2021 -> 2024 -> 2026
    p0, p1, p2 = rulm_series.points
    assert p0.form_id == "rcp_2021.pdf"
    assert p0.x_ratio == pytest.approx(0.0)
    assert p0.days_since_first_rcp == 0
    assert p0.display_value == "28 (D) / 30 (G)"
    assert p0.sub_values == {"D": 28.0, "G": 30.0}
    assert p0.is_manual is False

    assert p1.form_id == "rcp_2024.pdf"
    assert 0.55 < p1.x_ratio < 0.65
    assert p1.display_value == "Non testé (fatigue)"
    assert p1.is_annotative_only is True
    assert p1.numeric_value is None

    assert p2.form_id == "rcp_2026.pdf"
    assert p2.x_ratio == pytest.approx(1.0)
    assert p2.display_value == "34/37"
    assert p2.numeric_value == 34.0
    assert p2.is_manual is True
    # Delta compared to previous numeric point (29.0 -> 34.0 = +5.0)
    assert p2.delta_numeric == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# 3. Summary Obsolescence Evaluation & Queue Execution
# ---------------------------------------------------------------------------


def test_evaluate_patient_record_summary_obsolescence_detects_new_and_updated_forms():
    """Obsolescence check must flag when a newer PatientMDTForm is added or an existing one is refreshed."""
    t0 = datetime(2025, 6, 1, 10, 0, 0)
    t_gen = datetime(2025, 6, 2, 12, 0, 0)
    t_new = datetime(2026, 11, 5, 14, 30, 0)

    summary_snapshot = {
        "generated_at": t_gen.isoformat(),
        "covered_form_ids": ["rcp_2024.pdf", "rcp_2025.pdf"],
        "latest_form_id_at_generation": "rcp_2025.pdf",
        "latest_form_date_at_generation": "2025-06-01T00:00:00",
        "model_used": "mistral-nemo",
        "content": {
            "clinical_trajectory_overview": "Évolution favorable sous risdiplam.",
            "disease_and_treatment_evolution": "Stabilisation motrice.",
            "notable_metric_changes": ["HFMSE +4 pts"],
            "unresolved_vigilance_points": ["Surveillance CVF"],
            "mdt_decisions_recap": ["Poursuite risdiplam"],
            "sources_used": ["rcp_2024.pdf", "rcp_2025.pdf"],
        },
    }

    forms_up_to_date = [
        {
            "file": "rcp_2024.pdf",
            "date_refresh": t0 - timedelta(days=365),
            "PatientAdministrative": {"date_rcp": "2024-06-01"},
        },
        {
            "file": "rcp_2025.pdf",
            "date_refresh": t0,
            "PatientAdministrative": {"date_rcp": "2025-06-01"},
        },
    ]

    state_ok = evaluate_patient_record_summary_obsolescence(
        summary_snapshot, forms_up_to_date
    )
    assert state_ok is not None
    assert state_ok["is_obsolete"] is False
    assert state_ok["new_forms_since_summary"] == []

    # Add a new 2026 form
    forms_with_new = forms_up_to_date + [
        {
            "file": "rcp_2026.pdf",
            "date_refresh": t_new,
            "PatientAdministrative": {"date_rcp": "2026-11-05"},
        }
    ]
    state_obsolete_new = evaluate_patient_record_summary_obsolescence(
        summary_snapshot, forms_with_new
    )
    assert state_obsolete_new is not None
    assert state_obsolete_new["is_obsolete"] is True
    assert state_obsolete_new["new_forms_since_summary"] == ["rcp_2026.pdf"]
    assert "NEW_FORM_ADDED" in state_obsolete_new["obsolete_reasons"]

    # Modify an existing form after t_gen
    forms_modified = [
        forms_up_to_date[0],
        {
            "file": "rcp_2025.pdf",
            "date_refresh": t_new,
            "PatientAdministrative": {"date_rcp": "2025-06-01"},
        },
    ]
    state_obsolete_mod = evaluate_patient_record_summary_obsolescence(
        summary_snapshot, forms_modified
    )
    assert state_obsolete_mod is not None
    assert state_obsolete_mod["is_obsolete"] is True
    assert state_obsolete_mod["modified_forms_since_summary"] == ["rcp_2025.pdf"]
    assert "EXISTING_FORM_UPDATED" in state_obsolete_mod["obsolete_reasons"]


def test_patient_record_service_dashboard_and_summary_queue_lifecycle():
    """
    Full lifecycle test:
    1. Build dashboard with multi-year forms and no summary yet.
    2. Enqueue summary job in PriorityQueue (`JobType.PATIENT_SUMMARY`).
    3. Execute summary job via worker -> summary is persisted on `Patient` with `is_obsolete=False`.
    4. Attach a newer `PatientMDTForm` to the patient -> `record_summary` is preserved and `is_obsolete` becomes `True`!
    """
    patient = Patient(
        patient_id="dupont_jean_2015_04_12",
        first_name="Jean",
        last_name="Dupont",
        date_birth="2015-04-12",
        files=["rcp_2022.pdf", "rcp_2024.pdf"],
    )
    forms = [
        {
            "file": "rcp_2022.pdf",
            "patient_id": "dupont_jean_2015_04_12",
            "date_refresh": datetime(2022, 5, 10, 9, 0, 0),
            "processing_status": "COMPLETED",
            "PatientAdministrative": {
                "first_name": "Jean",
                "last_name": "Dupont",
                "date_birth": "2015-04-12",
                "date_rcp": "2022-05-10",
            },
            "MotorFunctionStatus": {
                "sma_type": "Type 2",
                "motor_milestones": ["Assis sans appui"],
                "rulm_score": "29/37",
                "hfmse_score": 38,
            },
            "CareOrientationProposal": {
                "care_adaptation_suggested": True,
                "suggested_priority": 1,
                "proposed_care_type": "Initiation risdiplam",
                "clinical_rationale": "Indication validée en RCP.",
            },
        },
        {
            "file": "rcp_2024.pdf",
            "patient_id": "dupont_jean_2015_04_12",
            "date_refresh": datetime(2024, 5, 15, 9, 0, 0),
            "processing_status": "COMPLETED",
            "PatientAdministrative": {
                "first_name": "Jean",
                "last_name": "Dupont",
                "date_birth": "2015-04-12",
                "date_rcp": "2024-05-15",
            },
            "MotorFunctionStatus": {
                "sma_type": "Type 2",
                "motor_milestones": ["Assis sans appui", "Tenue debout avec attelles"],
                "rulm_score": "33/37",
                "hfmse_score": 43,
            },
            "CareOrientationProposal": {
                "care_adaptation_suggested": False,
                "suggested_priority": 2,
                "proposed_care_type": "Poursuite risdiplam et kinésithérapie",
                "clinical_rationale": "Gain fonctionnel +4 pts RULM.",
            },
        },
    ]

    patient_repo = InMemoryPatientRepository([patient])
    form_repo = InMemoryPatientMDTFormRepository(forms)

    class InMemorySummaryExecutor:
        def on_job_enqueued(self, domain, filename, status, extra_fields=None):
            pass

        def on_job_failed(self, domain, filename, error_message):
            pass

        def stabilize_status(self, domain, filename):
            pass

        def has_administrative_data(self, domain, filename):
            return True

        def execute_wave1_admin(self, job, lease_id, queue_manager):
            return job.get("target_patient_id")

        def execute_wave2_clinical(self, job, lease_id, queue_manager):
            pass

        def execute_wave3_experts(self, job, lease_id, queue_manager):
            pass

        def execute_single_model(self, job, lease_id, queue_manager):
            pass

        def execute_patient_record_summary(self, job, lease_id, queue_manager):
            pid = job.get("target_patient_id") or job.get("filename")
            svc.generate_and_save_patient_record_summary(pid)

        def recover_unfinished_jobs(self, queue_manager):
            return 0

        def on_queue_idle(self):
            pass

    base_conf = AppConfig(domain="sma")
    queue_mgr = InMemoryQueueManager(
        base_config=base_conf,
        auto_start_workers=False,
        executor=InMemorySummaryExecutor(),
    )

    svc = PatientRecordService(
        patient_repo=patient_repo,
        mdt_form_repo=form_repo,
        queue_broker=queue_mgr,
        form_cls=PatientMDTSmaForm,
        config=base_conf,
    )

    # 1. Dashboard before summary generation
    dash_initial = svc.get_patient_record_dashboard("dupont_jean_2015_04_12")
    assert dash_initial is not None
    assert dash_initial["rcp_count"] == 2
    assert dash_initial["summary"]["has_summary"] is False
    assert dash_initial["summary"]["is_obsolete"] is False

    # 2. Trigger summary generation -> enqueued in AI PriorityQueue
    trig = svc.trigger_patient_record_summary("dupont_jean_2015_04_12")
    assert trig["queued"] is True
    assert trig["already_queued"] is False
    assert trig["job"]["job_type"] == JobType.PATIENT_SUMMARY.value
    assert trig["job"]["priority"] == JobPriority.PATIENT_SUMMARY

    # Calling trigger again while pending returns already_queued=True
    trig_dup = svc.trigger_patient_record_summary("dupont_jean_2015_04_12")
    assert trig_dup["already_queued"] is True

    # Dashboard while queued exposes active_job
    dash_queued = svc.get_patient_record_dashboard("dupont_jean_2015_04_12")
    assert dash_queued is not None
    assert dash_queued["summary"]["active_job"] is not None
    assert dash_queued["summary"]["active_job"]["status"] == JobStatus.PENDING.value

    # 3. Execute job via queue worker
    executed = queue_mgr.run_once(domain="sma")
    assert executed is True

    dash_ready = svc.get_patient_record_dashboard("dupont_jean_2015_04_12")
    assert dash_ready is not None
    assert dash_ready["summary"]["has_summary"] is True
    assert dash_ready["summary"]["is_obsolete"] is False
    assert dash_ready["summary"]["generated_at"] is not None
    assert set(dash_ready["summary"]["covered_form_ids"]) == {
        "rcp_2022.pdf",
        "rcp_2024.pdf",
    }
    assert dash_ready["summary"]["content"]["clinical_trajectory_overview"] != ""

    # 4. Attach a newer 2026 PatientMDTForm -> summary must be preserved and flagged as obsolete!
    new_form_2026 = {
        "file": "rcp_2026.pdf",
        "patient_id": "dupont_jean_2015_04_12",
        "date_refresh": datetime.now() + timedelta(seconds=10),
        "processing_status": "COMPLETED",
        "PatientAdministrative": {
            "first_name": "Jean",
            "last_name": "Dupont",
            "date_birth": "2015-04-12",
            "date_rcp": "2026-11-05",
        },
        "MotorFunctionStatus": {
            "sma_type": "Type 2",
            "motor_milestones": ["Assis sans appui"],
            "rulm_score": "34/37",
            "hfmse_score": 45,
        },
    }
    form_repo.save_full("rcp_2026.pdf", new_form_2026)
    svc.synchronize_patient_from_admin(
        filename="rcp_2026.pdf",
        admin_data=new_form_2026["PatientAdministrative"],
        target_patient_id="dupont_jean_2015_04_12",
    )

    dash_after_new_form = svc.get_patient_record_dashboard("dupont_jean_2015_04_12")
    assert dash_after_new_form is not None
    assert dash_after_new_form["rcp_count"] == 3
    assert dash_after_new_form["summary"]["has_summary"] is True
    assert dash_after_new_form["summary"]["is_obsolete"] is True
    assert dash_after_new_form["summary"]["new_forms_since_summary"] == ["rcp_2026.pdf"]


# ---------------------------------------------------------------------------
# 4. FastAPI Router Endpoints (/dashboard & /summary)
# ---------------------------------------------------------------------------


def test_patient_dashboard_and_summary_fastapi_endpoints():
    """FastAPI endpoints GET /patients/{id}/dashboard and POST /patients/{id}/summary must return valid schemas."""
    from fastapi import FastAPI
    from src.routers.patientmdtform import get_record_service, router

    patient = Patient(
        patient_id="martin_claire_1968_09_21",
        first_name="Claire",
        last_name="Martin",
        date_birth="1968-09-21",
        files=["rcp_onco_2023.pdf", "rcp_onco_2026.pdf"],
    )
    forms: list[dict[str, Any]] = [
        {
            "file": "rcp_onco_2023.pdf",
            "patient_id": "martin_claire_1968_09_21",
            "date_refresh": datetime(2023, 4, 10, 10, 0, 0),
            "processing_status": "COMPLETED",
            "PatientAdministrative": {
                "first_name": "Claire",
                "last_name": "Martin",
                "date_birth": "1968-09-21",
                "date_rcp": "2023-04-10",
            },
            "PatientPerformanceStatus": {"performance_status": 0},
            "CancerDescription": {
                "type_of_cancer": "Adénocarcinome pancréatique",
                "tnm_status": "cT2N0M0",
                "figo_stage": "Non applicable",
            },
        },
        {
            "file": "rcp_onco_2026.pdf",
            "patient_id": "martin_claire_1968_09_21",
            "date_refresh": datetime(2026, 10, 15, 10, 0, 0),
            "processing_status": "COMPLETED",
            "PatientAdministrative": {
                "first_name": "Claire",
                "last_name": "Martin",
                "date_birth": "1968-09-21",
                "date_rcp": "2026-10-15",
            },
            "PatientPerformanceStatus": {"performance_status": 1},
            "CancerDescription": {
                "type_of_cancer": "Adénocarcinome pancréatique",
                "tnm_status": "ypT1N0M0",
                "figo_stage": "Non applicable",
            },
        },
    ]

    patient_repo = InMemoryPatientRepository([patient])
    form_repo = InMemoryPatientMDTFormRepository(forms)
    svc = PatientRecordService(
        patient_repo=patient_repo,
        mdt_form_repo=form_repo,
        queue_broker=None,
        form_cls=PatientMDTOncologicForm,
        config=AppConfig(domain="oncology"),
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_record_service] = lambda: svc

    client = TestClient(app)

    # GET dashboard
    resp_dash = client.get(
        "/api/v1/patientmdtform/patients/martin_claire_1968_09_21/dashboard"
    )
    assert resp_dash.status_code == 200
    body = resp_dash.json()
    assert body["patient"]["patient_id"] == "martin_claire_1968_09_21"
    assert body["rcp_count"] == 2
    assert len(body["metrics"]) >= 2
    assert body["summary"]["has_summary"] is False

    # POST summary (synchronous fallback when queue_broker is None)
    resp_post = client.post(
        "/api/v1/patientmdtform/patients/martin_claire_1968_09_21/summary",
        json={"force": True},
    )
    assert resp_post.status_code == 200
    post_body = resp_post.json()
    assert post_body["summary"]["has_summary"] is True
    assert post_body["summary"]["is_obsolete"] is False
    assert post_body["summary"]["generated_at"] is not None


# ---------------------------------------------------------------------------
# 5. Enriched Oncology Clinical Sections & Longitudinal Metric Series
# ---------------------------------------------------------------------------


def test_oncology_enriched_clinical_sections_and_longitudinal_metrics():
    """
    PatientMDTOncologicForm must expose and validate the enriched TNCD digestive oncology
    sections (`CancerDescription`, `TumorBiology`, `SurgicalStatus`, `NutritionalStatus`,
    `HepaticStatus`) and `build_patient_metric_series(domain="oncology")` must extract
    numeric and categorical series across longitudinal forms.
    """
    # 1. Verify section models exist on PatientMDTOncologicForm
    for sec_name in (
        "CancerDescription",
        "TumorBiology",
        "SurgicalStatus",
        "NutritionalStatus",
        "HepaticStatus",
    ):
        assert hasattr(PatientMDTOncologicForm, sec_name), f"Missing section {sec_name}"
        sec_cls = getattr(PatientMDTOncologicForm, sec_name)
        assert PatientMDTOncologicForm.is_section_manually_editable(sec_cls) is True

    # 2. Validate Pydantic models directly
    cancer_desc = PatientMDTOncologicForm.CancerDescription(
        type_of_cancer="Adénocarcinome canalaire pancréatique",
        histological_grade="G2 (modérément différencié)",
        tnm_status="cT3N1M0",
        figo_stage="Non applicable",
        metastatic_status=False,
        metastatic_sites=[],
        target_lesion_size_mm=28.0,
        recist_response="Réponse partielle (RP)",
    )
    assert cancer_desc.tnm_status == "cT3N1M0"
    assert cancer_desc.target_lesion_size_mm == 28.0

    tumor_bio = PatientMDTOncologicForm.TumorBiology(
        msi_state=False,
        ca19_9="180 U/mL",
        ace=3.2,
        afp=None,
        dpd_uracilemia=8.5,
        ras_braf_status="KRAS G12D muté, BRAF sauvage",
        her2_status="HER2 négatif (0)",
    )
    assert tumor_bio.msi_state is False
    assert tumor_bio.ca19_9 == "180 U/mL"
    assert tumor_bio.dpd_uracilemia == 8.5

    surg_status = PatientMDTOncologicForm.SurgicalStatus(
        resectability_status="Borderline",
        surgery_done=False,
        resection_margin=None,
    )
    assert surg_status.resectability_status == "Borderline"
    assert surg_status.surgery_done is False

    nutri_status = PatientMDTOncologicForm.NutritionalStatus(
        weight_kg=62.5,
        weight_loss_percent=8.0,
        bmi=21.6,
        nutritional_status="Dénutrition modérée",
    )
    assert nutri_status.weight_kg == 62.5
    assert nutri_status.weight_loss_percent == 8.0

    hepatic_status = PatientMDTOncologicForm.HepaticStatus(
        bilirubin_umol_l=18.0,
        child_pugh_score="A5",
        bclc_stage="Non applicable",
    )
    assert hepatic_status.bilirubin_umol_l == 18.0
    assert hepatic_status.child_pugh_score == "A5"

    # 3. Build multi-RCP longitudinal oncology metric series
    forms = [
        {
            "file": "onco_t0.pdf",
            "PatientAdministrative": {"date_rcp": "2026-01-15"},
            "PatientPerformanceStatus": {"performance_status": 1},
            "CancerDescription": {
                "type_of_cancer": "Adénocarcinome pancréatique",
                "tnm_status": "cT3N1M0",
                "target_lesion_size_mm": 36.0,
                "recist_response": "Bilan initial",
            },
            "TumorBiology": {
                "msi_state": False,
                "ca19_9": "420 U/mL",
                "ace": "6.5 ng/mL",
                "dpd_uracilemia": 9.2,
                "ras_braf_status": "KRAS G12D",
            },
            "SurgicalStatus": {
                "resectability_status": "Borderline",
                "surgery_done": False,
            },
            "NutritionalStatus": {
                "weight_kg": 58.0,
                "weight_loss_percent": 11.0,
            },
            "HepaticStatus": {
                "bilirubin_umol_l": 45.0,
                "child_pugh_score": "A6",
            },
            "ChemotherapyTreament": {
                "chemotherapy": True,
                "chemotherapy_list": [
                    {
                        "chemotherapy_name": "FOLFIRINOX néo-adjuvant",
                        "chemotherapy_start_date": "2026-01-20",
                        "chemotherapy_tolerance": "Good",
                    }
                ],
            },
        },
        {
            "file": "onco_m6.pdf",
            "PatientAdministrative": {"date_rcp": "2026-07-15"},
            "PatientPerformanceStatus": {"performance_status": 0},
            "CancerDescription": {
                "type_of_cancer": "Adénocarcinome pancréatique",
                "tnm_status": "ypT1N0M0",
                "target_lesion_size_mm": 18.0,
                "recist_response": "Réponse partielle (RP)",
            },
            "TumorBiology": {
                "msi_state": False,
                "ca19_9": "48 U/mL",
                "ace": "2.1 ng/mL",
                "dpd_uracilemia": 9.2,
                "ras_braf_status": "KRAS G12D",
            },
            "SurgicalStatus": {
                "resectability_status": "Resectable",
                "surgery_done": True,
                "resection_margin": "R0",
            },
            "NutritionalStatus": {
                "weight_kg": 63.5,
                "weight_loss_percent": 2.0,
            },
            "HepaticStatus": {
                "bilirubin_umol_l": 11.0,
                "child_pugh_score": "A5",
            },
            "ChemotherapyTreament": {
                "chemotherapy": True,
                "chemotherapy_list": [
                    {
                        "chemotherapy_name": "FOLFIRINOX adjuvant",
                        "chemotherapy_start_date": "2026-08-01",
                        "chemotherapy_tolerance": "Medium",
                    }
                ],
            },
        },
    ]

    series_list = build_patient_metric_series(forms, domain="oncology")
    by_key = {s.metric_key: s for s in series_list}

    assert "TumorBiology.ca19_9" in by_key
    assert by_key["TumorBiology.ca19_9"].points[0].numeric_value == 420.0
    assert by_key["TumorBiology.ca19_9"].points[1].numeric_value == 48.0
    assert by_key["TumorBiology.ca19_9"].points[1].delta_numeric == -372.0

    assert "CancerDescription.target_lesion_size_mm" in by_key
    assert (
        by_key["CancerDescription.target_lesion_size_mm"].points[1].delta_numeric
        == -18.0
    )

    assert "NutritionalStatus.weight_kg" in by_key
    assert by_key["NutritionalStatus.weight_kg"].points[1].delta_numeric == 5.5

    assert "HepaticStatus.bilirubin_umol_l" in by_key
    assert by_key["HepaticStatus.bilirubin_umol_l"].points[1].delta_numeric == -34.0

    assert "SurgicalStatus.resectability_status" in by_key
    assert "SurgicalStatus.resection_margin" in by_key

    # Chemotherapy fallback from ChemotherapyTreament.chemotherapy_list[0]
    assert "Chemotherapy.chemotherapy_name" in by_key
    assert (
        by_key["Chemotherapy.chemotherapy_name"].points[0].display_value
        == "FOLFIRINOX néo-adjuvant"
    )
    assert "Chemotherapy.chemotherapy_tolerance" in by_key
    assert (
        by_key["Chemotherapy.chemotherapy_tolerance"].points[1].display_value
        == "Medium"
    )
