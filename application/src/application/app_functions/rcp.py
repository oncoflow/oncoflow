import gc
import hashlib
import os

from slugify import slugify

from src.application.app_functions.llm import unload_active_models
from src.domain.patient_mdt_form import PatientMDTForm
from src.infrastructure.documents.mongodb import Mongodb


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
