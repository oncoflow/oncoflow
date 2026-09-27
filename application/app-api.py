import os
from contextlib import asynccontextmanager

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
os.environ["DOCLING_DEVICE"] = "cpu"

import uvicorn
from fastapi import FastAPI

from src.application.config import AppConfig
from src.routers.rcp import router as rcp_router
from src.routers.agents import router as agents_router
from src.routers.resources import router as resources_router

app_conf = AppConfig()
logger = app_conf.set_logger("oncoflow.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Oncoflow FastAPI App...")
    yield
    logger.info("Shutting down Oncoflow FastAPI App...")
    try:
        from src.application.app_functions import unload_active_models

        unload_active_models(app_conf)
    except Exception as e:
        logger.warning(f"Error unloading active models during shutdown: {e}")


app = FastAPI(
    title="Oncoflow API",
    description="API REST versionnée pour la gestion des RCP d'oncologie et des agents IA.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# Expose OpenAPI JSON versionné explicitement
@app.get("/api/v1/openapi.json", include_in_schema=False)
def get_openapi_json():
    return app.openapi()


# Include versioned routers
app.include_router(rcp_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(resources_router, prefix="/api/v1")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
