from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.application.config import AppConfig
from src.application.paths import is_safe_filename
from src.infrastructure.queue import InMemoryQueueManager, get_global_queue_manager
from src.routers.dependencies import DomainConfigDep
from src.models.queue import (
    EnqueueImportRequest,
    EnqueueRerunRequest,
    EnqueueResponse,
    GpuLeaseResponse,
    JobDeletedResponse,
    QueueCleanRequest,
    QueueCleanResponse,
    QueueDomainsResponse,
    QueueJobResponse,
    QueueStatsResponse,
    ReleaseLocksResponse,
)

router = APIRouter(prefix="/queue", tags=["queue"])


def get_queue_manager() -> InMemoryQueueManager:
    return get_global_queue_manager()


QueueManagerDep = Annotated[InMemoryQueueManager, Depends(get_queue_manager)]


@router.get("/domains", response_model=QueueDomainsResponse)
def get_allowed_domains():
    """Retourne les domaines médicaux actifs configurés sur l'API Cross-Domains."""
    base_conf = AppConfig()
    return {
        "default_domain": base_conf.domain,
        "allowed_domains": base_conf.enabled_domains_list,
    }


@router.get("/stats", response_model=QueueStatsResponse)
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


@router.get("/jobs", response_model=list[QueueJobResponse])
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


@router.post("/enqueue-import", response_model=EnqueueResponse)
def enqueue_import_endpoint(
    request: EnqueueImportRequest,
    config: DomainConfigDep,
    manager: QueueManagerDep,
):
    """Enfile une fiche importée (Étape 1 Identification + Étape 2 Clinique) dans la `PriorityQueue`."""
    if not is_safe_filename(request.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        )
    return manager.enqueue_import_file(
        filename=request.filename,
        target_patient_id=request.target_patient_id,
        batch_id=request.batch_id,
        include_clinical=request.include_clinical,
        total_clinical_models=request.total_clinical_models,
        domain=config.domain,
    )


@router.post("/rerun", response_model=EnqueueResponse)
def enqueue_rerun_endpoint(
    request: EnqueueRerunRequest,
    config: DomainConfigDep,
    manager: QueueManagerDep,
):
    """Enfile une relance complète ou unitaire dans la `PriorityQueue` pour le domaine cible."""
    if not is_safe_filename(request.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        )
    return manager.enqueue_rcp_rerun(
        filename=request.filename,
        model_name=request.model_name,
        total_clinical_models=request.total_clinical_models,
        domain=config.domain,
    )


@router.post("/jobs/{job_id}/retry", response_model=QueueJobResponse)
def retry_queue_job_endpoint(job_id: str, manager: QueueManagerDep):
    """Remet en file d'attente une tâche spécifique."""
    updated = manager.retry_job(job_id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tâche '{job_id}' introuvable.",
        )
    return updated


@router.delete("/jobs/{job_id}", response_model=JobDeletedResponse)
def delete_queue_job_endpoint(job_id: str, manager: QueueManagerDep):
    """Annule ou supprime une tâche et libère son emplacement d'exécution éventuel."""
    deleted = manager.cancel_or_delete_job(job_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tâche '{job_id}' introuvable.",
        )
    return {"job_id": job_id, "deleted": True}


@router.post("/clean", response_model=QueueCleanResponse)
def clean_queue_endpoint(
    http_request: Request,
    request: QueueCleanRequest,
    manager: QueueManagerDep,
    domain: Annotated[Optional[str], Query()] = None,
):
    """Nettoie la file de traitement selon le mode demandé (par domaine ou globalement)."""
    # `mode` est validé par `QueueCleanMode` (Literal) : 422 si invalide.
    target_domain = getattr(http_request.state, "requested_domain", domain)
    return manager.clean_queue(mode=request.mode, domain=target_domain)


@router.get("/locks", response_model=list[GpuLeaseResponse])
def get_queue_locks_endpoint(manager: QueueManagerDep):
    """Liste les emplacements d'exécution (verrous) actifs."""
    return manager.get_all_gpu_leases()


@router.delete("/locks", response_model=ReleaseLocksResponse)
def release_queue_locks_endpoint(
    request: Request,
    manager: QueueManagerDep,
    lease_id: Annotated[Optional[str], Query()] = None,
    job_id: Annotated[Optional[str], Query()] = None,
    domain: Annotated[Optional[str], Query()] = None,
    force_all: Annotated[bool, Query()] = False,
):
    """Lève un verrou spécifique, ceux d'un domaine, ou tous les verrous actifs (requiert force_all=true)."""
    target_domain = getattr(request.state, "requested_domain", domain)
    if not lease_id and not job_id and not target_domain and not force_all:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Paramètre requis : fournissez `lease_id`, `job_id`, `domain`, ou `force_all=true`.",
        )
    removed = manager.release_gpu_lease(
        lease_id=lease_id,
        job_id=job_id,
        domain=target_domain,
        force_all=force_all,
    )
    return {"released_locks": removed}
