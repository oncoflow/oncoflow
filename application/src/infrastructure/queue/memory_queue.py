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
from src.domain.patient_mdt_form import NonPatientMDTFormError
from src.domain.repositories import QueueJobExecutor
from src.domain.worker import (
    JobPriority,
    JobStatus,
    JobType,
    QueueJob,
    RCPProcessingStatus,
)

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
        executor: QueueJobExecutor | None = None,
    ) -> None:
        self.base_config = base_config or AppConfig()
        self.logger = self.base_config.set_logger("oncoflow.queue")
        self._executor = executor
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

    @property
    def executor(self) -> QueueJobExecutor:
        if self._executor is None:
            from src.application.use_cases.queue_executor import (
                PatientMDTFormQueueJobExecutor,
            )

            self._executor = PatientMDTFormQueueJobExecutor(self.base_config)
        return self._executor

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
        self.executor.on_job_enqueued(
            domain=domain,
            filename=filename,
            status=processing_status,
            extra_fields=extra_fields,
        )

    def _stabilize_rcp_status_for_file(self, domain: str, filename: str) -> None:
        self.executor.stabilize_status(domain=domain, filename=filename)

    @staticmethod
    def _clone_job(job: dict[str, Any]) -> dict[str, Any]:
        cloned = dict(job)
        if isinstance(cloned.get("completed_models"), list):
            cloned["completed_models"] = list(cloned["completed_models"])
        return cloned

    def _get_transitive_dependents_locked(
        self, root_job_id: str
    ) -> list[dict[str, Any]]:
        """Return all direct and transitive dependent jobs of `root_job_id` in BFS order."""
        result: list[dict[str, Any]] = []
        frontier = [root_job_id]
        seen = {root_job_id}
        while frontier:
            parent_id = frontier.pop(0)
            for cand in self._jobs.values():
                cid = cand["job_id"]
                if cid not in seen and cand.get("depends_on_job_id") == parent_id:
                    seen.add(cid)
                    result.append(cand)
                    frontier.append(cid)
        return result

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
        total_expert_models: int = 3,
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
                in (
                    JobType.WAVE1_ADMIN.value,
                    JobType.WAVE2_CLINICAL.value,
                    JobType.WAVE3_EXPERTS.value,
                )
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
                    current_step="En attente de l'extraction clinique",
                    total_models=max(1, total_clinical_models),
                    max_retries=self.base_config.queue.max_retries,
                    created_at=now + timedelta(milliseconds=1),
                ).model_dump(mode="python")
                wave2_job["job_type"] = JobType.WAVE2_CLINICAL.value
                wave2_job["status"] = JobStatus.PENDING.value
                # Stored in _jobs; pushed to _pq automatically once wave1 completes
                self._jobs[wave2_job["job_id"]] = wave2_job
                created_jobs.append(self._clone_job(wave2_job))

                wave3_job = QueueJob(
                    batch_id=batch_id,
                    domain=target_domain,
                    filename=filename,
                    target_patient_id=target_patient_id,
                    job_type=JobType.WAVE3_EXPERTS,
                    status=JobStatus.PENDING,
                    priority=int(JobPriority.WAVE3_EXPERTS_IMPORT),
                    depends_on_job_id=wave2_job["job_id"],
                    current_step="En attente de la concertation d'experts",
                    total_models=max(1, total_expert_models),
                    max_retries=self.base_config.queue.max_retries,
                    created_at=now + timedelta(milliseconds=2),
                ).model_dump(mode="python")
                wave3_job["job_type"] = JobType.WAVE3_EXPERTS.value
                wave3_job["status"] = JobStatus.PENDING.value
                # Stored in _jobs; pushed to _pq automatically once wave2 completes
                self._jobs[wave3_job["job_id"]] = wave3_job
                created_jobs.append(self._clone_job(wave3_job))

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
        total_expert_models: int = 3,
        start_from_wave: int | None = None,
        domain: str | None = None,
        force_replace: bool = True,
        preserve_manual_edits: bool = True,
    ) -> dict[str, Any]:
        target_domain = self._normalize_domain(domain)
        now = datetime.now()

        # Repository check is done before taking the queue lock (never block workers on DB).
        has_admin = (
            self.executor.has_administrative_data(target_domain, filename)
            if not model_name and start_from_wave != 3
            else True
        )

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
                in (
                    JobType.WAVE1_ADMIN.value,
                    JobType.WAVE2_CLINICAL.value,
                    JobType.WAVE3_EXPERTS.value,
                )
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
            if start_from_wave == 3:
                wave3_job = QueueJob(
                    domain=target_domain,
                    filename=filename,
                    job_type=JobType.WAVE3_EXPERTS,
                    status=JobStatus.PENDING,
                    priority=int(JobPriority.WAVE3_EXPERTS_RERUN),
                    current_step="Relance de la concertation d'experts en attente",
                    total_models=max(1, total_expert_models),
                    force_replace=force_replace,
                    preserve_manual_edits=preserve_manual_edits,
                    max_retries=self.base_config.queue.max_retries,
                    created_at=now,
                ).model_dump(mode="python")
                wave3_job["job_type"] = JobType.WAVE3_EXPERTS.value
                wave3_job["status"] = JobStatus.PENDING.value
                self._jobs[wave3_job["job_id"]] = wave3_job
                self._push_to_pq(wave3_job)
                created_jobs.append(self._clone_job(wave3_job))
            else:
                if not has_admin:
                    wave1_job = QueueJob(
                        domain=target_domain,
                        filename=filename,
                        job_type=JobType.WAVE1_ADMIN,
                        status=JobStatus.PENDING,
                        priority=int(JobPriority.WAVE1_ADMIN_IMPORT),
                        current_step="En attente d'identification du patient",
                        total_models=1,
                        force_replace=force_replace,
                        preserve_manual_edits=preserve_manual_edits,
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
                    current_step="Relance de l'extraction clinique en attente",
                    total_models=max(1, total_clinical_models),
                    force_replace=force_replace,
                    preserve_manual_edits=preserve_manual_edits,
                    max_retries=self.base_config.queue.max_retries,
                    created_at=now + timedelta(milliseconds=1),
                ).model_dump(mode="python")
                wave2_job["job_type"] = JobType.WAVE2_CLINICAL.value
                wave2_job["status"] = JobStatus.PENDING.value
                self._jobs[wave2_job["job_id"]] = wave2_job
                if depends_id is None:
                    self._push_to_pq(wave2_job)
                created_jobs.append(self._clone_job(wave2_job))

                wave3_job = QueueJob(
                    domain=target_domain,
                    filename=filename,
                    job_type=JobType.WAVE3_EXPERTS,
                    status=JobStatus.PENDING,
                    priority=int(JobPriority.WAVE3_EXPERTS_RERUN),
                    depends_on_job_id=wave2_job["job_id"],
                    current_step="En attente de la concertation d'experts",
                    total_models=max(1, total_expert_models),
                    force_replace=force_replace,
                    preserve_manual_edits=preserve_manual_edits,
                    max_retries=self.base_config.queue.max_retries,
                    created_at=now + timedelta(milliseconds=2),
                ).model_dump(mode="python")
                wave3_job["job_type"] = JobType.WAVE3_EXPERTS.value
                wave3_job["status"] = JobStatus.PENDING.value
                self._jobs[wave3_job["job_id"]] = wave3_job
                created_jobs.append(self._clone_job(wave3_job))

        self._set_rcp_processing_status(
            target_domain,
            filename,
            RCPProcessingStatus.PENDING_EXPERTS
            if start_from_wave == 3
            else (
                RCPProcessingStatus.PENDING_CLINICAL
                if has_admin
                else RCPProcessingStatus.PENDING_ADMIN
            ),
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
            claimed_job["active_agent"] = None
            claimed_job["current_thinking"] = ""
            claimed_job["thinking_seq"] = 0
            claimed_job["thinking_updated_at"] = None
            self._notify_waiters()
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
            self._notify_waiters()
            return self._clone_job(job)

    def append_job_thinking(
        self,
        job_id: str,
        token: str = "",
        agent_name: str | None = None,
        reset: bool = False,
        run_id: str | None = None,
        lease_id: str | None = None,
        max_chars: int = 32000,
    ) -> dict[str, Any] | None:
        """
        Append live AI reasoning tokens (`<think>` or `reasoning_content`) to a running task
        and wake up any active thinking stream consumers immediately.
        """
        now = datetime.now()
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or self._is_stale_run(job, run_id, lease_id):
                return None
            if agent_name is not None:
                job["active_agent"] = agent_name
            current = "" if reset else str(job.get("current_thinking") or "")
            if token:
                current = current + token
                if len(current) > max_chars:
                    current = current[-max_chars:]
            job["current_thinking"] = current
            job["thinking_seq"] = int(job.get("thinking_seq") or 0) + 1
            job["thinking_updated_at"] = now
            job["heartbeat_at"] = now
            self._notify_waiters()
            return self._clone_job(job)

    @staticmethod
    def _format_thinking_snapshot(job: dict[str, Any] | None) -> dict[str, Any]:
        """Build a normalized thinking payload from a queue job dictionary."""
        if not job:
            return {
                "active": False,
                "job_id": None,
                "domain": None,
                "filename": None,
                "job_type": None,
                "status": None,
                "current_step": None,
                "active_agent": None,
                "current_thinking": "",
                "thinking_seq": 0,
                "progress_pct": None,
                "thinking_updated_at": None,
            }
        status = job.get("status")
        return {
            "active": status == JobStatus.PROCESSING.value,
            "job_id": job.get("job_id"),
            "domain": job.get("domain"),
            "filename": job.get("filename"),
            "job_type": job.get("job_type"),
            "status": status,
            "current_step": job.get("current_step"),
            "active_agent": job.get("active_agent"),
            "current_thinking": str(job.get("current_thinking") or ""),
            "thinking_seq": int(job.get("thinking_seq") or 0),
            "progress_pct": job.get("progress_pct"),
            "thinking_updated_at": job.get("thinking_updated_at"),
        }

    def _find_active_processing_job_locked(
        self, domain: str | None = None
    ) -> dict[str, Any] | None:
        """Return the currently PROCESSING job (most recently active first). Must hold `_lock`."""
        target_domain = domain.strip().lower() if domain else None
        processing_jobs = [
            j
            for j in self._jobs.values()
            if j.get("status") == JobStatus.PROCESSING.value
            and (not target_domain or j.get("domain") == target_domain)
        ]
        if not processing_jobs:
            return None
        processing_jobs.sort(
            key=lambda j: (
                j.get("thinking_updated_at") or j.get("started_at") or datetime.min
            ),
            reverse=True,
        )
        return processing_jobs[0]

    def get_job_thinking(
        self, job_id: str | None = None, domain: str | None = None
    ) -> dict[str, Any]:
        """
        Return the live AI reasoning snapshot for `job_id` or, when omitted,
        for the currently `PROCESSING` task in the queue.
        """
        with self._lock:
            if job_id:
                job = self._jobs.get(job_id)
            else:
                job = self._find_active_processing_job_locked(domain=domain)
            return self._format_thinking_snapshot(job)

    def stream_job_thinking(
        self,
        job_id: str | None = None,
        domain: str | None = None,
        timeout: float = 30.0,
        heartbeat_interval: float = 2.0,
    ):
        """
        Yield live AI reasoning events (`thinking`, `heartbeat`, `done`) for a specific
        `job_id` or for the currently `PROCESSING` task using condition-variable wakeups.
        """
        deadline = datetime.now() + timedelta(seconds=max(0.5, float(timeout)))
        last_seq = -1
        last_text = ""
        last_step = None
        last_agent = None
        tracked_job_id = job_id

        while not self._stop_event.is_set():
            with self._cond:
                job = (
                    self._jobs.get(tracked_job_id)
                    if tracked_job_id
                    else self._find_active_processing_job_locked(domain=domain)
                )
                if job and not tracked_job_id:
                    tracked_job_id = job.get("job_id")

                snap = self._format_thinking_snapshot(job)
                if not job:
                    yield {
                        **snap,
                        "event": "done",
                        "delta": "",
                    }
                    return

                seq = snap["thinking_seq"]
                text = snap["current_thinking"]
                step = snap["current_step"]
                agent = snap["active_agent"]
                status = snap["status"]

                changed = (
                    seq != last_seq
                    or step != last_step
                    or agent != last_agent
                    or status != JobStatus.PROCESSING.value
                )

                if changed:
                    if text.startswith(last_text):
                        delta = text[len(last_text) :]
                    else:
                        delta = text
                    last_seq = seq
                    last_text = text
                    last_step = step
                    last_agent = agent

                    if status != JobStatus.PROCESSING.value:
                        yield {
                            **snap,
                            "event": "done",
                            "delta": delta,
                        }
                        return

                    yield {
                        **snap,
                        "event": "thinking",
                        "delta": delta,
                    }
                    continue

                now = datetime.now()
                if now >= deadline:
                    yield {
                        **snap,
                        "event": "done",
                        "delta": "",
                    }
                    return

                remaining = (deadline - now).total_seconds()
                wait_time = min(max(0.05, heartbeat_interval), max(0.05, remaining))
                self._cond.wait(timeout=wait_time)

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

            # Propagate resolved_patient_id and revive any CANCELLED transitive dependents
            for candidate in self._get_transitive_dependents_locked(job_id):
                if candidate["status"] == JobStatus.CANCELLED.value:
                    candidate["status"] = JobStatus.PENDING.value
                    candidate["error_message"] = None
                    candidate["completed_at"] = None
                    candidate["current_step"] = "En attente de l'étape précédente"
                    self._cancelled_job_ids.discard(candidate["job_id"])
                if resolved_patient_id and not candidate.get("resolved_patient_id"):
                    candidate["resolved_patient_id"] = resolved_patient_id

            # Unlock & push direct dependent jobs into PriorityQueue
            for candidate in self._jobs.values():
                if (
                    candidate.get("depends_on_job_id") == job_id
                    and candidate["status"] == JobStatus.PENDING.value
                ):
                    self._push_to_pq(candidate)

            self.release_gpu_lease(lease_id=lease_id, job_id=job_id)
            self._notify_waiters()
            return self._clone_job(job)

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        lease_id: str | None = None,
        run_id: str | None = None,
        no_retry: bool = False,
        skip_rcp_status_update: bool = False,
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
            if not no_retry and attempts <= max_retries:
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
                job["current_step"] = (
                    "Document refusé (non-RCP)" if no_retry else "Échec du traitement"
                )
                for dep in self._get_transitive_dependents_locked(job_id):
                    if dep["status"] == JobStatus.PENDING.value:
                        dep["status"] = JobStatus.CANCELLED.value
                        dep["completed_at"] = now
                        dep["error_message"] = (
                            "Annulé : le document importé n'est pas une fiche RCP"
                            if no_retry
                            else "Annulé suite à l'échec d'une étape précédente"
                        )
                        dep["current_step"] = "Annulé"
                        self._cancelled_job_ids.add(dep["job_id"])
                if not skip_rcp_status_update:
                    job_to_fail_rcp = (job["domain"], job["filename"])

            self.release_gpu_lease(lease_id=lease_id, job_id=job_id)
            self._notify_waiters()
            result = self._clone_job(job)

        if job_to_fail_rcp:
            self.executor.on_job_failed(
                job_to_fail_rcp[0],
                job_to_fail_rcp[1],
                error_message,
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
            job = self._jobs.get(job_id)
            if not job:
                return False
            deps = self._get_transitive_dependents_locked(job_id)
            self._jobs.pop(job_id, None)
            self._cancelled_job_ids.add(job_id)
            self.release_gpu_lease(job_id=job_id)

            for dep in deps:
                dep_id = dep["job_id"]
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

            # Walk ancestor chain if this job depends on a previous wave
            ancestors: list[dict[str, Any]] = []
            cur_dep_id = job.get("depends_on_job_id")
            while cur_dep_id:
                dep_job = self._jobs.get(cur_dep_id)
                if not dep_job:
                    break
                ancestors.append(dep_job)
                cur_dep_id = dep_job.get("depends_on_job_id")

            uncompleted_ancestors = [
                a for a in ancestors if a["status"] != JobStatus.COMPLETED.value
            ]
            if uncompleted_ancestors:
                # Revive any FAILED or CANCELLED ancestors; push only the earliest uncompleted ancestor
                earliest = uncompleted_ancestors[-1]
                for anc in uncompleted_ancestors:
                    if anc["status"] in (
                        JobStatus.FAILED.value,
                        JobStatus.CANCELLED.value,
                    ):
                        anc_id = anc["job_id"]
                        self.release_gpu_lease(job_id=anc_id)
                        self._cancelled_job_ids.discard(anc_id)
                        self._reset_run_fields(anc)
                        anc["status"] = JobStatus.PENDING.value
                        anc["attempts"] = 0
                        anc["error_message"] = None
                        anc["completed_at"] = None
                        anc["current_step"] = (
                            "Remis en file d'attente"
                            if anc is earliest
                            else "En attente de l'étape précédente"
                        )
                        anc["heartbeat_at"] = now
                if earliest["status"] == JobStatus.PENDING.value:
                    self._push_to_pq(earliest)
                job["current_step"] = "En attente de l'étape précédente"
            else:
                self._push_to_pq(job)

            # Revive any CANCELLED transitive dependents (e.g., Wave 2 and Wave 3 when Wave 1 is retried)
            root_for_dependents = (
                uncompleted_ancestors[-1]["job_id"] if uncompleted_ancestors else job_id
            )
            for cand in self._get_transitive_dependents_locked(root_for_dependents):
                if cand["status"] == JobStatus.CANCELLED.value:
                    self._cancelled_job_ids.discard(cand["job_id"])
                    self._reset_run_fields(cand)
                    cand["status"] = JobStatus.PENDING.value
                    cand["attempts"] = 0
                    cand["error_message"] = None
                    cand["completed_at"] = None
                    cand["current_step"] = "En attente de l'étape précédente"
                    cand["heartbeat_at"] = now

            cloned = self._clone_job(job)

        if cloned["job_type"] == JobType.WAVE1_ADMIN.value:
            target_status = RCPProcessingStatus.PENDING_ADMIN
        elif cloned["job_type"] == JobType.WAVE3_EXPERTS.value:
            target_status = RCPProcessingStatus.PENDING_EXPERTS
        else:
            target_status = RCPProcessingStatus.PENDING_CLINICAL
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
                for r_id in retried_ids:
                    for cand in self._get_transitive_dependents_locked(r_id):
                        if cand["status"] == JobStatus.CANCELLED.value:
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
    # Worker Execution Logic (Wave 1, Wave 2, Wave 3, Single Model)
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
        return self.executor.execute_wave1_admin(job, lease_id, self)

    def _execute_wave2_clinical(self, job: dict[str, Any], lease_id: str) -> None:
        self.executor.execute_wave2_clinical(job, lease_id, self)

    def _execute_wave3_experts(self, job: dict[str, Any], lease_id: str) -> None:
        self.executor.execute_wave3_experts(job, lease_id, self)

    def _execute_single_model(self, job: dict[str, Any], lease_id: str) -> None:
        self.executor.execute_single_model(job, lease_id, self)

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
            elif job_type == JobType.WAVE3_EXPERTS.value:
                self._execute_wave3_experts(job, lease_id)
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
            is_non_mdt_form = isinstance(exc, NonPatientMDTFormError)
            if is_non_mdt_form:
                self.logger.warning(
                    "Job %s rejected (non-PatientMDTForm): %s", job_id, exc
                )
            else:
                self.logger.exception("Job %s failed: %s", job_id, exc)
            self.fail_job(
                job_id=job_id,
                error_message=str(exc),
                lease_id=lease_id,
                run_id=run_id,
                no_retry=is_non_mdt_form,
                skip_rcp_status_update=is_non_mdt_form,
            )
        finally:
            hb_stop.set()
            self._maybe_unload_models_if_idle()

    def _maybe_unload_models_if_idle(self) -> None:
        stats = self.get_queue_stats()
        if stats["pending"] == 0 and stats["processing"] == 0:
            self.executor.on_queue_idle()

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
        return self.executor.recover_unfinished_jobs(self)


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
        total_expert_models: int = 3,
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
                        "total_expert_models": total_expert_models,
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
            total_expert_models=total_expert_models,
            domain=self.domain,
        )

    def enqueue_rcp_rerun(
        self,
        filename: str,
        model_name: str | None = None,
        total_clinical_models: int = 1,
        total_expert_models: int = 3,
        start_from_wave: int | None = None,
        preserve_manual_edits: bool = True,
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
                        "total_expert_models": total_expert_models,
                        "preserve_manual_edits": preserve_manual_edits,
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
            total_expert_models=total_expert_models,
            domain=self.domain,
            start_from_wave=start_from_wave,
            preserve_manual_edits=preserve_manual_edits,
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

    def get_job_thinking(
        self, job_id: str | None = None, cross_domain: bool = False
    ) -> dict[str, Any]:
        """Return live AI reasoning state for a specific job or the active processing job."""
        target_domain = None if cross_domain else self.domain
        if self._use_remote_api():
            try:
                if job_id:
                    url = f"{self.api_url}/api/v1/queue/jobs/{job_id}/thinking"
                    params: dict[str, Any] = {}
                else:
                    url = f"{self.api_url}/api/v1/queue/thinking"
                    params = {"domain": target_domain} if target_domain else {}
                resp = httpx.get(
                    url,
                    params=params,
                    headers=self._auth_headers(),
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass
        return self._manager.get_job_thinking(job_id=job_id, domain=target_domain)

    def stream_job_thinking(
        self,
        job_id: str | None = None,
        cross_domain: bool = False,
        timeout: float = 30.0,
    ):
        """Stream live AI reasoning events (`thinking`, `done`) for the active or specified task."""
        import json

        target_domain = None if cross_domain else self.domain
        if self._use_remote_api():
            try:
                if job_id:
                    url = f"{self.api_url}/api/v1/queue/jobs/{job_id}/thinking/stream"
                    params: dict[str, Any] = {"timeout": timeout}
                else:
                    url = f"{self.api_url}/api/v1/queue/thinking/stream"
                    params = {"timeout": timeout}
                    if target_domain:
                        params["domain"] = target_domain
                with httpx.stream(
                    "GET",
                    url,
                    params=params,
                    headers=self._auth_headers(),
                    timeout=timeout + 5.0,
                ) as resp:
                    if resp.status_code == 200:
                        for line in resp.iter_lines():
                            if line.startswith("data:"):
                                raw = line[5:].strip()
                                if raw:
                                    yield json.loads(raw)
                        return
            except Exception:
                pass
        yield from self._manager.stream_job_thinking(
            job_id=job_id,
            domain=target_domain,
            timeout=timeout,
        )


# Backward-compatible alias
SqliteQueueBroker = QueueBroker
