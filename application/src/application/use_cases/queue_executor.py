from datetime import datetime
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from src.application.app_functions.llm import unload_active_models
from src.application.config import AppConfig
from src.application.reader import DocumentReader
from src.application.use_cases.patient_mdt_form_extraction import (
    PatientMDTFormExtractionService,
)
from src.domain.patient_mdt_form import get_domain_mdt_form_cls
from src.domain.worker import JobStatus, RCPProcessingStatus
from src.infrastructure.documents.mongodb import Mongodb
from src.infrastructure.documents.repositories import MongoPatientMDTFormRepository


class QueueThinkingCallbackHandler(BaseCallbackHandler):
    """
    Pure-Python LangChain callback handler that captures live AI reasoning tokens
    (`reasoning_content` or `<think>...</think>`) during queue task execution and
    streams them into `InMemoryQueueManager`.
    """

    def __init__(
        self,
        queue_manager: Any,
        job_id: str,
        run_id: str | None = None,
        lease_id: str | None = None,
        section_name: str | None = None,
    ) -> None:
        super().__init__()
        self.queue_manager = queue_manager
        self.job_id = job_id
        self.run_id = run_id
        self.lease_id = lease_id
        self.section_name = section_name
        self.active_agent: str | None = section_name
        self._in_think: bool = False
        self._raw_buffer: str = ""

    def _emit_thinking(self, text: str, reset: bool = False) -> None:
        if not text and not reset:
            return
        self.queue_manager.append_job_thinking(
            self.job_id,
            text,
            agent_name=self.active_agent,
            reset=reset,
            run_id=self.run_id,
            lease_id=self.lease_id,
        )

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        """Reset reasoning tag state and update active agent label when a new LLM call starts."""
        tags = kwargs.get("tags") or []
        new_agent = tags[0] if tags else (self.section_name or self.active_agent)
        self._in_think = False
        self._raw_buffer = ""
        if new_agent and new_agent != self.active_agent:
            self.active_agent = str(new_agent)
            self._emit_thinking("", reset=True)
        elif new_agent:
            self.active_agent = str(new_agent)

    @staticmethod
    def _partial_close_tag_len(buf: str) -> int:
        close_tag = "</think>"
        max_k = min(len(buf), len(close_tag) - 1)
        for k in range(max_k, 0, -1):
            if buf.endswith(close_tag[:k]):
                return k
        return 0

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Extract live reasoning tokens from `reasoning_content` or `<think>` tags."""
        chunk = kwargs.get("chunk")
        reasoning_token = ""
        if chunk is not None and hasattr(chunk, "message"):
            msg = chunk.message
            if hasattr(msg, "reasoning_content") and msg.reasoning_content:
                reasoning_token = str(msg.reasoning_content)
            elif hasattr(msg, "additional_kwargs") and isinstance(
                msg.additional_kwargs, dict
            ):
                rc = msg.additional_kwargs.get("reasoning_content")
                if rc:
                    reasoning_token = str(rc)

        if reasoning_token:
            self._emit_thinking(reasoning_token)
            if not token:
                return

        if not token:
            return

        self._raw_buffer += token
        open_tag = "<think>"
        close_tag = "</think>"

        while self._raw_buffer:
            if not self._in_think:
                idx = self._raw_buffer.find(open_tag)
                if idx != -1:
                    self._raw_buffer = self._raw_buffer[idx + len(open_tag) :]
                    self._in_think = True
                else:
                    # Keep a small suffix in case `<think>` is split across tokens
                    keep = len(open_tag) - 1
                    if len(self._raw_buffer) > keep:
                        self._raw_buffer = self._raw_buffer[-keep:]
                    break
            else:
                idx = self._raw_buffer.find(close_tag)
                if idx != -1:
                    to_emit = self._raw_buffer[:idx]
                    if to_emit:
                        self._emit_thinking(to_emit)
                    self._raw_buffer = self._raw_buffer[idx + len(close_tag) :]
                    self._in_think = False
                else:
                    partial_len = self._partial_close_tag_len(self._raw_buffer)
                    emit_upto = len(self._raw_buffer) - partial_len
                    if emit_upto > 0:
                        self._emit_thinking(self._raw_buffer[:emit_upto])
                        self._raw_buffer = self._raw_buffer[emit_upto:]
                    break


class PatientMDTFormQueueJobExecutor:
    """
    Application use-case adapter implementing `QueueJobExecutor` for `InMemoryQueueManager`.
    Separates technical queue scheduling/leases from `PatientMDTForm` domain extraction logic.
    """

    def __init__(self, base_config: AppConfig | None = None) -> None:
        self.base_config = base_config or AppConfig()
        self.logger = self.base_config.set_logger("oncoflow.queue.executor")

    def _resolve_domain_config(self, domain: str | None = None) -> AppConfig:
        norm_domain = (domain or self.base_config.domain or "oncology").strip().lower()
        return self.base_config.for_domain(norm_domain)

    def on_job_enqueued(
        self,
        domain: str,
        filename: str,
        status: RCPProcessingStatus | str,
        extra_fields: dict[str, Any] | None = None,
    ) -> None:
        """Persist the initial or updated queue processing status on the `PatientMDTForm` record."""
        domain_conf = self._resolve_domain_config(domain)
        if domain_conf.rcp.display_type != "mongodb":
            return

        status_val = (
            status.value if isinstance(status, RCPProcessingStatus) else str(status)
        )
        now = datetime.now()
        fields: dict[str, Any] = {
            "processing_status": status_val,
            "processing_updated_at": now,
        }
        if extra_fields:
            fields.update(extra_fields)

        db_client = Mongodb(domain_conf)
        try:
            repo = MongoPatientMDTFormRepository(db_client)
            repo.upsert_fields(
                filename,
                fields=fields,
                set_on_insert={"file": filename, "date_refresh": now},
            )
        finally:
            db_client.close()

    def on_job_failed(self, domain: str, filename: str, error_message: str) -> None:
        """Mark the `PatientMDTForm` record as `FAILED` with the associated error message."""
        self.on_job_enqueued(
            domain=domain,
            filename=filename,
            status=RCPProcessingStatus.FAILED,
            extra_fields={"processing_error": error_message},
        )

    def stabilize_status(self, domain: str, filename: str) -> None:
        """
        Stabilize the `processing_status` of a `PatientMDTForm` record after its queue jobs
        are cancelled or purged (`COMPLETED` if administrative data exists, otherwise `FAILED`).
        """
        domain_conf = self._resolve_domain_config(domain)
        if domain_conf.rcp.display_type != "mongodb":
            return

        db_client = Mongodb(domain_conf)
        try:
            repo = MongoPatientMDTFormRepository(db_client)
            doc = repo.get_by_file(filename)
            if not doc:
                return
            has_admin = bool(doc.get("PatientAdministrative"))
            target_status = (
                RCPProcessingStatus.COMPLETED.value
                if has_admin
                else RCPProcessingStatus.FAILED.value
            )
            repo.upsert_fields(
                filename,
                fields={
                    "processing_status": target_status,
                    "processing_updated_at": datetime.now(),
                },
            )
        finally:
            db_client.close()

    def has_administrative_data(self, domain: str, filename: str) -> bool:
        """Return True if the `PatientMDTForm` record already has `PatientAdministrative` data."""
        domain_conf = self._resolve_domain_config(domain)
        if domain_conf.rcp.display_type != "mongodb":
            return False

        db_client = Mongodb(domain_conf)
        try:
            repo = MongoPatientMDTFormRepository(db_client)
            doc = repo.get_by_file(filename)
            return bool(doc and doc.get("PatientAdministrative"))
        finally:
            db_client.close()

    def execute_wave1_admin(
        self, job: dict[str, Any], lease_id: str, queue_manager: Any
    ) -> str | None:
        """Execute Wave 1 (`PatientMDTFormCheck` verification and `Patient` identification)."""
        job_id = job["job_id"]
        domain = job["domain"]
        filename = job["filename"]
        target_patient_id = job.get("target_patient_id")
        domain_conf = self._resolve_domain_config(domain)

        self.on_job_enqueued(domain, filename, RCPProcessingStatus.PROCESSING_ADMIN)
        queue_manager.update_job_progress(
            job_id=job_id,
            current_step="Vérification de la fiche RCP et identification du patient",
            progress_pct=20.0,
        )
        queue_manager.refresh_gpu_lease(lease_id, job_id=job_id)

        reader = DocumentReader(domain_conf, filename)
        reader.read_document()
        service = PatientMDTFormExtractionService(
            config=domain_conf, filename=filename, reader=reader
        )
        thinking_cb = QueueThinkingCallbackHandler(
            queue_manager=queue_manager,
            job_id=job_id,
            run_id=job.get("run_id"),
            lease_id=lease_id,
            section_name="PatientAdministrative",
        )
        try:
            patient = service.process_patient_association(
                target_patient_id=target_patient_id,
                run_admin_ai=True,
                verify_patient_mdt_form=True,
                callbacks=[thinking_cb],
                form=service.form,
                reader=reader,
            )
            resolved_pid = patient.patient_id if patient else target_patient_id

            with queue_manager._lock:
                has_wave2 = any(
                    j.get("depends_on_job_id") == job_id
                    and j["status"] == JobStatus.PENDING.value
                    for j in queue_manager._jobs.values()
                )
            next_status = (
                RCPProcessingStatus.PENDING_CLINICAL
                if has_wave2
                else RCPProcessingStatus.COMPLETED
            )
            self.on_job_enqueued(
                domain,
                filename,
                next_status,
                extra_fields=({"patient_id": resolved_pid} if resolved_pid else None),
            )
            return resolved_pid
        finally:
            service.close()

    def execute_wave2_clinical(
        self, job: dict[str, Any], lease_id: str, queue_manager: Any
    ) -> None:
        """Execute Wave 2 (extraction of factual single-agent clinical sections on the `PatientMDTForm`)."""
        job_id = job["job_id"]
        domain = job["domain"]
        filename = job["filename"]
        domain_conf = self._resolve_domain_config(domain)

        self.on_job_enqueued(domain, filename, RCPProcessingStatus.PROCESSING_CLINICAL)

        reader = DocumentReader(domain_conf, filename)
        reader.read_document()
        service = PatientMDTFormExtractionService(
            config=domain_conf, filename=filename, reader=reader
        )
        try:
            clinical_models = service.form_cls.get_factual_clinical_models()
            total = max(1, len(clinical_models))
            completed_models: list[str] = list(job.get("completed_models") or [])
            run_id = job.get("run_id")
            is_Explicit_rerun = bool(job.get("force_replace", False))
            preserve_manual = bool(job.get("preserve_manual_edits", True))

            for idx, model_cls in enumerate(clinical_models, start=1):
                if queue_manager._is_job_aborted(
                    job_id, run_id=run_id, lease_id=lease_id
                ):
                    return
                model_name = model_cls.__name__

                is_manually_edited = (
                    preserve_manual
                    and service.form_cls.is_section_manually_edited(
                        service.form, model_name
                    )
                    and model_name in service.form.sections
                )

                # Skip sections already persisted on the form when resuming an unfinished job
                # or when protecting manually edited sections during a global rerun
                if is_manually_edited or (
                    not is_Explicit_rerun
                    and model_name in service.form.sections
                    and service.form.sections.get(model_name)
                ):
                    if model_name not in completed_models:
                        completed_models.append(model_name)
                    queue_manager.update_job_progress(
                        job_id=job_id,
                        current_step=f"Analyse clinique ({idx}/{total}) — {model_name} (déjà extraite)",
                        completed_models=completed_models,
                        progress_pct=round((idx / total) * 100.0, 1),
                        run_id=run_id,
                        lease_id=lease_id,
                    )
                    continue

                thinking_cb = QueueThinkingCallbackHandler(
                    queue_manager=queue_manager,
                    job_id=job_id,
                    run_id=run_id,
                    lease_id=lease_id,
                    section_name=model_name,
                )
                queue_manager.refresh_gpu_lease(lease_id, job_id=job_id)
                queue_manager.update_job_progress(
                    job_id=job_id,
                    current_step=f"Extraction clinique ({idx}/{total}) — {model_name}",
                    completed_models=completed_models,
                    progress_pct=round(((idx - 1) / total) * 100.0, 1),
                    run_id=run_id,
                    lease_id=lease_id,
                )
                extra_kwargs = (
                    {"clear_manual_flag": True} if not preserve_manual else {}
                )
                service.extract_section(
                    model_cls=model_cls,
                    upsert=True,
                    callbacks=[thinking_cb],
                    form=service.form,
                    reader=reader,
                    **extra_kwargs,
                )
                if model_name not in completed_models:
                    completed_models.append(model_name)
                queue_manager.update_job_progress(
                    job_id=job_id,
                    current_step=f"Extraction clinique ({idx}/{total}) — {model_name}",
                    completed_models=completed_models,
                    progress_pct=round((idx / total) * 100.0, 1),
                    run_id=run_id,
                    lease_id=lease_id,
                )

            with queue_manager._lock:
                has_wave3 = any(
                    j.get("depends_on_job_id") == job_id
                    and j["status"] == JobStatus.PENDING.value
                    for j in queue_manager._jobs.values()
                )
            next_status = (
                RCPProcessingStatus.PENDING_EXPERTS
                if has_wave3
                else RCPProcessingStatus.COMPLETED
            )
            self.on_job_enqueued(domain, filename, next_status)
        finally:
            service.close()

    def execute_wave3_experts(
        self, job: dict[str, Any], lease_id: str, queue_manager: Any
    ) -> None:
        """Execute Wave 3 (multi-agent expert board, completeness check, and care orientation on the `PatientMDTForm`)."""
        job_id = job["job_id"]
        domain = job["domain"]
        filename = job["filename"]
        domain_conf = self._resolve_domain_config(domain)

        self.on_job_enqueued(domain, filename, RCPProcessingStatus.PROCESSING_EXPERTS)

        reader = DocumentReader(domain_conf, filename)
        reader.read_document()
        service = PatientMDTFormExtractionService(
            config=domain_conf, filename=filename, reader=reader
        )
        try:
            expert_models = service.form_cls.get_expert_models()
            total = max(1, len(expert_models))
            completed_models: list[str] = list(job.get("completed_models") or [])
            run_id = job.get("run_id")
            is_Explicit_rerun = bool(job.get("force_replace", False))
            preserve_manual = bool(job.get("preserve_manual_edits", True))

            for idx, model_cls in enumerate(expert_models, start=1):
                if queue_manager._is_job_aborted(
                    job_id, run_id=run_id, lease_id=lease_id
                ):
                    return
                model_name = model_cls.__name__

                is_manually_edited = (
                    preserve_manual
                    and service.form_cls.is_section_manually_edited(
                        service.form, model_name
                    )
                    and model_name in service.form.sections
                )

                # Skip sections already persisted on the form when resuming an unfinished job
                # or when protecting manually edited sections during a global rerun
                if is_manually_edited or (
                    not is_Explicit_rerun
                    and model_name in service.form.sections
                    and service.form.sections.get(model_name)
                ):
                    if model_name not in completed_models:
                        completed_models.append(model_name)
                    queue_manager.update_job_progress(
                        job_id=job_id,
                        current_step=f"Concertation d'experts ({idx}/{total}) — {model_name} (déjà extraite)",
                        completed_models=completed_models,
                        progress_pct=round((idx / total) * 100.0, 1),
                        run_id=run_id,
                        lease_id=lease_id,
                    )
                    continue

                thinking_cb = QueueThinkingCallbackHandler(
                    queue_manager=queue_manager,
                    job_id=job_id,
                    run_id=run_id,
                    lease_id=lease_id,
                    section_name=model_name,
                )
                queue_manager.refresh_gpu_lease(lease_id, job_id=job_id)
                queue_manager.update_job_progress(
                    job_id=job_id,
                    current_step=f"Concertation d'experts ({idx}/{total}) — {model_name}",
                    completed_models=completed_models,
                    progress_pct=round(((idx - 1) / total) * 100.0, 1),
                    run_id=run_id,
                    lease_id=lease_id,
                )
                extra_kwargs = (
                    {"clear_manual_flag": True} if not preserve_manual else {}
                )
                service.extract_section(
                    model_cls=model_cls,
                    upsert=True,
                    callbacks=[thinking_cb],
                    form=service.form,
                    reader=reader,
                    **extra_kwargs,
                )
                if model_name not in completed_models:
                    completed_models.append(model_name)
                queue_manager.update_job_progress(
                    job_id=job_id,
                    current_step=f"Concertation d'experts ({idx}/{total}) — {model_name}",
                    completed_models=completed_models,
                    progress_pct=round((idx / total) * 100.0, 1),
                    run_id=run_id,
                    lease_id=lease_id,
                )

            self.on_job_enqueued(domain, filename, RCPProcessingStatus.COMPLETED)
        finally:
            service.close()

    def execute_single_model(
        self, job: dict[str, Any], lease_id: str, queue_manager: Any
    ) -> None:
        """Execute a single-section rerun job on the `PatientMDTForm`."""
        job_id = job["job_id"]
        domain = job["domain"]
        filename = job["filename"]
        target_model_name = job.get("model_name")
        if not target_model_name:
            raise ValueError("Missing model_name for SINGLE_MODEL job")

        domain_conf = self._resolve_domain_config(domain)
        queue_manager.refresh_gpu_lease(lease_id, job_id=job_id)
        queue_manager.update_job_progress(
            job_id=job_id,
            current_step=f"Mise à jour de la rubrique ({target_model_name})",
            progress_pct=30.0,
            run_id=job.get("run_id"),
            lease_id=lease_id,
        )

        reader = DocumentReader(domain_conf, filename)
        reader.read_document()
        service = PatientMDTFormExtractionService(
            config=domain_conf, filename=filename, reader=reader
        )
        thinking_cb = QueueThinkingCallbackHandler(
            queue_manager=queue_manager,
            job_id=job_id,
            run_id=job.get("run_id"),
            lease_id=lease_id,
            section_name=target_model_name,
        )
        try:
            target_cls = service.form_cls.get_section_model(target_model_name)
            if target_cls is None:
                raise ValueError(
                    f"Section '{target_model_name}' not found for domain '{domain}'."
                )

            if target_cls.__name__ == "PatientAdministrative":
                service.form.manual_edits = (
                    service.form_cls.archive_manual_edit_before_ai_rerun(
                        service.form.manual_edits,
                        "PatientAdministrative",
                    )
                )
                service.process_patient_association(
                    run_admin_ai=True,
                    callbacks=[thinking_cb],
                    form=service.form,
                    reader=reader,
                )
            else:
                extra_kwargs = (
                    {"clear_manual_flag": True}
                    if target_cls.__name__ in service.form.manual_edits
                    else {}
                )
                service.extract_section(
                    model_cls=target_cls,
                    upsert=True,
                    callbacks=[thinking_cb],
                    form=service.form,
                    reader=reader,
                    **extra_kwargs,
                )
        finally:
            service.close()

    def recover_unfinished_jobs(self, queue_manager: Any) -> int:
        """
        Scan unfinished `PatientMDTForm` records across all enabled domains on startup
        and re-enqueue them into `queue_manager`.
        """
        recovered = 0
        for domain in self.base_config.enabled_domains_list:
            try:
                domain_conf = self._resolve_domain_config(domain)
                if domain_conf.rcp.display_type != "mongodb":
                    continue
                form_cls = get_domain_mdt_form_cls(domain)
                clinical_count = max(1, len(form_cls.get_factual_clinical_models()))
                expert_count = max(1, len(form_cls.get_expert_models()))

                db_client = Mongodb(domain_conf)
                try:
                    repo = MongoPatientMDTFormRepository(db_client)
                    unfinished_docs = repo.list_unfinished()
                finally:
                    db_client.close()

                for doc in unfinished_docs:
                    filename = doc.get("file")
                    if not filename:
                        continue
                    status = doc.get("processing_status")
                    if status in (
                        RCPProcessingStatus.PENDING_ADMIN.value,
                        RCPProcessingStatus.PROCESSING_ADMIN.value,
                    ):
                        res = queue_manager.enqueue_import_file(
                            filename=filename,
                            target_patient_id=doc.get("target_patient_id")
                            or doc.get("patient_id"),
                            include_clinical=True,
                            total_clinical_models=clinical_count,
                            total_expert_models=expert_count,
                            domain=domain,
                        )
                    elif status in (
                        RCPProcessingStatus.PENDING_EXPERTS.value,
                        RCPProcessingStatus.PROCESSING_EXPERTS.value,
                    ):
                        res = queue_manager.enqueue_rcp_rerun(
                            filename=filename,
                            model_name=None,
                            total_clinical_models=clinical_count,
                            total_expert_models=expert_count,
                            domain=domain,
                            start_from_wave=3,
                            force_replace=False,
                        )
                    else:
                        res = queue_manager.enqueue_rcp_rerun(
                            filename=filename,
                            model_name=None,
                            total_clinical_models=clinical_count,
                            total_expert_models=expert_count,
                            domain=domain,
                            force_replace=False,
                        )
                    if not res.get("already_queued"):
                        recovered += 1
            except Exception as exc:
                self.logger.warning(
                    f"Could not recover unfinished jobs for domain '{domain}': {exc}"
                )
        return recovered

    def on_queue_idle(self) -> None:
        """Unload active LLM models when the processing queue becomes completely idle."""
        try:
            unload_active_models(self.base_config)
        except Exception:
            pass
