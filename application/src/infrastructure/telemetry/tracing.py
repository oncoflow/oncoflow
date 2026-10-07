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


def ensure_tracing_destination(
    experiment_id: str | None = None,
    experiment_name: str | None = None,
) -> str | None:
    """Verrouille definitivement la destination des traces MLflow sur l'experimentation voulue (global + context-local + env)."""
    import os
    import mlflow

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI") or "http://localhost:5000"
    try:
        mlflow.set_tracking_uri(tracking_uri)
    except Exception:
        pass

    exp_id = experiment_id or os.environ.get("MLFLOW_EXPERIMENT_ID")
    exp_name = (
        experiment_name
        or os.environ.get("MLFLOW_EXPERIMENT_NAME")
        or "oncoflow-agents-evaluation"
    )

    try:
        # Toujours activer l'experimentation par son nom pour que MLflow
        # positionne son etat fluent (_active_experiment_id) sur la bonne experience
        try:
            exp = mlflow.set_experiment(exp_name)
            exp_id_str = str(exp.experiment_id)
        except Exception as e_exp:
            logger.warning("Echec mlflow.set_experiment(%s) : %s", exp_name, e_exp)
            exp_id_str = str(exp_id or "1")

        os.environ["MLFLOW_EXPERIMENT_NAME"] = exp_name
        os.environ["MLFLOW_EXPERIMENT_ID"] = exp_id_str
        os.environ["MLFLOW_TRACING_DESTINATION"] = exp_id_str

        if hasattr(mlflow, "tracing") and hasattr(mlflow.tracing, "set_destination"):
            from mlflow.entities.trace_location import MlflowExperimentLocation

            try:
                loc = MlflowExperimentLocation(exp_id_str)
            except TypeError:
                loc = MlflowExperimentLocation(experiment_id=exp_id_str)

            # 1. Verrouillage global (essentiel pour les worker threads et LangChain autolog)
            try:
                mlflow.tracing.set_destination(loc)
            except Exception:
                try:
                    mlflow.tracing.set_destination(loc, context_local=False)
                except Exception:
                    pass

            # 2. Verrouillage contextuel (pour la tâche asynchrone / thread courant)
            try:
                mlflow.tracing.set_destination(loc, context_local=True)
            except Exception:
                pass

            logger.info(
                "Destination traces MLflow verrouillee sur experience ID=%s (%s)",
                exp_id_str,
                exp_name,
            )
        return exp_id_str
    except Exception as e:
        logger.warning("Configuration destination traces MLflow echouee : %s", e)
        return None


def init_telemetry(config: Any, force: bool = False) -> None:
    """Initialise OpenTelemetry et l'autologging MLflow (traces et sessions)."""
    global _telemetry_initialized

    telemetry_cfg = getattr(config, "telemetry", None)
    if telemetry_cfg and not telemetry_cfg.enabled:
        logger.info("Telemetrie desactivee par configuration.")
        return

    import os
    import mlflow

    endpoint = os.environ.get("MLFLOW_TRACKING_URI") or getattr(
        telemetry_cfg, "endpoint", "http://localhost:5000"
    )
    mlflow.set_tracking_uri(endpoint)

    exp_name = (
        os.environ.get("MLFLOW_EXPERIMENT_NAME")
        or getattr(telemetry_cfg, "experiment_name", None)
        or "oncoflow-agents-evaluation"
    )

    # Verrouillage de l'experience et de la destination des traces
    ensure_tracing_destination(experiment_name=exp_name)

    if _telemetry_initialized and not force:
        return

    # Configuration d'autologging LangChain et OpenAI
    try:
        autolog_langchain = getattr(telemetry_cfg, "autolog_langchain", True)
        if autolog_langchain:
            try:
                try:
                    mlflow.langchain.autolog(
                        log_traces=True,
                        run_tracer_inline=True,
                    )
                except TypeError:
                    mlflow.langchain.autolog(log_traces=True)
                logger.info(
                    "MLflow LangChain Autologging active avec traces OpenTelemetry."
                )
            except Exception as e:
                logger.warning("Impossible d'activer mlflow.langchain.autolog: %s", e)

        autolog_openai = getattr(telemetry_cfg, "autolog_openai", True)
        if autolog_openai:
            try:
                mlflow.openai.autolog(log_traces=True)
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
    ensure_tracing_destination()

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


def flush_telemetry_traces(terminate: bool = False) -> None:
    """Force l'exportation et le flush de toutes les traces en attente vers le serveur MLflow."""
    try:
        from mlflow.tracing.processor.base_mlflow import flush_all_batch_processors

        flush_all_batch_processors(terminate=terminate)
    except Exception:
        pass

    try:
        import mlflow

        if hasattr(mlflow, "flush_trace_async_logging"):
            mlflow.flush_trace_async_logging(terminate=terminate)
    except Exception as e:
        logger.debug("Flush des traces MLflow ignore ou indisponible : %s", e)
