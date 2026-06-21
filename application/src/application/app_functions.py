import os
from src.infrastructure.documents.mongodb import Mongodb
from src.domain.patient_mdt_form import PatientMDTForm


def full_read_mtd_agents(app_conf, filename: str, logger, replace: bool = True):
    logger.info(f"Start reading {filename} ...")
    fiche_rcp = PatientMDTForm(config=app_conf, document=filename)
    fiche_rcp.read_all_models()
    fiche_rcp.insert_datas_in_db()


def delete_document(app_conf, filename, delete_file: bool = True):
    if app_conf.rcp.display_type == "mongodb":
        client = Mongodb(app_conf)
        client.delete_docs(
            collections=["rcp_info", "rcp_metadata"], filter={"file": filename}
        )
        if delete_file:
            if os.path.exists(f"{app_conf.rcp.path}/{filename}"):
                os.remove(f"{app_conf.rcp.path}/{filename}")
        client.close()


def unload_active_models(app_conf):
    """
    Unload active models from Ollama to release GPU/CPU resources.
    This supports both direct Ollama usage and LiteLLM configurations.
    """
    import urllib.request
    import json
    import logging

    logger = logging.getLogger("cleanup")

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
