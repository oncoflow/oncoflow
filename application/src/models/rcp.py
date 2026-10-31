"""Pydantic request and response schemas for the `/api/v1/patientmdtform` router."""

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.models.queue import EnqueueResponse, QueueJobResponse


class ProcessRequest(BaseModel):
    model_name: Optional[str] = Field(
        default=None,
        description="Nom optionnel du modèle à réexécuter (ex: PatientPerformanceStatus). Si omis, exécute l'analyse complète.",
    )
    preserve_manual_edits: bool = Field(
        default=True,
        description="Conserver par défaut les rubriques modifiées manuellement lors d'une relance globale.",
    )


class SectionUpdateRequest(BaseModel):
    section_data: dict[str, Any] = Field(
        description="Données de la rubrique à valider et enregistrer"
    )
    edited_by: Optional[str] = Field(
        default=None,
        description="Identifiant de l'utilisateur ayant effectué la modification",
    )


class AdministrativeUpdateRequest(BaseModel):
    first_name: str = Field(default="", description="Prénom du patient")
    last_name: str = Field(default="", description="Nom d'usage du patient")
    born_name: Optional[str] = Field(default=None, description="Nom de naissance")
    date_birth: Optional[str | datetime] = Field(
        default=None, description="Date de naissance (YYYY-MM-DD)"
    )
    date_rcp: Optional[str | datetime] = Field(
        default=None, description="Date de la séance RCP (YYYY-MM-DD)"
    )
    gender: Optional[str] = Field(default=None, description="Genre du patient")
    apply_to_all_patient_forms: bool = Field(
        default=True,
        description="Appliquer la mise à jour d'état civil à toutes les fiches du dossier patient",
    )
    edited_by: Optional[str] = Field(
        default=None,
        description="Identifiant de l'utilisateur ayant effectué la modification",
    )


class LinkPatientRequest(BaseModel):
    target_patient_id: str = Field(
        description="Identifiant du dossier patient existant auquel rattacher la fiche RCP"
    )
    override_date_rcp: Optional[str | datetime] = Field(
        default=None,
        description="Date de la séance RCP optionnelle à enregistrer sur la fiche",
    )
    edited_by: Optional[str] = Field(
        default=None,
        description="Identifiant de l'utilisateur ayant effectué le rattachement",
    )


class ChatRequest(BaseModel):
    agent_name: str = Field(
        description="Nom de l'agent expert avec lequel échanger (ex: 'pancreas expert')"
    )
    message: str = Field(description="Question ou instruction pour l'agent")
    language: Optional[Literal["french", "english"]] = Field(
        default=None,
        description="Langue de réponse souhaitée pour l'agent ('french' ou 'english')",
    )


class RCPCardResponse(BaseModel):
    file: str
    link: Optional[str] = None
    patient_id: Optional[str] = None
    patient: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_birth: Optional[datetime] = None
    date_refresh: Optional[datetime] = None
    date: Optional[datetime] = None
    experts: List[str] = Field(default_factory=list)
    missing: List[str] = Field(default_factory=list)
    urgency: str
    urgency_score: int
    priority_level: Optional[int] = None
    intervention_required: Optional[bool] = None
    intervention_type: Optional[str] = None
    care_adaptation_suggested: Optional[bool] = None
    proposed_care_type: Optional[str] = None
    processing_status: Optional[str] = None
    processing_step: Optional[str] = None
    processing_progress_pct: Optional[float] = None


class PatientCardResponse(BaseModel):
    patient_id: str
    patient: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_birth: Optional[datetime] = None
    rcp_count: int = 1
    file: Optional[str] = None
    latest_file: str
    link: Optional[str] = None
    date_refresh: Optional[datetime] = None
    date: Optional[datetime] = None
    experts: List[str] = Field(default_factory=list)
    missing: List[str] = Field(default_factory=list)
    urgency: str
    urgency_score: int
    priority_level: Optional[int] = None
    intervention_required: Optional[bool] = None
    intervention_type: Optional[str] = None
    care_adaptation_suggested: Optional[bool] = None
    proposed_care_type: Optional[str] = None
    processing_status: Optional[str] = None
    processing_step: Optional[str] = None
    processing_progress_pct: Optional[float] = None


class PatientResponse(BaseModel):
    """Patient identity exposed by the API (whitelisted fields without internal MongoDB metadata)."""

    patient_id: str
    first_name: str = ""
    last_name: str = ""
    born_name: Optional[str] = None
    date_birth: Optional[datetime] = None
    gender: Optional[str] = None
    files: List[str] = Field(default_factory=list)
    updated_at: Optional[datetime] = None


