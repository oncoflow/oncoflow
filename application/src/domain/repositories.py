from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from src.domain.bug_report import BugReport, BugStatus
from src.domain.patient import Patient
from src.domain.worker.queue_job import RCPProcessingStatus


@runtime_checkable
class PatientRepository(Protocol):
    """Domain repository port for persisting `Patient` aggregates."""

    def get_by_id(self, patient_id: str) -> Patient | None: ...

    def find_by_identity(
        self,
        first_name: str | None,
        last_name: str | None,
        date_birth: datetime | str | None = None,
        fallback_file: str | None = None,
    ) -> Patient | None: ...

    def list_all(self) -> list[Patient]: ...

    def save(self, patient: Patient, filename: str | None = None) -> Patient: ...

    def remove_file(self, filename: str) -> None: ...

    def delete(self, patient_id: str) -> None: ...


@runtime_checkable
class PatientMDTFormRepository(Protocol):
    """Domain repository port for persisting `PatientMDTForm` aggregates."""

    def get_by_file(self, filename: str) -> dict[str, Any] | None: ...

    def list_all(
        self, projection: dict[str, int] | None = None
    ) -> list[dict[str, Any]]: ...

    def list_by_patient(
        self, patient_id: str, files: list[str] | None = None
    ) -> list[dict[str, Any]]: ...

    def list_by_files(
        self, filenames: list[str], projection: dict[str, int] | None = None
    ) -> list[dict[str, Any]]: ...

    def list_unfinished(self) -> list[dict[str, Any]]: ...

    def save_full(
        self, filename: str, payload: dict[str, Any], replace: bool = True
    ) -> None: ...

    def upsert_fields(
        self,
        filename: str,
        fields: dict[str, Any],
        set_on_insert: dict[str, Any] | None = None,
    ) -> None: ...

    def delete_by_file(self, filename: str) -> None: ...


@runtime_checkable
class DocumentCacheRepository(Protocol):
    """Domain repository port for caching parsed Markdown representations of PDF documents."""

    def get_by_hash(self, file_hash: str) -> dict[str, Any] | None: ...

    def save(
        self,
        file_hash: str,
        file_name: str,
        markdown: str,
        document_type: str = "mtd",
    ) -> None: ...

    def delete(
        self,
        file_hash: str | None = None,
        file_name: str | None = None,
        clear_all: bool = False,
    ) -> None: ...


@runtime_checkable
class BugReportRepository(Protocol):
    """Domain repository port for persisting `BugReport` entities."""

    def save(self, report: BugReport) -> BugReport: ...

    def get_by_id(self, bug_id: str) -> BugReport | None: ...

    def list_all(
        self,
        status: str | None = None,
        severity: str | None = None,
        category: str | None = None,
    ) -> list[BugReport]: ...

    def update_status(
        self, bug_id: str, status: BugStatus | str
    ) -> BugReport | None: ...

    def delete(self, bug_id: str) -> None: ...


@runtime_checkable
class QueueJobExecutor(Protocol):
    """Application port injected into the priority queue manager to execute domain jobs."""

    def on_job_enqueued(
        self,
        domain: str,
        filename: str,
        status: RCPProcessingStatus | str,
        extra_fields: dict[str, Any] | None = None,
    ) -> None: ...

    def on_job_failed(self, domain: str, filename: str, error_message: str) -> None: ...

    def stabilize_status(self, domain: str, filename: str) -> None: ...

    def has_administrative_data(self, domain: str, filename: str) -> bool: ...

    def execute_wave1_admin(
        self, job: dict[str, Any], lease_id: str, queue_manager: Any
    ) -> str | None: ...

    def execute_wave2_clinical(
        self, job: dict[str, Any], lease_id: str, queue_manager: Any
    ) -> None: ...

    def execute_wave3_experts(
        self, job: dict[str, Any], lease_id: str, queue_manager: Any
    ) -> None: ...

    def execute_single_model(
        self, job: dict[str, Any], lease_id: str, queue_manager: Any
    ) -> None: ...

    def recover_unfinished_jobs(self, queue_manager: Any) -> int: ...

    def on_queue_idle(self) -> None: ...
