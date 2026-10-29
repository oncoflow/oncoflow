import itertools
import os
import queue
import socket
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable

import httpx

from src.application.config import AppConfig
from src.domain.patient_mdt_form import get_domain_mdt_form_cls
from src.domain.worker import (
    JobPriority,
    JobStatus,
    JobType,
    QueueJob,
    RCPProcessingStatus,
)
from src.infrastructure.documents.mongodb import Mongodb

# Execution slot (GPU lease) time-to-live. A running job refreshes its lease from a
# heartbeat thread every `LEASE_HEARTBEAT_SECONDS`; a lease that is not refreshed
# before `expires_at` is considered orphaned (dead/hung worker) and is purged.
LEASE_TTL_SECONDS = 300
LEASE_HEARTBEAT_SECONDS = 60
# Upper bound of the passive wait of an idle worker (it is normally woken up earlier
# by `Condition.notify_all()` when a job is pushed or a lease is released).
WORKER_IDLE_WAIT_SECONDS = 5.0


class QueueUnavailableError(RuntimeError):
    """Raised by `QueueBroker` when the remote queue API cannot be reached or fails."""


def unload_active_models(app_conf: AppConfig) -> None:
    from src.application.app_functions.llm import unload_active_models as _unload

    _unload(app_conf)


def process_patient_association(*args: Any, **kwargs: Any):
    from src.application.patient import process_patient_association as _assoc

    return _assoc(*args, **kwargs)


