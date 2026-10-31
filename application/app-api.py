from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI

from src.infrastructure.documents.mongodb import close_all_mongo_clients
from src.infrastructure.queue import get_global_queue_manager
from src.models.queue import HealthResponse
from src.routers.agents import router as agents_router
from src.routers.bug_reports import router as bug_reports_router
from src.routers.dependencies import (
    AllowedDomainMiddleware,
    get_base_config,
    verify_api_token,
)
from src.routers.patientmdtform import router as patientmdtform_router
from src.routers.queue import router as queue_router
from src.routers.resources import router as resources_router

app_conf = get_base_config()
logger = app_conf.set_logger("oncoflow.api")

if app_conf.api_token is None:
    if not app_conf.dev_mode:
        raise RuntimeError(
            "APP_API_TOKEN est obligatoire hors mode développement (APP_DEV_MODE=false)."
        )
    logger.warning(
        "APP_API_TOKEN non défini : l'API est accessible sans authentification (dev mode)."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Starting Cross-Domain Oncoflow FastAPI App (allowed_domains={app_conf.enabled_domains_list}, "
        f"batch_size={app_conf.queue.batch_size})..."
    )
    queue_manager = get_global_queue_manager(app_conf, auto_start_workers=True)
    try:
        recovered = queue_manager.recover_unfinished_from_mongodb()
        if recovered:
            logger.info(
                f"Recovered {recovered} unfinished RCP file(s) into the PriorityQueue."
            )
    except Exception as exc:
        logger.warning(f"Startup queue recovery skipped: {exc}")

    yield

    logger.info("Shutting down Oncoflow FastAPI App & PriorityQueue workers...")
    queue_manager.shutdown()
    try:
        from src.application.app_functions import unload_active_models

        unload_active_models(app_conf)
    except Exception as e:
        logger.warning(f"Error unloading active models during shutdown: {e}")
    close_all_mongo_clients()


app = FastAPI(
    title="Oncoflow Cross-Domain API",
    description=(
        "API REST multi-domaines versionnée pour la gestion des RCP (Oncologie, SMA...) "
        "et de la file de traitement `queue.PriorityQueue` intégrée."
    ),
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    # Spécification OpenAPI versionnée (utilisée aussi par /docs et /redoc)
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(AllowedDomainMiddleware)


@app.get("/health", tags=["system"], response_model=HealthResponse)
def healthcheck():
    """Check the health status of the Cross-Domain API and its integrated priority queue."""
    manager = get_global_queue_manager()
    return {
        "status": "ok",
        "allowed_domains": app_conf.enabled_domains_list,
        "queue": manager.get_queue_stats(),
    }


# Include versioned routers (all protected by the shared API token)
_protected = [Depends(verify_api_token)]
app.include_router(patientmdtform_router, prefix="/api/v1", dependencies=_protected)
app.include_router(agents_router, prefix="/api/v1", dependencies=_protected)
app.include_router(resources_router, prefix="/api/v1", dependencies=_protected)
app.include_router(queue_router, prefix="/api/v1", dependencies=_protected)
app.include_router(bug_reports_router, prefix="/api/v1", dependencies=_protected)

if __name__ == "__main__":
    # Loopback by default (APP_API_HOST); containers set 0.0.0.0 on a private network.
    uvicorn.run(app, host=app_conf.api_host, port=8000, reload=False)
