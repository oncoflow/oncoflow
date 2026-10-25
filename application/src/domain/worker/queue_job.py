from datetime import datetime
from enum import Enum
import uuid

from pydantic import BaseModel, Field


class RCPProcessingStatus(str, Enum):
    """Statut de traitement d'une fiche RCP dans rcp_info."""

    PENDING_ADMIN = "PENDING_ADMIN"
    PROCESSING_ADMIN = "PROCESSING_ADMIN"
    PENDING_CLINICAL = "PENDING_CLINICAL"
    PROCESSING_CLINICAL = "PROCESSING_CLINICAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    @classmethod
    def labels_fr(cls) -> dict[str, str]:
        return {
            cls.PENDING_ADMIN.value: "⏳ En attente de traitement",
            cls.PROCESSING_ADMIN.value: "🔍 Identification du patient en cours",
            cls.PENDING_CLINICAL.value: "⏳ Analyse clinique en attente",
            cls.PROCESSING_CLINICAL.value: "🔄 Analyse clinique en cours",
            cls.COMPLETED.value: "✅ Dossier prêt",
            cls.FAILED.value: "❌ Échec du traitement",
        }


class JobStatus(str, Enum):
    """Statut d'une tâche dans la file de traitement (ai_jobs_queue)."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @classmethod
    def labels_fr(cls) -> dict[str, str]:
        return {
            cls.PENDING.value: "⏳ En attente",
            cls.PROCESSING.value: "🔄 En cours",
            cls.COMPLETED.value: "✅ Terminé",
            cls.FAILED.value: "❌ Échec",
            cls.CANCELLED.value: "🚫 Annulé",
        }


class JobType(str, Enum):
    """Type de tâche dans la file de traitement en 2 étapes."""

    WAVE1_ADMIN = "WAVE1_ADMIN"
    WAVE2_CLINICAL = "WAVE2_CLINICAL"
    SINGLE_MODEL = "SINGLE_MODEL"

    @classmethod
    def labels_fr(cls) -> dict[str, str]:
        return {
            cls.WAVE1_ADMIN.value: "Identification du patient",
            cls.WAVE2_CLINICAL.value: "Analyse clinique complète",
            cls.SINGLE_MODEL.value: "Mise à jour d'une rubrique",
        }


class JobPriority:
    """Priorités standards d'ordonnancement (plus grand = plus prioritaire)."""

    WAVE1_ADMIN_IMPORT = 100
    WAVE1_ADMIN_RERUN = 95
    SINGLE_MODEL_RERUN = 90
    WAVE2_CLINICAL_RERUN = 80
    WAVE2_CLINICAL_IMPORT = 50


class QueueJob(BaseModel):
    """Modèle domaine représentant une tâche dans la file de traitement."""

    job_id: str = Field(
        default_factory=lambda: f"job_{uuid.uuid4().hex[:12]}",
        description="Identifiant unique de la tâche",
    )
    batch_id: str | None = Field(
        default=None,
        description="Identifiant du lot d'import (regroupe les fichiers importés ensemble)",
    )
    domain: str = Field(
        default="oncology",
        description="Domaine applicatif (oncology, sma)",
    )
    filename: str = Field(
        description="Nom du fichier PDF de la fiche RCP",
    )
    target_patient_id: str | None = Field(
        default=None,
        description="Identifiant patient forcé à l'import (None si automatique)",
    )
    resolved_patient_id: str | None = Field(
        default=None,
        description="Identifiant patient résolu après l'étape d'identification",
    )
    patient_label: str | None = Field(
        default=None,
        description="Nom affiché du patient une fois identifié",
    )
    job_type: JobType = Field(
        default=JobType.WAVE1_ADMIN,
        description="Type de tâche (WAVE1_ADMIN, WAVE2_CLINICAL, SINGLE_MODEL)",
    )
    model_name: str | None = Field(
        default=None,
        description="Nom du modèle ciblé lorsque job_type == SINGLE_MODEL",
    )
    status: JobStatus = Field(
        default=JobStatus.PENDING,
        description="Statut courant de la tâche",
    )
    priority: int = Field(
        default=JobPriority.WAVE1_ADMIN_IMPORT,
        description="Priorité d'ordonnancement (100 = Étape 1, 50 = Étape 2)",
    )
    depends_on_job_id: str | None = Field(
        default=None,
        description="ID de la tâche parente (ex: WAVE1_ADMIN) devant être terminée avant l'exécution",
    )
    worker_id: str | None = Field(
        default=None,
        description="Identifiant du worker traitant la tâche",
    )
    lease_id: str | None = Field(
        default=None,
        description="Identifiant du verrou matériel associé",
    )
    current_step: str = Field(
        default="En attente de traitement",
        description="Libellé métier de l'étape en cours",
    )
    completed_models: list[str] = Field(
        default_factory=list,
        description="Liste des rubriques cliniques déjà traitées",
    )
    total_models: int = Field(
        default=1,
        ge=1,
        description="Nombre total de rubriques à traiter dans cette tâche",
    )
    progress_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Pourcentage d'avancement (0 à 100)",
    )
    attempts: int = Field(
        default=0,
        ge=0,
        description="Nombre de tentatives effectuées",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        description="Nombre maximal de réessais autorisés",
    )
    error_message: str | None = Field(
        default=None,
        description="Message d'erreur en cas d'échec",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Date de création de la tâche",
    )
    started_at: datetime | None = Field(
        default=None,
        description="Date de début de traitement",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Date de fin de traitement",
    )
    heartbeat_at: datetime | None = Field(
        default=None,
        description="Dernier signal de vie du worker",
    )


class GpuLease(BaseModel):
    """Modèle domaine représentant un verrou de traitement actif dans Oncoflow_system.gpu_leases."""

    lease_id: str = Field(
        default_factory=lambda: f"lease_{uuid.uuid4().hex[:10]}",
        description="Identifiant unique du verrou",
    )
    worker_id: str = Field(description="Identifiant du worker détenteur")
    domain: str = Field(description="Domaine applicatif (oncology, sma)")
    job_id: str = Field(description="Identifiant de la tâche en cours")
    filename: str = Field(description="Fichier RCP en cours de traitement")
    job_type: str = Field(default=JobType.WAVE1_ADMIN.value)
    acquired_at: datetime = Field(default_factory=datetime.now)
    heartbeat_at: datetime = Field(default_factory=datetime.now)
