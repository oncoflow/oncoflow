from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.application.use_cases import (
    PatientMDTFormExtractionService,
    PatientRecordService,
)
from src.domain.common.common_ressources import (
    Gender,
    PrimaryOrganEnum,
    RadiologicExamType,
    TreatmentToleranceEnum,
)
from src.domain.patient_mdt_form import PatientMDTOncologicForm, PatientMDTSmaForm
from src.domain.worker import RCPProcessingStatus
from src.infrastructure.documents.repositories import (
    InMemoryDocumentCacheRepository,
    InMemoryPatientMDTFormRepository,
    InMemoryPatientRepository,
)


def _make_record_service(
    tmp_path: Path | None = None,
    domain: str = "oncology",
) -> tuple[
    PatientRecordService,
    InMemoryPatientRepository,
    InMemoryPatientMDTFormRepository,
]:
    patient_repo = InMemoryPatientRepository()
    mdt_form_repo = InMemoryPatientMDTFormRepository()
    cache_repo = InMemoryDocumentCacheRepository()
    mock_conf = MagicMock()
    mock_conf.domain = domain
    mock_conf.rcp.path = str(tmp_path) if tmp_path else "/tmp"
    mock_conf.queue.enabled = False
    form_cls = PatientMDTSmaForm if domain == "sma" else PatientMDTOncologicForm
    service = PatientRecordService(
        patient_repo=patient_repo,
        mdt_form_repo=mdt_form_repo,
        cache_repo=cache_repo,
        form_cls=form_cls,
        config=mock_conf,
    )
    return service, patient_repo, mdt_form_repo


