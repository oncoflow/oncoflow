import os
import gc
from src.infrastructure.documents.mongodb import Mongodb
from src.domain.patient_mdt_form import PatientMDTForm


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


def delete_patient_dossier(
    app_conf, patient_id: str, delete_files: bool = True
) -> None:
    """
    Deletes a patient dossier and all its associated RCP documents from MongoDB and disk.
    """
    if app_conf.rcp.display_type == "mongodb":
        client = Mongodb(app_conf)
        patient_doc = client.get_patient(patient_id)
        files_to_delete = set()
        if patient_doc and isinstance(patient_doc.get("files"), list):
            files_to_delete.update(patient_doc["files"])

        rcp_docs = list(
            client.database["rcp_info"].find({"patient_id": patient_id}, {"file": 1})
        )
        for doc in rcp_docs:
            if doc.get("file"):
                files_to_delete.add(doc["file"])

        for fname in files_to_delete:
            client.delete_docs(
                collections=["rcp_info", "rcp_metadata", "document_cache"],
                filter={"file": fname},
            )
            if delete_files and os.path.exists(f"{app_conf.rcp.path}/{fname}"):
                os.remove(f"{app_conf.rcp.path}/{fname}")

        client.delete_docs(collections=["patients"], filter={"patient_id": patient_id})
        client.close()


def unload_active_models(app_conf):
    """
    Unload active models from Ollama to release GPU/CPU resources.
    This supports both direct Ollama usage and LiteLLM configurations.
    """
    import urllib.request
    import json

    logger = app_conf.set_logger("cleanup")

    # Check configured models
    models_to_unload = []

    # 1. Main reasoning models
    if hasattr(app_conf.llm, "models") and app_conf.llm.models:
        for m in app_conf.llm.models.split(","):
            models_to_unload.append(m.strip())

    # 2. OCR models
    if hasattr(app_conf.llm, "ocrmodels") and app_conf.llm.ocrmodels:
        for m in app_conf.llm.ocrmodels.split(","):
            models_to_unload.append(m.strip())

    # 3. Embeddings models
    if hasattr(app_conf.llm, "embeddings") and app_conf.llm.embeddings:
        for m in app_conf.llm.embeddings.split(","):
            models_to_unload.append(m.strip())

    # Deduplicate
    unique_models = []
    for m in models_to_unload:
        if m and m not in unique_models:
            unique_models.append(m)

    if not unique_models:
        return

    # Determine backend hosts to check
    # We will try:
    # 1. Configured url and port
    # 2. Configured url with default Ollama port (11434)
    # 3. Standard localhost / 127.0.0.1 on port 11434
    # 4. Docker hostname 'ollama' on port 11434 (commonly used in compose)
    url = app_conf.llm.url
    port = app_conf.llm.port

    endpoints_to_try = [
        (url, port),
        (url, "11434"),
        ("http://127.0.0.1", "11434"),
        ("http://localhost", "11434"),
        ("http://ollama", "11434"),
    ]

    # Deduplicate endpoints
    unique_endpoints = []
    for host, p in endpoints_to_try:
        # Normalize host string
        if not host.startswith("http://") and not host.startswith("https://"):
            host = f"http://{host}"
        host = host.rstrip("/")
        normalized = (host, str(p))
        if normalized not in unique_endpoints:
            unique_endpoints.append(normalized)

    logger.info(
        f"Initiating clean shutdown: unloading models {unique_models} from local backends..."
    )

    for model_name in unique_models:
        # Strip prefixes like "openai/" or "ollama/" for model name lookups in Ollama
        names_to_try = [model_name]
        if "/" in model_name:
            names_to_try.append(model_name.split("/")[-1])

        for name in names_to_try:
            unloaded = False
            for host, p in unique_endpoints:
                for path in ["/api/chat", "/api/generate"]:
                    try:
                        endpoint = f"{host}:{p}{path}"
                        data = json.dumps({"model": name, "keep_alive": 0}).encode(
                            "utf-8"
                        )
                        req = urllib.request.Request(
                            endpoint,
                            data=data,
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                        # Use a small timeout to avoid blocking shutdown on dead servers
                        with urllib.request.urlopen(req, timeout=1.5) as response:
                            response.read()
                        logger.info(f"Successfully unloaded '{name}' via {endpoint}")
                        unloaded = True
                        break  # Successfully reached and sent command, stop trying other paths
                    except Exception:
                        pass
                if unloaded:
                    break  # Model successfully unloaded, check next model
