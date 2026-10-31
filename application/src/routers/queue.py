from collections.abc import Iterable
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from src.application.paths import is_safe_filename
from src.infrastructure.queue import InMemoryQueueManager, get_global_queue_manager
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
    QueueThinkingResponse,
    QueueThinkingStreamEvent,
    ReleaseLocksResponse,
)
from src.routers.dependencies import DomainConfigDep, get_base_config, require_admin

router = APIRouter(prefix="/queue", tags=["queue"])


def get_queue_manager() -> InMemoryQueueManager:
    return get_global_queue_manager()


QueueManagerDep = Annotated[InMemoryQueueManager, Depends(get_queue_manager)]


@router.get("/domains", response_model=QueueDomainsResponse)
def get_allowed_domains():
    """Return active medical domains configured on the cross-domain API."""
    base_conf = get_base_config()
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
    """Retrieve statistics for the `PriorityQueue` and active execution slots."""
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
    """List tasks in the processing queue (filterable by domain, status, batch, or filename)."""
    target_domain = getattr(request.state, "requested_domain", domain)
    return manager.get_queue_jobs(
        status=status_filter,
        batch_id=batch_id,
        limit=limit,
        domain=target_domain,
        filename=filename,
    )


@router.get("/thinking", response_model=QueueThinkingResponse)
def get_active_thinking_endpoint(
    request: Request,
    manager: QueueManagerDep,
    domain: Annotated[Optional[str], Query()] = None,
):
    """Return a snapshot of the live AI reasoning for the currently running task."""
    target_domain = getattr(request.state, "requested_domain", domain)
    return manager.get_job_thinking(job_id=None, domain=target_domain)


@router.get("/thinking/stream", response_class=EventSourceResponse)
def stream_active_thinking_endpoint(
    request: Request,
    manager: QueueManagerDep,
    domain: Annotated[Optional[str], Query()] = None,
    timeout: Annotated[float, Query(ge=1.0, le=300.0)] = 30.0,
) -> Iterable[ServerSentEvent]:
    """Stream live AI reasoning tokens (SSE) for the currently running task in the queue."""
    target_domain = getattr(request.state, "requested_domain", domain)
    for ev in manager.stream_job_thinking(
        job_id=None, domain=target_domain, timeout=timeout
    ):
        payload = QueueThinkingStreamEvent(**ev)
        yield ServerSentEvent(data=payload, event=payload.event)


@router.get("/jobs/{job_id}/thinking", response_model=QueueThinkingResponse)
def get_job_thinking_endpoint(
    job_id: str,
    manager: QueueManagerDep,
):
    """Return a snapshot of the live AI reasoning for a specific task `job_id`."""
    snap = manager.get_job_thinking(job_id=job_id)
    if not snap.get("job_id"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tâche '{job_id}' introuvable.",
        )
    return snap


@router.get("/jobs/{job_id}/thinking/stream", response_class=EventSourceResponse)
def stream_job_thinking_endpoint(
    job_id: str,
    manager: QueueManagerDep,
    timeout: Annotated[float, Query(ge=1.0, le=300.0)] = 30.0,
) -> Iterable[ServerSentEvent]:
    """Stream live AI reasoning tokens (SSE) for a specific task `job_id`."""
    if not manager.get_job(job_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tâche '{job_id}' introuvable.",
        )
    for ev in manager.stream_job_thinking(job_id=job_id, timeout=timeout):
        payload = QueueThinkingStreamEvent(**ev)
        yield ServerSentEvent(data=payload, event=payload.event)


@router.post("/enqueue-import", response_model=EnqueueResponse)
def enqueue_import_endpoint(
    request: EnqueueImportRequest,
    config: DomainConfigDep,
    manager: QueueManagerDep,
):
    """Enqueue an imported `PatientMDTForm` file (Wave 1 Identification + Wave 2 Clinical + Wave 3 Experts) into the `PriorityQueue`."""
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
        total_expert_models=request.total_expert_models,
        domain=config.domain,
    )


@router.post("/rerun", response_model=EnqueueResponse)
def enqueue_rerun_endpoint(
    request: EnqueueRerunRequest,
    config: DomainConfigDep,
    manager: QueueManagerDep,
):
    """Enqueue a full or single-section rerun into the `PriorityQueue` for the target domain."""
    if not is_safe_filename(request.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        )
    return manager.enqueue_rcp_rerun(
        filename=request.filename,
        model_name=request.model_name,
        total_clinical_models=request.total_clinical_models,
        total_expert_models=request.total_expert_models,
        domain=config.domain,
        preserve_manual_edits=request.preserve_manual_edits,
    )


@router.post(
    "/jobs/{job_id}/retry",
    response_model=QueueJobResponse,
    dependencies=[Depends(require_admin)],
)
def retry_queue_job_endpoint(job_id: str, manager: QueueManagerDep):
    """Re-enqueue a specific task for execution (admin required when user headers are present)."""
    updated = manager.retry_job(job_id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tâche '{job_id}' introuvable.",
        )
    return updated


@router.delete(
    "/jobs/{job_id}",
    response_model=JobDeletedResponse,
    dependencies=[Depends(require_admin)],
)
def delete_queue_job_endpoint(job_id: str, manager: QueueManagerDep):
    """Cancel or delete a task and release any associated execution lease (admin required when user headers are present)."""
    deleted = manager.cancel_or_delete_job(job_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tâche '{job_id}' introuvable.",
        )
    return {"job_id": job_id, "deleted": True}


@router.post(
    "/clean",
    response_model=QueueCleanResponse,
    dependencies=[Depends(require_admin)],
)
def clean_queue_endpoint(
    http_request: Request,
    manager: QueueManagerDep,
    request: Annotated[QueueCleanRequest, Body()] = QueueCleanRequest(),
    domain: Annotated[Optional[str], Query()] = None,
):
    """Clean the processing queue according to the requested mode (per domain or globally)."""
    # `mode` is validated by `QueueCleanMode` (Literal): 422 if invalid.
    target_domain = getattr(http_request.state, "requested_domain", domain)
    return manager.clean_queue(mode=request.mode, domain=target_domain)


@router.get("/locks", response_model=list[GpuLeaseResponse])
def get_queue_locks_endpoint(manager: QueueManagerDep):
    """List active hardware execution slots (leases)."""
    return manager.get_all_gpu_leases()


@router.delete(
    "/locks",
    response_model=ReleaseLocksResponse,
    dependencies=[Depends(require_admin)],
)
def release_queue_locks_endpoint(
    request: Request,
    manager: QueueManagerDep,
    lease_id: Annotated[Optional[str], Query()] = None,
    job_id: Annotated[Optional[str], Query()] = None,
    domain: Annotated[Optional[str], Query()] = None,
    force_all: Annotated[bool, Query()] = False,
):
    """Release a specific lease, leases for a domain, or all active leases (requires `force_all=true`)."""
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
