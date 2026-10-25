from concurrent.futures import Future, ThreadPoolExecutor
import gc
import os
import signal
import socket
import threading

from src.application.app_functions import unload_active_models
from src.application.config import AppConfig
from src.application.patient import process_patient_association
from src.domain.patient_mdt_form import PatientMDTForm
from src.domain.worker.queue_job import JobStatus, JobType, RCPProcessingStatus
from src.infrastructure.queue import SqliteQueueBroker


class DomainQueueWorker:
    """
    Background worker that processes queued RCP tasks in 2 waves:
    - Wave 1 (WAVE1_ADMIN, priority 100): RAG indexing + PatientAdministrative extraction.
    - Wave 2 (WAVE2_CLINICAL, priority 50): Progressive clinical & expert analysis.
    - Single Model (SINGLE_MODEL, priority 90): Targeted section rerun.

    Respects hardware batch capacity (`config.queue.batch_size`) and cross-domain
    GPU leases in `Oncoflow_system.gpu_leases`.
    """

    def __init__(self, config: AppConfig, worker_id: str | None = None) -> None:
        self.config = config
        self.worker_id = (
            worker_id or f"worker_{config.domain}_{socket.gethostname()}_{os.getpid()}"
        )
        self.logger = config.set_logger(
            "oncoflow.worker",
            default_context={
                "domain": config.domain,
                "worker_id": self.worker_id,
                "batch_size": config.queue.batch_size,
            },
        )
        self._stop_event = threading.Event()
        self._had_recent_work = False

    def stop(self) -> None:
        """Signals the worker loop to stop gracefully."""
        self._stop_event.set()

    @staticmethod
    def _is_job_still_active(broker: SqliteQueueBroker, job_id: str) -> bool:
        """
        Checks if the job is still in PROCESSING state in SQLite.
        Allows cooperative cancellation if an administrator cleans the queue or cancels the job.
        """
        doc = broker.get_job(job_id)
        if not doc:
            return False
        return doc.get("status") == JobStatus.PROCESSING.value

    def process_single_job(self, job: dict) -> bool:
        """
        Executes a single claimed job (`WAVE1_ADMIN`, `WAVE2_CLINICAL`, or `SINGLE_MODEL`).
        Returns True on success, False if failed or cancelled.
        """
        job_id = str(job.get("job_id", ""))
        filename = str(job.get("filename", ""))
        job_type = str(job.get("job_type", JobType.WAVE1_ADMIN.value))
        lease_id = job.get("lease_id")
        target_patient_id = job.get("target_patient_id")

        broker = SqliteQueueBroker(self.config)
        form = None
        try:
            if not self._is_job_still_active(broker, job_id):
                self.logger.info(
                    f"Job {job_id} ({filename}) was cancelled before execution."
                )
                if lease_id:
                    broker.release_gpu_lease(lease_id=lease_id)
                return False

            self.logger.info(
                f"Starting job {job_id} on '{filename}' (type={job_type})..."
            )

            # ─── Étape 1 : Indexation documentaire + Identité du patient ────────
            if job_type == JobType.WAVE1_ADMIN.value:
                broker.update_job_step(
                    job_id=job_id,
                    filename=filename,
                    current_step="Identification du patient en cours",
                    completed_models=[],
                    total_models=1,
                    progress_pct=15.0,
                    processing_status=RCPProcessingStatus.PROCESSING_ADMIN.value,
                    lease_id=lease_id,
                )

                form = PatientMDTForm(config=self.config, document=filename)

                if not self._is_job_still_active(broker, job_id):
                    if lease_id:
                        broker.release_gpu_lease(lease_id=lease_id)
                    return False

                broker.update_job_step(
                    job_id=job_id,
                    filename=filename,
                    current_step="Extraction de l'identité du patient",
                    completed_models=[],
                    total_models=1,
                    progress_pct=55.0,
                    processing_status=RCPProcessingStatus.PROCESSING_ADMIN.value,
                    lease_id=lease_id,
                )

                patient = process_patient_association(
                    form=form,
                    target_patient_id=target_patient_id,
                    run_admin_ai=True,
                )

                # Determine if a Wave 2 clinical job is waiting for this file
                active_for_file = broker.get_active_jobs_for_file(filename)
                has_followup_wave2 = any(
                    j.get("job_id") != job_id
                    and j.get("job_type") == JobType.WAVE2_CLINICAL.value
                    for j in active_for_file
                )
                next_status = (
                    RCPProcessingStatus.PENDING_CLINICAL.value
                    if has_followup_wave2
                    else RCPProcessingStatus.COMPLETED.value
                )

                broker.complete_job(
                    job_id=job_id,
                    filename=filename,
                    lease_id=lease_id,
                    resolved_patient_id=patient.patient_id,
                    patient_label=patient.display_label,
                    next_rcp_status=next_status,
                )
                self.logger.info(
                    f"Completed WAVE1_ADMIN job {job_id} for '{filename}' -> patient '{patient.patient_id}'."
                )
                return True

            # ─── Étape 2 : Analyse clinique complète au fil de l'eau ────────────
            elif job_type == JobType.WAVE2_CLINICAL.value:
                form = PatientMDTForm(config=self.config, document=filename)
                clinical_models = [
                    m
                    for m in form.basemodel_list
                    if m.__name__ != "PatientAdministrative"
                ]
                total = max(1, len(clinical_models))
                completed_models: list[str] = []

                broker.update_job_step(
                    job_id=job_id,
                    filename=filename,
                    current_step=f"Analyse clinique en cours (0/{total})",
                    completed_models=completed_models,
                    total_models=total,
                    progress_pct=0.0,
                    processing_status=RCPProcessingStatus.PROCESSING_CLINICAL.value,
                    lease_id=lease_id,
                )

                for idx, model_cls in enumerate(clinical_models):
                    if self._stop_event.is_set() or not self._is_job_still_active(
                        broker, job_id
                    ):
                        self.logger.info(
                            f"Job {job_id} ({filename}) interrupted or cancelled at step {idx + 1}/{total}."
                        )
                        if lease_id:
                            broker.release_gpu_lease(lease_id=lease_id)
                        return False

                    step_label = f"Analyse clinique en cours ({idx + 1}/{total})"
                    broker.update_job_step(
                        job_id=job_id,
                        filename=filename,
                        current_step=step_label,
                        completed_models=completed_models,
                        total_models=total,
                        progress_pct=(idx / total) * 100.0,
                        processing_status=RCPProcessingStatus.PROCESSING_CLINICAL.value,
                        lease_id=lease_id,
                    )

                    # Save each clinical section progressively in MongoDB (upsert=True)
                    form.read_model(model_cls, upsert=True)
                    completed_models.append(model_cls.__name__)

                    broker.update_job_step(
                        job_id=job_id,
                        filename=filename,
                        current_step=step_label,
                        completed_models=completed_models,
                        total_models=total,
                        progress_pct=((idx + 1) / total) * 100.0,
                        processing_status=RCPProcessingStatus.PROCESSING_CLINICAL.value,
                        lease_id=lease_id,
                    )

                broker.complete_job(
                    job_id=job_id,
                    filename=filename,
                    lease_id=lease_id,
                    resolved_patient_id=form.mtd_datas.get("patient_id"),
                    next_rcp_status=RCPProcessingStatus.COMPLETED.value,
                )
                self.logger.info(
                    f"Completed WAVE2_CLINICAL job {job_id} for '{filename}' ({total} sections)."
                )
                return True

            # ─── Relance unitaire d'une rubrique (SINGLE_MODEL) ─────────────────
            elif job_type == JobType.SINGLE_MODEL.value:
                target_model_name = job.get("model_name")
                form = PatientMDTForm(config=self.config, document=filename)
                matched_model = None
                for m in form.basemodel_list:
                    if m.__name__.lower() == str(target_model_name or "").lower():
                        matched_model = m
                        break

                if matched_model is None:
                    raise ValueError(
                        f"Rubrique '{target_model_name}' introuvable pour le domaine '{self.config.domain}'."
                    )

                broker.update_job_step(
                    job_id=job_id,
                    filename=filename,
                    current_step="Mise à jour de la rubrique en cours",
                    completed_models=[],
                    total_models=1,
                    progress_pct=30.0,
                    lease_id=lease_id,
                )

                form.read_model(matched_model, upsert=True)

                broker.complete_job(
                    job_id=job_id,
                    filename=filename,
                    lease_id=lease_id,
                    resolved_patient_id=form.mtd_datas.get("patient_id"),
                )
                self.logger.info(
                    f"Completed SINGLE_MODEL job {job_id} ({matched_model.__name__}) for '{filename}'."
                )
                return True

            else:
                raise ValueError(f"Unsupported job_type: {job_type}")

        except Exception as e:
            self.logger.error(f"Error executing job {job_id} ({filename}): {e}")
            try:
                broker.fail_job(
                    job_id=job_id,
                    filename=filename,
                    error_message=str(e),
                    lease_id=lease_id,
                )
            except Exception as inner_e:
                self.logger.error(
                    f"Failed to record job failure for {job_id}: {inner_e}"
                )
            return False
        finally:
            if form is not None:
                del form
            broker.close()
            gc.collect()

    def run_once(self) -> int:
        """
        Claims up to `batch_size` ready jobs and processes them concurrently
        (e.g. 1 at a time when batch_size=1 on L4, or N in parallel when batch_size=N).
        Returns the number of jobs claimed and processed in this cycle.
        """
        batch_size = max(1, int(self.config.queue.batch_size))
        claimed_jobs: list[dict] = []

        broker = SqliteQueueBroker(self.config)
        try:
            for _ in range(batch_size):
                job = broker.claim_next_ready_job(worker_id=self.worker_id)
                if job is None:
                    break
                claimed_jobs.append(job)
        finally:
            broker.close()

        if not claimed_jobs:
            return 0

        if len(claimed_jobs) == 1:
            self.process_single_job(claimed_jobs[0])
            return 1

        with ThreadPoolExecutor(max_workers=len(claimed_jobs)) as pool:
            futures = [
                pool.submit(self.process_single_job, job) for job in claimed_jobs
            ]
            for fut in futures:
                fut.result()

        return len(claimed_jobs)

    def run_forever(self) -> None:
        """
        Main continuous worker loop with dynamic slot filling up to `batch_size`
        and smart model unloading when the queue becomes empty.
        """
        batch_size = max(1, int(self.config.queue.batch_size))
        poll_interval = float(self.config.queue.poll_interval)
        self.logger.info(
            f"Starting DomainQueueWorker '{self.worker_id}' for domain='{self.config.domain}' "
            f"(batch_size={batch_size}, global_gpu_lock={self.config.queue.global_gpu_lock})..."
        )

        active_futures: set[Future] = set()

        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            while not self._stop_event.is_set():
                try:
                    # Prune completed futures
                    done_futures = {f for f in active_futures if f.done()}
                    for f in done_futures:
                        active_futures.discard(f)
                        try:
                            f.result()
                        except Exception as exc:
                            self.logger.error(
                                f"Worker task raised unexpected error: {exc}"
                            )

                    # Fill available worker slots up to batch_size
                    slots_available = batch_size - len(active_futures)
                    claimed_any = False
                    if slots_available > 0:
                        broker = SqliteQueueBroker(self.config)
                        try:
                            for _ in range(slots_available):
                                if self._stop_event.is_set():
                                    break
                                job = broker.claim_next_ready_job(
                                    worker_id=self.worker_id
                                )
                                if job is None:
                                    break
                                claimed_any = True
                                self._had_recent_work = True
                                fut = executor.submit(self.process_single_job, job)
                                active_futures.add(fut)
                        finally:
                            broker.close()

                    # Smart Model Unload: unload models only when queue is completely idle
                    if not active_futures and not claimed_any and self._had_recent_work:
                        broker = SqliteQueueBroker(self.config)
                        try:
                            stats = broker.get_queue_stats()
                        finally:
                            broker.close()

                        if (
                            stats.get("pending", 0) == 0
                            and stats.get("processing", 0) == 0
                        ):
                            self._had_recent_work = False
                            try:
                                unload_active_models(self.config)
                            except Exception as e:
                                self.logger.warning(
                                    f"Could not unload active models on idle queue: {e}"
                                )

                    if not claimed_any:
                        self._stop_event.wait(timeout=poll_interval)
                except Exception as loop_err:
                    self.logger.error(f"Error in worker main loop: {loop_err}")
                    self._stop_event.wait(timeout=poll_interval)

        self.logger.info(f"DomainQueueWorker '{self.worker_id}' stopped cleanly.")


def run_worker_main() -> None:
    """Entrypoint for running the standalone domain queue worker process."""
    config = AppConfig()
    worker = DomainQueueWorker(config=config)

    def _handle_signal(signum, frame):
        worker.logger.info(f"Received signal {signum}, stopping worker...")
        worker.stop()

    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except ValueError:
        pass

    worker.run_forever()


if __name__ == "__main__":
    run_worker_main()
