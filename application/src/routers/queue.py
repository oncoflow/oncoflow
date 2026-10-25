from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.application.config import AppConfig
from src.infrastructure.queue import SqliteQueueBroker

app_conf = AppConfig()
router = APIRouter(prefix="/queue", tags=["queue"])


class QueueCleanRequest(BaseModel):
    mode: str = Field(
        default="completed",
        description="Mode de nettoyage : completed, reset_stuck, retry_failed, pending, all, failed",
    )


def get_queue_broker():
    broker = SqliteQueueBroker(app_conf)
    try:
        yield broker
    finally:
        broker.close()


@router.get("/stats")
def get_queue_stats_endpoint(broker: SqliteQueueBroker = Depends(get_queue_broker)):
    """Récupère les statistiques de la file de traitement et des verrous actifs."""
    return broker.get_queue_stats()


@router.get("/jobs")
def get_queue_jobs_endpoint(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    batch_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    broker: SqliteQueueBroker = Depends(get_queue_broker),
):
    """Liste les tâches de la file de traitement."""
    return broker.get_queue_jobs(status=status_filter, batch_id=batch_id, limit=limit)


@router.post("/jobs/{job_id}/retry")
def retry_queue_job_endpoint(
    job_id: str, broker: SqliteQueueBroker = Depends(get_queue_broker)
):
    """Remet en file d'attente une tâche spécifique."""
    updated = broker.retry_job(job_id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tâche '{job_id}' introuvable.",
        )
    return updated


@router.delete("/jobs/{job_id}")
def delete_queue_job_endpoint(
    job_id: str, broker: SqliteQueueBroker = Depends(get_queue_broker)
):
    """Annule ou supprime une tâche et libère son verrou éventuel."""
    deleted = broker.cancel_or_delete_job(job_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tâche '{job_id}' introuvable.",
        )
    return {"job_id": job_id, "deleted": True}


@router.post("/clean")
def clean_queue_endpoint(
    request: QueueCleanRequest,
    broker: SqliteQueueBroker = Depends(get_queue_broker),
):
    """Nettoie la file de traitement selon le mode demandé."""
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
    return broker.clean_queue(mode=request.mode)


@router.get("/locks")
def get_queue_locks_endpoint(broker: SqliteQueueBroker = Depends(get_queue_broker)):
    """Liste les verrous d'exécution actifs."""
    return broker.get_all_gpu_leases()


@router.delete("/locks")
def release_queue_locks_endpoint(
    lease_id: Optional[str] = Query(default=None),
    force_all: bool = Query(default=False),
    broker: SqliteQueueBroker = Depends(get_queue_broker),
):
    """Lève un verrou spécifique ou tous les verrous actifs."""
    if not lease_id and not force_all:
        force_all = True
    removed = broker.release_gpu_lease(lease_id=lease_id, force_all=force_all)
    return {"released_locks": removed}