class InMemoryQueueManager:
    """
    Cross-domain in-memory task queue manager powered by Python's standard library
    `queue.PriorityQueue`.

    Features:
    - Hardware batch sizing (`APP_QUEUE_BATCH_SIZE`, e.g., 1 by 1 on NVIDIA L4)
      enforced across all enabled domains (`APP_ALLOWED_DOMAINS`).
    - Two-wave scheduling: Step 1 (`WAVE1_ADMIN`, priority 100) always executes
      before Step 2 (`WAVE2_CLINICAL`, priority 50).
    - Strict deduplication per `(domain, filename, model_name)`.
    - Zero database polling (`PriorityQueue.get()` blocks passively on OS condition).
    - Automatic recovery of unfinished RCP documents from MongoDB on startup.
    """

    def __init__(
        self,
        base_config: AppConfig | None = None,
        auto_start_workers: bool = False,
    ) -> None:
        self.base_config = base_config or AppConfig()
        self.logger = self.base_config.set_logger("oncoflow.queue")
        self._pq: queue.PriorityQueue[tuple[int, float, int, str]] = (
            queue.PriorityQueue()
        )
        self._counter = itertools.count()
        self._lock = threading.RLock()
        # Workers wait passively on this condition (shares `_lock`); it is notified
        # whenever a job is pushed, a lease is released or the manager shuts down.
        self._cond = threading.Condition(self._lock)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._active_leases: dict[str, dict[str, Any]] = {}
        self._cancelled_job_ids: set[str] = set()
        self._stop_event = threading.Event()
        self._worker_threads: list[threading.Thread] = []
        self._workers_started = False

        if auto_start_workers:
            self.start_workers()

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _normalize_domain(self, domain: str | None = None) -> str:
        return (domain or self.base_config.domain or "oncology").strip().lower()

    def _resolve_domain_config(self, domain: str | None = None) -> AppConfig:
        return self.base_config.for_domain(self._normalize_domain(domain))

    def _notify_waiters(self) -> None:
        with self._cond:
            self._cond.notify_all()

    def _push_to_pq(self, job: dict[str, Any]) -> None:
        """Push a runnable job into the standard library PriorityQueue."""
        priority = int(job.get("priority", JobPriority.WAVE2_CLINICAL_IMPORT))
        created_at = job.get("created_at")
        ts = (
            created_at.timestamp()
            if isinstance(created_at, datetime)
            else datetime.now().timestamp()
        )
        seq = next(self._counter)
        self._pq.put((-priority, ts, seq, job["job_id"]))
        self._notify_waiters()

    @staticmethod
    def _reset_run_fields(job: dict[str, Any]) -> None:
        """Detach a job from its current execution attempt (invalidates `run_id`)."""
        job["run_id"] = None
        job["lease_id"] = None
        job["worker_id"] = None

    @staticmethod
    def _is_stale_run(
        job: dict[str, Any], run_id: str | None, lease_id: str | None
    ) -> bool:
        """
        True when the caller is not the current execution attempt of `job`
        (the job was retried / reset / requeued after lease expiry meanwhile).
        """
        if run_id is not None:
            return job.get("run_id") != run_id
        if lease_id is not None:
            return job.get("lease_id") != lease_id
        return False

    def _set_rcp_processing_status(
        self,
        domain: str,
        filename: str,
        processing_status: RCPProcessingStatus | str,
        extra_fields: dict[str, Any] | None = None,
    ) -> None:
        domain_conf = self._resolve_domain_config(domain)
        if domain_conf.rcp.display_type != "mongodb":
            return
        status_val = (
            processing_status.value
            if isinstance(processing_status, RCPProcessingStatus)
            else str(processing_status)
        )
        now = datetime.now()
        update_payload: dict[str, Any] = {
            "processing_status": status_val,
            "processing_updated_at": now,
        }
        if extra_fields:
            update_payload.update(extra_fields)

        db_client = Mongodb(domain_conf)
        try:
            db_client.database["rcp_info"].update_one(
                {"file": filename},
                {
                    "$set": update_payload,
                    "$setOnInsert": {
                        "file": filename,
                        "date_refresh": now,
                    },
                },
                upsert=True,
            )
        finally:
            db_client.close()

    def _stabilize_rcp_status_for_file(self, domain: str, filename: str) -> None:
        domain_conf = self._resolve_domain_config(domain)
        if domain_conf.rcp.display_type != "mongodb":
            return
        db_client = Mongodb(domain_conf)
        try:
            doc = db_client.database["rcp_info"].find_one({"file": filename})
            if not doc:
                return
            has_admin = bool(doc.get("PatientAdministrative"))
            target_status = (
                RCPProcessingStatus.COMPLETED.value
                if has_admin
                else RCPProcessingStatus.FAILED.value
            )
            db_client.database["rcp_info"].update_one(
                {"file": filename},
                {
                    "$set": {
                        "processing_status": target_status,
                        "processing_updated_at": datetime.now(),
                    }
                },
            )
        finally:
            db_client.close()

    @staticmethod
    def _clone_job(job: dict[str, Any]) -> dict[str, Any]:
        cloned = dict(job)
        if isinstance(cloned.get("completed_models"), list):
            cloned["completed_models"] = list(cloned["completed_models"])
        return cloned

    # ------------------------------------------------------------------
    # Deduplication & Active Job Queries
    # ------------------------------------------------------------------

    def get_active_jobs_for_file(
        self, filename: str, domain: str | None = None
    ) -> list[dict[str, Any]]:
        target_domain = self._normalize_domain(domain)
        with self._lock:
            active = [
                self._clone_job(j)
                for j in self._jobs.values()
                if j["domain"] == target_domain
                and j["filename"] == filename
                and j["status"] in (JobStatus.PENDING.value, JobStatus.PROCESSING.value)
            ]
        active.sort(
            key=lambda j: (
                -int(j.get("priority", 0)),
                j.get("created_at") or datetime.min,
            )
        )
        return active

    def has_active_job(
        self,
        filename: str,
        job_types: list[str] | None = None,
        model_name: str | None = None,
        domain: str | None = None,
    ) -> bool:
        active = self.get_active_jobs_for_file(filename, domain=domain)
        for job in active:
            if job_types and job.get("job_type") not in job_types:
                continue
            if model_name is not None and job.get("model_name") != model_name:
                continue
            return True
        return False

    # ------------------------------------------------------------------
    # Enqueue Operations (Step 1 + Step 2 & Reruns)
    # ------------------------------------------------------------------

    def enqueue_import_file(
        self,
        filename: str,
        target_patient_id: str | None = None,
        batch_id: str | None = None,
        include_clinical: bool = True,
        total_clinical_models: int = 1,
        domain: str | None = None,
    ) -> dict[str, Any]:
        target_domain = self._normalize_domain(domain)
        with self._lock:
            existing = [
                self._clone_job(j)
                for j in self._jobs.values()
                if j["domain"] == target_domain
                and j["filename"] == filename
                and j["status"] in (JobStatus.PENDING.value, JobStatus.PROCESSING.value)
                and j["job_type"]
                in (JobType.WAVE1_ADMIN.value, JobType.WAVE2_CLINICAL.value)
            ]
            if existing:
                return {
                    "already_queued": True,
                    "filename": filename,
                    "domain": target_domain,
                    "jobs": existing,
                }

            now = datetime.now()
            wave1_job = QueueJob(
                batch_id=batch_id,
                domain=target_domain,
                filename=filename,
                target_patient_id=target_patient_id,
                job_type=JobType.WAVE1_ADMIN,
                status=JobStatus.PENDING,
                priority=int(JobPriority.WAVE1_ADMIN_IMPORT),
                current_step="En attente d'identification du patient",
                total_models=1,
                max_retries=self.base_config.queue.max_retries,
                created_at=now,
            ).model_dump(mode="python")
            wave1_job["job_type"] = JobType.WAVE1_ADMIN.value
            wave1_job["status"] = JobStatus.PENDING.value

            self._jobs[wave1_job["job_id"]] = wave1_job
            self._push_to_pq(wave1_job)
            created_jobs = [self._clone_job(wave1_job)]

            if include_clinical:
                wave2_job = QueueJob(
                    batch_id=batch_id,
                    domain=target_domain,
                    filename=filename,
                    target_patient_id=target_patient_id,
                    job_type=JobType.WAVE2_CLINICAL,
                    status=JobStatus.PENDING,
                    priority=int(JobPriority.WAVE2_CLINICAL_IMPORT),
                    depends_on_job_id=wave1_job["job_id"],
                    current_step="En attente de l'analyse clinique",
                    total_models=max(1, total_clinical_models),
                    max_retries=self.base_config.queue.max_retries,
                    created_at=now + timedelta(milliseconds=1),
                ).model_dump(mode="python")
                wave2_job["job_type"] = JobType.WAVE2_CLINICAL.value
                wave2_job["status"] = JobStatus.PENDING.value
                # Stored in _jobs; pushed to _pq automatically once wave1 completes
                self._jobs[wave2_job["job_id"]] = wave2_job
                created_jobs.append(self._clone_job(wave2_job))

        self._set_rcp_processing_status(
            target_domain,
            filename,
            RCPProcessingStatus.PENDING_ADMIN,
            extra_fields=(
                {"target_patient_id": target_patient_id} if target_patient_id else None
            ),
        )
        return {
            "already_queued": False,
            "filename": filename,
            "domain": target_domain,
            "jobs": created_jobs,
        }

    def enqueue_rcp_rerun(
        self,
        filename: str,
        model_name: str | None = None,
        total_clinical_models: int = 1,
        domain: str | None = None,
    ) -> dict[str, Any]:
        target_domain = self._normalize_domain(domain)
        domain_conf = self._resolve_domain_config(target_domain)
        now = datetime.now()

        # Mongo I/O is done before taking the queue lock (never block workers on DB).
        has_admin = False
        if not model_name and domain_conf.rcp.display_type == "mongodb":
            db_client = Mongodb(domain_conf)
            try:
                rcp_doc = db_client.database["rcp_info"].find_one({"file": filename})
                has_admin = bool(rcp_doc and rcp_doc.get("PatientAdministrative"))
            finally:
                db_client.close()

        with self._lock:
            active_for_file = [
                j
                for j in self._jobs.values()
                if j["domain"] == target_domain
                and j["filename"] == filename
                and j["status"] in (JobStatus.PENDING.value, JobStatus.PROCESSING.value)
            ]

            full_active = [
                self._clone_job(j)
                for j in active_for_file
                if j["job_type"]
                in (JobType.WAVE1_ADMIN.value, JobType.WAVE2_CLINICAL.value)
            ]
            if full_active:
                return {
                    "already_queued": True,
                    "filename": filename,
                    "domain": target_domain,
                    "model_name": model_name,
                    "jobs": full_active,
                }

            if model_name:
                same_model = [
                    self._clone_job(j)
                    for j in active_for_file
                    if j["job_type"] == JobType.SINGLE_MODEL.value
                    and j.get("model_name") == model_name
                ]
                if same_model:
                    return {
                        "already_queued": True,
                        "filename": filename,
                        "domain": target_domain,
                        "model_name": model_name,
                        "jobs": same_model,
                    }

                single_job = QueueJob(
                    domain=target_domain,
                    filename=filename,
                    job_type=JobType.SINGLE_MODEL,
                    model_name=model_name,
                    status=JobStatus.PENDING,
                    priority=int(JobPriority.SINGLE_MODEL_RERUN),
                    current_step=f"Relance en attente ({model_name})",
                    total_models=1,
                    max_retries=self.base_config.queue.max_retries,
                    created_at=now,
                ).model_dump(mode="python")
                single_job["job_type"] = JobType.SINGLE_MODEL.value
                single_job["status"] = JobStatus.PENDING.value
                self._jobs[single_job["job_id"]] = single_job
                self._push_to_pq(single_job)
                return {
                    "already_queued": False,
                    "filename": filename,
                    "domain": target_domain,
                    "model_name": model_name,
                    "jobs": [self._clone_job(single_job)],
                }

            # Full rerun: cancel any pending SINGLE_MODEL jobs on this file
            for j in active_for_file:
                if (
                    j["job_type"] == JobType.SINGLE_MODEL.value
                    and j["status"] == JobStatus.PENDING.value
                ):
                    j["status"] = JobStatus.CANCELLED.value
                    j["completed_at"] = now
                    j["current_step"] = "Remplacée par une relance complète"
                    self._cancelled_job_ids.add(j["job_id"])

            created_jobs: list[dict[str, Any]] = []
            depends_id: str | None = None
            if not has_admin:
                wave1_job = QueueJob(
                    domain=target_domain,
                    filename=filename,
                    job_type=JobType.WAVE1_ADMIN,
                    status=JobStatus.PENDING,
                    priority=int(JobPriority.WAVE1_ADMIN_IMPORT),
                    current_step="En attente d'identification du patient",
                    total_models=1,
                    max_retries=self.base_config.queue.max_retries,
                    created_at=now,
                ).model_dump(mode="python")
                wave1_job["job_type"] = JobType.WAVE1_ADMIN.value
                wave1_job["status"] = JobStatus.PENDING.value
                self._jobs[wave1_job["job_id"]] = wave1_job
                self._push_to_pq(wave1_job)
                created_jobs.append(self._clone_job(wave1_job))
                depends_id = wave1_job["job_id"]

            wave2_job = QueueJob(
                domain=target_domain,
                filename=filename,
                job_type=JobType.WAVE2_CLINICAL,
                status=JobStatus.PENDING,
                priority=int(JobPriority.WAVE2_CLINICAL_RERUN),
                depends_on_job_id=depends_id,
                current_step="Relance de l'analyse clinique en attente",
                total_models=max(1, total_clinical_models),
                max_retries=self.base_config.queue.max_retries,
                created_at=now + timedelta(milliseconds=1),
            ).model_dump(mode="python")
            wave2_job["job_type"] = JobType.WAVE2_CLINICAL.value
            wave2_job["status"] = JobStatus.PENDING.value
            self._jobs[wave2_job["job_id"]] = wave2_job
            if depends_id is None:
                self._push_to_pq(wave2_job)
            created_jobs.append(self._clone_job(wave2_job))

        self._set_rcp_processing_status(
            target_domain,
            filename,
            RCPProcessingStatus.PENDING_CLINICAL
            if has_admin
            else RCPProcessingStatus.PENDING_ADMIN,
        )
        return {
            "already_queued": False,
            "filename": filename,
            "domain": target_domain,
            "model_name": None,
            "jobs": created_jobs,
        }

    # ------------------------------------------------------------------
    # Hardware Execution Slot (Lease) & Claim Operations
    # ------------------------------------------------------------------

    def _purge_expired_leases_locked(self, now: datetime | None = None) -> int:
        """
        Drop leases whose heartbeat stopped (`expires_at` in the past) and requeue the
        PROCESSING job they were protecting (its worker is dead or hung).
        Must be called while holding `self._lock`.
        """
        now = now or datetime.now()
        expired = [
            (lid, lease)
            for lid, lease in self._active_leases.items()
            if isinstance(lease.get("expires_at"), datetime)
            and lease["expires_at"] < now
        ]
        for lid, lease in expired:
            self._active_leases.pop(lid, None)
            job = self._jobs.get(lease.get("job_id") or "")
            if (
                job
                and job["status"] == JobStatus.PROCESSING.value
                and job.get("lease_id") == lid
            ):
                self.logger.warning(
                    f"GPU lease {lid} expired (worker {lease.get('worker_id')}); "
                    f"requeuing job {job['job_id']}"
                )
                job["status"] = JobStatus.PENDING.value
                self._reset_run_fields(job)
                job["current_step"] = "Remis en attente (verrou d'exécution expiré)"
                job["heartbeat_at"] = now
                self._push_to_pq(job)
        if expired:
            self._notify_waiters()
        return len(expired)

    def acquire_gpu_lease(
        self,
        worker_id: str,
        job_id: str,
        filename: str,
        domain: str | None = None,
        run_id: str | None = None,
    ) -> str | None:
        target_domain = self._normalize_domain(domain)
        now = datetime.now()
        with self._lock:
            self._purge_expired_leases_locked(now)
            if len(self._active_leases) >= self.base_config.queue.batch_size:
                return None
            lease_id = f"lease_{uuid.uuid4().hex[:10]}"
            self._active_leases[lease_id] = {
                "lease_id": lease_id,
                "worker_id": worker_id,
                "domain": target_domain,
                "job_id": job_id,
                "run_id": run_id,
                "filename": filename,
                "acquired_at": now,
                "heartbeat_at": now,
                "expires_at": now + timedelta(seconds=LEASE_TTL_SECONDS),
            }
            return lease_id

    def refresh_gpu_lease(self, lease_id: str, job_id: str | None = None) -> bool:
        now = datetime.now()
        with self._lock:
            lease = self._active_leases.get(lease_id)
            if not lease:
                return False
            lease["heartbeat_at"] = now
            lease["expires_at"] = now + timedelta(seconds=LEASE_TTL_SECONDS)
            job = self._jobs.get(job_id) if job_id else None
            if job and job.get("lease_id") in (None, lease_id):
                job["heartbeat_at"] = now
            return True

    def release_gpu_lease(
        self,
        lease_id: str | None = None,
        job_id: str | None = None,
        domain: str | None = None,
        force_all: bool = False,
    ) -> int:
        with self._lock:
            if force_all:
                count = len(self._active_leases)
                self._active_leases.clear()
            else:
                to_delete = [
                    lid
                    for lid, ldata in self._active_leases.items()
                    if (lease_id and lid == lease_id)
                    or (job_id and ldata.get("job_id") == job_id)
                    or (domain and ldata.get("domain") == domain)
                ]
                for lid in to_delete:
                    self._active_leases.pop(lid, None)
                count = len(to_delete)
            if count:
                self._notify_waiters()
            return count

    def get_all_gpu_leases(self) -> list[dict[str, Any]]:
        with self._lock:
            self._purge_expired_leases_locked()
            leases = [dict(v) for v in self._active_leases.values()]
        leases.sort(key=lambda x: x.get("acquired_at") or datetime.min)
        return leases

    def claim_next_job(
        self, worker_id: str, domain: str | None = None
    ) -> tuple[dict[str, Any] | None, str | None]:
        """
        Atomically pop the highest-priority runnable job from `queue.PriorityQueue`
        and acquire an execution slot respecting `batch_size`.

        Each successful claim stamps a fresh `run_id` (and `lease_id`) on the job:
        lifecycle updates coming from an older attempt are ignored.
        """
        with self._lock:
            self._purge_expired_leases_locked()
            if len(self._active_leases) >= self.base_config.queue.batch_size:
                return None, None

            requeue_buffer: list[tuple[int, float, int, str]] = []
            claimed_job: dict[str, Any] | None = None

            try:
                while not self._pq.empty():
                    try:
                        item = self._pq.get_nowait()
                    except queue.Empty:
                        break
                    prio, ts, seq, job_id = item
                    job = self._jobs.get(job_id)
                    if (
                        not job
                        or job_id in self._cancelled_job_ids
                        or job["status"] != JobStatus.PENDING.value
                    ):
                        self._pq.task_done()
                        continue

                    if domain and job["domain"] != domain.strip().lower():
                        requeue_buffer.append(item)
                        self._pq.task_done()
                        continue

                    dep_id = job.get("depends_on_job_id")
                    if dep_id:
                        dep_job = self._jobs.get(dep_id)
                        if dep_job and dep_job["status"] != JobStatus.COMPLETED.value:
                            # Dependency not completed yet: the job stays stored in
                            # `_jobs` (PENDING) and `complete_job(dep)` pushes it back.
                            job["current_step"] = "En attente de l'étape précédente"
                            self._pq.task_done()
                            continue

                    claimed_job = job
                    self._pq.task_done()
                    break
            finally:
                for item in requeue_buffer:
                    self._pq.put(item)

            if not claimed_job:
                return None, None

            now = datetime.now()
            run_id = uuid.uuid4().hex
            lease_id = self.acquire_gpu_lease(
                worker_id=worker_id,
                job_id=claimed_job["job_id"],
                filename=claimed_job["filename"],
                domain=claimed_job["domain"],
                run_id=run_id,
            )
            if not lease_id:  # pragma: no cover - capacity checked above
                self._push_to_pq(claimed_job)
                return None, None
            claimed_job["status"] = JobStatus.PROCESSING.value
            claimed_job["worker_id"] = worker_id
            claimed_job["run_id"] = run_id
            claimed_job["lease_id"] = lease_id
            claimed_job["started_at"] = now
            claimed_job["heartbeat_at"] = now
            return self._clone_job(claimed_job), lease_id

    # ------------------------------------------------------------------
    # Job Lifecycle Updates
    # ------------------------------------------------------------------

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._clone_job(job) if job else None

    def update_job_progress(
        self,
        job_id: str,
        current_step: str,
        completed_models: list[str] | None = None,
        progress_pct: float | None = None,
        resolved_patient_id: str | None = None,
        run_id: str | None = None,
        lease_id: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or self._is_stale_run(job, run_id, lease_id):
                return None
            job["current_step"] = current_step
            job["heartbeat_at"] = datetime.now()
            if completed_models is not None:
                job["completed_models"] = list(completed_models)
            if progress_pct is not None:
                job["progress_pct"] = round(float(progress_pct), 1)
            if resolved_patient_id is not None:
                job["resolved_patient_id"] = resolved_patient_id
            return self._clone_job(job)

    def complete_job(
        self,
        job_id: str,
        lease_id: str | None = None,
        resolved_patient_id: str | None = None,
        current_step: str = "Terminé",
        run_id: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now()
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                if lease_id:
                    self.release_gpu_lease(lease_id=lease_id)
                return None
            if self._is_stale_run(job, run_id, lease_id):
                if lease_id:
                    self.release_gpu_lease(lease_id=lease_id)
                return None
            job["status"] = JobStatus.COMPLETED.value
            job["completed_at"] = now
            job["heartbeat_at"] = now
            job["progress_pct"] = 100.0
            job["current_step"] = current_step
            self._reset_run_fields(job)
            if resolved_patient_id:
                job["resolved_patient_id"] = resolved_patient_id

            # Unlock & push any dependent Step 2 (WAVE2_CLINICAL) jobs into PriorityQueue
            # Also revive CANCELLED dependents if this wave1 was retried after a failure.
            for candidate in self._jobs.values():
                if candidate.get("depends_on_job_id") == job_id and candidate[
                    "status"
                ] in (JobStatus.PENDING.value, JobStatus.CANCELLED.value):
                    if candidate["status"] == JobStatus.CANCELLED.value:
                        candidate["status"] = JobStatus.PENDING.value
                        candidate["error_message"] = None
                        candidate["completed_at"] = None
                        candidate["current_step"] = "En attente de l'analyse clinique"
                        self._cancelled_job_ids.discard(candidate["job_id"])
                    if resolved_patient_id and not candidate.get("resolved_patient_id"):
                        candidate["resolved_patient_id"] = resolved_patient_id
                    self._push_to_pq(candidate)

            self.release_gpu_lease(lease_id=lease_id, job_id=job_id)
            return self._clone_job(job)

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        lease_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now()
        job_to_fail_rcp: tuple[str, str] | None = None
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                if lease_id:
                    self.release_gpu_lease(lease_id=lease_id)
                return None
            if self._is_stale_run(job, run_id, lease_id):
                if lease_id:
                    self.release_gpu_lease(lease_id=lease_id)
                return None

            self._reset_run_fields(job)
            attempts = int(job.get("attempts", 0)) + 1
            max_retries = int(
                job.get("max_retries", self.base_config.queue.max_retries)
            )
            if attempts <= max_retries:
                job["status"] = JobStatus.PENDING.value
                job["attempts"] = attempts
                job["error_message"] = error_message
                job["worker_id"] = None
                job["current_step"] = (
                    f"Nouvelle tentative programmée ({attempts}/{max_retries})"
                )
                job["heartbeat_at"] = now
                self._push_to_pq(job)
            else:
                job["status"] = JobStatus.FAILED.value
                job["attempts"] = attempts
                job["error_message"] = error_message
                job["completed_at"] = now
                job["heartbeat_at"] = now
                job["current_step"] = "Échec du traitement"
                for dep in self._jobs.values():
                    if (
                        dep.get("depends_on_job_id") == job_id
                        and dep["status"] == JobStatus.PENDING.value
                    ):
                        dep["status"] = JobStatus.CANCELLED.value
                        dep["completed_at"] = now
                        dep["error_message"] = (
                            "Annulé suite à l'échec de l'identification patient"
                        )
                        dep["current_step"] = "Annulé"
                        self._cancelled_job_ids.add(dep["job_id"])
                job_to_fail_rcp = (job["domain"], job["filename"])

            self.release_gpu_lease(lease_id=lease_id, job_id=job_id)
            result = self._clone_job(job)

        if job_to_fail_rcp:
            self._set_rcp_processing_status(
                job_to_fail_rcp[0],
                job_to_fail_rcp[1],
                RCPProcessingStatus.FAILED,
                extra_fields={"processing_error": error_message},
            )
        return result

    # ------------------------------------------------------------------
    # Admin & Monitoring Operations
    # ------------------------------------------------------------------

    def get_queue_stats(self, domain: str | None = None) -> dict[str, Any]:
        target_domain = domain.strip().lower() if domain else None
        with self._lock:
            relevant = [
                j
                for j in self._jobs.values()
                if not target_domain or j["domain"] == target_domain
            ]
            pending = sum(1 for j in relevant if j["status"] == JobStatus.PENDING.value)
            processing = sum(
                1 for j in relevant if j["status"] == JobStatus.PROCESSING.value
            )
            completed = sum(
                1 for j in relevant if j["status"] == JobStatus.COMPLETED.value
            )
            failed = sum(1 for j in relevant if j["status"] == JobStatus.FAILED.value)
            cancelled = sum(
                1 for j in relevant if j["status"] == JobStatus.CANCELLED.value
            )
            active_locks = len(self._active_leases)

        return {
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
            "active_locks": active_locks,
            "batch_size": self.base_config.queue.batch_size,
            "hardware_profile": self.base_config.queue.hardware_profile,
            "allowed_domains": self.base_config.enabled_domains_list,
        }

    def get_queue_jobs(
        self,
        status: str | None = None,
        batch_id: str | None = None,
        limit: int = 100,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        target_domain = domain.strip().lower() if domain else None
        with self._lock:
            jobs = [
                self._clone_job(j)
                for j in self._jobs.values()
                if (not target_domain or j["domain"] == target_domain)
                and (not status or j["status"] == status)
                and (not batch_id or j.get("batch_id") == batch_id)
            ]
        jobs.sort(key=lambda j: j.get("created_at") or datetime.min, reverse=True)
        return jobs[: int(limit)]

    def cancel_or_delete_job(self, job_id: str) -> bool:
        file_to_stabilize: tuple[str, str] | None = None
        with self._lock:
            job = self._jobs.pop(job_id, None)
            if not job:
                return False
            self._cancelled_job_ids.add(job_id)
            self.release_gpu_lease(job_id=job_id)

            for dep_id, dep in list(self._jobs.items()):
                if dep.get("depends_on_job_id") == job_id:
                    self._jobs.pop(dep_id, None)
                    self._cancelled_job_ids.add(dep_id)
                    self.release_gpu_lease(job_id=dep_id)

            domain = job["domain"]
            filename = job["filename"]
            still_active = any(
                j["domain"] == domain
                and j["filename"] == filename
                and j["status"] in (JobStatus.PENDING.value, JobStatus.PROCESSING.value)
                for j in self._jobs.values()
            )
            if not still_active:
                file_to_stabilize = (domain, filename)

        if file_to_stabilize:
            self._stabilize_rcp_status_for_file(*file_to_stabilize)
        return True

    def delete_jobs_for_file(self, filename: str, domain: str | None = None) -> int:
        target_domain = self._normalize_domain(domain)
        with self._lock:
            matching_ids = [
                jid
                for jid, j in self._jobs.items()
                if j["domain"] == target_domain and j["filename"] == filename
            ]
            for jid in matching_ids:
                self._jobs.pop(jid, None)
                self._cancelled_job_ids.add(jid)
                self.release_gpu_lease(job_id=jid)
            return len(matching_ids)

    def retry_job(self, job_id: str) -> dict[str, Any] | None:
        now = datetime.now()
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            self.release_gpu_lease(job_id=job_id)
            self._cancelled_job_ids.discard(job_id)
            self._reset_run_fields(job)
            job["status"] = JobStatus.PENDING.value
            job["attempts"] = 0
            job["error_message"] = None
            job["completed_at"] = None
            job["current_step"] = "Remis en file d'attente"
            job["heartbeat_at"] = now

            dep_id = job.get("depends_on_job_id")
            dep_job = self._jobs.get(dep_id) if dep_id else None
            if dep_job and dep_job["status"] != JobStatus.COMPLETED.value:
                if dep_job["status"] in (
                    JobStatus.FAILED.value,
                    JobStatus.CANCELLED.value,
                ):
                    self.release_gpu_lease(job_id=dep_id)
                    self._cancelled_job_ids.discard(dep_id)
                    self._reset_run_fields(dep_job)
                    dep_job["status"] = JobStatus.PENDING.value
                    dep_job["attempts"] = 0
                    dep_job["error_message"] = None
                    dep_job["completed_at"] = None
                    dep_job["current_step"] = "Remis en file d'attente"
                    dep_job["heartbeat_at"] = now
                    self._push_to_pq(dep_job)
                job["current_step"] = "En attente de l'étape précédente"
            else:
                self._push_to_pq(job)

            # If this job is a parent (wave1) being retried, revive any CANCELLED dependents
            for cand in self._jobs.values():
                if (
                    cand.get("depends_on_job_id") == job_id
                    and cand["status"] == JobStatus.CANCELLED.value
                ):
                    self._cancelled_job_ids.discard(cand["job_id"])
                    self._reset_run_fields(cand)
                    cand["status"] = JobStatus.PENDING.value
                    cand["attempts"] = 0
                    cand["error_message"] = None
                    cand["completed_at"] = None
                    cand["current_step"] = "En attente de l'étape précédente"
                    cand["heartbeat_at"] = now

            cloned = self._clone_job(job)

        target_status = (
            RCPProcessingStatus.PENDING_ADMIN
            if cloned["job_type"] == JobType.WAVE1_ADMIN.value
            else RCPProcessingStatus.PENDING_CLINICAL
        )
        self._set_rcp_processing_status(
            cloned["domain"], cloned["filename"], target_status
        )
        return cloned

    def clean_queue(
        self, mode: str = "completed", domain: str | None = None
    ) -> dict[str, Any]:
        target_domain = domain.strip().lower() if domain else None
        now = datetime.now()
        affected = 0
        files_to_stabilize: set[tuple[str, str]] = set()

        with self._lock:
            matching_ids = [
                jid
                for jid, j in self._jobs.items()
                if not target_domain or j["domain"] == target_domain
            ]

            if mode == "completed":
                for jid in matching_ids:
                    if self._jobs[jid]["status"] in (
                        JobStatus.COMPLETED.value,
                        JobStatus.CANCELLED.value,
                    ):
                        self._jobs.pop(jid, None)
                        affected += 1

            elif mode == "failed":
                for jid in matching_ids:
                    if self._jobs[jid]["status"] == JobStatus.FAILED.value:
                        self._jobs.pop(jid, None)
                        affected += 1

            elif mode == "reset_stuck":
                for jid in matching_ids:
                    job = self._jobs[jid]
                    if job["status"] == JobStatus.PROCESSING.value:
                        self._reset_run_fields(job)
                        job["status"] = JobStatus.PENDING.value
                        job["attempts"] = 0
                        job["current_step"] = "Remis en attente par l'administrateur"
                        job["heartbeat_at"] = now
                        self.release_gpu_lease(job_id=jid)
                        self._push_to_pq(job)
                        affected += 1
                self.release_gpu_lease(
                    domain=target_domain, force_all=(target_domain is None)
                )

            elif mode == "retry_failed":
                retried_ids: set[str] = set()
                for jid in matching_ids:
                    job = self._jobs[jid]
                    if job["status"] == JobStatus.FAILED.value:
                        self._reset_run_fields(job)
                        job["status"] = JobStatus.PENDING.value
                        job["attempts"] = 0
                        job["error_message"] = None
                        job["completed_at"] = None
                        job["current_step"] = "Relancé depuis l'espace d'administration"
                        job["heartbeat_at"] = now
                        dep_id = job.get("depends_on_job_id")
                        dep_job = self._jobs.get(dep_id) if dep_id else None
                        if (
                            not dep_job
                            or dep_job["status"] == JobStatus.COMPLETED.value
                        ):
                            self._push_to_pq(job)
                        retried_ids.add(jid)
                        affected += 1
                for cand in self._jobs.values():
                    if (
                        cand.get("depends_on_job_id") in retried_ids
                        and cand["status"] == JobStatus.CANCELLED.value
                    ):
                        self._cancelled_job_ids.discard(cand["job_id"])
                        self._reset_run_fields(cand)
                        cand["status"] = JobStatus.PENDING.value
                        cand["attempts"] = 0
                        cand["error_message"] = None
                        cand["completed_at"] = None
                        cand["current_step"] = "En attente de l'étape précédente"
                        cand["heartbeat_at"] = now

            elif mode == "pending":
                for jid in matching_ids:
                    job = self._jobs.get(jid)
                    if job and job["status"] == JobStatus.PENDING.value:
                        files_to_stabilize.add((job["domain"], job["filename"]))
                        self._jobs.pop(jid, None)
                        self._cancelled_job_ids.add(jid)
                        affected += 1

            elif mode == "all":
                for jid in matching_ids:
                    job = self._jobs.pop(jid, None)
                    if job:
                        files_to_stabilize.add((job["domain"], job["filename"]))
                        self._cancelled_job_ids.add(jid)
                        affected += 1
                self.release_gpu_lease(
                    domain=target_domain, force_all=(target_domain is None)
                )
            else:
                raise ValueError(f"Unsupported clean_queue mode: {mode}")

        for dom, fname in files_to_stabilize:
            self._stabilize_rcp_status_for_file(dom, fname)

        return {"mode": mode, "affected_jobs": affected}

    # ------------------------------------------------------------------
    # Worker Execution Logic (Step 1, Step 2, Single Model)
    # ------------------------------------------------------------------

    def _is_job_aborted(
        self,
        job_id: str,
        run_id: str | None = None,
        lease_id: str | None = None,
    ) -> bool:
        with self._lock:
            if job_id in self._cancelled_job_ids:
                return True
            job = self._jobs.get(job_id)
            if not job or job["status"] != JobStatus.PROCESSING.value:
                return True
            if self._is_stale_run(job, run_id, lease_id):
                return True
            return False

    def _execute_wave1_admin(self, job: dict[str, Any], lease_id: str) -> str | None:
        job_id = job["job_id"]
        domain = job["domain"]
        filename = job["filename"]
        target_patient_id = job.get("target_patient_id")
        domain_conf = self._resolve_domain_config(domain)
        form_cls = get_domain_mdt_form_cls(domain)

        self._set_rcp_processing_status(
            domain, filename, RCPProcessingStatus.PROCESSING_ADMIN
        )
        self.update_job_progress(
            job_id=job_id,
            current_step="Identification du patient en cours",
            progress_pct=20.0,
        )
        self.refresh_gpu_lease(lease_id, job_id=job_id)

        form = form_cls(config=domain_conf, document=filename)
        try:
            patient = process_patient_association(
                form=form,
                target_patient_id=target_patient_id,
                run_admin_ai=True,
            )
            resolved_pid = patient.patient_id if patient else target_patient_id

            with self._lock:
                has_wave2 = any(
                    j.get("depends_on_job_id") == job_id
                    and j["status"] == JobStatus.PENDING.value
                    for j in self._jobs.values()
                )
            next_rcp_status = (
                RCPProcessingStatus.PENDING_CLINICAL
                if has_wave2
                else RCPProcessingStatus.COMPLETED
            )
            self._set_rcp_processing_status(
                domain,
                filename,
                next_rcp_status,
                extra_fields=({"patient_id": resolved_pid} if resolved_pid else None),
            )
            return resolved_pid
        finally:
            del form

    def _execute_wave2_clinical(self, job: dict[str, Any], lease_id: str) -> None:
        job_id = job["job_id"]
        domain = job["domain"]
        filename = job["filename"]
        domain_conf = self._resolve_domain_config(domain)
        form_cls = get_domain_mdt_form_cls(domain)

        self._set_rcp_processing_status(
            domain, filename, RCPProcessingStatus.PROCESSING_CLINICAL
        )

        # Dynamically collect clinical models for this domain's PatientMDTForm
        import inspect
        from pydantic import BaseModel

        clinical_models = [
            obj
            for name, obj in inspect.getmembers(form_cls)
            if inspect.isclass(obj)
            and issubclass(obj, BaseModel)
            and name not in ("default_model", "PatientAdministrative")
        ]
        total = max(1, len(clinical_models))
        completed_models: list[str] = list(job.get("completed_models") or [])

        form = form_cls(config=domain_conf, document=filename)
        try:
            run_id = job.get("run_id")
            for idx, model_cls in enumerate(clinical_models, start=1):
                if self._is_job_aborted(job_id, run_id=run_id, lease_id=lease_id):
                    return
                model_name = model_cls.__name__
                self.refresh_gpu_lease(lease_id, job_id=job_id)
                self.update_job_progress(
                    job_id=job_id,
                    current_step=f"Analyse clinique ({idx}/{total})",
                    completed_models=completed_models,
                    progress_pct=round(((idx - 1) / total) * 100.0, 1),
                )
                form.read_model(model_cls, upsert=True)
                if model_name not in completed_models:
                    completed_models.append(model_name)
                self.update_job_progress(
                    job_id=job_id,
                    current_step=f"Analyse clinique ({idx}/{total})",
                    completed_models=completed_models,
                    progress_pct=round((idx / total) * 100.0, 1),
                )

            if hasattr(form, "read_experts"):
                if self._is_job_aborted(job_id, run_id=run_id, lease_id=lease_id):
                    return
                self.refresh_gpu_lease(lease_id, job_id=job_id)
                self.update_job_progress(
                    job_id=job_id,
                    current_step="Synthèse collégiale en cours",
                    completed_models=completed_models,
                    progress_pct=95.0,
                )
                form.read_experts()
                if domain_conf.rcp.display_type == "mongodb":
                    db_client = Mongodb(domain_conf)
                    try:
                        db_client.database["rcp_info"].update_one(
                            {"file": filename},
                            {
                                "$set": {
                                    "experts": form.mtd_datas.get("experts", {}),
                                    "date_refresh": datetime.now(),
                                }
                            },
                            upsert=True,
                        )
                    finally:
                        db_client.close()

            self._set_rcp_processing_status(
                domain, filename, RCPProcessingStatus.COMPLETED
            )
        finally:
            del form

    def _execute_single_model(self, job: dict[str, Any], lease_id: str) -> None:
        job_id = job["job_id"]
        domain = job["domain"]
        filename = job["filename"]
        target_model_name = job.get("model_name")
        if not target_model_name:
            raise ValueError("Missing model_name for SINGLE_MODEL job")

        domain_conf = self._resolve_domain_config(domain)
        form_cls = get_domain_mdt_form_cls(domain)

        self.refresh_gpu_lease(lease_id, job_id=job_id)
        self.update_job_progress(
            job_id=job_id,
            current_step=f"Mise à jour de la rubrique ({target_model_name})",
            progress_pct=30.0,
        )

        form = form_cls(config=domain_conf, document=filename)
        try:
            target_cls = getattr(form_cls, target_model_name, None)
            if target_cls is None:
                import inspect
                from pydantic import BaseModel

                for name, obj in inspect.getmembers(form_cls):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, BaseModel)
                        and name.lower() == target_model_name.lower()
                    ):
                        target_cls = obj
                        break
            if target_cls is None:
                raise ValueError(
                    f"Rubrique '{target_model_name}' introuvable pour le domaine '{domain}'."
                )

            if target_cls.__name__ == "PatientAdministrative":
                process_patient_association(form=form, run_admin_ai=True)
            else:
                form.read_model(target_cls, upsert=True)
        finally:
            del form

    def execute_claimed_job(self, job: dict[str, Any], lease_id: str) -> None:
        job_id = job["job_id"]
        run_id = job.get("run_id")
        job_type = job.get("job_type")
        hb_stop = threading.Event()

        def _heartbeat() -> None:
            while not hb_stop.wait(LEASE_HEARTBEAT_SECONDS):
                if not self.refresh_gpu_lease(lease_id, job_id=job_id):
                    break

        hb_thread = threading.Thread(
            target=_heartbeat,
            daemon=True,
            name=f"oncoflow-lease-hb-{lease_id}",
        )
        hb_thread.start()
        try:
            resolved_pid = job.get("resolved_patient_id")
            if job_type == JobType.WAVE1_ADMIN.value:
                resolved_pid = self._execute_wave1_admin(job, lease_id)
            elif job_type == JobType.WAVE2_CLINICAL.value:
                self._execute_wave2_clinical(job, lease_id)
            elif job_type == JobType.SINGLE_MODEL.value:
                self._execute_single_model(job, lease_id)
            else:
                raise ValueError(f"Unsupported job_type: {job_type}")

            if self._is_job_aborted(job_id, run_id=run_id, lease_id=lease_id):
                self.release_gpu_lease(lease_id=lease_id)
                return

            self.complete_job(
                job_id=job_id,
                lease_id=lease_id,
                resolved_patient_id=resolved_pid,
                current_step="Dossier prêt",
                run_id=run_id,
            )
        except Exception as exc:
            self.logger.exception("Job %s failed: %s", job_id, exc)
            self.fail_job(
                job_id=job_id,
                error_message=str(exc),
                lease_id=lease_id,
                run_id=run_id,
            )
        finally:
            hb_stop.set()
            self._maybe_unload_models_if_idle()

    def _maybe_unload_models_if_idle(self) -> None:
        stats = self.get_queue_stats()
        if stats["pending"] == 0 and stats["processing"] == 0:
            try:
                unload_active_models(self.base_config)
            except Exception:
                pass

    def run_once(
        self,
        domain: str | None = None,
        custom_step_runner: Callable[
            [dict[str, Any], "InMemoryQueueManager", str], None
        ]
        | None = None,
    ) -> bool:
        """
        Synchronously pop and execute at most one job from the `PriorityQueue`.
        Returns True if a job was claimed and processed.
        """
        worker_id = f"sync_worker_{socket.gethostname()}_{os.getpid()}"
        job, lease_id = self.claim_next_job(worker_id=worker_id, domain=domain)
        if not job or not lease_id:
            return False
        if custom_step_runner is not None:
            try:
                custom_step_runner(job, self, lease_id)
            except Exception as exc:
                self.fail_job(
                    job_id=job["job_id"],
                    error_message=str(exc),
                    lease_id=lease_id,
                )
            return True
        self.execute_claimed_job(job, lease_id)
        return True

    # ------------------------------------------------------------------
    # Background Worker Threads (Passive Wait on queue.PriorityQueue)
    # ------------------------------------------------------------------

    def start_workers(self) -> None:
        with self._lock:
            if self._workers_started:
                return
            self._stop_event.clear()
            self._workers_started = True
            batch_size = max(1, self.base_config.queue.batch_size)
            for idx in range(batch_size):
                worker_id = f"pq_worker_{idx}_{socket.gethostname()}_{os.getpid()}"
                thread = threading.Thread(
                    target=self._worker_loop,
                    args=(worker_id,),
                    daemon=True,
                    name=f"oncoflow-pq-worker-{idx}",
                )
                thread.start()
                self._worker_threads.append(thread)

    def _worker_loop(self, worker_id: str) -> None:
        while not self._stop_event.is_set():
            with self._cond:
                claimed, lease_id = self.claim_next_job(worker_id=worker_id)
                if not claimed or not lease_id:
                    self._cond.wait(timeout=WORKER_IDLE_WAIT_SECONDS)
                    continue
            self.execute_claimed_job(claimed, lease_id)

    def shutdown(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._workers_started = False
            threads = list(self._worker_threads)
            self._worker_threads.clear()
            self._cond.notify_all()
        curr = threading.current_thread()
        for t in threads:
            if t is not curr and t.is_alive():
                t.join(timeout=2.0)

    def recover_unfinished_from_mongodb(self) -> int:
        """
        Scan `rcp_info` across all enabled domains (`APP_ALLOWED_DOMAINS`) on startup
        and re-enqueue any document that was interrupted before `COMPLETED` or `FAILED`.
        """
        recovered = 0
        for domain in self.base_config.enabled_domains_list:
            try:
                domain_conf = self._resolve_domain_config(domain)
                if domain_conf.rcp.display_type != "mongodb":
                    continue
                form_cls = get_domain_mdt_form_cls(domain)
                import inspect
                from pydantic import BaseModel

                clinical_count = sum(
                    1
                    for name, obj in inspect.getmembers(form_cls)
                    if inspect.isclass(obj)
                    and issubclass(obj, BaseModel)
                    and name not in ("default_model", "PatientAdministrative")
                )

                db_client = Mongodb(domain_conf)
                try:
                    unfinished_docs = list(
                        db_client.database["rcp_info"].find(
                            {
                                "processing_status": {
                                    "$in": [
                                        RCPProcessingStatus.PENDING_ADMIN.value,
                                        RCPProcessingStatus.PROCESSING_ADMIN.value,
                                        RCPProcessingStatus.PENDING_CLINICAL.value,
                                        RCPProcessingStatus.PROCESSING_CLINICAL.value,
                                    ]
                                }
                            }
                        )
                    )
                finally:
                    db_client.close()

                for doc in unfinished_docs:
                    filename = doc.get("file")
                    if not filename:
                        continue
                    status = doc.get("processing_status")
                    if status in (
                        RCPProcessingStatus.PENDING_ADMIN.value,
                        RCPProcessingStatus.PROCESSING_ADMIN.value,
                    ):
                        res = self.enqueue_import_file(
                            filename=filename,
                            target_patient_id=doc.get("target_patient_id")
                            or doc.get("patient_id"),
                            include_clinical=True,
                            total_clinical_models=max(1, clinical_count),
                            domain=domain,
                        )
                    else:
                        res = self.enqueue_rcp_rerun(
                            filename=filename,
                            model_name=None,
                            total_clinical_models=max(1, clinical_count),
                            domain=domain,
                        )
                    if not res.get("already_queued"):
                        recovered += 1
            except Exception as exc:
                self.logger.warning(
                    f"Could not recover unfinished jobs for domain '{domain}': {exc}"
                )
        return recovered


# ----------------------------------------------------------------------
# Global In-Process Singleton & Domain-Scoped / HTTP Broker Adapter
# ----------------------------------------------------------------------

_GLOBAL_MANAGER_LOCK = threading.Lock()
_GLOBAL_MANAGER: InMemoryQueueManager | None = None


def get_global_queue_manager(
    config: AppConfig | None = None, auto_start_workers: bool = False
) -> InMemoryQueueManager:
    global _GLOBAL_MANAGER
    with _GLOBAL_MANAGER_LOCK:
        if _GLOBAL_MANAGER is None:
            _GLOBAL_MANAGER = InMemoryQueueManager(
                base_config=config or AppConfig(),
                auto_start_workers=auto_start_workers,
            )
        elif auto_start_workers:
            _GLOBAL_MANAGER.start_workers()
        return _GLOBAL_MANAGER


def reset_global_queue_manager(
    config: AppConfig | None = None, auto_start_workers: bool = False
) -> InMemoryQueueManager:
    """Reset the in-memory queue singleton (useful in tests or full admin reset)."""
    global _GLOBAL_MANAGER
    with _GLOBAL_MANAGER_LOCK:
        if _GLOBAL_MANAGER is not None:
            _GLOBAL_MANAGER.shutdown()
        _GLOBAL_MANAGER = InMemoryQueueManager(
            base_config=config or AppConfig(),
            auto_start_workers=auto_start_workers,
        )
        return _GLOBAL_MANAGER


class QueueBroker:
    """
    Domain-scoped queue broker facade.
    - When `config.queue.api_url` is set and reachable, delegates to the central
      cross-domain FastAPI container (`oncoflow-api`) via HTTP (`httpx`).
    - Otherwise, delegates directly to the in-process `InMemoryQueueManager`
      (`queue.PriorityQueue`).
    """

    def __init__(
        self,
        config: AppConfig | None = None,
        manager: InMemoryQueueManager | None = None,
    ) -> None:
        self.config = config or AppConfig()
        self.domain = (self.config.domain or "oncology").strip().lower()
        self.api_url = (self.config.queue.api_url or "").strip().rstrip("/")
        self._manager = manager or get_global_queue_manager(self.config)
        self._http_client: httpx.Client | None = None

    def _use_remote_api(self) -> bool:
        return bool(self.api_url)

    def _auth_headers(self) -> dict[str, str]:
        token = getattr(self.config, "api_token", None)
        if token is not None:
            return {"Authorization": f"Bearer {token.get_secret_value()}"}
        return {}

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(headers=self._auth_headers())
        return self._http_client

    def close(self) -> None:
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    # --- Delegation Methods ---

    def get_active_jobs_for_file(self, filename: str) -> list[dict[str, Any]]:
        if self._use_remote_api():
            try:
                resp = httpx.get(
                    f"{self.api_url}/api/v1/queue/jobs",
                    params={"domain": self.domain, "filename": filename},
                    headers=self._auth_headers(),
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    return [
                        j
                        for j in resp.json()
                        if j.get("status")
                        in (JobStatus.PENDING.value, JobStatus.PROCESSING.value)
                    ]
            except Exception:
                pass
        return self._manager.get_active_jobs_for_file(filename, domain=self.domain)

    def has_active_job(
        self,
        filename: str,
        job_types: list[str] | None = None,
        model_name: str | None = None,
    ) -> bool:
        return self._manager.has_active_job(
            filename=filename,
            job_types=job_types,
            model_name=model_name,
            domain=self.domain,
        )

    def enqueue_import_file(
        self,
        filename: str,
        target_patient_id: str | None = None,
        batch_id: str | None = None,
        include_clinical: bool = True,
        total_clinical_models: int = 1,
    ) -> dict[str, Any]:
        if self._use_remote_api():
            try:
                resp = httpx.post(
                    f"{self.api_url}/api/v1/queue/enqueue-import",
                    params={"domain": self.domain},
                    json={
                        "filename": filename,
                        "target_patient_id": target_patient_id,
                        "batch_id": batch_id,
                        "include_clinical": include_clinical,
                        "total_clinical_models": total_clinical_models,
                    },
                    headers=self._auth_headers(),
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                # Remote API unreachable in standalone dev mode -> start local PriorityQueue worker thread automatically
                self._manager.start_workers()
        return self._manager.enqueue_import_file(
            filename=filename,
            target_patient_id=target_patient_id,
            batch_id=batch_id,
            include_clinical=include_clinical,
            total_clinical_models=total_clinical_models,
            domain=self.domain,
        )

    def enqueue_rcp_rerun(
        self,
        filename: str,
        model_name: str | None = None,
        total_clinical_models: int = 1,
    ) -> dict[str, Any]:
        if self._use_remote_api():
            try:
                resp = httpx.post(
                    f"{self.api_url}/api/v1/queue/rerun",
                    params={"domain": self.domain},
                    json={
                        "filename": filename,
                        "model_name": model_name,
                        "total_clinical_models": total_clinical_models,
                    },
                    headers=self._auth_headers(),
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                # Remote API unreachable in standalone dev mode -> start local PriorityQueue worker thread automatically
                self._manager.start_workers()
        return self._manager.enqueue_rcp_rerun(
            filename=filename,
            model_name=model_name,
            total_clinical_models=total_clinical_models,
            domain=self.domain,
        )

    def acquire_gpu_lease(
        self, worker_id: str, job_id: str, filename: str
    ) -> str | None:
        return self._manager.acquire_gpu_lease(
            worker_id=worker_id,
            job_id=job_id,
            filename=filename,
            domain=self.domain,
        )

    def refresh_gpu_lease(self, lease_id: str, job_id: str | None = None) -> bool:
        return self._manager.refresh_gpu_lease(lease_id=lease_id, job_id=job_id)

    def release_gpu_lease(
        self,
        lease_id: str | None = None,
        job_id: str | None = None,
        domain: str | None = None,
        force_all: bool = False,
    ) -> int:
        if self._use_remote_api():
            try:
                params: dict[str, Any] = {
                    "force_all": force_all,
                    "domain": domain or self.domain,
                }
                if lease_id:
                    params["lease_id"] = lease_id
                if job_id:
                    params["job_id"] = job_id
                resp = httpx.delete(
                    f"{self.api_url}/api/v1/queue/locks",
                    params=params,
                    headers=self._auth_headers(),
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    return int(resp.json().get("released_locks", 0))
            except Exception:
                pass
        return self._manager.release_gpu_lease(
            lease_id=lease_id,
            job_id=job_id,
            domain=domain,
            force_all=force_all,
        )

    def get_all_gpu_leases(self) -> list[dict[str, Any]]:
        if self._use_remote_api():
            try:
                resp = httpx.get(
                    f"{self.api_url}/api/v1/queue/locks",
                    headers=self._auth_headers(),
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass
        return self._manager.get_all_gpu_leases()

    def claim_next_job(
        self, worker_id: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        return self._manager.claim_next_job(worker_id=worker_id, domain=self.domain)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self._manager.get_job(job_id)

    def update_job_progress(
        self,
        job_id: str,
        current_step: str,
        completed_models: list[str] | None = None,
        progress_pct: float | None = None,
        resolved_patient_id: str | None = None,
    ) -> dict[str, Any] | None:
        return self._manager.update_job_progress(
            job_id=job_id,
            current_step=current_step,
            completed_models=completed_models,
            progress_pct=progress_pct,
            resolved_patient_id=resolved_patient_id,
        )

    def complete_job(
        self,
        job_id: str,
        lease_id: str | None = None,
        resolved_patient_id: str | None = None,
        current_step: str = "Terminé",
    ) -> dict[str, Any] | None:
        return self._manager.complete_job(
            job_id=job_id,
            lease_id=lease_id,
            resolved_patient_id=resolved_patient_id,
            current_step=current_step,
        )

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        lease_id: str | None = None,
    ) -> dict[str, Any] | None:
        return self._manager.fail_job(
            job_id=job_id, error_message=error_message, lease_id=lease_id
        )

    def get_queue_stats(self, cross_domain: bool = False) -> dict[str, Any]:
        target_domain = None if cross_domain else self.domain
        if self._use_remote_api():
            try:
                params = {"domain": target_domain} if target_domain else {}
                resp = httpx.get(
                    f"{self.api_url}/api/v1/queue/stats",
                    params=params,
                    headers=self._auth_headers(),
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass
        return self._manager.get_queue_stats(domain=target_domain)

    def get_queue_jobs(
        self,
        status: str | None = None,
        batch_id: str | None = None,
        limit: int = 100,
        cross_domain: bool = False,
    ) -> list[dict[str, Any]]:
        target_domain = None if cross_domain else self.domain
        if self._use_remote_api():
            try:
                params: dict[str, Any] = {"limit": limit}
                if target_domain:
                    params["domain"] = target_domain
                if status:
                    params["status"] = status
                if batch_id:
                    params["batch_id"] = batch_id
                resp = httpx.get(
                    f"{self.api_url}/api/v1/queue/jobs",
                    params=params,
                    headers=self._auth_headers(),
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass
        return self._manager.get_queue_jobs(
            status=status,
            batch_id=batch_id,
            limit=limit,
            domain=target_domain,
        )

    def cancel_or_delete_job(self, job_id: str) -> bool:
        if self._use_remote_api():
            try:
                resp = httpx.delete(
                    f"{self.api_url}/api/v1/queue/jobs/{job_id}",
                    headers=self._auth_headers(),
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
        return self._manager.cancel_or_delete_job(job_id)

    def delete_jobs_for_file(self, filename: str) -> int:
        return self._manager.delete_jobs_for_file(filename=filename, domain=self.domain)

    def retry_job(self, job_id: str) -> dict[str, Any] | None:
        if self._use_remote_api():
            try:
                resp = httpx.post(
                    f"{self.api_url}/api/v1/queue/jobs/{job_id}/retry",
                    headers=self._auth_headers(),
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass
        return self._manager.retry_job(job_id)

    def clean_queue(
        self, mode: str = "completed", cross_domain: bool = False
    ) -> dict[str, Any]:
        target_domain = None if cross_domain else self.domain
        if self._use_remote_api():
            try:
                params = {"domain": target_domain} if target_domain else {}
                resp = httpx.post(
                    f"{self.api_url}/api/v1/queue/clean",
                    params=params,
                    json={"mode": mode},
                    headers=self._auth_headers(),
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass
        return self._manager.clean_queue(mode=mode, domain=target_domain)


# Backward-compatible alias
SqliteQueueBroker = QueueBroker
