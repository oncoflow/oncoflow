import gc
import hashlib
import inspect
import os
import uuid

from pydantic import BaseModel
from slugify import slugify

from src.application.app_functions.llm import unload_active_models
from src.domain.patient_mdt_form import PatientMDTForm
from src.domain.worker.queue_job import JobType
from src.infrastructure.documents.mongodb import Mongodb
from src.infrastructure.queue import SqliteQueueBroker


def get_clinical_models_for_domain() -> list[type[BaseModel]]:
    """
    Returns all clinical Pydantic model classes defined on PatientMDTForm
    (excluding default_model and PatientAdministrative).
    """
    models = []
    for name, obj in inspect.getmembers(PatientMDTForm):
        if (
            inspect.isclass(obj)
            and issubclass(obj, BaseModel)
            and name not in ("default_model", "PatientAdministrative")
        ):
            models.append(obj)
    return models


def enqueue_rcp_batch(
    app_conf,
    files_payload: list[dict],
    run_full_ai: bool = True,
) -> dict:
    """
    Enqueues a batch of uploaded RCP files into the MongoDB processing queue (2-wave pipeline).
    Each item in `files_payload` is a dict: {"filename": str, "patient_id": str | None}.
    Strictly deduplicates files that are already in the queue.
    """
    batch_id = f"batch_{uuid.uuid4().hex[:8]}"
    clinical_count = len(get_clinical_models_for_domain())
    results = []
    enqueued_count = 0
    already_queued_count = 0

    broker = SqliteQueueBroker(app_conf)
    try:
        for item in files_payload:
            filename = item["filename"]
            target_patient_id = item.get("patient_id")
            res = broker.enqueue_import_file(
                filename=filename,
                target_patient_id=target_patient_id,
                batch_id=batch_id,
                include_clinical=run_full_ai,
                total_clinical_models=max(1, clinical_count),
            )
            if res.get("already_queued"):
                already_queued_count += 1
            else:
                enqueued_count += 1
            results.append(res)
    finally:
        broker.close()

    return {
        "batch_id": batch_id,
        "enqueued_count": enqueued_count,
        "already_queued_count": already_queued_count,
        "results": results,
    }


def enqueue_rcp_rerun(
    app_conf,
    filename: str,
    model_name: str | None = None,
) -> dict:
    """
    Enqueues a full RCP rerun (model_name=None) or a single model rerun (model_name=...)
    into the MongoDB processing queue, strictly avoiding duplicates if already queued.
    """
    clinical_count = len(get_clinical_models_for_domain())
    broker = SqliteQueueBroker(app_conf)
    try:
        return broker.enqueue_rcp_rerun(
            filename=filename,
            model_name=model_name,
            total_clinical_models=max(1, clinical_count),
        )
    finally:
        broker.close()


def get_rcp_active_jobs_state(app_conf, filename: str) -> dict:
    """
    Returns the active queue state for `filename`:
    - `has_full_job`: True if WAVE1_ADMIN or WAVE2_CLINICAL is PENDING or PROCESSING
    - `has_any_job`: True if any job (wave or single model) is PENDING or PROCESSING
    - `active_models`: set of model_names with an active SINGLE_MODEL job
    - `current_step`: human-readable label of the currently running step (if any)
    - `jobs`: raw list of active jobs for this file
    """
    if app_conf.rcp.display_type != "mongodb":
        return {
            "has_full_job": False,
            "has_any_job": False,
            "active_models": set(),
            "current_step": None,
            "jobs": [],
        }

    broker = SqliteQueueBroker(app_conf)
    try:
        jobs = broker.get_active_jobs_for_file(filename)
        has_full = False
        active_models: set[str] = set()
        current_step = None
        for j in jobs:
            jt = j.get("job_type")
            if jt in (JobType.WAVE1_ADMIN.value, JobType.WAVE2_CLINICAL.value):
                has_full = True
            elif jt == JobType.SINGLE_MODEL.value and j.get("model_name"):
                active_models.add(j["model_name"])
            if j.get("status") == "PROCESSING" and j.get("current_step"):
                current_step = j.get("current_step")
        if not current_step and jobs:
            current_step = jobs[0].get("current_step")
        return {
            "has_full_job": has_full,
            "has_any_job": len(jobs) > 0,
            "active_models": active_models,
            "current_step": current_step,
            "jobs": jobs,
        }
    finally:
        broker.close()