class PatientListItemResponse(PatientResponse):
    """Raw patient record list item including computed `display_label` and `full_name`."""

    display_label: str = ""
    full_name: str = ""


class PatientMDTFormDetailResponse(BaseModel):
    """Full `PatientMDTForm` document response preserving dynamic domain-specific clinical sections."""

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    file: str
    patient_id: Optional[str] = None
    processing_status: Optional[str] = None
    manually_edited_sections: List[str] = Field(default_factory=list)
    last_manual_edit: Optional[dict[str, Any]] = None
    ui_date: Optional[datetime | str] = None
    PatientAdministrative: Optional[dict[str, Any]] = None
    metrics: Optional[RCPCardResponse] = None
    mdt_date: Optional[datetime] = None


class AdministrativeUpdateResponse(BaseModel):
    """Response returned when updating patient administrative details or linking a form to a patient."""

    patient: PatientResponse
    form: PatientMDTFormDetailResponse


class PatientDetailResponse(BaseModel):
    patient: PatientResponse
    latest_file: Optional[str] = None
    # Dynamic clinical sections per domain are preserved on each PatientMDTForm entry.
    rcps: List[dict[str, Any]]


class ChatResponse(BaseModel):
    response: str = Field(description="Réponse textuelle de l'agent")


class MessageResponse(BaseModel):
    message: str = Field(description="Message de confirmation lisible")


class UploadResponse(BaseModel):
    filename: str
    domain: str
    message: str
    is_duplicate: bool = False
    link: Optional[str] = None
    patient_id: Optional[str] = None
    patient: Optional[dict[str, Any]] = None
    batch_id: Optional[str] = None
    enqueued_count: Optional[int] = None
    already_queued_count: Optional[int] = None
    results: List[EnqueueResponse] = Field(default_factory=list)


class ProcessResponse(BaseModel):
    message: str
    filename: Optional[str] = None
    domain: Optional[str] = None
    model_name: Optional[str] = None
    queued: Optional[bool] = None
    already_queued: Optional[bool] = None
    jobs: List[QueueJobResponse] = Field(default_factory=list)


class FormSectionSchemaResponse(BaseModel):
    """Pure domain schema for a single clinical or decision section of a `PatientMDTForm`."""

    name: str
    description: str
    question: Optional[str] = None
    multi_agent: bool
    collaborative: bool = False
    agents: List[str] = Field(default_factory=list)
    editable: bool
    json_schema: dict[str, Any]


class DomainFormSchemaResponse(BaseModel):
    """Domain-specific `PatientMDTForm` schema including ordered sections and clinical enums."""

    domain: str
    sections: List[FormSectionSchemaResponse]
    enums: dict[str, List[Any]]


class ActiveJobsStateResponse(BaseModel):
    """Summary of active processing queue jobs for a specific `PatientMDTForm` file."""

    has_any_job: bool
    has_full_job: bool
    active_models: List[str] = Field(default_factory=list)
    current_step: Optional[str] = None
    jobs: List[QueueJobResponse] = Field(default_factory=list)


class PatientResolveResponse(BaseModel):
    """Resolved `PatientRecord`, its chronologically sorted `PatientMDTForm` records, and selected/latest files."""

    patient: Optional[PatientResponse] = None
    rcps: List[dict[str, Any]] = Field(default_factory=list)
    selected_file: Optional[str] = None
    latest_file: Optional[str] = None


class BatchFileStatusResponse(BaseModel):
    """Per-file status within an upload batch."""

    filename: str
    processing_status: Optional[str] = None
    step: Optional[str] = None
    pct: float = 0.0
    patient_id: Optional[str] = None
    patient_label: Optional[str] = None
    error: Optional[str] = None


class BatchStatusResponse(BaseModel):
    """Aggregated status of a multi-file upload batch."""

    batch_id: str
    overall_pct: float = 0.0
    files: List[BatchFileStatusResponse] = Field(default_factory=list)


class PatientMDTFormStatusResponse(BaseModel):
    """Lightweight processing status for a single `PatientMDTForm` record."""

    filename: Optional[str] = None
    processing_status: Optional[str] = None
    processing_step: Optional[str] = None
    processing_progress_pct: float = 0.0
    processing_error: Optional[str] = None
    patient_id: Optional[str] = None


class MeResponse(BaseModel):
    """Current authenticated user identity and admin role resolved from trusted proxy headers."""

    username: Optional[str] = None
    display_name: Optional[str] = None
    is_admin: bool = False
