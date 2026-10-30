import hashlib
import logging
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.application.agent.collaborate import collaborative_debate
from src.application.app_functions import to_naive
from src.application.config import AppConfig
from src.application.reader import DocumentReader
from src.application.use_cases.patient_record import PatientRecordService
from src.domain.patient import Patient
from src.domain.patient_mdt_form import (
    NonPatientMDTFormError,
    PatientMDTForm,
    get_domain_mdt_form_cls,
)
from src.domain.repositories import (
    DocumentCacheRepository,
    PatientMDTFormRepository,
    PatientRepository,
)
from src.domain.worker import JobType
from src.infrastructure.documents.mongodb import Mongodb
from src.infrastructure.documents.repositories import (
    InMemoryDocumentCacheRepository,
    InMemoryPatientMDTFormRepository,
    InMemoryPatientRepository,
    MongoDocumentCacheRepository,
    MongoPatientMDTFormRepository,
    MongoPatientRepository,
)


def _serialize_dates(data: Any) -> Any:
    """Recursively normalize all datetime objects into naive datetimes for persistence."""
    if isinstance(data, dict):
        return {k: _serialize_dates(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_serialize_dates(i) for i in data]
    if isinstance(data, datetime):
        return to_naive(data)
    return data


class PatientMDTFormExtractionService:
    """
    Application use-case service orchestrating AI extraction of `PatientMDTForm` sections,
    `PatientMDTFormCheck` validation, synchronization with the `Patient` aggregate,
    and submission into the priority processing queue.

    Replaces the legacy `PatientMDTForm(DocumentReader)` inheritance with clean composition
    between the pure `PatientMDTForm` entity, the technical `DocumentReader`, and domain repositories.
    """

    def __init__(
        self,
        config: AppConfig,
        filename: str | None = None,
        form_cls: type[PatientMDTForm] | None = None,
        reader: DocumentReader | None = None,
        patient_repo: PatientRepository | None = None,
        mdt_form_repo: PatientMDTFormRepository | None = None,
        cache_repo: DocumentCacheRepository | None = None,
        patient_record_service: PatientRecordService | None = None,
        db_client: Mongodb | None = None,
    ) -> None:
        self.config = config
        self.logger = (
            config.set_logger(__name__)
            if hasattr(config, "set_logger")
            else logging.getLogger(__name__)
        )
        self.filename = filename or ""
        domain_val = getattr(config, "domain", None)
        self.form_cls = form_cls or get_domain_mdt_form_cls(
            domain_val if isinstance(domain_val, str) else None
        )
        self._reader = reader
        self._owns_db_client = False
        self._db_client = db_client

        if mdt_form_repo is not None and (
            patient_record_service is not None or patient_repo is not None
        ):
            self.mdt_form_repo = mdt_form_repo
            self.cache_repo = cache_repo or InMemoryDocumentCacheRepository()
            self.patient_repo = patient_repo or (
                patient_record_service.patient_repo
                if patient_record_service is not None
                else InMemoryPatientRepository()
            )
            self.patient_record_service = (
                patient_record_service
                or PatientRecordService(
                    patient_repo=self.patient_repo,
                    mdt_form_repo=self.mdt_form_repo,
                    cache_repo=self.cache_repo,
                    mdt_form_storage_path=getattr(
                        getattr(config, "rcp", None), "path", None
                    ),
                    form_cls=self.form_cls,
                    config=config,
                )
            )
        elif getattr(getattr(config, "rcp", None), "display_type", None) == "mongodb":
            if self._db_client is None:
                self._db_client = Mongodb(config)
                self._owns_db_client = True
            self.mdt_form_repo = mdt_form_repo or MongoPatientMDTFormRepository(
                self._db_client
            )
            self.cache_repo = cache_repo or MongoDocumentCacheRepository(
                self._db_client
            )
            self.patient_repo = patient_repo or MongoPatientRepository(self._db_client)
            self.patient_record_service = (
                patient_record_service
                or PatientRecordService(
                    patient_repo=self.patient_repo,
                    mdt_form_repo=self.mdt_form_repo,
                    cache_repo=self.cache_repo,
                    mdt_form_storage_path=config.rcp.path,
                    form_cls=self.form_cls,
                    config=config,
                )
            )
        else:
            self.mdt_form_repo = mdt_form_repo or InMemoryPatientMDTFormRepository()
            self.cache_repo = cache_repo or InMemoryDocumentCacheRepository()
            self.patient_repo = patient_repo or InMemoryPatientRepository()
            self.patient_record_service = (
                patient_record_service
                or PatientRecordService(
                    patient_repo=self.patient_repo,
                    mdt_form_repo=self.mdt_form_repo,
                    cache_repo=self.cache_repo,
                    mdt_form_storage_path=getattr(
                        getattr(config, "rcp", None), "path", None
                    ),
                    form_cls=self.form_cls,
                    config=config,
                )
            )

        existing_raw = (
            self.mdt_form_repo.get_by_file(self.filename) if self.filename else None
        )
        if existing_raw:
            self.form = self.form_cls.from_persistence(existing_raw)
        else:
            self.form = self.form_cls(file=self.filename)

    def close(self) -> None:
        """Close the owned database client if one was created internally."""
        if self._owns_db_client and self._db_client is not None:
            self._db_client.close()
            self._db_client = None

    def get_reader(self, filename: str | None = None) -> DocumentReader:
        """Return or lazily initialize the indexed `DocumentReader`."""
        target_file = filename or self.filename
        if self._reader is None or (
            target_file and getattr(self._reader, "document", None) != target_file
        ):
            self._reader = DocumentReader(self.config, target_file)
            self._reader.read_document()
        return self._reader

    # ------------------------------------------------------------------
    # Section Extraction (Single-Agent, Multi-Agent, Collaborative Debate)
    # ------------------------------------------------------------------

    def extract_section(
        self,
        model_cls: type[BaseModel] | None = None,
        upsert: bool = False,
        callbacks: list | None = None,
        *,
        form: PatientMDTForm | None = None,
        reader: DocumentReader | None = None,
    ) -> Any:
        """
        Execute AI extraction for section `model_cls` on the `PatientMDTForm`,
        update `form` (or `self.form`), and optionally persist the result via `self.mdt_form_repo`.
        """
        if model_cls is None:
            raise ValueError("model_cls is required for extract_section")
        target_form = form if form is not None else self.form
        target_file = target_form.file or self.filename
        target_reader = (
            reader if reader is not None else self.get_reader(filename=target_file)
        )
        section_name = model_cls.__name__
        t_start = time.perf_counter()

        agents_list = getattr(model_cls, "agents", None) or []
        is_collaborative = bool(getattr(model_cls, "collaborative", False))
        question = getattr(model_cls, "question", None)

        if is_collaborative and len(agents_list) > 1:
            debate_res = collaborative_debate(
                agents_classes=agents_list,
                question=question,
                output_format=model_cls,
                config=self.config,
                mtd=target_reader,
                logger=self.logger,
                callbacks=callbacks,
            )
            serialized_value = _serialize_dates(
                debate_res.model_dump()
                if isinstance(debate_res, BaseModel)
                else debate_res
            )
        elif len(agents_list) > 1:
            multi_res: dict[str, Any] = {}
            for agent_cls in agents_list:
                agent = agent_cls(
                    config=self.config,
                    mtd=target_reader,
                    output_format=model_cls,
                )
                ans = agent.ask(question, callbacks=callbacks)
                ans_dict = (
                    ans.model_dump()
                    if isinstance(ans, BaseModel)
                    else (dict(ans) if isinstance(ans, dict) else {"value": ans})
                )
                if getattr(agent, "latest_thinking", ""):
                    ans_dict["reasoning_thinking"] = agent.latest_thinking
                key = getattr(agent, "agent_name", None) or agent_cls.__name__
                multi_res[key] = _serialize_dates(ans_dict)
            serialized_value = multi_res
        elif len(agents_list) == 1:
            agent_cls = agents_list[0]
            agent = agent_cls(
                config=self.config,
                mtd=target_reader,
                output_format=model_cls,
            )
            ans = agent.ask(question, callbacks=callbacks)
            ans_dict = (
                ans.model_dump()
                if isinstance(ans, BaseModel)
                else (dict(ans) if isinstance(ans, dict) else {"value": ans})
            )
            if getattr(agent, "latest_thinking", ""):
                ans_dict["reasoning_thinking"] = agent.latest_thinking
            serialized_value = _serialize_dates(ans_dict)
        else:
            raise ValueError(f"No agent defined on section model {section_name}")

        elapsed = round(time.perf_counter() - t_start, 2)
        target_form.set_section(section_name, serialized_value, elapsed_seconds=elapsed)

        if upsert and target_file:
            if section_name == "PatientAdministrative" and isinstance(
                serialized_value, dict
            ):
                patient, merged_admin = (
                    self.patient_record_service.synchronize_patient_from_admin(
                        filename=target_file,
                        admin_data=serialized_value,
                        target_patient_id=target_form.patient_id,
                    )
                )
                target_form.patient_id = patient.patient_id
                target_form.set_section(
                    section_name, merged_admin, elapsed_seconds=elapsed
                )
                serialized_value = merged_admin

            self.mdt_form_repo.upsert_fields(
                target_file,
                fields={
                    section_name: serialized_value,
                    "execution_times": dict(target_form.execution_times),
                    "date_refresh": target_form.date_refresh,
                },
                set_on_insert={
                    "file": target_file,
                    "ui_date": target_form.ui_date,
                },
            )

        return serialized_value

    # ------------------------------------------------------------------
    # PatientMDTForm Compliance Guardrail & Patient Identification (Wave 1)
    # ------------------------------------------------------------------

    def verify_is_patient_mdt_form(
        self,
        callbacks: list | None = None,
        *,
        form: PatientMDTForm | None = None,
        reader: DocumentReader | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Verify via `PatientMDTFormCheck` that the imported PDF is a valid `PatientMDTForm`.
        """
        target_form = form if form is not None else self.form
        raw_check = self.extract_section(
            form=target_form,
            reader=reader,
            model_cls=self.form_cls.PatientMDTFormCheck,
            upsert=False,
            callbacks=callbacks,
        )
        if isinstance(raw_check, BaseModel):
            check_dict = raw_check.model_dump()
        elif isinstance(raw_check, dict):
            check_dict = dict(raw_check)
        elif isinstance(target_form.sections.get("PatientMDTFormCheck"), dict):
            check_dict = dict(target_form.sections["PatientMDTFormCheck"])
        else:
            check_dict = {}

        is_valid = bool(check_dict.get("is_patient_mdt_form", True))
        target_form.set_section("PatientMDTFormCheck", check_dict)
        return is_valid, check_dict

    def reject_non_patient_mdt_form(
        self,
        check_result: dict[str, Any] | None = None,
        *,
        filename: str | None = None,
        reader: DocumentReader | None = None,
    ) -> None:
        """
        Clean up a rejected non-`PatientMDTForm` document (vector collection, cache, persistence, PDF)
        and raise `NonPatientMDTFormError`.
        """
        check_data = check_result or {}
        target_reader = reader if reader is not None else self._reader
        target_file = filename or (
            getattr(target_reader, "document", None) or self.filename
        )
        if target_reader is not None and hasattr(target_reader, "vecdb"):
            try:
                target_reader.vecdb.delete_collection()
            except Exception:
                pass

        if target_file:
            self.patient_record_service.delete_patient_mdt_form_document(
                target_file,
                delete_file=True,
                delete_queue_jobs=False,
                delete_vector_collection=(target_reader is None),
            )

        raise NonPatientMDTFormError(
            filename=target_file,
            detected_document_type=str(
                check_data.get("detected_document_type") or "Document non-RCP"
            ),
            justification=str(
                check_data.get("justification")
                or "Ce document ne correspond pas à une fiche de réunion de concertation pluridisciplinaire."
            ),
        )

    def process_patient_association(
        self,
        target_patient_id: str | None = None,
        run_admin_ai: bool = True,
        verify_patient_mdt_form: bool = False,
        callbacks: list | None = None,
        *,
        form: PatientMDTForm | None = None,
        reader: DocumentReader | None = None,
    ) -> Patient:
        """
        Execute Wave 1 (Patient Identification):
        1. Optionally verify that the document is a valid `PatientMDTForm`.
        2. Extract `PatientAdministrative` via the administrative agent.
        3. Synchronize the `Patient` aggregate and persist the `patient_id` <-> `filename` association.
        """
        target_form = form if form is not None else self.form
        target_file = target_form.file or self.filename

        if verify_patient_mdt_form:
            is_valid, check_dict = self.verify_is_patient_mdt_form(
                callbacks=callbacks,
                form=target_form,
                reader=reader,
            )
            if not is_valid:
                self.reject_non_patient_mdt_form(
                    check_dict,
                    filename=target_file,
                    reader=reader,
                )

        admin_raw = target_form.get_section("PatientAdministrative")
        if run_admin_ai and not admin_raw:
            admin_raw = self.extract_section(
                form=target_form,
                reader=reader,
                model_cls=self.form_cls.PatientAdministrative,
                upsert=False,
                callbacks=callbacks,
            )
            if admin_raw is None:
                admin_raw = target_form.get_section("PatientAdministrative")

        if isinstance(admin_raw, BaseModel):
            admin_dict = _serialize_dates(admin_raw.model_dump())
        elif isinstance(admin_raw, dict):
            admin_dict = _serialize_dates(dict(admin_raw))
        else:
            admin_dict = {}

        effective_target_pid = target_patient_id or target_form.patient_id
        patient, merged_admin = (
            self.patient_record_service.synchronize_patient_from_admin(
                filename=target_file,
                admin_data=admin_dict,
                target_patient_id=effective_target_pid,
            )
        )
        target_form.patient_id = patient.patient_id
        target_form.set_section("PatientAdministrative", merged_admin)

        upsert_payload: dict[str, Any] = {
            "patient_id": patient.patient_id,
            "PatientAdministrative": merged_admin,
            "execution_times": dict(target_form.execution_times),
            "date_refresh": target_form.date_refresh,
        }
        if "PatientMDTFormCheck" in target_form.sections:
            chk = target_form.sections["PatientMDTFormCheck"]
            upsert_payload["PatientMDTFormCheck"] = (
                chk.model_dump() if isinstance(chk, BaseModel) else chk
            )

        if target_file:
            self.mdt_form_repo.upsert_fields(
                target_file,
                fields=upsert_payload,
                set_on_insert={
                    "file": target_file,
                    "ui_date": target_form.ui_date,
                },
            )
        return patient

    def extract_all_sections(
        self,
        filename: str | None = None,
        replace: bool = True,
        unload_models: bool = True,
        callbacks: list | None = None,
    ) -> PatientMDTForm:
        """Execute full extraction across all sections of the `PatientMDTForm`."""
        if filename and filename != self.filename:
            self.filename = filename
            existing_raw = self.mdt_form_repo.get_by_file(filename)
            self.form = (
                self.form_cls.from_persistence(existing_raw)
                if existing_raw
                else self.form_cls(file=filename)
            )
            self._reader = None

        try:
            if replace or "PatientAdministrative" not in self.form.sections:
                self.process_patient_association(
                    target_patient_id=self.form.patient_id,
                    run_admin_ai=True,
                    verify_patient_mdt_form=False,
                    callbacks=callbacks,
                )

            for model_cls in self.form_cls.get_clinical_models():
                if not replace and model_cls.__name__ in self.form.sections:
                    continue
                self.extract_section(
                    model_cls=model_cls, upsert=True, callbacks=callbacks
                )

            return self.form
        finally:
            if unload_models:
                try:
                    from src.application.app_functions.llm import (
                        unload_active_models,
                    )

                    unload_active_models(self.config)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Orchestration Methods (Upload, Queue, Patient Record Readers)
    # ------------------------------------------------------------------

    def resolve_upload(
        self,
        file_bytes: bytes,
        original_filename: str,
    ) -> tuple[str, bool]:
        """
        Compute the SHA-256 digest of the uploaded PDF, generate a deterministic filename
        `<stem>_<hash10>.pdf`, and detect duplicates on disk or in `self.mdt_form_repo`.
        """
        file_hash = hashlib.sha256(file_bytes).hexdigest()[:10]
        base_name = os.path.basename(original_filename or "mdt_form.pdf")
        stem, ext = os.path.splitext(base_name)
        ext = ext if ext.lower() == ".pdf" else ".pdf"
        stem = re.sub(r"_[0-9a-f]{10}$", "", stem)
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_") or "mdt_form"
        resolved_filename = f"{safe_stem}_{file_hash}{ext}"

        target_path = Path(self.config.rcp.path) / resolved_filename
        if target_path.exists():
            return resolved_filename, True

        if self.mdt_form_repo.get_by_file(resolved_filename) is not None:
            return resolved_filename, True

        return resolved_filename, False

    def ingest_and_associate(
        self,
        filename: str,
        patient_id: str | None = None,
        run_admin_ai: bool = True,
        verify_patient_mdt_form: bool = True,
        unload_models: bool = True,
        callbacks: list | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Index a newly uploaded `PatientMDTForm` PDF, verify its compliance, and associate
        it with its `Patient` record.
        """
        self.filename = filename
        self.form = self.form_cls(file=filename)
        self._reader = None
        try:
            patient = self.process_patient_association(
                target_patient_id=patient_id,
                run_admin_ai=run_admin_ai,
                verify_patient_mdt_form=verify_patient_mdt_form,
                callbacks=callbacks,
            )
            return self.form.to_persistence(), patient.to_persistence()
        finally:
            if unload_models:
                try:
                    from src.application.app_functions.llm import (
                        unload_active_models,
                    )

                    unload_active_models(self.config)
                except Exception:
                    pass

    def enqueue_batch(
        self,
        files_payload: list[dict[str, Any]],
        run_full_ai: bool = True,
    ) -> dict[str, Any]:
        """Enqueue a batch of `PatientMDTForm` files into the priority processing queue."""
        from src.infrastructure.queue import QueueBroker

        clinical_count = max(1, len(self.form_cls.get_clinical_models()))
        batch_id = f"batch_{uuid.uuid4().hex[:10]}"

        broker = QueueBroker(self.config)
        try:
            results: list[dict[str, Any]] = []
            enqueued_count = 0
            already_queued_count = 0
            for item in files_payload:
                fname = item["filename"]
                target_pid = item.get("patient_id")
                res = broker.enqueue_import_file(
                    filename=fname,
                    target_patient_id=target_pid,
                    batch_id=batch_id,
                    include_clinical=run_full_ai,
                    total_clinical_models=clinical_count,
                )
                results.append(res)
                if res.get("already_queued"):
                    already_queued_count += 1
                else:
                    enqueued_count += 1
            return {
                "batch_id": batch_id,
                "enqueued_count": enqueued_count,
                "already_queued_count": already_queued_count,
                "results": results,
            }
        finally:
            broker.close()

    def enqueue_rerun(
        self,
        filename: str,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Enqueue a full `PatientMDTForm` rerun or a single-section rerun into the processing queue."""
        from src.infrastructure.queue import QueueBroker

        clinical_count = max(1, len(self.form_cls.get_clinical_models()))

        broker = QueueBroker(self.config)
        try:
            return broker.enqueue_rcp_rerun(
                filename=filename,
                model_name=model_name,
                total_clinical_models=clinical_count,
            )
        finally:
            broker.close()

    def get_active_jobs_state(self, filename: str) -> dict[str, Any]:
        """Return a summary of active queue jobs for a given `PatientMDTForm` `filename`."""
        from src.infrastructure.queue import QueueBroker

        broker = QueueBroker(self.config)
        try:
            active_jobs = broker.get_active_jobs_for_file(filename)
        finally:
            broker.close()

        has_full = any(
            j.get("job_type")
            in (JobType.WAVE1_ADMIN.value, JobType.WAVE2_CLINICAL.value)
            for j in active_jobs
        )
        active_models = [
            j["model_name"]
            for j in active_jobs
            if j.get("job_type") == JobType.SINGLE_MODEL.value and j.get("model_name")
        ]
        current_step = active_jobs[0].get("current_step") if active_jobs else None
        return {
            "has_any_job": len(active_jobs) > 0,
            "has_full_job": has_full,
            "active_models": active_models,
            "current_step": current_step,
            "jobs": active_jobs,
        }

    def build_patient_readers(
        self,
        filenames: list[str],
    ) -> list[DocumentReader]:
        """
        Build the list of `DocumentReader` instances for a `PatientRecord` multi-document chat,
        attaching `.sections` on each reader for the `get_patient_ai_history` tool.
        """
        docs_by_file: dict[str, dict[str, Any]] = {}
        for d in self.mdt_form_repo.list_by_files(filenames):
            if "file" in d:
                docs_by_file[d["file"]] = d

        readers: list[DocumentReader] = []
        for fname in filenames:
            reader = DocumentReader(self.config, fname)
            reader.read_document()
            reader.sections = docs_by_file.get(fname, {"file": fname})  # type: ignore[attr-defined]
            readers.append(reader)
        return readers
