from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from src.application.config import AppConfig
from src.infrastructure.documents.db_interface import DomainConfigDep
from src.infrastructure.queue import InMemoryQueueManager, get_global_queue_manager

router = APIRouter(prefix="/queue", tags=["queue"])


class QueueCleanRequest(BaseModel):
    mode: str = Field(
        default="completed",
        description="Mode de nettoyage : completed, reset_stuck, retry_failed, pending, all, failed",
    )


class EnqueueImportRequest(BaseModel):
    filename: str
    target_patient_id: str | None = None
    batch_id: str | None = None
    include_clinical: bool = True
    total_clinical_models: int = 1


class EnqueueRerunRequest(BaseModel):
    filename: str
    model_name: str | None = None
    total_clinical_models: int = 1


def get_queue_manager() -> InMemoryQueueManager:
    return get_global_queue_manager()


QueueManagerDep = Annotated[InMemoryQueueManager, Depends(get_queue_manager)]


@router.get("/domains")
def get_allowed_domains():
    """Retourne les domaines médicaux actifs configurés sur l'API Cross-Domains."""
    base_conf = AppConfig()
    return {
        "default_domain": base_conf.domain,
        "allowed_domains": base_conf.enabled_domains_list,
    }


@router.get("/stats")
def get_queue_stats_endpoint(
    request: Request,
    manager: QueueManagerDep,
    domain: Annotated[
        Optional[str],
        Query(
            description="Filtrer les statistiques par domaine (ou omettre pour tous les domaines)"
        ),
    ] = None,
):
    """Récupère les statistiques de la file de traitement `PriorityQueue` et des tâches actives."""
    target_domain = getattr(request.state, "requested_domain", domain)
    return manager.get_queue_stats(domain=target_domain)


@router.get("/jobs")
def get_queue_jobs_endpoint(
    request: Request,
    manager: QueueManagerDep,
    domain: Annotated[Optional[str], Query()] = None,
    status_filter: Annotated[Optional[str], Query(alias="status")] = None,
    batch_id: Annotated[Optional[str], Query()] = None,
    filename: Annotated[Optional[str], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """Liste les tâches de la file de traitement (filtrables par domaine, statut, lot ou fichier)."""
    target_domain = getattr(request.state, "requested_domain", domain)
    jobs = manager.get_queue_jobs(
        status=status_filter,
        batch_id=batch_id,
        limit=limit,
        domain=target_domain,
    )
    if filename:
        jobs = [j for j in jobs if j.get("filename") == filename]
    return jobs


@router.post("/enqueue-import")
def enqueue_import_endpoint(
    request: EnqueueImportRequest,
    config: DomainConfigDep,
    manager: QueueManagerDep,
):
    """Enfile une fiche importée (Étape 1 Identification + Étape 2 Clinique) dans la `PriorityQueue`."""
    return manager.enqueue_import_file(
        filename=request.filename,
        target_patient_id=request.target_patient_id,
        batch_id=request.batch_id,
        include_clinical=request.include_clinical,
        total_clinical_models=request.total_clinical_models,
        domain=config.domain,
    )


@router.post("/rerun")
def enqueue_rerun_endpoint(
    request: EnqueueRerunRequest,
    config: DomainConfigDep,
    manager: QueueManagerDep,
):
    """Enfile une relance complète ou unitaire dans la `PriorityQueue` pour le domaine cible."""
    return manager.enqueue_rcp_rerun(
        filename=request.filename,
        model_name=request.model_name,
        total_clinical_models=request.total_clinical_models,
        domain=config.domain,
    )


@router.post("/jobs/{job_id}/retry")
def retry_queue_job_endpoint(job_id: str, manager: QueueManagerDep):
    """Remet en file d'attente une tâche spécifique."""
    updated = manager.retry_job(job_id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tâche '{job_id}' introuvable.",
        )
    return updated


@router.delete("/jobs/{job_id}")
def delete_queue_job_endpoint(job_id: str, manager: QueueManagerDep):
    """Annule ou supprime une tâche et libère son emplacement d'exécution éventuel."""
    deleted = manager.cancel_or_delete_job(job_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tâche '{job_id}' introuvable.",
        )
    return {"job_id": job_id, "deleted": True}


@router.post("/clean")
def clean_queue_endpoint(
    http_request: Request,
    request: QueueCleanRequest,
    manager: QueueManagerDep,
    domain: Annotated[Optional[str], Query()] = None,
):
    """Nettoie la file de traitement selon le mode demandé (par domaine ou globalement)."""
    valid_modes = {
        "completed",
        "failed",
        "reset_stuck",
        "retry_failed",
        "pending",
        "all",
    }
    if request.mode not in valid_modes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mode '{request.mode}' invalide. Modes supportés : {sorted(valid_modes)}",
        )
    target_domain = getattr(http_request.state, "requested_domain", domain)
    return manager.clean_queue(mode=request.mode, domain=target_domain)


@router.get("/locks")
def get_queue_locks_endpoint(manager: QueueManagerDep):
    """Liste les emplacements d'exécution (verrous) actifs."""
    return manager.get_all_gpu_leases()


@router.delete("/locks")
def release_queue_locks_endpoint(
    request: Request,
    manager: QueueManagerDep,
    lease_id: Annotated[Optional[str], Query()] = None,
    domain: Annotated[Optional[str], Query()] = None,
    force_all: Annotated[bool, Query()] = False,
):
    """Lève un verrou spécifique, ceux d'un domaine, ou tous les verrous actifs."""
    target_domain = getattr(request.state, "requested_domain", domain)
    if not lease_id and not target_domain and not force_all:
        force_all = True
    removed = manager.release_gpu_lease(
        lease_id=lease_id, domain=target_domain, force_all=force_all
    )
    return {"released_locks": removed}