def resolve_rcp_upload(app_conf, file_bytes: bytes, filename: str) -> tuple[str, bool]:
    """
    Calcule le hash SHA-256 du fichier.
    Retourne (existing_filename, True) si le fichier existe déjà,
    sinon (hashed_filename, False).
    """
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    stem, _ = os.path.splitext(os.path.basename(filename))
    hashed_filename = f"{slugify(stem, separator='_')}_{file_hash[:8]}.pdf"

    if app_conf.rcp.display_type == "mongodb":
        client = Mongodb(app_conf)
        try:
            cached = client.get_document_cache(file_hash)
        finally:
            client.close()
        if cached and cached.get("file"):
            cached_file = cached["file"]
            if os.path.exists(os.path.join(app_conf.rcp.path, cached_file)):
                return cached_file, True

    if os.path.exists(os.path.join(app_conf.rcp.path, hashed_filename)):
        return hashed_filename, True

    return hashed_filename, False


def full_read_mtd_agents(app_conf, filename: str, logger, replace: bool = True):
    logger.info(f"Start reading {filename} ...")
    fiche_rcp = PatientMDTForm(config=app_conf, document=filename)
    fiche_rcp.read_all_models()
    fiche_rcp.insert_datas_in_db()
    del fiche_rcp
    gc.collect()
    try:
        unload_active_models(app_conf)
    except Exception as e:
        logger.warning(f"Error unloading models after full read: {e}")


def ingest_and_associate_rcp(
    app_conf,
    filename: str,
    patient_id: str | None = None,
    logger=None,
    run_admin_ai: bool = True,
    callbacks: list | None = None,
    unload_models: bool = True,
) -> tuple[dict, dict]:
    """
    Indexes the RCP document in RAG, runs the PatientAdministrative AI extraction,
    and associates or creates the corresponding Patient in MongoDB.
    """
    from src.application.patient import process_patient_association

    if logger is None:
        logger = app_conf.set_logger("oncoflow.patient")

    logger.info(
        f"Ingesting and associating RCP {filename} (target_patient_id={patient_id})..."
    )
    fiche_rcp = PatientMDTForm(config=app_conf, document=filename)
    patient = process_patient_association(
        form=fiche_rcp,
        target_patient_id=patient_id,
        run_admin_ai=run_admin_ai,
        callbacks=callbacks,
    )
    mtd_datas = dict(fiche_rcp.mtd_datas)
    patient_dict = patient.model_dump()
    del fiche_rcp
    gc.collect()
    if unload_models:
        try:
            unload_active_models(app_conf)
        except Exception as e:
            logger.warning(f"Error unloading models after ingest: {e}")
    return mtd_datas, patient_dict


def delete_document(app_conf, filename, delete_file: bool = True):
    try:
        broker = SqliteQueueBroker(app_conf)
        try:
            broker.delete_jobs_for_file(filename)
        finally:
            broker.close()
    except Exception:
        pass
    if app_conf.rcp.display_type == "mongodb":
        client = Mongodb(app_conf)
        client.remove_file_from_patient(filename)
        client.delete_docs(
            collections=["rcp_info", "rcp_metadata", "document_cache"],
            filter={"file": filename},
        )
        if delete_file:
            if os.path.exists(f"{app_conf.rcp.path}/{filename}"):
                os.remove(f"{app_conf.rcp.path}/{filename}")
        client.close()
