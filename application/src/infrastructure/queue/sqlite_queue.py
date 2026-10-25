from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import os
import sqlite3

from src.application.config import AppConfig
from src.domain.worker.queue_job import (
    GpuLease,
    JobPriority,
    JobStatus,
    JobType,
    QueueJob,
    RCPProcessingStatus,
)
from src.infrastructure.documents.mongodb import Mongodb

_DATETIME_FIELDS = (
    "created_at",
    "started_at",
    "completed_at",
    "heartbeat_at",
    "acquired_at",
)


def _dt_to_str(val: datetime | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _str_to_dt(val: str | datetime | None) -> datetime | None:
    if val is None or isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None


class SqliteQueueBroker:
    """
    Infrastructure broker for the 2-wave processing queue and hardware GPU leases,
    backed by SQLite in WAL mode (`PRAGMA journal_mode=WAL`) on a shared volume.

    Provides ACID atomic transactions (`BEGIN IMMEDIATE`) across domain workers
    (`oncology`, `sma`) and UI containers without requiring an external broker container
    or polluting `Mongodb`.
    """

    def __init__(self, config: AppConfig, sync_mongodb: bool = True) -> None:
        self.config = config
        self.sync_mongodb = sync_mongodb
        self.domain = getattr(config, "domain", "oncology")
        queue_cfg = getattr(config, "queue", None)
        self.db_path = getattr(
            queue_cfg, "db_path", "./ressources/queue/oncoflow_queue.db"
        )
        self.batch_size = int(getattr(queue_cfg, "batch_size", 1))
        self.global_gpu_lock = bool(getattr(queue_cfg, "global_gpu_lock", True))
        self.lease_ttl_seconds = int(getattr(queue_cfg, "lease_ttl_seconds", 300))
        self.max_retries = int(getattr(queue_cfg, "max_retries", 2))

        if self.db_path != ":memory:":
            parent_dir = os.path.dirname(os.path.abspath(self.db_path))
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

        self.conn = sqlite3.connect(
            self.db_path,
            timeout=10.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS queue_jobs (
                job_id TEXT PRIMARY KEY,
                batch_id TEXT,
                domain TEXT NOT NULL,
                filename TEXT NOT NULL,
                target_patient_id TEXT,
                resolved_patient_id TEXT,
                patient_label TEXT,
                job_type TEXT NOT NULL,
                model_name TEXT,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL,
                depends_on_job_id TEXT,
                worker_id TEXT,
                lease_id TEXT,
                current_step TEXT,
                completed_models TEXT NOT NULL DEFAULT '[]',
                total_models INTEGER NOT NULL DEFAULT 1,
                progress_pct REAL NOT NULL DEFAULT 0.0,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 2,
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                heartbeat_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_queue_jobs_domain_status_prio
                ON queue_jobs (domain, status, priority DESC, created_at ASC);

            CREATE INDEX IF NOT EXISTS idx_queue_jobs_domain_filename
                ON queue_jobs (domain, filename, status);

            CREATE TABLE IF NOT EXISTS gpu_leases (
                lease_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                job_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                job_type TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                heartbeat_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_gpu_leases_domain
                ON gpu_leases (domain, acquired_at ASC);
            """
        )

    @contextmanager
    def _atomic_transaction(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.execute("COMMIT")
        except Exception:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    @staticmethod
    def _row_to_job_dict(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        raw_models = d.get("completed_models")
        if isinstance(raw_models, str):
            try:
                d["completed_models"] = json.loads(raw_models)
            except Exception:
                d["completed_models"] = []
        for dt_field in _DATETIME_FIELDS:
            if dt_field in d:
                d[dt_field] = _str_to_dt(d[dt_field])
        return d

    @staticmethod
    def _row_to_lease_dict(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        for dt_field in ("acquired_at", "heartbeat_at"):
            if dt_field in d:
                d[dt_field] = _str_to_dt(d[dt_field])
        return d

    def _sync_rcp_info(self, filename: str, update_data: dict) -> None:
        """Synchronizes processing_status and progress fields to MongoDB rcp_info."""
        if not self.sync_mongodb:
            return
        if (
            getattr(getattr(self.config, "rcp", None), "display_type", None)
            != "mongodb"
        ):
            return
        try:
            db = Mongodb(self.config)
            try:
                db.update_doc(
                    collection="rcp_info",
                    filter={"file": filename},
                    upsertable_data=update_data,
                )
            finally:
                db.close()
        except Exception:
            pass

    def _get_rcp_info(self, filename: str) -> dict:
        if not self.sync_mongodb:
            return {}
        if (
            getattr(getattr(self.config, "rcp", None), "display_type", None)
            != "mongodb"
        ):
            return {}
        try:
            db = Mongodb(self.config)
            try:
                return db.get_document("rcp_info", {"file": filename}) or {}
            finally:
                db.close()
        except Exception:
            return {}

    def _insert_job(self, job: QueueJob) -> dict:
        d = job.model_dump(mode="python")
        d["job_type"] = job.job_type.value
        d["status"] = job.status.value
        self.conn.execute(
            """
            INSERT OR REPLACE INTO queue_jobs (
                job_id, batch_id, domain, filename, target_patient_id,
                resolved_patient_id, patient_label, job_type, model_name,
                status, priority, depends_on_job_id, worker_id, lease_id,
                current_step, completed_models, total_models, progress_pct,
                attempts, max_retries, error_message, created_at,
                started_at, completed_at, heartbeat_at
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?
            )
            """,
            (
                d["job_id"],
                d["batch_id"],
                d["domain"],
                d["filename"],
                d["target_patient_id"],
                d["resolved_patient_id"],
                d["patient_label"],
                d["job_type"],
                d["model_name"],
                d["status"],
                d["priority"],
                d["depends_on_job_id"],
                d["worker_id"],
                d["lease_id"],
                d["current_step"],
                json.dumps(d["completed_models"]),
                d["total_models"],
                d["progress_pct"],
                d["attempts"],
                d["max_retries"],
                d["error_message"],
                _dt_to_str(d["created_at"]),
                _dt_to_str(d["started_at"]),
                _dt_to_str(d["completed_at"]),
                _dt_to_str(d["heartbeat_at"]),
            ),
        )
        return d

    # ─── Query & Deduplication Methods ──────────────────────────────────────────

    def get_job(self, job_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM queue_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return self._row_to_job_dict(row)

    def get_active_jobs_for_file(self, filename: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM queue_jobs
            WHERE domain = ? AND filename = ? AND status IN (?, ?)
            ORDER BY priority DESC, created_at ASC
            """,
            (
                self.domain,
                filename,
                JobStatus.PENDING.value,
                JobStatus.PROCESSING.value,
            ),
        ).fetchall()
        return [self._row_to_job_dict(r) for r in rows if r is not None]

    def has_active_job(
        self,
        filename: str,
        job_type: str | None = None,
        model_name: str | None = None,
    ) -> bool:
        active_jobs = self.get_active_jobs_for_file(filename)
        if not active_jobs:
            return False
        if job_type is None:
            return True
        for job in active_jobs:
            jt = job.get("job_type")
            if job_type == JobType.SINGLE_MODEL.value:
                if jt in (JobType.WAVE1_ADMIN.value, JobType.WAVE2_CLINICAL.value):
                    return True
                if (
                    jt == JobType.SINGLE_MODEL.value
                    and job.get("model_name") == model_name
                ):
                    return True
            elif jt == job_type:
                return True
        return False

    # ─── Enqueue Methods (2-Wave Pipeline & Reruns) ─────────────────────────────

    def enqueue_import_file(
        self,
        filename: str,
        target_patient_id: str | None = None,
        batch_id: str | None = None,
        include_clinical: bool = True,
        total_clinical_models: int = 8,
    ) -> dict:
        with self._atomic_transaction():
            active_jobs = self.get_active_jobs_for_file(filename)
            has_wave_job = any(
                j.get("job_type")
                in (JobType.WAVE1_ADMIN.value, JobType.WAVE2_CLINICAL.value)
                for j in active_jobs
            )
            if has_wave_job:
                return {
                    "already_queued": True,
                    "filename": filename,
                    "jobs": active_jobs,
                }

            now = datetime.now()
            wave1 = QueueJob(
                batch_id=batch_id,
                domain=self.domain,
                filename=filename,
                target_patient_id=target_patient_id,
                job_type=JobType.WAVE1_ADMIN,
                status=JobStatus.PENDING,
                priority=JobPriority.WAVE1_ADMIN_IMPORT,
                current_step="En attente d'identification du patient",
                total_models=1,
                max_retries=self.max_retries,
                created_at=now,
            )
            w1_dict = self._insert_job(wave1)
            created_jobs = [w1_dict]

            if include_clinical:
                wave2 = QueueJob(
                    batch_id=batch_id,
                    domain=self.domain,
                    filename=filename,
                    target_patient_id=target_patient_id,
                    job_type=JobType.WAVE2_CLINICAL,
                    status=JobStatus.PENDING,
                    priority=JobPriority.WAVE2_CLINICAL_IMPORT,
                    depends_on_job_id=wave1.job_id,
                    current_step="En attente de l'analyse clinique",
                    total_models=max(1, total_clinical_models),
                    max_retries=self.max_retries,
                    created_at=now,
                )
                created_jobs.append(self._insert_job(wave2))

        rcp_init = {
            "file": filename,
            "processing_status": RCPProcessingStatus.PENDING_ADMIN.value,
            "processing_step": "En attente de traitement",
            "processing_progress_pct": 0.0,
            "ui_date": now,
        }
        if target_patient_id:
            rcp_init["patient_id"] = target_patient_id
        self._sync_rcp_info(filename, rcp_init)

        return {
            "already_queued": False,
            "filename": filename,
            "jobs": created_jobs,
        }

    def enqueue_rcp_rerun(
        self,
        filename: str,
        model_name: str | None = None,
        total_clinical_models: int = 8,
    ) -> dict:
        now = datetime.now()

        if model_name is None:
            existing_rcp = self._get_rcp_info(filename)
            target_pid = existing_rcp.get("patient_id")

            with self._atomic_transaction():
                active_jobs = self.get_active_jobs_for_file(filename)
                if active_jobs:
                    has_wave_or_running = any(
                        j.get("job_type")
                        in (JobType.WAVE1_ADMIN.value, JobType.WAVE2_CLINICAL.value)
                        or j.get("status") == JobStatus.PROCESSING.value
                        for j in active_jobs
                    )
                    if has_wave_or_running:
                        return {
                            "already_queued": True,
                            "filename": filename,
                            "model_name": None,
                            "jobs": active_jobs,
                        }
                    self.conn.execute(
                        """
                        UPDATE queue_jobs
                        SET status = ?, completed_at = ?, current_step = ?
                        WHERE domain = ? AND filename = ? AND job_type = ? AND status = ?
                        """,
                        (
                            JobStatus.CANCELLED.value,
                            _dt_to_str(now),
                            "Remplacé par une relance complète",
                            self.domain,
                            filename,
                            JobType.SINGLE_MODEL.value,
                            JobStatus.PENDING.value,
                        ),
                    )

                wave1 = QueueJob(
                    domain=self.domain,
                    filename=filename,
                    target_patient_id=target_pid,
                    job_type=JobType.WAVE1_ADMIN,
                    status=JobStatus.PENDING,
                    priority=JobPriority.WAVE1_ADMIN_RERUN,
                    current_step="En attente d'identification du patient",
                    total_models=1,
                    max_retries=self.max_retries,
                    created_at=now,
                )
                w1_dict = self._insert_job(wave1)

                wave2 = QueueJob(
                    domain=self.domain,
                    filename=filename,
                    target_patient_id=target_pid,
                    job_type=JobType.WAVE2_CLINICAL,
                    status=JobStatus.PENDING,
                    priority=JobPriority.WAVE2_CLINICAL_RERUN,
                    depends_on_job_id=wave1.job_id,
                    current_step="En attente de l'analyse clinique",
                    total_models=max(1, total_clinical_models),
                    max_retries=self.max_retries,
                    created_at=now,
                )
                w2_dict = self._insert_job(wave2)

            self._sync_rcp_info(
                filename,
                {
                    "processing_status": (
                        RCPProcessingStatus.PENDING_CLINICAL.value
                        if existing_rcp.get("PatientAdministrative")
                        else RCPProcessingStatus.PENDING_ADMIN.value
                    ),
                    "processing_step": "En attente de traitement",
                    "processing_progress_pct": 0.0,
                },
            )
            return {
                "already_queued": False,
                "filename": filename,
                "model_name": None,
                "jobs": [w1_dict, w2_dict],
            }

        with self._atomic_transaction():
            if self.has_active_job(
                filename,
                job_type=JobType.SINGLE_MODEL.value,
                model_name=model_name,
            ):
                return {
                    "already_queued": True,
                    "filename": filename,
                    "model_name": model_name,
                    "jobs": self.get_active_jobs_for_file(filename),
                }

            single_job = QueueJob(
                domain=self.domain,
                filename=filename,
                job_type=JobType.SINGLE_MODEL,
                model_name=model_name,
                status=JobStatus.PENDING,
                priority=(
                    JobPriority.WAVE1_ADMIN_RERUN
                    if model_name == "PatientAdministrative"
                    else JobPriority.SINGLE_MODEL_RERUN
                ),
                current_step="En attente de traitement",
                total_models=1,
                max_retries=self.max_retries,
                created_at=now,
            )
            s_dict = self._insert_job(single_job)

        return {
            "already_queued": False,
            "filename": filename,
            "model_name": model_name,
            "jobs": [s_dict],
        }

    # ─── GPU Leases & Stale Recovery ────────────────────────────────────────────

    def cleanup_expired_gpu_leases(self, ttl_seconds: int | None = None) -> int:
        ttl = self.lease_ttl_seconds if ttl_seconds is None else ttl_seconds
        cutoff = _dt_to_str(datetime.now() - timedelta(seconds=ttl))
        cur = self.conn.execute(
            "DELETE FROM gpu_leases WHERE heartbeat_at < ?", (cutoff,)
        )
        return cur.rowcount

    def recover_stale_jobs(self, ttl_seconds: int | None = None) -> int:
        ttl = self.lease_ttl_seconds if ttl_seconds is None else ttl_seconds
        cutoff = _dt_to_str(datetime.now() - timedelta(seconds=ttl))
        rows = self.conn.execute(
            """
            SELECT * FROM queue_jobs
            WHERE domain = ? AND status = ? AND heartbeat_at < ?
            """,
            (self.domain, JobStatus.PROCESSING.value, cutoff),
        ).fetchall()

        recovered = 0
        now_str = _dt_to_str(datetime.now())
        for row in rows:
            job = self._row_to_job_dict(row)
            if not job:
                continue
            job_id = job["job_id"]
            filename = job["filename"]
            if job.get("lease_id"):
                self.release_gpu_lease(lease_id=job["lease_id"])

            if int(job.get("attempts", 1)) <= int(job.get("max_retries", 2)):
                self.conn.execute(
                    """
                    UPDATE queue_jobs
                    SET status = ?, worker_id = NULL, lease_id = NULL, current_step = ?
                    WHERE job_id = ?
                    """,
                    (JobStatus.PENDING.value, "En attente de reprise", job_id),
                )
            else:
                self.conn.execute(
                    """
                    UPDATE queue_jobs
                    SET status = ?, worker_id = NULL, lease_id = NULL,
                        completed_at = ?, current_step = ?, error_message = ?
                    WHERE job_id = ?
                    """,
                    (
                        JobStatus.FAILED.value,
                        now_str,
                        "Échec (délai dépassé)",
                        "Tâche interrompue (délai de verrou dépassé).",
                        job_id,
                    ),
                )
                self._sync_rcp_info(
                    filename,
                    {
                        "processing_status": RCPProcessingStatus.FAILED.value,
                        "processing_step": "Échec du traitement",
                    },
                )
            recovered += 1
        return recovered

    def get_all_gpu_leases(self, domain: str | None = None) -> list[dict]:
        if domain:
            rows = self.conn.execute(
                "SELECT * FROM gpu_leases WHERE domain = ? ORDER BY acquired_at ASC",
                (domain,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM gpu_leases ORDER BY acquired_at ASC"
            ).fetchall()
        return [self._row_to_lease_dict(r) for r in rows if r is not None]

    def acquire_gpu_lease(
        self,
        worker_id: str,
        job_id: str,
        filename: str,
        job_type: str,
    ) -> dict | None:
        self.cleanup_expired_gpu_leases()
        with self._atomic_transaction():
            if self.global_gpu_lock:
                count_row = self.conn.execute(
                    "SELECT COUNT(*) AS cnt FROM gpu_leases"
                ).fetchone()
            else:
                count_row = self.conn.execute(
                    "SELECT COUNT(*) AS cnt FROM gpu_leases WHERE domain = ?",
                    (self.domain,),
                ).fetchone()

            if count_row and int(count_row["cnt"]) >= self.batch_size:
                return None

            now = datetime.now()
            lease = GpuLease(
                worker_id=worker_id,
                domain=self.domain,
                job_id=job_id,
                filename=filename,
                job_type=job_type,
                acquired_at=now,
                heartbeat_at=now,
            )
            self.conn.execute(
                """
                INSERT INTO gpu_leases (
                    lease_id, worker_id, domain, job_id, filename,
                    job_type, acquired_at, heartbeat_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lease.lease_id,
                    lease.worker_id,
                    lease.domain,
                    lease.job_id,
                    lease.filename,
                    lease.job_type,
                    _dt_to_str(lease.acquired_at),
                    _dt_to_str(lease.heartbeat_at),
                ),
            )
            return lease.model_dump(mode="python")

    def refresh_gpu_lease(
        self, lease_id: str | None = None, job_id: str | None = None
    ) -> None:
        now_str = _dt_to_str(datetime.now())
        if lease_id:
            self.conn.execute(
                "UPDATE gpu_leases SET heartbeat_at = ? WHERE lease_id = ?",
                (now_str, lease_id),
            )
        if job_id:
            self.conn.execute(
                "UPDATE queue_jobs SET heartbeat_at = ? WHERE job_id = ?",
                (now_str, job_id),
            )

    def release_gpu_lease(
        self,
        lease_id: str | None = None,
        job_id: str | None = None,
        domain: str | None = None,
        force_all: bool = False,
    ) -> int:
        if force_all:
            if domain:
                cur = self.conn.execute(
                    "DELETE FROM gpu_leases WHERE domain = ?", (domain,)
                )
            else:
                cur = self.conn.execute("DELETE FROM gpu_leases")
            return cur.rowcount

        if lease_id:
            cur = self.conn.execute(
                "DELETE FROM gpu_leases WHERE lease_id = ?", (lease_id,)
            )
            return cur.rowcount
        if job_id:
            cur = self.conn.execute(
                "DELETE FROM gpu_leases WHERE job_id = ?", (job_id,)
            )
            return cur.rowcount
        if domain:
            cur = self.conn.execute(
                "DELETE FROM gpu_leases WHERE domain = ?", (domain,)
            )
            return cur.rowcount
        return 0

    # ─── Atomic Job Claiming & Lifecycle ────────────────────────────────────────

    def claim_next_ready_job(self, worker_id: str) -> dict | None:
        """
        Atomically claims the next eligible PENDING job in SQLite using `BEGIN IMMEDIATE`:
        - Propagates FAILED/CANCELLED status from parent jobs (`depends_on_job_id`).
        - Enforces `batch_size` via `gpu_leases`.
        - Yields to other domains if they have a high-priority Wave 1 job pending.
        - Orders by `priority DESC, created_at ASC`.
        """
        self.cleanup_expired_gpu_leases()
        self.recover_stale_jobs()

        with self._atomic_transaction():
            # 1. Propagate parent failure/cancellation to dependent jobs
            now = datetime.now()
            now_str = _dt_to_str(now)
            self.conn.execute(
                """
                UPDATE queue_jobs
                SET status = (
                        SELECT p.status FROM queue_jobs p
                        WHERE p.job_id = queue_jobs.depends_on_job_id
                    ),
                    completed_at = ?,
                    current_step = 'Annulé suite à l''arrêt de l''étape précédente',
                    error_message = (
                        SELECT p.error_message FROM queue_jobs p
                        WHERE p.job_id = queue_jobs.depends_on_job_id
                    )
                WHERE domain = ?
                  AND status = ?
                  AND depends_on_job_id IS NOT NULL
                  AND EXISTS (
                      SELECT 1 FROM queue_jobs p
                      WHERE p.job_id = queue_jobs.depends_on_job_id
                        AND p.status IN (?, ?)
                  )
                """,
                (
                    now_str,
                    self.domain,
                    JobStatus.PENDING.value,
                    JobStatus.FAILED.value,
                    JobStatus.CANCELLED.value,
                ),
            )

            # 2. Check hardware lease capacity
            if self.global_gpu_lock:
                lease_cnt = self.conn.execute(
                    "SELECT COUNT(*) AS cnt FROM gpu_leases"
                ).fetchone()["cnt"]
            else:
                lease_cnt = self.conn.execute(
                    "SELECT COUNT(*) AS cnt FROM gpu_leases WHERE domain = ?",
                    (self.domain,),
                ).fetchone()["cnt"]

            if int(lease_cnt) >= self.batch_size:
                return None

            # 3. Cross-domain Wave 1 priority check
            min_priority = 0
            if self.global_gpu_lock:
                other_wave1 = self.conn.execute(
                    """
                    SELECT 1 FROM queue_jobs
                    WHERE domain != ? AND status = ? AND priority >= ?
                    LIMIT 1
                    """,
                    (
                        self.domain,
                        JobStatus.PENDING.value,
                        JobPriority.SINGLE_MODEL_RERUN,
                    ),
                ).fetchone()
                if other_wave1 is not None:
                    min_priority = JobPriority.SINGLE_MODEL_RERUN

            # 4. Select highest-priority ready job whose parent (if any) is COMPLETED
            cand_row = self.conn.execute(
                """
                SELECT j.*
                FROM queue_jobs j
                LEFT JOIN queue_jobs p ON j.depends_on_job_id = p.job_id
                WHERE j.domain = ?
                  AND j.status = ?
                  AND j.priority >= ?
                  AND (j.depends_on_job_id IS NULL OR p.status = ?)
                  AND NOT EXISTS (
                      SELECT 1 FROM queue_jobs r
                      WHERE r.domain = j.domain
                        AND r.filename = j.filename
                        AND r.status = ?
                  )
                ORDER BY j.priority DESC, j.created_at ASC
                LIMIT 1
                """,
                (
                    self.domain,
                    JobStatus.PENDING.value,
                    min_priority,
                    JobStatus.COMPLETED.value,
                    JobStatus.PROCESSING.value,
                ),
            ).fetchone()

            if cand_row is None:
                return None

            cand_id = cand_row["job_id"]
            fname = cand_row["filename"]
            jtype = cand_row["job_type"]

            lease = GpuLease(
                worker_id=worker_id,
                domain=self.domain,
                job_id=cand_id,
                filename=fname,
                job_type=jtype,
                acquired_at=now,
                heartbeat_at=now,
            )
            self.conn.execute(
                """
                INSERT INTO gpu_leases (
                    lease_id, worker_id, domain, job_id, filename,
                    job_type, acquired_at, heartbeat_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lease.lease_id,
                    lease.worker_id,
                    lease.domain,
                    lease.job_id,
                    lease.filename,
                    lease.job_type,
                    now_str,
                    now_str,
                ),
            )

            self.conn.execute(
                """
                UPDATE queue_jobs
                SET status = ?,
                    worker_id = ?,
                    lease_id = ?,
                    attempts = attempts + 1,
                    started_at = ?,
                    heartbeat_at = ?
                WHERE job_id = ?
                """,
                (
                    JobStatus.PROCESSING.value,
                    worker_id,
                    lease.lease_id,
                    now_str,
                    now_str,
                    cand_id,
                ),
            )

            claimed_row = self.conn.execute(
                "SELECT * FROM queue_jobs WHERE job_id = ?", (cand_id,)
            ).fetchone()
            return self._row_to_job_dict(claimed_row)

    def update_job_step(
        self,
        job_id: str,
        filename: str,
        current_step: str,
        completed_models: list[str] | None = None,
        total_models: int | None = None,
        progress_pct: float | None = None,
        processing_status: str | None = None,
        lease_id: str | None = None,
    ) -> None:
        now_str = _dt_to_str(datetime.now())
        sets = ["current_step = ?", "heartbeat_at = ?"]
        params: list = [current_step, now_str]

        if completed_models is not None:
            sets.append("completed_models = ?")
            params.append(json.dumps(list(completed_models)))
        if total_models is not None:
            sets.append("total_models = ?")
            params.append(int(total_models))
        if progress_pct is not None:
            sets.append("progress_pct = ?")
            params.append(round(float(progress_pct), 1))

        params.append(job_id)
        self.conn.execute(
            f"UPDATE queue_jobs SET {', '.join(sets)} WHERE job_id = ?",
            tuple(params),
        )

        if lease_id:
            self.refresh_gpu_lease(lease_id=lease_id)

        rcp_update: dict = {"processing_step": current_step}
        if progress_pct is not None:
            rcp_update["processing_progress_pct"] = round(float(progress_pct), 1)
        if processing_status is not None:
            rcp_update["processing_status"] = processing_status
        self._sync_rcp_info(filename, rcp_update)

    def complete_job(
        self,
        job_id: str,
        filename: str,
        lease_id: str | None = None,
        resolved_patient_id: str | None = None,
        patient_label: str | None = None,
        next_rcp_status: str | None = None,
    ) -> None:
        now_str = _dt_to_str(datetime.now())
        sets = [
            "status = ?",
            "progress_pct = 100.0",
            "current_step = 'Terminé'",
            "completed_at = ?",
            "heartbeat_at = ?",
            "lease_id = NULL",
            "error_message = NULL",
        ]
        params: list = [JobStatus.COMPLETED.value, now_str, now_str]

        if resolved_patient_id:
            sets.append("resolved_patient_id = ?")
            params.append(resolved_patient_id)
        if patient_label:
            sets.append("patient_label = ?")
            params.append(patient_label)

        params.append(job_id)
        self.conn.execute(
            f"UPDATE queue_jobs SET {', '.join(sets)} WHERE job_id = ?",
            tuple(params),
        )

        if lease_id:
            self.release_gpu_lease(lease_id=lease_id)
        else:
            self.release_gpu_lease(job_id=job_id)

        if next_rcp_status is None:
            remaining = self.get_active_jobs_for_file(filename)
            next_rcp_status = (
                RCPProcessingStatus.PENDING_CLINICAL.value
                if remaining
                else RCPProcessingStatus.COMPLETED.value
            )

        rcp_payload: dict = {
            "processing_status": next_rcp_status,
            "processing_step": (
                "Analyse clinique en attente"
                if next_rcp_status == RCPProcessingStatus.PENDING_CLINICAL.value
                else "Dossier prêt"
            ),
            "processing_progress_pct": (
                0.0
                if next_rcp_status == RCPProcessingStatus.PENDING_CLINICAL.value
                else 100.0
            ),
        }
        if resolved_patient_id:
            rcp_payload["patient_id"] = resolved_patient_id
        self._sync_rcp_info(filename, rcp_payload)

    def fail_job(
        self,
        job_id: str,
        filename: str,
        error_message: str,
        lease_id: str | None = None,
        force_fail: bool = False,
    ) -> str:
        if lease_id:
            self.release_gpu_lease(lease_id=lease_id)
        else:
            self.release_gpu_lease(job_id=job_id)

        job = self.get_job(job_id) or {}
        attempts = int(job.get("attempts", 1))
        max_retries = int(job.get("max_retries", 2))

        if not force_fail and attempts <= max_retries:
            self.conn.execute(
                """
                UPDATE queue_jobs
                SET status = ?, worker_id = NULL, lease_id = NULL,
                    current_step = ?, error_message = ?
                WHERE job_id = ?
                """,
                (
                    JobStatus.PENDING.value,
                    f"Nouvelle tentative en attente ({attempts}/{max_retries})",
                    error_message,
                    job_id,
                ),
            )
            return JobStatus.PENDING.value

        now_str = _dt_to_str(datetime.now())
        self.conn.execute(
            """
            UPDATE queue_jobs
            SET status = ?, worker_id = NULL, lease_id = NULL,
                completed_at = ?, current_step = 'Échec du traitement', error_message = ?
            WHERE job_id = ?
            """,
            (JobStatus.FAILED.value, now_str, error_message, job_id),
        )
        self.conn.execute(
            """
            UPDATE queue_jobs
            SET status = ?, completed_at = ?,
                current_step = 'Annulé suite à l''échec de l''étape précédente',
                error_message = ?
            WHERE depends_on_job_id = ? AND status = ?
            """,
            (
                JobStatus.FAILED.value,
                now_str,
                error_message,
                job_id,
                JobStatus.PENDING.value,
            ),
        )
        self._sync_rcp_info(
            filename,
            {
                "processing_status": RCPProcessingStatus.FAILED.value,
                "processing_step": "Échec du traitement",
            },
        )
        return JobStatus.FAILED.value

    # ─── Inspection, Retry & Admin Cleanup ──────────────────────────────────────

    def get_queue_jobs(
        self,
        status: str | None = None,
        batch_id: str | None = None,
        filename: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        clauses = ["domain = ?"]
        params: list = [self.domain]
        if status:
            clauses.append("status = ?")
            params.append(status)
        if batch_id:
            clauses.append("batch_id = ?")
            params.append(batch_id)
        if filename:
            clauses.append("filename = ?")
            params.append(filename)

        params.append(int(limit))
        rows = self.conn.execute(
            f"""
            SELECT * FROM queue_jobs
            WHERE {" AND ".join(clauses)}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [self._row_to_job_dict(r) for r in rows if r is not None]

    def get_queue_stats(self) -> dict:
        rows = self.conn.execute(
            "SELECT status, filename FROM queue_jobs WHERE domain = ?",
            (self.domain,),
        ).fetchall()
        counts = {
            "total": len(rows),
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        }
        active_files: set[str] = set()
        for r in rows:
            st_val = r["status"]
            if st_val == JobStatus.PENDING.value:
                counts["pending"] += 1
                if r["filename"]:
                    active_files.add(r["filename"])
            elif st_val == JobStatus.PROCESSING.value:
                counts["processing"] += 1
                if r["filename"]:
                    active_files.add(r["filename"])
            elif st_val == JobStatus.COMPLETED.value:
                counts["completed"] += 1
            elif st_val == JobStatus.FAILED.value:
                counts["failed"] += 1
            elif st_val == JobStatus.CANCELLED.value:
                counts["cancelled"] += 1

        leases = self.get_all_gpu_leases()
        counts["active_files_count"] = len(active_files)
        counts["active_locks"] = len(leases)
        counts["batch_size"] = self.batch_size
        return counts

    def retry_job(self, job_id: str) -> dict | None:
        job = self.get_job(job_id)
        if not job:
            return None

        if job.get("lease_id"):
            self.release_gpu_lease(lease_id=job["lease_id"])
        else:
            self.release_gpu_lease(job_id=job_id)

        self.conn.execute(
            """
            UPDATE queue_jobs
            SET status = ?, attempts = 0, worker_id = NULL, lease_id = NULL,
                error_message = NULL, completed_at = NULL, progress_pct = 0.0,
                current_step = 'En attente de traitement'
            WHERE job_id = ?
            """,
            (JobStatus.PENDING.value, job_id),
        )
        self.conn.execute(
            """
            UPDATE queue_jobs
            SET status = ?, attempts = 0, error_message = NULL,
                completed_at = NULL, progress_pct = 0.0,
                current_step = 'En attente de l''analyse clinique'
            WHERE depends_on_job_id = ? AND status IN (?, ?)
            """,
            (
                JobStatus.PENDING.value,
                job_id,
                JobStatus.FAILED.value,
                JobStatus.CANCELLED.value,
            ),
        )

        filename = job.get("filename")
        if filename:
            next_status = (
                RCPProcessingStatus.PENDING_ADMIN.value
                if job.get("job_type") == JobType.WAVE1_ADMIN.value
                else RCPProcessingStatus.PENDING_CLINICAL.value
            )
            self._sync_rcp_info(
                filename,
                {
                    "processing_status": next_status,
                    "processing_step": "En attente de traitement",
                },
            )
        return self.get_job(job_id)

    def cancel_or_delete_job(self, job_id: str, delete_record: bool = True) -> bool:
        job = self.get_job(job_id)
        if not job:
            return False

        if job.get("lease_id"):
            self.release_gpu_lease(lease_id=job["lease_id"])
        else:
            self.release_gpu_lease(job_id=job_id)

        if delete_record:
            self.conn.execute("DELETE FROM queue_jobs WHERE job_id = ?", (job_id,))
        else:
            self.conn.execute(
                """
                UPDATE queue_jobs
                SET status = ?, worker_id = NULL, lease_id = NULL, current_step = 'Annulé'
                WHERE job_id = ?
                """,
                (JobStatus.CANCELLED.value, job_id),
            )

        filename = job.get("filename")
        if filename and not self.get_active_jobs_for_file(filename):
            rcp_doc = self._get_rcp_info(filename)
            if rcp_doc and rcp_doc.get("processing_status") in (
                RCPProcessingStatus.PENDING_ADMIN.value,
                RCPProcessingStatus.PROCESSING_ADMIN.value,
                RCPProcessingStatus.PENDING_CLINICAL.value,
                RCPProcessingStatus.PROCESSING_CLINICAL.value,
            ):
                new_st = (
                    RCPProcessingStatus.COMPLETED.value
                    if rcp_doc.get("PatientAdministrative")
                    else RCPProcessingStatus.FAILED.value
                )
                self._sync_rcp_info(
                    filename,
                    {
                        "processing_status": new_st,
                        "processing_step": "Traitement interrompu",
                    },
                )
        return True

    def delete_jobs_for_file(self, filename: str) -> int:
        active = self.get_active_jobs_for_file(filename)
        for j in active:
            if j.get("lease_id"):
                self.release_gpu_lease(lease_id=j["lease_id"])
            elif j.get("job_id"):
                self.release_gpu_lease(job_id=j["job_id"])
        cur = self.conn.execute(
            "DELETE FROM queue_jobs WHERE domain = ? AND filename = ?",
            (self.domain, filename),
        )
        return cur.rowcount

    def clean_queue(self, mode: str = "all") -> dict:
        affected_jobs = 0
        released_locks = 0

        if mode == "completed":
            cur = self.conn.execute(
                "DELETE FROM queue_jobs WHERE domain = ? AND status IN (?, ?)",
                (
                    self.domain,
                    JobStatus.COMPLETED.value,
                    JobStatus.CANCELLED.value,
                ),
            )
            affected_jobs = cur.rowcount

        elif mode == "failed":
            cur = self.conn.execute(
                "DELETE FROM queue_jobs WHERE domain = ? AND status = ?",
                (self.domain, JobStatus.FAILED.value),
            )
            affected_jobs = cur.rowcount

        elif mode == "retry_failed":
            failed_rows = self.conn.execute(
                "SELECT job_id FROM queue_jobs WHERE domain = ? AND status = ?",
                (self.domain, JobStatus.FAILED.value),
            ).fetchall()
            for r in failed_rows:
                self.retry_job(r["job_id"])
                affected_jobs += 1

        elif mode == "reset_stuck":
            released_locks = self.release_gpu_lease(domain=self.domain, force_all=True)
            cur = self.conn.execute(
                """
                UPDATE queue_jobs
                SET status = ?, attempts = 0, worker_id = NULL, lease_id = NULL,
                    current_step = 'En attente de traitement'
                WHERE domain = ? AND status = ?
                """,
                (
                    JobStatus.PENDING.value,
                    self.domain,
                    JobStatus.PROCESSING.value,
                ),
            )
            affected_jobs = cur.rowcount

        elif mode == "pending":
            pending_rows = self.conn.execute(
                "SELECT job_id FROM queue_jobs WHERE domain = ? AND status = ?",
                (self.domain, JobStatus.PENDING.value),
            ).fetchall()
            for r in pending_rows:
                self.cancel_or_delete_job(r["job_id"], delete_record=True)
                affected_jobs += 1

        elif mode == "all":
            files_rows = self.conn.execute(
                "SELECT DISTINCT filename FROM queue_jobs WHERE domain = ?",
                (self.domain,),
            ).fetchall()
            cur = self.conn.execute(
                "DELETE FROM queue_jobs WHERE domain = ?", (self.domain,)
            )
            affected_jobs = cur.rowcount
            released_locks = self.release_gpu_lease(domain=self.domain, force_all=True)
            for r in files_rows:
                fn = r["filename"]
                rcp_doc = self._get_rcp_info(fn)
                if rcp_doc and rcp_doc.get("processing_status") in (
                    RCPProcessingStatus.PENDING_ADMIN.value,
                    RCPProcessingStatus.PROCESSING_ADMIN.value,
                    RCPProcessingStatus.PENDING_CLINICAL.value,
                    RCPProcessingStatus.PROCESSING_CLINICAL.value,
                ):
                    new_st = (
                        RCPProcessingStatus.COMPLETED.value
                        if rcp_doc.get("PatientAdministrative")
                        else RCPProcessingStatus.FAILED.value
                    )
                    self._sync_rcp_info(
                        fn,
                        {
                            "processing_status": new_st,
                            "processing_step": "File de traitement vidée",
                        },
                    )
        else:
            raise ValueError(f"Unknown clean_queue mode: {mode}")

        return {
            "mode": mode,
            "affected_jobs": affected_jobs,
            "released_locks": released_locks,
        }