class TestManualSectionEditing:
    """Test manual editing of clinical, completeness, and priority sections on PatientMDTForm."""

    def test_update_clinical_sections_oncology_and_manual_flag(self, tmp_path: Path):
        service, patient_repo, mdt_form_repo = _make_record_service(tmp_path)
        filename = "fiche_rcp_pancreas.pdf"
        service.synchronize_patient_from_admin(
            filename=filename,
            admin_data={
                "first_name": "Jean",
                "last_name": "Dupont",
                "age": 66,
                "date_birth": datetime(1960, 1, 15),
                "date_rcp": datetime(2026, 3, 10),
                "gender": "Male",
            },
        )

        # 1. Update TumorLocation
        updated_doc = service.update_patient_mdt_form_section(
            filename=filename,
            section_name="TumorLocation",
            section_data={"tumor_location": PrimaryOrganEnum.pancreas.value},
            edited_by="dr_martin",
        )
        assert updated_doc["TumorLocation"]["tumor_location"] == "Pancreas"
        assert PatientMDTOncologicForm.is_section_manually_edited(
            updated_doc, "TumorLocation"
        )
        assert updated_doc["manual_edits"]["TumorLocation"]["edited_by"] == "dr_martin"

        # 2. Update RadiologicExams with dynamic table rows
        updated_doc = service.update_patient_mdt_form_section(
            filename=filename,
            section_name="RadiologicExams",
            section_data={
                "exams_list": [
                    {
                        "exam_name": "Scanner TAP injecté",
                        "exam_date": date(2026, 2, 20),
                        "exam_type": RadiologicExamType.CT.value,
                        "exam_result": "Masse céphalique pancréatique de 28 mm résécable.",
                    }
                ]
            },
        )
        assert len(updated_doc["RadiologicExams"]["exams_list"]) == 1
        assert (
            updated_doc["RadiologicExams"]["exams_list"][0]["exam_date"] == "2026-02-20"
        )
        assert PatientMDTOncologicForm.is_section_manually_edited(
            updated_doc, "RadiologicExams"
        )

        # 3. Update ChemotherapyTreament
        updated_doc = service.update_patient_mdt_form_section(
            filename=filename,
            section_name="ChemotherapyTreament",
            section_data={
                "chemotherapy": True,
                "chemotherapy_list": [
                    {
                        "chemotherapy_name": "FOLFIRINOX",
                        "chemotherapy_start_date": "2025-11-01",
                        "chemotherapy_end_date": "2026-01-15",
                        "chemotherapy_tolerance": TreatmentToleranceEnum.good.value,
                    }
                ],
            },
        )
        assert updated_doc["ChemotherapyTreament"]["chemotherapy"] is True
        assert (
            updated_doc["ChemotherapyTreament"]["chemotherapy_list"][0][
                "chemotherapy_name"
            ]
            == "FOLFIRINOX"
        )

        # 4. CareOrientationProposal and ExpertAnswer must NOT be manually editable
        assert (
            PatientMDTOncologicForm.is_section_manually_editable(
                "CareOrientationProposal"
            )
            is False
        )
        assert (
            PatientMDTOncologicForm.is_section_manually_editable("ExpertAnswer")
            is False
        )
        with pytest.raises(ValueError, match="cannot be manually modified"):
            service.update_patient_mdt_form_section(
                filename=filename,
                section_name="CareOrientationProposal",
                section_data={
                    "care_adaptation_suggested": True,
                    "suggested_priority": "urgent",
                    "proposed_care_type": "Chirurgie DPC d'emblée",
                    "clinical_rationale": "Validation collégiale RCP.",
                },
            )

        # 5. Update MTDCompleted and verify card metrics reflect manual completeness override
        updated_doc = service.update_patient_mdt_form_section(
            filename=filename,
            section_name="MTDCompleted",
            section_data={
                "mtd_complete": {
                    "is_mtd_complete": True,
                    "reflection": "Tous les examens requis (scanner, écho-endoscopie, CA 19-9) ont été vérifiés.",
                    "what_missing": [],
                    "references": [],
                }
            },
        )
        metrics = PatientMDTOncologicForm.extract_card_metrics(updated_doc)
        assert metrics["missing"] == []

    def test_modified_fields_trace_preserved_for_llm_as_a_judge(self, tmp_path: Path):
        service, _, mdt_form_repo = _make_record_service(tmp_path)
        filename = "judge_trace_test.pdf"
        service.synchronize_patient_from_admin(
            filename=filename,
            admin_data={
                "first_name": "Jean",
                "last_name": "Dupont",
                "age": 66,
                "date_birth": datetime(1960, 1, 15),
                "date_rcp": datetime(2026, 3, 10),
                "gender": "Male",
            },
        )
        # Simulate an initial AI extraction on TumorLocation (with reasoning_thinking)
        mdt_form_repo.upsert_fields(
            filename,
            {
                "TumorLocation": {
                    "tumor_location": PrimaryOrganEnum.stomach.value,
                    "reasoning_thinking": "Le texte mentionne une lésion gastrique antro-pylorique.",
                    "time_execution": 2.4,
                }
            },
        )

        # First manual edit by clinician: Stomach -> Colon
        doc_after_edit1 = service.update_patient_mdt_form_section(
            filename=filename,
            section_name="TumorLocation",
            section_data={"tumor_location": PrimaryOrganEnum.colon.value},
            edited_by="dr_dupuis",
        )
        trace1 = doc_after_edit1["manual_edits"]["TumorLocation"]
        assert trace1["is_manual"] is True
        assert trace1["ai_original"]["tumor_location"] == "Stomach"
        assert (
            trace1["ai_reasoning_thinking"]
            == "Le texte mentionne une lésion gastrique antro-pylorique."
        )
        assert trace1["modified_fields"] == {
            "tumor_location": {
                "ai_value": "Stomach",
                "human_value": "Colon",
            }
        }
        assert len(trace1["edit_history"]) == 1

        # Second manual edit by clinician: Colon -> Pancreas (ai_original must stay "Stomach"!)
        doc_after_edit2 = service.update_patient_mdt_form_section(
            filename=filename,
            section_name="TumorLocation",
            section_data={"tumor_location": PrimaryOrganEnum.pancreas.value},
            edited_by="dr_martin",
        )
        trace2 = doc_after_edit2["manual_edits"]["TumorLocation"]
        assert trace2["ai_original"]["tumor_location"] == "Stomach"
        assert trace2["modified_fields"] == {
            "tumor_location": {
                "ai_value": "Stomach",
                "human_value": "Pancreas",
            }
        }
        assert len(trace2["edit_history"]) == 2
        assert trace2["edit_history"][1]["previous_value"] == {
            "tumor_location": "Colon"
        }
        assert trace2["edit_history"][1]["new_value"] == {"tumor_location": "Pancreas"}

        # If the section is later re-extracted by AI, the judge trace is archived and never lost
        archived_map = PatientMDTOncologicForm.archive_manual_edit_before_ai_rerun(
            doc_after_edit2["manual_edits"], "TumorLocation"
        )
        assert archived_map["TumorLocation"]["is_manual"] is False
        assert len(archived_map["TumorLocation"]["archived_judge_traces"]) == 1
        archived_item = archived_map["TumorLocation"]["archived_judge_traces"][0]
        assert archived_item["ai_original"]["tumor_location"] == "Stomach"
        assert archived_item["human_value"]["tumor_location"] == "Pancreas"
        assert archived_item["modified_fields"] == {
            "tumor_location": {
                "ai_value": "Stomach",
                "human_value": "Pancreas",
            }
        }

    def test_update_sma_clinical_sections(self, tmp_path: Path):
        service, _, _ = _make_record_service(tmp_path, domain="sma")
        filename = "sma_bilan.pdf"
        service.synchronize_patient_from_admin(
            filename=filename,
            admin_data={
                "first_name": "Lucas",
                "last_name": "Petit",
                "age": 2,
                "date_birth": datetime(2024, 5, 10),
                "date_rcp": datetime(2026, 5, 10),
                "gender": "Male",
            },
        )
        updated_doc = service.update_patient_mdt_form_section(
            filename=filename,
            section_name="GeneticDiagnosis",
            section_data={
                "smn1_deletion_confirmed": True,
                "smn2_copy_count": 2,
                "other_genetic_variants": "Aucune",
            },
        )
        assert updated_doc["GeneticDiagnosis"]["smn2_copy_count"] == 2
        assert PatientMDTSmaForm.is_section_manually_edited(
            updated_doc, "GeneticDiagnosis"
        )


