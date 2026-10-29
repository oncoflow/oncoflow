from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field

from src.models.queue import EnqueueResponse, QueueJobResponse


class ProcessRequest(BaseModel):
    model_name: Optional[str] = Field(
        default=None,
        description="Nom optionnel du modèle à réexécuter (ex: PatientPerformanceStatus). Si omis, exécute l'analyse complète.",
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
