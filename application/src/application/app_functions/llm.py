import json
import urllib.request


def unload_active_models(app_conf):
    """
    Unload active models from Ollama to release GPU/CPU resources.
    This supports both direct Ollama usage and LiteLLM configurations.
    """
    logger = app_conf.set_logger("cleanup")

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

    unique_models = []
    for m in models_to_unload:
        if m and m not in unique_models:
            unique_models.append(m)

    if not unique_models:
        return

    url = app_conf.llm.url
    port = app_conf.llm.port

    endpoints_to_try = [
        (url, port),
        (url, "11434"),
        ("http://127.0.0.1", "11434"),
        ("http://localhost", "11434"),
        ("http://ollama", "11434"),
    ]

    unique_endpoints = []
    for host, p in endpoints_to_try:
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
                        with urllib.request.urlopen(req, timeout=1.5) as response:
                            response.read()
                        logger.info(f"Successfully unloaded '{name}' via {endpoint}")
                        unloaded = True
                        break
                    except Exception:
                        pass
                if unloaded:
                    break
