"""Pydantic request and response schemas for the `/api/v1/patientmdtform` router."""

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.models.queue import EnqueueResponse, QueueJobResponse
from src.models.resources import ResourceIndexResponse

__all__ = [
    "EnqueueResponse",
    "QueueJobResponse",
    "ResourceIndexResponse",
]


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


class MissingItemsUpdateRequest(BaseModel):
    hide_missing_items: Optional[bool] = None
    toggle_item: Optional[str] = None
    hidden_missing_items: Optional[List[str]] = None
    what_missing: Optional[List[str]] = None
    edited_by: Optional[str] = None


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


class _RcpTriageCardBase(BaseModel):
    patient: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_birth: Optional[datetime] = None
    link: Optional[str] = None
    date_refresh: Optional[datetime] = None
    date: Optional[datetime] = None
    experts: List[str] = Field(default_factory=list)
    missing: List[str] = Field(default_factory=list)
    all_missing_items: List[str] = Field(default_factory=list)
    hidden_missing_items: List[str] = Field(default_factory=list)
    hide_missing_items: bool = False
    is_complete: Optional[bool] = None
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


class RCPCardResponse(_RcpTriageCardBase):
    file: str
    patient_id: Optional[str] = None


class PatientCardResponse(_RcpTriageCardBase):
    patient_id: str
    rcp_count: int = 1
    file: Optional[str] = None
    latest_file: str


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


class PatientMetricPointResponse(BaseModel):
    """Single chronological observation along a multi-year patient metric timeline."""

    form_id: str
    form_date: Optional[str] = None
    form_date_label: str = "Date non renseignée"
    days_since_first_rcp: int = 0
    x_ratio: float = 0.0
    raw_value: Any = None
    display_value: str = ""
    numeric_value: Optional[float] = None
    sub_values: Optional[dict[str, float]] = None
    is_annotative_only: bool = False
    is_manual: bool = False
    edited_by: Optional[str] = None
    edited_at: Optional[str] = None
    delta_numeric: Optional[float] = None
    delta_display: Optional[str] = None


class PatientMetricSeriesResponse(BaseModel):
    """Chronological series of raw metric observations across all forms of a patient."""

    metric_key: str
    section: str
    field: str
    label: str
    unit: str = ""
    scale_min: Optional[float] = None
    scale_max: Optional[float] = None
    polarity: str = "neutral"
    value_type: str = "numeric_or_mixed"
    points: List[PatientMetricPointResponse] = Field(default_factory=list)


class PatientRecordSummaryContentResponse(BaseModel):
    """Structured longitudinal clinical synthesis content."""

    clinical_trajectory_overview: str = ""
    disease_and_treatment_evolution: str = ""
    notable_metric_changes: List[str] = Field(default_factory=list)
    unresolved_vigilance_points: List[str] = Field(default_factory=list)
    mdt_decisions_recap: List[str] = Field(default_factory=list)
    sources_used: List[str] = Field(default_factory=list)


class PatientRecordSummaryStateResponse(BaseModel):
    """Global longitudinal patient summary state including obsolescence metadata and active queue job."""

    has_summary: bool = False
    generated_at: Optional[str] = None
    covered_form_ids: List[str] = Field(default_factory=list)
    latest_form_id_at_generation: Optional[str] = None
    latest_form_date_at_generation: Optional[str] = None
    model_used: Optional[str] = None
    is_obsolete: bool = False
    obsolete_reasons: List[str] = Field(default_factory=list)
    new_forms_since_summary: List[str] = Field(default_factory=list)
    removed_forms_since_summary: List[str] = Field(default_factory=list)
    modified_forms_since_summary: List[str] = Field(default_factory=list)
    content: Optional[PatientRecordSummaryContentResponse] = None
    active_job: Optional[dict[str, Any]] = None


class PatientDashboardResponse(BaseModel):
    """Consolidated longitudinal patient dashboard payload."""

    patient: PatientResponse
    domain: str
    latest_file: Optional[str] = None
    rcp_count: int = 0
    metrics: List[PatientMetricSeriesResponse] = Field(default_factory=list)
    summary: PatientRecordSummaryStateResponse


class PatientSummaryTriggerRequest(BaseModel):
    """Request payload to trigger on-demand global patient record summary generation."""

    force: bool = Field(
        default=False,
        description="Forcer la régénération même si le résumé n'est pas marqué obsolète",
    )


class PatientSummaryTriggerResponse(BaseModel):
    """Response returned when enqueuing or executing a global patient record summary."""

    patient_id: str
    domain: str
    queued: bool = True
    already_queued: bool = False
    job: Optional[dict[str, Any]] = None
    summary: Optional[PatientRecordSummaryStateResponse] = None
