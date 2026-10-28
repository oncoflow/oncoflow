from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.application.config import AppConfig
from src.infrastructure.documents.db_interface import AllowedDomainMiddleware
from src.infrastructure.queue import get_global_queue_manager
from src.routers.agents import router as agents_router
from src.routers.queue import router as queue_router
from src.routers.rcp import router as rcp_router
from src.routers.resources import router as resources_router

app_conf = AppConfig()
logger = app_conf.set_logger("oncoflow.api")


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
)

app.add_middleware(AllowedDomainMiddleware)


@app.get("/health", tags=["system"])
def healthcheck():
    """Vérifie l'état de santé de l'API Cross-Domains et de la file de traitement intégrée."""
    manager = get_global_queue_manager()
    return {
        "status": "ok",
        "allowed_domains": app_conf.enabled_domains_list,
        "queue": manager.get_queue_stats(),
    }


# Expose OpenAPI JSON versionné explicitement
@app.get("/api/v1/openapi.json", include_in_schema=False)
def get_openapi_json():
    return app.openapi()


# Include versioned routers
app.include_router(rcp_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(resources_router, prefix="/api/v1")
app.include_router(queue_router, prefix="/api/v1")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
