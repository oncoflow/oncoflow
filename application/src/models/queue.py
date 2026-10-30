"""Input/output schemas for the processing queue API (`/api/v1/queue`)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

QueueCleanMode = Literal[
    "completed", "failed", "reset_stuck", "retry_failed", "pending", "all"
]


# --- Requests ---


class QueueCleanRequest(BaseModel):
    mode: QueueCleanMode = Field(
        default="completed",
        description="Cleanup mode: completed, failed, reset_stuck, retry_failed, pending, all",
    )


class EnqueueImportRequest(BaseModel):
    filename: str
    target_patient_id: str | None = None
    batch_id: str | None = None
    include_clinical: bool = True
    total_clinical_models: int = Field(default=1, ge=1)
    total_expert_models: int = Field(default=3, ge=1)


class EnqueueRerunRequest(BaseModel):
    filename: str
    model_name: str | None = None
    total_clinical_models: int = Field(default=1, ge=1)
    total_expert_models: int = Field(default=3, ge=1)


# --- Responses ---


class QueueJobResponse(BaseModel):
    """API representation of a queue task (permissive mirror of `QueueJob`)."""

    job_id: str
    batch_id: str | None = None
    domain: str
    filename: str
    target_patient_id: str | None = None
    resolved_patient_id: str | None = None
    patient_label: str | None = None
    job_type: str
    model_name: str | None = None
    status: str
    priority: int | None = None
    depends_on_job_id: str | None = None
    worker_id: str | None = None
    lease_id: str | None = None
    current_step: str | None = None
    completed_models: list[str] = Field(default_factory=list)
    total_models: int | None = None
    progress_pct: float | None = None
    attempts: int | None = None
    max_retries: int | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    heartbeat_at: datetime | None = None
    active_agent: str | None = None
    current_thinking: str | None = None
    thinking_updated_at: datetime | None = None


class QueueThinkingResponse(BaseModel):
    """Snapshot of the live AI reasoning state for an active or specific queue task."""

    active: bool = False
    job_id: str | None = None
    domain: str | None = None
    filename: str | None = None
    job_type: str | None = None
    status: str | None = None
    current_step: str | None = None
    active_agent: str | None = None
    current_thinking: str = ""
    thinking_seq: int = 0
    progress_pct: float | None = None
    thinking_updated_at: datetime | None = None


class QueueThinkingStreamEvent(BaseModel):
    """Server-Sent Event payload emitted while streaming live AI reasoning for a queue task."""

    event: Literal["thinking", "done", "heartbeat"] = "thinking"
    active: bool = False
    job_id: str | None = None
    domain: str | None = None
    filename: str | None = None
    job_type: str | None = None
    status: str | None = None
    current_step: str | None = None
    active_agent: str | None = None
    delta: str = ""
    current_thinking: str = ""
    thinking_seq: int = 0
    progress_pct: float | None = None
    thinking_updated_at: datetime | None = None


class EnqueueResponse(BaseModel):
    already_queued: bool
    filename: str
    domain: str
    model_name: str | None = None
    jobs: list[QueueJobResponse] = Field(default_factory=list)


class QueueStatsResponse(BaseModel):
    pending: int
    processing: int
    completed: int
    failed: int
    cancelled: int
    active_locks: int
    batch_size: int
    hardware_profile: str
    allowed_domains: list[str]


class QueueDomainsResponse(BaseModel):
    default_domain: str | None = None
    allowed_domains: list[str]


class QueueCleanResponse(BaseModel):
    mode: QueueCleanMode
    affected_jobs: int


class JobDeletedResponse(BaseModel):
    job_id: str
    deleted: bool


class GpuLeaseResponse(BaseModel):
    lease_id: str
    worker_id: str | None = None
    domain: str | None = None
    job_id: str | None = None
    filename: str | None = None
    acquired_at: datetime | None = None
    heartbeat_at: datetime | None = None
    expires_at: datetime | None = None


class ReleaseLocksResponse(BaseModel):
    released_locks: int


class HealthResponse(BaseModel):
    status: str
    allowed_domains: list[str]
    queue: QueueStatsResponse