class TestAdministrativeRecoveryAndIdentityUpdate:
    """Test changing administrative information when AI fails or when correcting patient identity."""

    def test_recover_from_failed_ai_extraction_and_replace_fallback_patient(
        self, tmp_path: Path
    ):
        service, patient_repo, mdt_form_repo = _make_record_service(tmp_path)
        filename = "scan_mal_ocr_12345.pdf"

        # Simulate a failed Wave 1 extraction that created a fallback "Inconnu" patient
        fallback_patient, _ = service.synchronize_patient_from_admin(
            filename=filename,
            admin_data={},
        )
        assert fallback_patient.patient_id.startswith("patient_")
        assert fallback_patient.full_name == "Inconnu"
        mdt_form_repo.upsert_fields(
            filename,
            {
                "processing_status": RCPProcessingStatus.FAILED.value,
                "processing_error": "LLM timeout on PatientAdministrative",
            },
        )

        # User manually enters administrative info
        updated_patient, updated_doc = service.update_patient_administrative(
            filename=filename,
            admin_data={
                "first_name": "Sophie",
                "last_name": "Lambert",
                "born_name": "Moreau",
                "date_birth": "1975-08-22",
                "date_rcp": "2026-04-12",
                "gender": Gender.female.value,
            },
        )

        assert updated_patient.patient_id == "lambert_sophie_1975_08_22"
        assert updated_patient.full_name == "Sophie Lambert"
        assert updated_patient.born_name == "Moreau"
        assert updated_patient.files == [filename]

        # Old fallback patient must be automatically removed
        assert patient_repo.get_by_id(fallback_patient.patient_id) is None

        # Form document must be updated, marked COMPLETED, and carry calculated age (50)
        assert updated_doc["patient_id"] == "lambert_sophie_1975_08_22"
        assert updated_doc["processing_status"] == RCPProcessingStatus.COMPLETED.value
        assert updated_doc.get("processing_error") is None
        assert updated_doc["PatientAdministrative"]["age"] == 50
        assert PatientMDTOncologicForm.is_section_manually_edited(
            updated_doc, "PatientAdministrative"
        )

    def test_update_identity_across_multi_rcp_patient_preserves_each_form_date_rcp(
        self, tmp_path: Path
    ):
        service, patient_repo, mdt_form_repo = _make_record_service(tmp_path)
        file_1 = "rcp_2025.pdf"
        file_2 = "rcp_2026.pdf"

        # Initial patient with a typo in last_name ("Dupond" instead of "Dupont")
        p1, _ = service.synchronize_patient_from_admin(
            filename=file_1,
            admin_data={
                "first_name": "Marc",
                "last_name": "Dupond",
                "age": 60,
                "date_birth": datetime(1965, 3, 10),
                "date_rcp": datetime(2025, 3, 15),
                "gender": "Male",
            },
        )
        service.synchronize_patient_from_admin(
            filename=file_2,
            admin_data={
                "first_name": "Marc",
                "last_name": "Dupond",
                "age": 61,
                "date_birth": datetime(1965, 3, 10),
                "date_rcp": datetime(2026, 3, 20),
                "gender": "Male",
            },
        )
        assert p1.patient_id == "dupond_marc_1965_03_10"

        # Correct spelling on file_2 with apply_to_all_patient_forms=True
        new_patient, updated_doc_2 = service.update_patient_administrative(
            filename=file_2,
            admin_data={
                "first_name": "Marc",
                "last_name": "Dupont",
                "born_name": "Dupont",
                "date_birth": "1965-03-10",
                "date_rcp": "2026-03-25",
                "gender": "Male",
            },
            apply_to_all_patient_forms=True,
        )

        assert new_patient.patient_id == "dupont_marc_1965_03_10"
        assert set(new_patient.files) == {file_1, file_2}
        # Old misspelled patient_id must be cleaned up
        assert patient_repo.get_by_id("dupond_marc_1965_03_10") is None

        # Both forms must now point to dupont_marc_1965_03_10, while file_1 keeps its own date_rcp
        doc_1 = mdt_form_repo.get_by_file(file_1)
        assert doc_1 is not None
        assert doc_1["patient_id"] == "dupont_marc_1965_03_10"
        assert doc_1["PatientAdministrative"]["last_name"] == "Dupont"
        assert "2025-03-15" in str(doc_1["PatientAdministrative"]["date_rcp"])
        assert "2026-03-25" in str(updated_doc_2["PatientAdministrative"]["date_rcp"])


