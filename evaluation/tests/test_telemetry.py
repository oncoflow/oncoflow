"""Tests unitaires pour le module de telemetrie et OpenTelemetry / MLflow Tracing."""

from __future__ import annotations

from unittest.mock import patch

from src.application.config import AppConfig
from src.infrastructure.telemetry.tracing import (
    get_langchain_config,
    get_session_id,
    init_telemetry,
    set_session_id,
    trace_session,
)


def test_session_id_context():
    set_session_id("session-test-123")
    assert get_session_id() == "session-test-123"

    with trace_session("session-test-456") as s:
        assert s == "session-test-456"
        assert get_session_id() == "session-test-456"

    # Restauration apres context manager
    assert get_session_id() == "session-test-123"
    set_session_id(None)
    assert get_session_id() is None


def test_get_langchain_config():
    cfg = get_langchain_config(
        agent_name="pancreas expert",
        session_id="eval-session-001",
        callbacks=["mock_callback"],
        additional_metadata={"custom_key": "custom_val"},
    )

    assert "pancreas expert" in cfg["tags"]
    assert "session:eval-session-001" in cfg["tags"]
    assert cfg["metadata"]["session_id"] == "eval-session-001"
    assert cfg["metadata"]["mlflow.trace.sessionId"] == "eval-session-001"
    assert cfg["metadata"]["custom_key"] == "custom_val"
    assert "mock_callback" in cfg["callbacks"]


@patch("src.infrastructure.telemetry.tracing.mlflow")
def test_init_telemetry(mock_mlflow):
    app_config = AppConfig()
    app_config.telemetry.enabled = True
    app_config.telemetry.endpoint = "http://localhost:5000"

    init_telemetry(app_config)

    mock_mlflow.set_tracking_uri.assert_called_with("http://localhost:5000")
    mock_mlflow.set_experiment.assert_called_with("oncoflow-agents-evaluation")
    mock_mlflow.langchain.autolog.assert_called_once()
    mock_mlflow.openai.autolog.assert_called_once()


@patch("src.infrastructure.telemetry.tracing.mlflow")
def test_flush_telemetry_traces(mock_mlflow):
    from unittest.mock import MagicMock
    from src.infrastructure.telemetry.tracing import flush_telemetry_traces

    mock_mlflow.flush_trace_async_logging = MagicMock()
    flush_telemetry_traces(terminate=False)
    mock_mlflow.flush_trace_async_logging.assert_called_once_with(terminate=False)


@patch("src.infrastructure.telemetry.tracing.mlflow")
def test_ensure_tracing_destination(mock_mlflow):
    import os
    from unittest.mock import MagicMock
    from src.infrastructure.telemetry.tracing import ensure_tracing_destination

    mock_exp = MagicMock()
    mock_exp.experiment_id = "1"
    mock_mlflow.set_experiment.return_value = mock_exp

    exp_id = ensure_tracing_destination(experiment_name="oncoflow-agents-evaluation")

    assert exp_id == "1"
    assert os.environ.get("MLFLOW_EXPERIMENT_ID") == "1"
    assert os.environ.get("MLFLOW_TRACING_DESTINATION") == "1"
    mock_mlflow.tracing.set_destination.assert_called()
