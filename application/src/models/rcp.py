from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field

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


class RCPCardResponse(BaseModel):
    file: str
    patient_id: Optional[str] = None
    patient: str
    date_refresh: Optional[datetime]
    date: Optional[datetime]
    experts: List[str]
    missing: List[str]
    urgency: str
    urgency_score: int
    intervention_required: Optional[bool]
    intervention_type: Optional[str]


class PatientCardResponse(BaseModel):
    patient_id: str
    patient: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_birth: Optional[datetime] = None
    rcp_count: int = 1
    latest_file: str
    date_refresh: Optional[datetime] = None
    date: Optional[datetime] = None
    experts: List[str]
    missing: List[str]
    urgency: str
    urgency_score: int
    intervention_required: Optional[bool] = None
    intervention_type: Optional[str] = None


class PatientResponse(BaseModel):
    """Identité patient exposée par l'API (liste blanche de champs, sans métadonnées Mongo)."""

    patient_id: str
    first_name: str = ""
    last_name: str = ""
    born_name: Optional[str] = None
    date_birth: Optional[datetime] = None
    gender: Optional[str] = None
    files: List[str] = Field(default_factory=list)
    updated_at: Optional[datetime] = None


class PatientDetailResponse(BaseModel):
    patient: PatientResponse
    latest_file: Optional[str] = None
    # Le contenu d'une fiche RCP dépend des modèles cliniques du domaine (schéma dynamique).
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
