from datetime import datetime
from typing import List, Optional
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
    patient: str
    date_refresh: Optional[datetime]
    date: Optional[datetime]
    experts: List[str]
    missing: List[str]
    urgency: str
    urgency_score: int
    intervention_required: Optional[bool]
    intervention_type: Optional[str]


class ChatResponse(BaseModel):
    response: str = Field(description="Réponse textuelle de l'agent")
