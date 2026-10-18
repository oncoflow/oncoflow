from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field


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


class PatientDetailResponse(BaseModel):
    patient: dict[str, Any]
    latest_file: Optional[str] = None
    rcps: List[dict[str, Any]]


class ChatResponse(BaseModel):
    response: str = Field(description="Réponse textuelle de l'agent")
