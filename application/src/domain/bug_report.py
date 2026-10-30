import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class BugCategory(str, Enum):
    """Categories for bug reports or improvement suggestions."""

    ai_extraction = "ai_extraction"
    rag_guidelines = "rag_guidelines"
    chat_agent = "chat_agent"
    ui = "ui"
    import_pdf = "import_pdf"
    feature_request = "feature_request"
    other = "other"

    @classmethod
    def labels(cls) -> dict["BugCategory", str]:
        return {
            cls.ai_extraction: "Extraction IA / Résumé clinique",
            cls.rag_guidelines: "Référentiels TNCD / RAG",
            cls.chat_agent: "Assistant IA / Débat d'experts",
            cls.ui: "Interface utilisateur / Affichage",
            cls.import_pdf: "Import PDF / OCR",
            cls.feature_request: "Suggestion d'amélioration",
            cls.other: "Autre",
        }


class BugSeverity(str, Enum):
    """Severity levels for a bug report."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

    @classmethod
    def labels(cls) -> dict["BugSeverity", str]:
        return {
            cls.low: "Faible",
            cls.medium: "Moyen",
            cls.high: "Élevé",
            cls.critical: "Critique",
        }


class BugStatus(str, Enum):
    """Tracking statuses for a bug report."""

    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"

    @classmethod
    def labels(cls) -> dict["BugStatus", str]:
        return {
            cls.open: "Ouvert",
            cls.in_progress: "En cours",
            cls.resolved: "Résolu",
            cls.closed: "Fermé",
        }


def generate_bug_id() -> str:
    """Generate a short unique identifier for a bug report."""
    return f"bug_{uuid.uuid4().hex[:8]}"


class BugReport(BaseModel):
    """
    Domain model representing a bug report or user suggestion.
    """

    bug_id: str = Field(
        default_factory=generate_bug_id,
        description="Identifiant unique du rapport de bug",
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Titre court résumant le problème ou la suggestion",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Description détaillée du bug observé ou de l'amélioration souhaitée",
    )
    category: BugCategory = Field(
        default=BugCategory.other,
        description="Catégorie fonctionnelle du signalement",
    )
    severity: BugSeverity = Field(
        default=BugSeverity.medium,
        description="Niveau de sévérité ou d'impact",
    )
    status: BugStatus = Field(
        default=BugStatus.open,
        description="Statut de résolution du ticket",
    )
    page: str | None = Field(
        default=None,
        description="Page ou composant de l'application concerné",
    )
    patient_id: str | None = Field(
        default=None,
        description="Identifiant du dossier patient éventuellement concerné",
    )
    rcp_file: str | None = Field(
        default=None,
        description="Nom du fichier PDF RCP éventuellement concerné",
    )
    steps_to_reproduce: str | None = Field(
        default=None,
        description="Étapes pour reproduire le problème ou comportement attendu",
    )
    reporter: str | None = Field(
        default="anonymous",
        description="Utilisateur ayant soumis le rapport",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Date et heure de création du signalement",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Date et heure de dernière mise à jour",
    )

    @field_validator("created_at", mode="before")
    @classmethod
    def parse_created_at(cls, v: Any) -> datetime:
        if isinstance(v, datetime):
            return v
        if isinstance(v, str) and v.strip():
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                pass
        return datetime.now()

    @field_validator("updated_at", mode="before")
    @classmethod
    def parse_updated_at(cls, v: Any) -> datetime | None:
        if v is None or v == "":
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                return None
        return None

    @field_validator("category", mode="before")
    @classmethod
    def parse_category(cls, v: Any) -> BugCategory:
        if isinstance(v, BugCategory):
            return v
        if isinstance(v, str):
            for item in BugCategory:
                if v.lower() in (item.value.lower(), item.name.lower()):
                    return item
        return BugCategory.other

    @field_validator("severity", mode="before")
    @classmethod
    def parse_severity(cls, v: Any) -> BugSeverity:
        if isinstance(v, BugSeverity):
            return v
        if isinstance(v, str):
            for item in BugSeverity:
                if v.lower() in (item.value.lower(), item.name.lower()):
                    return item
        return BugSeverity.medium

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, v: Any) -> BugStatus:
        if isinstance(v, BugStatus):
            return v
        if isinstance(v, str):
            for item in BugStatus:
                if v.lower() in (item.value.lower(), item.name.lower()):
                    return item
        return BugStatus.open
