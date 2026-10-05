"""Module de configuration OpenTelemetry et d'autologging des traces et sessions MLflow."""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("Oncoflow.Telemetry")

# Contexte de session asynchrone / multi-thread
_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_session_id", default=None
)

_telemetry_initialized = False


def set_session_id(session_id: str | None) -> None:
    """Definit l'identifiant de la session courante."""
    _current_session_id.set(session_id)


def get_session_id() -> str | None:
    """Recupere l'identifiant de la session courante."""
    return _current_session_id.get()


def get_tracer(name: str = "oncoflow"):
    """Retourne un tracer OpenTelemetry."""
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except Exception:
        return None


def init_telemetry(config: Any) -> None:
    """Initialise OpenTelemetry et l'autologging MLflow (traces et sessions)."""
    global _telemetry_initialized
    if _telemetry_initialized:
        return

    telemetry_cfg = getattr(config, "telemetry", None)
    if telemetry_cfg and not telemetry_cfg.enabled:
        logger.info("Telemetrie desactivee par configuration.")
        return

    # 1. Initialisation d'OpenTelemetry
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        service_name = getattr(telemetry_cfg, "service_name", "oncoflow")
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.namespace": "clinical-oncology",
            }
        )
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)
        logger.info(
            "OpenTelemetry TracerProvider initialise pour le service : %s",
            service_name,
        )
    except Exception as e:
        logger.warning("Initialisation OpenTelemetry SDK ignoree ou echouee : %s", e)

    # 2. Configuration d'autologging MLflow Tracing
    try:
        import mlflow

        endpoint = getattr(telemetry_cfg, "endpoint", "http://127.0.0.1:5000")
        mlflow.set_tracking_uri(endpoint)

        autolog_langchain = getattr(telemetry_cfg, "autolog_langchain", True)
        if autolog_langchain:
            try:
                mlflow.langchain.autolog(
                    log_traces=True,
                    log_input_examples=True,
                    log_models=False,
                )
                logger.info(
                    "MLflow LangChain Autologging active avec traces OpenTelemetry."
                )
            except Exception as e:
                logger.warning("Impossible d'activer mlflow.langchain.autolog: %s", e)

        autolog_openai = getattr(telemetry_cfg, "autolog_openai", True)
        if autolog_openai:
            try:
                mlflow.openai.autolog(
                    log_traces=True,
                    log_models=False,
                )
                logger.info(
                    "MLflow OpenAI Autologging active avec traces OpenTelemetry."
                )
            except Exception as e:
                logger.warning("Impossible d'activer mlflow.openai.autolog: %s", e)

    except Exception as e:
        logger.warning("Connexion ou instrumentation MLflow non disponible : %s", e)

    _telemetry_initialized = True


def get_langchain_config(
    agent_name: str | None = None,
    session_id: str | None = None,
    callbacks: list | None = None,
    additional_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Genere une configuration RunnableConfig enrichie avec session et tags de trace."""
    eff_session = session_id or get_session_id()
    tags = []
    if agent_name:
        tags.append(agent_name)

    metadata: dict[str, Any] = {}
    if additional_metadata:
        metadata.update(additional_metadata)

    if eff_session:
        metadata["session_id"] = eff_session
        metadata["mlflow.trace.sessionId"] = eff_session
        metadata["session.id"] = eff_session
        tags.append(f"session:{eff_session}")

    cfg: dict[str, Any] = {
        "callbacks": callbacks or [],
        "tags": tags,
        "metadata": metadata,
    }
    return cfg


@contextmanager
def trace_session(session_id: str, tags: dict[str, Any] | None = None):
    """Gestionnaire de contexte pour assigner une session aux traces d'un bloc d'execution."""
    token = _current_session_id.set(session_id)
    try:
        import mlflow

        if hasattr(mlflow, "tracing") and hasattr(
            mlflow.tracing, "update_current_trace"
        ):
            trace_tags = {
                "mlflow.trace.sessionId": session_id,
                "session_id": session_id,
            }
            if tags:
                trace_tags.update(tags)
            try:
                mlflow.tracing.update_current_trace(tags=trace_tags)
            except Exception:
                pass
    except Exception:
        pass

    try:
        yield session_id
    finally:
        _current_session_id.reset(token)