class TestLinkMDTFormToExistingPatient:
    """Test linking an MDT form to an existing PatientRecord and cleaning up temporary records."""

    def test_link_orphan_or_misidentified_form_to_existing_patient(
        self, tmp_path: Path
    ):
        service, patient_repo, mdt_form_repo = _make_record_service(tmp_path)

        # Existing patient Claire Martin with 1 RCP
        existing_patient, _ = service.synchronize_patient_from_admin(
            filename="claire_rcp1.pdf",
            admin_data={
                "first_name": "Claire",
                "last_name": "Martin",
                "born_name": "Bernard",
                "age": 63,
                "date_birth": datetime(1962, 7, 21),
                "date_rcp": datetime(2025, 6, 10),
                "gender": "Female",
            },
        )

        # Second PDF where AI failed and created a temporary "Inconnu" patient
        orphan_file = "claire_rcp2_scan.pdf"
        temp_patient, _ = service.synchronize_patient_from_admin(
            filename=orphan_file,
            admin_data={"date_rcp": datetime(2026, 7, 25)},
        )
        assert temp_patient.patient_id.startswith("patient_")
        mdt_form_repo.upsert_fields(
            orphan_file,
            {"processing_status": RCPProcessingStatus.FAILED.value},
        )

        # Link orphan_file to Claire Martin
        linked_patient, updated_form = service.link_mdt_form_to_patient(
            filename=orphan_file,
            target_patient_id=existing_patient.patient_id,
        )

        assert linked_patient.patient_id == "martin_claire_1962_07_21"
        assert linked_patient.files == ["claire_rcp1.pdf", orphan_file]

        # Temporary patient record must be deleted since it has no remaining files
        assert patient_repo.get_by_id(temp_patient.patient_id) is None

        # Form must have Claire Martin's civil identity, keep its own date_rcp (2026-07-25), and compute age 64
        assert updated_form["patient_id"] == "martin_claire_1962_07_21"
        assert updated_form["processing_status"] == RCPProcessingStatus.COMPLETED.value
        admin = updated_form["PatientAdministrative"]
        assert admin["first_name"] == "Claire"
        assert admin["last_name"] == "Martin"
        assert admin["born_name"] == "Bernard"
        assert admin["gender"] == "Female"
        assert "2026-07-25" in str(admin["date_rcp"])
        assert admin["age"] == 64


class TestManualEditProtectionDuringReruns:
    """Test that manually edited sections are preserved by default during global AI reruns."""

    def test_extract_all_sections_preserves_manually_edited_sections_by_default(
        self, tmp_path: Path
    ):
        service, patient_repo, mdt_form_repo = _make_record_service(tmp_path)
        filename = "rcp_protected.pdf"
        service.synchronize_patient_from_admin(
            filename=filename,
            admin_data={
                "first_name": "Paul",
                "last_name": "Durand",
                "age": 70,
                "date_birth": datetime(1956, 1, 1),
                "date_rcp": datetime(2026, 1, 10),
                "gender": "Male",
            },
        )
        # Clinician manually sets TumorLocation to Colon
        service.update_patient_mdt_form_section(
            filename=filename,
            section_name="TumorLocation",
            section_data={"tumor_location": PrimaryOrganEnum.colon.value},
            edited_by="clinician",
        )

        extraction_service = PatientMDTFormExtractionService(
            config=service.config,
            filename=filename,
            patient_repo=patient_repo,
            mdt_form_repo=mdt_form_repo,
            patient_record_service=service,
        )

        # Spy on extract_section to see which models get re-extracted
        called_models: list[str] = []

        def _fake_extract(
            model_cls=None,
            upsert=False,
            callbacks=None,
            *,
            form=None,
            reader=None,
            clear_manual_flag=False,
        ):
            called_models.append(model_cls.__name__)
            return {}

        extraction_service.extract_section = MagicMock(side_effect=_fake_extract)  # type: ignore[method-assign]
        extraction_service.process_patient_association = MagicMock()  # type: ignore[method-assign]

        # Global rerun with preserve_manual_edits=True (default) must skip TumorLocation
        extraction_service.extract_all_sections(
            filename=filename,
            replace=True,
            preserve_manual_edits=True,
            unload_models=False,
        )
        assert "TumorLocation" not in called_models
        assert "PatientPerformanceStatus" in called_models
