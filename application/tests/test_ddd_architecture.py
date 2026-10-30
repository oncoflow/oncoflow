import ast
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.application.use_cases import (
    PatientMDTFormExtractionService,
    PatientMDTFormQueueJobExecutor,
    PatientRecordService,
)
from src.domain.bug_report import BugCategory, BugReport, BugSeverity
from src.domain.common.common_ressources import Gender
from src.domain.patient import Patient, PatientIdentity
from src.domain.patient_mdt_form import (
    NonPatientMDTFormError,
    PatientMDTOncologicForm,
    get_domain_mdt_form_cls,
)
from src.domain.repositories import (
    BugReportRepository,
    DocumentCacheRepository,
    PatientMDTFormRepository,
    PatientRepository,
    QueueJobExecutor,
)
from src.domain.worker import RCPProcessingStatus
from src.infrastructure.documents.repositories import (
    InMemoryBugReportRepository,
    InMemoryDocumentCacheRepository,
    InMemoryPatientMDTFormRepository,
    InMemoryPatientRepository,
)


class TestDDDArchitecturalBoundaries:
    """Verify strict DDD dependency rules and Ubiquitous Language via AST analysis."""

    def test_domain_has_zero_infrastructure_or_io_dependencies(self):
        domain_root = Path(__file__).resolve().parent.parent / "src" / "domain"
        forbidden_prefixes = (
            "src.infrastructure",
            "src.ui",
            "src.routers",
            "src.application.reader",
            "pymongo",
            "httpx",
            "streamlit",
            "fastapi",
        )
        violations: list[str] = []

        for py_file in domain_root.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(forbidden_prefixes):
                            violations.append(f"{py_file.name}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith(forbidden_prefixes):
                        violations.append(f"{py_file.name}: from {node.module}")
                elif isinstance(node, ast.Call):
                    if (
                        isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "os"
                        and node.func.attr in ("remove", "unlink", "makedirs")
                    ):
                        violations.append(
                            f"{py_file.name}: forbidden I/O call os.{node.func.attr}"
                        )

        assert violations == [], f"DDD boundary violations in src/domain/: {violations}"

    def test_ubiquitous_language_patient_mdt_form_and_patient_record_in_core_layers(
        self,
    ):
        """
        Ensure that `src/domain/`, `src/infrastructure/documents/repositories.py`,
        and `src/application/use_cases/` use `PatientMDTForm` and `PatientRecord`
        instead of French `rcp_form` or `dossier` in class and method names.
        """
        src_root = Path(__file__).resolve().parent.parent / "src"
        checked_files = (
            list((src_root / "domain").rglob("*.py"))
            + list((src_root / "application" / "use_cases").rglob("*.py"))
            + [src_root / "infrastructure" / "documents" / "repositories.py"]
        )
        violations: list[str] = []
        for py_file in checked_files:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    lower_name = node.name.lower()
                    if "dossier" in lower_name:
                        violations.append(
                            f"{py_file.name}: symbol '{node.name}' contains French 'dossier' instead of 'patient_record'"
                        )
                    if "rcp_form" in lower_name or "rcpextraction" in lower_name:
                        violations.append(
                            f"{py_file.name}: symbol '{node.name}' uses 'rcp' instead of 'patient_mdt_form'"
                        )
        assert violations == [], f"Ubiquitous language violations: {violations}"

    def test_patient_mdt_form_is_pure_entity_not_document_reader(self):
        from src.application.reader import DocumentReader

        form_cls = get_domain_mdt_form_cls("oncology")
        assert not issubclass(form_cls, DocumentReader)

        # Instantiating a domain form must perform zero disk/DB/vector I/O
        form = form_cls(file="pure_in_memory.pdf")
        assert form.file == "pure_in_memory.pdf"
        assert form.sections == {}
        assert not hasattr(form, "mtd_datas")

    def test_expert_agent_does_not_mutate_class_system_prompt(self):
        from src.domain.oncology.agents import Agents as OncoAgents

        assert OncoAgents.Expert_model.system_prompt == ""
        prompt = OncoAgents.Pancreas_expert_agent.get_system_prompt()
        assert "pancreas diseases" in prompt
        assert OncoAgents.Expert_model.system_prompt == ""

    def test_repositories_and_executor_satisfy_domain_protocols(self):
        assert isinstance(InMemoryPatientRepository(), PatientRepository)
        assert isinstance(InMemoryPatientMDTFormRepository(), PatientMDTFormRepository)
        assert isinstance(InMemoryDocumentCacheRepository(), DocumentCacheRepository)
        assert isinstance(InMemoryBugReportRepository(), BugReportRepository)
        assert isinstance(PatientMDTFormQueueJobExecutor(), QueueJobExecutor)


class TestPureDomainEntitiesAndValueObjects:
    """Test pure domain entities and value objects in memory."""

    def test_patient_identity_value_object_immutability_and_id_generation(self):
        identity = PatientIdentity(
            first_name="Jean-Pierre",
            last_name="D'Hérémont",
            born_name="Dupuis",
            date_birth=datetime(1958, 3, 14),
            gender=Gender.male,
        )
        assert identity.full_name == "Jean-Pierre D'Hérémont"
        assert identity.name_key == "d_heremont_jean_pierre"
        assert identity.build_patient_id() == "d_heremont_jean_pierre_1958_03_14"
        assert "14-03-1958" in identity.display_label

        with pytest.raises(Exception):
            identity.first_name = "Autre"  # type: ignore[misc]

    def test_patient_aggregate_file_attachment_and_admin_override(self):
        admin = PatientMDTOncologicForm.PatientAdministrative(
            first_name="Claire",
            last_name="Martin",
            born_name="Bernard",
            age=64,
            date_birth=datetime(1962, 7, 21),
            date_rcp=datetime(2026, 2, 10),
            gender=Gender.female,
        )
        patient = Patient.from_administrative(admin, filename="rcp_1.pdf")
        assert patient.patient_id == "martin_claire_1962_07_21"
        assert patient.files == ["rcp_1.pdf"]

        assert patient.attach_file("rcp_2.pdf") is True
        assert patient.attach_file("rcp_2.pdf") is False
        assert patient.files == ["rcp_1.pdf", "rcp_2.pdf"]

        # Applying patient identity to an OCR-extracted admin dict keeps date_rcp and age
        ocr_admin = {
            "first_name": "Clair_Typo",
            "last_name": "Martn",
            "age": 65,
            "date_rcp": datetime(2026, 8, 15),
        }
        merged = patient.apply_to_administrative(ocr_admin)
        assert merged["first_name"] == "Claire"
        assert merged["last_name"] == "Martin"
        assert merged["date_birth"] == "1962-07-21"
        assert merged["age"] == 65
        assert merged["date_rcp"] == datetime(2026, 8, 15)

        assert patient.detach_file("rcp_1.pdf") is True
        assert patient.files == ["rcp_2.pdf"]

    def test_patient_mdt_form_sections_hydration_and_metrics(self):
        raw_doc = {
            "file": "rcp_2026.pdf",
            "patient_id": "dupont_jean_1960_01_01",
            "ui_date": datetime(2026, 3, 20),
            "processing_status": RCPProcessingStatus.COMPLETED.value,
            "PatientAdministrative": {
                "first_name": "Jean",
                "last_name": "Dupont",
                "age": 66,
                "date_birth": datetime(1960, 1, 1),
                "date_rcp": datetime(2026, 3, 18),
                "gender": "Male",
            },
            "TumorLocation": {"tumor_location": "Pancreas"},
            "ExpertAnswer": {
                "pancreas expert": {
                    "expert_relevant": True,
                    "patient_priority": "Patient must be treated urgently",
                    "why_relevant": "Urgence pancréatique",
                    "sources_relevant": [],
                    "suggestions": [],
                }
            },
        }
        form = PatientMDTOncologicForm.from_persistence(raw_doc)
        assert form.file == "rcp_2026.pdf"
        assert form.patient_id == "dupont_jean_1960_01_01"
        assert "TumorLocation" in form.sections
        assert form.sections["TumorLocation"].tumor_location.value == "Pancreas"

        metrics = PatientMDTOncologicForm.extract_card_metrics(form)
        assert metrics["urgency"] == "Urgent"
        assert metrics["urgency_score"] == 2
        assert metrics["experts"] == ["pancreas expert"]
        assert metrics["patient"] == "Jean Dupont"

    def test_cross_domain_care_orientation_proposal_collaborative_schema_and_metrics(
        self,
    ):
        from src.domain.common.common_ressources import PatientPriority
        from src.domain.common.patient_mdt_common_form import (
            PatientMDTForm as BasePatientMDTForm,
        )
        from src.domain.sma.patient_mdt_sma_form import PatientMDTSmaForm

        # Base cross-domain definition on PatientMDTForm
        assert hasattr(BasePatientMDTForm, "CareOrientationProposal")
        assert hasattr(PatientMDTOncologicForm, "CareOrientationProposal")
        assert hasattr(PatientMDTSmaForm, "CareOrientationProposal")

        onco_proposal_cls = PatientMDTOncologicForm.CareOrientationProposal
        sma_proposal_cls = PatientMDTSmaForm.CareOrientationProposal

        assert issubclass(onco_proposal_cls, BasePatientMDTForm.CareOrientationProposal)
        assert issubclass(sma_proposal_cls, BasePatientMDTForm.CareOrientationProposal)
        assert getattr(onco_proposal_cls, "collaborative", False) is True
        assert getattr(sma_proposal_cls, "collaborative", False) is True
        assert len(onco_proposal_cls.agents) == 3
        assert len(sma_proposal_cls.agents) == 5
        assert "Time is Motoneuron" in sma_proposal_cls.question

        proposal = sma_proposal_cls(
            care_adaptation_suggested=True,
            suggested_priority=PatientPriority.urgent,
            proposed_care_type="Initiation of SMN-targeted therapy and NIV",
            clinical_rationale="Infant SMA Type 1 with 2 SMN2 copies requires immediate therapy discussion.",
        )
        assert proposal.care_adaptation_suggested is True
        assert proposal.suggested_priority == PatientPriority.urgent

        raw_doc = {
            "file": "sma_patient_2026.pdf",
            "patient_id": "petit_lucas_2025_11_02",
            "processing_status": RCPProcessingStatus.COMPLETED.value,
            "PatientAdministrative": {
                "first_name": "Lucas",
                "last_name": "Petit",
                "age": 1,
                "date_birth": datetime(2025, 11, 2),
                "date_rcp": datetime(2026, 4, 10),
                "gender": "Male",
            },
            "CareOrientationProposal": proposal.model_dump(mode="json"),
        }
        sma_form = PatientMDTSmaForm.from_persistence(raw_doc)
        assert "CareOrientationProposal" in sma_form.sections
        assert (
            sma_form.sections["CareOrientationProposal"].care_adaptation_suggested
            is True
        )

        metrics = PatientMDTSmaForm.extract_card_metrics(sma_form)
        assert metrics["care_adaptation_suggested"] is True
        assert metrics["intervention_required"] is True
        assert (
            metrics["proposed_care_type"]
            == "Initiation of SMN-targeted therapy and NIV"
        )
        assert (
            metrics["intervention_type"] == "Initiation of SMN-targeted therapy and NIV"
        )
        assert (
            PatientMDTSmaForm.select_latest_analyzed([raw_doc])["file"]
            == "sma_patient_2026.pdf"
        )


class TestRepositoriesAndApplicationUseCases:
    """Test Repositories and Application Use Cases in isolation (no MongoDB daemon)."""

    def test_patient_record_service_sync_cards_resolve_and_delete(self, tmp_path: Path):
        patient_repo = InMemoryPatientRepository()
        mdt_form_repo = InMemoryPatientMDTFormRepository()
        cache_repo = InMemoryDocumentCacheRepository()

        mock_conf = MagicMock()
        mock_conf.rcp.path = str(tmp_path)
        mock_conf.queue.enabled = False

        service = PatientRecordService(
            patient_repo=patient_repo,
            mdt_form_repo=mdt_form_repo,
            cache_repo=cache_repo,
            config=mock_conf,
        )

        # Create 2 dummy PDF files on disk
        file_old = "rcp_old.pdf"
        file_new = "rcp_new.pdf"
        (tmp_path / file_old).write_bytes(b"%PDF-1.4 old")
        (tmp_path / file_new).write_bytes(b"%PDF-1.4 new")

        # Sync first PatientMDTForm
        p1, _ = service.synchronize_patient_from_admin(
            filename=file_old,
            admin_data={
                "first_name": "Marion",
                "last_name": "Roussel",
                "age": 55,
                "date_birth": datetime(1970, 5, 12),
                "date_rcp": datetime(2025, 1, 10),
                "gender": "Female",
            },
        )
        assert p1 is not None
        assert p1.patient_id == "roussel_marion_1970_05_12"

        # Sync second PatientMDTForm for the same patient with clinical urgency
        p2, _ = service.synchronize_patient_from_admin(
            filename=file_new,
            admin_data={
                "first_name": "Marion",
                "last_name": "Roussel",
                "age": 56,
                "date_birth": datetime(1970, 5, 12),
                "date_rcp": datetime(2026, 2, 15),
                "gender": "Female",
            },
        )
        mdt_form_repo.update_fields(
            file_new,
            {
                "ExpertAnswer": {
                    "pancreas expert": {
                        "expert_relevant": True,
                        "patient_priority": "Patient must be treated urgently",
                    }
                },
                "processing_status": RCPProcessingStatus.COMPLETED.value,
            },
        )
        assert p2 is not None
        assert p2.patient_id == p1.patient_id
        assert p2.files == [file_old, file_new]

        # Build patient cards -> 1 card for Marion Roussel, pointing to rcp_new.pdf
        p_cards = service.list_patient_cards()
        assert len(p_cards) == 1
        assert p_cards[0]["patient_id"] == "roussel_marion_1970_05_12"
        assert p_cards[0]["file"] == file_new
        assert p_cards[0]["rcp_count"] == 2
        assert p_cards[0]["urgency"] == "Urgent"

        # Resolve PatientRecord by patient_id
        resolved_patient, rcps, selected_file = service.resolve_patient_record(
            patient_id_param="roussel_marion_1970_05_12"
        )
        assert resolved_patient is not None
        assert len(rcps) == 2
        assert selected_file == file_new

        # Delete single PatientMDTForm document -> patient keeps remaining file
        service.delete_patient_mdt_form_document(file_old, delete_file=True)
        assert not (tmp_path / file_old).exists()
        updated_p = patient_repo.get_by_id("roussel_marion_1970_05_12")
        assert updated_p is not None
        assert updated_p.files == [file_new]

        # Delete entire PatientRecord -> removes remaining file, forms, and patient
        assert service.delete_patient_record("roussel_marion_1970_05_12") is True
        assert not (tmp_path / file_new).exists()
        assert patient_repo.get_by_id("roussel_marion_1970_05_12") is None
        assert mdt_form_repo.get_by_filename(file_new) is None

    def test_patient_mdt_form_extraction_service_rejects_non_mdt_form_and_cleans_up(
        self, tmp_path: Path
    ):
        patient_repo = InMemoryPatientRepository()
        mdt_form_repo = InMemoryPatientMDTFormRepository()
        cache_repo = InMemoryDocumentCacheRepository()

        mock_conf = MagicMock()
        mock_conf.domain = "oncology"
        mock_conf.rcp.path = str(tmp_path)
        mock_conf.queue.enabled = False

        record_service = PatientRecordService(
            patient_repo=patient_repo,
            mdt_form_repo=mdt_form_repo,
            cache_repo=cache_repo,
            config=mock_conf,
        )

        pdf_file = "facture_hopital.pdf"
        (tmp_path / pdf_file).write_bytes(b"%PDF-1.4 Facture")
        mdt_form_repo.update_fields(pdf_file, {"file": pdf_file})

        mock_reader = MagicMock()
        mock_reader.document = pdf_file
        mock_reader.document_path = str(tmp_path / pdf_file)

        extraction_service = PatientMDTFormExtractionService(
            config=mock_conf,
            patient_repo=patient_repo,
            mdt_form_repo=mdt_form_repo,
            cache_repo=cache_repo,
            patient_record_service=record_service,
        )

        form = PatientMDTOncologicForm(file=pdf_file)

        # Simulate AI returning is_patient_mdt_form=False
        def _fake_extract_section(
            form, reader, model_cls, upsert=False, callbacks=None
        ):
            check = PatientMDTOncologicForm.PatientMDTFormCheck(
                is_patient_mdt_form=False,
                detected_document_type="Facture",
                justification="Document comptable.",
            )
            form.sections["PatientMDTFormCheck"] = check.model_dump()
            return check

        extraction_service.extract_section = MagicMock(  # type: ignore[method-assign]
            side_effect=_fake_extract_section
        )

        with pytest.raises(NonPatientMDTFormError) as exc_info:
            extraction_service.process_patient_association(
                form=form,
                reader=mock_reader,
                verify_patient_mdt_form=True,
            )

        assert "Facture" in str(exc_info.value)
        assert not (tmp_path / pdf_file).exists()
        assert mdt_form_repo.get_by_filename(pdf_file) is None
        mock_reader.vecdb.delete_collection.assert_called_once()

    def test_bug_report_repository_crud(self):
        repo = InMemoryBugReportRepository()
        b1 = BugReport(
            bug_id="bug_1",
            title="Bug 1",
            description="Desc 1",
            category=BugCategory.ui,
            severity=BugSeverity.low,
            created_at=datetime(2026, 1, 1),
        )
        b2 = BugReport(
            bug_id="bug_2",
            title="Bug 2",
            description="Desc 2",
            category=BugCategory.ai_extraction,
            severity=BugSeverity.critical,
            created_at=datetime(2026, 6, 1),
        )
        repo.create(b1)
        repo.create(b2)

        all_bugs = repo.list_all()
        assert [b["bug_id"] for b in all_bugs] == ["bug_2", "bug_1"]

        updated = repo.update("bug_1", {"status": "resolved"})
        assert updated is not None
        assert updated["status"] == "resolved"

        assert repo.delete("bug_1") is True
        assert [b["bug_id"] for b in repo.list_all()] == ["bug_2"]
